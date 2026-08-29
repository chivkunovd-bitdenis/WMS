"""Хотфикс 29.08.2026 — учёт товара по заказам FBS.

Найдено на боевых данных 29.08.2026:

Дефект 1 (`_write_off_sold_order`): списание со склада жило только в
завершении упаковки поставки. Заказ, закрывшийся статусом WB "sold" в обход
упаковки, физически уезжал, а в учёте оставался — на бою нашли 14 таких.

Дефект 2 (`reverse_fbs_shipment_if_needed`): при отмене остаток возвращался на
склад по факту "было списание и его ещё не отменяли", без проверки, что
посылку уже забрал WB. На бою — 275 ложных возвратов, все по заказам со
статусом поставщика "complete" (собрано и передано).

TC-NEW-FBS-WRITEOFF-SOLD-001 — sold-заказ в обход упаковки списывается один раз
TC-NEW-FBS-REVERSAL-COMPLETE-001 — отмена по complete-заказу не возвращает остаток
TC-NEW-FBS-REVERSAL-COMPLETE-002 — отмена по не-complete заказу остаток возвращает
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_ASSEMBLING,
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_DONE,
    FBS_ORDER_STATUS_PACKED,
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_NO_STOCK,
    FbsOrder,
)
from app.models.fbs_order_pick import FbsOrderPick
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_supply import FbsSupply
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import (
    MOVEMENT_TYPE_FBS_SHIPMENT,
    MOVEMENT_TYPE_INBOUND_INTAKE,
    InventoryMovement,
)
from app.models.product import Product
from app.services import inventory_service
from app.services.fbs_cancellation_service import reverse_fbs_shipment_if_needed
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.wb_marketplace_orders_service import (
    _apply_wb_status_to_order,
    upsert_order_from_wb_row,
)
from tests.fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID, seed_fbs_warehouse_binding


async def _register_ff_admin(async_client: AsyncClient) -> tuple[dict[str, str], str, uuid.UUID]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS writeoff {suffix}",
            "slug": f"fbs-writeoff-{suffix}",
            "admin_email": f"fbs-writeoff-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    return headers, suffix, tenant_id


async def _setup_seller_with_token(
    async_client: AsyncClient,
    headers: dict[str, str],
    suffix: str,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    seller = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": f"Seller {suffix}"},
    )
    assert seller.status_code in (200, 201), seller.text
    seller_id = uuid.UUID(seller.json()["id"])
    tok = await async_client.patch(
        f"/integrations/wildberries/sellers/{seller_id}/tokens",
        headers=headers,
        json={"marketplace_api_token": "wb-marketplace-token"},
    )
    assert tok.status_code == 200, tok.text
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WH", "code": f"wh-{suffix[-8:]}"},
    )
    assert warehouse.status_code in (200, 201), warehouse.text
    warehouse_id = uuid.UUID(warehouse.json()["id"])
    location = await async_client.post(
        f"/warehouses/{warehouse_id}/locations",
        headers=headers,
        json={"code": f"A-{suffix[-6:]}"},
    )
    assert location.status_code in (200, 201), location.text
    source_location_id = uuid.UUID(location.json()["id"])
    return seller_id, warehouse_id, source_location_id


def _wb_order_row(*, order_id: int, article: str) -> dict[str, Any]:
    return {
        "id": order_id,
        "rid": f"rid-{order_id}",
        "createdAt": "2026-07-01T12:00:00+03:00",
        "nmId": 900001,
        "chrtId": 555,
        "article": article,
        "skus": [f"BAR-{order_id}"],
        "price": 199900,
        "cargoType": 1,
        "officeId": 42,
        "isLegal": False,
        "warehouseId": DEFAULT_WB_WAREHOUSE_ID,
    }


# TC-NEW-FBS-WRITEOFF-SOLD-001 — sold-заказ в обход упаковки списывается ровно один раз
@pytest.mark.asyncio
async def test_write_off_sold_order_that_skipped_packaging_happens_once(
    async_client: AsyncClient,
) -> None:
    """Дефект 1: заказ подобран (лежит в ячейке сортировки), но так и не был
    упакован (в системе нет `FbsShipmentReversalLedger`, как это бывает у
    заказов, закрытых WB напрямую).

    Given: у заказа есть подбор (`FbsOrderPick`) в ячейку сортировки с 1 штукой
           остатка, но списания по нему ещё не было.
    When: приходит статус WB "sold" (обход синка статусов) — дважды подряд,
          как это происходит при повторном опросе WB.
    Then: остаток списывается один раз (движение `fbs_shipment` на -1,
          `FbsShipmentReversalLedger` с ровно одной строкой на заказ);
          повторный обход находит уже существующую запись в журнале и
          повторного списания не делает — остаток и число движений не меняются.
    """
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, source_location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
        )
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Sold-bypass product",
            sku_code=f"SOLD-{suffix[-8:]}",
            wb_barcode=f"SOLD-BAR-{suffix[-8:]}",
        )
        session.add(product)
        await session.flush()

        order, _created = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_id,
            _wb_order_row(order_id=970001, article=f"ART-{suffix}"),
        )
        order.product_id = product.id
        order.status = FBS_ORDER_STATUS_ASSEMBLING

        supply = FbsSupply(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            wb_supply_id=f"skip-pack-{suffix[-8:]}",
            name="Supply that never got packaged",
            delivery_type="warehouse_sc",
        )
        session.add(supply)
        await session.flush()
        order.supply_id = supply.id

        # Товар пришёл на склад и был подобран в сортировку — обычное
        # состояние перед упаковкой. В найденных на бою 14 случаях на этом
        # шаге всё и заканчивалось: упаковку заказ не проходил.
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product.id,
            storage_location_id=source_location_id,
            quantity_delta=1,
            movement_type=MOVEMENT_TYPE_INBOUND_INTAKE,
            actor_user_id=None,
        )
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
        await inventory_service.transfer_on_hand_between_locations(
            session,
            tenant_id=tenant_id,
            from_storage_location_id=source_location_id,
            to_storage_location_id=sorting.id,
            product_id=product.id,
            quantity=1,
            actor_user_id=None,
        )
        session.add(
            FbsOrderPick(
                tenant_id=tenant_id,
                fbs_order_id=order.id,
                fbs_supply_id=supply.id,
                source_storage_location_id=source_location_id,
                sorting_storage_location_id=sorting.id,
                product_id=product.id,
                picked_at=datetime.now(UTC),
                scan_idempotency_key=f"pick-{order.id}",
            )
        )
        await session.commit()
        order_id = order.id
        product_id = product.id
        sorting_id = sorting.id

    # Первый обход синка статусов: заказ выкуплен.
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        await _apply_wb_status_to_order(
            session, order, "sold", supplier_status="complete", actor_user_id=None
        )
        await session.commit()

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.status == FBS_ORDER_STATUS_DONE

        ledgers = list(
            (
                await session.execute(
                    select(FbsShipmentReversalLedger).where(
                        FbsShipmentReversalLedger.fbs_order_id == order_id
                    )
                )
            ).scalars()
        )
        assert len(ledgers) == 1
        assert ledgers[0].quantity == 1
        assert ledgers[0].storage_location_id == sorting_id
        assert ledgers[0].reversed_at is None

        write_off_count = await session.scalar(
            select(func.count(InventoryMovement.id)).where(
                InventoryMovement.tenant_id == tenant_id,
                InventoryMovement.product_id == product_id,
                InventoryMovement.movement_type == MOVEMENT_TYPE_FBS_SHIPMENT,
            )
        )
        assert write_off_count == 1

        balance = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == sorting_id,
            )
        )
        assert balance is not None
        assert int(balance.quantity) == 0

    # Второй обход синка статусов с тем же статусом — второго списания быть не должно.
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        await _apply_wb_status_to_order(
            session, order, "sold", supplier_status="complete", actor_user_id=None
        )
        await session.commit()

    async with SessionLocal() as session:
        ledgers = list(
            (
                await session.execute(
                    select(FbsShipmentReversalLedger).where(
                        FbsShipmentReversalLedger.fbs_order_id == order_id
                    )
                )
            ).scalars()
        )
        assert len(ledgers) == 1, "повторный обход не должен создавать вторую запись"

        write_off_count = await session.scalar(
            select(func.count(InventoryMovement.id)).where(
                InventoryMovement.tenant_id == tenant_id,
                InventoryMovement.product_id == product_id,
                InventoryMovement.movement_type == MOVEMENT_TYPE_FBS_SHIPMENT,
            )
        )
        assert write_off_count == 1, "повторный обход не должен списывать второй раз"

        balance = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == sorting_id,
            )
        )
        assert balance is not None
        assert int(balance.quantity) == 0


async def _seed_order_with_existing_write_off(
    async_client: AsyncClient,
    *,
    supplier_status: str,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Заказ, уже списанный (как при упаковке поставки), готовый к отмене.

    Возвращает (order_id, tenant_id, product_id, storage_location_id).
    """
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Already shipped product",
            sku_code=f"SHIP-{supplier_status}-{suffix[-8:]}",
            wb_barcode=f"SHIP-BAR-{supplier_status}-{suffix[-8:]}",
        )
        session.add(product)
        await session.flush()

        now = datetime.now(UTC)
        order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product_id=product.id,
            wb_order_id=int(f"98{suffix[-6:]}"),
            status=FBS_ORDER_STATUS_PACKED,
            supplier_status=supplier_status,
            created_at_wb=now,
            deadline_at=now + timedelta(hours=24),
            mapping_status=MAPPING_STATUS_MAPPED,
            reserve_status=RESERVE_STATUS_NO_STOCK,
        )
        session.add(order)
        await session.flush()

        # Один экземпляр лежал в ячейке, упаковка списала его — то же самое,
        # что делает `apply_fbs_supply_write_off` при завершении поставки.
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product.id,
            storage_location_id=location_id,
            quantity_delta=1,
            movement_type=MOVEMENT_TYPE_INBOUND_INTAKE,
            actor_user_id=None,
        )
        write_off = await inventory_service.apply_fbs_supply_write_off(
            session,
            tenant_id=tenant_id,
            product_id=product.id,
            storage_location_id=location_id,
            quantity=1,
            actor_user_id=None,
        )
        await session.flush()
        shipment_movement_id = write_off.id
        session.add(
            FbsShipmentReversalLedger(
                tenant_id=tenant_id,
                fbs_order_id=order.id,
                product_id=product.id,
                storage_location_id=location_id,
                quantity=1,
                # Возврат делается только по записи, которая помнит движение
                # списания: без него сторнировать нечего.
                shipment_movement_id=shipment_movement_id,
            )
        )
        await session.commit()
        order_id = order.id
        product_id = product.id

    return order_id, tenant_id, product_id, location_id


# TC-NEW-FBS-REVERSAL-COMPLETE-001 — отмена по complete-заказу не возвращает остаток
@pytest.mark.asyncio
async def test_reversal_blocked_when_supplier_status_complete(
    async_client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Дефект 2: `supplier_status == "complete"` значит посылку уже забрал WB.

    Given: заказ уже списан (запись в `fbs_shipment_reversal_ledger` есть,
           `reversed_at` пуст), `supplier_status == "complete"` — ровно
           признак, по которому на бою нашли 275 ложных возвратов.
    When: WB присылает по этому заказу статус отмены.
    Then: остаток на складе НЕ возвращается (баланс и число движений
          `fbs_shipment` не меняются), запись журнала помечается обработанной
          (`reversed_at` проставлен), но без движения (`reversal_movement_id`
          пуст) — иначе она пыталась бы вернуться на каждом следующем обходе;
          ограничение: в лог пишется предупреждение с номером заказа, продавцом
          и товаром, чтобы такие случаи были видны.
    """
    caplog.set_level("WARNING", logger="app.services.fbs_cancellation_service")
    order_id, tenant_id, product_id, location_id = await _seed_order_with_existing_write_off(
        async_client, supplier_status="complete"
    )

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        await _apply_wb_status_to_order(
            session, order, "cancel", supplier_status="complete", actor_user_id=None
        )
        await session.commit()

    assert "already handed to WB" in caplog.text
    assert str(order_id) in caplog.text

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.status == FBS_ORDER_STATUS_CANCELLED

        ledger = await session.scalar(
            select(FbsShipmentReversalLedger).where(
                FbsShipmentReversalLedger.fbs_order_id == order_id
            )
        )
        assert ledger is not None
        assert ledger.reversed_at is not None, "запись должна быть помечена обработанной"
        assert ledger.reversal_movement_id is None, "движения по складу быть не должно"

        movement_count = await session.scalar(
            select(func.count(InventoryMovement.id)).where(
                InventoryMovement.tenant_id == tenant_id,
                InventoryMovement.product_id == product_id,
                InventoryMovement.movement_type == MOVEMENT_TYPE_FBS_SHIPMENT,
            )
        )
        assert movement_count == 1, "должно остаться только исходное списание"

        balance = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == location_id,
            )
        )
        assert balance is not None
        assert int(balance.quantity) == 0, "остаток не должен вырасти — товара на складе нет"


# TC-NEW-FBS-REVERSAL-COMPLETE-002 — отмена по не-complete заказу остаток возвращает
@pytest.mark.asyncio
@pytest.mark.parametrize("supplier_status", ["new", "confirm"])
async def test_reversal_still_happens_when_supplier_status_not_complete(
    async_client: AsyncClient,
    supplier_status: str,
) -> None:
    """Given: заказ уже списан, но `supplier_status` ещё не "complete"
    (`new`/`confirm`) — посылка ещё у нас, WB её не забирал.
    When: WB присылает статус отмены.
    Then: остаток возвращается на склад (движение `fbs_shipment` +1, баланс
          растёт на 1), запись журнала помечена обработанной с заполненным
          `reversal_movement_id` — старое поведение для этого случая не
          меняется.
    """
    order_id, tenant_id, product_id, location_id = await _seed_order_with_existing_write_off(
        async_client, supplier_status=supplier_status
    )

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        await _apply_wb_status_to_order(
            session, order, "cancel", supplier_status=supplier_status,
            actor_user_id=None,
        )
        await session.commit()

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.status == FBS_ORDER_STATUS_CANCELLED

        ledger = await session.scalar(
            select(FbsShipmentReversalLedger).where(
                FbsShipmentReversalLedger.fbs_order_id == order_id
            )
        )
        assert ledger is not None
        assert ledger.reversed_at is not None
        assert ledger.reversal_movement_id is not None

        balance = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == location_id,
            )
        )
        assert balance is not None
        assert int(balance.quantity) == 1, "остаток должен вернуться — товар ещё у нас"


# TC-NEW-FBS-REVERSAL-COMPLETE-003 — параметр по умолчанию защищает вызов без явного флага
@pytest.mark.asyncio
async def test_reverse_fbs_shipment_if_needed_default_blocks_complete(
    async_client: AsyncClient,
) -> None:
    """Прямой вызов `reverse_fbs_shipment_if_needed` без явного параметра
    (как это делает ручная отмена оператором в `cancel_order`) обязан
    использовать безопасное значение по умолчанию и не возвращать остаток,
    если `supplier_status == "complete"`.
    """
    order_id, tenant_id, product_id, location_id = await _seed_order_with_existing_write_off(
        async_client, supplier_status="complete"
    )

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        reversed_flag = await reverse_fbs_shipment_if_needed(session, order)
        await session.commit()

    assert reversed_flag is False

    async with SessionLocal() as session:
        balance = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == location_id,
            )
        )
        assert balance is not None
        assert int(balance.quantity) == 0
