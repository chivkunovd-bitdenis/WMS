from __future__ import annotations

# Writer adapters deliberately accept already-loaded source models from five services.
# ruff's B009 is not meaningful for their shared structural interface.
# ruff: noqa: B009
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_intake import InboundIntakeRequest
from app.models.operation_fact import (
    OPERATION_SOURCE_SYSTEM,
    OPERATION_SOURCE_USER,
    OPERATION_SOURCES,
    OperationFact,
    OperationFactLine,
)
from app.models.product import Product
from app.models.seller import Seller
from app.models.user import User
from app.models.warehouse import Warehouse


class OperationFactError(ValueError):
    pass


# В системе живут два словаря маркетплейса: приёмка пишет `wildberries`, а
# заказы и поставки — `wb`. Пять адаптеров фактов писали в одну колонку из обоих,
# и читателей у неё пока нет — значит это мина под первый же отчёт в разрезе
# площадок, а не сегодняшняя поломка. Нормализуем на границе записи, пока цена
# правки нулевая.
_MARKETPLACE_ALIASES: dict[str, str] = {"wildberries": "wb"}


def normalize_marketplace(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    return _MARKETPLACE_ALIASES.get(normalized, normalized)


@dataclass(frozen=True)
class OperationFactLineInput:
    product_id: uuid.UUID | None
    sku_snapshot: str | None
    product_name_snapshot: str | None
    item_quantity: int


def line_input(
    product: object | None, product_id: uuid.UUID | None, quantity: int
) -> OperationFactLineInput:
    return OperationFactLineInput(
        product_id=product_id,
        sku_snapshot=getattr(product, "sku_code", None),
        product_name_snapshot=getattr(product, "name", None),
        item_quantity=quantity,
    )


async def record_inbound_completion(
    session: AsyncSession, request: InboundIntakeRequest, performer_id: uuid.UUID | None
) -> OperationFact:
    lines = [
        line_input(getattr(line, "product", None), line.product_id, int(line.posted_qty))
        for line in request.lines
        if int(line.posted_qty) > 0
    ]
    if request.completed_by_user_id is None:
        request.completed_by_user_id = performer_id
    return await write_operation_fact(
        session,
        tenant_id=request.tenant_id,
        operation_code=(
            "return_completed" if request.operation_type == "return" else "inbound_completed"
        ),
        billable_service_code=("return" if request.operation_type == "return" else "inbound"),
        source_kind="inbound_intake_request",
        source_event_id=request.id,
        idempotency_key=f"inbound-completed:{request.id}",
        seller_id=request.seller_id,
        seller_name_snapshot=getattr(getattr(request, "seller", None), "name", None),
        warehouse_id=request.warehouse_id,
        marketplace=request.marketplace,
        document_type="inbound_intake",
        document_id=request.id,
        document_number_snapshot=request.document_number,
        actor_user_id=performer_id,
        actor_name_snapshot=None,
        occurred_at=request.posted_at or datetime.now(UTC),
        item_quantity=sum(line.item_quantity for line in lines),
        lines=lines,
    )


async def record_fbs_pick(
    session: AsyncSession,
    *,
    supply: object,
    pick: object,
    source_event_id: uuid.UUID,
    source_kind: str,
    actor_user_id: uuid.UUID | None,
    occurred_at: datetime,
    reversal: bool = False,
    original_source_event_id: uuid.UUID | None = None,
    product: object | None = None,
) -> OperationFact:
    """Persist one canonical FBS pick event, never deriving it from billing rows."""
    original_id: uuid.UUID | None = None
    if reversal:
        original = await session.scalar(
            select(OperationFact.id).where(
                OperationFact.tenant_id == getattr(supply, "tenant_id"),
                OperationFact.source_kind == source_kind,
                OperationFact.source_event_id == (original_source_event_id or source_event_id),
                OperationFact.operation_code == "fbs_pick",
            )
        )
        original_id = original
    product = product or getattr(pick, "product", None)
    return await write_operation_fact(
        session,
        tenant_id=getattr(supply, "tenant_id"),
        operation_code="fbs_pick_reversal" if reversal else "fbs_pick",
        billable_service_code="fbs_pick",
        source_kind=source_kind,
        source_event_id=source_event_id,
        idempotency_key=(
            f"fbs-pick-reversal:{source_event_id}" if reversal else f"fbs-pick:{source_event_id}"
        ),
        seller_id=getattr(supply, "seller_id"),
        seller_name_snapshot=getattr(getattr(supply, "seller", None), "name", None),
        warehouse_id=getattr(supply, "warehouse_id"),
        marketplace=getattr(supply, "marketplace"),
        document_type="fbs_supply",
        document_id=getattr(supply, "id"),
        document_number_snapshot=_fbs_supply_number(supply),
        actor_user_id=actor_user_id,
        actor_name_snapshot=None,
        occurred_at=occurred_at,
        item_quantity=1,
        reversal_of_id=original_id,
        lines=[line_input(product, getattr(pick, "product_id"), 1)],
    )


def _fbs_supply_number(supply: object) -> str | None:
    """Как поставка называется в отчёте.

    Номер документа у поставок FBS заполняется не всегда, и в расчётах строка
    выходила «Документ без номера» — по такой не понять, о какой поставке речь.
    Берём первое непустое из того, чем поставку зовут на экранах.
    """
    for attribute in ("document_number", "display_number", "wb_supply_id", "name"):
        value = getattr(supply, attribute, None)
        if isinstance(value, str) and value.strip():
            return value.strip()[:64]
    return None


async def record_packaging_event(
    session: AsyncSession,
    *,
    task: object,
    event: object,
    line: object | None = None,
    original_event_id: uuid.UUID | None = None,
) -> OperationFact:
    """Record only item-level pack actions. Labels and task state transitions are excluded."""
    is_reversal = getattr(event, "action") == "undo_last"
    line = line or getattr(event, "line", None)
    product = getattr(line, "product", None) or getattr(event, "product", None)
    original_id: uuid.UUID | None = None
    if is_reversal and original_event_id is not None:
        original_id = await session.scalar(
            select(OperationFact.id).where(
                OperationFact.tenant_id == getattr(task, "tenant_id"),
                OperationFact.source_kind == "packaging_task_event",
                OperationFact.source_event_id == original_event_id,
                OperationFact.operation_code == "packing_completed",
            )
        )
    quantity = int(getattr(event, "quantity"))
    seller_id = getattr(product, "seller_id", None)
    seller_name_snapshot = None
    if seller_id is not None:
        seller_name_snapshot = await session.scalar(
            select(Seller.name).where(
                Seller.id == seller_id,
                Seller.tenant_id == getattr(task, "tenant_id"),
            )
        )
    return await write_operation_fact(
        session,
        tenant_id=getattr(task, "tenant_id"),
        operation_code="packing_reversal" if is_reversal else "packing_completed",
        billable_service_code="packaging",
        source_kind="packaging_task_event",
        source_event_id=getattr(event, "id"),
        idempotency_key=(
            f"packaging-reversal:{getattr(event, 'id')}"
            if is_reversal
            else f"packaging:{getattr(event, 'id')}"
        ),
        seller_id=seller_id,
        seller_name_snapshot=seller_name_snapshot,
        warehouse_id=getattr(task, "warehouse_id"),
        marketplace=None,
        document_type="packaging_task",
        document_id=getattr(task, "id"),
        document_number_snapshot=getattr(task, "document_number", None),
        actor_user_id=getattr(event, "created_by_user_id", None),
        actor_name_snapshot=None,
        occurred_at=getattr(event, "created_at") or datetime.now(UTC),
        item_quantity=quantity,
        reversal_of_id=original_id,
        lines=[line_input(product, getattr(event, "product_id", None), quantity)],
    )


async def record_marketplace_unload(
    session: AsyncSession,
    *,
    request: object,
    distributed: dict[uuid.UUID, int],
    occurred_at: datetime,
    performer_id: uuid.UUID | None,
    reversal: bool = False,
) -> OperationFact:
    original_id: uuid.UUID | None = None
    if reversal:
        original_id = await session.scalar(
            select(OperationFact.id).where(
                OperationFact.tenant_id == getattr(request, "tenant_id"),
                OperationFact.source_kind == "marketplace_unload_request",
                OperationFact.source_event_id == getattr(request, "id"),
                OperationFact.operation_code == "marketplace_outbound_completed",
            )
        )
    products = {
        getattr(line, "product_id"): getattr(line, "product", None)
        for line in getattr(request, "lines")
    }
    lines = [
        line_input(products.get(product_id), product_id, quantity)
        for product_id, quantity in distributed.items()
        if quantity > 0
    ]
    return await write_operation_fact(
        session,
        tenant_id=getattr(request, "tenant_id"),
        operation_code=(
            "marketplace_outbound_reversal" if reversal else "marketplace_outbound_completed"
        ),
        billable_service_code="marketplace_outbound",
        source_kind="marketplace_unload_request",
        source_event_id=getattr(request, "id"),
        idempotency_key=(
            f"marketplace-unload-reversal:{getattr(request, 'id')}"
            if reversal
            else f"marketplace-unload-shipped:{getattr(request, 'id')}"
        ),
        seller_id=getattr(request, "seller_id"),
        seller_name_snapshot=getattr(getattr(request, "seller", None), "name", None),
        warehouse_id=getattr(request, "warehouse_id"),
        marketplace=getattr(request, "marketplace"),
        document_type="marketplace_unload",
        document_id=getattr(request, "id"),
        document_number_snapshot=getattr(request, "document_number", None),
        actor_user_id=performer_id,
        actor_name_snapshot=None,
        occurred_at=occurred_at,
        item_quantity=sum(line.item_quantity for line in lines),
        reversal_of_id=original_id,
        lines=lines,
    )


async def record_storage_fixed(
    session: AsyncSession,
    *,
    statement: object,
    source_event_id: uuid.UUID,
    occurred_at: datetime,
) -> OperationFact:
    return await write_operation_fact(
        session,
        tenant_id=getattr(statement, "tenant_id"),
        operation_code="storage_fixed",
        billable_service_code="storage",
        source_kind="storage_measurement"
        if source_event_id != getattr(statement, "id")
        else "storage_statement",
        source_event_id=source_event_id,
        idempotency_key=f"storage-fixed:{source_event_id}",
        seller_id=getattr(statement, "seller_id"),
        seller_name_snapshot=getattr(getattr(statement, "seller", None), "name", None),
        warehouse_id=getattr(statement, "warehouse_id"),
        document_type="storage_statement",
        document_id=getattr(statement, "id"),
        document_number_snapshot=getattr(statement, "document_number", None),
        actor_user_id=None,
        actor_name_snapshot=None,
        source="system",
        occurred_at=occurred_at,
        item_quantity=0,
        lines=[],
    )


async def write_operation_fact(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    operation_code: str,
    source_kind: str,
    source_event_id: uuid.UUID,
    document_type: str,
    document_id: uuid.UUID,
    occurred_at: datetime,
    item_quantity: int,
    idempotency_key: str | None = None,
    billable_service_code: str | None = None,
    seller_id: uuid.UUID | None = None,
    seller_name_snapshot: str | None = None,
    warehouse_id: uuid.UUID | None = None,
    marketplace: str | None = None,
    document_number_snapshot: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_name_snapshot: str | None = None,
    source: str | None = None,
    reversal_of_id: uuid.UUID | None = None,
    integrity_status: str = "complete",
    lines: list[OperationFactLineInput] | None = None,
) -> OperationFact:
    if not operation_code:
        raise OperationFactError("operation_code_required")
    if not source_kind:
        raise OperationFactError("source_kind_required")
    if item_quantity < 0:
        raise OperationFactError("item_quantity_negative")
    resolved_source = source or (
        OPERATION_SOURCE_USER if actor_user_id else OPERATION_SOURCE_SYSTEM
    )
    if resolved_source not in OPERATION_SOURCES:
        raise OperationFactError("invalid_source")
    if resolved_source == OPERATION_SOURCE_USER and actor_user_id is None:
        raise OperationFactError("user_actor_required")
    if resolved_source == OPERATION_SOURCE_SYSTEM and actor_user_id is not None:
        raise OperationFactError("system_actor_must_be_null")
    materialized_lines = list(lines or [])
    if any(line.item_quantity < 0 for line in materialized_lines):
        raise OperationFactError("line_quantity_negative")
    if (
        materialized_lines
        and sum(line.item_quantity for line in materialized_lines) != item_quantity
    ):
        raise OperationFactError("line_quantity_mismatch")

    existing = await session.scalar(
        select(OperationFact).where(
            OperationFact.tenant_id == tenant_id,
            OperationFact.source_kind == source_kind,
            OperationFact.source_event_id == source_event_id,
            OperationFact.operation_code == operation_code,
        )
    )
    if existing is not None:
        return existing
    if idempotency_key is not None:
        replay = await session.scalar(
            select(OperationFact).where(
                OperationFact.tenant_id == tenant_id,
                OperationFact.idempotency_key == idempotency_key,
            )
        )
        if replay is not None:
            if (
                replay.source_kind != source_kind
                or replay.source_event_id != source_event_id
                or replay.operation_code != operation_code
            ):
                raise OperationFactError("idempotency_key_reused")
            return replay
    if reversal_of_id is not None:
        reversal_of = await session.scalar(
            select(OperationFact).where(
                OperationFact.id == reversal_of_id,
                OperationFact.tenant_id == tenant_id,
            )
        )
        if reversal_of is None:
            raise OperationFactError("reversal_fact_not_found")

    if seller_id is not None:
        seller = await session.scalar(
            select(Seller).where(Seller.id == seller_id, Seller.tenant_id == tenant_id)
        )
        if seller is None:
            raise OperationFactError("seller_tenant_mismatch")
    if warehouse_id is not None:
        warehouse = await session.scalar(
            select(Warehouse).where(Warehouse.id == warehouse_id, Warehouse.tenant_id == tenant_id)
        )
        if warehouse is None:
            raise OperationFactError("warehouse_tenant_mismatch")
    resolved_actor_snapshot = actor_name_snapshot
    if actor_user_id is not None:
        actor = await session.scalar(
            select(User).where(User.id == actor_user_id, User.tenant_id == tenant_id)
        )
        if actor is None:
            raise OperationFactError("actor_tenant_mismatch")
        resolved_actor_snapshot = actor.email
    for line in materialized_lines:
        if line.product_id is None:
            continue
        product = await session.scalar(
            select(Product).where(Product.id == line.product_id, Product.tenant_id == tenant_id)
        )
        if product is None:
            raise OperationFactError("product_tenant_mismatch")

    fact = OperationFact(
        tenant_id=tenant_id,
        operation_code=operation_code,
        billable_service_code=billable_service_code,
        source_kind=source_kind,
        source_event_id=source_event_id,
        idempotency_key=idempotency_key,
        seller_id=seller_id,
        seller_name_snapshot=seller_name_snapshot,
        warehouse_id=warehouse_id,
        marketplace=normalize_marketplace(marketplace),
        document_type=document_type,
        document_id=document_id,
        document_number_snapshot=document_number_snapshot,
        actor_user_id=actor_user_id,
        actor_name_snapshot=resolved_actor_snapshot,
        source=resolved_source,
        occurred_at=occurred_at,
        item_quantity=item_quantity,
        reversal_of_id=reversal_of_id,
        integrity_status=integrity_status,
        lines=[
            OperationFactLine(
                tenant_id=tenant_id,
                product_id=line.product_id,
                sku_snapshot=line.sku_snapshot,
                product_name_snapshot=line.product_name_snapshot,
                item_quantity=line.item_quantity,
            )
            for line in materialized_lines
        ],
    )
    try:
        async with session.begin_nested():
            session.add(fact)
            await session.flush()
    except IntegrityError as exc:
        concurrent = await session.scalar(
            select(OperationFact).where(
                OperationFact.tenant_id == tenant_id,
                OperationFact.source_kind == source_kind,
                OperationFact.source_event_id == source_event_id,
                OperationFact.operation_code == operation_code,
            )
        )
        if concurrent is not None:
            return concurrent
        raise OperationFactError("operation_fact_conflict") from exc
    return fact
