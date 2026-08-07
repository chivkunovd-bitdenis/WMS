from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_IN_SUPPLY,
    FBS_ORDER_STATUS_NEW,
    PICK_STATUS_PICKED,
    FbsOrder,
    FbsOrderReservation,
)
from app.models.fbs_order_pick import FbsOrderPick
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.fbs_trbx import FbsTrbx
from app.models.inventory_movement import MOVEMENT_TYPE_FBS_SHIPMENT, InventoryMovement
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.warehouse_box import WarehouseBox
from app.services import inventory_service
from app.services.fbs_packaging_integration_service import create_packaging_task_for_supply
from app.services.fbs_stock_availability_service import fbs_available_qty_for_product
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.wb_marketplace_orders_service import (
    _release_reservation,
    upsert_order_from_wb_row,
)
from tests.fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID, seed_fbs_warehouse_binding
from tests.test_fbs_shipment_warehouse_sc import _deliver_with_preflight


async def _register_ff_admin(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS pack {suffix}",
            "slug": f"fbs-pack-{suffix}",
            "admin_email": f"fbs-pack-{suffix}@example.com",
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
) -> tuple[str, str]:
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
    return seller_id, warehouse.json()["id"]


def _wb_order_row(
    *, order_id: int, article: str = "ART-A", wb_warehouse_id: int = DEFAULT_WB_WAREHOUSE_ID
) -> dict[str, Any]:
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
        "warehouseId": wb_warehouse_id,
    }


async def _create_product(
    async_client: AsyncClient,
    headers: dict[str, str],
    seller_id: str,
    *,
    sku: str,
    name: str,
) -> str:
    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": name,
            "sku_code": sku,
            "seller_id": seller_id,
            "wb_barcode": f"BAR-{sku}",
        },
    )
    assert product.status_code in (200, 201), product.text
    return product.json()["id"]


async def _create_supply_with_orders(
    async_client: AsyncClient,
    headers: dict[str, str],
    seller_id: str,
    warehouse_id: str,
    tenant_id: uuid.UUID,
    *,
    delivery_type: str = "warehouse_sc",
) -> tuple[str, list[uuid.UUID]]:
    supply_resp = await async_client.post(
        "/operations/fbs-supplies",
        headers=headers,
        json={
            "seller_id": seller_id,
            "warehouse_id": warehouse_id,
            "name": "Pack supply",
            "delivery_type": delivery_type,
        },
    )
    assert supply_resp.status_code == 201, supply_resp.text
    supply_id = supply_resp.json()["id"]

    product_a = await _create_product(
        async_client, headers, seller_id, sku="prod-a", name="Product A"
    )
    product_b = await _create_product(
        async_client, headers, seller_id, sku="prod-b", name="Product B"
    )

    order_ids: list[uuid.UUID] = []
    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=uuid.UUID(seller_id),
            wms_warehouse_id=uuid.UUID(warehouse_id),
        )
        for _idx, (order_no, product_id, article) in enumerate(
            [
                (910001, uuid.UUID(product_a), "ART-A"),
                (910002, uuid.UUID(product_b), "ART-B"),
                (910003, uuid.UUID(product_a), "ART-A"),
            ],
            start=1,
        ):
            order, _ = await upsert_order_from_wb_row(
                session,
                tenant_id,
                uuid.UUID(seller_id),
                _wb_order_row(order_id=order_no, article=article),
            )
            order.product_id = product_id
            order.supply_id = uuid.UUID(supply_id)
            order.status = FBS_ORDER_STATUS_IN_SUPPLY
            order_ids.append(order.id)
        await session.commit()

    return supply_id, order_ids


async def _seed_picks_for_supply_orders(
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    source_location_id: uuid.UUID | None = None,
) -> None:
    async with SessionLocal() as session:
        orders = list(
            (
                await session.execute(
                    select(FbsOrder).where(FbsOrder.supply_id == supply_id)
                )
            ).scalars()
        )
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
        for order in orders:
            if order.product_id is None:
                continue
            now = datetime.now(UTC)
            session.add(
                FbsOrderPick(
                    tenant_id=tenant_id,
                    fbs_order_id=order.id,
                    fbs_supply_id=supply_id,
                    source_storage_location_id=source_location_id or sorting.id,
                    sorting_storage_location_id=sorting.id,
                    product_id=order.product_id,
                    picked_at=now,
                    scan_idempotency_key=f"test-pick-{order.id}",
                )
            )
            order.pick_status = PICK_STATUS_PICKED
            order.picked_at = now
        await session.commit()


@pytest.fixture
def enable_wb_marketplace_supplies_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)


# TC-NEW-FBS-PACKINT-001
@pytest.mark.asyncio
async def test_fbs_packaging_task_created_on_assembling(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token_payload = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(token_payload.json()["tenant_id"])
    supply_id, _ = await _create_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
    )

    resp = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == FBS_SUPPLY_STATUS_ASSEMBLING
    assert body["packaging_task_id"] is not None

    async with SessionLocal() as session:
        task = await session.get(PackagingTask, uuid.UUID(body["packaging_task_id"]))
        assert task is not None
        lines = list(
            (
                await session.execute(
                    select(PackagingTaskLine).where(
                        PackagingTaskLine.task_id == task.id
                    )
                )
            ).scalars()
        )
        assert len(lines) == 2
        qty_by_product = {line.product_id: line.qty_total for line in lines}
        assert sum(qty_by_product.values()) == 3
        assert max(qty_by_product.values()) == 2


# TC-NEW-FBS-PACKINT-002
@pytest.mark.asyncio
async def test_fbs_bind_packaging_box_to_trbx(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token_payload = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(token_payload.json()["tenant_id"])
    supply_id, _ = await _create_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        delivery_type="pvz",
    )

    trbx_resp = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/trbx",
        headers=headers,
        json={"count": 2},
    )
    assert trbx_resp.status_code == 201, trbx_resp.text
    trbx_id = trbx_resp.json()["trbxes"][0]["id"]
    other_trbx_id = trbx_resp.json()["trbxes"][1]["id"]
    async with SessionLocal() as session:
        box = WarehouseBox(
            tenant_id=tenant_id,
            warehouse_id=uuid.UUID(warehouse_id),
            internal_barcode=f"FBS-TRBX-{suffix[-8:]}",
        )
        session.add(box)
        await session.commit()
        box_id = str(box.id)

    bind = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/trbx/bind-box",
        headers=headers,
        json={"trbx_id": trbx_id, "packaging_box_id": box_id},
    )
    assert bind.status_code == 200, bind.text
    assert bind.json()["packaging_box_id"] == box_id

    duplicate = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/trbx/bind-box",
        headers=headers,
        json={"trbx_id": other_trbx_id, "packaging_box_id": box_id},
    )
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["detail"]["code"] == "packaging_box_already_bound"

    async with SessionLocal() as session:
        trbx = await session.get(FbsTrbx, uuid.UUID(trbx_id))
        assert trbx is not None
        assert str(trbx.packaging_box_id) == box_id


# TC-NEW-FBS-PACKINT-002A — a physical box must belong to this tenant and warehouse.
@pytest.mark.asyncio
async def test_fbs_bind_packaging_box_rejects_foreign_tenant_warehouse(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    tenant_id = uuid.UUID((await async_client.get("/auth/me", headers=headers)).json()["tenant_id"])
    supply_id, _ = await _create_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        delivery_type="pvz",
    )
    trbx_resp = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/trbx",
        headers=headers,
        json={"count": 1},
    )
    assert trbx_resp.status_code == 201, trbx_resp.text
    trbx_id = trbx_resp.json()["trbxes"][0]["id"]

    foreign_headers, foreign_suffix = await _register_ff_admin(async_client)
    _foreign_seller_id, foreign_warehouse_id = await _setup_seller_with_token(
        async_client, foreign_headers, foreign_suffix
    )
    foreign_tenant_id = uuid.UUID(
        (await async_client.get("/auth/me", headers=foreign_headers)).json()["tenant_id"]
    )
    async with SessionLocal() as session:
        foreign_box = WarehouseBox(
            tenant_id=foreign_tenant_id,
            warehouse_id=uuid.UUID(foreign_warehouse_id),
            internal_barcode=f"FOREIGN-TRBX-{foreign_suffix[-8:]}",
        )
        session.add(foreign_box)
        await session.commit()
        foreign_box_id = str(foreign_box.id)

    bind = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/trbx/bind-box",
        headers=headers,
        json={"trbx_id": trbx_id, "packaging_box_id": foreign_box_id},
    )
    assert bind.status_code == 404, bind.text
    assert bind.json()["detail"]["code"] == "packaging_box_not_found"
    assert bind.json()["detail"]["context"] == {}
    assert bind.json()["detail"]["retryable"] is False

    async with SessionLocal() as session:
        trbx = await session.get(FbsTrbx, uuid.UUID(trbx_id))
        assert trbx is not None
        assert trbx.packaging_box_id is None


# TC-NEW-FBS-PACKINT-003
@pytest.mark.asyncio
async def test_fbs_supply_packed_after_packaging_complete(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token_payload = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(token_payload.json()["tenant_id"])
    supply_id, _ = await _create_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
    )

    async with SessionLocal() as session:
        orders = list(
            (
                await session.execute(
                    select(FbsOrder).where(FbsOrder.supply_id == uuid.UUID(supply_id))
                )
            ).scalars()
        )
        product_ids = {order.product_id for order in orders if order.product_id is not None}
        sorting = await get_or_create_sorting_location(
            session, tenant_id, uuid.UUID(warehouse_id)
        )
        for product_id in product_ids:
            qty = sum(1 for o in orders if o.product_id == product_id)
            await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=tenant_id,
                product_id=product_id,
                storage_location_id=sorting.id,
                quantity_delta=qty,
                movement_type="inbound_intake",
            )
        await session.commit()

    await _seed_picks_for_supply_orders(
        tenant_id,
        uuid.UUID(supply_id),
        uuid.UUID(warehouse_id),
    )

    status_resp = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    assert status_resp.status_code == 200, status_resp.text
    task_id = status_resp.json()["packaging_task_id"]

    task = await async_client.get(
        f"/operations/packaging-tasks/{task_id}",
        headers=headers,
    )
    assert task.status_code == 200, task.text
    for line in task.json()["lines"]:
        for _unit in range(line["qty_total"]):
            pack = await async_client.post(
                f"/operations/packaging-tasks/{task_id}/lines/{line['id']}/pack",
                headers=headers,
                json={"quantity": 1, "idempotency_key": str(uuid.uuid4())},
            )
            assert pack.status_code == 200, pack.text

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
    assert supply.status_code == 200, supply.text
    assert supply.json()["status"] == FBS_SUPPLY_STATUS_PACKED

    deliver = await _deliver_with_preflight(async_client, headers, supply_id)
    assert deliver.status_code == 200, deliver.text
    body = deliver.json()
    assert body["supply"]["status"] == FBS_SUPPLY_STATUS_IN_DELIVERY
    for order in body["orders"]:
        assert order["status"] == FBS_ORDER_STATUS_IN_DELIVERY


# TC-NEW-FBS-PACKINT-003b — deliver blocked before packaging
@pytest.mark.asyncio
async def test_fbs_supply_deliver_blocked_before_packaging(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token_payload = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(token_payload.json()["tenant_id"])
    supply_id, _ = await _create_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
    )

    blocked = await _deliver_with_preflight(async_client, headers, supply_id)
    assert blocked.status_code == 400
    assert blocked.json()["detail"]["code"] == "packaging_required"


# TC-NEW-FBS-PACKINT-004
@pytest.mark.asyncio
async def test_fbs_warehouse_sc_supply_gets_packaging_task(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token_payload = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(token_payload.json()["tenant_id"])
    supply_id, _ = await _create_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        delivery_type="warehouse_sc",
    )

    resp = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["packaging_task_id"] is not None


# TC-NEW-FBS-PACKINT-005
@pytest.mark.asyncio
async def test_fbs_packaging_task_skips_unmapped_product(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token_payload = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(token_payload.json()["tenant_id"])
    supply_id, _ = await _create_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
    )

    async with SessionLocal() as session:
        orphan = (
            await session.execute(
                select(FbsOrder).where(FbsOrder.supply_id == uuid.UUID(supply_id))
            )
        ).scalars().first()
        assert orphan is not None
        orphan.product_id = None
        await session.commit()

        task = await create_packaging_task_for_supply(
            session, tenant_id, uuid.UUID(supply_id)
        )
        await session.commit()
        lines = list(
            (
                await session.execute(
                    select(PackagingTaskLine).where(PackagingTaskLine.task_id == task.id)
                )
            ).scalars()
        )
    assert len(lines) == 2

    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, uuid.UUID(supply_id))
        assert supply is not None
        assert supply.packaging_task_id == task.id


# TC-NEW-FBS-PACKINT-006 — нельзя добавить заказ после assembling
@pytest.mark.asyncio
async def test_fbs_supply_add_order_rejected_after_assembling(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token_payload = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(token_payload.json()["tenant_id"])
    supply_id, order_ids = await _create_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
    )

    status_resp = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    assert status_resp.status_code == 200, status_resp.text

    extra_order_id = order_ids[0]
    async with SessionLocal() as session:
        extra = await session.get(FbsOrder, extra_order_id)
        assert extra is not None
        extra.supply_id = None
        extra.status = FBS_ORDER_STATUS_NEW
        await session.commit()

    add_resp = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/orders",
        headers=headers,
        json={"order_id": str(extra_order_id)},
    )
    assert add_resp.status_code == 409
    assert add_resp.json()["detail"] == "supply_not_editable"


@pytest.mark.asyncio
async def test_fbs_supply_manual_packed_status_rejected(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token_payload = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(token_payload.json()["tenant_id"])
    supply_id, _ = await _create_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
    )

    await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    packed = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "packed"},
    )
    assert packed.status_code == 400
    assert packed.json()["detail"]["code"] == "invalid_status_transition"


# TC-NEW-FBS-PACKINT-003 (marking branch) — после SGTIN отгрузка → packed
@pytest.mark.asyncio
async def test_fbs_supply_promoted_after_marking_when_honest_sign_required(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_put_meta(*_args: object, **_kwargs: object) -> None:
        return None

    async def noop_marking_assert(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        "app.services.packaging_task_service._assert_marking_done_for_task",
        noop_marking_assert,
    )
    monkeypatch.setattr(
        "app.services.fbs_marking_service.put_marketplace_order_meta",
        fake_put_meta,
    )

    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token_payload = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(token_payload.json()["tenant_id"])

    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Honest sign product",
            "sku_code": f"cz-{suffix}",
            "seller_id": seller_id,
            "wb_barcode": f"CZ-BAR-{suffix}",
            "requires_honest_sign": True,
        },
    )
    assert product.status_code in (200, 201), product.text
    product_id = product.json()["id"]

    supply_resp = await async_client.post(
        "/operations/fbs-supplies",
        headers=headers,
        json={
            "seller_id": seller_id,
            "warehouse_id": warehouse_id,
            "name": "CZ supply",
            "delivery_type": "warehouse_sc",
        },
    )
    assert supply_resp.status_code == 201, supply_resp.text
    supply_id = supply_resp.json()["id"]

    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=uuid.UUID(seller_id),
            wms_warehouse_id=uuid.UUID(warehouse_id),
        )
        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            uuid.UUID(seller_id),
            {**_wb_order_row(order_id=920001, article="CZ-ART"), "requiredMeta": ["sgtin"]},
        )
        order.product_id = uuid.UUID(product_id)
        order.supply_id = uuid.UUID(supply_id)
        order.status = FBS_ORDER_STATUS_IN_SUPPLY
        sorting = await get_or_create_sorting_location(
            session, tenant_id, uuid.UUID(warehouse_id)
        )
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=uuid.UUID(product_id),
            storage_location_id=sorting.id,
            quantity_delta=1,
            movement_type="inbound_intake",
        )
        await session.commit()
        order_id = order.id

    await _seed_picks_for_supply_orders(
        tenant_id,
        uuid.UUID(supply_id),
        uuid.UUID(warehouse_id),
    )

    status_resp = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    assert status_resp.status_code == 200, status_resp.text
    task_id = status_resp.json()["packaging_task_id"]

    task = await async_client.get(
        f"/operations/packaging-tasks/{task_id}",
        headers=headers,
    )
    assert task.status_code == 200, task.text
    line = task.json()["lines"][0]
    pack = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{line['id']}/pack",
        headers=headers,
        json={"quantity": 1, "idempotency_key": "cz-pack-1"},
    )
    assert pack.status_code == 200, pack.text

    complete = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/complete",
        headers=headers,
        json={"acknowledge_all_packed": False},
    )
    assert complete.status_code == 200, complete.text

    supply_mid = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}",
        headers=headers,
    )
    assert supply_mid.json()["status"] == FBS_SUPPLY_STATUS_ASSEMBLING

    mark = await async_client.put(
        f"/operations/fbs-orders/{order_id}/markings/sgtin",
        headers=headers,
        json={"value": "01CIS-PACKINT-TEST"},
    )
    assert mark.status_code == 200, mark.text

    from app.services.wildberries_fbs_client import MarketplaceOrderMetaRow

    async def fake_meta_batch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        assert order_ids == [920001]
        return [
            MarketplaceOrderMetaRow(
                order_id=920001,
                meta={"sgtins": [{"value": "01CIS-PACKINT-TEST", "checkStatus": "ok"}]},
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        fake_meta_batch,
    )
    sync = await async_client.post(
        f"/operations/fbs-orders/{order_id}/markings/sync",
        headers=headers,
    )
    assert sync.status_code == 200, sync.text

    supply_done = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}",
        headers=headers,
    )
    assert supply_done.json()["status"] == FBS_SUPPLY_STATUS_PACKED


# TC-NEW-FBS-STOCK-035 — STOCKFIX-035: promote write-off after per-order pack
@pytest.mark.asyncio
async def test_fbs_promote_write_off_shelf_confirm_sold_does_not_resurrect_available(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    """Per-order pack → fbs_shipment write-off → sold → avail 4 not 5."""
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token_payload = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(token_payload.json()["tenant_id"])

    supply_resp = await async_client.post(
        "/operations/fbs-supplies",
        headers=headers,
        json={
            "seller_id": seller_id,
            "warehouse_id": warehouse_id,
            "name": "Write-off supply",
            "delivery_type": "warehouse_sc",
        },
    )
    assert supply_resp.status_code == 201, supply_resp.text
    supply_id = supply_resp.json()["id"]
    product_id = uuid.UUID(
        await _create_product(async_client, headers, seller_id, sku="sold-035", name="Sold 035")
    )

    order_id: uuid.UUID
    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=uuid.UUID(seller_id),
            wms_warehouse_id=uuid.UUID(warehouse_id),
        )
        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            uuid.UUID(seller_id),
            _wb_order_row(order_id=920035, article="SOLD-035"),
        )
        order.product_id = product_id
        order.supply_id = uuid.UUID(supply_id)
        order.warehouse_id = uuid.UUID(warehouse_id)
        order.status = FBS_ORDER_STATUS_IN_SUPPLY
        order.reserve_status = "reserved"
        session.add(
            FbsOrderReservation(
                tenant_id=tenant_id,
                fbs_order_id=order.id,
                product_id=product_id,
                warehouse_id=uuid.UUID(warehouse_id),
                quantity=1,
            )
        )
        sorting = await get_or_create_sorting_location(
            session, tenant_id, uuid.UUID(warehouse_id)
        )
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=sorting.id,
            quantity_delta=5,
            movement_type="inbound_intake",
        )
        await session.commit()
        order_id = order.id

    await _seed_picks_for_supply_orders(
        tenant_id,
        uuid.UUID(supply_id),
        uuid.UUID(warehouse_id),
    )

    status_resp = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    assert status_resp.status_code == 200, status_resp.text
    task_id = status_resp.json()["packaging_task_id"]

    task = await async_client.get(
        f"/operations/packaging-tasks/{task_id}",
        headers=headers,
    )
    assert task.status_code == 200, task.text
    line = task.json()["lines"][0]
    pack = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{line['id']}/pack",
        headers=headers,
        json={"quantity": 1, "idempotency_key": "sold-035-pack"},
    )
    assert pack.status_code == 200, pack.text

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
    assert supply.status_code == 200, supply.text
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

        order = await session.get(FbsOrder, order_id)
        assert order is not None
        await _release_reservation(session, order)
        await session.commit()

        available_after_sold = await fbs_available_qty_for_product(
            session, tenant_id, uuid.UUID(warehouse_id), product_id
        )
        assert available_after_sold == 4
        assert available_after_sold != 5
