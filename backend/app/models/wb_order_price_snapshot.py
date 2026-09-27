"""WMS-517: append-only WB final price observations, without currency guesses."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, event
from sqlalchemy.engine import Connection
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import Mapped, Mapper, mapped_column
from sqlalchemy.types import TypeDecorator

from app.models.base import Base


class RawPriceValue(TypeDecorator[Any]):
    """JSON in TEXT avoids SQLite numeric affinity rounding large JSON scalars."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        return None if value is None else json.dumps(value, ensure_ascii=False, allow_nan=False)

    def process_result_value(self, value: str | None, dialect: Dialect) -> Any:
        return None if value is None else json.loads(value)


class WbOrderPriceSnapshot(Base):
    __tablename__ = "wb_order_price_snapshots"
    __table_args__ = (
        UniqueConstraint("order_id", "revision", name="uq_wb_order_price_revision"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("fbs_orders.id", ondelete="RESTRICT"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    # Raw JSON scalars deliberately preserve wrong types and out-of-range integers.
    # Coercing/truncating them here would erase the reason a CIS cannot be submitted.
    final_price: Mapped[Any] = mapped_column(RawPriceValue(), nullable=True)
    currency_code: Mapped[Any] = mapped_column(RawPriceValue(), nullable=True)
    converted_final_price: Mapped[Any] = mapped_column(RawPriceValue(), nullable=True)
    converted_currency_code: Mapped[Any] = mapped_column(RawPriceValue(), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@event.listens_for(WbOrderPriceSnapshot, "before_update")
@event.listens_for(WbOrderPriceSnapshot, "before_delete")
def _reject_snapshot_mutation(
    mapper: Mapper[WbOrderPriceSnapshot], connection: Connection, target: WbOrderPriceSnapshot
) -> None:
    raise ValueError("wb_price_snapshot_is_immutable")
