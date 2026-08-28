"""Readonly product availability for marketplace unload pickers."""

from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.inventory_reservation import InventoryReservation
from app.models.marketplace_unload import MarketplaceUnloadLine, MarketplaceUnloadRequest
from app.models.marketplace_unload_reservation import MarketplaceUnloadReservation
from app.models.outbound_shipment import OutboundShipmentLine, OutboundShipmentRequest
from app.models.product import Product
from app.services import inventory_service, stock_direction_service
from app.services.sorting_location_service import get_or_create_sorting_location
from tests.inventory_actor_helpers import resolve_test_actor_user_id


async def _seller_headers(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    seller_id: str,
) -> dict[str, str]:
    email = f"availability-{time.time_ns()}@example.com"
    account = await async_client.post(
        "/auth/seller-accounts",
        headers=admin_headers,
        json={"seller_id": seller_id, "email": email, "password": "password123"},
    )
    assert account.status_code == 201, account.text
    login = await async_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_mp_availability_includes_sorting_reserves_and_isolation(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    register = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "MP availability",
            "slug": f"mp-availability-{suffix}",
            "admin_email": f"mp-availability-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert register.status_code == 200, register.text
    admin_headers = {
        "Authorization": f"Bearer {register.json()['access_token']}"
    }
    warehouse = await async_client.post(
        "/warehouses",
        headers=admin_headers,
        json={"name": "Warehouse", "code": f"mp-av-{suffix[-8:]}"},
    )
    assert warehouse.status_code == 200, warehouse.text
    warehouse_id = str(warehouse.json()["id"])
    seller_a = await async_client.post(
        "/sellers", headers=admin_headers, json={"name": "Seller A"}
    )
    seller_b = await async_client.post(
        "/sellers", headers=admin_headers, json={"name": "Seller B"}
    )
    seller_a_id = str(seller_a.json()["id"])
    seller_b_id = str(seller_b.json()["id"])
    product_a = await async_client.post(
        "/products",
        headers=admin_headers,
        json={
            "name": "Sorting only",
            "sku_code": f"SORT-{suffix}",
            "seller_id": seller_a_id,
        },
    )
    product_b = await async_client.post(
        "/products",
        headers=admin_headers,
        json={
            "name": "Other seller",
            "sku_code": f"OTHER-{suffix}",
            "seller_id": seller_b_id,
        },
    )
    assert product_a.status_code == 200, product_a.text
    assert product_b.status_code == 200, product_b.text
    product_a_id = uuid.UUID(str(product_a.json()["id"]))
    product_b_id = uuid.UUID(str(product_b.json()["id"]))
    warehouse_uuid = uuid.UUID(warehouse_id)
    seller_a_uuid = uuid.UUID(seller_a_id)

    async with SessionLocal() as session:
        product = await session.get(Product, product_a_id)
        assert product is not None
        tenant_id = product.tenant_id
        sorting = await get_or_create_sorting_location(
            session, tenant_id, warehouse_uuid
        )
        for product_id in (product_a_id, product_b_id):
            await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=tenant_id,
                product_id=product_id,
                storage_location_id=sorting.id,
                quantity_delta=10,
                movement_type="inbound_intake",
                actor_user_id=await resolve_test_actor_user_id(session, tenant_id),
            )

        outbound = OutboundShipmentRequest(
            tenant_id=tenant_id,
            warehouse_id=warehouse_uuid,
            seller_id=seller_a_uuid,
            status="submitted",
        )
        session.add(outbound)
        await session.flush()
        outbound_line = OutboundShipmentLine(
            request_id=outbound.id,
            product_id=product_a_id,
            quantity=2,
            shipped_qty=0,
            storage_location_id=None,
        )
        session.add(outbound_line)
        await session.flush()
        session.add(
            InventoryReservation(
                tenant_id=tenant_id,
                outbound_shipment_line_id=outbound_line.id,
                product_id=product_a_id,
                warehouse_id=warehouse_uuid,
                storage_location_id=None,
                quantity=2,
            )
        )

        unload = MarketplaceUnloadRequest(
            tenant_id=tenant_id,
            warehouse_id=warehouse_uuid,
            seller_id=seller_a_uuid,
            status="collecting",
            ff_modified=False,
            has_discrepancy=False,
        )
        session.add(unload)
        await session.flush()
        unload_line = MarketplaceUnloadLine(
            request_id=unload.id,
            product_id=product_a_id,
            quantity=3,
        )
        session.add(unload_line)
        await session.flush()
        session.add(
            MarketplaceUnloadReservation(
                tenant_id=tenant_id,
                marketplace_unload_line_id=unload_line.id,
                product_id=product_a_id,
                warehouse_id=warehouse_uuid,
                quantity=3,
            )
        )
        unload_id = str(unload.id)

        other_unload = MarketplaceUnloadRequest(
            tenant_id=tenant_id,
            warehouse_id=warehouse_uuid,
            seller_id=seller_a_uuid,
            status="confirmed",
            ff_modified=False,
            has_discrepancy=False,
        )
        session.add(other_unload)
        await session.flush()
        other_line = MarketplaceUnloadLine(
            request_id=other_unload.id,
            product_id=product_a_id,
            quantity=1,
        )
        session.add(other_line)
        await session.flush()
        session.add(
            MarketplaceUnloadReservation(
                tenant_id=tenant_id,
                marketplace_unload_line_id=other_line.id,
                product_id=product_a_id,
                warehouse_id=warehouse_uuid,
                quantity=1,
            )
        )
        await session.commit()

    global_summary = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=admin_headers,
        params={"warehouse_id": warehouse_id, "seller_id": seller_a_id},
    )
    assert global_summary.status_code == 200, global_summary.text
    assert global_summary.json()[0]["quantity_in_sorting"] == 10
    assert global_summary.json()[0]["available"] == 0

    admin_available = await async_client.get(
        "/operations/marketplace-unload-requests/available-products",
        headers=admin_headers,
        params={"warehouse_id": warehouse_id, "seller_id": seller_a_id},
    )
    assert admin_available.status_code == 200, admin_available.text
    assert admin_available.json() == [
        {
            "product_id": str(product_a_id),
            "sku_code": f"SORT-{suffix}",
            "product_name": "Sorting only",
            "available": 4,
        }
    ]

    own_request_available = await async_client.get(
        "/operations/marketplace-unload-requests/available-products",
        headers=admin_headers,
        params={
            "warehouse_id": warehouse_id,
            "seller_id": seller_a_id,
            "exclude_request_id": unload_id,
        },
    )
    assert own_request_available.status_code == 200
    # Only current collecting reserve (3) is excluded; confirmed reserve (1) remains.
    assert own_request_available.json()[0]["available"] == 7

    seller_headers = await _seller_headers(
        async_client, admin_headers, seller_a_id
    )
    seller_available = await async_client.get(
        "/operations/marketplace-unload-requests/available-products",
        headers=seller_headers,
        params={"warehouse_id": warehouse_id},
    )
    assert seller_available.status_code == 200, seller_available.text
    assert [row["product_id"] for row in seller_available.json()] == [
        str(product_a_id)
    ]
    forbidden_seller_scope = await async_client.get(
        "/operations/marketplace-unload-requests/available-products",
        headers=seller_headers,
        params={"warehouse_id": warehouse_id, "seller_id": seller_b_id},
    )
    assert forbidden_seller_scope.status_code == 404

    other_register = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Other tenant",
            "slug": f"other-tenant-{suffix}",
            "admin_email": f"other-tenant-{suffix}@example.com",
            "password": "password123",
        },
    )
    other_headers = {
        "Authorization": f"Bearer {other_register.json()['access_token']}"
    }
    isolated = await async_client.get(
        "/operations/marketplace-unload-requests/available-products",
        headers=other_headers,
        params={"warehouse_id": warehouse_id, "seller_id": seller_a_id},
    )
    assert isolated.status_code == 404


@pytest.mark.asyncio
async def test_mp_availability_uses_free_fbo_after_directions_and_active_reserves(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    register = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "MP free FBO",
            "slug": f"mp-free-fbo-{suffix}",
            "admin_email": f"mp-free-fbo-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert register.status_code == 200, register.text
    admin_headers = {"Authorization": f"Bearer {register.json()['access_token']}"}
    warehouse = await async_client.post(
        "/warehouses",
        headers=admin_headers,
        json={"name": "FBO Warehouse", "code": f"fbo-{suffix[-8:]}"},
    )
    assert warehouse.status_code == 200, warehouse.text
    seller = await async_client.post(
        "/sellers", headers=admin_headers, json={"name": "FBO Seller"}
    )
    assert seller.status_code == 201, seller.text
    product = await async_client.post(
        "/products",
        headers=admin_headers,
        json={
            "name": "FBO Product",
            "sku_code": f"FBO-{suffix}",
            "seller_id": seller.json()["id"],
        },
    )
    assert product.status_code == 200, product.text
    location = await async_client.post(
        f"/warehouses/{warehouse.json()['id']}/locations",
        headers=admin_headers,
        json={"code": f"FBO-A-{suffix[-6:]}"},
    )
    assert location.status_code == 200, location.text

    warehouse_id = uuid.UUID(warehouse.json()["id"])
    seller_id = uuid.UUID(seller.json()["id"])
    product_id = uuid.UUID(product.json()["id"])
    location_id = uuid.UUID(location.json()["id"])

    async with SessionLocal() as session:
        db_product = await session.get(Product, product_id)
        assert db_product is not None
        tenant_id = db_product.tenant_id
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=location_id,
            quantity_delta=1000,
            movement_type="inbound_intake",
            actor_user_id=await resolve_test_actor_user_id(session, tenant_id),
        )
        await session.commit()
        await stock_direction_service.create_stock_direction(
            session,
            tenant_id,
            product_id,
            name="FBS WB",
            quantity=200,
            is_fbs=True,
        )
        await stock_direction_service.create_stock_direction(
            session,
            tenant_id,
            product_id,
            name="Наборы сентябрь",
            quantity=300,
            is_fbs=False,
        )

        other_unload = MarketplaceUnloadRequest(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            seller_id=seller_id,
            status="submitted",
            ff_modified=False,
            has_discrepancy=False,
        )
        session.add(other_unload)
        await session.flush()
        other_line = MarketplaceUnloadLine(
            request_id=other_unload.id,
            product_id=product_id,
            quantity=100,
        )
        session.add(other_line)
        await session.flush()
        session.add(
            MarketplaceUnloadReservation(
                tenant_id=tenant_id,
                marketplace_unload_line_id=other_line.id,
                product_id=product_id,
                warehouse_id=warehouse_id,
                quantity=100,
            )
        )
        await session.commit()

    summary = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=admin_headers,
        params={"warehouse_id": str(warehouse_id), "seller_id": str(seller_id)},
    )
    assert summary.status_code == 200, summary.text
    summary_row = next(row for row in summary.json() if row["product_id"] == str(product_id))
    # The FBS flag on directions is gone (FBS-02): every direction is stored
    # as a plain reserve now, regardless of the is_fbs argument passed above.
    # So quantity_fbs is always 0, and both directions (200 + 300) land in
    # quantity_reserved_directions.
    assert summary_row["quantity"] == 1000
    assert summary_row["quantity_fbs"] == 0
    assert summary_row["quantity_reserved_directions"] == 500
    assert summary_row["quantity_free_fbo"] == 500
    assert summary_row["available"] == 400

    available = await async_client.get(
        "/operations/marketplace-unload-requests/available-products",
        headers=admin_headers,
        params={"warehouse_id": str(warehouse_id), "seller_id": str(seller_id)},
    )
    assert available.status_code == 200, available.text
    assert available.json() == [
        {
            "product_id": str(product_id),
            "sku_code": f"FBO-{suffix}",
            "product_name": "FBO Product",
            "available": 400,
        }
    ]

    unload = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=admin_headers,
        json={"warehouse_id": str(warehouse_id), "seller_id": str(seller_id)},
    )
    assert unload.status_code == 201, unload.text
    unload_id = unload.json()["id"]
    too_much = await async_client.post(
        f"/operations/marketplace-unload-requests/{unload_id}/lines",
        headers=admin_headers,
        json={"product_id": str(product_id), "quantity": 401},
    )
    assert too_much.status_code == 422
    assert too_much.json()["detail"]["code"] == "insufficient_free_fbo"

    ok = await async_client.post(
        f"/operations/marketplace-unload-requests/{unload_id}/lines",
        headers=admin_headers,
        json={"product_id": str(product_id), "quantity": 400},
    )
    assert ok.status_code == 201, ok.text
