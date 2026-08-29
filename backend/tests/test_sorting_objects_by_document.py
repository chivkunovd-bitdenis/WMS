from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeCargoPlace,
    InboundIntakeLine,
    InboundIntakeRequest,
)
from app.models.inventory_balance import InventoryBalance
from app.models.pallet import Pallet
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services.sorting_location_service import get_or_create_sorting_location


@dataclass(frozen=True)
class SortingDocumentSeed:
    headers: dict[str, str]
    warehouse_id: uuid.UUID
    request_id: uuid.UUID
    own_product_id: uuid.UUID
    other_product_id: uuid.UUID
    own_container_ids: frozenset[uuid.UUID]
    other_container_ids: frozenset[uuid.UUID]
    accepted_qty: int


async def _register(client: AsyncClient) -> tuple[dict[str, str], Tenant]:
    suffix = f"sorting-doc-{time.time_ns()}"
    email = f"{suffix}@example.com"
    response = await client.post(
        "/auth/register",
        json={
            "organization_name": "Склад документной раскладки",
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


async def _seed_two_documents(client: AsyncClient) -> SortingDocumentSeed:
    headers, tenant = await _register(client)
    suffix = uuid.uuid4().hex[:10]
    async with SessionLocal() as session:
        warehouse = Warehouse(
            tenant_id=tenant.id,
            name="Склад приёмок",
            code=f"sorting-doc-{suffix}",
            barcode=f"WH-SORTING-DOC-{suffix}",
        )
        seller = Seller(tenant_id=tenant.id, name="ИП Документы")
        session.add_all([warehouse, seller])
        await session.flush()

        own_product = Product(
            tenant_id=tenant.id,
            seller_id=seller.id,
            name="Товар выбранной приёмки",
            sku_code=f"OWN-{suffix}",
            wb_barcode=f"OWN-BC-{suffix}",
        )
        other_product = Product(
            tenant_id=tenant.id,
            seller_id=seller.id,
            name="Товар другой приёмки",
            sku_code=f"OTHER-{suffix}",
            wb_barcode=f"OTHER-BC-{suffix}",
        )
        session.add_all([own_product, other_product])
        await session.flush()

        own_request = InboundIntakeRequest(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            seller_id=seller.id,
            status="sorting",
            document_number="000034",
        )
        other_request = InboundIntakeRequest(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            seller_id=seller.id,
            status="sorting",
            document_number="000035",
        )
        session.add_all([own_request, other_request])
        await session.flush()

        accepted_qty = 7
        session.add_all(
            [
                InboundIntakeLine(
                    request_id=own_request.id,
                    product_id=own_product.id,
                    expected_qty=9,
                    actual_qty=accepted_qty,
                    posted_qty=0,
                ),
                InboundIntakeLine(
                    request_id=other_request.id,
                    product_id=other_product.id,
                    expected_qty=11,
                    actual_qty=11,
                    posted_qty=0,
                ),
            ]
        )

        own_pallet = Pallet(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            code=f"ПЛ-OWN-{suffix}",
            barcode=f"PALLET-OWN-{suffix}",
        )
        other_pallet = Pallet(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            code=f"ПЛ-OTHER-{suffix}",
            barcode=f"PALLET-OTHER-{suffix}",
        )
        session.add_all([own_pallet, other_pallet])
        await session.flush()

        own_box = InboundIntakeBox(
            tenant_id=tenant.id,
            request_id=own_request.id,
            box_number=1,
            internal_barcode=f"BOX-OWN-{suffix}",
            pallet_id=own_pallet.id,
        )
        own_cargo_place = InboundIntakeCargoPlace(
            tenant_id=tenant.id,
            request_id=own_request.id,
            place_number=1,
            internal_barcode=f"CARGO-OWN-{suffix}",
            pallet_id=own_pallet.id,
        )
        other_box = InboundIntakeBox(
            tenant_id=tenant.id,
            request_id=other_request.id,
            box_number=1,
            internal_barcode=f"BOX-OTHER-{suffix}",
            pallet_id=other_pallet.id,
        )
        session.add_all([own_box, own_cargo_place, other_box])

        sorting = await get_or_create_sorting_location(session, tenant.id, warehouse.id)
        session.add_all(
            [
                InventoryBalance(
                    tenant_id=tenant.id,
                    storage_location_id=sorting.id,
                    product_id=own_product.id,
                    quantity=13,
                    quantity_unpacked=13,
                    quantity_packed=0,
                ),
                InventoryBalance(
                    tenant_id=tenant.id,
                    storage_location_id=sorting.id,
                    product_id=other_product.id,
                    quantity=11,
                    quantity_unpacked=11,
                    quantity_packed=0,
                ),
            ]
        )
        await session.commit()

        return SortingDocumentSeed(
            headers=headers,
            warehouse_id=warehouse.id,
            request_id=own_request.id,
            own_product_id=own_product.id,
            other_product_id=other_product.id,
            own_container_ids=frozenset({own_pallet.id, own_box.id, own_cargo_place.id}),
            other_container_ids=frozenset({other_pallet.id, other_box.id}),
            accepted_qty=accepted_qty,
        )


async def _get_sorting_objects(
    client: AsyncClient,
    seed: SortingDocumentSeed,
    *,
    by_document: bool,
) -> dict[str, Any]:
    params = {"inbound_request_id": str(seed.request_id)} if by_document else None
    response = await client.get(
        f"/warehouses/{seed.warehouse_id}/sorting-objects",
        headers=seed.headers,
        params=params,
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_without_parameter_returns_whole_warehouse(
    async_client: AsyncClient,
) -> None:
    seed = await _seed_two_documents(async_client)

    data = await _get_sorting_objects(async_client, seed, by_document=False)

    assert {row["productId"] for row in data["lines"]} == {
        str(seed.own_product_id),
        str(seed.other_product_id),
    }
    assert {uuid.UUID(row["id"]) for row in data["objects"]} == (
        seed.own_container_ids | seed.other_container_ids
    )
    assert sum(row["qty"] for row in data["lines"]) == 24


@pytest.mark.asyncio
async def test_with_parameter_returns_only_selected_document_contents(
    async_client: AsyncClient,
) -> None:
    seed = await _seed_two_documents(async_client)

    data = await _get_sorting_objects(async_client, seed, by_document=True)

    assert {row["productId"] for row in data["lines"]} == {
        str(seed.own_product_id)
    }
    assert {uuid.UUID(row["id"]) for row in data["objects"]} == seed.own_container_ids


@pytest.mark.asyncio
async def test_other_document_containers_are_not_returned(
    async_client: AsyncClient,
) -> None:
    seed = await _seed_two_documents(async_client)

    data = await _get_sorting_objects(async_client, seed, by_document=True)
    returned_ids = {uuid.UUID(row["id"]) for row in data["objects"]}

    assert returned_ids.isdisjoint(seed.other_container_ids)


@pytest.mark.asyncio
async def test_accepted_counter_is_limited_to_selected_document(
    async_client: AsyncClient,
) -> None:
    seed = await _seed_two_documents(async_client)

    data = await _get_sorting_objects(async_client, seed, by_document=True)

    assert sum(row["qty"] for row in data["lines"]) == seed.accepted_qty
