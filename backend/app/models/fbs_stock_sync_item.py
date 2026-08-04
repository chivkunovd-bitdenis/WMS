from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
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
    from app.models.fbs_warehouse_binding import FbsWarehouseBinding
    from app.models.product import Product

STOCK_SYNC_STATUS_PENDING = "pending"
STOCK_SYNC_STATUS_CONFIRMED = "confirmed"
STOCK_SYNC_STATUS_ERROR = "error"
STOCK_SYNC_STATUS_CONFLICT = "conflict"

FBS_STOCK_SYNC_STATUSES = frozenset(
    {
        STOCK_SYNC_STATUS_PENDING,
        STOCK_SYNC_STATUS_CONFIRMED,
        STOCK_SYNC_STATUS_ERROR,
        STOCK_SYNC_STATUS_CONFLICT,
    }
)


class FbsStockSyncItem(Base):
    """Per-chrtId stock sync state for one WB warehouse binding."""

    __tablename__ = "fbs_stock_sync_items"
    __table_args__ = (
        UniqueConstraint(
            "binding_id",
            "chrt_id",
            name="uq_fbs_stock_sync_items_binding_chrt",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    binding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_warehouse_bindings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    chrt_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    last_target_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_confirmed_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=STOCK_SYNC_STATUS_PENDING,
        server_default=STOCK_SYNC_STATUS_PENDING,
    )
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    binding: Mapped[FbsWarehouseBinding] = relationship(
        "FbsWarehouseBinding", back_populates="sync_items"
    )
    product: Mapped[Product | None] = relationship("Product")
