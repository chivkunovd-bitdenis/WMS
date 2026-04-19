from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.seller import Seller
    from app.models.tenant import Tenant
    from app.models.warehouse import Warehouse


class MarketplaceUnloadRequest(Base):
    """Выгрузка на склад маркетплейса (product term: download) — заголовок документа."""

    __tablename__ = "marketplace_unload_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="CASCADE"),
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
    warehouse: Mapped[Warehouse] = relationship("Warehouse")
    seller: Mapped[Seller | None] = relationship("Seller")
    lines: Mapped[list[MarketplaceUnloadLine]] = relationship(
        "MarketplaceUnloadLine",
        back_populates="request",
        cascade="all, delete-orphan",
    )


class MarketplaceUnloadLine(Base):
    __tablename__ = "marketplace_unload_lines"
    __table_args__ = (
        UniqueConstraint(
            "request_id",
            "product_id",
            name="uq_marketplace_unload_line_req_product",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("marketplace_unload_requests.id", ondelete="CASCADE"),
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    request: Mapped[MarketplaceUnloadRequest] = relationship(
        "MarketplaceUnloadRequest",
        back_populates="lines",
    )
    product: Mapped[Product] = relationship("Product")
