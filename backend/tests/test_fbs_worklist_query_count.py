"""FBS worklist read API — happy path and bounded query count."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import event, select

from app.db.session import SessionLocal, engine
from app.models.fbs_order import (
    FBS_ORDER_STATUS_DONE,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_NEW,
    FBS_ORDER_STATUS_SORTED,
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
)
from app.models.product import Product
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.tenant_wb_mp_warehouse import TenantWbMpWarehouse
from app.services import inventory_service
from app.services.fbs_worklist_service import build_worklist_items
from tests.fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID, seed_fbs_warehouse_binding


async def _setup_ff_admin_with_stock(
    async_client: AsyncClient,
    *,
    order_count: int = 1,
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, list[uuid.UUID]]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS worklist {suffix}",
            "slug": f"fbs-worklist-{suffix}",
            "admin_email": f"fbs-worklist-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    seller = await async_client.post("/sellers", headers=headers, json={"name": f"Seller {suffix}"})
    assert seller.status_code in (200, 201), seller.text
    seller_id = uuid.UUID(seller.json()["id"])
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
        json={"code": f"CELL-{suffix[-6:]}"},
    )
    assert location.status_code in (200, 201), location.text
    location_id = uuid.UUID(location.json()["id"])
    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "FBS product",
            "sku_code": f"FBS-{suffix}",
            "seller_id": str(seller_id),
            "wb_nm_id": 900_100,
            "wb_barcode": f"BAR-{suffix[-8:]}",
        },
    )
    assert product.status_code in (200, 201), product.text
    product_id = uuid.UUID(product.json()["id"])

    async with SessionLocal() as session:
        product_row = await session.get(Product, product_id)
        assert product_row is not None
        tenant_id = product_row.tenant_id
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
        )
        session.add(
            TenantWbMpWarehouse(
                tenant_id=tenant_id,
                wb_warehouse_id=DEFAULT_WB_WAREHOUSE_ID,
                name="WB Москва",
                is_active=True,
                is_transit_active=False,
            )
        )
        session.add(
            SellerWildberriesImportedCard(
                tenant_id=tenant_id,
                seller_id=seller_id,
                nm_id=900_100,
                vendor_code=f"ART-{suffix[-6:]}",
                title="Футболка",
                raw_json={
                    "nmID": 900_100,
                    "photos": [{"big": "https://images.example/wb.jpg"}],
                    "sizes": [{"skus": [f"BAR-{suffix[-8:]}"], "techSize": "L"}],
                },
            )
        )
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=location_id,
            quantity_delta=50,
            movement_type="inbound_intake",
        )
        now = datetime.now(tz=UTC)
        order_ids: list[uuid.UUID] = []
        for idx in range(order_count):
            order = FbsOrder(
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                product_id=product_id,
                wb_order_id=800_000 + idx,
                wb_nm_id=900_100,
                wb_barcode=f"BAR-{suffix[-8:]}",
                wb_article=f"ART-{suffix[-6:]}",
                cargo_type="mgt",
                wb_warehouse_id=DEFAULT_WB_WAREHOUSE_ID,
                can_pvz=True,
                status=FBS_ORDER_STATUS_NEW,
                wb_status="new",
                created_at_wb=now - timedelta(hours=1),
                deadline_at=now + timedelta(hours=24 + idx),
                mapping_status=MAPPING_STATUS_MAPPED,
                reserve_status=RESERVE_STATUS_RESERVED,
            )
            session.add(order)
            await session.flush()
            order_ids.append(order.id)
        await session.commit()

    return headers, seller_id, warehouse_id, product_id, location_id, order_ids


@pytest.mark.asyncio
async def test_fbs_worklist_happy_path(async_client: AsyncClient) -> None:
    """TC-NEW-FBS-WORKLIST-001: enriched worklist item without price."""
    (
        headers,
        seller_id,
        _warehouse_id,
        _product_id,
        _location_id,
        order_ids,
    ) = await _setup_ff_admin_with_stock(async_client, order_count=1)
    resp = await async_client.get(
        "/operations/fbs-orders/worklist",
        headers=headers,
        params={"seller_id": str(seller_id), "status_group": "new", "limit": 10},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "server_now" in body
    assert body["next_cursor"] is None
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["id"] == str(order_ids[0])
    assert item["wb_order_id"] == 800_000
    assert item["seller"]["name"].startswith("Seller ")
    assert item["wb_warehouse"]["name"] == "WB Москва"
    assert item["wms_warehouse"]["name"] == "WH"
    assert item["product"]["image_url"] == "https://images.example/wb.jpg"
    assert item["product"]["size"] == "L"
    assert item["inventory"]["available_unpacked"] >= 0
    assert len(item["inventory"]["locations"]) >= 1
    assert "price" not in item
    assert item["selection_blockers"] == []
    options_by_id = {option["id"]: option for option in body["warehouse_options"]}
    assert str(DEFAULT_WB_WAREHOUSE_ID) in options_by_id
    assert options_by_id[str(DEFAULT_WB_WAREHOUSE_ID)]["name"] == "WB Москва"


@pytest.mark.asyncio
async def test_fbs_worklist_delivery_and_done_groups(async_client: AsyncClient) -> None:
    """TC-S17-001: transferred and completed orders remain visible in separate groups."""
    headers, seller_id, _, _, _, order_ids = await _setup_ff_admin_with_stock(
        async_client, order_count=1
    )
    order_id = order_ids[0]

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        order.status = FBS_ORDER_STATUS_IN_DELIVERY
        await session.commit()

    delivery = await async_client.get(
        "/operations/fbs-orders/worklist",
        headers=headers,
        params={"seller_id": str(seller_id), "status_group": "delivery"},
    )
    assert delivery.status_code == 200, delivery.text
    assert [item["id"] for item in delivery.json()["items"]] == [str(order_id)]

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        order.status = FBS_ORDER_STATUS_SORTED
        await session.commit()

    sorted_delivery = await async_client.get(
        "/operations/fbs-orders/worklist",
        headers=headers,
        params={"seller_id": str(seller_id), "status_group": "delivery"},
    )
    assert sorted_delivery.status_code == 200, sorted_delivery.text
    assert [item["id"] for item in sorted_delivery.json()["items"]] == [str(order_id)]

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        order.status = FBS_ORDER_STATUS_DONE
        await session.commit()

    done = await async_client.get(
        "/operations/fbs-orders/worklist",
        headers=headers,
        params={"seller_id": str(seller_id), "status_group": "done"},
    )
    assert done.status_code == 200, done.text
    assert [item["id"] for item in done.json()["items"]] == [str(order_id)]


@pytest.mark.asyncio
async def test_fbs_worklist_filters_new_orders_by_warehouse(async_client: AsyncClient) -> None:
    """TC-S17-025: worklist filters new orders by seller warehouse."""
    (
        headers,
        seller_id,
        _warehouse_a_id,
        product_id,
        _location_a_id,
        order_ids,
    ) = await _setup_ff_admin_with_stock(async_client, order_count=1)
    suffix = str(time.time_ns())
    warehouse_b = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WH B", "code": f"whb-{suffix[-8:]}"},
    )
    assert warehouse_b.status_code in (200, 201), warehouse_b.text
    warehouse_b_id = uuid.UUID(warehouse_b.json()["id"])
    location_b = await async_client.post(
        f"/warehouses/{warehouse_b_id}/locations",
        headers=headers,
        json={"code": f"CELL-B-{suffix[-6:]}"},
    )
    assert location_b.status_code in (200, 201), location_b.text
    location_b_id = uuid.UUID(location_b.json()["id"])
    wb_warehouse_b = DEFAULT_WB_WAREHOUSE_ID + 1

    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        tenant_id = product.tenant_id
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_b_id,
            wb_warehouse_id=wb_warehouse_b,
        )
        session.add(
            TenantWbMpWarehouse(
                tenant_id=tenant_id,
                wb_warehouse_id=wb_warehouse_b,
                name="WB Казань",
                is_active=True,
                is_transit_active=False,
            )
        )
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=location_b_id,
            quantity_delta=20,
            movement_type="inbound_intake",
        )
        now = datetime.now(tz=UTC)
        order_b = FbsOrder(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_b_id,
            product_id=product_id,
            wb_order_id=801_000,
            wb_nm_id=900_100,
            wb_barcode=f"BAR-B-{suffix[-8:]}",
            wb_article=f"ART-B-{suffix[-6:]}",
            cargo_type="mgt",
            wb_warehouse_id=wb_warehouse_b,
            can_pvz=True,
            status=FBS_ORDER_STATUS_NEW,
            wb_status="new",
            created_at_wb=now - timedelta(hours=1),
            deadline_at=now + timedelta(hours=25),
            mapping_status=MAPPING_STATUS_MAPPED,
            reserve_status=RESERVE_STATUS_RESERVED,
        )
        session.add(order_b)
        await session.flush()
        order_b_id = order_b.id
        await session.commit()

    unfiltered = await async_client.get(
        "/operations/fbs-orders/worklist",
        headers=headers,
        params={"seller_id": str(seller_id), "status_group": "new", "limit": 10},
    )
    assert unfiltered.status_code == 200, unfiltered.text
    option_ids = {option["id"] for option in unfiltered.json()["warehouse_options"]}
    assert {str(DEFAULT_WB_WAREHOUSE_ID), str(wb_warehouse_b)} <= option_ids

    filtered = await async_client.get(
        "/operations/fbs-orders/worklist",
        headers=headers,
        params={
            "seller_id": str(seller_id),
            "status_group": "new",
            "wb_warehouse_id": wb_warehouse_b,
            "limit": 10,
        },
    )
    assert filtered.status_code == 200, filtered.text
    body = filtered.json()
    assert [item["id"] for item in body["items"]] == [str(order_b_id)]
    assert {option["id"] for option in body["warehouse_options"]} == option_ids
    assert str(order_ids[0]) not in {item["id"] for item in body["items"]}


@pytest.mark.asyncio
async def test_fbs_worklist_query_count_bounded(async_client: AsyncClient) -> None:
    """50 orders must not trigger per-order query storms."""
    (
        headers,
        seller_id,
        _warehouse_id,
        product_id,
        _location_id,
        _order_ids,
    ) = await _setup_ff_admin_with_stock(async_client, order_count=50)

    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        tenant_id = product.tenant_id
        stmt_orders = (
            select(FbsOrder)
            .where(
                FbsOrder.tenant_id == tenant_id,
                FbsOrder.seller_id == seller_id,
            )
            .order_by(FbsOrder.deadline_at.asc())
        )
        res = await session.execute(stmt_orders)
        orders = list(res.scalars().all())

    query_count = 0

    def _count_query(
        _conn: object,
        _cursor: object,
        _statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        nonlocal query_count
        query_count += 1

    sync_engine = engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", _count_query)
    try:
        async with SessionLocal() as session:
            product = await session.get(Product, product_id)
            assert product is not None
            await build_worklist_items(session, product.tenant_id, orders)
    finally:
        event.remove(sync_engine, "before_cursor_execute", _count_query)

    assert query_count <= 21, f"expected <=21 queries, got {query_count}"

    api_resp = await async_client.get(
        "/operations/fbs-orders/worklist",
        headers=headers,
        params={"seller_id": str(seller_id), "limit": 500},
    )
    assert api_resp.status_code == 200, api_resp.text
    assert len(api_resp.json()["items"]) == 50
