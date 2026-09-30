"""WMS-601: large catalog counts stay below PostgreSQL's bind limit."""

from __future__ import annotations

import uuid
from math import ceil
from typing import cast

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marking_code import (
    STATUS_AVAILABLE,
    STATUS_PRINTED,
    MarkingCode,
    MarkingPool,
    MarkingPoolProduct,
)
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.services import marking_code_service as service


class _EmptyRows:
    def all(self) -> list[tuple[uuid.UUID, int]]:
        return []


class _PostgresBindRecorder:
    def __init__(self) -> None:
        self.bind_counts: list[int] = []

    async def execute(self, statement: object) -> _EmptyRows:
        # Expand the same IN parameters psycopg would receive, rather than
        # counting only SQLAlchemy's pre-expansion placeholders.
        compiled = statement.compile(  # type: ignore[attr-defined]
            dialect=postgresql.dialect(), compile_kwargs={"render_postcompile": True}
        )
        self.bind_counts.append(len(compiled.params))
        return _EmptyRows()


@pytest.mark.asyncio
async def test_large_catalog_uses_bounded_postgres_parameters() -> None:
    product_ids = {uuid.UUID(int=index) for index in range(1, 32_770)}
    recorder = _PostgresBindRecorder()

    counts = await service.count_available_for_products_batch(
        cast(AsyncSession, recorder), uuid.uuid4(), product_ids
    )

    assert len(counts) == len(product_ids)
    assert set(counts.values()) == {0}
    assert len(recorder.bind_counts) == 2 * ceil(len(product_ids) / service.ID_IN_BATCH_SIZE)
    assert max(recorder.bind_counts) <= 2 * service.ID_IN_BATCH_SIZE + 3 < 65_535


@pytest.mark.asyncio
async def test_batched_counts_keep_pool_direct_seller_and_tenant_rules(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "ID_IN_BATCH_SIZE", 2)
    tenant = Tenant(name="Large catalog", slug=f"large-catalog-{uuid.uuid4().hex[:8]}")
    other_tenant = Tenant(name="Other catalog", slug=f"other-catalog-{uuid.uuid4().hex[:8]}")
    seller = Seller(tenant=tenant, name="Seller A")
    other_seller = Seller(tenant=tenant, name="Seller B")
    foreign_seller = Seller(tenant=other_tenant, name="Seller C")
    products = [
        Product(tenant=tenant, seller=seller, sku_code=f"SKU-{index}", name=f"Product {index}")
        for index in range(3)
    ]
    seller_product = Product(
        tenant=tenant, seller=other_seller, sku_code="SELLER-B", name="Seller B product"
    )
    foreign_product = Product(
        tenant=other_tenant,
        seller=foreign_seller,
        sku_code="FOREIGN",
        name="Foreign product",
    )
    db_session.add_all([*products, seller_product, foreign_product])
    await db_session.flush()
    pooled, direct, empty = products
    pool = MarkingPool(tenant=tenant, seller=seller, gtin="04600000000001", title="Pool")
    db_session.add(pool)
    await db_session.flush()
    db_session.add(MarkingPoolProduct(tenant=tenant, pool=pool, product=pooled))

    def code(
        index: int,
        *,
        owner: Seller = seller,
        product: Product | None = None,
        source_pool: MarkingPool | None = None,
        status: str = STATUS_AVAILABLE,
    ) -> MarkingCode:
        return MarkingCode(
            tenant=owner.tenant,
            seller=owner,
            product=product,
            pool=source_pool,
            cis_code=f"CIS-{index}",
            status=status,
        )

    db_session.add_all(
        [
            code(1, source_pool=pool),
            code(2, product=pooled, source_pool=pool),
            code(3, owner=other_seller, source_pool=pool),  # wrong seller for pooled
            code(4, product=pooled),  # direct code excluded for linked product
            code(5, product=direct),
            code(6, product=direct),
            code(7, product=direct, status=STATUS_PRINTED),
            code(8, owner=other_seller, product=direct),  # wrong seller for direct
            code(9, owner=other_seller, product=seller_product),
            code(10, owner=foreign_seller, product=foreign_product),
        ]
    )
    await db_session.commit()

    requested = {item.id for item in (*products, seller_product, foreign_product)}
    counts = await service.count_available_for_products_batch(db_session, tenant.id, requested)
    assert counts == {
        pooled.id: 2,
        direct.id: 2,
        empty.id: 0,
        seller_product.id: 1,
        foreign_product.id: 0,
    }
    assert await service.count_available_for_products_batch(db_session, tenant.id, set()) == {}
