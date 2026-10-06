"""WMS-669 C10: one-time read-only and PostgreSQL proof, not permanent guards."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal, engine
from app.models import Base
from tests.wms669_catalog_fixtures import (
    GROUP,
    Catalog,
    _assert_set,
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


async def _snapshot() -> dict[str, list[str]]:
    async with SessionLocal() as s:
        return {
            table.name: sorted(repr(tuple(row)) for row in (await s.execute(select(table))).all())
            for table in Base.metadata.sorted_tables
        }


async def test_c10_reading_has_no_writes(async_client: AsyncClient, catalog: Catalog):
    before = await _snapshot()
    for params in ({}, {"article": "2329блэк", "size": "48", "stock_only": "true", **GROUP}):
        await _page(async_client, catalog, **params)
        await _keys(async_client, catalog, **params)
    assert await _snapshot() == before


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="C10 requires isolated PostgreSQL")
async def test_c10_postgresql_json_sizes_and_stock(async_client: AsyncClient, catalog: Catalog):
    await _assert_set(
        async_client,
        catalog,
        {"wb:669101"},
        article="2329БЛЭК",
        size="48",
        on_fulfillment="no",
        **GROUP,
    )
    await _assert_set(
        async_client,
        catalog,
        {_key(catalog, "reserved"), _key(catalog, "variant")},
        category="Пуховики",
        article="2329блэк",
        size="48",
        stock_only="true",
        on_fulfillment="yes",
        **GROUP,
    )
