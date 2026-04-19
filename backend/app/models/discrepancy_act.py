from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.inbound_intake import InboundIntakeLine

if TYPE_CHECKING:
    from app.models.inbound_intake import InboundIntakeRequest
    from app.models.product import Product
    from app.models.seller import Seller
    from app.models.tenant import Tenant


class DiscrepancyAct(Base):
    """Акт расхождения (product term: diverge). Строки и согласования — позже."""

    __tablename__ = "discrepancy_acts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    inbound_intake_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("inbound_intake_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    seller_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sellers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant")
    inbound_intake_request: Mapped[InboundIntakeRequest | None] = relationship(
        "InboundIntakeRequest",
    )
    seller: Mapped[Seller | None] = relationship("Seller")
    lines: Mapped[list[DiscrepancyActLine]] = relationship(
        "DiscrepancyActLine",
        back_populates="act",
        cascade="all, delete-orphan",
    )


class DiscrepancyActLine(Base):
    """Строка акта: расхождение по количеству (факт минус план в бизнес-смысле, позже)."""

    __tablename__ = "discrepancy_act_lines"
    __table_args__ = (
        UniqueConstraint(
            "act_id",
            "product_id",
            name="uq_discrepancy_act_line_act_product",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    act_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("discrepancy_acts.id", ondelete="CASCADE"),
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        index=True,
    )
    inbound_intake_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("inbound_intake_lines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    act: Mapped[DiscrepancyAct] = relationship("DiscrepancyAct", back_populates="lines")
    product: Mapped[Product] = relationship("Product")
    inbound_intake_line: Mapped[InboundIntakeLine | None] = relationship(
        "InboundIntakeLine",
    )
