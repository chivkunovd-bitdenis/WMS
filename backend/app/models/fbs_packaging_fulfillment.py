from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
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
    from app.models.inventory_movement import InventoryMovement
    from app.models.packaging_task import PackagingTask, PackagingTaskLine
    from app.models.tenant import Tenant
    from app.models.user import User


class FbsPackagingFulfillment(Base):
    """Links one physical packaging unit to exactly one FBS order."""

    __tablename__ = "fbs_packaging_fulfillments"
    __table_args__ = (
        UniqueConstraint(
            "packaging_task_id",
            "pack_idempotency_key",
            name="uq_fbs_packaging_fulfillments_task_idempotency",
        ),
        Index(
            "uq_fbs_packaging_fulfillments_active_order",
            "fbs_order_id",
            unique=True,
            postgresql_where=text("undone_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    fbs_order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    packaging_task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("packaging_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    packaging_task_line_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("packaging_task_lines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fulfilled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    fulfilled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    inventory_movement_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("inventory_movements.id", ondelete="SET NULL"),
        nullable=True,
    )
    pack_idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    undone_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    order: Mapped[FbsOrder] = relationship("FbsOrder", back_populates="packaging_fulfillments")
    packaging_task: Mapped[PackagingTask] = relationship(
        "PackagingTask", back_populates="fbs_fulfillments"
    )
    packaging_task_line: Mapped[PackagingTaskLine] = relationship(
        "PackagingTaskLine", back_populates="fbs_fulfillments"
    )
    fulfilled_by_user: Mapped[User | None] = relationship("User")
    inventory_movement: Mapped[InventoryMovement | None] = relationship(
        "InventoryMovement"
    )
