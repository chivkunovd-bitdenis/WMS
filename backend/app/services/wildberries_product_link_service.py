"""Link internal Product rows to imported Wildberries card nm_id."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard


class WildberriesLinkError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


async def link_product_to_wb_card(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    product_id: uuid.UUID,
    nm_id: int,
) -> Product:
    p = await session.get(Product, product_id)
    if p is None or p.tenant_id != tenant_id:
        raise WildberriesLinkError("product_not_found")
    if p.seller_id is None:
        raise WildberriesLinkError("product_must_have_seller")
    if p.seller_id != seller_id:
        raise WildberriesLinkError("product_seller_mismatch")
    c_stmt = select(SellerWildberriesImportedCard).where(
        SellerWildberriesImportedCard.seller_id == seller_id,
        SellerWildberriesImportedCard.nm_id == nm_id,
    )
    c_res = await session.execute(c_stmt)
    card = c_res.scalar_one_or_none()
    if card is None:
        raise WildberriesLinkError("wb_card_not_found")
    taken = await session.execute(
        select(Product.id).where(
            Product.tenant_id == tenant_id,
            Product.wb_nm_id == nm_id,
            Product.id != product_id,
        )
    )
    if taken.scalar_one_or_none() is not None:
        raise WildberriesLinkError("wb_nm_already_linked")
    p.wb_nm_id = nm_id
    p.wb_vendor_code = card.vendor_code
    await session.commit()
    await session.refresh(p, attribute_names=["seller"])
    return p
