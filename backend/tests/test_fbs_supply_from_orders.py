"""FBSFLOW-040 — preflight, atomic from-orders, start-work (TC-01..06)."""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_IN_SUPPLY,
    FBS_ORDER_STATUS_NEW,
    FbsOrder,
)
from app.models.fbs_supply import FbsSupply
from app.models.fbs_wb_operation import (
    WB_OPERATION_STATE_CONFIRMED,
    WB_OPERATION_STATE_PENDING_CONFIRMATION,
    FbsWbOperation,
)
from app.models.product import Product
from app.services import inventory_service
from app.services.wb_marketplace_orders_service import upsert_order_from_wb_row
from app.services.wildberries_client import WildberriesClientError
from tests.fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID, seed_fbs_warehouse_binding


async def _register_ff_admin(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS from-orders {suffix}",
            "slug": f"fbs-from-orders-{suffix}",
            "admin_email": f"fbs-from-orders-{suffix}@example.com",
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
) -> tuple[str, str, str]:
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
        json={"name": "WH", "code": f"wh-{uuid.uuid4().hex[:10]}"},
    )
    assert warehouse.status_code in (200, 201), warehouse.text
    location = await async_client.post(
        f"/warehouses/{warehouse.json()['id']}/locations",
        headers=headers,
        json={"code": f"A-{uuid.uuid4().hex[:10]}"},
    )
    assert location.status_code in (200, 201), location.text
    return seller_id, warehouse.json()["id"], location.json()["id"]


def _wb_order_row(
    *,
    order_id: int,
    article: str = "ART-001",
    barcode: str | None = None,
    wb_warehouse_id: int = DEFAULT_WB_WAREHOUSE_ID,
    is_legal: bool = False,
    cargo_type: int = 1,
    can_pvz: bool = True,
) -> dict[str, Any]:
    now = datetime.now(tz=UTC)
    created_at = (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    return {
        "id": order_id,
        "rid": f"rid-{order_id}",
        "createdAt": created_at,
        "nmId": 900001,
        "chrtId": 555,
        "article": article,
        "skus": [barcode or f"BAR-{order_id}"],
        "price": 199900,
        "cargoType": cargo_type,
        "officeId": 42,
        "isLegal": is_legal,
        "canPvz": can_pvz,
        "warehouseId": wb_warehouse_id,
    }


async def _create_ready_order(
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    location_id: uuid.UUID,
    product: Product,
    *,
    order_id: int,
    wb_warehouse_id: int = DEFAULT_WB_WAREHOUSE_ID,
    is_legal: bool = False,
    cargo_type: int = 1,
    can_pvz: bool = True,
) -> uuid.UUID:
    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
            wb_warehouse_id=wb_warehouse_id,
        )
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product.id,
            storage_location_id=location_id,
            quantity_delta=3,
            movement_type="inbound_intake",
        )
        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_id,
            _wb_order_row(
                order_id=order_id,
                barcode=product.wb_barcode or f"BAR-{order_id}",
                wb_warehouse_id=wb_warehouse_id,
                is_legal=is_legal,
                cargo_type=cargo_type,
                can_pvz=can_pvz,
            ),
        )
        order.product_id = product.id
        await session.commit()
        return order.id


async def _create_product(
    async_client: AsyncClient,
    headers: dict[str, str],
    seller_id: str,
    *,
    sku: str,
) -> Product:
    resp = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": f"Product {sku}",
            "sku_code": sku,
            "seller_id": seller_id,
            "wb_barcode": f"BAR-{sku}",
        },
    )
    assert resp.status_code in (200, 201), resp.text
    async with SessionLocal() as session:
        product = await session.get(Product, uuid.UUID(resp.json()["id"]))
        assert product is not None
        return product


@pytest.fixture
def enable_wb_marketplace_supplies_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.settings import settings

    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)


# TC-01 — seller isolation: each seller gets its own supply via from-orders
@pytest.mark.asyncio
async def test_tc01_from_orders_per_seller(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])

    seller_a, wh_a, loc_a = await _setup_seller_with_token(async_client, headers, f"a-{suffix}")
    seller_b, wh_b, loc_b = await _setup_seller_with_token(async_client, headers, f"b-{suffix}")

    prod_a = await _create_product(async_client, headers, seller_a, sku=f"A-{suffix[-6:]}")
    prod_b = await _create_product(async_client, headers, seller_b, sku=f"B-{suffix[-6:]}")

    order_a = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_a),
        uuid.UUID(wh_a),
        uuid.UUID(loc_a),
        prod_a,
        order_id=850001,
    )
    order_b = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_b),
        uuid.UUID(wh_b),
        uuid.UUID(loc_b),
        prod_b,
        order_id=850002,
    )

    create_a = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "Supply A",
            "order_ids": [str(order_a)],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert create_a.status_code == 201, create_a.text
    body_a = create_a.json()
    assert body_a["supply"]["seller"]["id"] == seller_a
    assert len(body_a["orders"]) == 1

    create_b = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "Supply B",
            "order_ids": [str(order_b)],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert create_b.status_code == 201, create_b.text
    assert create_b.json()["supply"]["seller"]["id"] == seller_b
    assert create_b.json()["supply"]["id"] != body_a["supply"]["id"]


# TC-02 — different WB warehouses → preflight incompatible
@pytest.mark.asyncio
async def test_tc02_preflight_different_wb_warehouses(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product = await _create_product(async_client, headers, seller_id, sku=f"wh-{suffix[-6:]}")

    order_1 = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=851001,
        wb_warehouse_id=501001,
    )
    order_2 = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=851002,
        wb_warehouse_id=501001,
    )
    async with SessionLocal() as session:
        order_row = await session.get(FbsOrder, order_2)
        assert order_row is not None
        order_row.wb_warehouse_id = 501002
        await session.commit()

    preflight = await async_client.post(
        "/operations/fbs-supplies/preflight",
        headers=headers,
        json={
            "order_ids": [str(order_1), str(order_2)],
            "planned_delivery_type": "warehouse_sc",
        },
    )
    assert preflight.status_code == 200, preflight.text
    body = preflight.json()
    assert body["compatible"] is False
    codes = {issue["code"] for issue in body["issues"]}
    assert "different_wb_warehouse" in codes

    create = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "Should fail",
            "order_ids": [str(order_1), str(order_2)],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert create.status_code == 409
    detail = create.json()["detail"]
    assert detail["code"] == "order_incompatible"


# TC-03 — B2C + B2B incompatible
@pytest.mark.asyncio
async def test_tc03_preflight_b2c_b2b_incompatible(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product = await _create_product(async_client, headers, seller_id, sku=f"b2b-{suffix[-6:]}")

    order_b2c = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=852001,
        is_legal=False,
    )
    order_b2b = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=852002,
        is_legal=True,
    )

    preflight = await async_client.post(
        "/operations/fbs-supplies/preflight",
        headers=headers,
        json={
            "order_ids": [str(order_b2c), str(order_b2b)],
            "planned_delivery_type": "warehouse_sc",
        },
    )
    assert preflight.status_code == 200, preflight.text
    assert preflight.json()["compatible"] is False
    assert any(
        i["code"] == "legal_type_mismatch" for i in preflight.json()["issues"]
    )


# TC-04 — different cargo types incompatible
@pytest.mark.asyncio
async def test_tc04_preflight_different_cargo_types(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product = await _create_product(async_client, headers, seller_id, sku=f"cargo-{suffix[-6:]}")

    order_mgt = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=853001,
        cargo_type=1,
    )
    order_kgt = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=853002,
        cargo_type=2,
    )

    preflight = await async_client.post(
        "/operations/fbs-supplies/preflight",
        headers=headers,
        json={
            "order_ids": [str(order_mgt), str(order_kgt)],
            "planned_delivery_type": "warehouse_sc",
        },
    )
    assert preflight.status_code == 200, preflight.text
    assert preflight.json()["compatible"] is False
    assert any(
        i["code"] == "different_cargo_type" for i in preflight.json()["issues"]
    )


# TC-05 — PVZ blocked for can_pvz=false; warehouse_sc still allowed
@pytest.mark.asyncio
async def test_tc05_preflight_pvz_can_pvz_gate(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product = await _create_product(async_client, headers, seller_id, sku=f"pvz-{suffix[-6:]}")

    order_ok = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=854001,
        can_pvz=True,
    )
    order_no_pvz = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=854002,
        can_pvz=False,
    )

    pvz_preflight = await async_client.post(
        "/operations/fbs-supplies/preflight",
        headers=headers,
        json={
            "order_ids": [str(order_ok), str(order_no_pvz)],
            "planned_delivery_type": "pvz",
        },
    )
    assert pvz_preflight.status_code == 200, pvz_preflight.text
    pvz_body = pvz_preflight.json()
    assert pvz_body["compatible"] is False
    assert pvz_body["summary"]["pvz_blocked_count"] == 1
    assert any(i["code"] == "pvz_not_allowed" for i in pvz_body["issues"])

    sc_preflight = await async_client.post(
        "/operations/fbs-supplies/preflight",
        headers=headers,
        json={
            "order_ids": [str(order_ok), str(order_no_pvz)],
            "planned_delivery_type": "warehouse_sc",
        },
    )
    assert sc_preflight.status_code == 200, sc_preflight.text
    assert sc_preflight.json()["compatible"] is True


# TC-06 — atomic from-orders creates supply + orders in one call
@pytest.mark.asyncio
async def test_tc06_atomic_from_orders_workspace(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product = await _create_product(async_client, headers, seller_id, sku=f"atom-{suffix[-6:]}")

    order_ids = [
        await _create_ready_order(
            tenant_id,
            uuid.UUID(seller_id),
            uuid.UUID(warehouse_id),
            uuid.UUID(location_id),
            product,
            order_id=855001 + idx,
        )
        for idx in range(2)
    ]

    create = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "Atomic supply",
            "order_ids": [str(oid) for oid in order_ids],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert create.status_code == 201, create.text
    workspace = create.json()
    assert workspace["supply"]["name"] == "Atomic supply"
    assert workspace["supply"]["wb_supply_id"].startswith("WB-GI-MOCK-")
    assert len(workspace["orders"]) == 2
    assert all(o["status"] == FBS_ORDER_STATUS_IN_SUPPLY for o in workspace["orders"])


@pytest.mark.asyncio
async def test_from_orders_idempotency_same_key(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product = await _create_product(async_client, headers, seller_id, sku=f"idem-{suffix[-6:]}")
    order_id = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=856001,
    )
    idem_key = str(uuid.uuid4())
    payload = {
        "name": "Idem supply",
        "order_ids": [str(order_id)],
        "planned_delivery_type": "warehouse_sc",
        "idempotency_key": idem_key,
    }
    first = await async_client.post(
        "/operations/fbs-supplies/from-orders", headers=headers, json=payload
    )
    second = await async_client.post(
        "/operations/fbs-supplies/from-orders", headers=headers, json=payload
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["supply"]["id"] == second.json()["supply"]["id"]

    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(FbsSupply))
        assert count == 1


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
async def test_parallel_from_orders_one_order_one_supply(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    if "sqlite" in os.environ.get("DATABASE_URL", "").lower():
        pytest.skip("row-level FOR UPDATE locking requires PostgreSQL")

    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product = await _create_product(async_client, headers, seller_id, sku=f"race-{suffix[-6:]}")
    order_id = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=857001,
    )

    resp_a, resp_b = await asyncio.gather(
        async_client.post(
            "/operations/fbs-supplies/from-orders",
            headers=headers,
            json={
                "name": "Race A",
                "order_ids": [str(order_id)],
                "planned_delivery_type": "warehouse_sc",
                "idempotency_key": str(uuid.uuid4()),
            },
        ),
        async_client.post(
            "/operations/fbs-supplies/from-orders",
            headers=headers,
            json={
                "name": "Race B",
                "order_ids": [str(order_id)],
                "planned_delivery_type": "warehouse_sc",
                "idempotency_key": str(uuid.uuid4()),
            },
        ),
    )
    statuses = sorted([resp_a.status_code, resp_b.status_code])
    assert statuses == [201, 409], (resp_a.text, resp_b.text)
    rejected = resp_a if resp_a.status_code == 409 else resp_b
    assert rejected.json()["detail"]["code"] == "order_incompatible"

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.supply_id is not None
        assert order.status == FBS_ORDER_STATUS_IN_SUPPLY
        supply_count = await session.scalar(select(func.count()).select_from(FbsSupply))
        assert supply_count == 1


@pytest.mark.asyncio
async def test_batch_timeout_pending_confirmation_no_false_success(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product = await _create_product(async_client, headers, seller_id, sku=f"tout-{suffix[-6:]}")
    order_id = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=858001,
    )
    idem_key = str(uuid.uuid4())

    batch_calls = {"count": 0}

    async def fail_batch_first_call_only(
        client: object,
        *,
        api_token: str,
        supply_id: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> None:
        batch_calls["count"] += 1
        if batch_calls["count"] == 1:
            raise WildberriesClientError("transport_error")

    monkeypatch.setattr(
        "app.services.fbs_supply_service.add_orders_to_marketplace_supply",
        fail_batch_first_call_only,
    )

    resp = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "Timeout supply",
            "order_ids": [str(order_id)],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": idem_key,
        },
    )
    assert resp.status_code == 504, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "wb_timeout"
    assert detail["retryable"] is True

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.supply_id is None
        assert order.status == FBS_ORDER_STATUS_NEW
        op = await session.scalar(
            select(FbsWbOperation).where(FbsWbOperation.idempotency_key == idem_key)
        )
        assert op is not None
        assert op.state == WB_OPERATION_STATE_PENDING_CONFIRMATION

    retry = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "Timeout supply",
            "order_ids": [str(order_id)],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": idem_key,
        },
    )
    assert retry.status_code == 201, retry.text
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.supply_id is not None
        assert order.status == FBS_ORDER_STATUS_IN_SUPPLY

    async with SessionLocal() as session:
        supply_count = await session.scalar(select(func.count()).select_from(FbsSupply))
        assert supply_count == 1
        op = await session.scalar(
            select(FbsWbOperation).where(FbsWbOperation.idempotency_key == idem_key)
        )
        assert op is not None
        assert op.state == WB_OPERATION_STATE_CONFIRMED


@pytest.mark.asyncio
async def test_add_failure_no_false_success_legacy_path(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product = await _create_product(async_client, headers, seller_id, sku=f"fail-{suffix[-6:]}")
    order_id = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=859001,
    )

    create = await async_client.post(
        "/operations/fbs-supplies",
        headers=headers,
        json={
            "seller_id": seller_id,
            "warehouse_id": warehouse_id,
            "name": "Legacy",
            "delivery_type": "warehouse_sc",
        },
    )
    assert create.status_code == 201, create.text
    supply_id = create.json()["id"]

    async def fail_add(
        client: object,
        *,
        api_token: str,
        supply_id: str,
        order_id: int,
        marketplace_api_base: str | None = None,
    ) -> None:
        raise WildberriesClientError("upstream_error", status_code=502)

    monkeypatch.setattr(
        "app.services.fbs_supply_service.add_order_to_marketplace_supply",
        fail_add,
    )

    add = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/orders",
        headers=headers,
        json={"order_id": str(order_id)},
    )
    assert add.status_code == 502

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.supply_id is None
        assert order.status == FBS_ORDER_STATUS_NEW


@pytest.mark.asyncio
async def test_start_work_idempotent_packaging_task(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product = await _create_product(async_client, headers, seller_id, sku=f"work-{suffix[-6:]}")
    order_id = await _create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=860001,
    )

    create = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "Work supply",
            "order_ids": [str(order_id)],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert create.status_code == 201, create.text
    supply_id = create.json()["supply"]["id"]

    first = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/start-work",
        headers=headers,
    )
    second = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/start-work",
        headers=headers,
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["supply"]["packaging_task_id"] is not None
    assert (
        first.json()["supply"]["packaging_task_id"]
        == second.json()["supply"]["packaging_task_id"]
    )
