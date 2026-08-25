"""FBS packaging fulfillments — TC-10, TC-11."""

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
    FBS_ORDER_STATUS_IN_SUPPLY,
    FBS_ORDER_STATUS_PACKED,
    MAPPING_STATUS_MAPPED,
    PACK_STATUS_PACKED,
    PACK_STATUS_PENDING,
    PICK_STATUS_PICKED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
    FbsOrderProduct,
)
from app.models.fbs_order_pick import FbsOrderPick
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_DRAFT,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import MOVEMENT_TYPE_FBS_SHIPMENT, InventoryMovement
from app.services import inventory_service
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.wb_marketplace_orders_service import upsert_order_from_wb_row
from tests.fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID, seed_fbs_warehouse_binding


async def _register_ff_admin(async_client: AsyncClient) -> tuple[dict[str, str], str, uuid.UUID]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS pack fulfill {suffix}",
            "slug": f"fbs-pack-fulfill-{suffix}",
            "admin_email": f"fbs-pack-fulfill-{suffix}@example.com",
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


def _wb_order_row(
    *,
    order_id: int,
    article: str,
    created_at: str = "2026-07-01T12:00:00+03:00",
) -> dict[str, Any]:
    return {
        "id": order_id,
        "rid": f"rid-{order_id}",
        "createdAt": created_at,
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


async def _create_product(
    async_client: AsyncClient,
    headers: dict[str, str],
    seller_id: uuid.UUID,
    *,
    sku: str,
) -> uuid.UUID:
    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": sku,
            "sku_code": sku,
            "seller_id": str(seller_id),
            "wb_barcode": f"BAR-{sku}",
        },
    )
    assert product.status_code in (200, 201), product.text
    return uuid.UUID(product.json()["id"])


async def _seed_pick_for_order(
    session: object,
    *,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    order: FbsOrder,
    source_location_id: uuid.UUID,
    scan_key: str,
) -> None:
    sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
    await inventory_service.transfer_on_hand_between_locations(
        session,
        tenant_id=tenant_id,
        product_id=order.product_id,
        from_storage_location_id=source_location_id,
        to_storage_location_id=sorting.id,
        quantity=1,
    )
    now = datetime.now(UTC)
    session.add(
        FbsOrderPick(
            tenant_id=tenant_id,
            fbs_order_id=order.id,
            fbs_supply_id=supply_id,
            source_storage_location_id=source_location_id,
            sorting_storage_location_id=sorting.id,
            product_id=order.product_id,
            picked_at=now,
            scan_idempotency_key=scan_key,
        )
    )
    order.pick_status = PICK_STATUS_PICKED
    order.picked_at = now


@pytest.fixture
def enable_wb_marketplace_supplies_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.settings import settings

    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)


# TC-10 — picked item packed via PackagingTask; inventory unpacked→packed
@pytest.mark.asyncio
async def test_fbs_pack_picked_item_inventory_unpacked_to_packed(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, source_location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product_id = await _create_product(async_client, headers, seller_id, sku=f"sku-{suffix}")

    supply_resp = await async_client.post(
        "/operations/fbs-supplies",
        headers=headers,
        json={
            "seller_id": str(seller_id),
            "warehouse_id": str(warehouse_id),
            "name": "Pack fulfill supply",
            "delivery_type": "warehouse_sc",
        },
    )
    assert supply_resp.status_code == 201, supply_resp.text
    supply_id = uuid.UUID(supply_resp.json()["id"])

    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
        )
        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_id,
            _wb_order_row(order_id=930010, article=f"ART-{suffix}"),
        )
        order.product_id = product_id
        order.supply_id = supply_id
        order.status = FBS_ORDER_STATUS_IN_SUPPLY
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=source_location_id,
            quantity_delta=1,
            movement_type="inbound_intake",
        )
        await session.commit()
        order_id = order.id

    status_resp = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    assert status_resp.status_code == 200, status_resp.text
    task_id = status_resp.json()["packaging_task_id"]

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        await _seed_pick_for_order(
            session,
            tenant_id=tenant_id,
            supply_id=supply_id,
            warehouse_id=warehouse_id,
            order=order,
            source_location_id=source_location_id,
            scan_key=f"pick-{order_id}",
        )
        await session.commit()
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
        before = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == sorting.id,
            )
        )
        assert before is not None
        assert int(before.quantity_unpacked) == 1
        assert int(before.quantity_packed) == 0

    task = await async_client.get(
        f"/operations/packaging-tasks/{task_id}",
        headers=headers,
    )
    assert task.status_code == 200, task.text
    line = task.json()["lines"][0]

    without_pick = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{line['id']}/pack",
        headers=headers,
        json={"quantity": 1, "idempotency_key": "tc10-pack"},
    )
    assert without_pick.status_code == 200, without_pick.text
    body = without_pick.json()
    assert body["fulfilled_order"] is not None
    assert body["fulfilled_order"]["id"] == str(order_id)
    assert body["fulfilled_order"]["pack_status"] == PACK_STATUS_PACKED

    async with SessionLocal() as session:
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
        after = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == sorting.id,
            )
        )
        assert after is not None
        assert int(after.quantity_unpacked) == 0
        assert int(after.quantity_packed) == 1

    complete = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/complete",
        headers=headers,
        json={"acknowledge_all_packed": False},
    )
    assert complete.status_code == 200, complete.text

    supply = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}",
        headers=headers,
    )
    assert supply.json()["status"] == FBS_SUPPLY_STATUS_PACKED

    async with SessionLocal() as session:
        write_off_qty = await session.scalar(
            select(func.coalesce(func.sum(InventoryMovement.quantity_delta), 0)).where(
                InventoryMovement.tenant_id == tenant_id,
                InventoryMovement.product_id == product_id,
                InventoryMovement.movement_type == MOVEMENT_TYPE_FBS_SHIPMENT,
            )
        )
        assert int(write_off_qty) == -1


# TC-10 negative — cannot pack without pick
@pytest.mark.asyncio
async def test_fbs_pack_rejected_without_pick(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, _source_location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product_id = await _create_product(async_client, headers, seller_id, sku=f"nopick-{suffix}")

    supply_resp = await async_client.post(
        "/operations/fbs-supplies",
        headers=headers,
        json={
            "seller_id": str(seller_id),
            "warehouse_id": str(warehouse_id),
            "name": "No pick supply",
            "delivery_type": "warehouse_sc",
        },
    )
    assert supply_resp.status_code == 201, supply_resp.text
    supply_id = uuid.UUID(supply_resp.json()["id"])

    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session, tenant_id=tenant_id, seller_id=seller_id, wms_warehouse_id=warehouse_id
        )
        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_id,
            _wb_order_row(order_id=930011, article=f"NP-{suffix}"),
        )
        order.product_id = product_id
        order.supply_id = supply_id
        order.status = FBS_ORDER_STATUS_IN_SUPPLY
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=sorting.id,
            quantity_delta=1,
            movement_type="inbound_intake",
        )
        await session.commit()

    status_resp = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    task_id = status_resp.json()["packaging_task_id"]
    task = await async_client.get(
        f"/operations/packaging-tasks/{task_id}",
        headers=headers,
    )
    line = task.json()["lines"][0]
    blocked = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{line['id']}/pack",
        headers=headers,
        json={"quantity": 1},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "order_not_picked"


# TC-11 — two same-SKU orders fulfilled individually; third pack rejected
@pytest.mark.asyncio
async def test_fbs_pack_same_sku_two_orders_third_rejected(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, source_location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product_id = await _create_product(async_client, headers, seller_id, sku=f"dup-{suffix}")

    supply_resp = await async_client.post(
        "/operations/fbs-supplies",
        headers=headers,
        json={
            "seller_id": str(seller_id),
            "warehouse_id": str(warehouse_id),
            "name": "Dup SKU supply",
            "delivery_type": "warehouse_sc",
        },
    )
    assert supply_resp.status_code == 201, supply_resp.text
    supply_id = uuid.UUID(supply_resp.json()["id"])

    order_ids: list[uuid.UUID] = []
    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session, tenant_id=tenant_id, seller_id=seller_id, wms_warehouse_id=warehouse_id
        )
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=source_location_id,
            quantity_delta=2,
            movement_type="inbound_intake",
        )
        for idx, wb_id in enumerate((930021, 930022)):
            order, _ = await upsert_order_from_wb_row(
                session,
                tenant_id,
                seller_id,
                _wb_order_row(
                    order_id=wb_id,
                    article=f"DUP-{suffix}",
                    created_at=f"2026-07-0{idx + 1}T12:00:00+03:00",
                ),
            )
            order.product_id = product_id
            order.supply_id = supply_id
            order.status = FBS_ORDER_STATUS_IN_SUPPLY
            order.deadline_at = datetime.now(UTC) + timedelta(hours=24 - idx)
            order_ids.append(order.id)
        await session.commit()

    status_resp = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    task_id = status_resp.json()["packaging_task_id"]

    async with SessionLocal() as session:
        for order_id in order_ids:
            order = await session.get(FbsOrder, order_id)
            assert order is not None
            await _seed_pick_for_order(
                session,
                tenant_id=tenant_id,
                supply_id=supply_id,
                warehouse_id=warehouse_id,
                order=order,
                source_location_id=source_location_id,
                scan_key=f"pick-{order_id}",
            )
        await session.commit()

    task = await async_client.get(
        f"/operations/packaging-tasks/{task_id}",
        headers=headers,
    )
    line = task.json()["lines"][0]
    assert line["qty_total"] == 2

    first = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{line['id']}/pack",
        headers=headers,
        json={"quantity": 1, "idempotency_key": "pack-1"},
    )
    assert first.status_code == 200, first.text
    first_order_id = first.json()["fulfilled_order"]["id"]

    second = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{line['id']}/pack",
        headers=headers,
        json={"quantity": 1, "idempotency_key": "pack-2"},
    )
    assert second.status_code == 200, second.text
    second_order_id = second.json()["fulfilled_order"]["id"]
    assert first_order_id != second_order_id
    assert set(order_ids) == {uuid.UUID(first_order_id), uuid.UUID(second_order_id)}

    third = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{line['id']}/pack",
        headers=headers,
        json={"quantity": 1, "idempotency_key": "pack-3"},
    )
    assert third.status_code in (409, 422)
    assert third.json()["detail"] in ("no_eligible_order", "invalid_qty")

    async with SessionLocal() as session:
        fulfillments = list(
            (
                await session.execute(
                    select(FbsPackagingFulfillment).where(
                        FbsPackagingFulfillment.packaging_task_id == uuid.UUID(task_id),
                        FbsPackagingFulfillment.undone_at.is_(None),
                    )
                )
            ).scalars()
        )
        assert len(fulfillments) == 2


# Regression — packaging must not care about the unpacked/packed split, only the
# total balance at the packaging line's location. Reproduces the prod incident
# (supply WB-GI-266096235): the balance at the task line's location was already
# recorded as "packed" (e.g. by a manual DB fix or an earlier partial pack), yet
# "Всё упаковано" still failed with "Недостаточно неупакованного остатка" even
# though the product was physically right there. Before the fix this call
# raised insufficient_unpacked; after the fix it must succeed end-to-end.
@pytest.mark.asyncio
async def test_fbs_pack_succeeds_when_line_balance_already_marked_packed(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, source_location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product_id = await _create_product(async_client, headers, seller_id, sku=f"packed-{suffix}")

    supply_resp = await async_client.post(
        "/operations/fbs-supplies",
        headers=headers,
        json={
            "seller_id": str(seller_id),
            "warehouse_id": str(warehouse_id),
            "name": "Already-packed balance supply",
            "delivery_type": "warehouse_sc",
        },
    )
    assert supply_resp.status_code == 201, supply_resp.text
    supply_id = uuid.UUID(supply_resp.json()["id"])

    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session, tenant_id=tenant_id, seller_id=seller_id, wms_warehouse_id=warehouse_id
        )
        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_id,
            _wb_order_row(order_id=930030, article=f"PACKED-{suffix}"),
        )
        order.product_id = product_id
        order.supply_id = supply_id
        order.status = FBS_ORDER_STATUS_IN_SUPPLY
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=source_location_id,
            quantity_delta=1,
            movement_type="inbound_intake",
        )
        await session.commit()
        order_id = order.id

    status_resp = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    assert status_resp.status_code == 200, status_resp.text
    task_id = status_resp.json()["packaging_task_id"]

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        await _seed_pick_for_order(
            session,
            tenant_id=tenant_id,
            supply_id=supply_id,
            warehouse_id=warehouse_id,
            order=order,
            source_location_id=source_location_id,
            scan_key=f"pick-{order_id}",
        )
        await session.commit()

        # Flip the sorting-location balance so the unit is already recorded as
        # "packed" rather than "unpacked" — total stays 1, only the split changes.
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
        balance = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == sorting.id,
            )
        )
        assert balance is not None
        assert int(balance.quantity_unpacked) == 1
        balance.quantity_unpacked = 0
        balance.quantity_packed = 1
        await session.commit()

    task = await async_client.get(
        f"/operations/packaging-tasks/{task_id}",
        headers=headers,
    )
    assert task.status_code == 200, task.text
    line = task.json()["lines"][0]

    packed = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{line['id']}/pack",
        headers=headers,
        json={"quantity": 1, "idempotency_key": "pack-already-packed-balance"},
    )
    assert packed.status_code == 200, packed.text
    body = packed.json()
    assert body["fulfilled_order"]["id"] == str(order_id)
    assert body["fulfilled_order"]["pack_status"] == PACK_STATUS_PACKED

    complete = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/complete",
        headers=headers,
        json={"acknowledge_all_packed": False},
    )
    assert complete.status_code == 200, complete.text

    supply = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}",
        headers=headers,
    )
    assert supply.json()["status"] == FBS_SUPPLY_STATUS_PACKED


# Regression counterpart — when the product genuinely isn't there at all (total
# balance is zero), packing must still fail honestly, with a message that tells
# the operator what is missing and where to look.
@pytest.mark.asyncio
async def test_fbs_pack_continues_when_location_has_no_stock_at_all(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, source_location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product_id = await _create_product(async_client, headers, seller_id, sku=f"empty-{suffix}")

    supply_resp = await async_client.post(
        "/operations/fbs-supplies",
        headers=headers,
        json={
            "seller_id": str(seller_id),
            "warehouse_id": str(warehouse_id),
            "name": "No stock at all supply",
            "delivery_type": "warehouse_sc",
        },
    )
    assert supply_resp.status_code == 201, supply_resp.text
    supply_id = uuid.UUID(supply_resp.json()["id"])

    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session, tenant_id=tenant_id, seller_id=seller_id, wms_warehouse_id=warehouse_id
        )
        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_id,
            _wb_order_row(order_id=930031, article=f"EMPTY-{suffix}"),
        )
        order.product_id = product_id
        order.supply_id = supply_id
        order.status = FBS_ORDER_STATUS_IN_SUPPLY
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=source_location_id,
            quantity_delta=1,
            movement_type="inbound_intake",
        )
        await session.commit()
        order_id = order.id

    status_resp = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    assert status_resp.status_code == 200, status_resp.text
    task_id = status_resp.json()["packaging_task_id"]

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        await _seed_pick_for_order(
            session,
            tenant_id=tenant_id,
            supply_id=supply_id,
            warehouse_id=warehouse_id,
            order=order,
            source_location_id=source_location_id,
            scan_key=f"pick-{order_id}",
        )
        await session.commit()

        # Drain the sorting-location balance entirely — the product is genuinely
        # not there (e.g. written off or moved out by hand), total is zero.
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
        balance = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == sorting.id,
            )
        )
        assert balance is not None
        balance.quantity_unpacked = 0
        balance.quantity_packed = 0
        balance.quantity = 0
        await session.commit()

    task = await async_client.get(
        f"/operations/packaging-tasks/{task_id}",
        headers=headers,
    )
    assert task.status_code == 200, task.text
    line = task.json()["lines"][0]

    # 21.08.2026: пустая ячейка больше не повод останавливать упаковку. Подбор уже
    # прошёл, товар физически собран, а остаток мог остаться в ячейке сортировки другого
    # склада. Раньше здесь ждали ответ 409 и вставший склад. Теперь упаковка проходит,
    # а несписанный остаток честно называется оператору словами.
    packed = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{line['id']}/pack",
        headers=headers,
        json={"quantity": 1, "idempotency_key": "pack-no-stock-at-all"},
    )
    assert packed.status_code == 200, packed.text
    body = packed.json()
    assert body["fulfilled_order"] is not None
    warnings = body.get("warnings") or []
    assert warnings, "оператор должен увидеть, что остаток не списан"
    joined = " ".join(warnings)
    assert "остаток не списан" in joined
    # В сообщении по-прежнему видно, чего и где не хватило.
    assert "0" in joined

    async with SessionLocal() as session:
        balances = (
            (
                await session.execute(
                    select(InventoryBalance).where(
                        InventoryBalance.tenant_id == tenant_id,
                        InventoryBalance.product_id == product_id,
                    )
                )
            )
            .scalars()
            .all()
        )
    for balance in balances:
        assert balance.quantity >= 0, "остаток не должен уходить в минус"
        assert balance.quantity_unpacked >= 0
        assert balance.quantity_packed >= 0


@pytest.mark.asyncio
async def test_ozon_multi_product_packaging_requires_all_posting_units(
    async_client: AsyncClient,
) -> None:
    """One Ozon posting is packed only after every imported product unit is packed."""
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, source_location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    first_product_id = await _create_product(
        async_client, headers, seller_id, sku=f"ozon-first-{suffix}"
    )
    second_product_id = await _create_product(
        async_client, headers, seller_id, sku=f"ozon-second-{suffix}"
    )
    quantities = {first_product_id: 2, second_product_id: 3}

    async with SessionLocal() as session:
        supply = FbsSupply(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            marketplace="ozon",
            external_supply_id=f"ozon-packaging-{suffix}",
            wb_supply_id=f"PENDING-{suffix}",
            name="Ozon multi-product packaging",
            status=FBS_SUPPLY_STATUS_DRAFT,
            delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        )
        session.add(supply)
        await session.flush()
        now = datetime.now(UTC)
        order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product_id=first_product_id,
            supply_id=supply.id,
            marketplace="ozon",
            external_order_id=f"ozon-posting-{suffix}",
            wb_order_id=930040,
            created_at_wb=now - timedelta(hours=1),
            deadline_at=now + timedelta(hours=24),
            mapping_status=MAPPING_STATUS_MAPPED,
            reserve_status=RESERVE_STATUS_RESERVED,
            status=FBS_ORDER_STATUS_IN_SUPPLY,
        )
        session.add(order)
        await session.flush()
        session.add_all(
            [
                FbsOrderProduct(
                    order_id=order.id,
                    product_id=first_product_id,
                    ozon_sku=101,
                    offer_id="first-offer",
                    name="First Ozon product",
                    quantity=quantities[first_product_id],
                    reserved_quantity=quantities[first_product_id],
                    position_index=0,
                ),
                FbsOrderProduct(
                    order_id=order.id,
                    product_id=second_product_id,
                    ozon_sku=202,
                    offer_id="second-offer",
                    name="Second Ozon product",
                    quantity=quantities[second_product_id],
                    reserved_quantity=quantities[second_product_id],
                    position_index=1,
                ),
            ]
        )
        for product_id, quantity in quantities.items():
            await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=tenant_id,
                product_id=product_id,
                storage_location_id=source_location_id,
                quantity_delta=quantity,
                movement_type="inbound_intake",
            )
        await session.commit()
        supply_id = supply.id
        order_id = order.id

    assembling = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    assert assembling.status_code == 200, assembling.text
    task_id = assembling.json()["packaging_task_id"]

    for product_id, quantity in quantities.items():
        for unit in range(quantity):
            picked = await async_client.post(
                f"/operations/fbs-supplies/{supply_id}/pick/manual",
                headers=headers,
                json={
                    "location_id": str(source_location_id),
                    "product_id": str(product_id),
                    "order_id": str(order_id),
                    "idempotency_key": f"ozon-pick-{product_id}-{unit}",
                },
            )
            assert picked.status_code == 200, picked.text

    task = await async_client.get(f"/operations/packaging-tasks/{task_id}", headers=headers)
    assert task.status_code == 200, task.text
    lines_by_product = {uuid.UUID(line["product_id"]): line for line in task.json()["lines"]}
    assert {
        product_id: line["qty_total"] for product_id, line in lines_by_product.items()
    } == quantities

    partial = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{lines_by_product[first_product_id]['id']}/pack",
        headers=headers,
        json={"quantity": 1, "idempotency_key": "ozon-pack-first-partial"},
    )
    assert partial.status_code == 200, partial.text
    assert partial.json()["fulfilled_order"] == {
        "id": str(order_id),
        "wb_order_id": 930040,
        "pack_status": PACK_STATUS_PENDING,
        "marking_status": None,
        "sticker_status": "not_requested",
    }

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.status == FBS_ORDER_STATUS_ASSEMBLING
        assert order.pack_status == PACK_STATUS_PENDING

    remaining_first = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{lines_by_product[first_product_id]['id']}/pack",
        headers=headers,
        json={"quantity": 1, "idempotency_key": "ozon-pack-first-rest"},
    )
    assert remaining_first.status_code == 200, remaining_first.text
    complete_posting = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{lines_by_product[second_product_id]['id']}/pack",
        headers=headers,
        json={"quantity": 3, "idempotency_key": "ozon-pack-second-all"},
    )
    assert complete_posting.status_code == 200, complete_posting.text
    assert complete_posting.json()["fulfilled_order"]["pack_status"] == PACK_STATUS_PACKED

    complete_task = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/complete",
        headers=headers,
        json={"acknowledge_all_packed": False},
    )
    assert complete_task.status_code == 200, complete_task.text

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.status == FBS_ORDER_STATUS_PACKED
        assert order.pack_status == PACK_STATUS_PACKED

    supply = await async_client.get(f"/operations/fbs-supplies/{supply_id}", headers=headers)
    assert supply.status_code == 200, supply.text
    assert supply.json()["status"] == FBS_SUPPLY_STATUS_PACKED
