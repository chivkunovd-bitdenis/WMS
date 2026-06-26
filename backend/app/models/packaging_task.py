from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.inbound_intake import InboundIntakeRequest
    from app.models.marketplace_unload import MarketplaceUnloadLine, MarketplaceUnloadRequest
    from app.models.marking_code import MarkingCode
    from app.models.product import Product
    from app.models.storage_location import StorageLocation
    from app.models.tenant import Tenant
    from app.models.warehouse import Warehouse

STATUS_DRAFT = "draft"
STATUS_IN_PROGRESS = "in_progress"
STATUS_DONE = "done"
STATUS_CANCELLED = "cancelled"


class PackagingTask(Base):
    __tablename__ = "packaging_tasks"
    __table_args__ = (
        UniqueConstraint(
            "marketplace_unload_request_id",
            name="uq_packaging_task_marketplace_unload",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=STATUS_DRAFT)
    pick_resync_warning: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    marketplace_unload_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("marketplace_unload_requests.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    inbound_intake_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("inbound_intake_requests.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    billing_units_packed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    billing_rate_kopecks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    billing_earned_kopecks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    document_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    warehouse: Mapped[Warehouse] = relationship("Warehouse")
    marketplace_unload_request: Mapped[MarketplaceUnloadRequest | None] = relationship(
        "MarketplaceUnloadRequest",
        back_populates="packaging_task",
    )
    inbound_intake_request: Mapped[InboundIntakeRequest | None] = relationship(
        "InboundIntakeRequest"
    )
    lines: Mapped[list[PackagingTaskLine]] = relationship(
        "PackagingTaskLine",
        back_populates="task",
        cascade="all, delete-orphan",
    )


class PackagingTaskLine(Base):
    __tablename__ = "packaging_task_lines"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "product_id",
            "storage_location_id",
            name="uq_packaging_task_line_task_product_loc",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("packaging_tasks.id", ondelete="CASCADE"),
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE")
    )
    storage_location_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("storage_locations.id", ondelete="CASCADE"),
    )
    qty_total: Mapped[int] = mapped_column(Integer, nullable=False)
    qty_suggested_packed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qty_confirmed_packed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qty_packed_in_task: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qty_marking_printed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    marketplace_unload_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("marketplace_unload_lines.id", ondelete="SET NULL"),
        nullable=True,
    )

    task: Mapped[PackagingTask] = relationship("PackagingTask", back_populates="lines")
    product: Mapped[Product] = relationship("Product")
    storage_location: Mapped[StorageLocation] = relationship("StorageLocation")
    marketplace_unload_line: Mapped[MarketplaceUnloadLine | None] = relationship(
        "MarketplaceUnloadLine"
    )
    marking_codes: Mapped[list[MarkingCode]] = relationship(
        "MarkingCode",
        back_populates="packaging_task_line",
    )
