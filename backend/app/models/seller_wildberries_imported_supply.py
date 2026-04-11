from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    BigInteger,
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
    from app.models.seller import Seller


class SellerWildberriesImportedSupply(Base):
    """Snapshot of a WB FBW supply row (per seller)."""

    __tablename__ = "seller_wildberries_imported_supplies"
    __table_args__ = (
        UniqueConstraint("seller_id", "external_key", name="uq_wb_imported_supply_seller_key"),
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
    external_key: Mapped[str] = mapped_column(String(64), nullable=False)
    wb_supply_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    wb_preorder_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    seller: Mapped[Seller] = relationship("Seller", back_populates="wildberries_imported_supplies")
