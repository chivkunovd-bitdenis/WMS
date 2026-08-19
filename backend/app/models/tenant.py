from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, String, Time, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.background_job import BackgroundJob
    from app.models.inbound_intake import InboundIntakeRequest
    from app.models.inventory_balance import InventoryBalance
    from app.models.inventory_movement import InventoryMovement
    from app.models.notification import Notification
    from app.models.outbound_shipment import OutboundShipmentRequest
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
    address_storage_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
    )
    separate_marking_print_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        default=False,
    )
    # Управляет тем, обязателен ли этап упаковки перед раскладкой заказа по коробам.
    # По умолчанию True — сохраняет текущее поведение для всех тенантов; выключается
    # только явным решением владельца.
    fbs_packing_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
        default=True,
    )
    fbs_shipment_cutoff_time: Mapped[time | None] = mapped_column(
        Time(timezone=False),
        nullable=True,
    )
    # None deliberately keeps billing off for existing tenants.  It is set
    # when the tenant explicitly creates its first tariff version, rather
    # than backfilling already-finalised warehouse documents.
    billing_enabled_from: Mapped[date | None] = mapped_column(Date, nullable=True)
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
    inventory_movements: Mapped[list[InventoryMovement]] = relationship(
        "InventoryMovement",
        back_populates="tenant",
    )
    outbound_shipment_requests: Mapped[list[OutboundShipmentRequest]] = relationship(
        "OutboundShipmentRequest",
        back_populates="tenant",
    )
    background_jobs: Mapped[list[BackgroundJob]] = relationship(
        "BackgroundJob",
        back_populates="tenant",
    )
    notifications: Mapped[list[Notification]] = relationship(
        "Notification",
        back_populates="tenant",
    )
