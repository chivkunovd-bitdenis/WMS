from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.inbound_intake import InboundIntakeRequest
    from app.models.inventory_balance import InventoryBalance
    from app.models.product import Product
    from app.models.seller import Seller
    from app.models.storage_location import StorageLocation
    from app.models.user import User
    from app.models.warehouse import Warehouse


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    users: Mapped[list[User]] = relationship("User", back_populates="tenant")
    sellers: Mapped[list[Seller]] = relationship("Seller", back_populates="tenant")
    warehouses: Mapped[list[Warehouse]] = relationship(
        "Warehouse", back_populates="tenant"
    )
    locations: Mapped[list[StorageLocation]] = relationship(
        "StorageLocation", back_populates="tenant"
    )
    products: Mapped[list[Product]] = relationship("Product", back_populates="tenant")
    inbound_intake_requests: Mapped[list[InboundIntakeRequest]] = relationship(
        "InboundIntakeRequest",
        back_populates="tenant",
    )
    inventory_balances: Mapped[list[InventoryBalance]] = relationship(
        "InventoryBalance",
        back_populates="tenant",
    )
