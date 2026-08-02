"""Minimal order store for EMU-050 admin lane (schema compatible with EMU-020)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Boolean, Integer, String, func, select
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

_TEMPLATES_PATH = Path(__file__).parent / "order_templates.json"

WB_EVENT_MAP: dict[str, tuple[str, str, bool]] = {
    "sorted": ("confirm", "sorted", False),
    "sold": ("complete", "sold", False),
    "canceled_by_client": ("cancel", "canceled_by_client", True),
}


class EmulatorOrder(Base):
    """WB marketplace order row scoped by seller_key (same table as EMU-020)."""

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
    bind = session.get_bind()
    EmulatorOrder.__table__.create(bind=bind, checkfirst=True)


def order_to_api(order: EmulatorOrder) -> dict[str, Any]:
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


def upsert_order(session: Session, seller_key: str, payload: dict[str, Any]) -> EmulatorOrder:
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


def load_order_templates() -> list[dict[str, Any]]:
    raw = json.loads(_TEMPLATES_PATH.read_text(encoding="utf-8"))
    templates = raw.get("templates", [])
    if not isinstance(templates, list):
        raise ValueError("order_templates.json: templates must be a list")
    return templates


def _next_wb_order_ids(session: Session, count: int) -> list[int]:
    ensure_orders_table(session)
    max_id = session.scalar(select(func.max(EmulatorOrder.wb_order_id))) or 500000
    return [int(max_id) + offset + 1 for offset in range(count)]


def create_orders_for_seller(session: Session, seller_key: str, count: int) -> list[EmulatorOrder]:
    if count < 1:
        raise ValueError("count must be >= 1")
    templates = load_order_templates()
    if not templates:
        raise ValueError("no order templates configured")

    created: list[EmulatorOrder] = []
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    for wb_order_id in _next_wb_order_ids(session, count):
        template = templates[(len(created)) % len(templates)]
        payload: dict[str, Any] = {
            "id": wb_order_id,
            "rid": f"emu-rid-{wb_order_id}",
            "createdAt": now,
            "nmId": template["nmId"],
            "chrtId": template["chrtId"],
            "article": template["article"],
            "skus": list(template["skus"]),
            "price": template["price"],
            "cargoType": template["cargoType"],
            "officeId": template["officeId"],
            "isLegal": template.get("isLegal", False),
            "options": dict(template.get("options", {})),
            "supplierStatus": "new",
            "wbStatus": "waiting",
            "cancelled": False,
        }
        created.append(upsert_order(session, seller_key, payload))
    return created


def apply_wb_event(session: Session, seller_key: str, order_id: int, event: str) -> EmulatorOrder | None:
    if event not in WB_EVENT_MAP:
        raise ValueError(f"unsupported wb-event: {event}")
    ensure_orders_table(session)
    row = session.scalar(
        select(EmulatorOrder).where(
            EmulatorOrder.seller_key == seller_key,
            EmulatorOrder.wb_order_id == order_id,
        )
    )
    if row is None:
        return None
    supplier_status, wb_status, cancelled = WB_EVENT_MAP[event]
    row.supplier_status = supplier_status
    row.wb_status = wb_status
    row.cancelled = cancelled
    session.commit()
    session.refresh(row)
    return row


def get_admin_state(session: Session, seller_key: str | None = None) -> dict[str, Any]:
    ensure_orders_table(session)
    stmt = select(EmulatorOrder)
    if seller_key is not None:
        stmt = stmt.where(EmulatorOrder.seller_key == seller_key)
    rows = list(session.scalars(stmt).all())

    by_supplier: dict[str, int] = {}
    by_wb: dict[str, int] = {}
    for row in rows:
        by_supplier[row.supplier_status] = by_supplier.get(row.supplier_status, 0) + 1
        by_wb[row.wb_status] = by_wb.get(row.wb_status, 0) + 1

    return {
        "seller": seller_key,
        "orders_total": len(rows),
        "by_supplier_status": by_supplier,
        "by_wb_status": by_wb,
    }
