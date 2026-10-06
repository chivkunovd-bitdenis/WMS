"""Local variant characteristics for the product lines of printed documents."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, Protocol

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.services.catalog_service import chunked
from app.services.wb_card_enrichment import color_from_card, size_from_card_for_barcode


class PrintProductLine(Protocol):
    product_id: str
    size: str | None
    color: str | None


async def populate_print_variant_attributes(
    session: AsyncSession,
    products: Sequence[Product],
    lines: Sequence[PrintProductLine],
) -> None:
    """Enrich response DTOs only, matching snapshots by tenant, seller and nmID.

    A saved Product size wins; otherwise use the existing barcode-aware resolver,
    which leaves an unmatched multi-size card empty. No marketplace calls or writes.
    """
    products_by_id = {str(product.id): product for product in products}
    card_keys = {
        (product.tenant_id, product.seller_id, product.wb_nm_id)
        for product in products_by_id.values()
        if product.seller_id is not None and product.wb_nm_id is not None
    }
    cards: dict[tuple[uuid.UUID, uuid.UUID, int], dict[str, Any]] = {}
    # Tuple predicates need smaller batches than scalar product ID queries.
    for batch in chunked(card_keys, 500):
        snapshots = await session.scalars(
            select(SellerWildberriesImportedCard).where(
                tuple_(
                    SellerWildberriesImportedCard.tenant_id,
                    SellerWildberriesImportedCard.seller_id,
                    SellerWildberriesImportedCard.nm_id,
                ).in_(batch)
            )
        )
        for snapshot in snapshots:
            if isinstance(snapshot.raw_json, dict):
                cards[(snapshot.tenant_id, snapshot.seller_id, snapshot.nm_id)] = snapshot.raw_json

    for line in lines:
        product = products_by_id.get(line.product_id)
        if product is None:
            line.size = None
            line.color = None
            continue
        raw = (
            cards.get((product.tenant_id, product.seller_id, product.wb_nm_id))
            if product.seller_id is not None and product.wb_nm_id is not None
            else None
        )
        saved_size = (product.wb_size or "").strip()
        line.size = saved_size or (
            size_from_card_for_barcode(raw, product.wb_barcode) if raw else None
        )
        line.color = color_from_card(raw) if raw else None
