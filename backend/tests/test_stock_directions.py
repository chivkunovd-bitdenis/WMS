from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderReservation
from app.models.product import Product
from app.services import inventory_service, stock_direction_service
from app.services.fbs_stock_availability_service import fbs_available_qty_for_product
from app.services.marketplace_unload_service import list_available_products


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

    listed = await async_client.get(
        f"/products/{product_id}/stock-directions",
        headers=seller_headers,
    )
    assert listed.status_code == 200, listed.text
    assert [row["quantity"] for row in listed.json()] == [3, 2]

    summary = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=seller_headers,
        params={"warehouse_id": str(warehouse_id)},
    )
    assert summary.status_code == 200, summary.text
    row = next(item for item in summary.json() if item["product_id"] == str(product_id))
    assert row["quantity"] == 10
    assert row["quantity_fbs"] == 3
    assert row["quantity_reserved_directions"] == 2
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
async def test_directions_drive_fbs_pool_and_mp_free_fbo(
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
    admin_headers, _seller_id, _sku, _warehouse_id, _location_id, product_id = (
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
        json={"month": "2026-08-12"},
    )
    assert run.status_code == 200, run.text
    row = next(item for item in run.json() if item["product_id"] == str(product_id))
    assert row["snapshot_month"] == "2026-08-01"
    assert row["quantity_total"] == 10
    assert row["quantity_fbs"] == 3
    assert row["quantity_reserved"] == 2
    assert row["quantity_free_fbo"] == 5

    listed = await async_client.get(
        "/operations/inventory-balances/monthly-snapshots",
        headers=admin_headers,
        params={"month": "2026-08-01"},
    )
    assert listed.status_code == 200, listed.text
    assert len([item for item in listed.json() if item["product_id"] == str(product_id)]) == 1
