"""WMS-667 C1-C7: real HTTP routes and isolated DB, no stock/filter mocks.

Wire contract: has_stock=true selects displayed summary quantity > 0;
false/omitted leaves the existing catalog selection intact.
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
        response = await self.client.get(
            "/products/ff-catalog-page",
            headers=self.headers,
            params=params,
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
        tenant = Tenant(name="WMS667 test", slug=f"wms667-{uuid.uuid4().hex}")
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
                barcode=f"667-{uuid.uuid4().hex}",
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


def assert_selection(page, expected):
    assert [row["id"] for row in page["items"]] == expected
    assert page["total"] == len(expected)


async def test_c1_displayed_on_hand_strictly_positive(catalog):
    ids = [
        await catalog.add(sku, qty)
        for sku, qty in [("A-positive", 3), ("B-zero", 4), ("C-missing", None), ("D-negative", -5)]
    ]
    # Sum, not existence of a positive balance row: 4-4=0 and -5+3=-2.
    async with SessionLocal() as session:
        session.add_all(
            [
                InventoryBalance(
                    tenant_id=catalog.tenant,
                    product_id=uuid.UUID(pid),
                    storage_location_id=catalog.locations[1],
                    quantity=quantity,
                )
                for pid, quantity in [(ids[1], -4), (ids[3], 3)]
            ]
        )
        await session.commit()
    summary = await catalog.summary()
    assert [summary.get(pid, {}).get("quantity", 0) for pid in ids] == [3, 0, 0, -2]
    assert_selection(await catalog.page(), ids)  # existing unfiltered baseline
    assert_selection(await catalog.page(has_stock=False), ids)
    assert_selection(await catalog.page(has_stock=True), [ids[0]])


@pytest.mark.parametrize("reserved", [5, 7])
async def test_c2_positive_fully_reserved_is_included(catalog, reserved):
    positive = await catalog.add("A-positive-reserved", 5, reserved=reserved)
    zero = await catalog.add("B-zero-reserved", 0, reserved=2)
    summary = await catalog.summary()
    assert summary[positive]["quantity"] == 5
    assert summary[positive]["reserved"] == reserved
    assert summary[positive]["available"] == 5 - reserved
    assert summary[zero]["quantity"] == 0
    assert summary[zero]["available"] == -2
    assert_selection(await catalog.page(has_stock=True), [positive])


async def test_c3_filter_before_count_and_pagination(catalog):
    ids = [
        await catalog.add(sku, qty)
        for sku, qty in [("A", 0), ("B", 0), ("C", 4), ("D", 2), ("E", 0)]
    ]
    baseline = await catalog.page(limit=2)
    assert [row["id"] for row in baseline["items"]] == ids[:2]
    assert baseline["total"] == baseline["scope_total"] == 5
    page = await catalog.page(has_stock=True, limit=2)
    assert_selection(page, ids[2:4])
    assert page["scope_total"] == 5
    assert page["categories"] == baseline["categories"]
    later = await catalog.page(has_stock=True, limit=2, offset=2)
    assert later["items"] == []
    assert later["total"] == 2
    assert later["scope_total"] == 5


@pytest.mark.parametrize(
    "filters,expected",
    [
        ({"seller": 0}, [0, 2, 3, 4]),
        ({"marketplace": "wildberries"}, [0, 1, 3, 4]),
        ({"category": "X"}, [0, 1, 4]),
        ({"search": "NEEDLE"}, [0, 1, 2, 3]),
        ({"seller": 0, "marketplace": "wildberries", "category": "X", "search": "NEEDLE"}, [0]),
        ({"seller": 0, "marketplace": "ozon", "search": "NEEDLE"}, [2]),
        ({"seller": 0, "marketplace": "ozon", "search": "OZ-C-NEEDLE"}, [2]),
    ],
)
async def test_c4_stock_filter_intersects_existing_filters(catalog, filters, expected):
    ids = [
        await catalog.add("A-NEEDLE", 2),
        await catalog.add("B-NEEDLE", 3, seller=1),
        await catalog.add("C-NEEDLE", 4, wb=False, ozon=True),
        await catalog.add("D-NEEDLE", 2, category="Y"),
        await catalog.add("E-OTHER", 2),
        await catalog.add("F-NEEDLE", 0),
        await catalog.add("G-NEEDLE", 0, wb=False, ozon=True),
    ]
    params = dict(filters)
    if "seller" in params:
        params["seller_id"] = str(catalog.sellers[params.pop("seller")])
    baseline = await catalog.page(**params)
    page = await catalog.page(has_stock=True, **params)
    assert page["scope_total"] == baseline["scope_total"]
    assert page["categories"] == baseline["categories"]
    assert_selection(page, [ids[i] for i in expected])


async def snapshot():
    # All persisted columns, including updated_at, not just quantities.
    async with SessionLocal() as session:
        return {
            model.__tablename__: (await session.execute(select(model.__table__))).all()
            for model in [
                Product,
                InventoryBalance,
                StockDirection,
                StorageLocation,
                ProductMarketplaceLink,
            ]
        }


async def test_c5_publication_limit_and_get_are_independent(catalog):
    disabled = await catalog.add("A-disabled", 3, enabled=False, limit=0, reserved=3)
    enabled = await catalog.add("B-enabled", 2, enabled=True, limit=10)
    await catalog.add("C-zero-enabled", 0, enabled=True, limit=10)
    before = await snapshot()
    all_stock = await catalog.page(has_stock=True)
    none = await catalog.page(has_stock=True, stock_publication="none")
    wb = await catalog.page(has_stock=True, stock_publication="wb")
    assert await snapshot() == before
    assert_selection(all_stock, [disabled, enabled])
    assert_selection(none, [disabled])
    assert_selection(wb, [enabled])


async def test_c6_locations_container_and_relocation_keep_membership(catalog):
    positive = await catalog.add("A-distributed", 2)
    await catalog.add("B-zero", 0)
    async with SessionLocal() as session:
        session.add_all(
            [
                InventoryBalance(
                    tenant_id=catalog.tenant,
                    product_id=uuid.UUID(positive),
                    storage_location_id=loc,
                    quantity=qty,
                    container_kind="box" if index == 2 else None,
                    container_id=uuid.uuid4() if index == 2 else None,
                )
                for index, (loc, qty) in enumerate(
                    zip(catalog.locations[1:], [3, 4], strict=True), 1
                )
            ]
        )
        await session.commit()
    assert (await catalog.summary())[positive]["quantity"] == 9
    before = await catalog.page(has_stock=True)
    async with SessionLocal() as session:
        balances = list(
            (
                await session.scalars(
                    select(InventoryBalance)
                    .where(
                        InventoryBalance.product_id == uuid.UUID(positive),
                    )
                    .order_by(InventoryBalance.quantity)
                )
            ).all()
        )
        balances[0].quantity -= 1
        balances[1].quantity += 1
        await session.commit()
    assert (await catalog.summary())[positive]["quantity"] == 9
    after = await catalog.page(has_stock=True)
    assert_selection(before, [positive])
    assert_selection(after, [positive])


async def test_c7_tenant_isolation_and_existing_permission_denial(catalog):
    own = await catalog.add("A-own", 3)
    async with SessionLocal() as session:
        tenant = Tenant(name="Foreign", slug=f"foreign-{uuid.uuid4().hex}")
        session.add(tenant)
        await session.flush()
        seller = Seller(tenant_id=tenant.id, name="Foreign")
        session.add(seller)
        await session.flush()
        product = Product(
            tenant_id=tenant.id,
            seller_id=seller.id,
            sku_code="B-foreign",
            name="Foreign",
            wb_nm_id=667999,
        )
        warehouse = Warehouse(tenant_id=tenant.id, name="Foreign", code="FOREIGN")
        session.add_all([product, warehouse])
        await session.flush()
        location = StorageLocation(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            code="F",
            barcode=f"F-{uuid.uuid4().hex}",
        )
        session.add(location)
        await session.flush()
        session.add(
            InventoryBalance(
                tenant_id=tenant.id,
                product_id=product.id,
                storage_location_id=location.id,
                quantity=20,
            )
        )
        await session.commit()
    for params in [{}, {"has_stock": True}]:
        assert_selection(await catalog.page(**params), [own])
        denied = await catalog.client.get(
            "/products/ff-catalog-page", headers=catalog.denied_headers, params=params
        )
        assert denied.status_code == 403
        assert denied.json()["detail"] == "forbidden"


async def test_regression_unfiltered_summary_publication_and_readonly_get(catalog):
    positive = await catalog.add("A-positive", 5, reserved=7)
    zero = await catalog.add("B-zero", 0, enabled=True, limit=10)
    before = await snapshot()
    summary = await catalog.summary()
    assert summary[positive]["quantity"] == 5
    assert summary[positive]["reserved"] == 7
    assert summary[positive]["available"] == -2
    assert summary[zero]["quantity"] == 0
    assert_selection(await catalog.page(), [positive, zero])
    assert_selection(await catalog.page(has_stock=False), [positive, zero])
    assert_selection(await catalog.page(stock_publication="none"), [positive])
    assert_selection(await catalog.page(stock_publication="wb"), [zero])
    assert await snapshot() == before
