from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox
from app.services.sorting_location_service import get_or_create_sorting_location


async def _register(client: AsyncClient, label: str) -> tuple[dict[str, str], Tenant]:
    suffix = f"{label}-{time.time_ns()}"
    email = f"{suffix}@example.com"
    response = await client.post(
        "/auth/register",
        json={
            "organization_name": f"Склад {label}",
            "slug": suffix,
            "admin_email": email,
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        tenant = await session.get(Tenant, user.tenant_id)
        assert tenant is not None
        session.expunge(tenant)
    return headers, tenant


async def _seed_warehouse(
    tenant_id: uuid.UUID,
) -> tuple[Warehouse, StorageLocation, Product, InventoryBalance]:
    suffix = uuid.uuid4().hex[:10]
    async with SessionLocal() as session:
        warehouse = Warehouse(
            tenant_id=tenant_id,
            name="Склад раскладки",
            code=f"sorting-cells-{suffix}",
            barcode=f"WH-SORTING-CELLS-{suffix}",
        )
        session.add(warehouse)
        await session.flush()
        cell = StorageLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            code="А-01-01",
            barcode=f"CELL-{suffix}",
        )
        seller = Seller(tenant_id=tenant_id, name="ИП Раскладка")
        session.add_all([cell, seller])
        await session.flush()
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller.id,
            name="Товар для раскладки",
            sku_code=f"SORT-{suffix}",
            wb_barcode=f"4600{suffix[:8]}",
        )
        session.add(product)
        await session.flush()
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse.id)
        balance = InventoryBalance(
            tenant_id=tenant_id,
            storage_location_id=sorting.id,
            product_id=product.id,
            quantity=4,
            quantity_unpacked=4,
            quantity_packed=0,
        )
        session.add(balance)
        await session.commit()
        for row in (warehouse, cell, product, balance):
            session.expunge(row)
    return warehouse, cell, product, balance


async def _create_object(
    client: AsyncClient,
    headers: dict[str, str],
    warehouse_id: uuid.UUID,
    kind: str,
) -> dict[str, object]:
    response = await client.post(
        f"/warehouses/{warehouse_id}/sorting-objects",
        headers=headers,
        json={"kind": kind},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_object_in_cell_is_returned_with_cell_holder(
    async_client: AsyncClient,
) -> None:
    headers, tenant = await _register(async_client, "object-in-cell")
    warehouse, cell, _product, _balance = await _seed_warehouse(tenant.id)
    box = await _create_object(async_client, headers, warehouse.id, "box")

    placed = await async_client.post(
        f"/warehouses/{warehouse.id}/sorting-objects/place",
        headers=headers,
        json={
            "kind": "box",
            "id": box["id"],
            "cell_id": str(cell.id),
            "to_id": None,
            "qty": 1,
        },
    )
    assert placed.status_code == 200, placed.text

    response = await async_client.get(
        f"/warehouses/{warehouse.id}/sorting-objects",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    stored_cell = next(row for row in data["cells"] if row["id"] == str(cell.id))
    stored_box = next(row for row in data["objects"] if row["id"] == box["id"])
    assert stored_box["holder"] == f"cell:{cell.id}"
    assert stored_cell["objects"] == [stored_box]
    assert stored_cell["lines"] == []


@pytest.mark.asyncio
async def test_empty_target_returns_object_to_unassigned(
    async_client: AsyncClient,
) -> None:
    headers, tenant = await _register(async_client, "take-off-cell")
    warehouse, cell, _product, _balance = await _seed_warehouse(tenant.id)
    box = await _create_object(async_client, headers, warehouse.id, "box")
    placed = await async_client.post(
        f"/warehouses/{warehouse.id}/sorting-objects/place",
        headers=headers,
        json={
            "kind": "box",
            "id": box["id"],
            "cell_id": str(cell.id),
            "to_id": None,
            "qty": 1,
        },
    )
    assert placed.status_code == 200, placed.text

    removed = await async_client.post(
        f"/warehouses/{warehouse.id}/sorting-objects/place",
        headers=headers,
        json={
            "kind": "box",
            "id": box["id"],
            "cell_id": None,
            "to_id": None,
            "qty": 1,
        },
    )
    assert removed.status_code == 200, removed.text

    response = await async_client.get(
        f"/warehouses/{warehouse.id}/sorting-objects",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    unassigned_box = next(
        row for row in response.json()["objects"] if row["id"] == box["id"]
    )
    assert unassigned_box["holder"] is None


@pytest.mark.asyncio
async def test_to_id_places_box_inside_pallet(
    async_client: AsyncClient,
) -> None:
    headers, tenant = await _register(async_client, "box-in-pallet")
    warehouse, _cell, _product, _balance = await _seed_warehouse(tenant.id)
    pallet = await _create_object(async_client, headers, warehouse.id, "pallet")
    box = await _create_object(async_client, headers, warehouse.id, "box")

    placed = await async_client.post(
        f"/warehouses/{warehouse.id}/sorting-objects/place",
        headers=headers,
        json={
            "kind": "box",
            "id": box["id"],
            "cell_id": None,
            "to_id": pallet["id"],
            "qty": 1,
        },
    )
    assert placed.status_code == 200, placed.text

    response = await async_client.get(
        f"/warehouses/{warehouse.id}/sorting-objects",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    stored_box = next(
        row for row in response.json()["objects"] if row["id"] == box["id"]
    )
    assert stored_box["holder"] == f"obj:{pallet['id']}"
    assert not stored_box["holder"].startswith("cell:")
    async with SessionLocal() as session:
        db_box = await session.get(WarehouseBox, uuid.UUID(str(box["id"])))
        assert db_box is not None
        assert db_box.pallet_id == uuid.UUID(str(pallet["id"]))
        assert db_box.storage_location_id is None


@pytest.mark.asyncio
async def test_product_in_cell_is_returned_with_quantity(
    async_client: AsyncClient,
) -> None:
    headers, tenant = await _register(async_client, "product-in-cell")
    warehouse, cell, product, balance = await _seed_warehouse(tenant.id)

    placed = await async_client.post(
        f"/warehouses/{warehouse.id}/sorting-objects/place",
        headers=headers,
        json={
            "kind": "product",
            "id": str(balance.id),
            "cell_id": str(cell.id),
            "to_id": None,
            "qty": 4,
        },
    )
    assert placed.status_code == 200, placed.text

    response = await async_client.get(
        f"/warehouses/{warehouse.id}/sorting-objects",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    stored_line = next(
        row
        for row in data["lines"]
        if row["productId"] == str(product.id)
    )
    assert stored_line["holder"] == f"cell:{cell.id}"
    assert stored_line["qty"] == 4
    stored_cell = next(row for row in data["cells"] if row["id"] == str(cell.id))
    assert stored_cell["objects"] == []
    assert stored_cell["lines"] == [stored_line]
