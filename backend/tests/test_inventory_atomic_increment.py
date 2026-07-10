"""Concurrent positive inventory increments use an atomic database upsert."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, engine
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import (
    MOVEMENT_TYPE_OUTBOUND_SHIPMENT,
    MOVEMENT_TYPE_PRODUCT_TZ_IMPORT,
    InventoryMovement,
)
from app.models.product import Product
from app.services import inventory_service
from app.services.sorting_location_service import get_or_create_sorting_location


@dataclass(frozen=True)
class InventoryContext:
    tenant_id: uuid.UUID
    product_id: uuid.UUID
    storage_location_id: uuid.UUID


async def _create_inventory_context(
    async_client: AsyncClient,
    marker: str,
) -> InventoryContext:
    suffix = f"{marker}-{time.time_ns()}"
    register = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Atomic {marker}",
            "slug": suffix,
            "admin_email": f"{suffix}@example.com",
            "password": "password123",
        },
    )
    assert register.status_code == 200, register.text
    headers = {"Authorization": f"Bearer {register.json()['access_token']}"}
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Atomic warehouse", "code": f"atomic-{time.time_ns()}"},
    )
    product_response = await async_client.post(
        "/products",
        headers=headers,
        json={"name": "Atomic product", "sku_code": f"ATOMIC-{time.time_ns()}"},
    )
    assert warehouse.status_code == 200, warehouse.text
    assert product_response.status_code == 200, product_response.text
    warehouse_id = uuid.UUID(str(warehouse.json()["id"]))
    product_id = uuid.UUID(str(product_response.json()["id"]))
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        sorting = await get_or_create_sorting_location(
            session, product.tenant_id, warehouse_id
        )
        await session.commit()
    return InventoryContext(product.tenant_id, product_id, sorting.id)


async def _seed_unpacked(context: InventoryContext, quantity: int) -> None:
    async with SessionLocal() as session:
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=context.tenant_id,
            product_id=context.product_id,
            storage_location_id=context.storage_location_id,
            quantity_delta=quantity,
            movement_type=MOVEMENT_TYPE_PRODUCT_TZ_IMPORT,
        )
        await session.commit()


async def _preload_balance_for_postgresql(
    session: AsyncSession,
    context: InventoryContext,
) -> None:
    if engine.dialect.name != "postgresql":
        return
    await session.execute(
        select(InventoryBalance).where(
            InventoryBalance.tenant_id == context.tenant_id,
            InventoryBalance.product_id == context.product_id,
            InventoryBalance.storage_location_id == context.storage_location_id,
        )
    )


def test_positive_balance_upsert_compiles_for_postgresql() -> None:
    stmt = inventory_service._build_positive_balance_upsert(
        dialect_name="postgresql",
        tenant_id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        storage_location_id=uuid.uuid4(),
        quantity_delta=7,
    )

    sql = str(
        stmt.compile(
            dialect=postgresql.dialect()  # type: ignore[no-untyped-call]
        )
    )

    assert "ON CONFLICT (storage_location_id, product_id) DO UPDATE" in sql
    assert "quantity_unpacked" in sql
    assert "quantity_packed" in sql


@pytest.mark.asyncio
async def test_concurrent_positive_movements_do_not_lose_balance(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    register = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Atomic inventory",
            "slug": f"atomic-inventory-{suffix}",
            "admin_email": f"atomic-inventory-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert register.status_code == 200, register.text
    headers = {"Authorization": f"Bearer {register.json()['access_token']}"}
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Atomic warehouse", "code": f"atomic-{suffix[-8:]}"},
    )
    product_response = await async_client.post(
        "/products",
        headers=headers,
        json={"name": "Atomic product", "sku_code": f"ATOMIC-{suffix}"},
    )
    assert warehouse.status_code == 200, warehouse.text
    assert product_response.status_code == 200, product_response.text
    warehouse_id = uuid.UUID(str(warehouse.json()["id"]))
    product_id = uuid.UUID(str(product_response.json()["id"]))

    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        tenant_id = product.tenant_id
        sorting = await get_or_create_sorting_location(
            session, tenant_id, warehouse_id
        )
        sorting_id = sorting.id
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=sorting_id,
            quantity_delta=10,
            movement_type=MOVEMENT_TYPE_PRODUCT_TZ_IMPORT,
        )
        await inventory_service.apply_packaging_convert(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=sorting_id,
            quantity=4,
        )
        await session.commit()

    async def add_quantity(quantity: int) -> None:
        async with SessionLocal() as session:
            await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=tenant_id,
                product_id=product_id,
                storage_location_id=sorting_id,
                quantity_delta=quantity,
                movement_type=MOVEMENT_TYPE_PRODUCT_TZ_IMPORT,
            )
            await session.commit()

    await asyncio.gather(add_quantity(7), add_quantity(11))

    async with SessionLocal() as session:
        balance = (
            await session.execute(
                select(InventoryBalance).where(
                    InventoryBalance.tenant_id == tenant_id,
                    InventoryBalance.product_id == product_id,
                    InventoryBalance.storage_location_id == sorting_id,
                )
            )
        ).scalar_one()
        movement_totals = (
            await session.execute(
                select(
                    func.count(InventoryMovement.id),
                    func.sum(InventoryMovement.quantity_delta),
                ).where(
                    InventoryMovement.tenant_id == tenant_id,
                    InventoryMovement.product_id == product_id,
                    InventoryMovement.storage_location_id == sorting_id,
                    InventoryMovement.movement_type
                    == MOVEMENT_TYPE_PRODUCT_TZ_IMPORT,
                )
            )
        ).one()

    assert balance.quantity_unpacked == 24
    assert balance.quantity_packed == 4
    assert balance.quantity == 28
    assert balance.quantity == balance.quantity_unpacked + balance.quantity_packed
    assert movement_totals == (3, 28)


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
async def test_import_and_pack_overlap_without_lost_bucket_update(
    async_client: AsyncClient,
) -> None:
    context = await _create_inventory_context(async_client, "import-pack")
    await _seed_unpacked(context, 10)
    barrier = asyncio.Barrier(2)

    async def import_quantity() -> None:
        async with SessionLocal() as session:
            await _preload_balance_for_postgresql(session, context)
            await barrier.wait()
            await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=context.tenant_id,
                product_id=context.product_id,
                storage_location_id=context.storage_location_id,
                quantity_delta=7,
                movement_type=MOVEMENT_TYPE_PRODUCT_TZ_IMPORT,
            )
            await session.commit()

    async def package_quantity() -> None:
        async with SessionLocal() as session:
            await _preload_balance_for_postgresql(session, context)
            await barrier.wait()
            await inventory_service.apply_packaging_convert(
                session,
                tenant_id=context.tenant_id,
                product_id=context.product_id,
                storage_location_id=context.storage_location_id,
                quantity=4,
            )
            await session.commit()

    await asyncio.gather(import_quantity(), package_quantity())

    async with SessionLocal() as session:
        balance = (
            await session.execute(
                select(InventoryBalance).where(
                    InventoryBalance.tenant_id == context.tenant_id,
                    InventoryBalance.product_id == context.product_id,
                    InventoryBalance.storage_location_id
                    == context.storage_location_id,
                )
            )
        ).scalar_one()
        movement_deltas = (
            await session.scalars(
                select(InventoryMovement.quantity_delta)
                .where(
                    InventoryMovement.tenant_id == context.tenant_id,
                    InventoryMovement.product_id == context.product_id,
                    InventoryMovement.storage_location_id
                    == context.storage_location_id,
                )
                .order_by(InventoryMovement.created_at, InventoryMovement.id)
            )
        ).all()

    assert (balance.quantity_unpacked, balance.quantity_packed) == (13, 4)
    assert balance.quantity == 17
    assert balance.quantity == balance.quantity_unpacked + balance.quantity_packed
    assert sorted(movement_deltas) == [7, 10]


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
async def test_import_and_deduct_overlap_without_lost_bucket_update(
    async_client: AsyncClient,
) -> None:
    context = await _create_inventory_context(async_client, "import-deduct")
    await _seed_unpacked(context, 10)
    async with SessionLocal() as session:
        await inventory_service.apply_packaging_convert(
            session,
            tenant_id=context.tenant_id,
            product_id=context.product_id,
            storage_location_id=context.storage_location_id,
            quantity=4,
        )
        await session.commit()
    barrier = asyncio.Barrier(2)

    async def import_quantity() -> None:
        async with SessionLocal() as session:
            await _preload_balance_for_postgresql(session, context)
            await barrier.wait()
            await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=context.tenant_id,
                product_id=context.product_id,
                storage_location_id=context.storage_location_id,
                quantity_delta=7,
                movement_type=MOVEMENT_TYPE_PRODUCT_TZ_IMPORT,
            )
            await session.commit()

    async def deduct_quantity() -> None:
        async with SessionLocal() as session:
            await _preload_balance_for_postgresql(session, context)
            await barrier.wait()
            await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=context.tenant_id,
                product_id=context.product_id,
                storage_location_id=context.storage_location_id,
                quantity_delta=-4,
                movement_type=MOVEMENT_TYPE_OUTBOUND_SHIPMENT,
                deduct_prefer="unpacked",
            )
            await session.commit()

    await asyncio.gather(import_quantity(), deduct_quantity())

    async with SessionLocal() as session:
        balance = (
            await session.execute(
                select(InventoryBalance).where(
                    InventoryBalance.tenant_id == context.tenant_id,
                    InventoryBalance.product_id == context.product_id,
                    InventoryBalance.storage_location_id
                    == context.storage_location_id,
                )
            )
        ).scalar_one()
        movement_deltas = (
            await session.scalars(
                select(InventoryMovement.quantity_delta).where(
                    InventoryMovement.tenant_id == context.tenant_id,
                    InventoryMovement.product_id == context.product_id,
                    InventoryMovement.storage_location_id
                    == context.storage_location_id,
                )
            )
        ).all()

    assert (balance.quantity_unpacked, balance.quantity_packed) == (9, 4)
    assert balance.quantity == 13
    assert balance.quantity == balance.quantity_unpacked + balance.quantity_packed
    assert sorted(movement_deltas) == [-4, 7, 10]
