"""WMS-669 shared isolated HTTP/DB fixtures for forever and once contracts.

Frozen before implementation: article/size are exact, trimmed, case-insensitive;
stock_only is organization quantity > 0; group_by requests server group ordering.
Unknown query arguments currently return 200 but fail the business assertions.
No service mocks, production DB, external marketplace calls or guard edits.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest_asyncio
from httpx import AsyncClient

from app.core.roles import FULFILLMENT_SELLER
from app.db.session import SessionLocal, engine
from app.models.fbs_order import FbsOrder, FbsOrderReservation
from app.models.fbs_stock_sync_item import FbsStockSyncItem
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.seller_ozon_imported_card import SellerOzonImportedCard
from app.models.seller_staff_permissions import SellerStaffPermissions
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services.sorting_location_service import SORTING_LOCATION_CODE
from app.services.tokens import create_access_token

GROUP = {"group_by": "category_article_size"}


@pytest_asyncio.fixture(autouse=True)
async def _release_postgresql_pool_before_loop_closes():
    # async_client and the tests use function-scoped asyncio loops. asyncpg
    # pooled connections belong to that loop; do not carry them to the next test.
    # Autouse starts before async_client, so teardown runs after its DB cleanup.
    yield
    if engine.dialect.name == "postgresql":
        await engine.dispose()


@dataclass
class Catalog:
    tenant: uuid.UUID
    seller: uuid.UUID
    user: uuid.UUID
    headers: dict[str, str]
    products: dict[str, str]
    other_seller: uuid.UUID
    other_headers: dict[str, str]
    foreign_headers: dict[str, str]
    denied_headers: dict[str, str]


def _headers(user: User, seller_id: uuid.UUID | None = None) -> dict[str, str]:
    return {
        "Authorization": "Bearer "
        + create_access_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
            role=user.role,
            seller_id=seller_id or user.seller_id,
        )
    }


@pytest_asyncio.fixture
async def catalog(async_client: AsyncClient) -> Catalog:
    """Valid FK data on both SQLite and PostgreSQL; auth still runs normally."""
    async with SessionLocal() as s:
        tenant = Tenant(id=uuid.uuid4(), name="669", slug="wms669")
        foreign = Tenant(id=uuid.uuid4(), name="other", slug="wms669-other")
        s.add_all([tenant, foreign])
        await s.flush()
        sellers = [
            Seller(id=uuid.uuid4(), tenant_id=t, name=n)
            for t, n in ((tenant.id, "home"), (tenant.id, "shop"), (foreign.id, "foreign"))
        ]
        s.add_all(sellers)
        await s.flush()
        users = [
            User(
                id=uuid.uuid4(),
                tenant_id=sl.tenant_id,
                seller_id=sl.id,
                role=FULFILLMENT_SELLER,
                password_hash="test-only",
                email=f"{i}@wms669.example",
            )
            for i, sl in enumerate(sellers)
        ]
        denied = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            seller_id=sellers[0].id,
            role=FULFILLMENT_SELLER,
            password_hash="test-only",
        )
        s.add_all([*users, denied])
        await s.flush()
        s.add(SellerStaffPermissions(user_id=denied.id, can_products=False))
        for user in users:
            s.add(SellerStaffPermissions(user_id=user.id, can_products=True))
        warehouses = [
            Warehouse(id=uuid.uuid4(), tenant_id=tenant.id, name=str(i), code=f"669-{i}")
            for i in range(2)
        ]
        s.add_all(warehouses)
        await s.flush()
        locations = [
            StorageLocation(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                warehouse_id=wh.id,
                code=code,
                barcode=f"669-{i}",
            )
            for i, (wh, code) in enumerate(
                [(warehouses[0], SORTING_LOCATION_CODE), (warehouses[1], "CELL-669")]
            )
        ]
        s.add_all(locations)
        await s.flush()
        binding = FbsWarehouseBinding(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            seller_id=sellers[0].id,
            wb_warehouse_id=669,
            wms_warehouse_id=warehouses[0].id,
        )
        s.add(binding)
        await s.flush()
        products: dict[str, str] = {}
        # Deliberately conflicting SKU order: category/article/size must order first.
        specs = [
            ("reserved", "z-669", "2329блэк", "48", "Пуховики", [4]),
            ("variant", "a-669", "2329блэк", "48", "Пуховики", [2]),
            ("article", "b-669", "23290", "48", "Пуховики", [1]),
            ("size", "c-669", "2329блэк", "148", "Пуховики", [1]),
            ("category", "d-669", "2329блэк", "48", "Футболки", [1]),
            ("zero", "e-669", "zero", "48", "Пуховики", [0]),
            ("negative", "f-669", "neg", "48", "Пуховики", [-1]),
            ("absent", "g-669", "absent", "48", "Пуховики", []),
            ("cancel", "h-669", "cancel", "48", "Пуховики", [5, -5]),
            ("split", "zz-669", "split", "48", "Пуховики", [2, 3]),
            ("unknown", "2329блэк-48", None, None, None, []),
        ]
        for i, (label, sku, article, size, category, quantities) in enumerate(specs):
            pid, nm = uuid.uuid4(), 669000 + i
            products[label] = str(pid)
            raw: dict[str, Any] = {
                "nmID": nm,
                "title": "Пуховик 2329блэк 48",
                "sizes": [],
                "characteristics": [{"name": "Цвет", "value": [label]}],
            }
            if category:
                raw["subjectName"] = category
            s.add(
                SellerWildberriesImportedCard(
                    tenant_id=tenant.id,
                    seller_id=sellers[0].id,
                    nm_id=nm,
                    vendor_code=article,
                    raw_json=raw,
                )
            )
            s.add(
                Product(
                    id=pid,
                    tenant_id=tenant.id,
                    seller_id=sellers[0].id,
                    name=f"Пуховик {label}",
                    sku_code=sku,
                    wb_nm_id=nm,
                    wb_chrt_id=nm * 10,
                    wb_vendor_code=article,
                    wb_size=size,
                    fbs_stock_limit=0 if label == "reserved" else 999,
                )
            )
            await s.flush()
            s.add(
                FbsStockSyncItem(
                    binding_id=binding.id,
                    product_id=pid,
                    chrt_id=nm * 10,
                    last_confirmed_amount=0 if label == "reserved" else 999,
                    status="confirmed",
                )
            )
            for j, quantity in enumerate(quantities):
                s.add(
                    InventoryBalance(
                        tenant_id=tenant.id,
                        product_id=pid,
                        storage_location_id=locations[j].id,
                        quantity=quantity,
                        container_kind="box" if j else None,
                        container_id=uuid.uuid4() if j else None,
                    )
                )
        order = FbsOrder(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            seller_id=sellers[0].id,
            warehouse_id=warehouses[0].id,
            product_id=uuid.UUID(products["reserved"]),
            wb_order_id=669,
            created_at_wb=datetime.now(UTC),
            deadline_at=datetime.now(UTC),
            mapping_status="mapped",
            reserve_status="reserved",
            status="new",
        )
        s.add(order)
        await s.flush()
        s.add(
            FbsOrderReservation(
                tenant_id=tenant.id,
                fbs_order_id=order.id,
                product_id=uuid.UUID(products["reserved"]),
                warehouse_id=warehouses[0].id,
                quantity=4,
            )
        )
        # Same physical product connected to WB and Ozon stays one row.
        s.add(
            ProductMarketplaceLink(
                tenant_id=tenant.id,
                seller_id=sellers[0].id,
                product_id=uuid.UUID(products["reserved"]),
                marketplace="ozon",
                external_product_id="669-dual",
                external_offer_id="2329блэк",
            )
        )
        for nm, vendor, sizes in [
            (669101, "2329блэк", [{"techSize": "46"}, {"techSize": "", "wbSize": "48"}]),
            (669102, "2329блэк", [{"techSize": "148"}]),
            (669103, None, []),
        ]:
            s.add(
                SellerWildberriesImportedCard(
                    tenant_id=tenant.id,
                    seller_id=sellers[0].id,
                    nm_id=nm,
                    vendor_code=vendor,
                    title="Пуховик 2329блэк 48",
                    raw_json={
                        "nmID": nm,
                        "vendorCode": vendor,
                        "title": "Пуховик 2329блэк 48",
                        "sizes": sizes,
                        **({"subjectName": "Пуховики"} if vendor else {}),
                    },
                )
            )
        s.add(
            SellerOzonImportedCard(
                tenant_id=tenant.id,
                seller_id=sellers[0].id,
                ozon_product_id="669-ozon",
                offer_id="2329блэк",
                name="Пуховик 48",
                raw_json={"offer_id": "2329блэк"},
            )
        )
        for i, seller in enumerate(sellers[1:]):
            pid, wh, loc = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            s.add(
                Product(
                    id=pid,
                    tenant_id=seller.tenant_id,
                    seller_id=seller.id,
                    name="Пуховик чужой",
                    sku_code="z-669",
                    wb_vendor_code="2329блэк",
                    wb_size="48",
                    wb_nm_id=669201 + i,
                )
            )
            s.add(
                SellerWildberriesImportedCard(
                    tenant_id=seller.tenant_id,
                    seller_id=seller.id,
                    nm_id=669201 + i,
                    vendor_code="2329блэк",
                    raw_json={"subjectName": "Пуховики"},
                )
            )
            s.add(Warehouse(id=wh, tenant_id=seller.tenant_id, name="other", code="other-669"))
            await s.flush()
            s.add(
                StorageLocation(
                    id=loc,
                    tenant_id=seller.tenant_id,
                    warehouse_id=wh,
                    code="other",
                    barcode=f"other-{i}",
                )
            )
            await s.flush()
            s.add(
                InventoryBalance(
                    tenant_id=seller.tenant_id,
                    product_id=pid,
                    storage_location_id=loc,
                    quantity=888,
                )
            )
        await s.commit()
        return Catalog(
            tenant.id,
            sellers[0].id,
            users[0].id,
            _headers(users[0]),
            products,
            sellers[1].id,
            _headers(users[1]),
            _headers(users[2]),
            _headers(denied),
        )


def _key(c: Catalog, label: str) -> str:
    return f"product:{c.products[label]}"


async def _page(client: AsyncClient, c: Catalog, **params: Any) -> dict[str, Any]:
    response = await client.get("/seller-catalog/page", headers=c.headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def _keys(client: AsyncClient, c: Catalog, **params: Any) -> list[str]:
    response = await client.get("/seller-catalog/keys", headers=c.headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def _assert_set(client: AsyncClient, c: Catalog, expected: set[str], **params: Any) -> None:
    page = await _page(client, c, **params)
    assert {r["key"] for r in page["items"]} == expected
    assert page["total"] == len(expected)
    assert set(await _keys(client, c, **params)) == expected
