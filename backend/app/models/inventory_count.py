from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.inventory_movement import InventoryMovement
    from app.models.product import Product
    from app.models.seller import Seller
    from app.models.storage_location import StorageLocation
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.warehouse import Warehouse


class InventoryCount(Base):
    """Документ, фиксирующий системный и фактический остаток товаров."""

    __tablename__ = "inventory_counts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    seller_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sellers.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant: Mapped[Tenant] = relationship("Tenant")
    warehouse: Mapped[Warehouse | None] = relationship("Warehouse")
    seller: Mapped[Seller | None] = relationship("Seller")
    created_by: Mapped[User] = relationship("User", foreign_keys=[created_by_user_id])
    posted_by: Mapped[User | None] = relationship("User", foreign_keys=[posted_by_user_id])
    lines: Mapped[list[InventoryCountLine]] = relationship(
        "InventoryCountLine",
        back_populates="count",
        cascade="all, delete-orphan",
        order_by="InventoryCountLine.id",
    )


class InventoryCountLine(Base):
    """Одна пересчитываемая позиция шага 1: товар в ячейке."""

    __tablename__ = "inventory_count_lines"
    __table_args__ = (
        Index(
            "uq_inventory_count_line_scope",
            "count_id",
            text("COALESCE(storage_location_id, '00000000-0000-0000-0000-000000000000')"),
            text("COALESCE(container_kind, '')"),
            text("COALESCE(container_id, '00000000-0000-0000-0000-000000000000')"),
            "product_id",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    count_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("inventory_counts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    storage_location_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("storage_locations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    container_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    container_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    expected_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    posted_delta: Mapped[int | None] = mapped_column(Integer, nullable=True)

    count: Mapped[InventoryCount] = relationship("InventoryCount", back_populates="lines")
    product: Mapped[Product] = relationship("Product")
    storage_location: Mapped[StorageLocation | None] = relationship("StorageLocation")
    movements: Mapped[list[InventoryMovement]] = relationship(
        "InventoryMovement",
        back_populates="inventory_count_line",
    )
