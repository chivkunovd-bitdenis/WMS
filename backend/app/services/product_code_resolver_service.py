from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Literal, TypeAlias

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from app.models.product_marketplace_link import ProductMarketplaceLink

_EDGE_WHITESPACE = " \t\r\n"


class ProductCodeSource(StrEnum):
    WB_PRIMARY = "wb_primary"
    WB_ADDITIONAL = "wb_additional"
    SKU = "sku"
    OZON_EXTERNAL_BARCODE = "ozon_external_barcode"
    OZON_EXTERNAL_SKU = "ozon_external_sku"
    OZON_EXTERNAL_OFFER_ID = "ozon_external_offer_id"


@dataclass(frozen=True, slots=True)
class ProductCodeScope:
    """The product set in which ambiguity is allowed to be calculated.

    ``seller_ids=None`` means all sellers of the tenant. An empty seller or product set
    intentionally means an empty scope.
    """

    tenant_id: uuid.UUID
    seller_ids: frozenset[uuid.UUID] | None = None
    product_ids: frozenset[uuid.UUID] | None = None


@dataclass(frozen=True, slots=True)
class ProductCodeAliasPolicy:
    """Optional aliases on top of primary/additional WB barcodes and SKU."""

    include_external_barcodes: bool = True
    include_marketplace_identity: bool = False


DEFAULT_PRODUCT_CODE_ALIAS_POLICY = ProductCodeAliasPolicy()
WB_ONLY_PRODUCT_CODE_ALIAS_POLICY = ProductCodeAliasPolicy(
    include_external_barcodes=False
)


@dataclass(frozen=True, slots=True)
class ProductCodeMatch:
    product_id: uuid.UUID
    matched_sources: tuple[ProductCodeSource, ...]


@dataclass(frozen=True, slots=True)
class ProductCodeFound:
    status: Literal["found"]
    product_id: uuid.UUID
    matched_sources: tuple[ProductCodeSource, ...]
    matched_code: str
    used_layout_candidate: bool


@dataclass(frozen=True, slots=True)
class ProductCodeNotFound:
    status: Literal["not_found"]


@dataclass(frozen=True, slots=True)
class ProductCodeAmbiguous:
    status: Literal["ambiguous"]
    product_ids: tuple[uuid.UUID, ...]
    matches: tuple[ProductCodeMatch, ...]
    matched_code: str
    used_layout_candidate: bool


ProductCodeResolution: TypeAlias = (
    ProductCodeFound | ProductCodeNotFound | ProductCodeAmbiguous
)


@dataclass(frozen=True, slots=True)
class ProductCodeIndex:
    scope: ProductCodeScope
    policy: ProductCodeAliasPolicy
    _matches_by_code: Mapping[str, tuple[ProductCodeMatch, ...]]


def normalize_product_code(value: str) -> str:
    """Trim only framing whitespace; preserve the payload byte-for-byte otherwise."""
    return value.strip(_EDGE_WHITESPACE)


def _lookup_key(value: str) -> str:
    return normalize_product_code(value).casefold()


def _empty_index(
    scope: ProductCodeScope,
    policy: ProductCodeAliasPolicy,
) -> ProductCodeIndex:
    return ProductCodeIndex(
        scope=scope,
        policy=policy,
        _matches_by_code=MappingProxyType({}),
    )


def _add_alias(
    aliases: dict[str, dict[uuid.UUID, set[ProductCodeSource]]],
    *,
    product_id: uuid.UUID,
    value: object,
    source: ProductCodeSource,
) -> None:
    if not isinstance(value, str):
        return
    key = _lookup_key(value)
    if not key:
        return
    aliases.setdefault(key, {}).setdefault(product_id, set()).add(source)


def _freeze_aliases(
    aliases: dict[str, dict[uuid.UUID, set[ProductCodeSource]]],
) -> Mapping[str, tuple[ProductCodeMatch, ...]]:
    frozen: dict[str, tuple[ProductCodeMatch, ...]] = {}
    for code, product_sources in aliases.items():
        frozen[code] = tuple(
            ProductCodeMatch(
                product_id=product_id,
                matched_sources=tuple(sorted(sources, key=str)),
            )
            for product_id, sources in sorted(
                product_sources.items(), key=lambda item: str(item[0])
            )
        )
    return MappingProxyType(frozen)


async def build_product_code_index(
    session: AsyncSession,
    *,
    scope: ProductCodeScope,
    policy: ProductCodeAliasPolicy = DEFAULT_PRODUCT_CODE_ALIAS_POLICY,
) -> ProductCodeIndex:
    """Load every product alias in scope with a fixed number of batch queries."""
    if scope.seller_ids == frozenset() or scope.product_ids == frozenset():
        return _empty_index(scope, policy)

    product_stmt = select(
        Product.id,
        Product.wb_barcode,
        Product.sku_code,
    ).where(Product.tenant_id == scope.tenant_id)
    if scope.seller_ids is not None:
        product_stmt = product_stmt.where(Product.seller_id.in_(scope.seller_ids))
    if scope.product_ids is not None:
        product_stmt = product_stmt.where(Product.id.in_(scope.product_ids))

    product_rows = (await session.execute(product_stmt)).all()
    if not product_rows:
        return _empty_index(scope, policy)

    aliases: dict[str, dict[uuid.UUID, set[ProductCodeSource]]] = {}
    scoped_product_ids = tuple(row.id for row in product_rows)
    for row in product_rows:
        _add_alias(
            aliases,
            product_id=row.id,
            value=row.wb_barcode,
            source=ProductCodeSource.WB_PRIMARY,
        )
        _add_alias(
            aliases,
            product_id=row.id,
            value=row.sku_code,
            source=ProductCodeSource.SKU,
        )

    barcode_rows = (
        await session.execute(
            select(ProductBarcode.product_id, ProductBarcode.barcode).where(
                ProductBarcode.tenant_id == scope.tenant_id,
                ProductBarcode.product_id.in_(scoped_product_ids),
                ProductBarcode.source == "wb",
            )
        )
    ).all()
    for barcode_row in barcode_rows:
        _add_alias(
            aliases,
            product_id=barcode_row.product_id,
            value=barcode_row.barcode,
            source=ProductCodeSource.WB_ADDITIONAL,
        )

    if policy.include_external_barcodes or policy.include_marketplace_identity:
        marketplace_rows = (
            await session.execute(
                select(
                    ProductMarketplaceLink.product_id,
                    ProductMarketplaceLink.external_barcodes,
                    ProductMarketplaceLink.external_sku,
                    ProductMarketplaceLink.external_offer_id,
                )
                .join(Product, Product.id == ProductMarketplaceLink.product_id)
                .where(
                    ProductMarketplaceLink.tenant_id == scope.tenant_id,
                    ProductMarketplaceLink.product_id.in_(scoped_product_ids),
                    ProductMarketplaceLink.marketplace == "ozon",
                    ProductMarketplaceLink.is_active.is_(True),
                    Product.tenant_id == ProductMarketplaceLink.tenant_id,
                    Product.seller_id == ProductMarketplaceLink.seller_id,
                )
            )
        ).all()
        for marketplace_row in marketplace_rows:
            if policy.include_external_barcodes and isinstance(
                marketplace_row.external_barcodes, (list, tuple)
            ):
                for barcode in marketplace_row.external_barcodes:
                    _add_alias(
                        aliases,
                        product_id=marketplace_row.product_id,
                        value=barcode,
                        source=ProductCodeSource.OZON_EXTERNAL_BARCODE,
                    )
            if policy.include_marketplace_identity:
                _add_alias(
                    aliases,
                    product_id=marketplace_row.product_id,
                    value=marketplace_row.external_sku,
                    source=ProductCodeSource.OZON_EXTERNAL_SKU,
                )
                _add_alias(
                    aliases,
                    product_id=marketplace_row.product_id,
                    value=marketplace_row.external_offer_id,
                    source=ProductCodeSource.OZON_EXTERNAL_OFFER_ID,
                )

    return ProductCodeIndex(
        scope=scope,
        policy=policy,
        _matches_by_code=_freeze_aliases(aliases),
    )


def _resolve_candidate(
    index: ProductCodeIndex,
    candidate: str,
    *,
    used_layout_candidate: bool,
) -> ProductCodeResolution:
    normalized = normalize_product_code(candidate)
    matches = index._matches_by_code.get(normalized.casefold(), ())
    if not matches:
        return ProductCodeNotFound(status="not_found")
    if len(matches) == 1:
        match = matches[0]
        return ProductCodeFound(
            status="found",
            product_id=match.product_id,
            matched_sources=match.matched_sources,
            matched_code=normalized,
            used_layout_candidate=used_layout_candidate,
        )
    return ProductCodeAmbiguous(
        status="ambiguous",
        product_ids=tuple(match.product_id for match in matches),
        matches=matches,
        matched_code=normalized,
        used_layout_candidate=used_layout_candidate,
    )


def resolve_product_code_from_index(
    index: ProductCodeIndex,
    code: str,
    *,
    layout_candidate: str | None = None,
) -> ProductCodeResolution:
    """Resolve raw input first, then an explicitly supplied keyboard-layout fallback."""
    raw_result = _resolve_candidate(index, code, used_layout_candidate=False)
    if raw_result.status != "not_found" or layout_candidate is None:
        return raw_result
    if _lookup_key(layout_candidate) == _lookup_key(code):
        return raw_result
    return _resolve_candidate(index, layout_candidate, used_layout_candidate=True)


async def resolve_product_code(
    session: AsyncSession,
    code: str,
    *,
    scope: ProductCodeScope,
    policy: ProductCodeAliasPolicy = DEFAULT_PRODUCT_CODE_ALIAS_POLICY,
    layout_candidate: str | None = None,
) -> ProductCodeResolution:
    """Build a scoped index and resolve one code without any per-product queries."""
    index = await build_product_code_index(session, scope=scope, policy=policy)
    return resolve_product_code_from_index(
        index,
        code,
        layout_candidate=layout_candidate,
    )
