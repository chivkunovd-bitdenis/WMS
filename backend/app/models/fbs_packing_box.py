"""Persistent physical FBS boxes and their packed-order membership."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.fbs_order import FbsOrder
    from app.models.fbs_supply import FbsSupply
    from app.models.fbs_trbx import FbsTrbx
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.warehouse_box import WarehouseBox


class FbsPackingBox(Base):
    __tablename__ = "fbs_packing_boxes"
    __table_args__ = (
        UniqueConstraint("supply_id", "box_number", name="uq_fbs_packing_boxes_supply_number"),
        UniqueConstraint("warehouse_box_id", name="uq_fbs_packing_boxes_warehouse_box"),
        UniqueConstraint("trbx_id", name="uq_fbs_packing_boxes_trbx"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    supply_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fbs_supplies.id", ondelete="CASCADE"), index=True
    )
    warehouse_box_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouse_boxes.id", ondelete="RESTRICT"), index=True
    )
    trbx_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_trbxes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    box_number: Mapped[int] = mapped_column(Integer, nullable=False)
    creation_idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_without_distribution: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    supply: Mapped[FbsSupply] = relationship("FbsSupply")
    warehouse_box: Mapped[WarehouseBox] = relationship("WarehouseBox")
    trbx: Mapped[FbsTrbx | None] = relationship("FbsTrbx")
    items: Mapped[list[FbsPackingBoxItem]] = relationship(
        "FbsPackingBoxItem", back_populates="box", cascade="all, delete-orphan"
    )


class FbsPackingBoxItem(Base):
    __tablename__ = "fbs_packing_box_items"
    __table_args__ = (
        Index(
            "uq_fbs_packing_box_items_order_position",
            "fbs_order_id",
            text("coalesce(order_product_id, '00000000-0000-0000-0000-000000000000')"),
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    box_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fbs_packing_boxes.id", ondelete="CASCADE"), index=True
    )
    fbs_order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fbs_orders.id", ondelete="CASCADE"), index=True
    )
    assigned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    order_product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_order_products.id", ondelete="CASCADE"),
        nullable=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    box: Mapped[FbsPackingBox] = relationship("FbsPackingBox", back_populates="items")
    order: Mapped[FbsOrder] = relationship("FbsOrder")
    assigned_by_user: Mapped[User | None] = relationship("User")
