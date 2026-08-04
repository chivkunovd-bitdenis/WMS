"""SQLite-backed FBS stocks persistence for marketplace emulator."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Integer, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from wb_emulator.models import Base


class StockRow(Base):
    __tablename__ = "emu_stocks"
    __table_args__ = (
        UniqueConstraint(
            "seller_key",
            "warehouse_id",
            "chrt_id",
            name="uq_emu_stock_seller_wh_chrt",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seller_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    warehouse_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    chrt_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


@dataclass(frozen=True)
class StockItem:
    chrt_id: int
    amount: int


def upsert_stocks(
    session: Session,
    *,
    seller_key: str,
    warehouse_id: int,
    stocks: list[StockItem],
) -> None:
    """Insert or update only the stocks sent in the request body."""
    for item in stocks:
        row = session.scalar(
            select(StockRow).where(
                StockRow.seller_key == seller_key,
                StockRow.warehouse_id == warehouse_id,
                StockRow.chrt_id == item.chrt_id,
            )
        )
        if row is None:
            session.add(
                StockRow(
                    seller_key=seller_key,
                    warehouse_id=warehouse_id,
                    chrt_id=item.chrt_id,
                    amount=item.amount,
                )
            )
        else:
            row.amount = item.amount
    session.commit()


def get_stocks_by_chrt_ids(
    session: Session,
    *,
    seller_key: str,
    warehouse_id: int,
    chrt_ids: list[int],
) -> list[StockItem]:
    """Return known stocks for requested chrtIds only (unknown ids omitted)."""
    if not chrt_ids:
        return []

    rows = session.scalars(
        select(StockRow)
        .where(
            StockRow.seller_key == seller_key,
            StockRow.warehouse_id == warehouse_id,
            StockRow.chrt_id.in_(chrt_ids),
        )
        .order_by(StockRow.chrt_id)
    ).all()

    requested = set(chrt_ids)
    return [
        StockItem(chrt_id=row.chrt_id, amount=row.amount)
        for row in rows
        if row.chrt_id in requested
    ]
