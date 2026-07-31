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
    from app.models.fbs_supply import FbsSupply
    from app.models.fbs_trbx import FbsTrbx
    from app.models.marking_code import MarkingCode
    from app.models.product import Product
    from app.models.seller import Seller
    from app.models.tenant import Tenant
    from app.models.warehouse import Warehouse

MAPPING_STATUS_MAPPED = "mapped"
MAPPING_STATUS_MISSING = "missing"

RESERVE_STATUS_RESERVED = "reserved"
RESERVE_STATUS_NO_STOCK = "no_stock"
RESERVE_STATUS_RELEASED = "released"
RESERVE_STATUS_SKIPPED_NO_PRODUCT = "skipped_no_product"

FBS_ORDER_STATUS_NEW = "new"
FBS_ORDER_STATUS_IN_SUPPLY = "in_supply"
FBS_ORDER_STATUS_ASSEMBLING = "assembling"
FBS_ORDER_STATUS_PACKED = "packed"
FBS_ORDER_STATUS_IN_DELIVERY = "in_delivery"
FBS_ORDER_STATUS_SORTED = "sorted"
FBS_ORDER_STATUS_CANCELLED = "cancelled"
FBS_ORDER_STATUS_DONE = "done"
FBS_ORDER_STATUS_DEFECT = "defect"

FBS_ORDER_MARKING_WRITE_STATUSES = frozenset(
    {
        FBS_ORDER_STATUS_NEW,
        FBS_ORDER_STATUS_IN_SUPPLY,
        FBS_ORDER_STATUS_ASSEMBLING,
        FBS_ORDER_STATUS_PACKED,
    }
)
FBS_ORDER_MARKING_FROZEN_STATUSES = frozenset(
    {
        FBS_ORDER_STATUS_IN_DELIVERY,
        FBS_ORDER_STATUS_CANCELLED,
        FBS_ORDER_STATUS_DONE,
    }
)

MARKING_KIND_SGTIN = "sgtin"
MARKING_KIND_UIN = "uin"
MARKING_KIND_IMEI = "imei"
MARKING_KIND_GTIN = "gtin"
FBS_MARKING_KINDS = frozenset(
    {MARKING_KIND_SGTIN, MARKING_KIND_UIN, MARKING_KIND_IMEI, MARKING_KIND_GTIN}
)

CHECK_STATUS_NEW = "new"
CHECK_STATUS_CHECKING = "checking"
CHECK_STATUS_OK = "ok"
CHECK_STATUS_ERROR = "error"
CHECK_STATUS_NO_CHECK = "no_check"
FBS_MARKING_CHECK_STATUSES = frozenset(
    {
        CHECK_STATUS_NEW,
        CHECK_STATUS_CHECKING,
        CHECK_STATUS_OK,
        CHECK_STATUS_ERROR,
        CHECK_STATUS_NO_CHECK,
    }
)


class FbsOrder(Base):
    __tablename__ = "fbs_orders"
    __table_args__ = (
        UniqueConstraint("seller_id", "wb_order_id", name="uq_fbs_orders_seller_wb_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    wb_order_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    wb_rid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    wb_nm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    wb_chrt_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    wb_article: Mapped[str | None] = mapped_column(String(255), nullable=True)
    wb_barcode: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_legal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    cargo_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    wb_office_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    can_pvz: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    supply_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_supplies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sticker_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sticker_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    trbx_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_trbxes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=FBS_ORDER_STATUS_NEW, server_default="new"
    )
    wb_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at_wb: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    mapping_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reserve_status: Mapped[str] = mapped_column(String(32), nullable=False)
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
    seller: Mapped[Seller] = relationship("Seller")
    warehouse: Mapped[Warehouse] = relationship("Warehouse")
    product: Mapped[Product | None] = relationship("Product")
    supply: Mapped[FbsSupply | None] = relationship("FbsSupply", back_populates="orders")
    trbx: Mapped[FbsTrbx | None] = relationship("FbsTrbx", back_populates="orders")
    markings: Mapped[list[FbsOrderMarking]] = relationship(
        "FbsOrderMarking",
        back_populates="order",
        cascade="all, delete-orphan",
    )
    reservation: Mapped[FbsOrderReservation | None] = relationship(
        "FbsOrderReservation",
        back_populates="order",
        uselist=False,
        cascade="all, delete-orphan",
    )


class FbsOrderMarking(Base):
    __tablename__ = "fbs_order_markings"
    __table_args__ = (
        UniqueConstraint(
            "order_id",
            "kind",
            "value",
            name="uq_fbs_order_markings_order_kind_value",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    check_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="new", server_default="new"
    )
    marking_code_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("marking_codes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    order: Mapped[FbsOrder] = relationship("FbsOrder", back_populates="markings")
    marking_code: Mapped[MarkingCode | None] = relationship("MarkingCode")


class FbsOrderReservation(Base):
    """Warehouse-level reserve for an FBS order (1:1)."""

    __tablename__ = "fbs_order_reservations"
    __table_args__ = (
        UniqueConstraint("fbs_order_id", name="uq_fbs_order_reservation_order"),
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
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        index=True,
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="CASCADE"),
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    tenant: Mapped[Tenant] = relationship("Tenant")
    order: Mapped[FbsOrder] = relationship("FbsOrder", back_populates="reservation")
    product: Mapped[Product] = relationship("Product")
    warehouse: Mapped[Warehouse] = relationship("Warehouse")
