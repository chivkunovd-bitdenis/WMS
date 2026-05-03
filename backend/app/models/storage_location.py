from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.inbound_intake import InboundIntakeLine
    from app.models.inventory_balance import InventoryBalance
    from app.models.inventory_movement import InventoryMovement
    from app.models.outbound_shipment import OutboundShipmentLine
    from app.models.tenant import Tenant
    from app.models.warehouse import Warehouse


class StorageLocation(Base):
    __tablename__ = "storage_locations"
    __table_args__ = (
        UniqueConstraint(
            "warehouse_id", "code", name="uq_storage_locations_wh_code"
        ),
        UniqueConstraint(
            "tenant_id", "barcode", name="uq_storage_locations_tenant_barcode"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    barcode: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="locations")
    warehouse: Mapped[Warehouse] = relationship(
        "Warehouse", back_populates="locations"
    )
    inventory_balances: Mapped[list[InventoryBalance]] = relationship(
        "InventoryBalance",
        back_populates="storage_location",
    )
    inventory_movements: Mapped[list[InventoryMovement]] = relationship(
        "InventoryMovement",
        back_populates="storage_location",
    )
    inbound_intake_lines: Mapped[list[InboundIntakeLine]] = relationship(
        "InboundIntakeLine",
        back_populates="storage_location",
    )
    outbound_shipment_lines: Mapped[list[OutboundShipmentLine]] = relationship(
        "OutboundShipmentLine",
        back_populates="storage_location",
    )
