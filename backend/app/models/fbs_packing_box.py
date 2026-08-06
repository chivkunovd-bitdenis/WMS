from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.fbs_order import FbsOrder
    from app.models.fbs_supply import FbsSupply
    from app.models.user import User
    from app.models.warehouse_box import WarehouseBox


class FbsPackingBox(Base):
    """Local physical WMS box; never represents a WB cargo place itself."""

    __tablename__ = "fbs_packing_boxes"
    __table_args__ = (
        UniqueConstraint("supply_id", "box_number", name="uq_fbs_packing_boxes_supply_number"),
        UniqueConstraint("warehouse_box_id", name="uq_fbs_packing_boxes_warehouse_box"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    supply_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_supplies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    warehouse_box_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("warehouse_boxes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    box_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="open", server_default="open"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    supply: Mapped[FbsSupply] = relationship("FbsSupply")
    warehouse_box: Mapped[WarehouseBox] = relationship("WarehouseBox")
    items: Mapped[list[FbsPackingBoxItem]] = relationship(
        "FbsPackingBoxItem", back_populates="box", cascade="all, delete-orphan"
    )


class FbsPackingBoxItem(Base):
    """One FBS order/unit assigned to exactly one local physical box."""

    __tablename__ = "fbs_packing_box_items"
    __table_args__ = (UniqueConstraint("fbs_order_id", name="uq_fbs_packing_box_items_order"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    box_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_packing_boxes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fbs_order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    box: Mapped[FbsPackingBox] = relationship("FbsPackingBox", back_populates="items")
    order: Mapped[FbsOrder] = relationship("FbsOrder")
    assigned_by_user: Mapped[User | None] = relationship("User")
