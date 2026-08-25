from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, cast

import jwt
from sqlalchemy import Connection, event, func, insert, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload
from starlette.types import ASGIApp, Receive, Scope, Send

from app.models.document_event import (
    DOCUMENT_EVENT_SOURCES,
    DOCUMENT_EVENT_TYPES,
    DOCUMENT_TYPE_FBS_SUPPLY,
    DOCUMENT_TYPE_INBOUND_INTAKE,
    DOCUMENT_TYPE_MARKETPLACE_UNLOAD,
    DOCUMENT_TYPES,
    EVENT_DEFECT_QTY_CHANGED,
    EVENT_LINE_ADDED,
    EVENT_LINE_QTY_CHANGED,
    EVENT_LINE_REMOVED,
    EVENT_PLANNED_DATE_CHANGED,
    EVENT_STATUS_CHANGED,
    EVENT_WAREHOUSE_CHANGED,
    SOURCE_SYSTEM,
    SOURCE_USER,
    DocumentEvent,
)
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeBoxLine,
    InboundIntakeLine,
    InboundIntakeRequest,
)
from app.models.marketplace_unload import (
    MarketplaceUnloadBox,
    MarketplaceUnloadBoxLine,
    MarketplaceUnloadLine,
    MarketplaceUnloadRequest,
)
from app.services.tokens import decode_access_token

logger = logging.getLogger(__name__)


class DocumentEventError(ValueError):
    pass


@dataclass(frozen=True)
class DocumentEventActor:
    actor_user_id: uuid.UUID | None
    source: str


_SYSTEM_ACTOR = DocumentEventActor(actor_user_id=None, source=SOURCE_SYSTEM)
_actor_context: ContextVar[DocumentEventActor] = ContextVar(
    "document_event_actor", default=_SYSTEM_ACTOR
)


@contextmanager
def document_event_actor(actor_user_id: uuid.UUID) -> Iterator[None]:
    """Bind an authenticated user to document changes in the current context."""
    token = _actor_context.set(DocumentEventActor(actor_user_id=actor_user_id, source=SOURCE_USER))
    try:
        yield
    finally:
        _actor_context.reset(token)


@contextmanager
def system_document_events() -> Iterator[None]:
    """Explicitly mark background or provider-driven changes as system actions."""
    token = _actor_context.set(_SYSTEM_ACTOR)
    try:
        yield
    finally:
        _actor_context.reset(token)


class DocumentEventActorMiddleware:
    """Extract the already validated JWT identity for transaction-level auditing."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        actor = _actor_from_scope(scope)
        token = _actor_context.set(actor)
        try:
            await self.app(scope, receive, send)
        finally:
            _actor_context.reset(token)


def _actor_from_scope(scope: Scope) -> DocumentEventActor:
    headers = {key.lower(): value for key, value in scope.get("headers", [])}
    raw = headers.get(b"authorization", b"").decode("latin-1")
    scheme, _, credential = raw.partition(" ")
    if scheme.lower() != "bearer" or not credential:
        return _SYSTEM_ACTOR
    try:
        payload = decode_access_token(credential)
        subject = payload.get("sub")
        if not isinstance(subject, str):
            return _SYSTEM_ACTOR
        return DocumentEventActor(actor_user_id=uuid.UUID(subject), source=SOURCE_USER)
    except (jwt.PyJWTError, ValueError):
        return _SYSTEM_ACTOR


def _json_value(value: object) -> object:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _validate_event(
    *,
    document_type: str,
    event_type: str,
    source: str,
    actor_user_id: uuid.UUID | None,
) -> None:
    if document_type not in DOCUMENT_TYPES:
        raise DocumentEventError("invalid_document_type")
    if event_type not in DOCUMENT_EVENT_TYPES:
        raise DocumentEventError("invalid_event_type")
    if source not in DOCUMENT_EVENT_SOURCES:
        raise DocumentEventError("invalid_source")
    if source == SOURCE_USER and actor_user_id is None:
        raise DocumentEventError("user_actor_required")
    if source == SOURCE_SYSTEM and actor_user_id is not None:
        raise DocumentEventError("system_actor_must_be_null")


def _event_row(
    *,
    tenant_id: uuid.UUID,
    document_type: str,
    document_id: uuid.UUID,
    event_type: str,
    actor: DocumentEventActor,
    qty: int | None = None,
    product_id: uuid.UUID | None = None,
    payload_json: dict[str, object] | None = None,
    idempotency_key: str | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, object]:
    _validate_event(
        document_type=document_type,
        event_type=event_type,
        source=actor.source,
        actor_user_id=actor.actor_user_id,
    )
    if idempotency_key is not None and len(idempotency_key) > 128:
        raise DocumentEventError("idempotency_key_too_long")
    now = occurred_at or datetime.now(UTC)
    return {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "document_type": document_type,
        "document_id": document_id,
        "event_type": event_type,
        "actor_user_id": actor.actor_user_id,
        "source": actor.source,
        "occurred_at": now,
        "qty": qty,
        "product_id": product_id,
        "payload_json": payload_json or {},
        "idempotency_key": idempotency_key,
        "created_at": now,
    }


async def record_document_event(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    document_type: str,
    document_id: uuid.UUID,
    event_type: str,
    source: str,
    actor_user_id: uuid.UUID | None,
    qty: int | None = None,
    product_id: uuid.UUID | None = None,
    payload_json: dict[str, object] | None = None,
    idempotency_key: str | None = None,
    occurred_at: datetime | None = None,
) -> bool:
    """Insert one event without flushing unrelated warehouse changes."""
    row = _event_row(
        tenant_id=tenant_id,
        document_type=document_type,
        document_id=document_id,
        event_type=event_type,
        actor=DocumentEventActor(actor_user_id=actor_user_id, source=source),
        qty=qty,
        product_id=product_id,
        payload_json=payload_json,
        idempotency_key=idempotency_key,
        occurred_at=occurred_at,
    )
    connection = await session.connection()
    savepoint = await connection.begin_nested()
    try:
        await connection.execute(insert(DocumentEvent).values(**row))
    except IntegrityError:
        await savepoint.rollback()
        if idempotency_key is not None:
            return False
        raise
    except Exception:
        await savepoint.rollback()
        raise
    else:
        await savepoint.commit()
        return True


async def record_document_event_safely(session: AsyncSession, **values: Any) -> bool:
    """Best-effort observer: journal storage failure never aborts the warehouse action."""
    try:
        return await record_document_event(session, **values)
    except DocumentEventError:
        raise
    except Exception:
        logger.exception(
            "document event write failed: document_type=%s document_id=%s event_type=%s",
            values.get("document_type"),
            values.get("document_id"),
            values.get("event_type"),
        )
        return False


async def list_document_events(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    document_type: str,
    document_id: uuid.UUID,
    limit: int,
    offset: int,
) -> list[DocumentEvent]:
    if document_type not in DOCUMENT_TYPES:
        raise DocumentEventError("invalid_document_type")
    stmt = (
        select(DocumentEvent)
        .where(
            DocumentEvent.tenant_id == tenant_id,
            DocumentEvent.document_type == document_type,
            DocumentEvent.document_id == document_id,
        )
        .options(selectinload(DocumentEvent.actor), selectinload(DocumentEvent.product))
        .order_by(DocumentEvent.occurred_at.desc(), DocumentEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list((await session.scalars(stmt)).all())


def _history_pair(obj: object, attribute: str) -> tuple[object, object] | None:
    state = cast(Any, inspect(obj))
    history = state.attrs[attribute].history
    if not history.has_changes() or not history.added:
        return None
    before = history.deleted[0] if history.deleted else None
    after = history.added[0]
    if before == after:
        return None
    return before, after


def _request_qty(
    session: Session,
    connection: Connection,
    request: InboundIntakeRequest,
    status_after: str,
) -> int:
    state = inspect(request)
    if "lines" not in state.unloaded:
        loose_or_total = sum(int(line.actual_qty or 0) for line in request.lines)
    else:
        loose_or_total = int(
            connection.scalar(
                select(func.coalesce(func.sum(InboundIntakeLine.actual_qty), 0)).where(
                    InboundIntakeLine.request_id == request.id
                )
            )
            or 0
        )
    if status_after in {"sorting", "done"}:
        return loose_or_total
    if "boxes" not in state.unloaded:
        boxed = sum(int(line.quantity) for box in request.boxes for line in box.lines)
    else:
        boxed = int(
            connection.scalar(
                select(func.coalesce(func.sum(InboundIntakeBoxLine.quantity), 0))
                .join(InboundIntakeBox, InboundIntakeBoxLine.box_id == InboundIntakeBox.id)
                .where(InboundIntakeBox.request_id == request.id)
            )
            or 0
        )
    return loose_or_total + boxed


def _supply_qty(connection: Connection, supply: FbsSupply) -> int:
    if "orders" not in inspect(supply).unloaded:
        return len(supply.orders)
    return int(
        connection.scalar(select(func.count(FbsOrder.id)).where(FbsOrder.supply_id == supply.id))
        or 0
    )


def _unload_qty(connection: Connection, request: MarketplaceUnloadRequest) -> int:
    if "boxes" not in inspect(request).unloaded:
        return sum(int(line.quantity) for box in request.boxes for line in box.lines)
    return int(
        connection.scalar(
            select(func.coalesce(func.sum(MarketplaceUnloadBoxLine.quantity), 0))
            .join(MarketplaceUnloadBox, MarketplaceUnloadBoxLine.box_id == MarketplaceUnloadBox.id)
            .where(MarketplaceUnloadBox.request_id == request.id)
        )
        or 0
    )


def _document_rows(session: Session, connection: Connection) -> list[dict[str, object]]:
    actor = _actor_context.get()
    rows: list[dict[str, object]] = []
    for obj in session.dirty:
        if isinstance(obj, InboundIntakeRequest):
            rows.extend(_request_change_rows(session, connection, obj, actor))
        elif isinstance(obj, FbsSupply):
            rows.extend(_supply_change_rows(connection, obj, actor))
        elif isinstance(obj, MarketplaceUnloadRequest):
            rows.extend(_unload_change_rows(connection, obj, actor))
        elif isinstance(obj, InboundIntakeLine):
            rows.extend(_inbound_line_change_rows(connection, obj, actor))
        elif isinstance(obj, MarketplaceUnloadLine):
            rows.extend(_unload_line_change_rows(connection, obj, actor))
        elif isinstance(obj, FbsOrder):
            rows.extend(_fbs_order_change_rows(connection, obj, actor))
    for obj in session.new:
        if isinstance(obj, InboundIntakeLine):
            row = _line_added_row(connection, obj, actor)
            if row is not None:
                rows.append(row)
        elif isinstance(obj, MarketplaceUnloadLine):
            row = _unload_line_added_row(connection, obj, actor)
            if row is not None:
                rows.append(row)
    for obj in session.deleted:
        if isinstance(obj, InboundIntakeLine):
            row = _line_removed_row(connection, obj, actor)
            if row is not None:
                rows.append(row)
        elif isinstance(obj, MarketplaceUnloadLine):
            row = _unload_line_removed_row(connection, obj, actor)
            if row is not None:
                rows.append(row)
    return rows


def _request_change_rows(
    session: Session,
    connection: Connection,
    request: InboundIntakeRequest,
    actor: DocumentEventActor,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    status = _history_pair(request, "status")
    if status is not None:
        before, after = status
        rows.append(
            _event_row(
                tenant_id=request.tenant_id,
                document_type=DOCUMENT_TYPE_INBOUND_INTAKE,
                document_id=request.id,
                event_type=EVENT_STATUS_CHANGED,
                actor=actor,
                qty=_request_qty(session, connection, request, str(after)),
                payload_json={"from": before, "to": after},
            )
        )
    rows.extend(
        _field_change_rows(
            request,
            actor=actor,
            document_type=DOCUMENT_TYPE_INBOUND_INTAKE,
            fields=(
                ("warehouse_id", EVENT_WAREHOUSE_CHANGED),
                ("planned_delivery_date", EVENT_PLANNED_DATE_CHANGED),
            ),
        )
    )
    return rows


def _supply_change_rows(
    connection: Connection, supply: FbsSupply, actor: DocumentEventActor
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    status = _history_pair(supply, "status")
    if status is not None:
        before, after = status
        rows.append(
            _event_row(
                tenant_id=supply.tenant_id,
                document_type=DOCUMENT_TYPE_FBS_SUPPLY,
                document_id=supply.id,
                event_type=EVENT_STATUS_CHANGED,
                actor=actor,
                qty=_supply_qty(connection, supply),
                payload_json={"from": before, "to": after},
            )
        )
    rows.extend(
        _field_change_rows(
            supply,
            actor=actor,
            document_type=DOCUMENT_TYPE_FBS_SUPPLY,
            fields=(
                ("warehouse_id", EVENT_WAREHOUSE_CHANGED),
                ("planned_shipment_date", EVENT_PLANNED_DATE_CHANGED),
            ),
        )
    )
    return rows


def _unload_change_rows(
    connection: Connection,
    request: MarketplaceUnloadRequest,
    actor: DocumentEventActor,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    status = _history_pair(request, "status")
    if status is not None:
        before, after = status
        rows.append(
            _event_row(
                tenant_id=request.tenant_id,
                document_type=DOCUMENT_TYPE_MARKETPLACE_UNLOAD,
                document_id=request.id,
                event_type=EVENT_STATUS_CHANGED,
                actor=actor,
                qty=_unload_qty(connection, request),
                payload_json={"from": before, "to": after},
            )
        )
    rows.extend(
        _field_change_rows(
            request,
            actor=actor,
            document_type=DOCUMENT_TYPE_MARKETPLACE_UNLOAD,
            fields=(
                ("warehouse_id", EVENT_WAREHOUSE_CHANGED),
                ("wb_mp_warehouse_id", EVENT_WAREHOUSE_CHANGED),
                ("planned_shipment_date", EVENT_PLANNED_DATE_CHANGED),
            ),
        )
    )
    return rows


def _field_change_rows(
    document: InboundIntakeRequest | FbsSupply | MarketplaceUnloadRequest,
    *,
    actor: DocumentEventActor,
    document_type: str,
    fields: Sequence[tuple[str, str]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for field, event_type in fields:
        change = _history_pair(document, field)
        if change is None:
            continue
        before, after = change
        rows.append(
            _event_row(
                tenant_id=document.tenant_id,
                document_type=document_type,
                document_id=document.id,
                event_type=event_type,
                actor=actor,
                payload_json={
                    "field": field,
                    "value_before": _json_value(before),
                    "value_after": _json_value(after),
                },
            )
        )
    return rows


def _inbound_context(
    connection: Connection, request_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID] | None:
    row = connection.execute(
        select(InboundIntakeRequest.tenant_id, InboundIntakeRequest.id).where(
            InboundIntakeRequest.id == request_id
        )
    ).one_or_none()
    return (row[0], row[1]) if row is not None else None


def _unload_context(
    connection: Connection, request_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID] | None:
    row = connection.execute(
        select(MarketplaceUnloadRequest.tenant_id, MarketplaceUnloadRequest.id).where(
            MarketplaceUnloadRequest.id == request_id
        )
    ).one_or_none()
    return (row[0], row[1]) if row is not None else None


def _as_int(value: object) -> int:
    return int(cast(Any, value) or 0)


def _inbound_line_change_rows(
    connection: Connection, line: InboundIntakeLine, actor: DocumentEventActor
) -> list[dict[str, object]]:
    context = _inbound_context(connection, line.request_id)
    if context is None:
        return []
    tenant_id, document_id = context
    rows: list[dict[str, object]] = []
    for field in ("expected_qty", "actual_qty"):
        change = _history_pair(line, field)
        if change is None:
            continue
        before, after = change
        rows.append(
            _event_row(
                tenant_id=tenant_id,
                document_type=DOCUMENT_TYPE_INBOUND_INTAKE,
                document_id=document_id,
                event_type=EVENT_LINE_QTY_CHANGED,
                actor=actor,
                qty=_as_int(after),
                product_id=line.product_id,
                payload_json={"qty_before": _as_int(before), "qty_after": _as_int(after)},
            )
        )
    defect = _history_pair(line, "defective_qty")
    if defect is not None:
        before, after = defect
        rows.append(
            _event_row(
                tenant_id=tenant_id,
                document_type=DOCUMENT_TYPE_INBOUND_INTAKE,
                document_id=document_id,
                event_type=EVENT_DEFECT_QTY_CHANGED,
                actor=actor,
                qty=_as_int(after),
                product_id=line.product_id,
                payload_json={
                    "field": "defective_qty",
                    "value_before": _as_int(before),
                    "value_after": _as_int(after),
                },
            )
        )
    return rows


def _unload_line_change_rows(
    connection: Connection, line: MarketplaceUnloadLine, actor: DocumentEventActor
) -> list[dict[str, object]]:
    change = _history_pair(line, "quantity")
    context = _unload_context(connection, line.request_id)
    if change is None or context is None:
        return []
    before, after = change
    return [
        _event_row(
            tenant_id=context[0],
            document_type=DOCUMENT_TYPE_MARKETPLACE_UNLOAD,
            document_id=context[1],
            event_type=EVENT_LINE_QTY_CHANGED,
            actor=actor,
            qty=_as_int(after),
            product_id=line.product_id,
            payload_json={"qty_before": _as_int(before), "qty_after": _as_int(after)},
        )
    ]


def _line_added_row(
    connection: Connection, line: InboundIntakeLine, actor: DocumentEventActor
) -> dict[str, object] | None:
    context = _inbound_context(connection, line.request_id)
    if context is None:
        return None
    qty = int(line.expected_qty)
    return _event_row(
        tenant_id=context[0],
        document_type=DOCUMENT_TYPE_INBOUND_INTAKE,
        document_id=context[1],
        event_type=EVENT_LINE_ADDED,
        actor=actor,
        qty=qty,
        product_id=line.product_id,
        payload_json={"qty_before": 0, "qty_after": qty},
    )


def _line_removed_row(
    connection: Connection, line: InboundIntakeLine, actor: DocumentEventActor
) -> dict[str, object] | None:
    context = _inbound_context(connection, line.request_id)
    if context is None:
        return None
    qty = int(line.expected_qty)
    return _event_row(
        tenant_id=context[0],
        document_type=DOCUMENT_TYPE_INBOUND_INTAKE,
        document_id=context[1],
        event_type=EVENT_LINE_REMOVED,
        actor=actor,
        qty=qty,
        product_id=line.product_id,
        payload_json={"qty_before": qty, "qty_after": 0},
    )


def _unload_line_added_row(
    connection: Connection, line: MarketplaceUnloadLine, actor: DocumentEventActor
) -> dict[str, object] | None:
    context = _unload_context(connection, line.request_id)
    if context is None:
        return None
    qty = int(line.quantity)
    return _event_row(
        tenant_id=context[0],
        document_type=DOCUMENT_TYPE_MARKETPLACE_UNLOAD,
        document_id=context[1],
        event_type=EVENT_LINE_ADDED,
        actor=actor,
        qty=qty,
        product_id=line.product_id,
        payload_json={"qty_before": 0, "qty_after": qty},
    )


def _unload_line_removed_row(
    connection: Connection, line: MarketplaceUnloadLine, actor: DocumentEventActor
) -> dict[str, object] | None:
    context = _unload_context(connection, line.request_id)
    if context is None:
        return None
    qty = int(line.quantity)
    return _event_row(
        tenant_id=context[0],
        document_type=DOCUMENT_TYPE_MARKETPLACE_UNLOAD,
        document_id=context[1],
        event_type=EVENT_LINE_REMOVED,
        actor=actor,
        qty=qty,
        product_id=line.product_id,
        payload_json={"qty_before": qty, "qty_after": 0},
    )


def _fbs_order_change_rows(
    connection: Connection, order: FbsOrder, actor: DocumentEventActor
) -> list[dict[str, object]]:
    change = _history_pair(order, "supply_id")
    if change is None:
        return []
    before, after = change
    rows: list[dict[str, object]] = []
    for supply_id, event_type, qty_before, qty_after in (
        (before, EVENT_LINE_REMOVED, 1, 0),
        (after, EVENT_LINE_ADDED, 0, 1),
    ):
        if not isinstance(supply_id, uuid.UUID):
            continue
        tenant_id = connection.scalar(select(FbsSupply.tenant_id).where(FbsSupply.id == supply_id))
        if tenant_id is None:
            continue
        rows.append(
            _event_row(
                tenant_id=tenant_id,
                document_type=DOCUMENT_TYPE_FBS_SUPPLY,
                document_id=supply_id,
                event_type=event_type,
                actor=actor,
                qty=qty_after or qty_before,
                product_id=order.product_id,
                payload_json={"qty_before": qty_before, "qty_after": qty_after},
            )
        )
    return rows


def _write_rows_safely(connection: Connection, rows: Sequence[dict[str, object]]) -> None:
    for row in rows:
        savepoint = connection.begin_nested()
        try:
            _insert_event_row(connection, row)
        except Exception:
            savepoint.rollback()
            logger.exception(
                "document event write failed: document_type=%s document_id=%s event_type=%s",
                row["document_type"],
                row["document_id"],
                row["event_type"],
            )
        else:
            savepoint.commit()


def _insert_event_row(connection: Connection, row: dict[str, object]) -> None:
    connection.execute(insert(DocumentEvent).values(**row))


def _before_flush(session: Session, _flush_context: object, _instances: object) -> None:
    try:
        connection = session.connection()
        rows = _document_rows(session, connection)
        if not rows:
            return
        if connection.dialect.name == "postgresql":
            connection.execute(
                select(func.set_config("wms.document_event_writer", "application", True))
            )
        _write_rows_safely(connection, rows)
    except Exception:
        logger.exception("document event collection failed")


def install_document_event_tracking() -> None:
    """Install the transaction observer once for all sync and async ORM sessions."""
    if not event.contains(Session, "before_flush", _before_flush):
        event.listen(Session, "before_flush", _before_flush)
