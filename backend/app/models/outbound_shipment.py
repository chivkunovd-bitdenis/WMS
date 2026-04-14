from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.inventory_movement import InventoryMovement
    from app.models.inventory_reservation import InventoryReservation
    from app.models.product import Product
    from app.models.seller import Seller
    from app.models.storage_location import StorageLocation
    from app.models.tenant import Tenant
    from app.models.warehouse import Warehouse


class OutboundShipmentRequest(Base):
    """Заявка на отгрузку: списание остатков из указанных ячеек."""

    __tablename__ = "outbound_shipment_requests"

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
    seller_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sellers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    tenant: Mapped[Tenant] = relationship(
        "Tenant", back_populates="outbound_shipment_requests"
    )
    warehouse: Mapped[Warehouse] = relationship(
        "Warehouse", back_populates="outbound_shipment_requests"
    )
    seller: Mapped[Seller | None] = relationship("Seller")
    lines: Mapped[list[OutboundShipmentLine]] = relationship(
        "OutboundShipmentLine",
        back_populates="request",
        cascade="all, delete-orphan",
    )


class OutboundShipmentLine(Base):
    __tablename__ = "outbound_shipment_lines"
    __table_args__ = (
        UniqueConstraint(
            "request_id", "product_id", name="uq_outbound_shipment_line_req_product"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("outbound_shipment_requests.id", ondelete="CASCADE"),
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    shipped_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_location_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("storage_locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    request: Mapped[OutboundShipmentRequest] = relationship(
        "OutboundShipmentRequest", back_populates="lines"
    )
    product: Mapped[Product] = relationship(
        "Product", back_populates="outbound_shipment_lines"
    )
    storage_location: Mapped[StorageLocation | None] = relationship(
        "StorageLocation", back_populates="outbound_shipment_lines"
    )
    inventory_movements: Mapped[list[InventoryMovement]] = relationship(
        "InventoryMovement",
        back_populates="outbound_line",
    )
    inventory_reservation: Mapped[InventoryReservation | None] = relationship(
        "InventoryReservation",
        back_populates="outbound_line",
        uselist=False,
        cascade="all, delete-orphan",
    )
