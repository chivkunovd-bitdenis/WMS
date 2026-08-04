"""Persistent order store for WB Marketplace orders API emulation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Boolean, Integer, String, func, select, text, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from wb_emulator.models import Base
from wb_emulator.services.stocks_store import StockRow

_TEMPLATES_PATH = Path(__file__).resolve().parent.parent / "seed" / "order_templates.json"

DEFAULT_EMULATOR_WAREHOUSE_ID = 501001
DEFAULT_EMULATOR_OFFICE_ID = 601001

WB_EVENT_MAP: dict[str, tuple[str, str, bool]] = {
    "sorted": ("confirm", "sorted", False),
    "sold": ("complete", "sold", False),
    "canceled_by_client": ("cancel", "canceled_by_client", True),
}

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
    "warehouseId": DEFAULT_EMULATOR_WAREHOUSE_ID,
    "officeId": DEFAULT_EMULATOR_OFFICE_ID,
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
    warehouse_id: Mapped[int] = mapped_column(Integer, nullable=False)
    office_id: Mapped[int] = mapped_column(Integer, nullable=False)
    is_legal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_b2b: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_pvz: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_pvz: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    required_meta_json: Mapped[str | None] = mapped_column(String(512), nullable=True)
    optional_meta_json: Mapped[str | None] = mapped_column(String(512), nullable=True)
    supplier_status: Mapped[str] = mapped_column(String(64), nullable=False, default="new")
    wb_status: Mapped[str] = mapped_column(String(64), nullable=False, default="waiting")
    cancelled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


def _ensure_orders_columns(session: Session) -> None:
    """Add meta columns on existing SQLite tables (idempotent)."""
    bind = session.get_bind()
    if bind.dialect.name != "sqlite":
        return
    existing = {
        row[1]
        for row in session.execute(text("PRAGMA table_info(emulator_orders)")).fetchall()
    }
    if not existing:
        return
    if "required_meta_json" not in existing:
        session.execute(text("ALTER TABLE emulator_orders ADD COLUMN required_meta_json VARCHAR(512)"))
        session.commit()
    if "optional_meta_json" not in existing:
        session.execute(text("ALTER TABLE emulator_orders ADD COLUMN optional_meta_json VARCHAR(512)"))
        session.commit()


def ensure_orders_table(session: Session) -> None:
    """Create emulator_orders table if missing (EMU-020 lane; no models.py change)."""
    bind = session.get_bind()
    EmulatorOrder.__table__.create(bind=bind, checkfirst=True)
    _ensure_orders_columns(session)


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
        "warehouseId": order.warehouse_id,
        "officeId": order.office_id,
        "isLegal": order.is_legal,
        "options": {"isB2B": order.is_b2b},
    }
    if order.can_pvz is not None:
        payload["canPvz"] = order.can_pvz
    if order.is_pvz is not None:
        payload["isPvz"] = order.is_pvz
    if order.required_meta_json:
        payload["requiredMeta"] = json.loads(order.required_meta_json)
    if order.optional_meta_json:
        payload["optionalMeta"] = json.loads(order.optional_meta_json)
    return payload


def status_row(order_id: int, *, supplier_status: str = "new", wb_status: str = "waiting") -> dict[str, Any]:
    return {"id": order_id, "supplierStatus": supplier_status, "wbStatus": wb_status}


def _order_fields_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    skus = payload.get("skus") or []
    options = payload.get("options") or {}
    warehouse_id = int(payload.get("warehouseId", DEFAULT_EMULATOR_WAREHOUSE_ID))
    office_id = int(payload.get("officeId", DEFAULT_EMULATOR_OFFICE_ID))
    return {
        "rid": str(payload["rid"]),
        "created_at": str(payload["createdAt"]),
        "nm_id": int(payload["nmId"]),
        "chrt_id": int(payload["chrtId"]),
        "article": str(payload["article"]),
        "skus_json": json.dumps(skus),
        "price": int(payload["price"]),
        "cargo_type": int(payload["cargoType"]),
        "warehouse_id": warehouse_id,
        "office_id": office_id,
        "is_legal": bool(payload.get("isLegal", False)),
        "is_b2b": bool(options.get("isB2B", False)),
        "can_pvz": payload.get("canPvz"),
        "is_pvz": payload.get("isPvz"),
        "supplier_status": str(payload.get("supplierStatus", "new")),
        "wb_status": str(payload.get("wbStatus", "waiting")),
        "cancelled": bool(payload.get("cancelled", False)),
        "required_meta_json": _meta_json_from_payload(payload, "requiredMeta", "required_meta"),
        "optional_meta_json": _meta_json_from_payload(payload, "optionalMeta", "optional_meta"),
    }


def _meta_json_from_payload(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        raw = payload.get(key)
        if isinstance(raw, list) and raw:
            return json.dumps(raw)
    return None


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
    fields = _order_fields_from_payload(payload)
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


def get_order(session: Session, seller_key: str, wb_order_id: int) -> EmulatorOrder | None:
    ensure_orders_table(session)
    return session.scalar(
        select(EmulatorOrder).where(
            EmulatorOrder.seller_key == seller_key,
            EmulatorOrder.wb_order_id == wb_order_id,
        )
    )


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


def get_statuses(
    session: Session,
    seller_key: str,
    order_ids: list[int],
    *,
    omit_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    ensure_orders_table(session)
    if not order_ids:
        return []
    skip = omit_ids or set()
    rows = session.scalars(
        select(EmulatorOrder).where(
            EmulatorOrder.seller_key == seller_key,
            EmulatorOrder.wb_order_id.in_(order_ids),
        )
    ).all()
    by_id = {row.wb_order_id: row for row in rows}
    result: list[dict[str, Any]] = []
    for order_id in order_ids:
        if order_id in skip:
            continue
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


def load_order_templates() -> list[dict[str, Any]]:
    raw = json.loads(_TEMPLATES_PATH.read_text(encoding="utf-8"))
    templates = raw.get("templates", [])
    if not isinstance(templates, list):
        raise ValueError("order_templates.json: templates must be a list")
    return templates



def _template_pool(templates: list[dict[str, Any]], chrt_id: int | None) -> list[dict[str, Any]]:
    if chrt_id is None:
        return templates
    matching = [template for template in templates if int(template["chrtId"]) == chrt_id]
    if not matching:
        raise ValueError(f"no order template for chrtId={chrt_id}")
    return matching


def _build_order_payload(
    template: dict[str, Any],
    *,
    wb_order_id: int,
    warehouse_id: int,
    now: str,
) -> dict[str, Any]:
    office_id = int(template.get("officeId", DEFAULT_EMULATOR_OFFICE_ID))
    payload: dict[str, Any] = {
        "id": wb_order_id,
        "rid": f"emu-rid-{wb_order_id}",
        "createdAt": str(template.get("createdAt", now)),
        "nmId": template["nmId"],
        "chrtId": template["chrtId"],
        "article": template["article"],
        "skus": list(template["skus"]),
        "price": template["price"],
        "cargoType": template["cargoType"],
        "warehouseId": warehouse_id,
        "officeId": office_id,
        "isLegal": template.get("isLegal", False),
        "options": dict(template.get("options", {})),
        "supplierStatus": str(template.get("supplierStatus", "new")),
        "wbStatus": str(template.get("wbStatus", "waiting")),
        "cancelled": bool(template.get("cancelled", False)),
    }
    if "canPvz" in template:
        payload["canPvz"] = bool(template["canPvz"])
    if "isPvz" in template:
        payload["isPvz"] = bool(template["isPvz"])
    if template.get("requiredMeta"):
        payload["requiredMeta"] = list(template["requiredMeta"])
    if template.get("optionalMeta"):
        payload["optionalMeta"] = list(template["optionalMeta"])
    return payload


def template_to_seed_payload(template: dict[str, Any], *, now: str | None = None) -> dict[str, Any]:
    """Build upsert payload from a seed template (fixed seedOrderId)."""
    from datetime import timedelta

    created_at = template.get("createdAt")
    if created_at is None and template.get("nearDeadline"):
        deadline_now = datetime.now(UTC) - timedelta(minutes=15)
        created_at = deadline_now.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    resolved_now = created_at or now or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    warehouse_id = int(template.get("warehouseId", DEFAULT_EMULATOR_WAREHOUSE_ID))
    return _build_order_payload(
        template,
        wb_order_id=int(template["seedOrderId"]),
        warehouse_id=warehouse_id,
        now=resolved_now,
    )


def seed_orders_from_templates(
    session: Session,
    *,
    seller_keys: list[str] | None = None,
) -> dict[str, int]:
    """Upsert fixed seed orders per seller from order_templates.json (idempotent)."""
    templates = load_order_templates()
    allowed = set(seller_keys) if seller_keys is not None else None
    counts: dict[str, int] = {}
    for template in templates:
        seller = str(template.get("seller", "")).strip()
        if not seller:
            continue
        if allowed is not None and seller not in allowed:
            continue
        payload = template_to_seed_payload(template)
        upsert_order(session, seller, payload)
        counts[seller] = counts.get(seller, 0) + 1
    return counts


def count_seeded_orders(session: Session, seller_key: str | None = None) -> int:
    ensure_orders_table(session)
    stmt = select(func.count()).select_from(EmulatorOrder)
    if seller_key is not None:
        stmt = stmt.where(EmulatorOrder.seller_key == seller_key)
    return int(session.scalar(stmt) or 0)


def _try_purchase_one(
    session: Session,
    seller_key: str,
    warehouse_id: int,
    template: dict[str, Any],
    now: str,
) -> EmulatorOrder | None:
    """Atomically decrement stock by 1 and create one order, or return None if no stock."""
    ensure_orders_table(session)
    chrt_id = int(template["chrtId"])

    session.execute(text("BEGIN IMMEDIATE"))
    try:
        decremented = session.execute(
            update(StockRow)
            .where(
                StockRow.seller_key == seller_key,
                StockRow.warehouse_id == warehouse_id,
                StockRow.chrt_id == chrt_id,
                StockRow.amount > 0,
            )
            .values(amount=StockRow.amount - 1)
        )
        if getattr(decremented, "rowcount", None) != 1:
            session.rollback()
            return None

        wb_order_id = int(session.scalar(select(func.max(EmulatorOrder.wb_order_id))) or 500000) + 1
        payload = _build_order_payload(template, wb_order_id=wb_order_id, warehouse_id=warehouse_id, now=now)
        fields = _order_fields_from_payload(payload)
        order = EmulatorOrder(seller_key=seller_key, wb_order_id=wb_order_id, **fields)
        session.add(order)
        session.commit()
        session.refresh(order)
        return order
    except Exception:
        session.rollback()
        raise


class PurchaseResult:
    """Result of stock-constrained admin purchase."""

    __slots__ = ("created", "orders", "rejected_no_stock")

    def __init__(self, orders: list[EmulatorOrder], *, created: int, rejected_no_stock: int) -> None:
        self.orders = orders
        self.created = created
        self.rejected_no_stock = rejected_no_stock


def create_orders_for_seller(
    session: Session,
    seller_key: str,
    count: int,
    *,
    warehouse_id: int | None = None,
    chrt_id: int | None = None,
) -> PurchaseResult:
    if count < 1:
        raise ValueError("count must be >= 1")

    templates = load_order_templates()
    if not templates:
        raise ValueError("no order templates configured")

    seller_templates = [
        template
        for template in templates
        if not template.get("seller") or str(template.get("seller", "")).strip() == seller_key
    ]
    if not seller_templates:
        seller_templates = templates

    resolved_warehouse_id = warehouse_id if warehouse_id is not None else DEFAULT_EMULATOR_WAREHOUSE_ID
    pool = _template_pool(seller_templates, chrt_id)

    created: list[EmulatorOrder] = []
    rejected_no_stock = 0
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    for index in range(count):
        template = pool[index % len(pool)]
        order = _try_purchase_one(session, seller_key, resolved_warehouse_id, template, now)
        if order is None:
            rejected_no_stock += 1
        else:
            created.append(order)

    return PurchaseResult(created, created=len(created), rejected_no_stock=rejected_no_stock)


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
