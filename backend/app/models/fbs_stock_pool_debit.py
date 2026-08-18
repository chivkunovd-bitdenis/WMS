from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.fbs_binding_stock_pool import FbsBindingStockPool
    from app.models.fbs_order import FbsOrder


class FbsStockPoolDebit(Base):
    """Idempotency ledger: one row per FBS order whose arrival has already been
    processed against fbs_binding_stock_pools.

    WB re-sends the same order on every autopoll pass and on every manual sync
    click. The UNIQUE constraint on order_id is what guarantees a given order
    can debit its pool at most once, no matter how many times it is seen --
    the debit function checks for an existing row first, and the constraint
    is the hard backstop against a race between a concurrent manual sync and
    an autopoll run touching the same order at the same time.
    """

    __tablename__ = "fbs_stock_pool_debits"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_fbs_stock_pool_debits_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pool_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_binding_stock_pools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fbs_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    quantity_debited: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_shortfall: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    pool: Mapped[FbsBindingStockPool] = relationship("FbsBindingStockPool")
    order: Mapped[FbsOrder] = relationship("FbsOrder")
