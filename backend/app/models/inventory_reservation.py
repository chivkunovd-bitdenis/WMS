from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.outbound_shipment import OutboundShipmentLine
    from app.models.product import Product
    from app.models.storage_location import StorageLocation
    from app.models.tenant import Tenant
    from app.models.warehouse import Warehouse


class InventoryReservation(Base):
    """Резерв строки operational outbound: по ячейке или по складу (без ячейки)."""

    __tablename__ = "inventory_reservations"
    __table_args__ = (
        UniqueConstraint(
            "outbound_shipment_line_id",
            name="uq_inventory_reservation_line",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    outbound_shipment_line_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("outbound_shipment_lines.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        index=True,
    )
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    storage_location_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("storage_locations.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    tenant: Mapped[Tenant] = relationship("Tenant")
    outbound_line: Mapped[OutboundShipmentLine] = relationship(
        "OutboundShipmentLine",
        back_populates="inventory_reservation",
    )
    product: Mapped[Product] = relationship("Product")
    warehouse: Mapped[Warehouse | None] = relationship("Warehouse")
    storage_location: Mapped[StorageLocation | None] = relationship("StorageLocation")
