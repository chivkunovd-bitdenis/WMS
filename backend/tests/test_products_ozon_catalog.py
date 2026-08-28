from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.marketplace_account import MarketplaceAccount
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.services.integration_fernet import encrypt_secret


async def _register_admin(async_client: AsyncClient, suffix: str) -> dict[str, str]:
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Ozon catalog {suffix}",
            "slug": f"ozon-catalog-{suffix}",
            "admin_email": f"ozon-catalog-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    return {"Authorization": f"Bearer {registered.json()['access_token']}"}


async def _create_product(
    async_client: AsyncClient,
    headers: dict[str, str],
    *,
    name: str,
    sku_code: str,
    seller_id: str,
    ozon_sku: str | None = None,
    ozon_offer_id: str | None = None,
    wb_vendor_code: str | None = None,
) -> dict[str, object]:
    response = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": name,
            "sku_code": sku_code,
            "seller_id": seller_id,
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "wb_vendor_code": wb_vendor_code,
        },
    )
    assert response.status_code == 200, response.text
    product = response.json()
    if ozon_sku or ozon_offer_id:
        linked = await async_client.patch(
            f"/products/{product['id']}/ozon-link",
            headers=headers,
            json={"ozon_sku": ozon_sku, "ozon_offer_id": ozon_offer_id},
        )
        assert linked.status_code == 200, linked.text
        product = linked.json()
    return product


async def _create_seller_account(
    async_client: AsyncClient,
    headers: dict[str, str],
    *,
    seller_id: str,
    email: str,
) -> dict[str, str]:
    account = await async_client.post(
        "/auth/seller-accounts",
        headers=headers,
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
async def test_products_search_and_marketplace_filter_include_ozon_links(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, suffix)
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Seller Ozon"})
    assert seller.status_code == 201, seller.text
    seller_id = seller.json()["id"]

    linked = await _create_product(
        async_client,
        headers,
        name="Ozon linked product",
        sku_code=f"LOCAL-{suffix}",
        seller_id=seller_id,
        ozon_sku=f"OZON-SKU-{suffix}",
        ozon_offer_id=f"OZON-OFFER-{suffix}",
        wb_vendor_code=f"WB-{suffix}",
    )
    unlinked = await _create_product(
        async_client,
        headers,
        name="Product without marketplace mapping",
        sku_code=f"UNLINKED-{suffix}",
        seller_id=seller_id,
    )

    by_ozon_sku = await async_client.get(
        f"/products?search=OZON-SKU-{suffix}", headers=headers
    )
    assert by_ozon_sku.status_code == 200, by_ozon_sku.text
    assert [row["id"] for row in by_ozon_sku.json()] == [linked["id"]]
    assert by_ozon_sku.json()[0]["ozon_offer_id"] == f"OZON-OFFER-{suffix}"

    by_ozon_offer = await async_client.get(
        f"/products?search=OZON-OFFER-{suffix}", headers=headers
    )
    assert by_ozon_offer.status_code == 200, by_ozon_offer.text
    assert [row["id"] for row in by_ozon_offer.json()] == [linked["id"]]

    ozon_only = await async_client.get("/products?marketplace=ozon", headers=headers)
    assert ozon_only.status_code == 200, ozon_only.text
    assert {row["id"] for row in ozon_only.json()} == {linked["id"]}

    wb_only = await async_client.get("/products?marketplace=wildberries", headers=headers)
    assert wb_only.status_code == 200, wb_only.text
    assert {row["id"] for row in wb_only.json()} == {linked["id"]}

    all_products = await async_client.get("/products", headers=headers)
    assert all_products.status_code == 200, all_products.text
    unlinked_row = next(row for row in all_products.json() if row["id"] == unlinked["id"])
    assert unlinked_row["ozon_sku"] is None
    assert unlinked_row["ozon_offer_id"] is None


@pytest.mark.asyncio
async def test_ff_catalog_page_searches_ozon_sku_and_offer_id(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, f"page-search-{suffix}")
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Seller"})
    assert seller.status_code == 201, seller.text
    linked = await _create_product(
        async_client,
        headers,
        name="Ozon searchable product",
        sku_code=f"LOCAL-PAGE-{suffix}",
        seller_id=seller.json()["id"],
        ozon_sku=f"OZON-PAGE-SKU-{suffix}",
        ozon_offer_id=f"OZON-PAGE-OFFER-{suffix}",
    )

    for search in (f"OZON-PAGE-SKU-{suffix}", f"OZON-PAGE-OFFER-{suffix}"):
        response = await async_client.get(
            "/products/ff-catalog-page",
            headers=headers,
            params={"search": search},
        )

        assert response.status_code == 200, response.text
        page = response.json()
        assert [row["id"] for row in page["items"]] == [linked["id"]]
        assert page["total"] == 1


@pytest.mark.asyncio
async def test_ff_catalog_page_ozon_search_keeps_unique_rows_and_total(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, f"page-total-{suffix}")
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Seller"})
    assert seller.status_code == 201, seller.text
    seller_id = seller.json()["id"]
    linked = await _create_product(
        async_client,
        headers,
        name="Product with multiple marketplace links",
        sku_code=f"MULTI-LINK-{suffix}",
        seller_id=seller_id,
        ozon_sku=f"OZON-MULTI-{suffix}",
    )
    await _create_product(
        async_client,
        headers,
        name="Unmatched product",
        sku_code=f"UNMATCHED-{suffix}",
        seller_id=seller_id,
    )

    async with SessionLocal() as session:
        seller_row = await session.get(Seller, uuid.UUID(seller_id))
        assert seller_row is not None
        session.add(
            ProductMarketplaceLink(
                tenant_id=seller_row.tenant_id,
                seller_id=seller_row.id,
                product_id=uuid.UUID(str(linked["id"])),
                marketplace="wildberries",
                external_sku=f"WB-MULTI-{suffix}",
            )
        )
        await session.commit()

    response = await async_client.get(
        "/products/ff-catalog-page",
        headers=headers,
        params={"search": f"OZON-MULTI-{suffix}"},
    )

    assert response.status_code == 200, response.text
    page = response.json()
    assert [row["id"] for row in page["items"]] == [linked["id"]]
    assert page["total"] == 1
    assert page["scope_total"] == 2


@pytest.mark.asyncio
async def test_ozon_catalog_links_do_not_cross_seller_or_tenant_boundaries(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    owner_headers = await _register_admin(async_client, f"owner-{suffix}")
    seller_a = await async_client.post("/sellers", headers=owner_headers, json={"name": "A"})
    seller_b = await async_client.post("/sellers", headers=owner_headers, json={"name": "B"})
    assert seller_a.status_code == seller_b.status_code == 201
    seller_a_id = seller_a.json()["id"]
    seller_b_id = seller_b.json()["id"]
    product_a = await _create_product(
        async_client,
        owner_headers,
        name="Seller A Ozon",
        sku_code=f"A-{suffix}",
        seller_id=seller_a_id,
        ozon_sku=f"ISOLATED-{suffix}",
    )
    await _create_product(
        async_client,
        owner_headers,
        name="Seller B Ozon",
        sku_code=f"B-{suffix}",
        seller_id=seller_b_id,
        ozon_sku=f"ISOLATED-{suffix}",
    )

    seller_account = await async_client.post(
        "/auth/seller-accounts",
        headers=owner_headers,
        json={
            "seller_id": seller_a_id,
            "email": f"seller-a-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert seller_account.status_code in (200, 201), seller_account.text
    login = await async_client.post(
        "/auth/login",
        json={"email": f"seller-a-{suffix}@example.com", "password": "password123"},
    )
    assert login.status_code == 200, login.text
    seller_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    seller_products = await async_client.get(
        f"/products?search=ISOLATED-{suffix}", headers=seller_headers
    )
    assert seller_products.status_code == 200, seller_products.text
    assert [row["id"] for row in seller_products.json()] == [product_a["id"]]

    other_headers = await _register_admin(async_client, f"other-{suffix}")
    other_products = await async_client.get(
        f"/products?search=ISOLATED-{suffix}", headers=other_headers
    )
    assert other_products.status_code == 200, other_products.text
    assert other_products.json() == []


@pytest.mark.asyncio
async def test_warehouse_ozon_link_requires_seller_with_explicit_422(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, suffix)

    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Existing SKU without seller",
            "sku_code": f"EXISTING-NO-SELLER-{suffix}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
        },
    )
    assert product.status_code == 200, product.text
    update = await async_client.patch(
        f"/products/{product.json()['id']}/ozon-link",
        headers=headers,
        json={"ozon_sku": f"OZON-UPDATE-{suffix}"},
    )
    assert update.status_code == 422, update.text
    assert update.json()["detail"] == "ozon_link_requires_seller"


@pytest.mark.asyncio
async def test_existing_product_ozon_link_update_is_warehouse_only_and_tenant_scoped(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    owner_headers = await _register_admin(async_client, f"update-{suffix}")
    seller_a = await async_client.post("/sellers", headers=owner_headers, json={"name": "A"})
    seller_b = await async_client.post("/sellers", headers=owner_headers, json={"name": "B"})
    assert seller_a.status_code == seller_b.status_code == 201
    seller_a_id = seller_a.json()["id"]
    seller_b_id = seller_b.json()["id"]
    product = await _create_product(
        async_client,
        owner_headers,
        name="Existing WMS SKU",
        sku_code=f"EXISTING-{suffix}",
        seller_id=seller_a_id,
    )
    seller_a_headers = await _create_seller_account(
        async_client,
        owner_headers,
        seller_id=seller_a_id,
        email=f"update-a-{suffix}@example.com",
    )
    seller_b_headers = await _create_seller_account(
        async_client,
        owner_headers,
        seller_id=seller_b_id,
        email=f"update-b-{suffix}@example.com",
    )

    seller_attempt = await async_client.patch(
        f"/products/{product['id']}/ozon-link",
        headers=seller_a_headers,
        json={"ozon_sku": f"OZON-1-{suffix}", "ozon_offer_id": f"OFFER-1-{suffix}"},
    )
    assert seller_attempt.status_code == 403, seller_attempt.text

    added = await async_client.patch(
        f"/products/{product['id']}/ozon-link",
        headers=owner_headers,
        json={"ozon_sku": f"OZON-1-{suffix}", "ozon_offer_id": f"OFFER-1-{suffix}"},
    )
    assert added.status_code == 200, added.text
    assert added.json()["ozon_sku"] == f"OZON-1-{suffix}"

    changed = await async_client.patch(
        f"/products/{product['id']}/ozon-link",
        headers=owner_headers,
        json={"ozon_sku": f"OZON-2-{suffix}", "ozon_offer_id": f"OFFER-2-{suffix}"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["ozon_offer_id"] == f"OFFER-2-{suffix}"
    listed = await async_client.get(
        f"/products?search=OZON-2-{suffix}", headers=owner_headers
    )
    assert [row["id"] for row in listed.json()] == [product["id"]]

    wrong_seller = await async_client.patch(
        f"/products/{product['id']}/ozon-link",
        headers=seller_b_headers,
        json={"ozon_sku": "FORBIDDEN"},
    )
    assert wrong_seller.status_code == 403, wrong_seller.text

    other_headers = await _register_admin(async_client, f"update-other-{suffix}")
    other_tenant = await async_client.patch(
        f"/products/{product['id']}/ozon-link",
        headers=other_headers,
        json={"ozon_sku": "FOREIGN"},
    )
    assert other_tenant.status_code == 404, other_tenant.text


@pytest.mark.asyncio
async def test_ozon_sku_cannot_be_linked_to_two_products(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, f"duplicate-{suffix}")
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Seller"})
    assert seller.status_code == 201, seller.text
    seller_id = seller.json()["id"]
    first = await _create_product(
        async_client,
        headers,
        name="First",
        sku_code=f"FIRST-{suffix}",
        seller_id=seller_id,
    )
    second = await _create_product(
        async_client,
        headers,
        name="Second",
        sku_code=f"SECOND-{suffix}",
        seller_id=seller_id,
    )
    ozon_sku = f"OZON-DUPLICATE-{suffix}"
    first_link = await async_client.patch(
        f"/products/{first['id']}/ozon-link",
        headers=headers,
        json={"ozon_sku": ozon_sku},
    )
    second_link = await async_client.patch(
        f"/products/{second['id']}/ozon-link",
        headers=headers,
        json={"ozon_sku": ozon_sku},
    )

    assert first_link.status_code == 200, first_link.text
    assert second_link.status_code == 409, second_link.text
    assert second_link.json()["detail"] == "ozon_sku_taken"


@pytest.mark.asyncio
async def test_seller_catalog_keeps_ozon_marker_without_connected_account(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, f"seller-view-{suffix}")
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Seller"})
    assert seller.status_code == 201, seller.text
    seller_id = seller.json()["id"]
    product = await _create_product(
        async_client,
        headers,
        name="Visible Ozon link",
        sku_code=f"VISIBLE-{suffix}",
        seller_id=seller_id,
        ozon_sku=f"OZON-VISIBLE-{suffix}",
        ozon_offer_id=f"OFFER-VISIBLE-{suffix}",
    )
    seller_headers = await _create_seller_account(
        async_client,
        headers,
        seller_id=seller_id,
        email=f"seller-view-{suffix}@example.com",
    )

    response = await async_client.get("/products/wb-catalog", headers=seller_headers)

    assert response.status_code == 200, response.text
    row = next(item for item in response.json() if item["id"] == product["id"])
    assert row["ozon_sku"] == f"OZON-VISIBLE-{suffix}"
    assert row["ozon_offer_id"] == f"OFFER-VISIBLE-{suffix}"
    assert row["wb_connected"] is False
    assert row["ozon_connected"] is False

    async with SessionLocal() as session:
        connected_seller = await session.get(Seller, uuid.UUID(seller_id))
        assert connected_seller is not None
        session.add_all(
            [
                SellerWildberriesCredentials(
                    seller_id=connected_seller.id,
                    marketplace_token_encrypted=encrypt_secret("wb-token"),
                ),
                MarketplaceAccount(
                    tenant_id=connected_seller.tenant_id,
                    seller_id=connected_seller.id,
                    marketplace="ozon",
                    account_slot="primary",
                    is_active=True,
                    validation_status="valid",
                ),
            ]
        )
        await session.commit()

    connected_response = await async_client.get("/products/wb-catalog", headers=seller_headers)
    assert connected_response.status_code == 200, connected_response.text
    connected_row = next(
        item for item in connected_response.json() if item["id"] == product["id"]
    )
    assert connected_row["wb_connected"] is True
    assert connected_row["ozon_connected"] is True


@pytest.mark.asyncio
async def test_seller_catalog_status_marks_only_connected_ozon_account(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, f"status-{suffix}")
    connected = await async_client.post(
        "/sellers", headers=headers, json={"name": "Ozon connected"}
    )
    wb_only = await async_client.post(
        "/sellers", headers=headers, json={"name": "WB only"}
    )
    assert connected.status_code == wb_only.status_code == 201

    async with SessionLocal() as session:
        connected_seller = await session.get(Seller, uuid.UUID(connected.json()["id"]))
        assert connected_seller is not None
        session.add(
            MarketplaceAccount(
                tenant_id=connected_seller.tenant_id,
                seller_id=uuid.UUID(connected.json()["id"]),
                marketplace="ozon",
                account_slot="primary",
                is_active=True,
                validation_status="valid",
            )
        )
        await session.commit()

    response = await async_client.get("/sellers", headers=headers)
    assert response.status_code == 200, response.text
    by_id = {row["id"]: row for row in response.json()}
    assert by_id[connected.json()["id"]]["ozon_connected"] is True
    assert by_id[wb_only.json()["id"]]["ozon_connected"] is False
