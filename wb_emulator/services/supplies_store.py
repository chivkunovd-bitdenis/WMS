"""SQLite-backed supplies and trbx persistence for marketplace emulator."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from wb_emulator.models import Base


class SupplyStatus(StrEnum):
    ACTIVE = "active"
    DELIVERED = "delivered"


class SupplyRow(Base):
    __tablename__ = "emu_supplies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    seller_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=SupplyStatus.ACTIVE)


class SupplyOrderRow(Base):
    __tablename__ = "emu_supply_orders"
    __table_args__ = (UniqueConstraint("seller_key", "order_id", name="uq_supply_order_seller"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supply_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("emu_supplies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seller_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    order_id: Mapped[int] = mapped_column(Integer, nullable=False)


class SupplyAuditRow(Base):
    """Persistent call counters used by black-box full-stack assertions."""

    __tablename__ = "emu_supply_audit"

    supply_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    seller_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    deliver_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class TrbxRow(Base):
    __tablename__ = "emu_trbxes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    supply_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("emu_supplies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seller_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    orders: Mapped[list[TrbxOrderRow]] = relationship(
        back_populates="trbx", cascade="all, delete-orphan"
    )


class TrbxOrderRow(Base):
    __tablename__ = "emu_trbx_orders"
    __table_args__ = (UniqueConstraint("trbx_id", "order_id", name="uq_trbx_order"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trbx_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("emu_trbxes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_id: Mapped[int] = mapped_column(Integer, nullable=False)
    trbx: Mapped[TrbxRow] = relationship(back_populates="orders")


class SuppliesStoreError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class SupplyView:
    id: str
    name: str
    status: str
    order_ids: list[int]
    trbx_ids: list[str]


def _new_supply_id() -> str:
    return f"WB-GI-{uuid.uuid4().hex[:12].upper()}"


def _new_trbx_id() -> str:
    return f"TRBX-{uuid.uuid4().hex[:10].upper()}"


def _get_supply(session: Session, *, seller_key: str, supply_id: str) -> SupplyRow:
    row = session.scalar(
        select(SupplyRow).where(SupplyRow.id == supply_id, SupplyRow.seller_key == seller_key)
    )
    if row is None:
        raise SuppliesStoreError("not_found", "Supply not found")
    return row


def create_supply(session: Session, *, seller_key: str, name: str) -> dict[str, str]:
    supply_id = _new_supply_id()
    row = SupplyRow(id=supply_id, seller_key=seller_key, name=name, status=SupplyStatus.ACTIVE)
    session.add(row)
    session.add(SupplyAuditRow(supply_id=supply_id, seller_key=seller_key, deliver_calls=0))
    session.commit()
    return {"id": supply_id, "name": name}


def get_supply(session: Session, *, seller_key: str, supply_id: str) -> SupplyView:
    row = _get_supply(session, seller_key=seller_key, supply_id=supply_id)
    order_ids = list(
        session.scalars(
            select(SupplyOrderRow.order_id)
            .where(
                SupplyOrderRow.supply_id == supply_id,
                SupplyOrderRow.seller_key == seller_key,
            )
            .order_by(SupplyOrderRow.order_id)
        )
    )
    trbx_ids = list(
        session.scalars(
            select(TrbxRow.id).where(
                TrbxRow.supply_id == supply_id,
                TrbxRow.seller_key == seller_key,
            )
        )
    )
    return SupplyView(
        id=row.id,
        name=row.name,
        status=row.status,
        order_ids=order_ids,
        trbx_ids=trbx_ids,
    )


def add_order_to_supply(
    session: Session, *, seller_key: str, supply_id: str, order_id: int
) -> None:
    supply = _get_supply(session, seller_key=seller_key, supply_id=supply_id)
    if supply.status == SupplyStatus.DELIVERED:
        raise SuppliesStoreError("delivered", "Supply already delivered")

    existing = session.scalar(
        select(SupplyOrderRow).where(
            SupplyOrderRow.seller_key == seller_key,
            SupplyOrderRow.order_id == order_id,
        )
    )
    if existing is not None and existing.supply_id != supply_id:
        raise SuppliesStoreError("conflict", "Order already assigned to another supply")

    if existing is None:
        session.add(
            SupplyOrderRow(
                supply_id=supply_id,
                seller_key=seller_key,
                order_id=order_id,
            )
        )
        session.commit()


def deliver_supply(session: Session, *, seller_key: str, supply_id: str) -> None:
    audit = session.scalar(
        select(SupplyAuditRow).where(
            SupplyAuditRow.supply_id == supply_id,
            SupplyAuditRow.seller_key == seller_key,
        )
    )
    if audit is None:
        audit = SupplyAuditRow(supply_id=supply_id, seller_key=seller_key, deliver_calls=0)
        session.add(audit)
    audit.deliver_calls += 1
    session.commit()

    supply = _get_supply(session, seller_key=seller_key, supply_id=supply_id)
    if supply.status == SupplyStatus.DELIVERED:
        raise SuppliesStoreError("delivered", "Supply already delivered")
    supply.status = SupplyStatus.DELIVERED
    session.commit()


def get_admin_supply_state(
    session: Session, *, seller_key: str | None = None
) -> list[dict[str, object]]:
    """Return supply/order/trbx bindings plus WB deliver call counts for E2E evidence."""
    stmt = select(SupplyRow).order_by(SupplyRow.id)
    if seller_key is not None:
        stmt = stmt.where(SupplyRow.seller_key == seller_key)

    result: list[dict[str, object]] = []
    for supply in session.scalars(stmt):
        view = get_supply(session, seller_key=supply.seller_key, supply_id=supply.id)
        audit = session.scalar(
            select(SupplyAuditRow).where(
                SupplyAuditRow.supply_id == supply.id,
                SupplyAuditRow.seller_key == supply.seller_key,
            )
        )
        trbx_rows: list[dict[str, object]] = []
        for trbx_id in view.trbx_ids:
            order_ids = list(
                session.scalars(
                    select(TrbxOrderRow.order_id)
                    .where(TrbxOrderRow.trbx_id == trbx_id)
                    .order_by(TrbxOrderRow.order_id)
                )
            )
            trbx_rows.append({"id": trbx_id, "orders": order_ids})
        result.append(
            {
                "id": view.id,
                "seller": supply.seller_key,
                "done": view.status == SupplyStatus.DELIVERED,
                "orders": view.order_ids,
                "trbx": trbx_rows,
                "deliver_calls": audit.deliver_calls if audit is not None else 0,
            }
        )
    return result


def create_trbxes(session: Session, *, seller_key: str, supply_id: str, amount: int) -> list[str]:
    if amount < 1:
        raise SuppliesStoreError("validation", "amount must be >= 1")
    _get_supply(session, seller_key=seller_key, supply_id=supply_id)
    ids: list[str] = []
    for _ in range(amount):
        trbx_id = _new_trbx_id()
        session.add(TrbxRow(id=trbx_id, supply_id=supply_id, seller_key=seller_key))
        ids.append(trbx_id)
    session.commit()
    return ids


def delete_trbxes(
    session: Session,
    *,
    seller_key: str,
    supply_id: str,
    trbx_ids: list[str],
) -> None:
    """Delete only cargo places belonging to this seller's active supply."""
    supply = _get_supply(session, seller_key=seller_key, supply_id=supply_id)
    if supply.status == SupplyStatus.DELIVERED:
        raise SuppliesStoreError("delivered", "Supply already delivered")

    requested_ids = set(trbx_ids)
    rows = list(
        session.scalars(
            select(TrbxRow).where(
                TrbxRow.id.in_(requested_ids),
                TrbxRow.supply_id == supply_id,
                TrbxRow.seller_key == seller_key,
            )
        )
    )
    found_ids = {row.id for row in rows}
    if found_ids != requested_ids:
        raise SuppliesStoreError("not_found", "Trbx not found")

    for row in rows:
        session.delete(row)
    session.commit()


def bind_orders_to_trbx(
    session: Session,
    *,
    seller_key: str,
    supply_id: str,
    trbx_id: str,
    order_ids: list[int],
) -> None:
    _get_supply(session, seller_key=seller_key, supply_id=supply_id)
    trbx = session.scalar(
        select(TrbxRow).where(
            TrbxRow.id == trbx_id,
            TrbxRow.supply_id == supply_id,
            TrbxRow.seller_key == seller_key,
        )
    )
    if trbx is None:
        raise SuppliesStoreError("not_found", "Trbx not found")

    supply_order_ids = set(
        session.scalars(
            select(SupplyOrderRow.order_id).where(
                SupplyOrderRow.supply_id == supply_id,
                SupplyOrderRow.seller_key == seller_key,
            )
        )
    )
    for order_id in order_ids:
        if order_id not in supply_order_ids:
            raise SuppliesStoreError("validation", f"Order {order_id} not in supply")

    existing = {
        row.order_id
        for row in session.scalars(
            select(TrbxOrderRow).where(TrbxOrderRow.trbx_id == trbx_id)
        )
    }
    for order_id in order_ids:
        if order_id not in existing:
            session.add(TrbxOrderRow(trbx_id=trbx_id, order_id=order_id))
    session.commit()


# Stub payload for EMU-040 barcode/stickers hooks.
TINY_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def stub_supply_barcode_bytes() -> bytes:
    import base64

    return base64.b64decode(TINY_PNG_BASE64)


def stub_trbx_stickers(trbx_ids: list[str]) -> list[dict[str, str]]:
    return [
        {"trbxId": trbx_id, "file": TINY_PNG_BASE64, "barcode": f"EMU-QR-{trbx_id}"}
        for trbx_id in trbx_ids
    ]
