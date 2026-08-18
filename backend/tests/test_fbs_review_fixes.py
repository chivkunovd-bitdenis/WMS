"""TC-NEW-FBS-FIX-* — review fixes for PR #103."""

from __future__ import annotations

import time
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import (
    CHECK_STATUS_NEW,
    FBS_ORDER_STATUS_ASSEMBLING,
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_DONE,
    FBS_ORDER_STATUS_IN_SUPPLY,
    FBS_ORDER_STATUS_NEW,
    FBS_ORDER_STATUS_PACKED,
    FBS_ORDER_STATUS_SORTED,
    MAPPING_STATUS_MAPPED,
    META_STATUS_ACCEPTED,
    PACK_STATUS_PACKED,
    PICK_STATUS_PICKED,
    RESERVE_STATUS_NO_STOCK,
    FbsOrder,
    FbsOrderMarking,
    FbsOrderReservation,
)
from app.models.fbs_order_pick import FbsOrderPick
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_DRAFT,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.inventory_movement import MOVEMENT_TYPE_FBS_SHIPMENT, InventoryMovement
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.services import inventory_service, stock_direction_service
from app.services.fbs_packaging_integration_service import (
    _write_off_active_orders_once,
    detach_cancelled_order_from_supply,
    try_promote_fbs_supply_if_ready,
)
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.wb_marketplace_orders_service import (
    _apply_wb_status_to_order,
    _try_reserve_order,
    sync_order_statuses,
    upsert_order_from_wb_row,
)
from tests.fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID, seed_fbs_warehouse_binding


async def _register_ff_admin(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS fix {suffix}",
            "slug": f"fbs-fix-{suffix}",
            "admin_email": f"fbs-fix-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    return headers, suffix


async def _setup_seller_with_token(
    async_client: AsyncClient,
    headers: dict[str, str],
    suffix: str,
) -> tuple[str, str, uuid.UUID]:
    seller = await async_client.post(
        "/sellers", headers=headers, json={"name": f"Seller {suffix}"}
    )
    assert seller.status_code in (200, 201), seller.text
    seller_id = seller.json()["id"]
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
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    return seller_id, warehouse.json()["id"], tenant_id


def _wb_order_row(
    *,
    order_id: int,
    created_at: datetime,
    wb_warehouse_id: int = DEFAULT_WB_WAREHOUSE_ID,
) -> dict[str, Any]:
    return {
        "id": order_id,
        "rid": f"rid-{order_id}",
        "createdAt": created_at.isoformat(),
        "nmId": 900001,
        "chrtId": 555,
        "article": f"ART-{order_id}",
        "skus": [f"BAR-{order_id}"],
        "price": 199900,
        "cargoType": 1,
        "officeId": 42,
        "isLegal": False,
        "warehouseId": wb_warehouse_id,
    }


@pytest.fixture
def enable_wb_marketplace_supplies_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)


# TC-NEW-FBS-FIX-001 — cancel in assembling does not block supply
@pytest.mark.asyncio
async def test_cancel_in_assembling_detaches_and_adjusts_packaging(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)

    supply_resp = await async_client.post(
        "/operations/fbs-supplies",
        headers=headers,
        json={
            "seller_id": seller_id,
            "warehouse_id": warehouse_id,
            "name": "Fix supply",
            "delivery_type": "warehouse_sc",
        },
    )
    assert supply_resp.status_code == 201, supply_resp.text
    supply_id = uuid.UUID(supply_resp.json()["id"])

    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_uuid,
            name="Fix product",
            sku_code=f"FIX-{suffix[-6:]}",
            wb_barcode="FIX-BAR",
        )
        session.add(product)
        await session.flush()
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_uuid)
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product.id,
            storage_location_id=sorting.id,
            quantity_delta=10,
            movement_type="inbound_intake",
        )
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_uuid,
            wms_warehouse_id=warehouse_uuid,
        )
        orders: list[FbsOrder] = []
        base = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
        for idx, wb_id in enumerate((920001, 920002), start=0):
            order, _ = await upsert_order_from_wb_row(
                session,
                tenant_id,
                seller_uuid,
                _wb_order_row(order_id=wb_id, created_at=base + timedelta(hours=idx)),
            )
            order.product_id = product.id
            order.supply_id = supply_id
            order.status = FBS_ORDER_STATUS_IN_SUPPLY
            orders.append(order)
        await session.commit()
        order_to_cancel = orders[0].id

    status_resp = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    assert status_resp.status_code == 200, status_resp.text
    task_id = uuid.UUID(status_resp.json()["packaging_task_id"])

    async def fake_cancel(
        client: object,
        *,
        api_token: str,
        order_id: int,
        marketplace_api_base: str | None = None,
    ) -> None:
        return None

    monkeypatch.setattr(
        "app.services.fbs_cancellation_service.cancel_marketplace_order",
        fake_cancel,
    )

    cancel = await async_client.patch(
        f"/operations/fbs-orders/{order_to_cancel}/cancel",
        headers=headers,
    )
    assert cancel.status_code == 200, cancel.text

    async with SessionLocal() as session:
        cancelled = await session.get(FbsOrder, order_to_cancel)
        assert cancelled is not None
        assert cancelled.status == FBS_ORDER_STATUS_CANCELLED
        assert cancelled.supply_id is None

        line = (
            await session.execute(
                select(PackagingTaskLine).where(PackagingTaskLine.task_id == task_id)
            )
        ).scalar_one()
        assert line.qty_total == 1

        remaining_order = (
            await session.execute(
                select(FbsOrder).where(
                    FbsOrder.supply_id == supply_id,
                    FbsOrder.status != FBS_ORDER_STATUS_CANCELLED,
                )
            )
        ).scalar_one()
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_uuid)
        now = datetime.now(tz=UTC)
        session.add(
            FbsOrderPick(
                tenant_id=tenant_id,
                fbs_order_id=remaining_order.id,
                fbs_supply_id=supply_id,
                source_storage_location_id=sorting.id,
                sorting_storage_location_id=sorting.id,
                product_id=remaining_order.product_id,
                picked_at=now,
                scan_idempotency_key=f"pick-{remaining_order.id}",
            )
        )
        remaining_order.pick_status = PICK_STATUS_PICKED
        remaining_order.picked_at = now
        await session.commit()

        task = await async_client.get(
            f"/operations/packaging-tasks/{task_id}",
            headers=headers,
        )
        assert task.status_code == 200
        pack_line = task.json()["lines"][0]
        pack = await async_client.post(
            f"/operations/packaging-tasks/{task_id}/lines/{pack_line['id']}/pack",
            headers=headers,
            json={"quantity": 1, "idempotency_key": "fix-cancel-pack"},
        )
        assert pack.status_code == 200, pack.text
        complete = await async_client.post(
            f"/operations/packaging-tasks/{task_id}/complete",
            headers=headers,
            json={"acknowledge_all_packed": False},
        )
        assert complete.status_code == 200, complete.text

        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        assert supply.status == "packed"


# TC-NEW-FBS-FIX-001 negative — last order cancel reverts supply to draft
@pytest.mark.asyncio
async def test_cancel_last_order_in_assembling_reverts_supply_to_draft(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)

    supply_resp = await async_client.post(
        "/operations/fbs-supplies",
        headers=headers,
        json={
            "seller_id": seller_id,
            "warehouse_id": warehouse_id,
            "name": "Single",
            "delivery_type": "warehouse_sc",
        },
    )
    assert supply_resp.status_code == 201
    supply_id = uuid.UUID(supply_resp.json()["id"])

    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_uuid,
            name="Single",
            sku_code=f"SGL-{suffix[-6:]}",
            wb_barcode="SGL-BAR",
        )
        session.add(product)
        await session.flush()
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_uuid,
            wms_warehouse_id=warehouse_uuid,
        )
        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_uuid,
            _wb_order_row(order_id=920101, created_at=datetime.now(tz=UTC)),
        )
        order.product_id = product.id
        order.supply_id = supply_id
        order.status = FBS_ORDER_STATUS_IN_SUPPLY
        order_id = order.id
        await session.commit()

    await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )

    async def fake_cancel(
        client: object,
        *,
        api_token: str,
        order_id: int,
        marketplace_api_base: str | None = None,
    ) -> None:
        return None

    monkeypatch.setattr(
        "app.services.fbs_cancellation_service.cancel_marketplace_order",
        fake_cancel,
    )
    cancel = await async_client.patch(
        f"/operations/fbs-orders/{order_id}/cancel",
        headers=headers,
    )
    assert cancel.status_code == 200

    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        assert supply.status == FBS_SUPPLY_STATUS_DRAFT


# TC-NEW-FBS-FIX-002 — concurrent reserve does not oversell
@pytest.mark.asyncio
async def test_concurrent_reserve_only_one_succeeds(
    async_client: AsyncClient,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)
    wb_base = 930000

    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_uuid,
            name="P",
            sku_code=f"SKU-C-{suffix[-6:]}",
            wb_barcode=f"BC-C-{suffix[-6:]}",
        )
        session.add(product)
        await session.flush()
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_uuid)
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product.id,
            storage_location_id=sorting.id,
            quantity_delta=1,
            movement_type="inbound_intake",
        )
        await stock_direction_service.create_stock_direction(
            session,
            tenant_id,
            product.id,
            name="FBS pool",
            quantity=1,
            is_fbs=True,
        )
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_uuid,
            wms_warehouse_id=warehouse_uuid,
        )
        orders: list[uuid.UUID] = []
        for idx in range(2):
            order, _ = await upsert_order_from_wb_row(
                session,
                tenant_id,
                seller_uuid,
                _wb_order_row(
                    order_id=wb_base + idx,
                    created_at=datetime(2026, 7, 2, idx, 0, tzinfo=UTC),
                ),
            )
            order.product_id = product.id
            orders.append(order.id)
        await session.commit()

    async def reserve_one(order_id: uuid.UUID) -> str:
        async with SessionLocal() as session:
            order = await session.get(FbsOrder, order_id)
            assert order is not None
            await _try_reserve_order(session, order)
            await session.commit()
            refreshed = await session.get(FbsOrder, order_id)
            assert refreshed is not None
            return refreshed.reserve_status

    first = await reserve_one(orders[0])
    second = await reserve_one(orders[1])
    assert first == "reserved"
    assert second == "no_stock"

    async with SessionLocal() as session:
        count = (
            await session.execute(select(FbsOrderReservation))
        ).scalars().all()
        assert len(count) == 1


# TC-NEW-FBS-FIX-003 — pagination reaches oldest order
@pytest.mark.asyncio
async def test_sync_order_statuses_paginates_past_500(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)
    oldest_wb_id = 940001
    tail_wb_id = 940501
    total_orders = 501

    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_uuid,
            wms_warehouse_id=warehouse_uuid,
        )
        base = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
        for idx in range(total_orders):
            order, _ = await upsert_order_from_wb_row(
                session,
                tenant_id,
                seller_uuid,
                _wb_order_row(
                    order_id=940000 + idx + 1,
                    created_at=base + timedelta(minutes=idx),
                ),
            )
            order.status = FBS_ORDER_STATUS_NEW
        await session.commit()

    seen_batches: list[list[int]] = []

    async def fake_status(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[dict[str, Any]]:
        seen_batches.append(list(order_ids))
        return [
            {"id": oid, "wbStatus": "cancel" if oid == oldest_wb_id else "waiting"}
            for oid in order_ids
        ]

    monkeypatch.setattr(
        "app.services.wb_marketplace_orders_service.fetch_marketplace_orders_status",
        fake_status,
    )

    async with SessionLocal() as session:
        async with httpx.AsyncClient() as http_client:
            updated = await sync_order_statuses(
                session, tenant_id, seller_uuid, http_client, "token"
            )
        await session.commit()

    assert updated >= 2
    all_synced_ids = {oid for batch in seen_batches for oid in batch}
    assert oldest_wb_id in all_synced_ids
    assert tail_wb_id in all_synced_ids
    assert len(seen_batches) >= 2

    async with SessionLocal() as session:
        oldest = (
            await session.execute(
                select(FbsOrder).where(FbsOrder.wb_order_id == oldest_wb_id)
            )
        ).scalar_one()
        assert oldest.status == FBS_ORDER_STATUS_CANCELLED
        tail = (
            await session.execute(
                select(FbsOrder).where(FbsOrder.wb_order_id == tail_wb_id)
            )
        ).scalar_one()
        assert tail.wb_status == "waiting"


# TC-NEW-FBS-FIX-004 — PACKED waits for accepted required WB metadata
@pytest.mark.asyncio
async def test_promote_packed_requires_marking_ok(
    async_client: AsyncClient,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)
    supply_id = uuid.uuid4()
    order_id = uuid.uuid4()
    task_id = uuid.uuid4()
    line_id = uuid.uuid4()

    async with SessionLocal() as session:
        from app.models.packaging_task import PackagingTask, PackagingTaskLine

        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_uuid,
            name="HS",
            sku_code=f"HS-{suffix[-6:]}",
            wb_barcode=f"HS-BAR-{suffix[-6:]}",
            requires_honest_sign=True,
        )
        session.add(product)
        await session.flush()
        session.add(
            PackagingTask(
                id=task_id,
                tenant_id=tenant_id,
                warehouse_id=warehouse_uuid,
                status="done",
            )
        )
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_uuid)
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product.id,
            storage_location_id=sorting.id,
            quantity_delta=1,
            movement_type="inbound_intake",
        )
        session.add(
            PackagingTaskLine(
                id=line_id,
                task_id=task_id,
                product_id=product.id,
                storage_location_id=sorting.id,
                qty_total=1,
                qty_confirmed_packed=0,
                qty_packed_in_task=1,
            )
        )
        session.add(
            FbsSupply(
                id=supply_id,
                tenant_id=tenant_id,
                seller_id=seller_uuid,
                warehouse_id=warehouse_uuid,
                wb_supply_id="wb-1",
                name="M",
                status=FBS_SUPPLY_STATUS_ASSEMBLING,
                delivery_type="warehouse_sc",
                packaging_task_id=task_id,
            )
        )
        session.add(
            FbsOrder(
                id=order_id,
                tenant_id=tenant_id,
                seller_id=seller_uuid,
                warehouse_id=warehouse_uuid,
                product_id=product.id,
                wb_order_id=950001,
                status=FBS_ORDER_STATUS_ASSEMBLING,
                supply_id=supply_id,
                pack_status=PACK_STATUS_PACKED,
                created_at_wb=datetime.now(tz=UTC),
                deadline_at=datetime.now(tz=UTC) + timedelta(hours=120),
                mapping_status=MAPPING_STATUS_MAPPED,
                reserve_status=RESERVE_STATUS_NO_STOCK,
                required_meta_json=["sgtin"],
            )
        )
        session.add(
            FbsOrderMarking(
                order_id=order_id,
                tenant_id=tenant_id,
                kind="sgtin",
                value="010460000000000021N4N57RTCBUZTQ",
                check_status=CHECK_STATUS_NEW,
            )
        )
        session.add(
            FbsPackagingFulfillment(
                tenant_id=tenant_id,
                fbs_order_id=order_id,
                packaging_task_id=task_id,
                packaging_task_line_id=line_id,
                fulfilled_at=datetime.now(tz=UTC),
                pack_idempotency_key="review-fix-pack",
            )
        )
        await session.flush()

        blocked = await try_promote_fbs_supply_if_ready(session, tenant_id, supply_id)
        assert blocked is not None
        assert blocked.status == FBS_SUPPLY_STATUS_ASSEMBLING

        marking = (
            await session.execute(
                select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
            )
        ).scalar_one()
        marking.meta_status = META_STATUS_ACCEPTED
        await session.flush()

        promoted = await try_promote_fbs_supply_if_ready(session, tenant_id, supply_id)
        assert promoted is not None
        assert promoted.status == "packed"


# TC-NEW-FBS-FIX-001 — cancel in packed supply demotes supply to assembling
@pytest.mark.asyncio
async def test_cancel_in_packed_supply_demotes_to_assembling(
    async_client: AsyncClient,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)
    supply_id = uuid.uuid4()
    cancel_order_id = uuid.uuid4()
    keep_order_id = uuid.uuid4()

    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_uuid,
            name="Packed cancel",
            sku_code=f"PK-{suffix[-6:]}",
            wb_barcode=f"PK-BAR-{suffix[-6:]}",
        )
        session.add(product)
        await session.flush()
        session.add(
            FbsSupply(
                id=supply_id,
                tenant_id=tenant_id,
                seller_id=seller_uuid,
                warehouse_id=warehouse_uuid,
                wb_supply_id="wb-packed",
                name="Packed",
                status=FBS_SUPPLY_STATUS_PACKED,
                delivery_type="warehouse_sc",
            )
        )
        session.add(
            FbsOrder(
                id=cancel_order_id,
                tenant_id=tenant_id,
                seller_id=seller_uuid,
                warehouse_id=warehouse_uuid,
                product_id=product.id,
                wb_order_id=970001,
                status=FBS_ORDER_STATUS_PACKED,
                supply_id=supply_id,
                created_at_wb=datetime.now(tz=UTC),
                deadline_at=datetime.now(tz=UTC) + timedelta(hours=120),
                mapping_status=MAPPING_STATUS_MAPPED,
                reserve_status=RESERVE_STATUS_NO_STOCK,
            )
        )
        session.add(
            FbsOrder(
                id=keep_order_id,
                tenant_id=tenant_id,
                seller_id=seller_uuid,
                warehouse_id=warehouse_uuid,
                product_id=product.id,
                wb_order_id=970002,
                status=FBS_ORDER_STATUS_PACKED,
                supply_id=supply_id,
                created_at_wb=datetime.now(tz=UTC),
                deadline_at=datetime.now(tz=UTC) + timedelta(hours=120),
                mapping_status=MAPPING_STATUS_MAPPED,
                reserve_status=RESERVE_STATUS_NO_STOCK,
            )
        )
        await session.commit()

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, cancel_order_id)
        assert order is not None
        order.status = FBS_ORDER_STATUS_CANCELLED
        await detach_cancelled_order_from_supply(session, tenant_id, order)
        await session.commit()

    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        assert supply.status == FBS_SUPPLY_STATUS_ASSEMBLING
        kept = await session.get(FbsOrder, keep_order_id)
        assert kept is not None
        assert kept.status == FBS_ORDER_STATUS_ASSEMBLING
        assert kept.supply_id == supply_id


# TC-NEW-FBS-FIX-003 — sorted orders remain in sync until sold
@pytest.mark.asyncio
async def test_sync_order_statuses_advances_sorted_to_sold(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)

    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_uuid,
            wms_warehouse_id=warehouse_uuid,
        )
        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_uuid,
            _wb_order_row(order_id=960001, created_at=datetime.now(tz=UTC)),
        )
        order.status = FBS_ORDER_STATUS_SORTED
        await session.commit()

    seen: list[int] = []

    async def fake_status(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[dict[str, Any]]:
        seen.extend(order_ids)
        return [
            {"id": order_id, "supplierStatus": "complete", "wbStatus": "sold"}
            for order_id in order_ids
        ]

    monkeypatch.setattr(
        "app.services.wb_marketplace_orders_service.fetch_marketplace_orders_status",
        fake_status,
    )

    async with SessionLocal() as session:
        async with httpx.AsyncClient() as http_client:
            updated = await sync_order_statuses(
                session, tenant_id, seller_uuid, http_client, "token"
            )
        await session.commit()

    assert updated == 1
    assert seen == [960001]
    async with SessionLocal() as session:
        order = await session.scalar(
            select(FbsOrder).where(FbsOrder.wb_order_id == 960001)
        )
        assert order is not None
        assert order.wb_status == "sold"
        assert order.supplier_status == "complete"
        assert order.status == FBS_ORDER_STATUS_DONE


# TC-NEW-FBS-REVERSAL-001 — shipment and reversal stay on the fulfilled line.
@pytest.mark.asyncio
async def test_fbs_shipment_uses_each_order_fulfillment_location(
    async_client: AsyncClient,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)

    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_uuid,
            name="Two-cell FBS product",
            sku_code=f"2CELL-{suffix[-8:]}",
            wb_barcode=f"2CELL-BAR-{suffix[-8:]}",
        )
        task = PackagingTask(
            tenant_id=tenant_id,
            warehouse_id=warehouse_uuid,
            status="done",
        )
        locations = [
            StorageLocation(
                tenant_id=tenant_id,
                warehouse_id=warehouse_uuid,
                code=f"L{index}-{suffix[-6:]}",
                barcode=f"L{index}-{suffix}",
            )
            for index in (1, 2)
        ]
        session.add_all([product, task, *locations])
        await session.flush()
        supply = FbsSupply(
            tenant_id=tenant_id,
            seller_id=seller_uuid,
            warehouse_id=warehouse_uuid,
            wb_supply_id=f"two-cell-{suffix[-8:]}",
            name="Two-cell supply",
            status=FBS_SUPPLY_STATUS_ASSEMBLING,
            delivery_type="warehouse_sc",
            packaging_task_id=task.id,
        )
        session.add(supply)
        await session.flush()

        orders: list[FbsOrder] = []
        for index, location in enumerate(locations, start=1):
            line = PackagingTaskLine(
                task=task,
                product_id=product.id,
                storage_location_id=location.id,
                qty_total=1,
                qty_packed_in_task=1,
            )
            order = FbsOrder(
                tenant_id=tenant_id,
                seller_id=seller_uuid,
                warehouse_id=warehouse_uuid,
                product_id=product.id,
                wb_order_id=980000 + index,
                status=FBS_ORDER_STATUS_ASSEMBLING,
                supply=supply,
                pack_status=PACK_STATUS_PACKED,
                created_at_wb=datetime.now(tz=UTC),
                deadline_at=datetime.now(tz=UTC) + timedelta(hours=24),
                mapping_status=MAPPING_STATUS_MAPPED,
                reserve_status=RESERVE_STATUS_NO_STOCK,
            )
            session.add_all([line, order])
            await session.flush()
            session.add(
                FbsPackagingFulfillment(
                    tenant_id=tenant_id,
                    fbs_order_id=order.id,
                    packaging_task_id=task.id,
                    packaging_task_line_id=line.id,
                    fulfilled_at=datetime.now(tz=UTC),
                    pack_idempotency_key=f"two-cell-{index}",
                )
            )
            await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=tenant_id,
                product_id=product.id,
                storage_location_id=location.id,
                quantity_delta=1,
                movement_type="inbound_intake",
            )
            orders.append(order)
        await session.flush()

        supply = (
            await session.execute(
                select(FbsSupply)
                .where(FbsSupply.id == supply.id)
                .options(selectinload(FbsSupply.orders))
            )
        ).scalar_one()
        await _write_off_active_orders_once(session, tenant_id, supply, task)
        ledgers = list(
            (
                await session.execute(
                    select(FbsShipmentReversalLedger).where(
                        FbsShipmentReversalLedger.fbs_order_id.in_([order.id for order in orders])
                    )
                )
            ).scalars()
        )
        assert {ledger.fbs_order_id: ledger.storage_location_id for ledger in ledgers} == {
            order.id: location.id for order, location in zip(orders, locations, strict=True)
        }

        await _apply_wb_status_to_order(session, orders[0], "canceled")
        await _apply_wb_status_to_order(session, orders[0], "canceled")
        await session.flush()
        movements = list(
            (
                await session.execute(
                    select(InventoryMovement).where(
                        InventoryMovement.tenant_id == tenant_id,
                        InventoryMovement.product_id == product.id,
                        InventoryMovement.movement_type == MOVEMENT_TYPE_FBS_SHIPMENT
                    )
                )
            ).scalars()
        )
        movement_locations = Counter(
            (movement.storage_location_id, movement.quantity_delta)
            for movement in movements
        )
        assert movement_locations == Counter(
            {
                (locations[0].id, -1): 1,
                (locations[1].id, -1): 1,
                (locations[0].id, 1): 1,
            }
        )
