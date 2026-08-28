from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.storage_location import StorageLocation
    from app.models.tenant import Tenant


class InventoryBalance(Base):
    """Остаток SKU в ячейке. Меняется только проведёнными операциями."""

    __tablename__ = "inventory_balances"
    __table_args__ = (
        CheckConstraint(
            "(container_kind IS NULL AND container_id IS NULL) OR "
            "(container_kind IS NOT NULL AND container_id IS NOT NULL)",
            name="ck_inventory_balance_container_pair",
        ),
        CheckConstraint(
            "container_kind IS NULL OR container_kind IN ('pallet', 'box', 'cargo_place')",
            name="ck_inventory_balance_container_kind",
        ),
        CheckConstraint("quantity >= 0", name="ck_inventory_balance_quantity_nonnegative"),
        CheckConstraint(
            "quantity_unpacked >= 0",
            name="ck_inventory_balance_quantity_unpacked_nonnegative",
        ),
        CheckConstraint(
            "quantity_packed >= 0",
            name="ck_inventory_balance_quantity_packed_nonnegative",
        ),
        Index(
            "uq_inventory_balance_loc_product_container",
            "storage_location_id",
            "product_id",
            text("coalesce(container_id, '00000000-0000-0000-0000-000000000000')"),
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    storage_location_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("storage_locations.id", ondelete="CASCADE"),
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        index=True,
    )
    container_kind: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    container_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_unpacked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quantity_packed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="inventory_balances")
    storage_location: Mapped[StorageLocation] = relationship(
        "StorageLocation", back_populates="inventory_balances"
    )
    product: Mapped[Product] = relationship(
        "Product", back_populates="inventory_balances"
    )
