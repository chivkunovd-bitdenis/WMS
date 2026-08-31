"""Wave 2: seller warehouse scope, intake privacy, assembly time and legacy reset."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_order import (
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_NO_STOCK,
    FbsOrder,
)
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_DONE,
    FbsSupply,
)
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product import Product
from app.models.seller import Seller
from app.services.wb_marketplace_orders_service import sync_seller_orders

WB_WAREHOUSE_OURS = 501001
WB_WAREHOUSE_UNMAPPED = 777888


async def _register_admin(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    suffix = str(time.time_ns())
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Wave 2 {suffix}",
            "slug": f"wave-2-{suffix}",
            "admin_email": f"wave-2-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}, suffix


async def _create_seller(
    async_client: AsyncClient, headers: dict[str, str], suffix: str, label: str = "Seller"
) -> str:
    response = await async_client.post(
        "/sellers", headers=headers, json={"name": f"{label} {suffix}"}
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


async def _create_warehouse(
    async_client: AsyncClient, headers: dict[str, str], suffix: str
) -> str:
    response = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Wave 2 WH", "code": f"wave-2-{suffix}"},
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


async def _set_marketplace_token(
    async_client: AsyncClient, headers: dict[str, str], seller_id: str
) -> None:
    response = await async_client.patch(
        f"/integrations/wildberries/sellers/{seller_id}/tokens",
        headers=headers,
        json={"marketplace_api_token": "wave-2-marketplace-token"},
    )
    assert response.status_code == 200, response.text


def _wb_order(order_id: int, warehouse_id: int, barcode: str) -> dict[str, Any]:
    return {
        "id": order_id,
        "rid": f"rid-{order_id}",
        "createdAt": "2026-08-28T08:00:00Z",
        "warehouseId": warehouse_id,
        "officeId": 601001,
        "nmId": order_id,
        "chrtId": order_id,
        "article": f"article-{order_id}",
        "skus": [barcode],
        "price": 1000,
    }


# TC-NEW-FBS-SHARE-W2-001: WB list is enriched and PUT persists served.
@pytest.mark.asyncio
async def test_fbs_seller_warehouses_contract_get_and_put(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_warehouses", True)
    headers, suffix = await _register_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)
    warehouse_id = await _create_warehouse(async_client, headers, suffix)
    await _set_marketplace_token(async_client, headers, seller_id)

    initial = await async_client.get(f"/fbs-sellers/{seller_id}/warehouses", headers=headers)
    assert initial.status_code == 200, initial.text
    row = initial.json()[0]
    assert row["wb_warehouse_id"] == WB_WAREHOUSE_OURS
    assert row["name"] == "E2E Seller Warehouse"
    assert row["served"] is False
    assert row["wms_warehouse_id"] is None

    missing_wms = await async_client.put(
        f"/fbs-sellers/{seller_id}/warehouses/{WB_WAREHOUSE_OURS}",
        headers=headers,
        json={"served": True, "wms_warehouse_id": None},
    )
    assert missing_wms.status_code == 422

    configured = await async_client.put(
        f"/fbs-sellers/{seller_id}/warehouses/{WB_WAREHOUSE_OURS}",
        headers=headers,
        json={"served": True, "wms_warehouse_id": warehouse_id},
    )
    assert configured.status_code == 200, configured.text
    assert configured.json()["served"] is True
    assert configured.json()["wms_warehouse_id"] == warehouse_id

    listed = await async_client.get(f"/fbs-sellers/{seller_id}/warehouses", headers=headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["served"] is True
    assert listed.json()[0]["wms_warehouse_id"] == warehouse_id

    disabled = await async_client.put(
        f"/fbs-sellers/{seller_id}/warehouses/{WB_WAREHOUSE_OURS}",
        headers=headers,
        json={"served": False, "wms_warehouse_id": warehouse_id},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["served"] is False
    async with SessionLocal() as session:
        binding = await session.scalar(
            select(FbsWarehouseBinding).where(
                FbsWarehouseBinding.seller_id == uuid.UUID(seller_id),
                FbsWarehouseBinding.wb_warehouse_id == WB_WAREHOUSE_OURS,
            )
        )
        assert binding is not None
        assert binding.served is False


# TC-NEW-FBS-SHARE-W2-002: explicitly foreign is discarded; an unknown WB
# warehouse is bound to the sole physical WMS warehouse.
@pytest.mark.asyncio
async def test_fbs_import_skips_unserved_but_binds_unknown_to_sole_warehouse(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)
    warehouse_id = await _create_warehouse(async_client, headers, suffix)
    await _set_marketplace_token(async_client, headers, seller_id)
    barcode = f"W2-BAR-{suffix}"
    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Wave 2 product",
            "sku_code": f"W2-{suffix}",
            "seller_id": seller_id,
            "wb_barcode": barcode,
        },
    )
    assert product.status_code in (200, 201), product.text

    async with SessionLocal() as session:
        seller = await session.get(Seller, uuid.UUID(seller_id))
        assert seller is not None
        tenant_id = seller.tenant_id
        session.add(
            FbsWarehouseBinding(
                tenant_id=tenant_id,
                seller_id=seller.id,
                wb_warehouse_id=WB_WAREHOUSE_OURS,
                wms_warehouse_id=uuid.UUID(warehouse_id),
                is_active=True,
                stock_sync_enabled=False,
                served=False,
            )
        )
        await session.commit()

    rows = [
        _wb_order(920001, WB_WAREHOUSE_OURS, barcode),
        _wb_order(920002, WB_WAREHOUSE_UNMAPPED, barcode),
    ]

    async def fake_new(*args: object, **kwargs: object) -> list[dict[str, Any]]:
        return rows

    monkeypatch.setattr(
        "app.services.wb_marketplace_orders_service.fetch_marketplace_orders_new",
        fake_new,
    )
    async with SessionLocal() as session, httpx.AsyncClient() as http_client:
        result = await sync_seller_orders(
            session,
            tenant_id,
            uuid.UUID(seller_id),
            http_client,
            include_history=False,
        )

    assert result["orders_received"] == 2
    assert result["orders_upserted"] == 1
    assert result["orders_created"] == 1
    assert result["orders_skipped_unserved"] == 1
    async with SessionLocal() as session:
        orders = list(
            (
                await session.execute(
                    select(FbsOrder).where(FbsOrder.seller_id == uuid.UUID(seller_id))
                )
            )
            .scalars()
            .all()
        )
    assert [order.wb_order_id for order in orders] == [920002]
    assert orders[0].warehouse_id == uuid.UUID(warehouse_id)
    assert orders[0].reserve_status == RESERVE_STATUS_NO_STOCK
    async with SessionLocal() as session:
        binding = await session.scalar(
            select(FbsWarehouseBinding).where(
                FbsWarehouseBinding.seller_id == uuid.UUID(seller_id),
                FbsWarehouseBinding.wb_warehouse_id == WB_WAREHOUSE_UNMAPPED,
            )
        )
    assert binding is not None
    assert binding.wms_warehouse_id == uuid.UUID(warehouse_id)
    assert binding.served is True
    assert binding.stock_sync_enabled is False


# TC-NEW-FBS-SHARE-W2-003: assembly metrics share one period and seller scope.
@pytest.mark.asyncio
async def test_fbs_assembly_time_period_and_seller_filter(async_client: AsyncClient) -> None:
    headers, suffix = await _register_admin(async_client)
    seller_a = await _create_seller(async_client, headers, suffix, "Seller A")
    seller_b = await _create_seller(async_client, headers, suffix, "Seller B")
    warehouse_id = await _create_warehouse(async_client, headers, suffix)
    period_from = datetime(2026, 8, 20, tzinfo=UTC)

    async with SessionLocal() as session:
        seller = await session.get(Seller, uuid.UUID(seller_a))
        assert seller is not None
        tenant_id = seller.tenant_id
        for index, (seller_id, hours) in enumerate(
            ((seller_a, 6), (seller_a, 12), (seller_b, 30)), start=1
        ):
            created_at = period_from + timedelta(days=index)
            supply = FbsSupply(
                tenant_id=tenant_id,
                seller_id=uuid.UUID(seller_id),
                warehouse_id=uuid.UUID(warehouse_id),
                wb_supply_id=f"W2-SUP-{index}",
                name=f"Supply {index}",
                status=FBS_SUPPLY_STATUS_DONE,
                delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
                delivered_at=created_at + timedelta(hours=hours),
            )
            session.add(supply)
            await session.flush()
            session.add(
                FbsOrder(
                    tenant_id=tenant_id,
                    seller_id=uuid.UUID(seller_id),
                    warehouse_id=uuid.UUID(warehouse_id),
                    wb_order_id=930000 + index,
                    supply_id=supply.id,
                    created_at_wb=created_at,
                    deadline_at=created_at + timedelta(hours=24),
                    mapping_status=MAPPING_STATUS_MAPPED,
                    reserve_status=RESERVE_STATUS_NO_STOCK,
                )
            )
        await session.commit()

    missing_period = await async_client.get("/fbs/assembly-time", headers=headers)
    assert missing_period.status_code == 422

    response = await async_client.get(
        "/fbs/assembly-time",
        headers=headers,
        params={
            "from": period_from.isoformat(),
            "to": (period_from + timedelta(days=7)).isoformat(),
            "seller_id": seller_a,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "hours": 9.0,
        "orders": 2,
        "within_12_hours_percent": 100,
        "within_24_hours_percent": 100,
    }

    all_sellers_response = await async_client.get(
        "/fbs/assembly-time",
        headers=headers,
        params={
            "from": period_from.isoformat(),
            "to": (period_from + timedelta(days=7)).isoformat(),
        },
    )
    assert all_sellers_response.status_code == 200, all_sellers_response.text
    assert all_sellers_response.json() == {
        "hours": 16.0,
        "orders": 3,
        "within_12_hours_percent": 67,
        "within_24_hours_percent": 67,
    }


# TC-NEW-FBS-SHARE-W2-003: an empty period returns zeroed assembly metrics.
@pytest.mark.asyncio
async def test_fbs_assembly_time_empty_period(async_client: AsyncClient) -> None:
    headers, _ = await _register_admin(async_client)
    period_from = datetime(2026, 9, 20, tzinfo=UTC)

    response = await async_client.get(
        "/fbs/assembly-time",
        headers=headers,
        params={
            "from": period_from.isoformat(),
            "to": (period_from + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "hours": 0.0,
        "orders": 0,
        "within_12_hours_percent": 0,
        "within_24_hours_percent": 0,
    }


# TC-NEW-FBS-SHARE-W2-005: warehouse and assembly routes never cross tenants.
@pytest.mark.asyncio
async def test_fbs_wave2_routes_are_tenant_isolated(async_client: AsyncClient) -> None:
    owner_headers, owner_suffix = await _register_admin(async_client)
    owner_seller_id = await _create_seller(
        async_client, owner_headers, owner_suffix, "Owner seller"
    )

    outsider_headers, outsider_suffix = await _register_admin(async_client)
    outsider_warehouse_id = await _create_warehouse(
        async_client, outsider_headers, outsider_suffix
    )

    warehouses = await async_client.get(
        f"/fbs-sellers/{owner_seller_id}/warehouses", headers=outsider_headers
    )
    assert warehouses.status_code == 404

    configure = await async_client.put(
        f"/fbs-sellers/{owner_seller_id}/warehouses/{WB_WAREHOUSE_OURS}",
        headers=outsider_headers,
        json={"served": True, "wms_warehouse_id": outsider_warehouse_id},
    )
    assert configure.status_code == 404

    period_from = datetime(2026, 8, 20, tzinfo=UTC)
    assembly = await async_client.get(
        "/fbs/assembly-time",
        headers=outsider_headers,
        params={
            "from": period_from.isoformat(),
            "to": (period_from + timedelta(days=7)).isoformat(),
            "seller_id": owner_seller_id,
        },
    )
    assert assembly.status_code == 404


# TC-NEW-FBS-SHARE-W2-004: legacy values reset only by the explicit second step.
@pytest.mark.asyncio
async def test_fbs_legacy_limits_reset_requires_rule_and_zeros_all_old_values(
    async_client: AsyncClient,
) -> None:
    headers, suffix = await _register_admin(async_client)
    seller_id = await _create_seller(async_client, headers, suffix)
    warehouse_id = await _create_warehouse(async_client, headers, suffix)
    configured = await async_client.put(
        f"/fbs-sellers/{seller_id}/warehouses/{WB_WAREHOUSE_OURS}",
        headers=headers,
        json={"served": True, "wms_warehouse_id": warehouse_id},
    )
    assert configured.status_code == 200, configured.text

    async def create_product(label: str) -> str:
        response = await async_client.post(
            "/products",
            headers=headers,
            json={
                "name": label,
                "sku_code": f"{label}-{suffix}",
                "seller_id": seller_id,
            },
        )
        assert response.status_code in (200, 201), response.text
        return response.json()["id"]

    configured_product_id = await create_product("Configured")
    untouched_product_id = await create_product("Untouched")
    async with SessionLocal() as session:
        for product_id in (configured_product_id, untouched_product_id):
            product = await session.get(Product, uuid.UUID(product_id))
            assert product is not None
            product.fbs_stock_limit = 9
        await session.commit()

    rejected = await async_client.post(
        "/products/fbs-rule/reset-legacy-limits",
        headers=headers,
        json={"product_ids": [untouched_product_id]},
    )
    assert rejected.status_code == 422
    assert "Сначала настройте правило" in rejected.json()["detail"]

    rule = await async_client.put(
        f"/products/{configured_product_id}/fbs-rule",
        headers=headers,
        json={
            "publish": True,
            "same_everywhere": False,
            "percent": 50,
            "by_warehouse": {str(WB_WAREHOUSE_OURS): 50},
        },
    )
    assert rule.status_code == 200, rule.text
    async with SessionLocal() as session:
        pool = await session.scalar(
            select(FbsBindingStockPool).where(
                FbsBindingStockPool.product_id == uuid.UUID(configured_product_id)
            )
        )
        assert pool is not None
        pool.quantity = 7
        product = await session.get(Product, uuid.UUID(configured_product_id))
        assert product is not None
        assert product.fbs_stock_limit == 9
        await session.commit()

    reset = await async_client.post(
        "/products/fbs-rule/reset-legacy-limits",
        headers=headers,
        json={"product_ids": [configured_product_id]},
    )
    assert reset.status_code == 200, reset.text
    assert reset.json() == {"updated_count": 1}

    async with SessionLocal() as session:
        configured_product = await session.get(Product, uuid.UUID(configured_product_id))
        untouched_product = await session.get(Product, uuid.UUID(untouched_product_id))
        assert configured_product is not None
        assert untouched_product is not None
        assert configured_product.fbs_stock_limit == 0
        assert untouched_product.fbs_stock_limit == 9
        quantity = await session.scalar(
            select(func.sum(FbsBindingStockPool.quantity)).where(
                FbsBindingStockPool.product_id == uuid.UUID(configured_product_id)
            )
        )
        assert quantity == 0
