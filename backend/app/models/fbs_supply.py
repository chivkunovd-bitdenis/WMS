from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.fbs_order import FbsOrder
    from app.models.fbs_print_asset import FbsPrintAsset
    from app.models.fbs_trbx import FbsTrbx
    from app.models.seller import Seller
    from app.models.tenant import Tenant
    from app.models.warehouse import Warehouse

FBS_SUPPLY_STATUS_DRAFT = "draft"
FBS_SUPPLY_STATUS_ASSEMBLING = "assembling"
FBS_SUPPLY_STATUS_PACKED = "packed"
FBS_SUPPLY_STATUS_IN_DELIVERY = "in_delivery"
FBS_SUPPLY_STATUS_DONE = "done"

FBS_SUPPLY_SOURCE_WMS = "wms"
FBS_SUPPLY_SOURCE_WB = "wb"

FBS_DELIVERY_TYPE_WAREHOUSE_SC = "warehouse_sc"
FBS_DELIVERY_TYPE_PVZ = "pvz"

FBS_SUPPLY_SOURCE_WMS = "wms"
FBS_SUPPLY_SOURCE_WB = "wb"


class FbsSupply(Base):
    __tablename__ = "fbs_supplies"
    __table_args__ = (
        UniqueConstraint(
            "seller_id",
            "marketplace",
            "external_supply_id",
            name="uq_fbs_supplies_seller_marketplace_external_supply",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), index=True
    )
    marketplace: Mapped[str] = mapped_column(
        String(32), nullable=False, default="wb", server_default="wb", index=True
    )
    external_supply_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # Nullable in storage for Ozon; WB service paths establish a non-empty value
    # before calling WB-specific helpers.
    wb_supply_id: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=FBS_SUPPLY_SOURCE_WMS,
        server_default=FBS_SUPPLY_SOURCE_WMS,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=FBS_SUPPLY_STATUS_DRAFT,
        server_default=FBS_SUPPLY_STATUS_DRAFT,
    )
    delivery_type: Mapped[str] = mapped_column(String(32), nullable=False)
    cargo_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    wb_office_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    barcode_file: Mapped[str | None] = mapped_column(String(512), nullable=True)
    document_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    display_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    planned_destination_office_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    planned_destination_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    planned_destination_zone: Mapped[str | None] = mapped_column(String(128), nullable=True)
    planned_shipment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_wb_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    barcode_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        # The database FK is created in migration 0069 under this name.  Keep
        # it deferred in SQLAlchemy metadata: print assets point back to
        # supplies, so PostgreSQL needs an ALTER TABLE step when dropping the
        # test schema.
        ForeignKey(
            "fbs_print_assets.id",
            name="fk_fbs_supplies_barcode_asset_id",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
        index=True,
    )
    packaging_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("packaging_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at_wb: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    honest_sign_skipped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    honest_sign_skipped_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    boxes_without_distribution_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    boxes_without_distribution_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    seller: Mapped[Seller] = relationship("Seller")
    warehouse: Mapped[Warehouse] = relationship("Warehouse")
    orders: Mapped[list[FbsOrder]] = relationship(
        "FbsOrder",
        back_populates="supply",
    )
    trbxes: Mapped[list[FbsTrbx]] = relationship(
        "FbsTrbx",
        back_populates="supply",
        cascade="all, delete-orphan",
    )
    barcode_asset: Mapped[FbsPrintAsset | None] = relationship(
        "FbsPrintAsset",
        foreign_keys=[barcode_asset_id],
    )
    print_assets: Mapped[list[FbsPrintAsset]] = relationship(
        "FbsPrintAsset",
        back_populates="supply",
        foreign_keys="FbsPrintAsset.fbs_supply_id",
    )
