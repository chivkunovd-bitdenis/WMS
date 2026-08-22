from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.inventory_movement import InventoryMovement
    from app.models.product import Product
    from app.models.product_dimension_event import ProductDimensionEvent
    from app.models.seller import Seller
    from app.models.tenant import Tenant
    from app.models.warehouse import Warehouse


class StorageMeasurement(Base):
    """Immutable, non-financial measurement of storage for one product period."""

    __tablename__ = "storage_measurements"
    __table_args__ = (
        Index(
            "ix_storage_measurements_scope_period",
            "tenant_id",
            "seller_id",
            "warehouse_id",
            "period_start",
            "period_end",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    dimension_event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product_dimension_events.id", ondelete="RESTRICT"),
        nullable=True,
    )
    movement_start_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("inventory_movements.id", ondelete="RESTRICT"), nullable=True
    )
    movement_end_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("inventory_movements.id", ondelete="RESTRICT"), nullable=True
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    quantity_days: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    liter_days: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="calculated")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    seller: Mapped[Seller] = relationship("Seller")
    warehouse: Mapped[Warehouse] = relationship("Warehouse")
    product: Mapped[Product] = relationship("Product")
    dimension_event: Mapped[ProductDimensionEvent | None] = relationship("ProductDimensionEvent")
    movement_start: Mapped[InventoryMovement | None] = relationship(
        "InventoryMovement", foreign_keys=[movement_start_id]
    )
    movement_end: Mapped[InventoryMovement | None] = relationship(
        "InventoryMovement", foreign_keys=[movement_end_id]
    )
