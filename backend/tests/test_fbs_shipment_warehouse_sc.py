from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_IN_SUPPLY,
    FBS_ORDER_STATUS_NEW,
    FBS_ORDER_STATUS_PACKED,
    FbsOrder,
)
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FbsSupply,
)
from app.models.product import Product
from app.services.wb_marketplace_orders_service import upsert_order_from_wb_row
from app.services.wildberries_client import WildberriesClientError


async def _register_ff_admin(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS shipment {suffix}",
            "slug": f"fbs-ship-{suffix}",
            "admin_email": f"fbs-ship-{suffix}@example.com",
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
    reg = await async_client.get("/auth/me", headers=headers)
    assert reg.status_code == 200
    tenant_id = uuid.UUID(reg.json()["tenant_id"])
    return seller_id, warehouse.json()["id"], tenant_id


def _wb_order_row(*, order_id: int) -> dict[str, Any]:
    return {
        "id": order_id,
        "rid": f"rid-{order_id}",
        "createdAt": "2026-07-01T12:00:00+03:00",
        "nmId": 900001,
        "chrtId": 555,
        "article": "ART-001",
        "skus": [f"BAR-{order_id}"],
        "price": 199900,
        "cargoType": 1,
        "officeId": 42,
        "isLegal": False,
    }


async def _create_order(
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    order_id: int,
    product: Product | None = None,
) -> uuid.UUID:
    async with SessionLocal() as session:
        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_id,
            warehouse_id,
            _wb_order_row(order_id=order_id),
        )
        order.status = FBS_ORDER_STATUS_NEW
        if product is not None:
            order.product_id = product.id
        await session.commit()
        return order.id


async def _create_supply(
    async_client: AsyncClient,
    headers: dict[str, str],
    seller_id: str,
    warehouse_id: str,
    *,
    name: str,
    delivery_type: str = "warehouse_sc",
) -> dict[str, Any]:
    resp = await async_client.post(
        "/operations/fbs-supplies",
        headers=headers,
        json={
            "seller_id": seller_id,
            "warehouse_id": warehouse_id,
            "name": name,
            "delivery_type": delivery_type,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _prepare_supply_with_orders(
    async_client: AsyncClient,
    headers: dict[str, str],
    seller_id: str,
    warehouse_id: str,
    tenant_id: uuid.UUID,
    *,
    wb_order_ids: list[int],
    order_status: str = FBS_ORDER_STATUS_PACKED,
    supply_status: str = FBS_SUPPLY_STATUS_ASSEMBLING,
    products: list[Product | None] | None = None,
    supply_name: str,
    delivery_type: str = "warehouse_sc",
) -> tuple[dict[str, Any], list[uuid.UUID]]:
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)
    order_ids: list[uuid.UUID] = []
    for idx, wb_order_id in enumerate(wb_order_ids):
        product = products[idx] if products is not None else None
        order_ids.append(
            await _create_order(
                tenant_id,
                seller_uuid,
                warehouse_uuid,
                order_id=wb_order_id,
                product=product,
            )
        )

    supply = await _create_supply(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        name=supply_name,
        delivery_type=delivery_type,
    )
    for local_order_id in order_ids:
        add = await async_client.post(
            f"/operations/fbs-supplies/{supply['id']}/orders",
            headers=headers,
            json={"order_id": str(local_order_id)},
        )
        assert add.status_code == 200, add.text

    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert supply_row is not None
        supply_row.status = supply_status
        for local_order_id in order_ids:
            order = await session.get(FbsOrder, local_order_id)
            assert order is not None
            order.status = order_status
        await session.commit()

    return supply, order_ids


@pytest.fixture
def enable_wb_marketplace_supplies_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)


# TC-NEW-FBS-SHIPWH-001 — deliver → in_delivery; bad order status → 400
@pytest.mark.asyncio
async def test_fbs_shipment_deliver_ok_and_orders_not_ready(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    supply, order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[950001, 950002],
        supply_name="Deliver OK",
    )

    deliver = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/deliver",
        headers=headers,
    )
    assert deliver.status_code == 200, deliver.text
    body = deliver.json()
    assert body["status"] == FBS_SUPPLY_STATUS_IN_DELIVERY
    assert body["delivered_at"] is not None
    for order in body["orders"]:
        assert order["status"] == FBS_ORDER_STATUS_IN_DELIVERY

    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert supply_row is not None
        assert supply_row.status == FBS_SUPPLY_STATUS_IN_DELIVERY
        assert supply_row.delivered_at is not None
        for local_order_id in order_ids:
            order = await session.get(FbsOrder, local_order_id)
            assert order is not None
            assert order.status == FBS_ORDER_STATUS_IN_DELIVERY

    supply_bad, _ = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[950003],
        order_status=FBS_ORDER_STATUS_NEW,
        supply_name="Deliver bad status",
    )

    bad = await async_client.post(
        f"/operations/fbs-supplies/{supply_bad['id']}/deliver",
        headers=headers,
    )
    assert bad.status_code == 400
    assert bad.json()["detail"] == "orders_not_ready"


# TC-NEW-FBS-SHIPWH-002 — barcode PNG cached
@pytest.mark.asyncio
async def test_fbs_shipment_barcode_png_cached(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    supply, _ = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[951001],
        supply_name="Barcode cache",
    )

    fetch_calls = 0

    async def counting_fetch(
        client: object,
        *,
        api_token: str,
        supply_id: str,
        type: str = "png",
        marketplace_api_base: str | None = None,
    ) -> bytes:
        nonlocal fetch_calls
        fetch_calls += 1
        from app.services.wildberries_client import _tiny_png_bytes

        return _tiny_png_bytes()

    monkeypatch.setattr(
        "app.services.fbs_shipment_service.fetch_marketplace_supply_barcode",
        counting_fetch,
    )

    first = await async_client.get(
        f"/operations/fbs-supplies/{supply['id']}/barcode",
        headers=headers,
        params={"type": "png"},
    )
    assert first.status_code == 200, first.text
    assert first.headers["content-type"].startswith("image/png")
    assert len(first.content) > 0
    assert fetch_calls == 1

    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert supply_row is not None
        assert supply_row.barcode_file is not None
        cached_path = Path(settings.wms_data_dir) / supply_row.barcode_file
        assert cached_path.is_file()

    second = await async_client.get(
        f"/operations/fbs-supplies/{supply['id']}/barcode",
        headers=headers,
        params={"type": "png"},
    )
    assert second.status_code == 200, second.text
    assert second.content == first.content
    assert fetch_calls == 1


# TC-NEW-FBS-SHIPWH-003 — requires_honest_sign without sgtin → 400; with sgtin → ok
@pytest.mark.asyncio
async def test_fbs_shipment_marking_required_and_ok(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_marking", True)

    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant_id,
            seller_id=uuid.UUID(seller_id),
            name="CHZ product",
            sku_code=f"CHZ-{suffix[-8:]}",
            requires_honest_sign=True,
        )
        session.add(product)
        await session.commit()
        await session.refresh(product)

    supply, order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[952001],
        products=[product],
        supply_name="Marking required",
    )

    missing = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/deliver",
        headers=headers,
    )
    assert missing.status_code == 400
    assert missing.json()["detail"] == "marking_required"

    put = await async_client.put(
        f"/operations/fbs-orders/{order_ids[0]}/markings/sgtin",
        headers=headers,
        json={"value": "01CIS-SHIP-001"},
    )
    assert put.status_code == 200, put.text

    deliver = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/deliver",
        headers=headers,
    )
    assert deliver.status_code == 200, deliver.text
    assert deliver.json()["status"] == FBS_SUPPLY_STATUS_IN_DELIVERY


# TC-NEW-FBS-SHIPWH-004 — WB error → statuses unchanged
@pytest.mark.asyncio
async def test_fbs_shipment_deliver_wb_error_no_status_change(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    supply, order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[953001],
        supply_name="WB fail",
    )

    async def fail_deliver(
        client: object,
        *,
        api_token: str,
        supply_id: str,
        marketplace_api_base: str | None = None,
    ) -> None:
        raise WildberriesClientError("upstream_error", status_code=502)

    monkeypatch.setattr(
        "app.services.fbs_shipment_service.deliver_marketplace_supply",
        fail_deliver,
    )

    resp = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/deliver",
        headers=headers,
    )
    assert resp.status_code == 502
    assert resp.json()["detail"] == "wb_upstream_error_502"

    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert supply_row is not None
        assert supply_row.status == FBS_SUPPLY_STATUS_ASSEMBLING
        assert supply_row.delivered_at is None
        order = await session.get(FbsOrder, order_ids[0])
        assert order is not None
        assert order.status == FBS_ORDER_STATUS_PACKED


# TC-NEW-FBS-SHIPWH-005 — pvz supply deliver requires trbx on every order
@pytest.mark.asyncio
async def test_fbs_shipment_deliver_pvz_requires_trbx(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    supply, _ = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[954001, 954002],
        supply_name="PVZ supply",
        delivery_type="pvz",
    )

    resp = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/deliver",
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "trbx_required"


# TC-NEW-FBS-SHIPWH-006 — cancelled order blocks deliver
@pytest.mark.asyncio
async def test_fbs_shipment_deliver_cancelled_order_in_supply(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    supply, order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[955001, 955002],
        order_status=FBS_ORDER_STATUS_IN_SUPPLY,
        supply_name="Cancelled in supply",
    )

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_ids[0])
        assert order is not None
        order.status = FBS_ORDER_STATUS_CANCELLED
        await session.commit()

    resp = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/deliver",
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "supply_has_cancelled_orders"

    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert supply_row is not None
        assert supply_row.status == FBS_SUPPLY_STATUS_ASSEMBLING
        assert supply_row.delivered_at is None
        for local_order_id in order_ids:
            order = await session.get(FbsOrder, local_order_id)
            assert order is not None
            assert order.status != FBS_ORDER_STATUS_IN_DELIVERY
