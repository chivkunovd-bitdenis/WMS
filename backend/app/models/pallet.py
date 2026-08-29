from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.inbound_intake import InboundIntakeBox, InboundIntakeCargoPlace
    from app.models.storage_location import StorageLocation
    from app.models.tenant import Tenant
    from app.models.warehouse import Warehouse
    from app.models.warehouse_box import WarehouseBox


class Pallet(Base):
    """Tenant-owned warehouse pallet grouping boxes and cargo places."""

    __tablename__ = "pallets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_pallets_tenant_code"),
        UniqueConstraint("tenant_id", "barcode", name="uq_pallets_tenant_barcode"),
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
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    barcode: Mapped[str] = mapped_column(String(64), nullable=False)
    free_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_location_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("storage_locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    disbanded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    warehouse: Mapped[Warehouse] = relationship("Warehouse")
    storage_location: Mapped[StorageLocation | None] = relationship("StorageLocation")
    boxes: Mapped[list[InboundIntakeBox]] = relationship(
        "InboundIntakeBox", back_populates="pallet"
    )
    cargo_places: Mapped[list[InboundIntakeCargoPlace]] = relationship(
        "InboundIntakeCargoPlace", back_populates="pallet"
    )
    warehouse_boxes: Mapped[list[WarehouseBox]] = relationship(
        "WarehouseBox", back_populates="pallet"
    )
