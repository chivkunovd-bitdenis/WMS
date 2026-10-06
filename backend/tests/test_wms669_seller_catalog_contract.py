"""WMS-669 C1-C5/C9: permanent regression contract, frozen before code."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.seller_shop_delegation import SellerShopDelegation
from app.models.user import User
from tests.wms669_catalog_fixtures import (
    GROUP,
    Catalog,
    _assert_set,
    _headers,
    _key,
    _keys,
    _page,
)
from tests.wms669_catalog_fixtures import (
    _release_postgresql_pool_before_loop_closes as _release_postgresql_pool_before_loop_closes,
)
from tests.wms669_catalog_fixtures import (
    catalog as catalog,
)


async def test_c1_intersection_and_exact_article_size(async_client: AsyncClient, catalog: Catalog):
    c = catalog
    await _assert_set(
        async_client,
        c,
        {_key(c, "reserved"), _key(c, "variant")},
        search="Пуховик",
        category="Пуховики",
        article=" 2329БЛЭК ",
        size=" 48 ",
        marketplace="wildberries",
        on_fulfillment="yes",
        **GROUP,
    )
    await _assert_set(async_client, c, set(), article="2329", size="48")


async def test_c1_control_empty_filters_keep_previous_catalog(
    async_client: AsyncClient,
    catalog: Catalog,
):
    plain = await _page(async_client, catalog)
    empty = await _page(async_client, catalog, article="", size="", stock_only="false")
    assert empty == plain
    assert plain["total"] == 15
    assert set(await _keys(async_client, catalog)) == {r["key"] for r in plain["items"]}
    old = await _page(
        async_client,
        catalog,
        category="Пуховики",
        marketplace="wildberries",
        search="Пуховик",
        on_fulfillment="yes",
    )
    assert old["total"] == 9


async def test_c2_quantity_not_free_limit_or_published(async_client: AsyncClient, catalog: Catalog):
    summary = await async_client.get(
        "/operations/inventory-balances/summary", headers=catalog.headers
    )
    assert summary.status_code == 200, summary.text
    row = next(r for r in summary.json() if r["product_id"] == catalog.products["reserved"])
    assert (row["quantity"], row["reserved"], row["available"]) == (4, 4, 0)
    rows = {r["key"]: r for r in (await _page(async_client, catalog))["items"]}
    assert rows[_key(catalog, "reserved")]["fbs_published_amount"] == 0
    assert rows[_key(catalog, "reserved")]["fbs_stock_limit"] == 0
    assert rows[_key(catalog, "zero")]["fbs_published_amount"] == 999
    expected = {
        _key(catalog, label)
        for label in ("reserved", "variant", "article", "size", "category", "split")
    }
    await _assert_set(async_client, catalog, expected, stock_only="true")
    await _assert_set(async_client, catalog, set(), stock_only="true", on_fulfillment="no")


async def test_c3_aggregate_before_limit_offset(async_client: AsyncClient, catalog: Catalog):
    c = catalog
    summary = await async_client.get("/operations/inventory-balances/summary", headers=c.headers)
    assert summary.status_code == 200
    totals = {r["product_id"]: r["quantity"] for r in summary.json()}
    assert totals[c.products["split"]] == 5
    assert totals[c.products["cancel"]] == 0
    unfiltered = await _page(async_client, c, limit=1)
    assert unfiltered["items"][0]["key"] != _key(c, "split")
    filtered = await _page(async_client, c, stock_only="true", article="split", limit=1)
    assert [r["key"] for r in filtered["items"]] == [_key(c, "split")]
    assert filtered["total"] == 1 and filtered["scope_total"] == 15
    assert await _keys(async_client, c, stock_only="true", article="split") == [_key(c, "split")]
    assert (await _page(async_client, c, stock_only="true", article="split", limit=1, offset=1))[
        "items"
    ] == []


async def test_c4_server_order_and_unique_rows_across_pages(
    async_client: AsyncClient, catalog: Catalog
):
    c = catalog
    params = {**GROUP, "on_fulfillment": "yes"}
    full = await _page(async_client, c, **params)
    tuples = [
        (r["wb_subject_name"], r["wb_vendor_code"], r["wb_size"], r["key"])
        for r in full["items"]
        if r["wb_subject_name"] is not None
    ]
    assert tuples == sorted(tuples)
    seen = []
    for offset in range(full["total"]):
        page = await _page(async_client, c, **params, limit=1, offset=offset)
        assert page["total"] == full["total"]
        seen.extend(r["key"] for r in page["items"])
    assert seen == [r["key"] for r in full["items"]]
    assert len(seen) == len(set(seen)) == 11
    assert {_key(c, "reserved"), _key(c, "variant")} <= set(seen)
    assert set(await _keys(async_client, c, **params)) == set(seen)


async def test_c5_imported_size_membership_fallback_and_ozon_offer(
    async_client: AsyncClient,
    catalog: Catalog,
):
    await _assert_set(
        async_client,
        catalog,
        {"wb:669101"},
        article="2329БЛЭК",
        size="48",
        marketplace="wildberries",
        on_fulfillment="no",
    )
    row = (await _page(async_client, catalog, article="2329блэк", size="48", on_fulfillment="no"))[
        "items"
    ][0]
    assert row["sizes"] == ["46", "48"]
    await _assert_set(
        async_client,
        catalog,
        {"ozon:669-ozon"},
        article=" 2329БЛЭК ",
        marketplace="ozon",
        on_fulfillment="no",
    )
    await _assert_set(
        async_client,
        catalog,
        set(),
        article="2329блэк",
        size="48",
        marketplace="ozon",
        on_fulfillment="no",
    )


async def test_c5_control_missing_values_are_not_guessed(
    async_client: AsyncClient,
    catalog: Catalog,
):
    page = await _page(async_client, catalog)
    rows = {r["key"]: r for r in page["items"]}
    assert rows[_key(catalog, "unknown")]["wb_vendor_code"] is None
    assert rows[_key(catalog, "unknown")]["wb_size"] is None
    assert rows["wb:669103"]["sizes"] == [] and rows["wb:669103"]["category"] is None
    assert rows["ozon:669-ozon"]["sizes"] == [] and rows["ozon:669-ozon"]["category"] is None


@pytest.mark.parametrize("marketplace", [None, "wildberries", "ozon"])
async def test_c9_scope_parity_and_summary(
    async_client: AsyncClient, catalog: Catalog, marketplace
):
    c = catalog
    params = {"article": "2329блэк", "size": "48", "stock_only": "true", **GROUP}
    if marketplace:
        params["marketplace"] = marketplace
    expected = {_key(c, "reserved")}
    if marketplace != "ozon":
        expected |= {_key(c, "variant"), _key(c, "category")}
    await _assert_set(async_client, c, expected, **params)
    summary = await async_client.get("/operations/inventory-balances/summary", headers=c.headers)
    assert summary.status_code == 200
    assert {r["product_id"] for r in summary.json()} <= set(c.products.values())
    for headers in (c.other_headers, c.foreign_headers):
        page = await async_client.get("/seller-catalog/page", headers=headers, params=params)
        keys = await async_client.get("/seller-catalog/keys", headers=headers, params=params)
        assert page.status_code == keys.status_code == 200
        assert not ({r["key"] for r in page.json()["items"]} & expected)
        assert set(keys.json()) == {r["key"] for r in page.json()["items"]}


async def test_c9_control_permissions_and_shop_switch(async_client: AsyncClient, catalog: Catalog):
    c = catalog
    for path in (
        "/seller-catalog/page",
        "/seller-catalog/keys",
        "/operations/inventory-balances/summary",
    ):
        denied = await async_client.get(
            path, headers=c.denied_headers, params={"article": "2329блэк", "stock_only": "true"}
        )
        assert denied.status_code == 403
    async with SessionLocal() as s:
        user = await s.get(User, c.user)
        assert user is not None
        forged = _headers(user, c.other_seller)
        response = await async_client.get("/seller-catalog/page", headers=forged)
        assert response.status_code == 200
        assert {r["key"] for r in response.json()["items"]} == set(await _keys(async_client, c))
        user.can_manage_seller_shops = True
        s.add(SellerShopDelegation(user_id=user.id, target_seller_id=c.other_seller))
        await s.commit()
        delegated = _headers(user, c.other_seller)
    for path in ("/seller-catalog/page", "/seller-catalog/keys"):
        delegated_res = await async_client.get(path, headers=delegated)
        own_res = await async_client.get(path, headers=c.other_headers)
        assert delegated_res.status_code == own_res.status_code == 200
        assert delegated_res.json() == own_res.json()


@pytest.mark.parametrize("endpoint", ["page", "keys"])
@pytest.mark.parametrize(
    "filters,labels",
    [
        ({"article": "2329БЛЭК", "size": "48"}, {"reserved", "variant", "category"}),
        ({"article": "2329"}, set()),
        ({"article": "2329блэк", "size": "148"}, {"size"}),
    ],
)
async def test_c1_each_endpoint_filters_exact_values(
    async_client: AsyncClient,
    catalog: Catalog,
    endpoint: str,
    filters: dict[str, str],
    labels: set[str],
):
    response = await async_client.get(
        f"/seller-catalog/{endpoint}",
        headers=catalog.headers,
        params={**filters, "on_fulfillment": "yes"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    actual = set(body) if endpoint == "keys" else {r["key"] for r in body["items"]}
    assert actual == {_key(catalog, label) for label in labels}


@pytest.mark.parametrize("marketplace,total", [(None, 15), ("wildberries", 14), ("ozon", 2)])
async def test_c9_control_existing_tenant_seller_marketplace_scope(
    async_client: AsyncClient,
    catalog: Catalog,
    marketplace: str | None,
    total: int,
):
    params = {"marketplace": marketplace} if marketplace else {}
    home = await _page(async_client, catalog, **params)
    home_keys = {r["key"] for r in home["items"]}
    assert home["total"] == total
    assert set(await _keys(async_client, catalog, **params)) == home_keys
    for headers in (catalog.other_headers, catalog.foreign_headers):
        response = await async_client.get("/seller-catalog/page", headers=headers, params=params)
        keys = await async_client.get("/seller-catalog/keys", headers=headers, params=params)
        assert response.status_code == keys.status_code == 200
        other_keys = {r["key"] for r in response.json()["items"]}
        assert other_keys.isdisjoint(home_keys)
        assert set(keys.json()) == other_keys
        summary = await async_client.get("/operations/inventory-balances/summary", headers=headers)
        assert summary.status_code == 200
        assert {r["product_id"] for r in summary.json()}.isdisjoint(catalog.products.values())
    summary = await async_client.get(
        "/operations/inventory-balances/summary", headers=catalog.headers
    )
    assert summary.status_code == 200
    assert {r["product_id"] for r in summary.json()} <= set(catalog.products.values())


async def test_c4_control_variants_keep_identity_name_color_and_separate_stock(
    async_client: AsyncClient,
    catalog: Catalog,
):
    page = await _page(async_client, catalog)
    rows = {r["key"]: r for r in page["items"]}
    for label in ("reserved", "variant"):
        assert rows[_key(catalog, label)]["name"] == f"Пуховик {label}"
        assert rows[_key(catalog, label)]["wb_color"] == label
    assert [r["key"] for r in page["items"]].count(_key(catalog, "reserved")) == 1
    assert rows[_key(catalog, "reserved")]["ozon_offer_id"] == "2329блэк"
    summary = await async_client.get(
        "/operations/inventory-balances/summary", headers=catalog.headers
    )
    assert summary.status_code == 200
    quantities = {r["product_id"]: r["quantity"] for r in summary.json()}
    assert quantities[catalog.products["reserved"]] == 4
    assert quantities[catalog.products["variant"]] == 2


@pytest.mark.parametrize("endpoint", ["page", "keys"])
@pytest.mark.parametrize(
    "filters,expected",
    [
        ({"article": "2329БЛЭК", "size": "48", "marketplace": "wildberries"}, {"wb:669101"}),
        ({"article": "2329блэк", "size": "148", "marketplace": "wildberries"}, {"wb:669102"}),
        ({"article": "2329БЛЭК", "marketplace": "ozon"}, {"ozon:669-ozon"}),
        ({"article": "2329блэк", "size": "48", "marketplace": "ozon"}, set()),
    ],
)
async def test_c5_each_endpoint_imported_sizes_and_offer_id(
    async_client: AsyncClient,
    catalog: Catalog,
    endpoint: str,
    filters: dict[str, str],
    expected: set[str],
):
    response = await async_client.get(
        f"/seller-catalog/{endpoint}",
        headers=catalog.headers,
        params={**filters, "on_fulfillment": "no"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    actual = set(body) if endpoint == "keys" else {r["key"] for r in body["items"]}
    assert actual == expected
    if endpoint == "page" and expected == {"wb:669101"}:
        assert body["items"][0]["sizes"] == ["46", "48"]
