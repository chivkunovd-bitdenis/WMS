from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.pallet import Pallet
    from app.models.storage_location import StorageLocation
    from app.models.tenant import Tenant
    from app.models.warehouse import Warehouse


class WarehouseBox(Base):
    """Сквозной физический короб склада (ШК печатается на этикетке 58x40)."""

    __tablename__ = "warehouse_boxes"
    __table_args__ = (
        CheckConstraint(
            "container_kind IN ('box', 'cargo_place')",
            name="ck_warehouse_boxes_container_kind",
        ),
        UniqueConstraint(
            "tenant_id",
            "internal_barcode",
            name="uq_warehouse_boxes_tenant_barcode",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="CASCADE"),
        index=True,
    )
    inbound_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("inbound_intake_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    internal_barcode: Mapped[str] = mapped_column(String(64), nullable=False)
    container_kind: Mapped[Literal["box", "cargo_place"]] = mapped_column(
        String(32), nullable=False, default="box", server_default="box"
    )
    storage_location_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("storage_locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    pallet_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pallets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    warehouse: Mapped[Warehouse] = relationship("Warehouse")
    storage_location: Mapped[StorageLocation | None] = relationship("StorageLocation")
    pallet: Mapped[Pallet | None] = relationship(
        "Pallet", back_populates="warehouse_boxes"
    )
