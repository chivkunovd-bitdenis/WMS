from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.storage_location import StorageLocation
    from app.models.warehouse import Warehouse


class WarehouseStorageRack(Base):
    __tablename__ = "warehouse_storage_racks"
    __table_args__ = (
        UniqueConstraint(
            "warehouse_id",
            "name",
            name="uq_warehouse_storage_racks_wh_name",
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
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    warehouse: Mapped[Warehouse] = relationship(
        "Warehouse", back_populates="storage_racks"
    )
    locations: Mapped[list[StorageLocation]] = relationship(
        "StorageLocation",
        back_populates="rack",
    )
