from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, Uuid, func
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
        UniqueConstraint(
            "storage_location_id",
            "product_id",
            name="uq_inventory_balance_loc_product",
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
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
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
