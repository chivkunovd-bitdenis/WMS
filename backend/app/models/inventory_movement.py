from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# Типы движений (строка для расширяемости).
MOVEMENT_TYPE_INBOUND_INTAKE = "inbound_intake"
MOVEMENT_TYPE_STOCK_TRANSFER_OUT = "stock_transfer_out"
MOVEMENT_TYPE_STOCK_TRANSFER_IN = "stock_transfer_in"
MOVEMENT_TYPE_OUTBOUND_SHIPMENT = "outbound_shipment"

if TYPE_CHECKING:
    from app.models.inbound_intake import InboundIntakeLine
    from app.models.outbound_shipment import OutboundShipmentLine
    from app.models.product import Product
    from app.models.storage_location import StorageLocation
    from app.models.tenant import Tenant


class InventoryMovement(Base):
    """Журнал движений. delta > 0 — приход в ячейку; delta < 0 — расход."""

    __tablename__ = "inventory_movements"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        index=True,
    )
    storage_location_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("storage_locations.id", ondelete="CASCADE"),
        index=True,
    )
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    movement_type: Mapped[str] = mapped_column(String(64), nullable=False)
    inbound_intake_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("inbound_intake_lines.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    outbound_shipment_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("outbound_shipment_lines.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    transfer_group_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="inventory_movements")
    product: Mapped[Product] = relationship(
        "Product", back_populates="inventory_movements"
    )
    storage_location: Mapped[StorageLocation] = relationship(
        "StorageLocation", back_populates="inventory_movements"
    )
    inbound_line: Mapped[InboundIntakeLine | None] = relationship(
        "InboundIntakeLine",
        back_populates="inventory_movements",
    )
    outbound_line: Mapped[OutboundShipmentLine | None] = relationship(
        "OutboundShipmentLine",
        back_populates="inventory_movements",
    )
