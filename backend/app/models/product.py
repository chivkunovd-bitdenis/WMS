from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.inbound_intake import InboundIntakeLine
    from app.models.inventory_balance import InventoryBalance
    from app.models.inventory_movement import InventoryMovement
    from app.models.outbound_shipment import OutboundShipmentLine
    from app.models.seller import Seller
    from app.models.tenant import Tenant


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sku_code", name="uq_products_tenant_sku"),
        UniqueConstraint("tenant_id", "wb_barcode", name="uq_products_tenant_wb_barcode"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    seller_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sellers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku_code: Mapped[str] = mapped_column(String(128), nullable=False)
    wb_nm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    wb_vendor_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    wb_chrt_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    wb_barcode: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    wb_size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    length_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    packaging_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_honest_sign: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="products")
    seller: Mapped[Seller | None] = relationship("Seller", back_populates="products")
    inbound_intake_lines: Mapped[list[InboundIntakeLine]] = relationship(
        "InboundIntakeLine",
        back_populates="product",
    )
    inventory_balances: Mapped[list[InventoryBalance]] = relationship(
        "InventoryBalance",
        back_populates="product",
    )
    inventory_movements: Mapped[list[InventoryMovement]] = relationship(
        "InventoryMovement",
        back_populates="product",
    )
    outbound_shipment_lines: Mapped[list[OutboundShipmentLine]] = relationship(
        "OutboundShipmentLine",
        back_populates="product",
    )
