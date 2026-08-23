from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.seller import Seller
from app.models.warehouse import Warehouse
from app.services import inventory_service
from app.services.sorting_location_service import get_or_create_sorting_location


def test_inventory_movement_has_frozen_storage_dimensions() -> None:
    columns = InventoryMovement.__table__.c

    assert columns.seller_id.nullable is True
    assert columns.warehouse_id.nullable is False
    assert columns.reporting_dimensions_legacy.nullable is False


def test_migrations_backfill_movements_and_exclude_technical_warehouses() -> None:
    versions = Path(__file__).parents[1] / "alembic/versions"
    movement_source = (
        versions / "20260823_0096_inventory_movement_reporting_dimensions.py"
    ).read_text()
    warehouse_source = (
        versions / "20260823_0098_exclude_technical_storage_warehouses.py"
    ).read_text()

    assert "SELECT product.seller_id" in movement_source
    assert "SELECT location.warehouse_id" in movement_source
    assert 'down_revision: str | Sequence[str] | None = "20260823_0095"' in movement_source
    assert "unresolved historical warehouse" in movement_source
    assert 'op.alter_column("inventory_movements", "warehouse_id", nullable=False)' in (
        movement_source
    )
    assert "lower(name) = 'fbs wb'" in warehouse_source
    assert "lower(code) LIKE 'fbs-wb-%'" in warehouse_source


@pytest.mark.asyncio
async def test_movement_freezes_seller_and_warehouse_at_write_time(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Storage movement scope",
            "slug": f"storage-movement-{suffix}",
            "admin_email": f"storage-movement-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    first_warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Storage warehouse", "code": f"storage-{suffix}"},
    )
    second_warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Moved warehouse", "code": f"moved-{suffix}"},
    )
    assert first_warehouse.status_code == 200, first_warehouse.text
    assert second_warehouse.status_code == 200, second_warehouse.text

    async with SessionLocal() as session:
        warehouse = await session.get(
            Warehouse,
            uuid.UUID(str(first_warehouse.json()["id"])),
        )
        assert warehouse is not None
        tenant_id = warehouse.tenant_id
        original_seller = Seller(tenant_id=tenant_id, name="Original seller")
        reassigned_seller = Seller(tenant_id=tenant_id, name="Reassigned seller")
        session.add_all([original_seller, reassigned_seller])
        await session.flush()
        product = Product(
            tenant_id=tenant_id,
            seller_id=original_seller.id,
            name="Storage product",
            sku_code=f"STORAGE-{suffix}",
        )
        session.add(product)
        await session.flush()
        location = await get_or_create_sorting_location(
            session,
            tenant_id,
            uuid.UUID(str(first_warehouse.json()["id"])),
        )

        movement = await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product.id,
            storage_location_id=location.id,
            quantity_delta=2,
            movement_type="storage_scope_test",
        )
        await session.flush()
        movement_id = movement.id
        original_seller_id = original_seller.id
        original_warehouse_id = location.warehouse_id

        product.seller_id = reassigned_seller.id
        location.code = f"moved-location-{suffix}"
        location.warehouse_id = uuid.UUID(str(second_warehouse.json()["id"]))
        await session.commit()

    async with SessionLocal() as session:
        saved = await session.scalar(
            select(InventoryMovement).where(InventoryMovement.id == movement_id)
        )
        assert saved is not None
        assert saved.seller_id == original_seller_id
        assert saved.warehouse_id == original_warehouse_id
        assert saved.reporting_dimensions_legacy is False
