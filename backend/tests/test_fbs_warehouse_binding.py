"""API tests for FBS warehouse bindings (STOCK-050).

TC-NEW-FBS-STOCK-003: binding CRUD maps WB warehouses to WMS warehouses.
TC-NEW-FBS-STOCK-004: unmapped path is separate; bindings are explicit.
TC-NEW-FBS-STOCK-014: admin binding API validates tenant/seller/warehouse.
N1: cross-tenant isolation → 404 without leaking existence.
N2: one WMS warehouse binds many WB warehouses for the same seller (pool 1, item 5).
N3: WMS warehouse change blocked when active FBS reservations exist.
N4: disable binding blocked when active FBS reservations exist.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_NEW,
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
    FbsOrderReservation,
)
from app.models.fbs_stock_sync_item import (
    STOCK_SYNC_STATUS_CONFIRMED,
    FbsStockSyncItem,
)
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product import Product
from app.models.seller import Seller
from app.models.warehouse import Warehouse
from app.services.fbs_autopoll_service import list_active_stock_sync_bindings


def _assert_fbs_error(
    response: Response,
    *,
    status_code: int,
    code: str,
    message: str,
) -> None:
    assert response.status_code == status_code, response.text
    assert response.json() == {
        "detail": {
            "code": code,
            "message": message,
            "context": {},
            "retryable": False,
        }
    }


async def _register_ff_admin(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS bind {suffix}",
            "slug": f"fbs-bind-{suffix}",
            "admin_email": f"fbs-bind-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    return headers, suffix


async def _create_seller(async_client: AsyncClient, headers: dict[str, str], suffix: str) -> str:
    seller = await async_client.post(
        "/sellers", headers=headers, json={"name": f"Seller {suffix}"}
    )
    assert seller.status_code in (200, 201), seller.text
    return seller.json()["id"]


async def _create_warehouse(
    async_client: AsyncClient, headers: dict[str, str], suffix: str, code_suffix: str
) -> str:
    wh = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": f"WH {code_suffix}", "code": f"wh-{suffix}-{code_suffix}"},
    )
    assert wh.status_code in (200, 201), wh.text
    return wh.json()["id"]


def _bindings_url(seller_id: str, wb_warehouse_id: int | None = None) -> str:
    base = f"/operations/fbs-sellers/{seller_id}/warehouse-bindings"
    if wb_warehouse_id is None:
        return base
    return f"{base}/{wb_warehouse_id}"


def _stock_sync_url(seller_id: str) -> str:
    return f"/operations/fbs-sellers/{seller_id}/stocks/sync"


def _stock_sync_status_url(seller_id: str, wb_warehouse_id: int) -> str:
    return (
        f"/operations/fbs-sellers/{seller_id}/stocks/sync-status"
        f"?wb_warehouse_id={wb_warehouse_id}"
    )


# TC-NEW-FBS-STOCK-014 — create binding, list, toggle sync, soft-disable
@pytest.mark.asyncio
async def test_fbs_warehouse_binding_crud_happy_path(async_client: AsyncClient) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)
    wh_a = await _create_warehouse(async_client, headers, suffix, "a")
    wh_b = await _create_warehouse(async_client, headers, suffix, "b")

    empty = await async_client.get(_bindings_url(seller_id), headers=headers)
    assert empty.status_code == 200
    assert empty.json() == []

    created = await async_client.put(
        _bindings_url(seller_id, 501001),
        headers=headers,
        json={"wms_warehouse_id": wh_a, "stock_sync_enabled": True},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["wb_warehouse_id"] == 501001
    assert body["wms_warehouse_id"] == wh_a
    assert body["is_active"] is True
    assert body["stock_sync_enabled"] is True

    listed = await async_client.get(_bindings_url(seller_id), headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    toggled = await async_client.put(
        _bindings_url(seller_id, 501001),
        headers=headers,
        json={"wms_warehouse_id": wh_a, "stock_sync_enabled": False},
    )
    assert toggled.status_code == 200
    assert toggled.json()["stock_sync_enabled"] is False

    moved = await async_client.put(
        _bindings_url(seller_id, 501001),
        headers=headers,
        json={"wms_warehouse_id": wh_b, "stock_sync_enabled": True},
    )
    assert moved.status_code == 200
    assert moved.json()["wms_warehouse_id"] == wh_b

    disabled = await async_client.delete(
        _bindings_url(seller_id, 501001),
        headers=headers,
    )
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False

    async with SessionLocal() as session:
        row = await session.scalar(
            select(FbsWarehouseBinding).where(
                FbsWarehouseBinding.seller_id == uuid.UUID(seller_id),
                FbsWarehouseBinding.wb_warehouse_id == 501001,
            )
        )
        assert row is not None
        assert row.is_active is False


# TC-NEW-FBS-STOCK-003 — two WB warehouses map to two distinct WMS warehouses
@pytest.mark.asyncio
async def test_fbs_warehouse_binding_two_wb_two_wms(async_client: AsyncClient) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)
    wh_a = await _create_warehouse(async_client, headers, suffix, "a")
    wh_b = await _create_warehouse(async_client, headers, suffix, "b")

    r1 = await async_client.put(
        _bindings_url(seller_id, 501001),
        headers=headers,
        json={"wms_warehouse_id": wh_a, "stock_sync_enabled": True},
    )
    assert r1.status_code == 200

    r2 = await async_client.put(
        _bindings_url(seller_id, 501002),
        headers=headers,
        json={"wms_warehouse_id": wh_b, "stock_sync_enabled": True},
    )
    assert r2.status_code == 200

    listed = await async_client.get(_bindings_url(seller_id), headers=headers)
    by_wb = {row["wb_warehouse_id"]: row for row in listed.json()}
    assert by_wb[501001]["wms_warehouse_id"] == wh_a
    assert by_wb[501002]["wms_warehouse_id"] == wh_b


# N1 — cross-tenant seller and warehouse do not leak
@pytest.mark.asyncio
async def test_fbs_warehouse_binding_cross_tenant_404(async_client: AsyncClient) -> None:
    headers_a, suffix_a = await _register_ff_admin(async_client)
    seller_a = await _create_seller(async_client, headers_a, suffix_a)
    wh_a = await _create_warehouse(async_client, headers_a, suffix_a, "a")

    headers_b, suffix_b = await _register_ff_admin(async_client)
    wh_b = await _create_warehouse(async_client, headers_b, suffix_b, "b")

    cross_list = await async_client.get(_bindings_url(seller_a), headers=headers_b)
    _assert_fbs_error(
        cross_list,
        status_code=404,
        code="seller_not_found",
        message="Селлер не найден.",
    )

    cross_put = await async_client.put(
        _bindings_url(seller_a, 501001),
        headers=headers_b,
        json={"wms_warehouse_id": wh_b, "stock_sync_enabled": True},
    )
    _assert_fbs_error(
        cross_put,
        status_code=404,
        code="seller_not_found",
        message="Селлер не найден.",
    )

    foreign_wh = await async_client.put(
        _bindings_url(seller_a, 501001),
        headers=headers_a,
        json={"wms_warehouse_id": wh_b, "stock_sync_enabled": True},
    )
    _assert_fbs_error(
        foreign_wh,
        status_code=404,
        code="warehouse_not_found",
        message="Склад не найден.",
    )

    ok = await async_client.put(
        _bindings_url(seller_a, 501001),
        headers=headers_a,
        json={"wms_warehouse_id": wh_a, "stock_sync_enabled": True},
    )
    assert ok.status_code == 200


# N2 — one WMS warehouse feeds many WB warehouses for the same seller
# (pool 1, item 5 of HANDOFF-POLISH.md): the former 409
# wms_warehouse_already_bound blocked live-order binding on staging.
@pytest.mark.asyncio
async def test_fbs_warehouse_binding_wms_shared_across_wb_warehouses(
    async_client: AsyncClient,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)
    wh_a = await _create_warehouse(async_client, headers, suffix, "a")

    first = await async_client.put(
        _bindings_url(seller_id, 501001),
        headers=headers,
        json={"wms_warehouse_id": wh_a, "stock_sync_enabled": True},
    )
    assert first.status_code == 200

    second = await async_client.put(
        _bindings_url(seller_id, 501002),
        headers=headers,
        json={"wms_warehouse_id": wh_a, "stock_sync_enabled": True},
    )
    assert second.status_code == 200, second.text
    assert second.json()["wms_warehouse_id"] == wh_a

    listed = await async_client.get(_bindings_url(seller_id), headers=headers)
    by_wb = {row["wb_warehouse_id"]: row for row in listed.json()}
    assert by_wb[501001]["wms_warehouse_id"] == wh_a
    assert by_wb[501002]["wms_warehouse_id"] == wh_a


# N3 — cannot change WMS warehouse while active FBS reservations exist
@pytest.mark.asyncio
async def test_fbs_warehouse_binding_blocked_by_active_reservations_409(
    async_client: AsyncClient,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)
    wh_a = await _create_warehouse(async_client, headers, suffix, "a")
    wh_b = await _create_warehouse(async_client, headers, suffix, "b")

    created = await async_client.put(
        _bindings_url(seller_id, 501001),
        headers=headers,
        json={"wms_warehouse_id": wh_a, "stock_sync_enabled": True},
    )
    assert created.status_code == 200

    async with SessionLocal() as session:
        seller = await session.get(Seller, uuid.UUID(seller_id))
        assert seller is not None
        tenant_id = seller.tenant_id
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            seller_id=seller.id,
            name="Bind product",
            sku_code=f"BIND-{suffix}",
            wb_barcode="BIND-BAR",
        )
        now = datetime.now(UTC)
        order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=seller.id,
            warehouse_id=uuid.UUID(wh_a),
            product_id=product.id,
            wb_order_id=990001,
            status=FBS_ORDER_STATUS_NEW,
            created_at_wb=now,
            deadline_at=now + timedelta(hours=24),
            mapping_status=MAPPING_STATUS_MAPPED,
            reserve_status=RESERVE_STATUS_RESERVED,
        )
        session.add_all([product, order])
        await session.flush()
        session.add(
            FbsOrderReservation(
                tenant_id=tenant_id,
                fbs_order_id=order.id,
                product_id=product.id,
                warehouse_id=uuid.UUID(wh_a),
                quantity=1,
            )
        )
        await session.commit()

    blocked = await async_client.put(
        _bindings_url(seller_id, 501001),
        headers=headers,
        json={"wms_warehouse_id": wh_b, "stock_sync_enabled": True},
    )
    _assert_fbs_error(
        blocked,
        status_code=409,
        code="active_fbs_reservations",
        message="Есть активные FBS-резервы.",
    )

    toggle_ok = await async_client.put(
        _bindings_url(seller_id, 501001),
        headers=headers,
        json={"wms_warehouse_id": wh_a, "stock_sync_enabled": False},
    )
    assert toggle_ok.status_code == 200
    assert toggle_ok.json()["stock_sync_enabled"] is False


# N4 — cannot disable binding while active FBS reservations exist
@pytest.mark.asyncio
async def test_fbs_warehouse_binding_disable_blocked_by_active_reservations_409(
    async_client: AsyncClient,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)
    wh_a = await _create_warehouse(async_client, headers, suffix, "a")

    created = await async_client.put(
        _bindings_url(seller_id, 501001),
        headers=headers,
        json={"wms_warehouse_id": wh_a, "stock_sync_enabled": True},
    )
    assert created.status_code == 200

    async with SessionLocal() as session:
        seller = await session.get(Seller, uuid.UUID(seller_id))
        assert seller is not None
        tenant_id = seller.tenant_id
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            seller_id=seller.id,
            name="Disable bind product",
            sku_code=f"DIS-{suffix}",
            wb_barcode="DIS-BAR",
        )
        now = datetime.now(UTC)
        order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=seller.id,
            warehouse_id=uuid.UUID(wh_a),
            product_id=product.id,
            wb_order_id=990002,
            status=FBS_ORDER_STATUS_NEW,
            created_at_wb=now,
            deadline_at=now + timedelta(hours=24),
            mapping_status=MAPPING_STATUS_MAPPED,
            reserve_status=RESERVE_STATUS_RESERVED,
        )
        session.add_all([product, order])
        await session.flush()
        session.add(
            FbsOrderReservation(
                tenant_id=tenant_id,
                fbs_order_id=order.id,
                product_id=product.id,
                warehouse_id=uuid.UUID(wh_a),
                quantity=1,
            )
        )
        await session.commit()

    blocked = await async_client.delete(
        _bindings_url(seller_id, 501001),
        headers=headers,
    )
    _assert_fbs_error(
        blocked,
        status_code=409,
        code="active_fbs_reservations",
        message="Есть активные FBS-резервы.",
    )

    async with SessionLocal() as session:
        row = await session.scalar(
            select(FbsWarehouseBinding).where(
                FbsWarehouseBinding.seller_id == uuid.UUID(seller_id),
                FbsWarehouseBinding.wb_warehouse_id == 501001,
            )
        )
        assert row is not None
        assert row.is_active is True


# TC-NEW-FBS-STOCK-014 — invalid WB warehouse id rejected
@pytest.mark.asyncio
async def test_fbs_warehouse_binding_invalid_wb_id_400(async_client: AsyncClient) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)
    wh_a = await _create_warehouse(async_client, headers, suffix, "a")

    bad = await async_client.put(
        _bindings_url(seller_id, 0),
        headers=headers,
        json={"wms_warehouse_id": wh_a, "stock_sync_enabled": True},
    )
    assert bad.status_code == 422


# TC-NEW-FBS-STOCK-004 — disable keeps row for audit; re-upsert reactivates
@pytest.mark.asyncio
async def test_fbs_warehouse_binding_reactivate_after_disable(async_client: AsyncClient) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)
    wh_a = await _create_warehouse(async_client, headers, suffix, "a")

    created = await async_client.put(
        _bindings_url(seller_id, 501001),
        headers=headers,
        json={"wms_warehouse_id": wh_a, "stock_sync_enabled": True},
    )
    binding_id = created.json()["id"]

    disabled = await async_client.delete(
        _bindings_url(seller_id, 501001),
        headers=headers,
    )
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False

    reactivated = await async_client.put(
        _bindings_url(seller_id, 501001),
        headers=headers,
        json={"wms_warehouse_id": wh_a, "stock_sync_enabled": True},
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["id"] == binding_id
    assert reactivated.json()["is_active"] is True


# TC-NEW-FBS-STOCK-014 — manual stock sync returns inline result without Celery broker
@pytest.mark.asyncio
async def test_fbs_manual_stock_sync_inline_200(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)
    wh_a = await _create_warehouse(async_client, headers, suffix, "sync")

    created = await async_client.put(
        _bindings_url(seller_id, 501001),
        headers=headers,
        json={"wms_warehouse_id": wh_a, "stock_sync_enabled": True},
    )
    assert created.status_code == 200

    async def fake_sync(
        session: object,
        tenant_id: uuid.UUID,
        sid: uuid.UUID,
        http_client: object,
        *,
        wb_warehouse_id: int | None = None,
    ) -> object:
        from app.services.fbs_autopoll_service import SellerStockSyncResult

        return SellerStockSyncResult(
            bindings_processed=1,
            products_targeted=2,
            products_confirmed=2,
        )

    monkeypatch.setattr(
        "app.api.fbs_sellers.sync_seller_stocks",
        fake_sync,
    )

    resp = await async_client.post(
        _stock_sync_url(seller_id),
        headers=headers,
        json={},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["bindings_processed"] == 1
    assert body["products_targeted"] == 2
    assert body["products_confirmed"] == 2


# TC-NEW-FBS-STOCK-020 — Celery broker: enqueue job, 202 + job body (not 500)
@pytest.mark.asyncio
async def test_fbs_manual_stock_sync_celery_202(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)
    wh_a = await _create_warehouse(async_client, headers, suffix, "celery")

    created = await async_client.put(
        _bindings_url(seller_id, 501001),
        headers=headers,
        json={"wms_warehouse_id": wh_a, "stock_sync_enabled": True},
    )
    assert created.status_code == 200

    enqueued_job_ids: list[str] = []

    def _fake_enqueue(job_id: uuid.UUID) -> None:
        enqueued_job_ids.append(str(job_id))

    monkeypatch.setattr(
        "app.api.fbs_sellers._enqueue_fbs_stock_sync_job",
        _fake_enqueue,
    )
    monkeypatch.setattr(settings, "celery_broker_url", "redis://test-broker/0")

    resp = await async_client.post(
        _stock_sync_url(seller_id),
        headers=headers,
        json={},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert "id" in body
    assert body["status"] == "pending"
    uuid.UUID(body["id"])
    assert enqueued_job_ids == [body["id"]]


# TC-NEW-FBS-STOCK-014 — sync status read returns per-chrt target/confirmed/status
@pytest.mark.asyncio
async def test_fbs_stock_sync_status_read(async_client: AsyncClient) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)
    wh_a = await _create_warehouse(async_client, headers, suffix, "status")

    created = await async_client.put(
        _bindings_url(seller_id, 501001),
        headers=headers,
        json={"wms_warehouse_id": wh_a, "stock_sync_enabled": True},
    )
    assert created.status_code == 200
    binding_id = created.json()["id"]

    async with SessionLocal() as session:
        binding = await session.get(FbsWarehouseBinding, uuid.UUID(binding_id))
        assert binding is not None
        product = Product(
            id=uuid.uuid4(),
            tenant_id=binding.tenant_id,
            seller_id=binding.seller_id,
            name="Sync product",
            sku_code=f"SYNC-{suffix}",
            wb_barcode="SYNC-BAR",
            wb_chrt_id=777001,
        )
        session.add(product)
        await session.flush()
        session.add(
            FbsStockSyncItem(
                binding_id=binding.id,
                product_id=product.id,
                chrt_id=777001,
                last_target_amount=5,
                last_confirmed_amount=5,
                status=STOCK_SYNC_STATUS_CONFIRMED,
            )
        )
        binding.last_sync_status = STOCK_SYNC_STATUS_CONFIRMED
        binding.last_sync_at = datetime.now(UTC)
        await session.commit()

    resp = await async_client.get(
        _stock_sync_status_url(seller_id, 501001),
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["wb_warehouse_id"] == 501001
    assert body["binding_last_sync_status"] == STOCK_SYNC_STATUS_CONFIRMED
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["chrt_id"] == 777001
    assert item["target"] == 5
    assert item["confirmed"] == 5
    assert item["status"] == STOCK_SYNC_STATUS_CONFIRMED
    assert item["error"] is None
    assert item["timestamp"] is not None


# TC-NEW-FBS-STOCK-014 — cross-tenant stock sync endpoints return 404
@pytest.mark.asyncio
async def test_fbs_stock_sync_cross_tenant_404(async_client: AsyncClient) -> None:
    headers_a, suffix_a = await _register_ff_admin(async_client)
    seller_a = await _create_seller(async_client, headers_a, suffix_a)
    headers_b, _ = await _register_ff_admin(async_client)

    cross_sync = await async_client.post(
        _stock_sync_url(seller_a),
        headers=headers_b,
        json={},
    )
    _assert_fbs_error(
        cross_sync,
        status_code=404,
        code="seller_not_found",
        message="Селлер не найден.",
    )

    cross_status = await async_client.get(
        _stock_sync_status_url(seller_a, 501001),
        headers=headers_b,
    )
    _assert_fbs_error(
        cross_status,
        status_code=404,
        code="seller_not_found",
        message="Селлер не найден.",
    )


# TC-NEW-FBS-STOCK-004 — old technical FBS WB warehouses are not publish sources
@pytest.mark.asyncio
async def test_fbs_stock_sync_ignores_auto_technical_warehouse(
    async_client: AsyncClient,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)

    async with SessionLocal() as session:
        seller = await session.get(Seller, uuid.UUID(seller_id))
        assert seller is not None
        technical = Warehouse(
            tenant_id=seller.tenant_id,
            name="FBS WB 777888",
            code=f"fbs-wb-{suffix[-8:]}-777888",
        )
        session.add(technical)
        await session.flush()
        session.add(
            FbsWarehouseBinding(
                tenant_id=seller.tenant_id,
                seller_id=seller.id,
                wb_warehouse_id=777888,
                wms_warehouse_id=technical.id,
                stock_sync_enabled=True,
                is_active=True,
            )
        )
        await session.commit()

    async with SessionLocal() as session:
        seller = await session.get(Seller, uuid.UUID(seller_id))
        assert seller is not None
        rows = await list_active_stock_sync_bindings(
            session,
            seller.tenant_id,
            seller.id,
        )
    assert rows == []


@pytest.mark.asyncio
async def test_wb_stock_sync_does_not_publish_ozon_binding(
    async_client: AsyncClient,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)

    async with SessionLocal() as session:
        seller = await session.get(Seller, uuid.UUID(seller_id))
        assert seller is not None
        warehouse = Warehouse(
            tenant_id=seller.tenant_id,
            name="Ozon physical",
            code=f"ozon-physical-{suffix[-8:]}",
        )
        session.add(warehouse)
        await session.flush()
        session.add(
            FbsWarehouseBinding(
                tenant_id=seller.tenant_id,
                seller_id=seller.id,
                marketplace="ozon",
                external_warehouse_id="ozon-warehouse",
                wb_warehouse_id=-777888,
                wms_warehouse_id=warehouse.id,
                stock_sync_enabled=True,
                is_active=True,
            )
        )
        await session.commit()

        rows = await list_active_stock_sync_bindings(
            session,
            seller.tenant_id,
            seller.id,
        )

    assert rows == []


# --- Ozon ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_ozon_warehouse_binding_can_be_created_and_found_by_a_posting(
    async_client: AsyncClient,
) -> None:
    """Привязку склада Ozon раньше было неоткуда взять.

    Модель по умолчанию ставила `wb`, три места создания маркетплейс не
    передавали, а у ручки такого поля не было вовсе. Каждый заказ Ozon из-за
    этого гарантированно получал «склад не привязан» и не резервировался.

    Идентификатор склада взят живой: `/v2/warehouse/list` на кабинете
    «ИП Горячкина Т.И.» 03.09.2026 отдал склад `1020005028840530` «мой склад».
    """
    headers, suffix = await _register_ff_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)
    warehouse_id = await _create_warehouse(async_client, headers, suffix, "ozon")
    ozon_warehouse_id = 1020005028840530

    created = await async_client.put(
        _bindings_url(seller_id, ozon_warehouse_id),
        headers=headers,
        json={
            "wms_warehouse_id": warehouse_id,
            "stock_sync_enabled": False,
            "marketplace": "ozon",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["marketplace"] == "ozon"
    # Внешний идентификатор подставляется из пути: именно по нему привязка
    # находится при разборе отправления.
    assert body["external_warehouse_id"] == str(ozon_warehouse_id)
    assert body["wb_warehouse_id"] == ozon_warehouse_id

    listed = await async_client.get(_bindings_url(seller_id), headers=headers)
    assert listed.status_code == 200, listed.text
    assert [row["marketplace"] for row in listed.json()] == ["ozon"]


@pytest.mark.asyncio
async def test_binding_marketplace_defaults_to_wb_and_keeps_external_id_empty(
    async_client: AsyncClient,
) -> None:
    """Вайлдберрисовский путь не меняется ни на шаг: то же тело, тот же результат."""
    headers, suffix = await _register_ff_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)
    warehouse_id = await _create_warehouse(async_client, headers, suffix, "wb")

    created = await async_client.put(
        _bindings_url(seller_id, 501001),
        headers=headers,
        json={"wms_warehouse_id": warehouse_id, "stock_sync_enabled": True},
    )
    assert created.status_code == 200, created.text
    assert created.json()["marketplace"] == "wb"
    assert created.json()["external_warehouse_id"] is None


@pytest.mark.asyncio
async def test_unknown_marketplace_is_refused_with_a_readable_error(
    async_client: AsyncClient,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)
    warehouse_id = await _create_warehouse(async_client, headers, suffix, "x")

    refused = await async_client.put(
        _bindings_url(seller_id, 501002),
        headers=headers,
        json={
            "wms_warehouse_id": warehouse_id,
            "stock_sync_enabled": False,
            "marketplace": "avito",
        },
    )
    assert refused.status_code == 422, refused.text


@pytest.mark.asyncio
async def test_ozon_binding_is_addressed_separately_from_the_wb_one(
    async_client: AsyncClient,
) -> None:
    """Одна ручка на два маркетплейса не должна их путать."""
    headers, suffix = await _register_ff_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)
    wh_wb = await _create_warehouse(async_client, headers, suffix, "wbwh")
    wh_ozon = await _create_warehouse(async_client, headers, suffix, "ozwh")

    wb = await async_client.put(
        _bindings_url(seller_id, 501003),
        headers=headers,
        json={"wms_warehouse_id": wh_wb, "stock_sync_enabled": True},
    )
    assert wb.status_code == 200, wb.text
    ozon = await async_client.put(
        _bindings_url(seller_id, 1020005028840530),
        headers=headers,
        json={
            "wms_warehouse_id": wh_ozon,
            "stock_sync_enabled": False,
            "marketplace": "ozon",
        },
    )
    assert ozon.status_code == 200, ozon.text

    listed = await async_client.get(_bindings_url(seller_id), headers=headers)
    rows = {row["marketplace"]: row for row in listed.json()}
    assert set(rows) == {"wb", "ozon"}
    assert rows["wb"]["wms_warehouse_id"] == wh_wb
    assert rows["ozon"]["wms_warehouse_id"] == wh_ozon
    assert rows["ozon"]["stock_sync_enabled"] is False
