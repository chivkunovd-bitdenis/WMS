"""Persistent order store for WB Marketplace orders API emulation."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Boolean, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from wb_emulator.models import Base

DEFAULT_MOCK_ORDER: dict[str, Any] = {
    "id": 990001,
    "rid": "mock-rid-990001",
    "createdAt": "2026-07-01T10:00:00+03:00",
    "nmId": 424242,
    "chrtId": 111,
    "article": "E2E-MOCK",
    "skus": ["E2E-MOCK-BARCODE"],
    "price": 150000,
    "cargoType": 1,
    "officeId": 12345,
    "isLegal": False,
    "options": {"isB2B": False},
}


class EmulatorOrder(Base):
    """WB marketplace order row scoped by seller_key."""

    __tablename__ = "emulator_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seller_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    wb_order_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    rid: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    nm_id: Mapped[int] = mapped_column(Integer, nullable=False)
    chrt_id: Mapped[int] = mapped_column(Integer, nullable=False)
    article: Mapped[str] = mapped_column(String(256), nullable=False)
    skus_json: Mapped[str] = mapped_column(String(1024), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    cargo_type: Mapped[int] = mapped_column(Integer, nullable=False)
    office_id: Mapped[int] = mapped_column(Integer, nullable=False)
    is_legal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_b2b: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_pvz: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_pvz: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    supplier_status: Mapped[str] = mapped_column(String(64), nullable=False, default="new")
    wb_status: Mapped[str] = mapped_column(String(64), nullable=False, default="waiting")
    cancelled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


def ensure_orders_table(session: Session) -> None:
    """Create emulator_orders table if missing (EMU-020 lane; no models.py change)."""
    bind = session.get_bind()
    EmulatorOrder.__table__.create(bind=bind, checkfirst=True)


def order_to_api(order: EmulatorOrder) -> dict[str, Any]:
    """Serialize order row to WB camelCase JSON shape."""
    payload: dict[str, Any] = {
        "id": order.wb_order_id,
        "rid": order.rid,
        "createdAt": order.created_at,
        "nmId": order.nm_id,
        "chrtId": order.chrt_id,
        "article": order.article,
        "skus": json.loads(order.skus_json),
        "price": order.price,
        "cargoType": order.cargo_type,
        "officeId": order.office_id,
        "isLegal": order.is_legal,
        "options": {"isB2B": order.is_b2b},
    }
    if order.can_pvz is not None:
        payload["canPvz"] = order.can_pvz
    if order.is_pvz is not None:
        payload["isPvz"] = order.is_pvz
    return payload


def status_row(order_id: int, *, supplier_status: str = "new", wb_status: str = "waiting") -> dict[str, Any]:
    return {"id": order_id, "supplierStatus": supplier_status, "wbStatus": wb_status}


def upsert_order(session: Session, seller_key: str, payload: dict[str, Any]) -> EmulatorOrder:
    """Insert or update an order for a seller (tests and admin seeding)."""
    ensure_orders_table(session)
    wb_order_id = int(payload["id"])
    existing = session.scalar(
        select(EmulatorOrder).where(
            EmulatorOrder.seller_key == seller_key,
            EmulatorOrder.wb_order_id == wb_order_id,
        )
    )
    skus = payload.get("skus") or []
    options = payload.get("options") or {}
    fields = {
        "rid": str(payload["rid"]),
        "created_at": str(payload["createdAt"]),
        "nm_id": int(payload["nmId"]),
        "chrt_id": int(payload["chrtId"]),
        "article": str(payload["article"]),
        "skus_json": json.dumps(skus),
        "price": int(payload["price"]),
        "cargo_type": int(payload["cargoType"]),
        "office_id": int(payload["officeId"]),
        "is_legal": bool(payload.get("isLegal", False)),
        "is_b2b": bool(options.get("isB2B", False)),
        "can_pvz": payload.get("canPvz"),
        "is_pvz": payload.get("isPvz"),
        "supplier_status": str(payload.get("supplierStatus", "new")),
        "wb_status": str(payload.get("wbStatus", "waiting")),
        "cancelled": bool(payload.get("cancelled", False)),
    }
    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
        session.commit()
        session.refresh(existing)
        return existing

    order = EmulatorOrder(seller_key=seller_key, wb_order_id=wb_order_id, **fields)
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


def seed_default_order(session: Session, seller_key: str) -> EmulatorOrder:
    """Seed canonical mock order (990001) for a seller if absent."""
    ensure_orders_table(session)
    existing = session.scalar(
        select(EmulatorOrder).where(
            EmulatorOrder.seller_key == seller_key,
            EmulatorOrder.wb_order_id == DEFAULT_MOCK_ORDER["id"],
        )
    )
    if existing is not None:
        return existing
    return upsert_order(session, seller_key, DEFAULT_MOCK_ORDER)


def list_new_orders(session: Session, seller_key: str) -> list[EmulatorOrder]:
    ensure_orders_table(session)
    seed_default_order(session, seller_key)
    stmt = (
        select(EmulatorOrder)
        .where(
            EmulatorOrder.seller_key == seller_key,
            EmulatorOrder.supplier_status == "new",
            EmulatorOrder.cancelled.is_(False),
        )
        .order_by(EmulatorOrder.wb_order_id.asc())
    )
    return list(session.scalars(stmt).all())


def list_orders_page(
    session: Session,
    seller_key: str,
    *,
    limit: int,
    next_cursor: int | None,
) -> tuple[list[EmulatorOrder], int | None]:
    ensure_orders_table(session)
    stmt = select(EmulatorOrder).where(EmulatorOrder.seller_key == seller_key)
    if next_cursor is not None:
        stmt = stmt.where(EmulatorOrder.wb_order_id > next_cursor)
    stmt = stmt.order_by(EmulatorOrder.wb_order_id.asc()).limit(limit + 1)
    rows = list(session.scalars(stmt).all())
    if len(rows) > limit:
        page = rows[:limit]
        return page, page[-1].wb_order_id
    return rows, None


def get_statuses(session: Session, seller_key: str, order_ids: list[int]) -> list[dict[str, Any]]:
    ensure_orders_table(session)
    if not order_ids:
        return []
    rows = session.scalars(
        select(EmulatorOrder).where(
            EmulatorOrder.seller_key == seller_key,
            EmulatorOrder.wb_order_id.in_(order_ids),
        )
    ).all()
    by_id = {row.wb_order_id: row for row in rows}
    result: list[dict[str, Any]] = []
    for order_id in order_ids:
        row = by_id.get(order_id)
        if row is None:
            result.append(status_row(order_id))
        else:
            result.append(status_row(order_id, supplier_status=row.supplier_status, wb_status=row.wb_status))
    return result


def cancel_order(session: Session, seller_key: str, order_id: int) -> None:
    """Mark order cancelled; no-op if missing (WB mock parity)."""
    ensure_orders_table(session)
    row = session.scalar(
        select(EmulatorOrder).where(
            EmulatorOrder.seller_key == seller_key,
            EmulatorOrder.wb_order_id == order_id,
        )
    )
    if row is None:
        return
    row.cancelled = True
    row.supplier_status = "cancel"
    row.wb_status = "canceled"
    session.commit()
