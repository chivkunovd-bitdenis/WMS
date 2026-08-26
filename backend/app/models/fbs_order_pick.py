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
    from app.models.fbs_supply import FbsSupply
    from app.models.inventory_movement import InventoryMovement
    from app.models.product import Product
    from app.models.storage_location import StorageLocation
    from app.models.tenant import Tenant
    from app.models.user import User

PICK_EVENT_PICKED = "picked"
PICK_EVENT_UNDONE = "undone"
FBS_PICK_EVENT_TYPES = frozenset({PICK_EVENT_PICKED, PICK_EVENT_UNDONE})


class FbsOrderPick(Base):
    """Active 1:1 pick record per FBS order (undone picks remain for audit)."""

    __tablename__ = "fbs_order_picks"
    __table_args__ = (
        UniqueConstraint(
            "fbs_supply_id",
            "scan_idempotency_key",
            name="uq_fbs_order_picks_supply_scan_idempotency",
        ),
        Index(
            "uq_fbs_order_picks_active_order",
            "fbs_order_id",
            unique=True,
            postgresql_where=text("undone_at IS NULL"),
            sqlite_where=text("undone_at IS NULL"),
        ),
        Index("ix_fbs_order_picks_tenant_supply", "tenant_id", "fbs_supply_id"),
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
    fbs_supply_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_supplies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_storage_location_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("storage_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sorting_storage_location_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("storage_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    scanned_product_barcode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    picked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    picked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    inventory_movement_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("inventory_movements.id", ondelete="SET NULL"),
        nullable=True,
    )
    scan_idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    undone_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    order: Mapped[FbsOrder] = relationship("FbsOrder", back_populates="picks")
    supply: Mapped[FbsSupply] = relationship("FbsSupply")
    source_storage_location: Mapped[StorageLocation] = relationship(
        "StorageLocation",
        foreign_keys=[source_storage_location_id],
    )
    sorting_storage_location: Mapped[StorageLocation] = relationship(
        "StorageLocation",
        foreign_keys=[sorting_storage_location_id],
    )
    product: Mapped[Product] = relationship("Product")
    picked_by_user: Mapped[User | None] = relationship("User")
    inventory_movement: Mapped[InventoryMovement | None] = relationship(
        "InventoryMovement"
    )
    events: Mapped[list[FbsOrderPickEvent]] = relationship(
        "FbsOrderPickEvent",
        back_populates="pick",
        cascade="all, delete-orphan",
    )


class FbsOrderPickEvent(Base):
    """Append-only audit trail for pick and undo operations."""

    __tablename__ = "fbs_order_pick_events"
    __table_args__ = (
        Index(
            "uq_fbs_order_pick_events_undo_idempotency",
            "pick_id",
            "event_type",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    pick_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_order_picks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_storage_location_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("storage_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sorting_storage_location_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("storage_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    inventory_movement_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("inventory_movements.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    pick: Mapped[FbsOrderPick] = relationship("FbsOrderPick", back_populates="events")
    actor_user: Mapped[User | None] = relationship("User")
