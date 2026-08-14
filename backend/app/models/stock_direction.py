from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.tenant import Tenant


class StockDirection(Base):
    """Seller-managed allocation of a product's physical stock."""

    __tablename__ = "stock_directions"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_stock_directions_quantity_nonnegative"),
        Index("ix_stock_directions_tenant_product", "tenant_id", "product_id"),
        Index("ix_stock_directions_tenant_product_fbs", "tenant_id", "product_id", "is_fbs"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_fbs: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    product: Mapped[Product] = relationship("Product", back_populates="stock_directions")


class StockMonthlySnapshot(Base):
    """Stock distribution captured for the first day of a month."""

    __tablename__ = "stock_monthly_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "product_id",
            "snapshot_month",
            name="uq_stock_monthly_snapshot_product_month",
        ),
        CheckConstraint("quantity_total >= 0", name="ck_stock_monthly_total_nonnegative"),
        CheckConstraint("quantity_fbs >= 0", name="ck_stock_monthly_fbs_nonnegative"),
        CheckConstraint(
            "quantity_reserved >= 0", name="ck_stock_monthly_reserved_nonnegative"
        ),
        CheckConstraint("quantity_free_fbo >= 0", name="ck_stock_monthly_free_nonnegative"),
        Index("ix_stock_monthly_snapshots_tenant_month", "tenant_id", "snapshot_month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    snapshot_month: Mapped[date] = mapped_column(Date, nullable=False)
    quantity_total: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_fbs: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_reserved: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_free_fbo: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    product: Mapped[Product] = relationship("Product")
