"""Additional frozen HTTP regressions for Astra F1/F2 on 43cdb021.

Expected labels come from actual /page display fields, never raw JSON SQL keys.
No new alphabetic/numeric collation contract: equal displayed groups must be
contiguous, and page/keys must select exactly the displayed size/variant.
"""

from __future__ import annotations

import uuid
from itertools import groupby
from typing import Any

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard as Card
from tests.wms669_catalog_fixtures import GROUP, Catalog, _keys, _page
from tests.wms669_catalog_fixtures import (
    _release_postgresql_pool_before_loop_closes as _release_postgresql_pool_before_loop_closes,
)
from tests.wms669_catalog_fixtures import catalog as catalog


async def _cards(c: Catalog, article: str, raws: list[dict[str, Any]]) -> list[str]:
    async with SessionLocal() as session:
        for i, raw in enumerate(raws):
            session.add(Card(
                tenant_id=c.tenant, seller_id=c.seller, nm_id=669901 + i,
                vendor_code=article, raw_json=raw,
            ))
        await session.commit()
    return [f"wb:{669901 + i}" for i in range(len(raws))]


@pytest.mark.parametrize("first_category", [
    {"subjectName": " Футболки "}, {"subject_name": "Футболки"},
], ids=["trimmed-subjectName", "fallback-subject_name"])
async def test_displayed_categories_stay_contiguous_before_pagination(
    async_client: AsyncClient, catalog: Catalog, first_category: dict[str, str],
):
    article = "z-669-review-category"
    expected = await _cards(catalog, article, [
        {**category, "sizes": [{"techSize": "48"}]}
        for category in [first_category, {"subjectName": "Пуховики"},
                         {"subjectName": "Футболки"}]
    ])
    params = {"article": article, **GROUP}
    full = await _page(async_client, catalog, **params)
    rows = full["items"]
    # These are exactly the fields consumed by the screen's category headings.
    visible = {r["key"]: r["category"] for r in rows}
    assert visible == dict(zip(expected, ["Футболки", "Пуховики", "Футболки"], strict=True))
    pages = [await _page(async_client, catalog, limit=1, offset=i, **params) for i in range(3)]
    paged = [r for page in pages for r in page["items"]]
    assert paged == rows
    assert all(page["total"] == full["total"] == 3 for page in pages)
    assert set(await _keys(async_client, catalog, **params)) == set(expected)
    sequence = [r["category"] for r in paged]
    runs = [label for label, _ in groupby(sequence)]
    assert len(runs) == len(set(sequence)), f"visible category sequence: {sequence}"


async def test_imported_display_size_fallback_matches_exact_page_and_keys(
    async_client: AsyncClient, catalog: Catalog,
):
    article = "z-669-review-size"
    expected = await _cards(catalog, article, [
        {"sizes": [{"techSize": 148, "wbSize": " 48 "}]},
        {"sizes": [{"techSize": "148"}]},
        {"sizes": [{"techSize": "48"}]},
    ])
    params = {"article": article, **GROUP}
    full = await _page(async_client, catalog, **params)
    assert {r["key"]: r["sizes"] for r in full["items"]} == {
        expected[0]: ["48"], expected[1]: ["148"], expected[2]: ["48"],
    }
    observed = {}
    for size in ["48", "148"]:
        page = await _page(async_client, catalog, size=size, limit=1, **params)
        keys = await _keys(async_client, catalog, size=size, **params)
        observed[size] = ([(r["key"], r["sizes"]) for r in page["items"]], keys, page["total"])
    assert observed == {
        "48": ([(expected[0], ["48"])], [expected[0], expected[2]], 2),
        "148": ([(expected[1], ["148"])], [expected[1]], 1),
    }, f"actual visible sizes and exact filter results: {observed}"
    sequence = [tuple(r["sizes"]) for r in full["items"]]
    runs = [label for label, _ in groupby(sequence)]
    assert len(runs) == len(set(sequence)), f"visible size sequence: {sequence}"
    paged = [
        r for i in range(3)
        for r in (await _page(async_client, catalog, limit=1, offset=i, **params))["items"]
    ]
    assert paged == full["items"]
    assert set(await _keys(async_client, catalog, **params)) == set(expected)


async def test_product_variant_uses_exact_source_barcode_and_display_fallback(
    async_client: AsyncClient, catalog: Catalog,
):
    article = "z-669-review-variant"
    await _cards(catalog, article, [{"sizes": [
        {"techSize": "148", "skus": ["review-code-148"]},
        {"techSize": 148, "wbSize": "48", "skus": ["review-code-48"]},
    ]}])
    pid = uuid.uuid4()
    async with SessionLocal() as session:
        session.add(Product(
            id=pid, tenant_id=catalog.tenant, seller_id=catalog.seller,
            name="Review variant", sku_code=article, wb_vendor_code=article,
            wb_nm_id=669901, wb_size=None, wb_barcode=None,
        ))
        await session.flush()
        session.add(ProductBarcode(
            tenant_id=catalog.tenant, seller_id=catalog.seller, product_id=pid,
            source="wb", barcode="review-code-48",
        ))
        await session.commit()
    key = f"product:{pid}"
    full = await _page(async_client, catalog, article=article, **GROUP)
    assert [(r["key"], r["wb_size"]) for r in full["items"]] == [(key, "48")]
    observed = {}
    for size in ["48", "148"]:
        page = await _page(async_client, catalog, article=article, size=size, **GROUP)
        keys = await _keys(async_client, catalog, article=article, size=size, **GROUP)
        observed[size] = ([(r["key"], r["wb_size"]) for r in page["items"]], keys, page["total"])
    assert observed == {
        "48": ([(key, "48")], [key], 1), "148": ([], [], 0),
    }, f"actual source-barcode variant results: {observed}"


async def test_malformed_size_json_keeps_unknown_rows_and_ozon_metadata(
    async_client: AsyncClient, catalog: Catalog,
):
    article = "z-669-review-malformed"
    expected = await _cards(catalog, article, [
        {"sizes": "invalid"}, {"sizes": {"techSize": "48"}},
        {"sizes": [None, "48", 148, {"techSize": "", "wbSize": "48"}]},
    ])
    full = await _page(async_client, catalog, article=article, **GROUP)
    assert {r["key"]: r["sizes"] for r in full["items"]} == {
        expected[0]: [], expected[1]: [], expected[2]: ["48"],
    }
    assert full["total"] == 3
    assert set(await _keys(async_client, catalog, article=article, **GROUP)) == set(expected)
    for size, wanted in [("48", [expected[2]]), ("148", [])]:
        page = await _page(async_client, catalog, article=article, size=size, **GROUP)
        assert [r["key"] for r in page["items"]] == wanted
        assert page["total"] == len(wanted)
        assert await _keys(async_client, catalog, article=article, size=size, **GROUP) == wanted
    # Reuse the existing imported Ozon card: no category/size invented from its name.
    ozon = await _page(async_client, catalog, marketplace="ozon", on_fulfillment="no", **GROUP)
    assert [(r["key"], r["vendor_code"], r["category"], r["sizes"]) for r in ozon["items"]] == [
        ("ozon:669-ozon", "2329блэк", None, []),
    ]
    assert await _keys(
        async_client, catalog, marketplace="ozon", on_fulfillment="no", size="48", **GROUP,
    ) == []
