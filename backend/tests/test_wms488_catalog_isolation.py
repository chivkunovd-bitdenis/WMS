from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER, FULFILLMENT_STAFF
from app.db.session import SessionLocal
from app.models.fbs_order import MAPPING_STATUS_MAPPED, RESERVE_STATUS_RESERVED, FbsOrder
from app.models.ff_staff_permissions import FfStaffPermissions
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.seller_shop_delegation import SellerShopDelegation
from app.models.seller_staff_permissions import SellerStaffPermissions
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox
from app.services.tokens import create_access_token


async def _seed() -> tuple[dict[str, User], dict[str, Product], Warehouse]:
    async with SessionLocal() as session:
        tenants = [Tenant(name=name, slug=name) for name in ("avpack", "other-tenant")]
        session.add_all(tenants)
        await session.flush()
        sellers = {
            key: Seller(tenant_id=tenants[index].id, name=key)
            for key, index in (("a", 0), ("b", 0), ("foreign", 1))
        }
        session.add_all(sellers.values())
        await session.flush()
        users = {
            key: User(
                tenant_id=seller.tenant_id,
                seller_id=seller.id,
                email=f"{key}@merchant.ru",
                password_hash="unused",
                role=FULFILLMENT_SELLER,
            )
            for key, seller in sellers.items()
        }
        for key, role in (("admin", FULFILLMENT_ADMIN), ("staff", FULFILLMENT_STAFF)):
            users[key] = User(tenant_id=tenants[0].id, role=role, password_hash="unused")
        warehouse = Warehouse(tenant_id=tenants[0].id, name="Warehouse", code="WH")
        products = {
            key: Product(
                tenant_id=seller.tenant_id,
                seller_id=seller.id,
                name=f"Private {key}",
                sku_code=f"SKU-{key}",
                wb_barcode=f"WB-{key}",
            )
            for key, seller in sellers.items()
        }
        session.add_all([*users.values(), warehouse, *products.values()])
        await session.flush()
        for key, product in products.items():
            session.add(
                ProductMarketplaceLink(
                    tenant_id=product.tenant_id,
                    seller_id=product.seller_id,
                    product_id=product.id,
                    marketplace="ozon",
                    external_sku=f"OZ-{key}",
                    external_barcodes=[f"OZN-{key}"],
                )
            )
        session.add(
            WarehouseBox(
                tenant_id=tenants[0].id,
                warehouse_id=warehouse.id,
                internal_barcode="BOX",
                container_kind="box",
            )
        )
        session.add(
            FbsOrder(
                tenant_id=tenants[0].id,
                seller_id=sellers["b"].id,
                product_id=products["b"].id,
                wb_order_id=12345,
                sticker_barcode="ORDER",
                sticker_code="Private order",
                mapping_status=MAPPING_STATUS_MAPPED,
                reserve_status=RESERVE_STATUS_RESERVED,
                warehouse_id=warehouse.id,
                created_at_wb=datetime.now(UTC),
                deadline_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        await session.commit()
        return users, products, warehouse


def _headers(user: User, *, active_seller: uuid.UUID | None = None) -> dict[str, str]:
    token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        seller_id=active_seller,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("prefix", ["SKU", "WB", "OZN", "OZ"])
async def test_scan_returns_only_own_products_for_each_identifier(
    async_client: AsyncClient,
    prefix: str,
) -> None:
    users, products, _ = await _seed()
    for actor in ("a", "b", "foreign"):
        for target in ("a", "b", "foreign"):
            response = await async_client.get(
                "/operations/scan/resolve",
                headers=_headers(users[actor]),
                params={"code": f"{prefix}-{target}"},
            )
            if actor == target:
                assert response.status_code == 200, response.text
                assert response.json()["id"] == str(products[target].id)
            else:
                assert response.status_code == 404, response.text
                assert response.json()["detail"]["matches"] == []
                assert str(products[target].id) not in response.text
                assert products[target].name not in response.text


async def test_scan_filters_before_ambiguity_and_ozon_fallback(async_client: AsyncClient) -> None:
    users, products, warehouse = await _seed()
    async with SessionLocal() as session:
        own = await session.get(Product, products["a"].id)
        other = await session.get(Product, products["b"].id)
        assert own is not None and other is not None
        own.sku_code = other.sku_code = "SHARED"
        other.wb_barcode = "OZN-a"
        session.add(
            WarehouseBox(
                tenant_id=warehouse.tenant_id,
                warehouse_id=warehouse.id,
                internal_barcode="SHARED",
                container_kind="box",
            )
        )
        await session.commit()
    for code in ("SHARED", "OZN-a"):
        response = await async_client.get(
            "/operations/scan/resolve",
            headers=_headers(users["a"]),
            params={"code": code},
        )
        assert response.status_code == 200, response.text
        assert response.json()["id"] == str(products["a"].id)
    async with SessionLocal() as session:
        second = Product(
            tenant_id=users["a"].tenant_id,
            seller_id=users["a"].seller_id,
            name="Own second",
            sku_code="SECOND",
            wb_barcode="SHARED",
        )
        session.add(second)
        await session.commit()
    ambiguous = await async_client.get(
        "/operations/scan/resolve",
        headers=_headers(users["a"]),
        params={"code": "SHARED"},
    )
    assert ambiguous.status_code == 409, ambiguous.text
    assert {item["id"] for item in ambiguous.json()["detail"]["matches"]} == {
        str(products["a"].id),
        str(second.id),
    }
    assert "Private b" not in ambiguous.text
    assert "box" not in ambiguous.text


@pytest.mark.parametrize("code", ["BOX", "ORDER", "WH"])
async def test_seller_does_not_resolve_warehouse_objects(
    async_client: AsyncClient,
    code: str,
) -> None:
    users, _, warehouse = await _seed()
    for params in ({"code": code}, {"code": code, "warehouse_id": str(warehouse.id)}):
        response = await async_client.get(
            "/operations/scan/resolve",
            headers=_headers(users["a"]),
            params=params,
        )
        assert response.status_code == 404, response.text
        assert response.json()["detail"]["matches"] == []


@pytest.mark.parametrize(
    "permission", ["reception", "mp_shipments", "packaging", "cells", "inventory"]
)
async def test_authorized_ff_scans_keep_tenant_scope(
    async_client: AsyncClient,
    permission: str,
) -> None:
    users, _, _ = await _seed()
    async with SessionLocal() as session:
        session.add(FfStaffPermissions(user_id=users["staff"].id, **{f"can_{permission}": True}))
        await session.commit()
    for actor in ("admin", "staff"):
        for code in ("SKU-a", "WB-b", "OZN-b", "BOX", "ORDER", "WH"):
            response = await async_client.get(
                "/operations/scan/resolve",
                headers=_headers(users[actor]),
                params={"code": code},
            )
            assert response.status_code == 200, response.text
        foreign = await async_client.get(
            "/operations/scan/resolve",
            headers=_headers(users[actor]),
            params={"code": "SKU-foreign"},
        )
        assert foreign.status_code == 404


async def test_scan_requires_existing_catalog_permissions(async_client: AsyncClient) -> None:
    users, _, _ = await _seed()
    async with SessionLocal() as session:
        session.add(SellerStaffPermissions(user_id=users["a"].id, can_products=False))
        session.add(FfStaffPermissions(user_id=users["staff"].id, can_settings=True))
        await session.commit()
    for actor in ("a", "staff"):
        response = await async_client.get(
            "/operations/scan/resolve",
            headers=_headers(users[actor]),
            params={"code": "SKU-a"},
        )
        assert response.status_code == 403, response.text


async def test_scan_revalidates_active_shop_and_preserves_explicit_delegation(
    async_client: AsyncClient,
) -> None:
    users, products, _ = await _seed()
    headers = _headers(users["a"], active_seller=users["b"].seller_id)
    own = await async_client.get(
        "/operations/scan/resolve",
        headers=headers,
        params={"code": "SKU-a"},
    )
    assert own.status_code == 200
    foreign = await async_client.get(
        "/operations/scan/resolve",
        headers=headers,
        params={"code": "SKU-b"},
    )
    assert foreign.status_code == 404
    async with SessionLocal() as session:
        manager = await session.get(User, users["a"].id)
        assert manager is not None
        manager.can_manage_seller_shops = True
        delegation = SellerShopDelegation(
            user_id=manager.id,
            target_seller_id=users["b"].seller_id,
            enabled=True,
        )
        session.add(delegation)
        await session.commit()
    delegated = await async_client.get(
        "/operations/scan/resolve",
        headers=headers,
        params={"code": "SKU-b"},
    )
    assert delegated.status_code == 200, delegated.text
    assert delegated.json()["id"] == str(products["b"].id)
    async with SessionLocal() as session:
        stored = await session.get(SellerShopDelegation, delegation.id)
        assert stored is not None
        stored.enabled = False
        await session.commit()
    revoked = await async_client.get(
        "/operations/scan/resolve",
        headers=headers,
        params={"code": "SKU-b"},
    )
    assert revoked.status_code == 403


async def test_bulk_honest_sign_requires_products_permission_and_preserves_foreign_rows(
    async_client: AsyncClient,
) -> None:
    users, products, _ = await _seed()
    async with SessionLocal() as session:
        session.add(SellerStaffPermissions(user_id=users["a"].id, can_products=False))
        await session.commit()
    body = {
        "product_ids": [str(product.id) for product in products.values()],
        "requires_honest_sign": True,
    }
    denied = await async_client.patch(
        "/products/requires-honest-sign/bulk",
        headers=_headers(users["a"]),
        json=body,
    )
    assert denied.status_code == 403, denied.text
    async with SessionLocal() as session:
        rows = list((await session.scalars(select(Product))).all())
        assert all(not row.requires_honest_sign for row in rows)
        permission = await session.get(SellerStaffPermissions, users["a"].id)
        assert permission is not None
        permission.can_products = True
        await session.commit()
    accepted = await async_client.patch(
        "/products/requires-honest-sign/bulk",
        headers=_headers(users["a"]),
        json=body,
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["updated_count"] == 1
    async with SessionLocal() as session:
        rows = list((await session.scalars(select(Product))).all())
        assert {row.id for row in rows if row.requires_honest_sign} == {products["a"].id}


async def test_ozon_link_cannot_bypass_product_owner_or_link_owner(
    async_client: AsyncClient,
) -> None:
    users, products, _ = await _seed()
    async with SessionLocal() as session:
        # A bad legacy link must not authorize the product it points at.
        session.add(
            ProductMarketplaceLink(
                tenant_id=users["a"].tenant_id,
                seller_id=users["a"].seller_id,
                product_id=products["b"].id,
                marketplace="ozon",
                external_sku="BAD-OWNER",
                external_barcodes=["OZN-BAD-OWNER"],
            )
        )
        session.add(
            ProductMarketplaceLink(
                tenant_id=users["a"].tenant_id,
                seller_id=users["b"].seller_id,
                product_id=products["a"].id,
                marketplace="ozon",
                external_sku="BAD-LINK",
                external_barcodes=["OZN-BAD-LINK"],
            )
        )
        links = list((await session.scalars(select(ProductMarketplaceLink))).all())
        for link in links:
            if link.product_id in (products["a"].id, products["b"].id):
                link.external_barcodes = [*link.external_barcodes, "SHARED-OZON"]
        await session.commit()
    for code in ("BAD-OWNER", "OZN-BAD-OWNER", "BAD-LINK", "OZN-BAD-LINK"):
        response = await async_client.get(
            "/operations/scan/resolve",
            headers=_headers(users["a"]),
            params={"code": code},
        )
        assert response.status_code == 404, response.text
    own = await async_client.get(
        "/operations/scan/resolve",
        headers=_headers(users["a"]),
        params={"code": "SHARED-OZON"},
    )
    assert own.status_code == 200, own.text
    assert own.json()["id"] == str(products["a"].id)
    ff = await async_client.get(
        "/operations/scan/resolve",
        headers=_headers(users["admin"]),
        params={"code": "SHARED-OZON"},
    )
    assert ff.status_code == 409, ff.text
    assert {match["id"] for match in ff.json()["detail"]["matches"]} == {
        str(products["a"].id),
        str(products["b"].id),
    }
