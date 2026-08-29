from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.inbound_intake import InboundIntakeRequest
from app.models.pallet import Pallet
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox


async def _register(client: AsyncClient, label: str) -> tuple[dict[str, str], Tenant]:
    suffix = f"{label.replace('_', '-')}-{time.time_ns()}"
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


async def _create_warehouse(tenant_id: uuid.UUID, label: str) -> Warehouse:
    suffix = uuid.uuid4().hex[:10]
    async with SessionLocal() as session:
        warehouse = Warehouse(
            tenant_id=tenant_id,
            name=f"Склад {label}",
            code=f"sorting-{suffix}",
            barcode=f"WH-SORTING-{suffix}",
        )
        session.add(warehouse)
        await session.commit()
        await session.refresh(warehouse)
        session.expunge(warehouse)
    return warehouse


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["pallet", "box", "cargo_place"])
async def test_created_sorting_object_is_unassigned_on_map_and_resolvable_by_barcode(
    async_client: AsyncClient,
    kind: str,
) -> None:
    headers, tenant = await _register(async_client, f"create-{kind}")
    warehouse = await _create_warehouse(tenant.id, kind)

    created = await async_client.post(
        f"/warehouses/{warehouse.id}/sorting-objects",
        headers=headers,
        json={"kind": kind},
    )

    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["kind"] == kind
    assert payload["barcode"]
    assert payload["holder"] is None

    sorting_objects = await async_client.get(
        f"/warehouses/{warehouse.id}/sorting-objects",
        headers=headers,
    )
    assert sorting_objects.status_code == 200, sorting_objects.text
    sorting_row = next(
        row for row in sorting_objects.json()["objects"] if row["id"] == payload["id"]
    )
    assert sorting_row == payload

    warehouse_map = await async_client.get(
        f"/warehouses/{warehouse.id}/map",
        headers=headers,
    )
    assert warehouse_map.status_code == 200, warehouse_map.text
    map_row = next(
        row for row in warehouse_map.json()["unassigned"] if row["id"] == payload["id"]
    )
    assert map_row["kind"] == kind
    assert map_row["barcode"] == payload["barcode"]
    assert map_row["qty"] == 0
    assert map_row["children"] == []

    resolved = await async_client.get(
        "/operations/scan/resolve",
        headers=headers,
        params={"code": payload["barcode"], "warehouse_id": str(warehouse.id)},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["type"] == kind
    assert resolved.json()["id"] == payload["id"]

    async with SessionLocal() as session:
        if kind == "pallet":
            stored = await session.get(Pallet, uuid.UUID(payload["id"]))
            assert stored is not None
            assert stored.tenant_id == tenant.id
            assert stored.warehouse_id == warehouse.id
            assert stored.storage_location_id is None
            assert stored.disbanded_at is None
        else:
            stored_box = await session.get(WarehouseBox, uuid.UUID(payload["id"]))
            assert stored_box is not None
            assert stored_box.tenant_id == tenant.id
            assert stored_box.warehouse_id == warehouse.id
            assert stored_box.container_kind == kind
            assert stored_box.storage_location_id is None
            assert stored_box.pallet_id is None


@pytest.mark.asyncio
async def test_sorting_object_creation_and_listing_are_tenant_scoped(
    async_client: AsyncClient,
) -> None:
    owner_headers, owner_tenant = await _register(async_client, "owner")
    foreign_headers, foreign_tenant = await _register(async_client, "foreign")
    owner_warehouse = await _create_warehouse(owner_tenant.id, "owner")
    foreign_warehouse = await _create_warehouse(foreign_tenant.id, "foreign")
    created = await async_client.post(
        f"/warehouses/{owner_warehouse.id}/sorting-objects",
        headers=owner_headers,
        json={"kind": "box"},
    )
    assert created.status_code == 201, created.text

    foreign_list = await async_client.get(
        f"/warehouses/{foreign_warehouse.id}/sorting-objects",
        headers=foreign_headers,
    )
    assert foreign_list.status_code == 200, foreign_list.text
    assert created.json()["id"] not in {
        row["id"] for row in foreign_list.json()["objects"]
    }

    denied = await async_client.get(
        f"/warehouses/{owner_warehouse.id}/sorting-objects",
        headers=foreign_headers,
    )
    assert denied.status_code == 404
    assert denied.json()["detail"] == "warehouse_not_found"


@pytest.mark.asyncio
async def test_sorting_object_creation_rejects_missing_warehouse(
    async_client: AsyncClient,
) -> None:
    headers, _tenant = await _register(async_client, "missing")

    response = await async_client.post(
        f"/warehouses/{uuid.uuid4()}/sorting-objects",
        headers=headers,
        json={"kind": "cargo_place"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "warehouse_not_found"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["pallet", "box", "cargo_place"])
async def test_created_sorting_object_can_be_bound_to_one_inbound_request(
    async_client: AsyncClient,
    kind: str,
) -> None:
    headers, tenant = await _register(async_client, f"document-{kind}")
    warehouse = await _create_warehouse(tenant.id, kind)
    async with SessionLocal() as session:
        own_request = InboundIntakeRequest(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            status="sorting",
        )
        other_request = InboundIntakeRequest(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            status="sorting",
        )
        session.add_all([own_request, other_request])
        await session.commit()
        own_request_id = own_request.id
        other_request_id = other_request.id

    created = await async_client.post(
        f"/warehouses/{warehouse.id}/sorting-objects",
        headers=headers,
        json={"kind": kind, "inbound_request_id": str(own_request_id)},
    )

    assert created.status_code == 201, created.text
    object_id = created.json()["id"]
    own_listing = await async_client.get(
        f"/warehouses/{warehouse.id}/sorting-objects",
        headers=headers,
        params={"inbound_request_id": str(own_request_id)},
    )
    other_listing = await async_client.get(
        f"/warehouses/{warehouse.id}/sorting-objects",
        headers=headers,
        params={"inbound_request_id": str(other_request_id)},
    )

    assert own_listing.status_code == 200, own_listing.text
    assert object_id in {row["id"] for row in own_listing.json()["objects"]}
    assert other_listing.status_code == 200, other_listing.text
    assert object_id not in {row["id"] for row in other_listing.json()["objects"]}

    async with SessionLocal() as session:
        model = Pallet if kind == "pallet" else WarehouseBox
        stored = await session.get(model, uuid.UUID(object_id))
        assert stored is not None
        assert stored.inbound_request_id == own_request_id
