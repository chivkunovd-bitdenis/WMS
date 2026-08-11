from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_EXTERNAL_PROCESSING,
    FBS_ORDER_STATUS_NEW,
    MAPPING_STATUS_MAPPED,
    MAPPING_STATUS_MISSING,
    RESERVE_STATUS_NO_STOCK,
    RESERVE_STATUS_RELEASED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
    FbsOrderReservation,
)
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product import Product
from app.models.warehouse import Warehouse
from app.services import inventory_service
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.tokens import decode_access_token
from app.services.wb_marketplace_orders_service import (
    FBS_DEADLINE_HOURS,
    RESERVE_STATUS_WAREHOUSE_REMAP_CONFLICT,
    WbMarketplaceOrdersError,
    sync_seller_orders,
    upsert_order_from_wb_row,
)
from app.services.wildberries_client import WildberriesClientError

WB_WAREHOUSE_A = 501001
WB_WAREHOUSE_B = 501002
UNKNOWN_WB_WAREHOUSE = 777888


def _wb_order_row(
    *,
    order_id: int = 700001,
    barcode: str = "FBS-BARCODE-001",
    nm_id: int = 900001,
    chrt_id: int = 555,
    created_at: str = "2026-07-01T12:00:00+03:00",
    office_id: int = 42,
    warehouse_id: int = WB_WAREHOUSE_A,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": order_id,
        "rid": f"rid-{order_id}",
        "createdAt": created_at,
        "nmId": nm_id,
        "chrtId": chrt_id,
        "article": "ART-001",
        "skus": [barcode],
        "price": 199900,
        "cargoType": 1,
        "officeId": office_id,
        "isLegal": False,
    }
    if warehouse_id is not None:
        row["warehouseId"] = warehouse_id
    return row


async def _register_ff_admin(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS intake {suffix}",
            "slug": f"fbs-intake-{suffix}",
            "admin_email": f"fbs-intake-{suffix}@example.com",
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
        json={
            "supplies_api_token": "wb-marketplace-token",
            "marketplace_api_token": "wb-marketplace-token",
        },
    )
    assert tok.status_code == 200, tok.text
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WH", "code": f"wh-{suffix[-8:]}"},
    )
    assert warehouse.status_code in (200, 201), warehouse.text
    return seller_id, warehouse.json()["id"]


async def _create_binding(
    async_client: AsyncClient,
    headers: dict[str, str],
    seller_id: str,
    wb_warehouse_id: int,
    wms_warehouse_id: str,
) -> None:
    resp = await async_client.put(
        f"/operations/fbs-sellers/{seller_id}/warehouse-bindings/{wb_warehouse_id}",
        headers=headers,
        json={"wms_warehouse_id": wms_warehouse_id, "stock_sync_enabled": True},
    )
    assert resp.status_code == 200, resp.text


async def _seed_binding(
    session: Any,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    wb_warehouse_id: int,
    wms_warehouse_id: uuid.UUID,
) -> None:
    session.add(
        FbsWarehouseBinding(
            tenant_id=tenant_id,
            seller_id=seller_id,
            wb_warehouse_id=wb_warehouse_id,
            wms_warehouse_id=wms_warehouse_id,
            stock_sync_enabled=True,
            is_active=True,
        )
    )
    await session.flush()


def _patch_wb_order_fetches(
    monkeypatch: pytest.MonkeyPatch,
    *,
    new_rows: list[dict[str, Any]] | None = None,
    page_rows: list[dict[str, Any]] | None = None,
    status_rows: list[dict[str, Any]] | None = None,
    new_raises: BaseException | None = None,
    page_raises: BaseException | None = None,
    status_raises: BaseException | None = None,
) -> None:
    async def fake_new(
        client: object, *, api_token: str, marketplace_api_base: str | None = None
    ) -> list[dict[str, Any]]:
        if new_raises is not None:
            raise new_raises
        return new_rows or []

    async def fake_page(
        client: object,
        *,
        api_token: str,
        marketplace_api_base: str | None = None,
        limit: int = 100,
        next_token: int | None = None,
    ) -> tuple[list[dict[str, Any]], int | None]:
        if page_raises is not None:
            raise page_raises
        return page_rows or [], None

    async def fake_status(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[dict[str, Any]]:
        if status_raises is not None:
            raise status_raises
        if status_rows is not None:
            return status_rows
        return [{"id": oid, "wbStatus": "waiting"} for oid in order_ids]

    monkeypatch.setattr(
        "app.services.wb_marketplace_orders_service.fetch_marketplace_orders_new",
        fake_new,
    )
    monkeypatch.setattr(
        "app.services.wb_marketplace_orders_service.fetch_marketplace_orders_page",
        fake_page,
    )
    monkeypatch.setattr(
        "app.services.wb_marketplace_orders_service.fetch_marketplace_orders_status",
        fake_status,
    )


async def _wait_for_job(
    async_client: AsyncClient, headers: dict[str, str], job_id: str
) -> dict[str, Any]:
    for _ in range(40):
        await asyncio.sleep(0.12)
        job = await async_client.get(
            f"/operations/background-jobs/{job_id}", headers=headers
        )
        assert job.status_code == 200
        body = job.json()
        if body["status"] in ("done", "failed"):
            return body
    raise AssertionError("sync job did not finish")


@pytest.fixture(autouse=True)
def _disable_wb_mp_background_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    async def noop(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        "app.services.wb_mp_warehouse_service.run_wb_mp_warehouses_sync_task",
        noop,
    )


# TC-NEW-FBS-INTAKE-001
@pytest.mark.asyncio
async def test_fbs_order_upsert_idempotent_and_deadline(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    await _create_binding(async_client, headers, seller_id, WB_WAREHOUSE_A, warehouse_id)
    row = _wb_order_row(order_id=800001)

    _patch_wb_order_fetches(monkeypatch, new_rows=[row])

    start = await async_client.post(
        "/operations/fbs-orders/sync",
        headers=headers,
        json={"seller_id": seller_id, "warehouse_id": warehouse_id},
    )
    assert start.status_code == 202, start.text
    body = await _wait_for_job(async_client, headers, start.json()["id"])
    assert body["status"] == "done", body

    listed = await async_client.get("/operations/fbs-orders", headers=headers)
    assert listed.status_code == 200
    orders = listed.json()
    assert len(orders) == 1
    order = orders[0]
    assert order["status"] == FBS_ORDER_STATUS_NEW
    assert order["wb_order_id"] == 800001
    created_at_wb = datetime.fromisoformat(order["created_at_wb"])
    deadline_at = datetime.fromisoformat(order["deadline_at"])
    assert deadline_at - created_at_wb == timedelta(hours=FBS_DEADLINE_HOURS)

    start2 = await async_client.post(
        "/operations/fbs-orders/sync",
        headers=headers,
        json={"seller_id": seller_id, "warehouse_id": warehouse_id},
    )
    assert start2.status_code == 202
    body2 = await _wait_for_job(async_client, headers, start2.json()["id"])
    assert body2["status"] == "done"

    listed2 = await async_client.get("/operations/fbs-orders", headers=headers)
    assert len(listed2.json()) == 1


# TC-NEW-FBS-INTAKE-002
@pytest.mark.asyncio
async def test_fbs_order_product_mapping_success_and_missing(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    await _create_binding(async_client, headers, seller_id, WB_WAREHOUSE_A, warehouse_id)

    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Mapped product",
            "sku_code": f"MAP-{suffix}",
            "seller_id": seller_id,
            "wb_barcode": "FBS-BARCODE-MAPPED",
            "wb_nm_id": 777001,
        },
    )
    assert product.status_code in (200, 201), product.text

    rows = [
        _wb_order_row(order_id=800101, barcode="FBS-BARCODE-MAPPED", nm_id=777001),
        _wb_order_row(order_id=800102, barcode="UNKNOWN-BARCODE", nm_id=999999),
    ]

    _patch_wb_order_fetches(monkeypatch, new_rows=rows)

    start = await async_client.post(
        "/operations/fbs-orders/sync",
        headers=headers,
        json={"seller_id": seller_id, "warehouse_id": warehouse_id},
    )
    assert start.status_code == 202
    body = await _wait_for_job(async_client, headers, start.json()["id"])
    assert body["status"] == "done"

    listed = await async_client.get("/operations/fbs-orders", headers=headers)
    by_wb = {o["wb_order_id"]: o for o in listed.json()}
    assert by_wb[800101]["product_id"] == product.json()["id"]
    assert by_wb[800101]["mapping_status"] == MAPPING_STATUS_MAPPED
    assert by_wb[800102]["product_id"] is None
    assert by_wb[800102]["mapping_status"] == MAPPING_STATUS_MISSING


@pytest.mark.asyncio
async def test_fbs_order_product_mapping_prefers_chrt_id_over_shared_nm_id(
    async_client: AsyncClient,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, _warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    token = headers["Authorization"].removeprefix("Bearer ")
    tenant_id = uuid.UUID(str(decode_access_token(token)["tenant_id"]))
    product_a = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Shared nm size A",
            "sku_code": f"CHRT-A-{suffix}",
            "seller_id": seller_id,
            "wb_barcode": f"CHRT-A-BAR-{suffix}",
            "wb_nm_id": 777777,
        },
    )
    assert product_a.status_code in (200, 201), product_a.text
    product_b = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Shared nm size B",
            "sku_code": f"CHRT-B-{suffix}",
            "seller_id": seller_id,
            "wb_barcode": f"CHRT-B-BAR-{suffix}",
            "wb_nm_id": 777777,
        },
    )
    assert product_b.status_code in (200, 201), product_b.text
    async with SessionLocal() as session:
        a = await session.get(Product, uuid.UUID(product_a.json()["id"]))
        b = await session.get(Product, uuid.UUID(product_b.json()["id"]))
        assert a is not None
        assert b is not None
        a.wb_chrt_id = 111111
        b.wb_chrt_id = 222222
        await session.commit()

    async with SessionLocal() as session:
        order, _created = await upsert_order_from_wb_row(
            session,
            tenant_id,
            uuid.UUID(seller_id),
            _wb_order_row(
                order_id=800103,
                barcode="WB-SIZE-B-ORDER-BARCODE",
                nm_id=777777,
                chrt_id=222222,
            ),
        )

    assert str(order.product_id) == product_b.json()["id"]
    assert order.mapping_status == MAPPING_STATUS_MAPPED


# TC-NEW-FBS-INTAKE-003
@pytest.mark.asyncio
async def test_fbs_order_reserve_and_no_stock(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    await _create_binding(async_client, headers, seller_id, WB_WAREHOUSE_A, warehouse_id)

    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Stock product",
            "sku_code": f"STK-{suffix}",
            "seller_id": seller_id,
            "wb_barcode": "FBS-STOCK-OK",
        },
    )
    assert product.status_code in (200, 201)
    product_id = uuid.UUID(product.json()["id"])
    warehouse_uuid = uuid.UUID(warehouse_id)

    async with SessionLocal() as session:
        prod = await session.get(Product, product_id)
        assert prod is not None
        sorting = await get_or_create_sorting_location(
            session, prod.tenant_id, warehouse_uuid
        )
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=prod.tenant_id,
            product_id=product_id,
            storage_location_id=sorting.id,
            quantity_delta=1,
            movement_type="inbound_intake",
        )
        await session.commit()

    rows = [
        _wb_order_row(order_id=800201, barcode="FBS-STOCK-OK"),
        _wb_order_row(order_id=800202, barcode="FBS-STOCK-OK"),
    ]

    _patch_wb_order_fetches(monkeypatch, new_rows=rows)

    start = await async_client.post(
        "/operations/fbs-orders/sync",
        headers=headers,
        json={"seller_id": seller_id, "warehouse_id": warehouse_id},
    )
    assert start.status_code == 202
    body = await _wait_for_job(async_client, headers, start.json()["id"])
    assert body["status"] == "done"

    listed = await async_client.get("/operations/fbs-orders", headers=headers)
    by_wb = {o["wb_order_id"]: o for o in listed.json()}
    assert by_wb[800201]["reserve_status"] == RESERVE_STATUS_RESERVED
    assert by_wb[800202]["reserve_status"] == RESERVE_STATUS_NO_STOCK

    async with SessionLocal() as session:
        count_stmt = select(func.count()).select_from(FbsOrderReservation)
        res = await session.execute(count_stmt)
        assert int(res.scalar_one()) == 1


@pytest.mark.asyncio
async def test_fbs_order_status_sync_supplier_confirm_moves_new_to_external_processing(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    await _create_binding(async_client, headers, seller_id, WB_WAREHOUSE_A, warehouse_id)

    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Confirm product",
            "sku_code": f"CNF-{suffix}",
            "seller_id": seller_id,
            "wb_barcode": "FBS-CONFIRM-001",
        },
    )
    assert product.status_code in (200, 201), product.text
    product_id = uuid.UUID(product.json()["id"])
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)

    async with SessionLocal() as session:
        prod = await session.get(Product, product_id)
        assert prod is not None
        tenant_id = prod.tenant_id
        order, _created = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_uuid,
            _wb_order_row(order_id=800302, barcode="FBS-CONFIRM-001"),
        )
        await session.commit()
        order_id = order.id
        assert order.status == FBS_ORDER_STATUS_NEW

    _patch_wb_order_fetches(
        monkeypatch,
        new_rows=[],
        status_rows=[
            {"id": 800302, "supplierStatus": "confirm", "wbStatus": "waiting"}
        ],
    )

    async with SessionLocal() as session:
        import httpx

        async with httpx.AsyncClient() as http_client:
            await sync_seller_orders(
                session,
                tenant_id,
                seller_uuid,
                http_client,
                warehouse_id=warehouse_uuid,
            )

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.wb_status == "waiting"
        assert order.supplier_status == "confirm"
        assert order.status == FBS_ORDER_STATUS_EXTERNAL_PROCESSING

    new_page = await async_client.get(
        "/operations/fbs-orders/worklist?status_group=new",
        headers=headers,
    )
    assert new_page.status_code == 200, new_page.text
    assert all(item["wb_order_id"] != 800302 for item in new_page.json()["items"])

    active_page = await async_client.get(
        "/operations/fbs-orders/worklist?status_group=active",
        headers=headers,
    )
    assert active_page.status_code == 200, active_page.text
    by_wb = {item["wb_order_id"]: item for item in active_page.json()["items"]}
    assert 800302 not in by_wb


# TC-NEW-FBS-INTAKE-004
@pytest.mark.asyncio
async def test_fbs_order_status_sync_releases_reserve_on_cancel(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    await _create_binding(async_client, headers, seller_id, WB_WAREHOUSE_A, warehouse_id)

    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Cancel product",
            "sku_code": f"CNL-{suffix}",
            "seller_id": seller_id,
            "wb_barcode": "FBS-CANCEL-001",
        },
    )
    assert product.status_code in (200, 201)
    product_id = uuid.UUID(product.json()["id"])
    warehouse_uuid = uuid.UUID(warehouse_id)
    seller_uuid = uuid.UUID(seller_id)

    async with SessionLocal() as session:
        prod = await session.get(Product, product_id)
        assert prod is not None
        tenant_id = prod.tenant_id
        sorting = await get_or_create_sorting_location(
            session, tenant_id, warehouse_uuid
        )
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=sorting.id,
            quantity_delta=2,
            movement_type="inbound_intake",
        )
        order, _created = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_uuid,
            _wb_order_row(order_id=800301, barcode="FBS-CANCEL-001"),
        )
        await session.commit()
        order_id = order.id
        saved_tenant_id = tenant_id

    status_calls = {"n": 0}

    async def fake_status(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[dict[str, Any]]:
        status_calls["n"] += 1
        return [{"id": 800301, "wbStatus": "canceled"}]

    _patch_wb_order_fetches(monkeypatch, new_rows=[], status_rows=[])
    monkeypatch.setattr(
        "app.services.wb_marketplace_orders_service.fetch_marketplace_orders_status",
        fake_status,
    )

    async with SessionLocal() as session:
        import httpx

        async with httpx.AsyncClient() as http_client:
            result = await sync_seller_orders(
                session,
                saved_tenant_id,
                seller_uuid,
                http_client,
                warehouse_id=warehouse_uuid,
            )
        assert result["statuses_updated"] == 1

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.wb_status == "canceled"
        assert order.status == "cancelled"
        assert order.reserve_status == RESERVE_STATUS_RELEASED
        res_stmt = select(func.count()).select_from(FbsOrderReservation).where(
            FbsOrderReservation.fbs_order_id == order_id
        )
        res = await session.execute(res_stmt)
        assert int(res.scalar_one()) == 0

    assert status_calls["n"] >= 1


# TC-NEW-FBS-INTAKE-004 N2 — WB client error surfaces as failed job
@pytest.mark.asyncio
async def test_fbs_sync_job_fails_on_wb_client_error(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)

    _patch_wb_order_fetches(
        monkeypatch,
        new_raises=WildberriesClientError("upstream_error", status_code=502),
    )

    start = await async_client.post(
        "/operations/fbs-orders/sync",
        headers=headers,
        json={"seller_id": seller_id, "warehouse_id": warehouse_id},
    )
    assert start.status_code == 202
    body = await _wait_for_job(async_client, headers, start.json()["id"])
    assert body["status"] == "failed"
    assert body["error_message"] == "wb_upstream_error_502"


@pytest.mark.asyncio
async def test_fbs_sync_keeps_new_orders_when_page_fetch_fails(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, _warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    seller_uuid = uuid.UUID(seller_id)
    _patch_wb_order_fetches(
        monkeypatch,
        new_rows=[_wb_order_row(order_id=800501)],
        page_raises=WildberriesClientError("upstream_error", status_code=400),
    )

    async with SessionLocal() as session:
        from app.models.seller import Seller

        seller = await session.get(Seller, seller_uuid)
        assert seller is not None
        tenant_id = seller.tenant_id
        import httpx

        async with httpx.AsyncClient() as http_client:
            result = await sync_seller_orders(session, tenant_id, seller_uuid, http_client)

    assert result["orders_created"] == 1
    assert result["orders_page_error"] == "wb_upstream_error_400"
    async with SessionLocal() as session:
        order = (
            await session.execute(
                select(FbsOrder).where(FbsOrder.seller_id == seller_uuid)
            )
        ).scalar_one()
    assert order.wb_order_id == 800501


@pytest.mark.asyncio
async def test_fbs_sync_keeps_new_orders_when_status_fetch_fails(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, _warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    seller_uuid = uuid.UUID(seller_id)
    _patch_wb_order_fetches(
        monkeypatch,
        new_rows=[_wb_order_row(order_id=800502)],
        status_raises=WildberriesClientError("upstream_error", status_code=400),
    )

    async with SessionLocal() as session:
        from app.models.seller import Seller

        seller = await session.get(Seller, seller_uuid)
        assert seller is not None
        tenant_id = seller.tenant_id
        import httpx

        async with httpx.AsyncClient() as http_client:
            result = await sync_seller_orders(session, tenant_id, seller_uuid, http_client)

    assert result["orders_created"] == 1
    assert result["status_sync_error"] == "wb_upstream_error_400"
    async with SessionLocal() as session:
        order = (
            await session.execute(
                select(FbsOrder).where(FbsOrder.seller_id == seller_uuid)
            )
        ).scalar_one()
    assert order.wb_order_id == 800502


# TC-NEW-FBS-INTAKE-004 N3 — missing marketplace token
@pytest.mark.asyncio
async def test_fbs_sync_missing_marketplace_token(
    async_client: AsyncClient,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller = await async_client.post(
        "/sellers", headers=headers, json={"name": f"No token {suffix}"}
    )
    assert seller.status_code in (200, 201), seller.text
    seller_id = seller.json()["id"]
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WH", "code": f"wh-nt-{suffix[-8:]}"},
    )
    assert warehouse.status_code in (200, 201), warehouse.text

    import httpx

    from app.models.seller import Seller

    async with SessionLocal() as session:
        seller_uuid = uuid.UUID(seller_id)
        seller_obj = await session.get(Seller, seller_uuid)
        assert seller_obj is not None
        tenant_id = seller_obj.tenant_id
        async with httpx.AsyncClient() as http_client:
            with pytest.raises(WbMarketplaceOrdersError) as exc_info:
                await sync_seller_orders(
                    session,
                    tenant_id,
                    seller_uuid,
                    http_client,
                    warehouse_id=uuid.UUID(warehouse.json()["id"]),
                )
    assert exc_info.value.code == "missing_marketplace_token"


@pytest.mark.asyncio
async def test_fbs_cancelled_order_not_re_reserved_on_upsert(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    await _create_binding(async_client, headers, seller_id, WB_WAREHOUSE_A, warehouse_id)

    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Terminal product",
            "sku_code": f"TRM-{suffix}",
            "seller_id": seller_id,
            "wb_barcode": "FBS-TERMINAL-001",
        },
    )
    assert product.status_code in (200, 201)
    product_id = uuid.UUID(product.json()["id"])
    warehouse_uuid = uuid.UUID(warehouse_id)
    seller_uuid = uuid.UUID(seller_id)

    async with SessionLocal() as session:
        prod = await session.get(Product, product_id)
        assert prod is not None
        tenant_id = prod.tenant_id
        sorting = await get_or_create_sorting_location(
            session, tenant_id, warehouse_uuid
        )
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=sorting.id,
            quantity_delta=1,
            movement_type="inbound_intake",
        )
        order, _created = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_uuid,
            _wb_order_row(order_id=800401, barcode="FBS-TERMINAL-001"),
        )
        await session.commit()
        order_id = order.id
        assert order.reserve_status == RESERVE_STATUS_RESERVED

    _patch_wb_order_fetches(
        monkeypatch,
        new_rows=[],
        status_rows=[{"id": 800401, "supplierStatus": "canceled_by_client"}],
    )

    async with SessionLocal() as session:
        import httpx

        async with httpx.AsyncClient() as http_client:
            await sync_seller_orders(
                session,
                tenant_id,
                seller_uuid,
                http_client,
                warehouse_id=warehouse_uuid,
            )

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.status == "cancelled"
        res_stmt = select(func.count()).select_from(FbsOrderReservation).where(
            FbsOrderReservation.fbs_order_id == order_id
        )
        res = await session.execute(res_stmt)
        assert int(res.scalar_one()) == 0

        await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_uuid,
            _wb_order_row(order_id=800401, barcode="FBS-TERMINAL-001"),
        )
        await session.commit()

        order2 = await session.get(FbsOrder, order_id)
        assert order2 is not None
        assert order2.status == "cancelled"
        assert order2.reserve_status == RESERVE_STATUS_RELEASED
        res2 = await session.execute(res_stmt)
        assert int(res2.scalar_one()) == 0


@pytest.mark.asyncio
async def test_fbs_sync_ignores_body_warehouse_id(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manual /sync body warehouse_id must not bypass WB warehouse binding."""
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_a = await _setup_seller_with_token(async_client, headers, suffix)
    warehouse_b = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WH B", "code": f"wh-b-{suffix[-8:]}"},
    )
    assert warehouse_b.status_code in (200, 201), warehouse_b.text
    warehouse_b_id = warehouse_b.json()["id"]
    await _create_binding(async_client, headers, seller_id, WB_WAREHOUSE_A, warehouse_a)

    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Bind product",
            "sku_code": f"BIND-{suffix}",
            "seller_id": seller_id,
            "wb_barcode": "FBS-BIND-001",
        },
    )
    assert product.status_code in (200, 201), product.text

    _patch_wb_order_fetches(
        monkeypatch,
        new_rows=[_wb_order_row(order_id=800501, barcode="FBS-BIND-001")],
    )

    start = await async_client.post(
        "/operations/fbs-orders/sync",
        headers=headers,
        json={"seller_id": seller_id, "warehouse_id": warehouse_b_id},
    )
    assert start.status_code == 202, start.text
    body = await _wait_for_job(async_client, headers, start.json()["id"])
    assert body["status"] == "done", body

    listed = await async_client.get("/operations/fbs-orders", headers=headers)
    order = listed.json()[0]
    assert order["warehouse_id"] == warehouse_a
    assert order["wb_warehouse_id"] == WB_WAREHOUSE_A
    assert order["wb_office_id"] == 42


# TC-NEW-FBS-STOCK-003 — two WB warehouses map to two WMS warehouses
@pytest.mark.asyncio
async def test_fbs_orders_bind_to_correct_wms_warehouse(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_a = await _setup_seller_with_token(async_client, headers, suffix)
    warehouse_b = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WH B", "code": f"wh-b2-{suffix[-8:]}"},
    )
    assert warehouse_b.status_code in (200, 201), warehouse_b.text
    warehouse_b_id = warehouse_b.json()["id"]
    await _create_binding(async_client, headers, seller_id, WB_WAREHOUSE_A, warehouse_a)
    await _create_binding(async_client, headers, seller_id, WB_WAREHOUSE_B, warehouse_b_id)

    rows = [
        _wb_order_row(order_id=800601, warehouse_id=WB_WAREHOUSE_A),
        _wb_order_row(order_id=800602, warehouse_id=WB_WAREHOUSE_B, office_id=99),
    ]
    _patch_wb_order_fetches(monkeypatch, new_rows=rows)

    start = await async_client.post(
        "/operations/fbs-orders/sync",
        headers=headers,
        json={"seller_id": seller_id},
    )
    assert start.status_code == 202
    body = await _wait_for_job(async_client, headers, start.json()["id"])
    assert body["status"] == "done"

    listed = await async_client.get("/operations/fbs-orders", headers=headers)
    by_wb = {o["wb_order_id"]: o for o in listed.json()}
    assert by_wb[800601]["warehouse_id"] == warehouse_a
    assert by_wb[800601]["wb_warehouse_id"] == WB_WAREHOUSE_A
    assert by_wb[800601]["wb_office_id"] == 42
    assert by_wb[800602]["warehouse_id"] == warehouse_b_id
    assert by_wb[800602]["wb_warehouse_id"] == WB_WAREHOUSE_B
    assert by_wb[800602]["wb_office_id"] == 99


# TC-NEW-FBS-STOCK-004 — unknown WB warehouse creates a technical binding
@pytest.mark.asyncio
async def test_fbs_order_unknown_wb_warehouse_auto_creates_binding(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    await _create_binding(async_client, headers, seller_id, WB_WAREHOUSE_A, warehouse_id)

    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Unmapped product",
            "sku_code": f"UNM-{suffix}",
            "seller_id": seller_id,
            "wb_barcode": "FBS-UNMAPPED-001",
        },
    )
    assert product.status_code in (200, 201), product.text

    _patch_wb_order_fetches(
        monkeypatch,
        new_rows=[
            _wb_order_row(
                order_id=800701,
                barcode="FBS-UNMAPPED-001",
                warehouse_id=UNKNOWN_WB_WAREHOUSE,
            )
        ],
    )

    start = await async_client.post(
        "/operations/fbs-orders/sync",
        headers=headers,
        json={"seller_id": seller_id},
    )
    assert start.status_code == 202
    body = await _wait_for_job(async_client, headers, start.json()["id"])
    assert body["status"] == "done"

    listed = await async_client.get("/operations/fbs-orders", headers=headers)
    order = listed.json()[0]
    assert order["warehouse_id"] is not None
    assert order["wb_warehouse_id"] == UNKNOWN_WB_WAREHOUSE
    assert order["mapping_status"] == MAPPING_STATUS_MAPPED
    assert order["reserve_status"] == RESERVE_STATUS_NO_STOCK

    async with SessionLocal() as session:
        binding_stmt = select(FbsWarehouseBinding).where(
            FbsWarehouseBinding.seller_id == uuid.UUID(seller_id),
            FbsWarehouseBinding.wb_warehouse_id == UNKNOWN_WB_WAREHOUSE,
        )
        binding = await session.scalar(binding_stmt)
        assert binding is not None
        assert str(binding.wms_warehouse_id) == order["warehouse_id"]
        assert binding.is_active is True
        # Привязка создаётся сразу включённой: от выгрузки нулей защищает
        # признак на товаре. Выключенный рубильник был второй скрытой заслонкой.
        assert binding.stock_sync_enabled is True

        warehouse = await session.get(Warehouse, uuid.UUID(order["warehouse_id"]))
        assert warehouse is not None
        assert warehouse.code.startswith("fbs-wb-")

        count_stmt = select(func.count()).select_from(FbsOrderReservation)
        res = await session.execute(count_stmt)
        assert int(res.scalar_one()) == 0


# TC-NEW-FBS-STOCK-004 — zero local WMS stock does not block FBS selection
@pytest.mark.asyncio
async def test_fbs_order_without_local_stock_is_selectable(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    await _create_binding(async_client, headers, seller_id, WB_WAREHOUSE_A, warehouse_id)
    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Selectable without local stock",
            "sku_code": f"SEL-{suffix}",
            "seller_id": seller_id,
            "wb_barcode": "FBS-BARCODE-001",
        },
    )
    assert product.status_code in (200, 201), product.text

    _patch_wb_order_fetches(
        monkeypatch,
        new_rows=[
            _wb_order_row(
                order_id=800801,
                created_at=datetime.now(UTC).isoformat(),
                warehouse_id=UNKNOWN_WB_WAREHOUSE,
            ),
        ],
    )
    start = await async_client.post(
        "/operations/fbs-orders/sync",
        headers=headers,
        json={"seller_id": seller_id},
    )
    assert start.status_code == 202
    await _wait_for_job(async_client, headers, start.json()["id"])

    listed = await async_client.get("/operations/fbs-orders", headers=headers)
    order_id = listed.json()[0]["id"]
    assert listed.json()[0]["reserve_status"] == RESERVE_STATUS_NO_STOCK

    worklist = await async_client.get(
        "/operations/fbs-orders/worklist?status_group=new",
        headers=headers,
    )
    assert worklist.status_code == 200, worklist.text
    worklist_order = worklist.json()["items"][0]
    assert worklist_order["id"] == order_id
    assert worklist_order["inventory"]["available_unpacked"] == 0
    assert worklist_order["selection_blockers"] == []

    preflight = await async_client.post(
        "/operations/fbs-supplies/preflight",
        headers=headers,
        json={"order_ids": [order_id], "planned_delivery_type": "warehouse_sc"},
    )
    assert preflight.status_code == 200, preflight.text
    assert preflight.json()["compatible"] is True


# Binding later → re-sync assigns warehouse and reserves
@pytest.mark.asyncio
async def test_fbs_binding_later_assigns_warehouse_and_reserves(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)

    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Late bind product",
            "sku_code": f"LATE-{suffix}",
            "seller_id": seller_id,
            "wb_barcode": "FBS-LATE-001",
        },
    )
    assert product.status_code in (200, 201), product.text
    product_id = uuid.UUID(product.json()["id"])
    warehouse_uuid = uuid.UUID(warehouse_id)

    async with SessionLocal() as session:
        prod = await session.get(Product, product_id)
        assert prod is not None
        sorting = await get_or_create_sorting_location(
            session, prod.tenant_id, warehouse_uuid
        )
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=prod.tenant_id,
            product_id=product_id,
            storage_location_id=sorting.id,
            quantity_delta=1,
            movement_type="inbound_intake",
        )
        await session.commit()

    _patch_wb_order_fetches(
        monkeypatch,
        new_rows=[_wb_order_row(order_id=800901, barcode="FBS-LATE-001")],
    )
    start = await async_client.post(
        "/operations/fbs-orders/sync",
        headers=headers,
        json={"seller_id": seller_id},
    )
    assert start.status_code == 202
    await _wait_for_job(async_client, headers, start.json()["id"])

    listed = await async_client.get("/operations/fbs-orders", headers=headers)
    assert listed.json()[0]["warehouse_id"] is not None
    assert listed.json()[0]["warehouse_id"] != warehouse_id
    assert listed.json()[0]["reserve_status"] == RESERVE_STATUS_NO_STOCK

    await _create_binding(async_client, headers, seller_id, WB_WAREHOUSE_A, warehouse_id)

    start2 = await async_client.post(
        "/operations/fbs-orders/sync",
        headers=headers,
        json={"seller_id": seller_id},
    )
    assert start2.status_code == 202
    await _wait_for_job(async_client, headers, start2.json()["id"])

    listed2 = await async_client.get("/operations/fbs-orders", headers=headers)
    order = listed2.json()[0]
    assert order["warehouse_id"] == warehouse_id
    assert order["reserve_status"] == RESERVE_STATUS_RESERVED


# TC-NEW-FBS-STOCK-008 — defect releases reservation like cancel/sold
@pytest.mark.asyncio
async def test_fbs_order_status_sync_releases_reserve_on_defect(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    await _create_binding(async_client, headers, seller_id, WB_WAREHOUSE_A, warehouse_id)

    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Defect product",
            "sku_code": f"DEF-{suffix}",
            "seller_id": seller_id,
            "wb_barcode": "FBS-DEFECT-001",
        },
    )
    assert product.status_code in (200, 201)
    product_id = uuid.UUID(product.json()["id"])
    warehouse_uuid = uuid.UUID(warehouse_id)
    seller_uuid = uuid.UUID(seller_id)

    async with SessionLocal() as session:
        prod = await session.get(Product, product_id)
        assert prod is not None
        tenant_id = prod.tenant_id
        sorting = await get_or_create_sorting_location(
            session, tenant_id, warehouse_uuid
        )
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=sorting.id,
            quantity_delta=1,
            movement_type="inbound_intake",
        )
        order, _created = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_uuid,
            _wb_order_row(order_id=801001, barcode="FBS-DEFECT-001"),
        )
        await session.commit()
        order_id = order.id
        assert order.reserve_status == RESERVE_STATUS_RESERVED

    _patch_wb_order_fetches(
        monkeypatch,
        new_rows=[],
        status_rows=[{"id": 801001, "wbStatus": "defect"}],
    )

    async with SessionLocal() as session:
        import httpx

        async with httpx.AsyncClient() as http_client:
            await sync_seller_orders(session, tenant_id, seller_uuid, http_client)

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.status == "defect"
        assert order.reserve_status == RESERVE_STATUS_RELEASED
        res_stmt = select(func.count()).select_from(FbsOrderReservation).where(
            FbsOrderReservation.fbs_order_id == order_id
        )
        res = await session.execute(res_stmt)
        assert int(res.scalar_one()) == 0


# Reservation on other warehouse → binding change does not silently move
@pytest.mark.asyncio
async def test_fbs_order_reservation_conflict_keeps_warehouse(
    async_client: AsyncClient,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_a = await _setup_seller_with_token(async_client, headers, suffix)
    warehouse_b = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WH conflict", "code": f"wh-c-{suffix[-8:]}"},
    )
    assert warehouse_b.status_code in (200, 201), warehouse_b.text
    warehouse_b_id = warehouse_b.json()["id"]

    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Conflict product",
            "sku_code": f"CNF-{suffix}",
            "seller_id": seller_id,
            "wb_barcode": "FBS-CONFLICT-001",
        },
    )
    assert product.status_code in (200, 201), product.text
    product_id = uuid.UUID(product.json()["id"])
    seller_uuid = uuid.UUID(seller_id)
    warehouse_a_uuid = uuid.UUID(warehouse_a)
    warehouse_b_uuid = uuid.UUID(warehouse_b_id)

    async with SessionLocal() as session:
        prod = await session.get(Product, product_id)
        assert prod is not None
        tenant_id = prod.tenant_id
        sorting = await get_or_create_sorting_location(
            session, tenant_id, warehouse_a_uuid
        )
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=sorting.id,
            quantity_delta=1,
            movement_type="inbound_intake",
        )
        await _seed_binding(
            session, tenant_id, seller_uuid, WB_WAREHOUSE_A, warehouse_a_uuid
        )
        await _seed_binding(
            session, tenant_id, seller_uuid, WB_WAREHOUSE_B, warehouse_b_uuid
        )
        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_uuid,
            _wb_order_row(
                order_id=801101,
                barcode="FBS-CONFLICT-001",
                warehouse_id=WB_WAREHOUSE_A,
            ),
        )
        assert order.warehouse_id == warehouse_a_uuid
        assert order.reserve_status == RESERVE_STATUS_RESERVED
        await session.commit()
        order_id = order.id

        order2 = await session.get(FbsOrder, order_id)
        assert order2 is not None
        from app.services.wb_marketplace_orders_service import (
            _assign_wms_warehouse_from_binding,
        )

        await _assign_wms_warehouse_from_binding(
            session, tenant_id, seller_uuid, order2, WB_WAREHOUSE_B
        )
        await session.commit()
        await session.refresh(order2)

        assert order2.warehouse_id == warehouse_a_uuid
        assert order2.reserve_status == RESERVE_STATUS_WAREHOUSE_REMAP_CONFLICT
        res_stmt = select(FbsOrderReservation).where(
            FbsOrderReservation.fbs_order_id == order_id
        )
        res = await session.execute(res_stmt)
        reservation = res.scalar_one_or_none()
        assert reservation is not None
        assert reservation.warehouse_id == warehouse_a_uuid


# TC-NEW-FBS-STOCK-012 — WB warehouse remap with active reserve is observable
@pytest.mark.asyncio
async def test_fbs_order_wb_warehouse_remap_conflict_on_resync(
    async_client: AsyncClient,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_a = await _setup_seller_with_token(async_client, headers, suffix)
    warehouse_b = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WH remap", "code": f"wh-r-{suffix[-8:]}"},
    )
    assert warehouse_b.status_code in (200, 201), warehouse_b.text
    warehouse_b_id = warehouse_b.json()["id"]

    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Remap product",
            "sku_code": f"RMP-{suffix}",
            "seller_id": seller_id,
            "wb_barcode": "FBS-REMAP-001",
        },
    )
    assert product.status_code in (200, 201), product.text
    product_id = uuid.UUID(product.json()["id"])
    seller_uuid = uuid.UUID(seller_id)
    warehouse_a_uuid = uuid.UUID(warehouse_a)
    warehouse_b_uuid = uuid.UUID(warehouse_b_id)

    async with SessionLocal() as session:
        prod = await session.get(Product, product_id)
        assert prod is not None
        tenant_id = prod.tenant_id
        sorting = await get_or_create_sorting_location(
            session, tenant_id, warehouse_a_uuid
        )
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=sorting.id,
            quantity_delta=1,
            movement_type="inbound_intake",
        )
        await _seed_binding(
            session, tenant_id, seller_uuid, WB_WAREHOUSE_A, warehouse_a_uuid
        )
        await _seed_binding(
            session, tenant_id, seller_uuid, WB_WAREHOUSE_B, warehouse_b_uuid
        )
        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_uuid,
            _wb_order_row(
                order_id=801201,
                barcode="FBS-REMAP-001",
                warehouse_id=WB_WAREHOUSE_A,
            ),
        )
        assert order.reserve_status == RESERVE_STATUS_RESERVED
        await session.commit()

        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_uuid,
            _wb_order_row(
                order_id=801201,
                barcode="FBS-REMAP-001",
                warehouse_id=WB_WAREHOUSE_B,
            ),
        )
        await session.commit()
        await session.refresh(order)

        assert order.wb_warehouse_id == WB_WAREHOUSE_A
        assert order.warehouse_id == warehouse_a_uuid
        assert order.reserve_status == RESERVE_STATUS_WAREHOUSE_REMAP_CONFLICT
        res_stmt = select(FbsOrderReservation).where(
            FbsOrderReservation.fbs_order_id == order.id
        )
        res = await session.execute(res_stmt)
        reservation = res.scalar_one_or_none()
        assert reservation is not None
        assert reservation.warehouse_id == warehouse_a_uuid
