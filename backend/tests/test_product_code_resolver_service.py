from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.services.product_code_resolver_service import (
    DEFAULT_PRODUCT_CODE_ALIAS_POLICY,
    WB_ONLY_PRODUCT_CODE_ALIAS_POLICY,
    ProductCodeAliasPolicy,
    ProductCodeAmbiguous,
    ProductCodeFound,
    ProductCodeNotFound,
    ProductCodeScope,
    ProductCodeSource,
    build_product_code_index,
    resolve_product_code,
    resolve_product_code_from_index,
)

WB_PRIMARY = "4601234567893"
WB_ADDITIONAL = "4601234567886"
WB_LEADING_ZERO = "04601234567893"
OZON_BARCODE = "OZN-987654"
CYRILLIC_SKU = "ФА_МОД8-4а/083/42"
RUSSIAN_LAYOUT_INPUT = "Сршт-56005"
LATIN_LAYOUT_SKU = "Chin-56005"
DUPLICATE_CODE = "DUP-536"


@dataclass(frozen=True)
class Seed:
    tenant_id: uuid.UUID
    other_tenant_id: uuid.UUID
    seller_id: uuid.UUID
    other_seller_id: uuid.UUID
    product_id: uuid.UUID
    leading_zero_product_id: uuid.UUID
    cyrillic_product_id: uuid.UUID
    layout_product_id: uuid.UUID
    duplicate_sku_product_id: uuid.UUID
    duplicate_ozon_product_id: uuid.UUID
    other_seller_product_id: uuid.UUID
    other_tenant_product_id: uuid.UUID


async def _seed(db_session: AsyncSession) -> Seed:
    tenant = Tenant(name="WMS-536", slug=f"wms-536-{uuid.uuid4().hex}")
    other_tenant = Tenant(
        name="WMS-536 other tenant",
        slug=f"wms-536-other-{uuid.uuid4().hex}",
    )
    seller = Seller(tenant=tenant, name="Seller A")
    other_seller = Seller(tenant=tenant, name="Seller B")
    foreign_seller = Seller(tenant=other_tenant, name="Seller C")

    product = Product(
        tenant=tenant,
        seller=seller,
        name="Product P",
        sku_code="AbC-42",
        wb_barcode=WB_PRIMARY,
    )
    leading_zero_product = Product(
        tenant=tenant,
        seller=seller,
        name="Product Q",
        sku_code="LEADING-ZERO-Q",
        wb_barcode=WB_LEADING_ZERO,
    )
    cyrillic_product = Product(
        tenant=tenant,
        seller=seller,
        name="Cyrillic product",
        sku_code=CYRILLIC_SKU,
    )
    layout_product = Product(
        tenant=tenant,
        seller=seller,
        name="Layout product",
        sku_code=LATIN_LAYOUT_SKU,
    )
    duplicate_sku_product = Product(
        tenant=tenant,
        seller=seller,
        name="Duplicate by SKU",
        sku_code=DUPLICATE_CODE,
    )
    duplicate_ozon_product = Product(
        tenant=tenant,
        seller=seller,
        name="Duplicate by Ozon barcode",
        sku_code="DUPLICATE-OZON-PRODUCT",
    )
    other_seller_product = Product(
        tenant=tenant,
        seller=other_seller,
        name="Same code in another seller",
        sku_code="OTHER-SELLER-SKU",
        wb_barcode=WB_PRIMARY,
    )
    other_tenant_product = Product(
        tenant=other_tenant,
        seller=foreign_seller,
        name="Same code in another tenant",
        sku_code="OTHER-TENANT-SKU",
        wb_barcode=WB_PRIMARY,
    )
    db_session.add_all(
        [
            tenant,
            other_tenant,
            seller,
            other_seller,
            foreign_seller,
            product,
            leading_zero_product,
            cyrillic_product,
            layout_product,
            duplicate_sku_product,
            duplicate_ozon_product,
            other_seller_product,
            other_tenant_product,
        ]
    )
    await db_session.flush()

    db_session.add_all(
        [
            ProductBarcode(
                tenant_id=tenant.id,
                seller_id=seller.id,
                product_id=product.id,
                barcode=WB_PRIMARY,
                source="wb",
            ),
            ProductBarcode(
                tenant_id=tenant.id,
                seller_id=seller.id,
                product_id=product.id,
                barcode=WB_ADDITIONAL,
                source="wb",
            ),
            ProductMarketplaceLink(
                tenant_id=tenant.id,
                seller_id=seller.id,
                product_id=product.id,
                marketplace="ozon",
                external_sku="987654",
                external_offer_id="offer-536",
                external_barcodes=[OZON_BARCODE],
            ),
            ProductMarketplaceLink(
                tenant_id=tenant.id,
                seller_id=seller.id,
                product_id=duplicate_ozon_product.id,
                marketplace="ozon",
                external_sku="duplicate-external-sku",
                external_offer_id="duplicate-offer-id",
                external_barcodes=[DUPLICATE_CODE],
            ),
        ]
    )
    await db_session.commit()
    return Seed(
        tenant_id=tenant.id,
        other_tenant_id=other_tenant.id,
        seller_id=seller.id,
        other_seller_id=other_seller.id,
        product_id=product.id,
        leading_zero_product_id=leading_zero_product.id,
        cyrillic_product_id=cyrillic_product.id,
        layout_product_id=layout_product.id,
        duplicate_sku_product_id=duplicate_sku_product.id,
        duplicate_ozon_product_id=duplicate_ozon_product.id,
        other_seller_product_id=other_seller_product.id,
        other_tenant_product_id=other_tenant_product.id,
    )


def _seller_scope(seed: Seed) -> ProductCodeScope:
    return ProductCodeScope(
        tenant_id=seed.tenant_id,
        seller_ids=frozenset({seed.seller_id}),
    )


def _found(result: object) -> ProductCodeFound:
    assert isinstance(result, ProductCodeFound)
    return result


@pytest.mark.asyncio
async def test_required_aliases_resolve_together_and_same_product_is_not_ambiguous(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)
    index = await build_product_code_index(db_session, scope=_seller_scope(seed))

    primary = _found(resolve_product_code_from_index(index, WB_PRIMARY))
    assert primary.product_id == seed.product_id
    assert set(primary.matched_sources) == {
        ProductCodeSource.WB_PRIMARY,
        ProductCodeSource.WB_ADDITIONAL,
    }

    expected = {
        WB_ADDITIONAL: (seed.product_id, ProductCodeSource.WB_ADDITIONAL),
        OZON_BARCODE: (seed.product_id, ProductCodeSource.OZON_EXTERNAL_BARCODE),
        "aBc-42": (seed.product_id, ProductCodeSource.SKU),
    }
    for code, (product_id, source) in expected.items():
        result = _found(resolve_product_code_from_index(index, code))
        assert result.product_id == product_id
        assert source in result.matched_sources


@pytest.mark.asyncio
async def test_raw_cyrillic_sku_wins_before_layout_candidate(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)
    result = _found(
        await resolve_product_code(
            db_session,
            CYRILLIC_SKU,
            scope=_seller_scope(seed),
            layout_candidate=LATIN_LAYOUT_SKU,
        )
    )

    assert result.product_id == seed.cyrillic_product_id
    assert result.used_layout_candidate is False
    assert result.matched_code == CYRILLIC_SKU


@pytest.mark.asyncio
async def test_layout_candidate_is_an_explicit_fallback_after_raw_miss(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)
    without_fallback = await resolve_product_code(
        db_session,
        RUSSIAN_LAYOUT_INPUT,
        scope=_seller_scope(seed),
    )
    assert isinstance(without_fallback, ProductCodeNotFound)

    result = _found(
        await resolve_product_code(
            db_session,
            RUSSIAN_LAYOUT_INPUT,
            scope=_seller_scope(seed),
            layout_candidate=LATIN_LAYOUT_SKU,
        )
    )
    assert result.product_id == seed.layout_product_id
    assert result.used_layout_candidate is True
    assert result.matched_code == LATIN_LAYOUT_SKU


@pytest.mark.asyncio
async def test_cross_source_duplicate_returns_all_scoped_product_ids(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)
    result = await resolve_product_code(
        db_session,
        DUPLICATE_CODE,
        scope=_seller_scope(seed),
    )

    assert isinstance(result, ProductCodeAmbiguous)
    assert set(result.product_ids) == {
        seed.duplicate_sku_product_id,
        seed.duplicate_ozon_product_id,
    }
    sources = {match.product_id: set(match.matched_sources) for match in result.matches}
    assert sources[seed.duplicate_sku_product_id] == {ProductCodeSource.SKU}
    assert sources[seed.duplicate_ozon_product_id] == {
        ProductCodeSource.OZON_EXTERNAL_BARCODE
    }


@pytest.mark.asyncio
async def test_scope_is_applied_before_ambiguity_for_seller_tenant_and_product_ids(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)

    seller_result = _found(
        await resolve_product_code(
            db_session,
            WB_PRIMARY,
            scope=_seller_scope(seed),
        )
    )
    assert seller_result.product_id == seed.product_id

    tenant_wide = await resolve_product_code(
        db_session,
        WB_PRIMARY,
        scope=ProductCodeScope(tenant_id=seed.tenant_id),
    )
    assert isinstance(tenant_wide, ProductCodeAmbiguous)
    assert set(tenant_wide.product_ids) == {
        seed.product_id,
        seed.other_seller_product_id,
    }
    assert seed.other_tenant_product_id not in tenant_wide.product_ids

    document_only = await resolve_product_code(
        db_session,
        WB_PRIMARY,
        scope=ProductCodeScope(
            tenant_id=seed.tenant_id,
            seller_ids=frozenset({seed.seller_id}),
            product_ids=frozenset({seed.leading_zero_product_id}),
        ),
    )
    assert isinstance(document_only, ProductCodeNotFound)


@pytest.mark.asyncio
async def test_13_and_14_digit_codes_with_leading_zero_are_distinct(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)

    thirteen = _found(
        await resolve_product_code(db_session, WB_PRIMARY, scope=_seller_scope(seed))
    )
    fourteen = _found(
        await resolve_product_code(
            db_session,
            WB_LEADING_ZERO,
            scope=_seller_scope(seed),
        )
    )
    assert thirteen.product_id == seed.product_id
    assert fourteen.product_id == seed.leading_zero_product_id

    only_thirteen = await resolve_product_code(
        db_session,
        WB_LEADING_ZERO,
        scope=ProductCodeScope(
            tenant_id=seed.tenant_id,
            seller_ids=frozenset({seed.seller_id}),
            product_ids=frozenset({seed.product_id}),
        ),
    )
    assert isinstance(only_thirteen, ProductCodeNotFound)


@pytest.mark.asyncio
async def test_only_edge_space_tab_cr_lf_are_trimmed_and_internal_gs_is_preserved(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)

    framed = _found(
        await resolve_product_code(
            db_session,
            f"\t  {WB_PRIMARY}\r\n",
            scope=_seller_scope(seed),
        )
    )
    assert framed.product_id == seed.product_id

    with_internal_gs = await resolve_product_code(
        db_session,
        "460123\x1d4567893",
        scope=_seller_scope(seed),
    )
    assert isinstance(with_internal_gs, ProductCodeNotFound)


@pytest.mark.asyncio
async def test_marketplace_identity_requires_explicit_policy_and_joins_ambiguity(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)
    product_only_scope = ProductCodeScope(
        tenant_id=seed.tenant_id,
        seller_ids=frozenset({seed.seller_id}),
        product_ids=frozenset({seed.product_id}),
    )

    default_result = await resolve_product_code(
        db_session,
        "offer-536",
        scope=product_only_scope,
        policy=DEFAULT_PRODUCT_CODE_ALIAS_POLICY,
    )
    assert isinstance(default_result, ProductCodeNotFound)

    enabled = _found(
        await resolve_product_code(
            db_session,
            "offer-536",
            scope=product_only_scope,
            policy=ProductCodeAliasPolicy(include_marketplace_identity=True),
        )
    )
    assert enabled.product_id == seed.product_id
    assert enabled.matched_sources == (ProductCodeSource.OZON_EXTERNAL_OFFER_ID,)

    collision = Product(
        tenant_id=seed.tenant_id,
        seller_id=seed.seller_id,
        name="Identity collision",
        sku_code="offer-536",
    )
    db_session.add(collision)
    await db_session.commit()
    ambiguous = await resolve_product_code(
        db_session,
        "offer-536",
        scope=_seller_scope(seed),
        policy=ProductCodeAliasPolicy(include_marketplace_identity=True),
    )
    assert isinstance(ambiguous, ProductCodeAmbiguous)
    assert set(ambiguous.product_ids) == {seed.product_id, collision.id}


@pytest.mark.asyncio
async def test_wb_only_policy_excludes_ozon_barcode_but_keeps_wb_and_sku(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)
    index = await build_product_code_index(
        db_session,
        scope=_seller_scope(seed),
        policy=WB_ONLY_PRODUCT_CODE_ALIAS_POLICY,
    )

    assert isinstance(
        resolve_product_code_from_index(index, OZON_BARCODE),
        ProductCodeNotFound,
    )
    assert _found(resolve_product_code_from_index(index, WB_ADDITIONAL)).product_id == (
        seed.product_id
    )
    assert _found(resolve_product_code_from_index(index, "abc-42")).product_id == (
        seed.product_id
    )


@pytest.mark.asyncio
async def test_built_index_supports_many_lookups_without_a_session_or_rebuild(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)
    index = await build_product_code_index(db_session, scope=_seller_scope(seed))

    db_session.expunge_all()
    for _ in range(100):
        assert _found(resolve_product_code_from_index(index, WB_PRIMARY)).product_id == (
            seed.product_id
        )
        assert _found(resolve_product_code_from_index(index, WB_ADDITIONAL)).product_id == (
            seed.product_id
        )
