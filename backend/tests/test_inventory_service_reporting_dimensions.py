from __future__ import annotations

import time
import uuid
from typing import Any

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.seller import Seller
from app.services import inventory_service
from app.services.sorting_location_service import get_or_create_sorting_location


@pytest.mark.asyncio
async def test_movement_keeps_seller_and_warehouse_at_write_time(
    async_client: Any,
) -> None:
    suffix = str(time.time_ns())
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Reporting dimensions",
            "slug": f"reporting-{suffix}",
            "admin_email": f"reporting-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    warehouse_response = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Warehouse one", "code": f"wh-one-{suffix}"},
    )
    warehouse_two_response = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Warehouse two", "code": f"wh-two-{suffix}"},
    )
    product_response = await async_client.post(
        "/products",
        headers=headers,
        json={"name": "Reporting product", "sku_code": f"REPORT-{suffix}"},
    )
    assert warehouse_response.status_code == 200, warehouse_response.text
    assert warehouse_two_response.status_code == 200, warehouse_two_response.text
    assert product_response.status_code == 200, product_response.text

    warehouse_id = uuid.UUID(str(warehouse_response.json()["id"]))
    warehouse_two_id = uuid.UUID(str(warehouse_two_response.json()["id"]))
    product_id = uuid.UUID(str(product_response.json()["id"]))

    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        seller = Seller(tenant_id=product.tenant_id, name="Original seller")
        session.add(seller)
        await session.flush()
        product.seller_id = seller.id
        location = await get_or_create_sorting_location(
            session, product.tenant_id, warehouse_id
        )
        await session.flush()

        movement = await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=product.tenant_id,
            product_id=product.id,
            storage_location_id=location.id,
            quantity_delta=3,
            movement_type="reporting_test",
        )
        await session.flush()
        original_seller_id = seller.id

        product.seller_id = None
        location.code = f"moved-{suffix}"
        location.warehouse_id = warehouse_two_id
        await session.commit()

    async with SessionLocal() as session:
        saved = await session.scalar(
            select(InventoryMovement).where(InventoryMovement.id == movement.id)
        )
        assert saved is not None
        assert saved.seller_id == original_seller_id
        assert saved.warehouse_id == warehouse_id
        assert saved.reporting_dimensions_legacy is False
