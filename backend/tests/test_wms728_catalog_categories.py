"""WMS-728: real catalog API/SQL, multiple category values form a union.

The existing singular category remains backward compatible. Fixtures use
subjectName; Product.category is intentionally not the category source.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
import pytest_asyncio
from httpx import AsyncClient, AsyncHTTPTransport
from sqlalchemy import select

from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_STAFF
from app.db.session import SessionLocal
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.stock_direction import StockDirection
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services.sorting_location_service import SORTING_LOCATION_CODE
from app.services.tokens import create_access_token


@dataclass
class Catalog:
    client: AsyncClient
    headers: dict[str, str]
    denied_headers: dict[str, str]
    tenant: uuid.UUID
    sellers: list[uuid.UUID]
    locations: list[uuid.UUID]

    async def add(
        self,
        sku,
        quantity,
        *,
        seller=0,
        category="X",
        wb=True,
        ozon=False,
        enabled=False,
        limit=0,
        reserved=0,
    ):
        async with SessionLocal() as session:
            product = Product(
                tenant_id=self.tenant,
                seller_id=self.sellers[seller],
                name=sku,
                sku_code=sku,
                wb_nm_id=int(uuid.uuid4().int % 1_000_000_000) if wb else None,
                fbs_stock_sync_enabled=enabled,
                fbs_ozon_stock_sync_enabled=enabled,
                fbs_stock_limit=limit,
                fbs_units_mode=True,
            )
            session.add(product)
            await session.flush()
            if wb:
                session.add(
                    SellerWildberriesImportedCard(
                        tenant_id=self.tenant,
                        seller_id=product.seller_id,
                        nm_id=product.wb_nm_id,
                        raw_json={"subjectName": category},
                    )
                )
            if ozon:
                session.add(
                    ProductMarketplaceLink(
                        tenant_id=self.tenant,
                        seller_id=product.seller_id,
                        product_id=product.id,
                        marketplace="ozon",
                        external_sku=f"OZ-{sku}",
                        is_active=True,
                    )
                )
            if quantity is not None:
                session.add(
                    InventoryBalance(
                        tenant_id=self.tenant,
                        product_id=product.id,
                        storage_location_id=self.locations[0],
                        quantity=quantity,
                    )
                )
            if reserved:
                session.add(
                    StockDirection(
                        tenant_id=self.tenant,
                        product_id=product.id,
                        name="Test reserve",
                        quantity=reserved,
                    )
                )
            await session.commit()
            return str(product.id)

    async def page(self, **params):
        selected = params.pop("categories", None)
        query = list(params.items())
        if selected is not None:
            # D3 leaves the array parameter name to implementation. Prefer an
            # advertised category array; current code advertises only category,
            # where repeated query values expose the existing last-value bug.
            schema = (await self.client.get("/openapi.json")).json()
            parameters = schema["paths"]["/products/ff-catalog-page"]["get"].get("parameters", [])
            array_name = "category"
            for parameter in parameters:
                types = [parameter.get("schema", {}), *parameter.get("schema", {}).get("anyOf", [])]
                if "categor" in parameter["name"] and any(
                    value.get("type") == "array" for value in types
                ):
                    array_name = parameter["name"]
                    break
            query.extend((array_name, value) for value in selected)

        response = await self.client.get(
            "/products/ff-catalog-page",
            headers=self.headers,
            params=query,
        )
        assert response.status_code == 200, response.text
        return response.json()

    async def summary(self):
        response = await self.client.get(
            "/operations/inventory-balances/summary",
            headers=self.headers,
        )
        assert response.status_code == 200, response.text
        return {row["product_id"]: row for row in response.json()}


def headers(user):
    return {
        "Authorization": "Bearer "
        + create_access_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
            role=user.role,
        )
    }


@pytest_asyncio.fixture
async def catalog(async_client, monkeypatch):
    async def forbidden_external_http(*args, **kwargs):
        pytest.fail("Catalog GET must not call an external HTTP service")

    monkeypatch.setattr(AsyncHTTPTransport, "handle_async_request", forbidden_external_http)
    async with SessionLocal() as session:
        tenant = Tenant(name="WMS728 test", slug=f"wms728-{uuid.uuid4().hex}")
        session.add(tenant)
        await session.flush()
        admin = User(tenant_id=tenant.id, role=FULFILLMENT_ADMIN, password_hash="unused")
        denied = User(tenant_id=tenant.id, role=FULFILLMENT_STAFF, password_hash="unused")
        sellers = [Seller(tenant_id=tenant.id, name=name) for name in ["Seller A", "Seller B"]]
        warehouse = Warehouse(tenant_id=tenant.id, name="Test warehouse", code="TEST667")
        second_warehouse = Warehouse(
            tenant_id=tenant.id, name="Second warehouse", code="SECOND667", is_operational=False
        )
        session.add_all([admin, denied, *sellers, warehouse, second_warehouse])
        await session.flush()
        locations = [
            StorageLocation(
                tenant_id=tenant.id,
                warehouse_id=second_warehouse.id if code == "CONTAINER" else warehouse.id,
                code=code,
                barcode=f"728-{uuid.uuid4().hex}",
            )
            for code in ["CELL", SORTING_LOCATION_CODE, "CONTAINER"]
        ]
        session.add_all(locations)
        await session.commit()
        return Catalog(
            async_client,
            headers(admin),
            headers(denied),
            tenant.id,
            [s.id for s in sellers],
            [loc.id for loc in locations],
        )


async def test_c1_category_union_uses_subject_name_and_excludes_other_categories(catalog):
    a = await catalog.add("A-one", 2, category="A")
    b = await catalog.add("B-one", 3, category="B")
    await catalog.add("C-one", 4, category="C")
    result = await catalog.page(categories=["A", "B"])
    assert [item["id"] for item in result["items"]] == [a, b]
    assert result["total"] == 2
    assert set(result["categories"]) == {"A", "B", "C"}


async def test_c2_union_count_pagination_repeated_values_and_legacy_single_category(catalog):
    ids = [
        await catalog.add(f"{category}-{index}", 1, category=category)
        for category in ["A", "B", "C"]
        for index in range(3)
    ]
    legacy = await catalog.page(category="A")
    assert [item["id"] for item in legacy["items"]] == ids[:3]
    first = await catalog.page(categories=["A", "B", "A"], limit=4)
    second = await catalog.page(categories=["A", "B", "A"], limit=4, offset=4)
    assert first["total"] == second["total"] == 6
    combined = [item["id"] for item in first["items"] + second["items"]]
    assert combined == ids[:6]
    assert len(set(combined)) == 6
    assert await catalog.page(categories=["A", "B", "A"], limit=4) == first


async def test_c3_empty_category_set_includes_uncategorized_without_resetting_other_filters(
    catalog,
):
    a = await catalog.add("NEEDLE-A", 1, category="A")
    b = await catalog.add("NEEDLE-B", 1, category="B")
    none = await catalog.add("NEEDLE-none", 1, category=None)
    await catalog.add("other-A", 1, category="A")
    result = await catalog.page(categories=[], search="NEEDLE")
    assert [item["id"] for item in result["items"]] == [a, b, none]
    single = await catalog.page(category="A", search="NEEDLE")
    assert [item["id"] for item in single["items"]] == [a]


@pytest.mark.parametrize(
    "filters,expected_names",
    [
        ({"search": "NEEDLE"}, ["A-NEEDLE", "B-NEEDLE", "D-NEEDLE", "E-NEEDLE"]),
        ({"marketplace": "ozon"}, ["A-NEEDLE", "E-NEEDLE"]),
        ({"stock_publication": "none"}, ["A-NEEDLE", "D-NEEDLE", "E-NEEDLE"]),
        ({"has_stock": True}, ["A-NEEDLE", "B-NEEDLE", "E-NEEDLE"]),
        (
            {
                "search": "NEEDLE",
                "marketplace": "ozon",
                "stock_publication": "none",
                "has_stock": True,
            },
            ["A-NEEDLE", "E-NEEDLE"],
        ),
    ],
)
async def test_c4_category_union_intersects_filters_and_uses_actual_reserved_stock(
    catalog, filters, expected_names
):
    ids = {}
    ids["A-NEEDLE"] = await catalog.add("A-NEEDLE", 5, category="A", ozon=True, reserved=5)
    ids["B-NEEDLE"] = await catalog.add("B-NEEDLE", 3, category="B", enabled=True, limit=3)
    await catalog.add("C-other", 0, category="B", enabled=True)
    ids["D-NEEDLE"] = await catalog.add("D-NEEDLE", 0, category="A")
    ids["E-NEEDLE"] = await catalog.add("E-NEEDLE", 2, category="B", ozon=True)
    await catalog.add("F-NEEDLE", 7, category="C", ozon=True)
    result = await catalog.page(categories=["A", "B"], **filters)
    assert [item["id"] for item in result["items"]] == [ids[name] for name in expected_names]
    assert result["total"] == len(expected_names)
    assert result["scope_total"] == (3 if filters.get("marketplace") == "ozon" else 6)
    summary = await catalog.summary()
    assert summary[ids["A-NEEDLE"]]["quantity"] == summary[ids["A-NEEDLE"]]["reserved"] == 5
    assert summary[ids["A-NEEDLE"]]["available"] == 0


async def test_c7_union_keeps_tenant_seller_access_and_does_not_write_stock_or_publication(catalog):
    a = await catalog.add("A-mine", 5, category="A", ozon=True, enabled=True, limit=2)
    b = await catalog.add("B-mine", 2, category="B")
    other = await catalog.add("C-other-seller", 7, category="A", seller=1)
    async with SessionLocal() as session:
        tenant = Tenant(name="Other 728", slug=f"wms728-foreign-{uuid.uuid4().hex}")
        session.add(tenant)
        await session.flush()
        seller = Seller(tenant_id=tenant.id, name="Foreign")
        session.add(seller)
        await session.flush()
        product = Product(
            tenant_id=tenant.id,
            seller_id=seller.id,
            name="foreign",
            sku_code="FOREIGN",
            wb_nm_id=728991,
        )
        session.add(product)
        await session.flush()
        session.add(
            SellerWildberriesImportedCard(
                tenant_id=tenant.id,
                seller_id=seller.id,
                nm_id=728991,
                raw_json={"subjectName": "FOREIGN"},
            )
        )
        session.add(
            Product(
                tenant_id=tenant.id,
                seller_id=seller.id,
                name="foreign A",
                sku_code="FOREIGN-A",
                wb_nm_id=728992,
            )
        )
        session.add(
            SellerWildberriesImportedCard(
                tenant_id=tenant.id,
                seller_id=seller.id,
                nm_id=728992,
                raw_json={"subjectName": "A"},
            )
        )
        await session.commit()
        foreign_seller = str(seller.id)
    before = await catalog.summary()
    async with SessionLocal() as session:
        original = await session.get(Product, uuid.UUID(a))
        publication = (
            original.fbs_stock_sync_enabled,
            original.fbs_ozon_stock_sync_enabled,
            original.fbs_stock_limit,
        )
    result = await catalog.page(categories=["A", "B"], seller_id=str(catalog.sellers[0]))
    assert "FOREIGN" not in result["categories"]
    assert other not in [item["id"] for item in result["items"]]
    foreign = await catalog.client.get(
        "/products/ff-catalog-page",
        headers=catalog.headers,
        params=[("category", "A"), ("category", "B"), ("seller_id", foreign_seller)],
    )
    assert foreign.status_code in (200, 403, 404)
    if foreign.status_code == 200:
        assert foreign.json()["items"] == []
        assert foreign.json()["categories"] == []
    denied = await catalog.client.get(
        "/products/ff-catalog-page",
        headers=catalog.denied_headers,
        params=[("category", "A"), ("category", "B")],
    )
    assert denied.status_code == 403
    assert await catalog.summary() == before
    async with SessionLocal() as session:
        original = await session.get(Product, uuid.UUID(a))
        assert (
            original.fbs_stock_sync_enabled,
            original.fbs_ozon_stock_sync_enabled,
            original.fbs_stock_limit,
        ) == publication
    assert [item["id"] for item in result["items"]] == [a, b]


async def test_c7_legacy_seller_single_category_grouping_and_publication_are_preserved(catalog):
    from app.core.roles import FULFILLMENT_SELLER
    from app.models.seller_staff_permissions import SellerStaffPermissions

    first = await catalog.add("A-first", 5, category="A", ozon=True, enabled=True, limit=2)
    second = await catalog.add("A-second", 2, category="A")
    await catalog.add("B-other-category", 3, category="B")
    await catalog.add("C-other-seller", 4, category="A", seller=1)
    async with SessionLocal() as session:
        user = User(
            tenant_id=catalog.tenant,
            seller_id=catalog.sellers[0],
            role=FULFILLMENT_SELLER,
            password_hash="test-only",
        )
        session.add(user)
        await session.flush()
        session.add(SellerStaffPermissions(user_id=user.id, can_products=True))
        await session.commit()
        seller_headers = headers(user)
        before = [
            (p.id, p.fbs_stock_sync_enabled, p.fbs_ozon_stock_sync_enabled, p.fbs_stock_limit)
            for p in (
                await session.scalars(
                    select(Product).where(Product.tenant_id == catalog.tenant).order_by(Product.id)
                )
            ).all()
        ]
    balance_before = await catalog.summary()
    for grouped in [False, True]:
        params = {"category": "A"}
        if grouped:
            params["group_by"] = "category_article_size"
        response = await catalog.client.get(
            "/seller-catalog/page", headers=seller_headers, params=params
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2
        assert all(item["wb_subject_name"] == "A" for item in body["items"])
        assert {item["id"] for item in body["items"]} == {first, second}
        assert body["scope_total"] == 3
        repeated = await catalog.client.get(
            "/seller-catalog/page", headers=seller_headers, params=params
        )
        assert repeated.json() == body
    assert await catalog.summary() == balance_before
    async with SessionLocal() as session:
        after = [
            (p.id, p.fbs_stock_sync_enabled, p.fbs_ozon_stock_sync_enabled, p.fbs_stock_limit)
            for p in (
                await session.scalars(
                    select(Product).where(Product.tenant_id == catalog.tenant).order_by(Product.id)
                )
            ).all()
        ]
        assert after == before
