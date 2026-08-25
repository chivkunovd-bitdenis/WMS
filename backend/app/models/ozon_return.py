from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
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
    from app.models.inbound_intake import InboundIntakeRequest
    from app.models.product import Product


class InboundOzonReturnGiveout(Base):
    """One Ozon return giveout imported for an inbound intake request."""

    __tablename__ = "inbound_ozon_return_giveouts"
    __table_args__ = (
        UniqueConstraint(
            "request_id",
            "giveout_id",
            name="uq_inbound_ozon_return_giveout_request",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("inbound_intake_requests.id", ondelete="CASCADE"),
        index=True,
    )
    giveout_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    giveout_status: Mapped[str] = mapped_column(String(64), nullable=False)
    warehouse_external_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    warehouse_name: Mapped[str] = mapped_column(String(255), nullable=False)
    warehouse_address: Mapped[str] = mapped_column(String(512), nullable=False)
    approved_articles_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_articles_count: Mapped[int] = mapped_column(Integer, nullable=False)
    route_position: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    storage_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    utilization_forecast_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    provider_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    request: Mapped[InboundIntakeRequest] = relationship(
        "InboundIntakeRequest", back_populates="ozon_return_giveouts"
    )
    items: Mapped[list[InboundOzonReturnItem]] = relationship(
        "InboundOzonReturnItem",
        back_populates="giveout",
        cascade="all, delete-orphan",
    )


class InboundOzonReturnItem(Base):
    """One Ozon return item within a giveout imported for inbound processing."""

    __tablename__ = "inbound_ozon_return_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_inbound_ozon_return_item_quantity_positive"),
        UniqueConstraint(
            "giveout_record_id",
            "source_key",
            name="uq_inbound_ozon_return_item_source",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("inbound_intake_requests.id", ondelete="CASCADE"),
        index=True,
    )
    giveout_record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("inbound_ozon_return_giveouts.id", ondelete="CASCADE"),
    )
    inbound_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("inbound_intake_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    source_key: Mapped[str] = mapped_column(String(255), nullable=False)
    external_return_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    posting_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    return_barcode: Mapped[str | None] = mapped_column(String(255), nullable=True)
    return_reason_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    return_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    offer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ozon_sku: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    product_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    provider_data_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    giveout: Mapped[InboundOzonReturnGiveout] = relationship(
        "InboundOzonReturnGiveout", back_populates="items"
    )
    product: Mapped[Product | None] = relationship("Product")
