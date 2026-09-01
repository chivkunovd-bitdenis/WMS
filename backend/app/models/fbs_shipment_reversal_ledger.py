from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
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
    from app.models.fbs_order import FbsOrder
    from app.models.fbs_wb_operation import FbsWbOperation
    from app.models.inventory_movement import InventoryMovement
    from app.models.product import Product
    from app.models.storage_location import StorageLocation
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.warehouse import Warehouse


class FbsShipmentReversalLedger(Base):
    """One physical FBS shipment unit and its at-most-once reversal."""

    __tablename__ = "fbs_shipment_reversal_ledger"
    __table_args__ = (
        UniqueConstraint("fbs_order_id", name="uq_fbs_shipment_reversal_order"),
        UniqueConstraint(
            "shipment_movement_id",
            name="uq_fbs_shipment_reversal_movement",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    fbs_order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fbs_orders.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT")
    )
    storage_location_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("storage_locations.id", ondelete="RESTRICT")
    )
    source_warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    container_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    container_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    source_mode: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    shortage_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    negative_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    ozon_positions_json: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    wb_operation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_wb_operations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    written_off_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    written_off_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    shipment_movement_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("inventory_movements.id", ondelete="SET NULL"),
        nullable=True,
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reversal_movement_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("inventory_movements.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    order: Mapped[FbsOrder] = relationship("FbsOrder")
    product: Mapped[Product] = relationship("Product")
    storage_location: Mapped[StorageLocation] = relationship("StorageLocation")
    source_warehouse: Mapped[Warehouse | None] = relationship("Warehouse")
    wb_operation: Mapped[FbsWbOperation | None] = relationship("FbsWbOperation")
    written_off_by_user: Mapped[User | None] = relationship("User")
    shipment_movement: Mapped[InventoryMovement | None] = relationship(
        "InventoryMovement",
        foreign_keys=[shipment_movement_id],
    )
    reversal_movement: Mapped[InventoryMovement | None] = relationship(
        "InventoryMovement",
        foreign_keys=[reversal_movement_id],
    )
