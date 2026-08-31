# ruff: noqa: RUF059
from __future__ import annotations

import time
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import (
    CHECK_STATUS_NEW,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_IN_SUPPLY,
    FBS_ORDER_STATUS_NEW,
    META_STATUS_PENDING,
    STICKER_STATUS_READY,
    FbsOrder,
    FbsOrderMarking,
    FbsOrderReservation,
)
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FbsSupply,
)
from app.models.fbs_trbx import FbsTrbx
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import MOVEMENT_TYPE_FBS_SHIPMENT, InventoryMovement
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.product import Product
from app.models.warehouse_box import WarehouseBox
from app.services import inventory_service
from app.services.fbs_packaging_integration_service import create_packaging_task_for_supply
from app.services.fbs_stock_availability_service import fbs_available_qty_for_product
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.wb_marketplace_orders_service import upsert_order_from_wb_row
from tests.fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID, seed_fbs_warehouse_binding
from tests.inventory_actor_helpers import resolve_test_actor_user_id
from tests.test_fbs_shipment_warehouse_sc import (
    _create_and_fill_physical_box,
    _deliver_with_preflight,
)


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
    async with SessionLocal() as session:
        row = await session.get(Product, uuid.UUID(product.json()["id"]))
        assert row is not None
        row.fbs_stock_sync_enabled = True
        row.fbs_percent = 100
        await session.commit()
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


@pytest.fixture
def enable_wb_marketplace_supplies_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)


def _mock_actual_composition(
    monkeypatch: pytest.MonkeyPatch,
    wb_supply_id: str,
    wb_order_ids: list[int],
) -> None:
    async def fetch_actual_order_ids(
        client: object,
        *,
        api_token: str,
        wb_supply_id: str,
        expected_order_ids: list[int] | None = None,
    ) -> list[int]:
        return list(wb_order_ids) if wb_supply_id == expected_supply_id else []

    expected_supply_id = wb_supply_id
    monkeypatch.setattr(
        "app.services.fbs_supply_composition_service.fetch_wb_supply_order_ids",
        fetch_actual_order_ids,
    )


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
        cargo_place = WarehouseBox(
            tenant_id=tenant_id,
            warehouse_id=uuid.UUID(warehouse_id),
            internal_barcode=f"FBS-CARGO-{suffix[-8:]}",
            container_kind="cargo_place",
        )
        session.add_all([box, cargo_place])
        await session.commit()
        box_id = str(box.id)
        cargo_place_id = str(cargo_place.id)

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

    cargo_bind = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/trbx/bind-box",
        headers=headers,
        json={"trbx_id": other_trbx_id, "packaging_box_id": cargo_place_id},
    )
    assert cargo_bind.status_code == 404, cargo_bind.text
    assert cargo_bind.json()["detail"]["code"] == "packaging_box_not_found"

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


# TC-NEW-FBS-PACKINT-003 — WB packaging is an optional fact: it neither
# converts stock nor promotes the supply, and delivery remains independent.
@pytest.mark.asyncio
async def test_fbs_packaging_complete_does_not_convert_or_promote_supply(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
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
        supply_row = await session.get(FbsSupply, uuid.UUID(supply_id))
        assert supply_row is not None
        wb_supply_id = supply_row.wb_supply_id
        wb_order_ids = [int(order.wb_order_id) for order in orders]
        product_ids = {order.product_id for order in orders if order.product_id is not None}
        packed_order_ids = [order.id for order in orders]
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
                actor_user_id=await resolve_test_actor_user_id(session, tenant_id),
            )
        for order in orders:
            order.sticker_status = STICKER_STATUS_READY
            order.sticker_file = f"fbs/orders/{order.id}.png"
        await session.commit()
        sorting_id = sorting.id

    _mock_actual_composition(monkeypatch, wb_supply_id, wb_order_ids)

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
    assert supply.json()["status"] == FBS_SUPPLY_STATUS_ASSEMBLING

    async with SessionLocal() as session:
        balances = list(
            (
                await session.execute(
                    select(InventoryBalance).where(
                        InventoryBalance.tenant_id == tenant_id,
                        InventoryBalance.product_id.in_(product_ids),
                        InventoryBalance.storage_location_id == sorting_id,
                    )
                )
            ).scalars()
        )
        assert sum(balance.quantity_unpacked for balance in balances) == len(
            packed_order_ids
        )
        assert sum(balance.quantity_packed for balance in balances) == 0
        packaging_movements = await session.scalar(
            select(func.count(InventoryMovement.id)).where(
                InventoryMovement.tenant_id == tenant_id,
                InventoryMovement.product_id.in_(product_ids),
                InventoryMovement.movement_type == "packaging_convert",
            )
        )
        assert int(packaging_movements or 0) == 0

    # Передача возможна только после раскладки упакованных заказов по физическим
    # коробам — гейт physical_boxes_required (см. fbs_shipment_service).
    await _create_and_fill_physical_box(async_client, headers, supply_id, packed_order_ids)

    deliver = await _deliver_with_preflight(async_client, headers, supply_id)
    assert deliver.status_code == 200, deliver.text
    body = deliver.json()
    assert body["supply"]["status"] == FBS_SUPPLY_STATUS_IN_DELIVERY
    for order in body["orders"]:
        assert order["status"] == FBS_ORDER_STATUS_IN_DELIVERY


# TC-NEW-FBS-PACKINT-003b — WB delivery is not gated by packaging.
@pytest.mark.asyncio
async def test_fbs_supply_deliver_allowed_without_packaging(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
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

    async with SessionLocal() as session:
        orders = list(
            (
                await session.execute(
                    select(FbsOrder).where(FbsOrder.supply_id == uuid.UUID(supply_id))
                )
            ).scalars()
        )
        supply_row = await session.get(FbsSupply, uuid.UUID(supply_id))
        assert supply_row is not None
        wb_supply_id = supply_row.wb_supply_id
        wb_order_ids = [int(order.wb_order_id) for order in orders]
        sorting = await get_or_create_sorting_location(
            session, tenant_id, uuid.UUID(warehouse_id)
        )
        for order in orders:
            assert order.product_id is not None
            order.sticker_status = STICKER_STATUS_READY
            order.sticker_file = f"fbs/orders/{order.id}.png"
            await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=tenant_id,
                product_id=order.product_id,
                storage_location_id=sorting.id,
                quantity_delta=1,
                movement_type="inbound_intake",
                actor_user_id=await resolve_test_actor_user_id(session, tenant_id),
            )
        await session.commit()

    _mock_actual_composition(monkeypatch, wb_supply_id, wb_order_ids)
    await _create_and_fill_physical_box(async_client, headers, supply_id, order_ids)
    delivered = await _deliver_with_preflight(async_client, headers, supply_id)
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["supply"]["status"] == FBS_SUPPLY_STATUS_IN_DELIVERY


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
async def test_fbs_marking_update_does_not_promote_wb_supply(
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
            actor_user_id=await resolve_test_actor_user_id(session, tenant_id),
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

    async with SessionLocal() as session:
        session.add(
            FbsOrderMarking(
                order_id=order_id,
                tenant_id=tenant_id,
                kind="sgtin",
                value="01CIS-PACKINT-TEST",
                check_status=CHECK_STATUS_NEW,
                meta_status=META_STATUS_PENDING,
            )
        )
        await session.commit()

    from app.services.wildberries_fbs_client import (
        MarketplaceMetaDetail,
        MarketplaceOrderMetaRow,
    )

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
                meta_details=(
                    MarketplaceMetaDetail(
                        key="sgtin",
                        value="01CIS-PACKINT-TEST",
                        decision="filled",
                    ),
                ),
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
    assert supply_done.json()["status"] == FBS_SUPPLY_STATUS_ASSEMBLING


# TC-NEW-FBS-SHIP-STOCK-001 — packaging keeps physical stock and reservation.
@pytest.mark.asyncio
async def test_fbs_packaging_keeps_physical_stock_reserved_until_delivery(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    """Per-order pack changes no physical stock; the order remains reserved."""
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
            actor_user_id=await resolve_test_actor_user_id(session, tenant_id),
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
    assert supply.json()["status"] == FBS_SUPPLY_STATUS_ASSEMBLING

    async with SessionLocal() as session:
        write_off_qty = await session.scalar(
            select(func.coalesce(func.sum(InventoryMovement.quantity_delta), 0)).where(
                InventoryMovement.tenant_id == tenant_id,
                InventoryMovement.product_id == product_id,
                InventoryMovement.movement_type == MOVEMENT_TYPE_FBS_SHIPMENT,
            )
        )
        assert int(write_off_qty) == 0
        packaging_movement_count = await session.scalar(
            select(func.count(InventoryMovement.id)).where(
                InventoryMovement.tenant_id == tenant_id,
                InventoryMovement.product_id == product_id,
                InventoryMovement.movement_type == "packaging_convert",
            )
        )
        assert int(packaging_movement_count or 0) == 0

        order = await session.get(FbsOrder, order_id)
        assert order is not None
        reservation = await session.scalar(
            select(FbsOrderReservation).where(FbsOrderReservation.fbs_order_id == order.id)
        )
        assert reservation is not None

        available_before_delivery = await fbs_available_qty_for_product(
            session, tenant_id, uuid.UUID(warehouse_id), product_id
        )
        assert available_before_delivery == 4


# WB packaging records a fact even without a pick or physical stock.
@pytest.mark.asyncio
async def test_fbs_packing_without_stock_in_line_location(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    """A WB packaging fact has no pick or inventory prerequisite."""
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token_payload = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(token_payload.json()["tenant_id"])

    # Создать поставку с заказами
    supply_id, order_ids = await _create_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
    )

    # Получить информацию о товарах в заказах
    async with SessionLocal() as session:
        orders = list(
            (
                await session.execute(
                    select(FbsOrder).where(FbsOrder.supply_id == uuid.UUID(supply_id))
                )
            ).scalars()
        )
        product_ids = {order.product_id for order in orders if order.product_id is not None}

        # ВАЖНО: НЕ добавляем товар в сортировку — оставляем ноль остатка
        # Это симулирует ситуацию, когда оператор забыл закончить подбор

        await session.commit()

    # Переводим поставку в статус assembling (должен создать упаковку)
    status_resp = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    assert status_resp.status_code == 200, status_resp.text
    task_id = status_resp.json()["packaging_task_id"]

    # Получить задачу упаковки
    task = await async_client.get(
        f"/operations/packaging-tasks/{task_id}",
        headers=headers,
    )
    assert task.status_code == 200, task.text
    task_data = task.json()

    # Упаковать первую линию: это должно пройти, несмотря на нулевой остаток
    first_line = task_data["lines"][0]
    pack_resp = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{first_line['id']}/pack",
        headers=headers,
        json={"quantity": 1, "idempotency_key": str(uuid.uuid4())},
    )

    # Должно быть успешно (200), а не 400 с insufficient_packaging_stock
    assert pack_resp.status_code == 200, pack_resp.text

    pack_result = pack_resp.json()

    assert pack_result.get("warnings") is None

    # Проверить, что заказ помечен как упакованный в ответе
    assert pack_result["fulfilled_order"] is not None
    fulfilled_order_from_api = pack_result["fulfilled_order"]
    assert fulfilled_order_from_api["pack_status"] == "packed"

    # Проверить, что остаток не ушёл в минус
    async with SessionLocal() as session:
        # Проверить, что остаток не ушёл в минус
        # Остаток в сортировке должен остаться нулевым (или не измениться)
        sorting = await get_or_create_sorting_location(
            session, tenant_id, uuid.UUID(warehouse_id)
        )
        balances = list(
            (
                await session.execute(
                    select(InventoryBalance).where(
                        InventoryBalance.storage_location_id == sorting.id,
                        InventoryBalance.tenant_id == tenant_id,
                    )
                )
            ).scalars()
        )
        # Все остатки должны быть >= 0
        for balance in balances:
            assert balance.quantity >= 0, f"Остаток в минусе: {balance.quantity}"

        # The packaging fact exists, but it creates no inventory movement.
        movements = list(
            (
                await session.execute(
                    select(InventoryMovement).where(
                        InventoryMovement.tenant_id == tenant_id,
                        InventoryMovement.product_id.in_(product_ids),
                        InventoryMovement.movement_type == "packaging_convert",
                    )
                )
            ).scalars()
        )
        assert movements == []


@pytest.mark.asyncio
async def test_fbs_packing_does_not_convert_stock_from_other_warehouse(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    """WB packaging never searches for or converts stock in another warehouse."""
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token_payload = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(token_payload.json()["tenant_id"])

    supply_id, _order_ids = await _create_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
    )
    # Второй склад того же клиента, и весь товар лежит в его ячейке сортировки.
    other = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WH-2", "code": f"wh2-{suffix[-8:]}"},
    )
    assert other.status_code in (200, 201), other.text
    other_warehouse_id = uuid.UUID(other.json()["id"])

    async with SessionLocal() as session:
        orders = list(
            (
                await session.execute(
                    select(FbsOrder).where(FbsOrder.supply_id == uuid.UUID(supply_id))
                )
            ).scalars()
        )
        product_ids = [order.product_id for order in orders if order.product_id is not None]
        assert product_ids

        own_sorting = await get_or_create_sorting_location(
            session, tenant_id, uuid.UUID(warehouse_id)
        )
        other_sorting = await get_or_create_sorting_location(
            session, tenant_id, other_warehouse_id
        )
        # В своей ячейке пусто, в чужой — есть.
        for product_id in set(product_ids):
            await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=tenant_id,
                product_id=product_id,
                storage_location_id=other_sorting.id,
                quantity_delta=5,
                movement_type="inbound_intake",
                actor_user_id=await resolve_test_actor_user_id(session, tenant_id),
            )
        await session.commit()
        own_sorting_id = own_sorting.id
        other_sorting_id = other_sorting.id

    status_resp = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": "assembling"},
    )
    assert status_resp.status_code == 200, status_resp.text
    task_id = status_resp.json()["packaging_task_id"]

    task = await async_client.get(f"/operations/packaging-tasks/{task_id}", headers=headers)
    assert task.status_code == 200, task.text
    first_line = task.json()["lines"][0]
    assert first_line["storage_location_id"] == str(own_sorting_id)

    async with SessionLocal() as session:
        before = await session.scalar(
            select(InventoryBalance.quantity_unpacked).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == uuid.UUID(first_line["product_id"]),
                InventoryBalance.storage_location_id == other_sorting_id,
            )
        )

    pack_resp = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{first_line['id']}/pack",
        headers=headers,
        json={"quantity": 1, "idempotency_key": str(uuid.uuid4())},
    )
    assert pack_resp.status_code == 200, pack_resp.text
    body = pack_resp.json()
    assert body.get("warnings") is None

    async with SessionLocal() as session:
        after = await session.scalar(
            select(InventoryBalance.quantity_unpacked).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == uuid.UUID(first_line["product_id"]),
                InventoryBalance.storage_location_id == other_sorting_id,
            )
        )
        assert int(after or 0) == int(before or 0)
        packaging_movements = await session.scalar(
            select(func.count(InventoryMovement.id)).where(
                InventoryMovement.tenant_id == tenant_id,
                InventoryMovement.product_id.in_(set(product_ids)),
                InventoryMovement.movement_type == "packaging_convert",
            )
        )
        assert int(packaging_movements or 0) == 0
        balances = list(
            (
                await session.execute(
                    select(InventoryBalance).where(
                        InventoryBalance.tenant_id == tenant_id,
                        InventoryBalance.product_id.in_(set(product_ids)),
                    )
                )
            ).scalars()
        )
        for balance in balances:
            assert balance.quantity >= 0
            assert balance.quantity_unpacked >= 0
            assert balance.quantity_packed >= 0


@pytest.mark.asyncio
async def test_fbs_packaging_task_completes_without_stock_or_supply_promotion(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    """Completing WB packaging changes only packaging facts and task state."""
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token_payload = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(token_payload.json()["tenant_id"])

    supply_id, _order_ids = await _create_supply_with_orders(
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
    task_id = status_resp.json()["packaging_task_id"]

    task = await async_client.get(f"/operations/packaging-tasks/{task_id}", headers=headers)
    assert task.status_code == 200, task.text
    for line in task.json()["lines"]:
        remaining = int(line["qty_total"]) - int(line.get("qty_packed_in_task") or 0)
        if remaining < 1:
            continue
        packed = await async_client.post(
            f"/operations/packaging-tasks/{task_id}/lines/{line['id']}/pack",
            headers=headers,
            json={"quantity": remaining, "idempotency_key": str(uuid.uuid4())},
        )
        assert packed.status_code == 200, packed.text

    done = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/complete",
        headers=headers,
        json={"acknowledge_all_packed": False},
    )
    assert done.status_code == 200, done.text

    supply_after = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}", headers=headers
    )
    assert supply_after.status_code == 200, supply_after.text
    assert supply_after.json()["status"] == FBS_SUPPLY_STATUS_ASSEMBLING

    async with SessionLocal() as session:
        balances = list(
            (
                await session.execute(
                    select(InventoryBalance).where(InventoryBalance.tenant_id == tenant_id)
                )
            ).scalars()
        )
        for balance in balances:
            assert balance.quantity >= 0
            assert balance.quantity_unpacked >= 0
            assert balance.quantity_packed >= 0


@pytest.mark.asyncio
async def test_tape_covers_every_order_and_matches_picking_list(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    """Гарантия полноты: в ленте столько же заказов, сколько в поставке и в листе подбора.

    Оператор печатает ленту и лист подбора, идёт собирать по ним. Если лента короче
    состава поставки, часть заказов просто не существует для склада — 21.08.2026 так и
    было. Тест держит равенство трёх чисел: заказы поставки, строки листа подбора,
    заказы в ленте.
    """
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
    assert order_ids

    picking = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/picking-list", headers=headers
    )
    assert picking.status_code == 200, picking.text
    picking_total = sum(int(item["quantity"]) for item in picking.json()["items"])
    assert picking_total == len(order_ids), "лист подбора обязан покрывать все заказы поставки"
    assert [item["article"] for item in picking.json()["items"]] == ["ART-A", "ART-B"]

    tape = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/order-print-tape",
        headers=headers,
        json={
            "order_ids": [str(oid) for oid in order_ids],
            "layout": None,
            "allow_partial": False,
            "include_order_qr": True,
            "reprint": False,
        },
    )
    assert tape.status_code == 200, tape.text
    tape_body = tape.json()
    assert len(tape_body["orders"]) == len(order_ids), tape_body.get("order_errors")
    assert not tape_body.get("order_errors")
    assert [item["wb_order_id"] for item in tape_body["orders"]] == [
        910001,
        910003,
        910002,
    ], "полная лента обязана идти группами в том же порядке, что и лист подбора"

    partial = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/order-print-tape",
        headers=headers,
        json={
            "order_ids": [str(order_ids[1]), str(order_ids[0])],
            "layout": None,
            "allow_partial": True,
            "include_order_qr": True,
            "reprint": True,
        },
    )
    assert partial.status_code == 200, partial.text
    assert [item["wb_order_id"] for item in partial.json()["orders"]] == [910002, 910001]

    # Повторная печать не должна давать ленту короче: заказы уже помечены напечатанными,
    # но в ленту обязаны попасть все — иначе после зажёванной бумаги не перепечатать.
    again = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/order-print-tape",
        headers=headers,
        json={
            "order_ids": [str(oid) for oid in order_ids],
            "layout": None,
            "allow_partial": False,
            "include_order_qr": True,
            "reprint": True,
        },
    )
    assert again.status_code == 200, again.text
    assert len(again.json()["orders"]) == len(order_ids)
