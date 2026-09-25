from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
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


class ProductBarcode(Base):
    __tablename__ = "product_barcodes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "seller_id", "product_id"],
            ["products.tenant_id", "products.seller_id", "products.id"],
            name="fk_product_barcodes_product_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id",
            "seller_id",
            "barcode",
            name="uq_product_barcodes_tenant_seller_barcode",
        ),
        Index("ix_product_barcodes_product_id", "product_id"),
        Index("ix_product_barcodes_tenant_barcode", "tenant_id", "barcode"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sellers.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    barcode: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="wb", server_default="wb"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant", viewonly=True)
    seller: Mapped[Seller] = relationship("Seller", viewonly=True)
    product: Mapped[Product] = relationship("Product", viewonly=True)
