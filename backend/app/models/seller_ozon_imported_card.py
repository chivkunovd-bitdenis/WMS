from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.seller import Seller


class SellerOzonImportedCard(Base):
    """Snapshot of an Ozon card row from catalog import (per seller).

    WMS-548 D3: by the same reasoning as ``SellerWildberriesImportedCard`` —
    the seller must see every card of a connected marketplace, whether or not
    it is a WMS product yet, without a live API call each time. Ozon's own
    catalog import (``ozon_product_import_service``) writes here on every key
    save and sync; a card only becomes a product when the seller explicitly
    adds it (WMS-548 R12) or when it happens to match a product already on
    fulfillment (the "same physical item, two marketplaces" case, R13).
    """

    __tablename__ = "seller_ozon_imported_cards"
    __table_args__ = (
        UniqueConstraint(
            "seller_id", "ozon_product_id", name="uq_ozon_imported_card_seller_product"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), index=True
    )
    # Ozon's `id` (product_id) — the identifier stock publishing and
    # ProductMarketplaceLink.external_product_id already key off. Stored as
    # text like that column: Ozon ids are large integers we never do
    # arithmetic on, only compare and display.
    ozon_product_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    offer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    seller: Mapped[Seller] = relationship("Seller", back_populates="ozon_imported_cards")
