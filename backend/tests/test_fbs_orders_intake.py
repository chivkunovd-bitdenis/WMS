from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_NEW,
    MAPPING_STATUS_MAPPED,
    MAPPING_STATUS_MISSING,
    RESERVE_STATUS_NO_STOCK,
    RESERVE_STATUS_RELEASED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
    FbsOrderReservation,
)
from app.models.product import Product
from app.services import inventory_service
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.wb_marketplace_orders_service import (
    FBS_DEADLINE_HOURS,
    WbMarketplaceOrdersError,
    sync_seller_orders,
    upsert_order_from_wb_row,
)
from app.services.wildberries_client import WildberriesClientError


def _wb_order_row(
    *,
    order_id: int = 700001,
    barcode: str = "FBS-BARCODE-001",
    nm_id: int = 900001,
    created_at: str = "2026-07-01T12:00:00+03:00",
) -> dict[str, Any]:
    return {
        "id": order_id,
        "rid": f"rid-{order_id}",
        "createdAt": created_at,
        "nmId": nm_id,
        "chrtId": 555,
        "article": "ART-001",
        "skus": [barcode],
        "price": 199900,
        "cargoType": 1,
        "officeId": 42,
        "isLegal": False,
    }


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
        json={"supplies_api_token": "wb-marketplace-token"},
    )
    assert tok.status_code == 200, tok.text
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WH", "code": f"wh-{suffix[-8:]}"},
    )
    assert warehouse.status_code in (200, 201), warehouse.text
    return seller_id, warehouse.json()["id"]


def _patch_wb_order_fetches(
    monkeypatch: pytest.MonkeyPatch,
    *,
    new_rows: list[dict[str, Any]] | None = None,
    page_rows: list[dict[str, Any]] | None = None,
    status_rows: list[dict[str, Any]] | None = None,
    new_raises: BaseException | None = None,
    page_raises: BaseException | None = None,
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


# TC-NEW-FBS-INTAKE-001
@pytest.mark.asyncio
async def test_fbs_order_upsert_idempotent_and_deadline(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
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


# TC-NEW-FBS-INTAKE-003
@pytest.mark.asyncio
async def test_fbs_order_reserve_and_no_stock(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)

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


# TC-NEW-FBS-INTAKE-004
@pytest.mark.asyncio
async def test_fbs_order_status_sync_releases_reserve_on_cancel(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)

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
            warehouse_uuid,
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
            warehouse_uuid,
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
            warehouse_uuid,
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
async def test_fbs_sync_rejects_warehouse_from_other_tenant(
    async_client: AsyncClient,
) -> None:
    headers_a, suffix_a = await _register_ff_admin(async_client)
    seller_id, _warehouse_a = await _setup_seller_with_token(
        async_client, headers_a, suffix_a
    )

    headers_b, suffix_b = await _register_ff_admin(async_client)
    warehouse_b = await async_client.post(
        "/warehouses",
        headers=headers_b,
        json={"name": "Other WH", "code": f"wh-b-{suffix_b[-8:]}"},
    )
    assert warehouse_b.status_code in (200, 201), warehouse_b.text
    other_wh_id = warehouse_b.json()["id"]

    sync = await async_client.post(
        "/operations/fbs-orders/sync",
        headers=headers_a,
        json={"seller_id": seller_id, "warehouse_id": other_wh_id},
    )
    assert sync.status_code == 404
    assert sync.json()["detail"] == "warehouse_not_found"
