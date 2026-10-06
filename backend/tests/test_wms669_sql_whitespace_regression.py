"""Permanent D1 contract: SQL selection/grouping must match displayed strip().

Real HTTP routes, auth, service, enrichment and SQL; only an isolated test DB.
R2/R4/R5/R6, extending the frozen bca2fc9 cases without changing their bytes.
No new collation requirement: equal visible category labels stay contiguous.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from itertools import groupby
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.roles import FULFILLMENT_SELLER
from app.db.session import SessionLocal
from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from app.models.seller import Seller
from app.models.seller_staff_permissions import SellerStaffPermissions
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard as Card
from app.models.tenant import Tenant
from app.models.user import User
from app.services.tokens import create_access_token

GROUP = {"group_by": "category_article_size"}
WHITESPACE = pytest.mark.parametrize("outer", ["\t", "\u00a0"], ids=["tabs", "nbsp"])


@dataclass(frozen=True)
class Scope:
    tenant: uuid.UUID
    seller: uuid.UUID
    headers: dict[str, str]


@pytest_asyncio.fixture
async def scope(async_client: AsyncClient) -> Scope:
    # Minimal deterministic data; async_client owns schema/reset in its test DB.
    tenant_id, seller_id, user_id = [uuid.UUID(int=669960 + i) for i in range(3)]
    async with SessionLocal() as session:
        session.add(Tenant(id=tenant_id, name="D1", slug="wms669-d1"))
        await session.flush()
        session.add(Seller(id=seller_id, tenant_id=tenant_id, name="D1 seller"))
        await session.flush()
        session.add(User(
            id=user_id, tenant_id=tenant_id, seller_id=seller_id,
            role=FULFILLMENT_SELLER, password_hash="test-only",
        ))
        await session.flush()
        session.add(SellerStaffPermissions(user_id=user_id, can_products=True))
        await session.commit()
    token = create_access_token(
        user_id=user_id, tenant_id=tenant_id, role=FULFILLMENT_SELLER, seller_id=seller_id,
    )
    return Scope(tenant_id, seller_id, {"Authorization": "Bearer " + token})


async def _cards(scope: Scope, article: str, raws: list[dict[str, Any]]) -> list[str]:
    async with SessionLocal() as session:
        for i, raw in enumerate(raws):
            session.add(Card(
                tenant_id=scope.tenant, seller_id=scope.seller, nm_id=669970 + i,
                vendor_code=article, raw_json=raw,
            ))
        await session.commit()
    return [f"wb:{669970 + i}" for i in range(len(raws))]


async def _get(client: AsyncClient, scope: Scope, endpoint: str, **params: Any) -> Any:
    response = await client.get(
        f"/seller-catalog/{endpoint}", headers=scope.headers, params={**GROUP, **params},
    )
    assert response.status_code == 200, response.text
    return response.json()


@WHITESPACE
async def test_category_strip_groups_are_contiguous_across_http_pages(
    async_client: AsyncClient, scope: Scope, outer: str,
) -> None:
    article = "wms669-d1-category"
    keys = await _cards(scope, article, [
        {"subjectName": category, "sizes": [{"techSize": "48"}]}
        for category in [f"{outer}Футболки{outer}", "Пуховики", "Футболки"]
    ])
    full = await _get(async_client, scope, "page", article=article)
    rows = full["items"]
    assert {r["key"]: r["category"] for r in rows} == dict(zip(
        keys, ["Футболки", "Пуховики", "Футболки"], strict=True,
    ))
    pages = [await _get(
        async_client, scope, "page", article=article, limit=1, offset=i,
    ) for i in range(3)]
    paged = [r for page in pages for r in page["items"]]
    assert paged == rows
    assert all(page["total"] == full["total"] == 3 for page in pages)
    assert set(await _get(async_client, scope, "keys", article=article)) == set(keys)
    sequence = [r["category"] for r in paged]
    runs = [label for label, _ in groupby(sequence)]
    assert len(runs) == len(set(sequence)), f"D1 visible category sequence: {sequence}"


@WHITESPACE
async def test_numeric_techsize_string_wbsize_strip_matches_http_page_keys(
    async_client: AsyncClient, scope: Scope, outer: str,
) -> None:
    article = "wms669-d1-imported"
    keys = await _cards(scope, article, [
        {"sizes": [{"techSize": 148, "wbSize": f"{outer}48{outer}"}]},
        {"sizes": [{"techSize": "148"}]},
        {"sizes": [{"techSize": "48"}]},
    ])
    full = await _get(async_client, scope, "page", article=article)
    assert full["total"] == 3
    assert {r["key"]: r["sizes"] for r in full["items"]} == {
        keys[0]: ["48"], keys[1]: ["148"], keys[2]: ["48"],
    }
    assert set(await _get(async_client, scope, "keys", article=article)) == set(keys)
    observed = {}
    for size in ["48", "148"]:
        first = await _get(async_client, scope, "page", article=article, size=size, limit=1)
        second = await _get(
            async_client, scope, "page", article=article, size=size, limit=1, offset=1,
        )
        selected = await _get(async_client, scope, "keys", article=article, size=size)
        observed[size] = (
            [(r["key"], r["sizes"]) for r in first["items"] + second["items"]],
            selected, first["total"], second["total"],
        )
    assert observed == {
        "48": ([(keys[0], ["48"]), (keys[2], ["48"])], [keys[0], keys[2]], 2, 2),
        "148": ([(keys[1], ["148"])], [keys[1]], 1, 1),
    }, f"D1 displayed 48 must match both HTTP endpoints before pagination: {observed}"


@WHITESPACE
async def test_own_barcode_variant_strip_matches_http_page_keys(
    async_client: AsyncClient, scope: Scope, outer: str,
) -> None:
    article = "wms669-d1-own-variant"
    await _cards(scope, article, [{"sizes": [
        {"techSize": "148", "skus": ["d1-other"]},
        {"techSize": 148, "wbSize": f"{outer}48{outer}", "skus": ["d1-own"]},
    ]}])
    pid = uuid.UUID(int=669980)
    async with SessionLocal() as session:
        session.add(Product(
            id=pid, tenant_id=scope.tenant, seller_id=scope.seller,
            name="D1 own variant", sku_code=article, wb_vendor_code=article,
            wb_nm_id=669970, wb_size=None, wb_barcode=None,
        ))
        await session.flush()
        session.add(ProductBarcode(
            tenant_id=scope.tenant, seller_id=scope.seller, product_id=pid,
            source="wb", barcode="d1-own",
        ))
        await session.commit()
    key = f"product:{pid}"
    full = await _get(async_client, scope, "page", article=article)
    assert full["total"] == 1
    assert [(r["key"], r["wb_size"]) for r in full["items"]] == [(key, "48")]
    assert await _get(async_client, scope, "keys", article=article) == [key]
    observed = {}
    for size in ["48", "148"]:
        page = await _get(async_client, scope, "page", article=article, size=size, limit=1)
        selected = await _get(async_client, scope, "keys", article=article, size=size)
        observed[size] = (
            [(r["key"], r["wb_size"]) for r in page["items"]], selected, page["total"],
        )
    assert observed == {
        "48": ([(key, "48")], [key], 1), "148": ([], [], 0),
    }, f"D1 own source=wb barcode variant, displayed 48: {observed}"
