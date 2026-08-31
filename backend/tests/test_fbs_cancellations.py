from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_DEFECT,
    FBS_ORDER_STATUS_DONE,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_NEW,
    FBS_ORDER_STATUS_SORTED,
    RESERVE_STATUS_RELEASED,
    FbsOrder,
    FbsOrderReservation,
)
from app.models.product import Product
from app.services import inventory_service
from app.services.fbs_cancellation_service import penalty_band_for_order
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.wb_marketplace_orders_service import (
    sync_order_statuses,
    upsert_order_from_wb_row,
)
from app.services.wildberries_client import WildberriesClientError
from tests.fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID, seed_fbs_warehouse_binding
from tests.inventory_actor_helpers import resolve_test_actor_user_id


def _assert_fbs_error(
    response: httpx.Response,
    *,
    status_code: int,
    code: str,
    message: str,
    retryable: bool = False,
    context: dict[str, object] | None = None,
) -> None:
    assert response.status_code == status_code, response.text
    assert response.json() == {
        "detail": {
            "code": code,
            "message": message,
            "context": context or {},
            "retryable": retryable,
        }
    }


def _wb_order_row(
    *,
    order_id: int = 700001,
    barcode: str = "FBS-BARCODE-001",
    nm_id: int = 900001,
    created_at: str = "2026-07-01T12:00:00+03:00",
    wb_warehouse_id: int = DEFAULT_WB_WAREHOUSE_ID,
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
        "warehouseId": wb_warehouse_id,
    }


async def _register_ff_admin(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS cancel {suffix}",
            "slug": f"fbs-cancel-{suffix}",
            "admin_email": f"fbs-cancel-{suffix}@example.com",
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


async def _seed_reserved_order(
    *,
    seller_id: str,
    warehouse_id: str,
    wb_order_id: int = 810001,
    barcode: str = "FBS-CANCEL-RESERVE",
    order_status: str = FBS_ORDER_STATUS_NEW,
    created_at: str | None = None,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)

    async with SessionLocal() as session:
        from app.models.seller import Seller

        seller = await session.get(Seller, seller_uuid)
        assert seller is not None
        tenant_id = seller.tenant_id

        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_uuid,
            name="Cancel product",
            sku_code=f"CNL-{wb_order_id}",
            wb_barcode=barcode,
            fbs_stock_sync_enabled=True,
            fbs_percent=100,
        )
        session.add(product)
        await session.flush()

        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_uuid)
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product.id,
            storage_location_id=sorting.id,
            quantity_delta=2,
            movement_type="inbound_intake",
            actor_user_id=await resolve_test_actor_user_id(session, tenant_id),
        )

        row = _wb_order_row(
            order_id=wb_order_id,
            barcode=barcode,
            created_at=created_at or datetime.now(tz=UTC).isoformat(),
        )
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_uuid,
            wms_warehouse_id=warehouse_uuid,
        )
        order, _created = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_uuid,
            row,
        )
        order.status = order_status
        await session.commit()
        return tenant_id, order.id, product.id


# TC-NEW-FBS-CANCEL-001
@pytest.mark.asyncio
async def test_cancel_new_order_releases_reserve(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    _tenant_id, order_id, _product_id = await _seed_reserved_order(
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_order_id=810101,
    )

    cancel_calls: list[int] = []

    async def fake_cancel(
        client: object,
        *,
        api_token: str,
        order_id: int,
        marketplace_api_base: str | None = None,
    ) -> None:
        cancel_calls.append(order_id)

    monkeypatch.setattr(
        "app.services.fbs_cancellation_service.cancel_marketplace_order",
        fake_cancel,
    )

    resp = await async_client.patch(
        f"/operations/fbs-orders/{order_id}/cancel",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == FBS_ORDER_STATUS_CANCELLED
    assert body["reserve_status"] == RESERVE_STATUS_RELEASED
    assert cancel_calls == [810101]

    async with SessionLocal() as session:
        res_stmt = select(func.count()).select_from(FbsOrderReservation).where(
            FbsOrderReservation.fbs_order_id == order_id
        )
        res = await session.execute(res_stmt)
        assert int(res.scalar_one()) == 0


@pytest.mark.asyncio
async def test_cancel_in_delivery_returns_409(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    _tenant_id, order_id, _product_id = await _seed_reserved_order(
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_order_id=810102,
        order_status=FBS_ORDER_STATUS_IN_DELIVERY,
    )

    async def fake_cancel(
        client: object,
        *,
        api_token: str,
        order_id: int,
        marketplace_api_base: str | None = None,
    ) -> None:
        raise AssertionError("WB cancel must not be called")

    monkeypatch.setattr(
        "app.services.fbs_cancellation_service.cancel_marketplace_order",
        fake_cancel,
    )

    resp = await async_client.patch(
        f"/operations/fbs-orders/{order_id}/cancel",
        headers=headers,
    )
    _assert_fbs_error(
        resp,
        status_code=409,
        code="order_not_cancellable",
        message="Заказ нельзя отменить.",
    )


def test_penalty_band_lt13() -> None:
    created = datetime.now(tz=UTC) - timedelta(hours=2)
    assert penalty_band_for_order(created) == "lt13"


# TC-NEW-FBS-CANCEL-002
@pytest.mark.asyncio
async def test_sync_statuses_sold_and_canceled(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    _tenant_id, order_sold_id, _ = await _seed_reserved_order(
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_order_id=810201,
        barcode="FBS-SYNC-SOLD",
    )
    _tenant_id2, order_cancel_id, _ = await _seed_reserved_order(
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_order_id=810202,
        barcode="FBS-SYNC-CANCEL",
    )
    _tenant_id3, order_sorted_id, _ = await _seed_reserved_order(
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_order_id=810203,
        barcode="FBS-SYNC-SORTED",
    )

    async def fake_status(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for oid in order_ids:
            if oid == 810201:
                rows.append({"id": oid, "wbStatus": "sold"})
            elif oid == 810202:
                rows.append({"id": oid, "wbStatus": "canceled"})
            elif oid == 810203:
                rows.append({"id": oid, "wbStatus": "sorted"})
        return rows

    monkeypatch.setattr(
        "app.services.wb_marketplace_orders_service.fetch_marketplace_orders_status",
        fake_status,
    )

    resp = await async_client.post(
        "/operations/fbs-orders/sync-statuses",
        headers=headers,
        json={"seller_id": seller_id},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["statuses_updated"] >= 3

    async with SessionLocal() as session:
        sold = await session.get(FbsOrder, order_sold_id)
        canceled = await session.get(FbsOrder, order_cancel_id)
        sorted_order = await session.get(FbsOrder, order_sorted_id)
        assert sold is not None and canceled is not None and sorted_order is not None
        assert sold.status == FBS_ORDER_STATUS_DONE
        assert sold.wb_status == "sold"
        assert sold.reserve_status == RESERVE_STATUS_RELEASED
        sold_rsv = await session.execute(
            select(FbsOrderReservation).where(FbsOrderReservation.fbs_order_id == order_sold_id)
        )
        assert sold_rsv.scalar_one_or_none() is None
        assert canceled.status == FBS_ORDER_STATUS_CANCELLED
        assert canceled.wb_status == "canceled"
        assert canceled.reserve_status == RESERVE_STATUS_RELEASED
        assert sorted_order.status == FBS_ORDER_STATUS_SORTED
        assert sorted_order.wb_status == "sorted"


# TC-NEW-FBS-CANCEL-003
@pytest.mark.asyncio
async def test_cancel_idempotent_second_call(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    _tenant_id, order_id, _product_id = await _seed_reserved_order(
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_order_id=810301,
    )

    calls = {"n": 0}

    async def fake_cancel(
        client: object,
        *,
        api_token: str,
        order_id: int,
        marketplace_api_base: str | None = None,
    ) -> None:
        calls["n"] += 1

    monkeypatch.setattr(
        "app.services.fbs_cancellation_service.cancel_marketplace_order",
        fake_cancel,
    )

    first = await async_client.patch(
        f"/operations/fbs-orders/{order_id}/cancel",
        headers=headers,
    )
    assert first.status_code == 200
    second = await async_client.patch(
        f"/operations/fbs-orders/{order_id}/cancel",
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["status"] == FBS_ORDER_STATUS_CANCELLED
    assert calls["n"] == 1


# TC-NEW-FBS-CANCEL-004
@pytest.mark.asyncio
async def test_sync_defect_sets_status_defect(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    tenant_id, order_id, _ = await _seed_reserved_order(
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_order_id=810401,
        barcode="FBS-SYNC-DEFECT",
    )
    seller_uuid = uuid.UUID(seller_id)

    async def fake_status(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[dict[str, Any]]:
        return [{"id": 810401, "wbStatus": "defect"}]

    monkeypatch.setattr(
        "app.services.wb_marketplace_orders_service.fetch_marketplace_orders_status",
        fake_status,
    )

    async with SessionLocal() as session:
        async with httpx.AsyncClient() as http_client:
            updated = await sync_order_statuses(
                session,
                tenant_id,
                seller_uuid,
                http_client,
                "token",
                actor_user_id=None,
            )
        await session.commit()
    assert updated == 1

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.wb_status == "defect"
        assert order.status == FBS_ORDER_STATUS_DEFECT
        assert order.reserve_status == RESERVE_STATUS_RELEASED
        res_stmt = select(func.count()).select_from(FbsOrderReservation).where(
            FbsOrderReservation.fbs_order_id == order_id
        )
        res = await session.execute(res_stmt)
        assert int(res.scalar_one()) == 0


@pytest.mark.asyncio
async def test_cancel_wb_error_surfaces_502(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    _tenant_id, order_id, _product_id = await _seed_reserved_order(
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_order_id=810601,
    )

    async def fake_cancel(
        client: object,
        *,
        api_token: str,
        order_id: int,
        marketplace_api_base: str | None = None,
    ) -> None:
        raise WildberriesClientError(
            "upstream_error",
            status_code=409,
            endpoint=f"/api/v3/orders/{order_id}/cancel",
            response_body='{"message":"order cannot be cancelled after sorting"}',
        )

    monkeypatch.setattr(
        "app.services.fbs_cancellation_service.cancel_marketplace_order",
        fake_cancel,
    )

    resp = await async_client.patch(
        f"/operations/fbs-orders/{order_id}/cancel",
        headers=headers,
    )
    assert resp.status_code == 502, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "wb_upstream_error_409"
    assert detail["message"] == (
        "Wildberries ответил: order cannot be cancelled after sorting"
    )
    assert detail["context"]["wb_status_code"] == 409
    assert detail["context"]["wb_endpoint"] == "/api/v3/orders/810601/cancel"
    assert detail["context"]["wb_order_id"] == 810601
    assert detail["context"]["ref"].startswith("wb-")
    assert detail["retryable"] is False
