from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, date, datetime, tzinfo

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderReservation
from app.models.product import Product
from app.models.stock_direction import StockDirection, StockMonthlySnapshot
from app.services import inventory_service, stock_direction_service
from app.services.fbs_stock_availability_service import fbs_available_qty_for_product
from app.services.marketplace_unload_service import list_available_products
from tests.inventory_actor_helpers import resolve_test_actor_user_id


@pytest.fixture(autouse=True)
def _disable_background_stock_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    def _noop(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(inventory_service, "schedule_seller_stock_publish", _noop)
    monkeypatch.setattr(stock_direction_service, "schedule_seller_stock_publish", _noop)


async def _seed_stocked_product(
    async_client: AsyncClient,
) -> tuple[dict[str, str], str, str, uuid.UUID, uuid.UUID, uuid.UUID]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Stock directions",
            "slug": f"stock-dir-{suffix}",
            "admin_email": f"stock-dir-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    admin_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    seller = await async_client.post(
        "/sellers", headers=admin_headers, json={"name": "Direction Seller"}
    )
    assert seller.status_code in (200, 201), seller.text
    warehouse = await async_client.post(
        "/warehouses",
        headers=admin_headers,
        json={"name": "WH", "code": f"stock-dir-{suffix[-8:]}"},
    )
    assert warehouse.status_code in (200, 201), warehouse.text
    location = await async_client.post(
        f"/warehouses/{warehouse.json()['id']}/locations",
        headers=admin_headers,
        json={"code": "DIR-1"},
    )
    assert location.status_code in (200, 201), location.text
    product = await async_client.post(
        "/products",
        headers=admin_headers,
        json={
            "name": "Direction Product",
            "sku_code": f"DIR-{suffix}",
            "seller_id": seller.json()["id"],
        },
    )
    assert product.status_code in (200, 201), product.text

    product_id = uuid.UUID(product.json()["id"])
    warehouse_id = uuid.UUID(warehouse.json()["id"])
    location_id = uuid.UUID(location.json()["id"])
    async with SessionLocal() as session:
        row = await session.get(Product, product_id)
        assert row is not None
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=row.tenant_id,
            product_id=product_id,
            storage_location_id=location_id,
            quantity_delta=10,
            movement_type="inbound_intake",
            actor_user_id=await resolve_test_actor_user_id(session, row.tenant_id),
        )
        await session.commit()

    return (
        admin_headers,
        str(seller.json()["id"]),
        product.json()["sku_code"],
        warehouse_id,
        location_id,
        product_id,
    )


async def _seller_headers(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    seller_id: str,
) -> dict[str, str]:
    email = f"seller-stock-dir-{time.time_ns()}@example.com"
    created = await async_client.post(
        "/auth/seller-accounts",
        headers=admin_headers,
        json={"seller_id": seller_id, "email": email, "password": "password123"},
    )
    assert created.status_code in (200, 201), created.text
    login = await async_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _ff_staff_headers(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    *,
    inventory: bool,
) -> dict[str, str]:
    email = f"ff-inventory-staff-{time.time_ns()}@example.com"
    created = await async_client.post(
        "/auth/staff-accounts",
        headers=admin_headers,
        json={"email": email},
    )
    assert created.status_code == 201, created.text
    permissions = await async_client.patch(
        f"/auth/staff-accounts/{created.json()['id']}/permissions",
        headers=admin_headers,
        json={
            "settings": False,
            "mp_shipments": False,
            "reception": False,
            "cells": False,
            "inventory": inventory,
            "packaging": False,
            "shift_lead": False,
        },
    )
    assert permissions.status_code == 200, permissions.text
    password = await async_client.post(
        "/auth/set-initial-password",
        json={"email": email, "password": "password123"},
    )
    assert password.status_code == 200, password.text
    login = await async_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _previous_month(value: date) -> date:
    if value.month == 1:
        return date(value.year - 1, 12, 1)
    return date(value.year, value.month - 1, 1)


def test_current_snapshot_month_uses_moscow_business_month(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FrozenDateTime:
        @staticmethod
        def now(tz: tzinfo | None = None) -> datetime:
            frozen = datetime(2026, 8, 31, 21, 30, tzinfo=UTC)
            if tz is None:
                return frozen.replace(tzinfo=None)
            return frozen.astimezone(tz)

    monkeypatch.setattr(stock_direction_service, "datetime", FrozenDateTime)

    assert stock_direction_service.current_snapshot_month() == date(2026, 9, 1)


@pytest.mark.asyncio
async def test_seller_stock_directions_summary_and_scope(
    async_client: AsyncClient,
) -> None:
    admin_headers, seller_id, _sku, warehouse_id, _location_id, product_id = (
        await _seed_stocked_product(async_client)
    )
    seller_headers = await _seller_headers(async_client, admin_headers, seller_id)

    reserve = await async_client.post(
        f"/products/{product_id}/stock-directions",
        headers=seller_headers,
        json={"name": "Reserve September", "quantity": 2, "is_fbs": False},
    )
    assert reserve.status_code == 201, reserve.text
    fbs = await async_client.post(
        f"/products/{product_id}/stock-directions",
        headers=seller_headers,
        json={"name": "FBS WB", "comment": "пул продаж", "quantity": 3, "is_fbs": True},
    )
    assert fbs.status_code == 201, fbs.text

    # Сравнять время создания явно. Правило сортировки — «сначала по времени,
    # при равном времени по имени», и проверять мы хотим именно вторую его
    # половину. Но `created_at` в SQLite идёт целыми секундами, и если два
    # запроса разошлись по разные стороны секунды, решает уже время, а не имя, —
    # тест падал через раз именно на этом.
    async with SessionLocal() as session:
        await session.execute(
            update(StockDirection)
            .where(StockDirection.product_id == product_id)
            .values(created_at=datetime(2026, 9, 1, 12, tzinfo=UTC))
        )
        await session.commit()

    listed = await async_client.get(
        f"/products/{product_id}/stock-directions",
        headers=seller_headers,
    )
    assert listed.status_code == 200, listed.text
    # Признак ФБС у направлений остатка отменён 18.08.2026 (коммит 36df9ce8,
    # «галка FBS убрана»): доля на ФБС задаётся у товара, а не направлением.
    # Поэтому оба направления обычные, и список идёт по времени создания.
    # Проверяем именно это правило, а не совпадение чисел: раньше тест ловил
    # порядок вставки и падал через раз.
    rows = listed.json()
    assert [row["is_fbs"] for row in rows] == [False, False], rows
    # Оба заведены в одну секунду, поэтому решает имя: «FBS WB» < «Reserve».
    assert [row["name"] for row in rows] == ["FBS WB", "Reserve September"], rows
    assert [row["quantity"] for row in rows] == [3, 2], rows

    summary = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=seller_headers,
        params={"warehouse_id": str(warehouse_id)},
    )
    assert summary.status_code == 200, summary.text
    row = next(item for item in summary.json() if item["product_id"] == str(product_id))
    assert row["quantity"] == 10
    # Галки «FBS» у направлений больше нет: оба направления — обычный резерв,
    # поэтому FBS-часть всегда ноль, а в резерв уходит вся сумма направлений.
    assert row["quantity_fbs"] == 0
    assert row["quantity_reserved_directions"] == 5
    assert row["quantity_free_fbo"] == 5
    assert row["available"] == 5

    too_much = await async_client.post(
        f"/products/{product_id}/stock-directions",
        headers=seller_headers,
        json={"name": "Сверх остатка", "quantity": 6, "is_fbs": False},
    )
    assert too_much.status_code == 422
    assert too_much.json()["detail"] == "directions_exceed_stock"


@pytest.mark.asyncio
async def test_directions_reserve_from_stock_and_mp_free_fbo(
    async_client: AsyncClient,
) -> None:
    admin_headers, seller_id, _sku, warehouse_id, _location_id, product_id = (
        await _seed_stocked_product(async_client)
    )

    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        tenant_id = product.tenant_id
        await stock_direction_service.create_stock_direction(
            session,
            tenant_id,
            product_id,
            name="FBS пул",
            quantity=4,
            is_fbs=True,
        )
        await stock_direction_service.create_stock_direction(
            session,
            tenant_id,
            product_id,
            name="Reserve",
            quantity=2,
            is_fbs=False,
        )

        assert (
            await fbs_available_qty_for_product(session, tenant_id, warehouse_id, product_id)
        ) == 4

        order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=uuid.UUID(seller_id),
            warehouse_id=warehouse_id,
            product_id=product_id,
            wb_order_id=930001,
            created_at_wb=product.created_at,
            deadline_at=product.created_at,
            mapping_status="mapped",
            reserve_status="reserved",
        )
        session.add(order)
        await session.flush()
        session.add(
            FbsOrderReservation(
                tenant_id=tenant_id,
                fbs_order_id=order.id,
                product_id=product_id,
                warehouse_id=warehouse_id,
                quantity=1,
            )
        )
        await session.commit()

        assert (
            await fbs_available_qty_for_product(session, tenant_id, warehouse_id, product_id)
        ) == 3
        available = await list_available_products(
            session,
            tenant_id,
            warehouse_id=warehouse_id,
            seller_id=uuid.UUID(seller_id),
        )
        assert available[0].available == 4

    admin_available = await async_client.get(
        "/operations/marketplace-unload-requests/available-products",
        headers=admin_headers,
        params={"warehouse_id": str(warehouse_id), "seller_id": seller_id},
    )
    assert admin_available.status_code == 200, admin_available.text
    assert admin_available.json()[0]["available"] == 4


@pytest.mark.asyncio
async def test_monthly_stock_snapshot_captures_distribution(
    async_client: AsyncClient,
) -> None:
    current_month = stock_direction_service.current_snapshot_month()
    admin_headers, seller_id, _sku, _warehouse_id, location_id, product_id = (
        await _seed_stocked_product(async_client)
    )
    fbs = await async_client.post(
        f"/products/{product_id}/stock-directions",
        headers=admin_headers,
        json={"name": "FBS", "quantity": 3, "is_fbs": True},
    )
    assert fbs.status_code == 201, fbs.text
    reserve = await async_client.post(
        f"/products/{product_id}/stock-directions",
        headers=admin_headers,
        json={"name": "Reserve", "quantity": 2, "is_fbs": False},
    )
    assert reserve.status_code == 201, reserve.text

    run = await async_client.post(
        "/operations/inventory-balances/monthly-snapshots/run",
        headers=admin_headers,
        json={"month": current_month.isoformat()},
    )
    assert run.status_code == 200, run.text
    row = next(item for item in run.json() if item["product_id"] == str(product_id))
    assert row["snapshot_month"] == current_month.isoformat()
    assert row["product_name"] == "Direction Product"
    assert row["sku_code"] == _sku
    assert row["quantity_total"] == 10
    assert row["quantity_fbs"] == 0
    assert row["quantity_reserved"] == 5
    assert row["quantity_free_fbo"] == 5

    changed_fbs = await async_client.patch(
        f"/products/stock-directions/{fbs.json()['id']}",
        headers=admin_headers,
        json={"quantity": 4},
    )
    assert changed_fbs.status_code == 200, changed_fbs.text
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=product.tenant_id,
            product_id=product_id,
            storage_location_id=location_id,
            quantity_delta=5,
            movement_type="inbound_intake",
            actor_user_id=await resolve_test_actor_user_id(session, product.tenant_id),
        )
        await session.commit()

    rerun = await async_client.post(
        "/operations/inventory-balances/monthly-snapshots/run",
        headers=admin_headers,
        json={"month": current_month.isoformat()},
    )
    assert rerun.status_code == 200, rerun.text
    rerun_row = next(item for item in rerun.json() if item["product_id"] == str(product_id))
    assert rerun_row["id"] == row["id"]
    assert rerun_row["quantity_total"] == 10
    assert rerun_row["quantity_fbs"] == 0
    assert rerun_row["quantity_reserved"] == 5
    assert rerun_row["quantity_free_fbo"] == 5

    new_product = await async_client.post(
        "/products",
        headers=admin_headers,
        json={
            "name": "Late Direction Product",
            "sku_code": f"LATE-DIR-{time.time_ns()}",
            "seller_id": seller_id,
        },
    )
    assert new_product.status_code in (200, 201), new_product.text
    new_product_id = uuid.UUID(new_product.json()["id"])
    async with SessionLocal() as session:
        late = await session.get(Product, new_product_id)
        assert late is not None
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=late.tenant_id,
            product_id=new_product_id,
            storage_location_id=location_id,
            quantity_delta=7,
            movement_type="inbound_intake",
            actor_user_id=await resolve_test_actor_user_id(session, late.tenant_id),
        )
        await session.commit()

    late_rerun = await async_client.post(
        "/operations/inventory-balances/monthly-snapshots/run",
        headers=admin_headers,
        json={"month": current_month.isoformat()},
    )
    assert late_rerun.status_code == 200, late_rerun.text
    assert len(late_rerun.json()) == len(run.json())
    assert all(item["product_id"] != str(new_product_id) for item in late_rerun.json())

    listed = await async_client.get(
        "/operations/inventory-balances/monthly-snapshots",
        headers=admin_headers,
        params={"month": current_month.isoformat()},
    )
    assert listed.status_code == 200, listed.text
    assert len([item for item in listed.json() if item["product_id"] == str(product_id)]) == 1
    assert all(item["product_id"] != str(new_product_id) for item in listed.json())


@pytest.mark.asyncio
async def test_monthly_stock_snapshot_get_requires_ff_inventory_access(
    async_client: AsyncClient,
) -> None:
    current_month = stock_direction_service.current_snapshot_month()
    admin_headers, seller_id, _sku, _warehouse_id, _location_id, product_id = (
        await _seed_stocked_product(async_client)
    )

    run = await async_client.post(
        "/operations/inventory-balances/monthly-snapshots/run",
        headers=admin_headers,
        json={"month": current_month.isoformat()},
    )
    assert run.status_code == 200, run.text

    admin_listed = await async_client.get(
        "/operations/inventory-balances/monthly-snapshots",
        headers=admin_headers,
        params={"month": current_month.isoformat()},
    )
    assert admin_listed.status_code == 200, admin_listed.text
    assert [row["product_id"] for row in admin_listed.json()] == [str(product_id)]

    inventory_staff_headers = await _ff_staff_headers(
        async_client,
        admin_headers,
        inventory=True,
    )
    staff_listed = await async_client.get(
        "/operations/inventory-balances/monthly-snapshots",
        headers=inventory_staff_headers,
        params={"month": current_month.isoformat()},
    )
    assert staff_listed.status_code == 200, staff_listed.text
    assert staff_listed.json() == admin_listed.json()

    no_inventory_staff_headers = await _ff_staff_headers(
        async_client,
        admin_headers,
        inventory=False,
    )
    blocked_staff = await async_client.get(
        "/operations/inventory-balances/monthly-snapshots",
        headers=no_inventory_staff_headers,
        params={"month": current_month.isoformat()},
    )
    assert blocked_staff.status_code == 403

    seller_headers = await _seller_headers(async_client, admin_headers, seller_id)
    blocked_seller = await async_client.get(
        "/operations/inventory-balances/monthly-snapshots",
        headers=seller_headers,
        params={"month": current_month.isoformat()},
    )
    assert blocked_seller.status_code == 403


@pytest.mark.asyncio
async def test_monthly_stock_snapshot_concurrent_first_run_returns_persisted_slice(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_month = stock_direction_service.current_snapshot_month()
    admin_headers, _seller_id, _sku, _warehouse_id, _location_id, product_id = (
        await _seed_stocked_product(async_client)
    )
    original_list = stock_direction_service.list_monthly_snapshots
    first_empty_reads = 0
    first_empty_reads_lock = asyncio.Lock()
    both_requests_reached_first_empty_read = asyncio.Event()

    async def _wait_after_first_empty_read(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        month: date,
    ) -> list[StockMonthlySnapshot]:
        nonlocal first_empty_reads
        rows = await original_list(session, tenant_id, month)
        if rows:
            return rows
        async with first_empty_reads_lock:
            first_empty_reads += 1
            if first_empty_reads == 2:
                both_requests_reached_first_empty_read.set()
        await both_requests_reached_first_empty_read.wait()
        return rows

    monkeypatch.setattr(
        stock_direction_service,
        "list_monthly_snapshots",
        _wait_after_first_empty_read,
    )

    first, second = await asyncio.gather(
        async_client.post(
            "/operations/inventory-balances/monthly-snapshots/run",
            headers=admin_headers,
            json={"month": current_month.isoformat()},
        ),
        async_client.post(
            "/operations/inventory-balances/monthly-snapshots/run",
            headers=admin_headers,
            json={"month": current_month.isoformat()},
        ),
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert len(first.json()) == 1
    assert first.json() == second.json()
    assert first.json()[0]["product_id"] == str(product_id)

    listed = await async_client.get(
        "/operations/inventory-balances/monthly-snapshots",
        headers=admin_headers,
        params={"month": current_month.isoformat()},
    )
    assert listed.status_code == 200, listed.text
    assert listed.json() == first.json()


@pytest.mark.asyncio
async def test_monthly_stock_snapshot_historical_month_without_rows_fails_closed(
    async_client: AsyncClient,
) -> None:
    historical_month = _previous_month(stock_direction_service.current_snapshot_month())
    admin_headers, _seller_id, _sku, _warehouse_id, _location_id, _product_id = (
        await _seed_stocked_product(async_client)
    )

    run = await async_client.post(
        "/operations/inventory-balances/monthly-snapshots/run",
        headers=admin_headers,
        json={"month": historical_month.isoformat()},
    )
    assert run.status_code == 422
    assert run.json()["detail"] == "monthly_snapshot_historical_empty"

    listed = await async_client.get(
        "/operations/inventory-balances/monthly-snapshots",
        headers=admin_headers,
        params={"month": historical_month.isoformat()},
    )
    assert listed.status_code == 200, listed.text
    assert listed.json() == []


@pytest.mark.asyncio
async def test_monthly_stock_snapshot_empty_current_month_can_run_later(
    async_client: AsyncClient,
) -> None:
    current_month = stock_direction_service.current_snapshot_month()
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Empty monthly snapshot",
            "slug": f"empty-monthly-snapshot-{suffix}",
            "admin_email": f"empty-monthly-snapshot-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    admin_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    empty_run = await async_client.post(
        "/operations/inventory-balances/monthly-snapshots/run",
        headers=admin_headers,
        json={"month": current_month.isoformat()},
    )
    assert empty_run.status_code == 422
    assert empty_run.json()["detail"] == "monthly_snapshot_empty"

    seller = await async_client.post(
        "/sellers", headers=admin_headers, json={"name": "Late Seller"}
    )
    assert seller.status_code in (200, 201), seller.text
    late_product = await async_client.post(
        "/products",
        headers=admin_headers,
        json={
            "name": "Late Product After Empty Run",
            "sku_code": f"LATE-AFTER-EMPTY-{suffix}",
            "seller_id": seller.json()["id"],
        },
    )
    assert late_product.status_code in (200, 201), late_product.text

    late_run = await async_client.post(
        "/operations/inventory-balances/monthly-snapshots/run",
        headers=admin_headers,
        json={"month": current_month.isoformat()},
    )
    assert late_run.status_code == 200, late_run.text
    assert [row["product_id"] for row in late_run.json()] == [late_product.json()["id"]]
