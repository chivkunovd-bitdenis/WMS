from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.seller import Seller
    from app.models.tenant import Tenant


class ProductMarketplaceLink(Base):
    """One WMS product linked to one seller's product identity at a marketplace."""

    __tablename__ = "product_marketplace_links"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "seller_id",
            "product_id",
            "marketplace",
            name="uq_product_marketplace_links_product_provider",
        ),
        UniqueConstraint(
            "tenant_id",
            "seller_id",
            "marketplace",
            "external_product_id",
            name="uq_product_marketplace_links_external_product",
        ),
        Index(
            "ix_product_marketplace_links_lookup",
            "tenant_id",
            "seller_id",
            "marketplace",
            "external_offer_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    marketplace: Mapped[str] = mapped_column(String(32), nullable=False)
    external_product_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_offer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_sku: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    external_barcodes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    provider_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    seller: Mapped[Seller] = relationship("Seller")
    product: Mapped[Product] = relationship("Product")
