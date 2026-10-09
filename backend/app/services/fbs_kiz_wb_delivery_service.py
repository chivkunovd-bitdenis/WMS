"""WMS-640: KIZ changes of the packing screen reach WB in the background.

The operator's request only changes WMS and queues the change as a WB operation
(``order_kiz_bind`` / ``order_kiz_unbind``, error code ``wb_queued``).  Right after
the response a background task calls :func:`deliver_order_kiz_to_wb`; the periodic
marking autopoll calls :func:`deliver_queued_for_seller` as a safety net.

Rules kept here:

* No row lock is held while WB is called: an operator action on the same order
  never waits for WB.  One worker at a time holds an operation (``wb_sending``).
* The removal of an old code is always sent before the write of a new one.
* A removal reads WB first and deletes only while WB still holds exactly that
  code; a lost answer is never followed by a blind second action.
* A write answered by WB goes to the existing pending verdict check; a temporary
  refusal (429, 408, 5xx, lost answer) stays with the existing read-first resend;
  a final refusal keeps the KIZ bound and turns the row red (WMS-635 R4.3).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.fbs_order import (
    CHECK_STATUS_ERROR,
    FBS_ORDER_STATUS_CANCELLED,
    MARKING_KIND_SGTIN,
    META_STATUS_REJECTED,
    FbsOrder,
    FbsOrderMarking,
)
from app.models.fbs_wb_operation import (
    WB_OPERATION_STATE_CONFIRMED,
    WB_OPERATION_STATE_FAILED,
    WB_OPERATION_STATE_PENDING_CONFIRMATION,
    FbsWbOperation,
)
from app.services import fbs_marking_service as marking_svc
from app.services import wildberries_fbs_client as wb_fbs
from app.services.marketplace_scope import is_wildberries
from app.services.wildberries_errors import WildberriesBusinessError, WildberriesClientError

logger = logging.getLogger(__name__)

# A worker that took an operation and vanished: after this long the operation is
# treated as a lost answer and goes to the read-first reconciliation.
SENDING_LEASE = timedelta(seconds=150)


@dataclass(frozen=True)
class _BindJob:
    op_id: uuid.UUID
    marking_id: uuid.UUID
    value: str
    wb_order_id: int
    replace: bool
    read_first: bool
    token: str


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _claimed_at(op: FbsWbOperation) -> datetime | None:
    raw = (op.response_summary_json or {}).get("claimed_at")
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _sending_is_fresh(op: FbsWbOperation) -> bool:
    claimed = _claimed_at(op)
    return claimed is not None and _now() - claimed < SENDING_LEASE


def _take(op: FbsWbOperation) -> None:
    op.error_code = marking_svc.KIZ_WB_SENDING
    op.response_summary_json = {"claimed_at": _now().isoformat()}


def _is_temporary(exc: WildberriesClientError) -> bool:
    return (
        exc.code == "transport_error"
        or exc.status_code in {408, 429}
        or (exc.status_code is not None and exc.status_code >= 500)
    )


async def _lock_operation(session: AsyncSession, op_id: uuid.UUID) -> FbsWbOperation | None:
    operation: FbsWbOperation | None = await session.scalar(
        select(FbsWbOperation)
        .where(FbsWbOperation.id == op_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return operation


async def _release_operation(session: AsyncSession, op_id: uuid.UUID, error_code: str) -> None:
    """Give the operation back with the reason; the next round tries again."""
    await session.rollback()
    op = await _lock_operation(session, op_id)
    if op is not None and op.state == WB_OPERATION_STATE_PENDING_CONFIRMATION:
        op.error_code = error_code
    await session.commit()


async def _finish_operation(
    session: AsyncSession, op_id: uuid.UUID, *, state: str, error_code: str | None
) -> None:
    await session.rollback()
    op = await _lock_operation(session, op_id)
    if op is not None and op.state == WB_OPERATION_STATE_PENDING_CONFIRMATION:
        op.state = state
        op.error_code = error_code
        if state == WB_OPERATION_STATE_CONFIRMED:
            op.confirmed_at = _now()
        else:
            op.failed_at = _now()
    await session.commit()


async def _delete_kiz_in_wb(
    http_client: httpx.AsyncClient, token: str, wb_order_id: int
) -> None:
    """Delete the order's KIZ in WB; «already absent» is a success."""
    try:
        await wb_fbs.delete_marketplace_order_meta(
            http_client, api_token=token, order_id=wb_order_id, key=MARKING_KIND_SGTIN
        )
    except WildberriesClientError as exc:
        if exc.status_code != 404:
            raise


# --- removal ---------------------------------------------------------------------


async def _deliver_unbind(
    session: AsyncSession, http_client: httpx.AsyncClient, op_id: uuid.UUID
) -> bool:
    """Remove one KIZ from WB.  True when the operation is finished."""
    op = await _lock_operation(session, op_id)
    if op is None or op.state != WB_OPERATION_STATE_PENDING_CONFIRMATION:
        await session.rollback()
        return True
    if op.error_code == marking_svc.KIZ_WB_SENDING and _sending_is_fresh(op):
        await session.rollback()
        return False
    value = str((op.request_summary_json or {}).get("value") or "")
    wb_order_id = int(op.wb_object_id or 0)
    tenant_id, seller_id = op.tenant_id, op.seller_id
    try:
        token = await marking_svc.require_marketplace_token(session, tenant_id, seller_id)
    except marking_svc.FbsMarkingError as exc:
        await session.rollback()
        logger.warning("WMS-640: KIZ removal %s waits, no WB token: %s", op_id, exc.code)
        return False
    _take(op)
    await session.commit()
    # No lock is held from here: WB may be slow, the operator is not waiting for it.
    try:
        rows = await marking_svc.fetch_marketplace_orders_meta_batch(
            http_client, api_token=token, order_ids=[wb_order_id]
        )
    except WildberriesClientError as exc:
        await _release_operation(session, op_id, marking_svc._wb_error_code(exc))
        return False
    row = next((one for one in rows if one.order_id == wb_order_id), None)
    if row is None:
        # No row for the order is no proof of anything.
        await _release_operation(session, op_id, "wb_pending_confirmation")
        return False
    bound = [
        detail.value for detail in row.meta_details
        if detail.key == MARKING_KIND_SGTIN and detail.value
    ]
    if any(marking_svc._same_marking_value(value, one) for one in bound):
        try:
            await _delete_kiz_in_wb(http_client, token, wb_order_id)
        except WildberriesClientError as exc:
            code = marking_svc._wb_error_code(exc)
            if _is_temporary(exc):
                await _release_operation(session, op_id, code)
                return False
            await _finish_operation(
                session, op_id, state=WB_OPERATION_STATE_FAILED, error_code=code
            )
            return True
    # Absent, or WB already holds another code: nothing of this KIZ is left to delete.
    await _finish_operation(
        session, op_id, state=WB_OPERATION_STATE_CONFIRMED, error_code=None
    )
    return True


# --- write -----------------------------------------------------------------------


async def _take_bind(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> _BindJob | None:
    order = await session.scalar(
        select(FbsOrder)
        .where(FbsOrder.id == order_id, FbsOrder.tenant_id == tenant_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if order is None or not is_wildberries(order):
        await session.rollback()
        return None
    marking = await session.scalar(
        select(FbsOrderMarking)
        .where(
            FbsOrderMarking.order_id == order_id,
            FbsOrderMarking.kind == MARKING_KIND_SGTIN,
            FbsOrderMarking.meta_status != META_STATUS_REJECTED,
        )
        .order_by(FbsOrderMarking.created_at.desc(), FbsOrderMarking.id.desc())
        .limit(1)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    operation = await marking_svc.pending_kiz_operation(session, marking) if marking else None
    if marking is None or operation is None:
        await session.rollback()
        return None
    if operation.error_code == marking_svc.KIZ_WB_SENDING:
        if not _sending_is_fresh(operation):
            # The worker is gone: its answer is lost, WB is read before any repeat.
            operation.error_code = "wb_transport_error"
            await session.commit()
        else:
            await session.rollback()
        return None
    if operation.error_code != marking_svc.KIZ_WB_QUEUED:
        await session.rollback()
        return None
    if order.status == FBS_ORDER_STATUS_CANCELLED:
        operation.state = WB_OPERATION_STATE_FAILED
        operation.failed_at = _now()
        operation.error_code = "order_cancelled"
        await session.commit()
        return None
    try:
        token = await marking_svc.require_marketplace_token(session, tenant_id, order.seller_id)
    except marking_svc.FbsMarkingError as exc:
        await session.rollback()
        logger.warning("WMS-640: KIZ write for order %s waits, no WB token: %s", order_id, exc.code)
        return None
    job = _BindJob(
        op_id=operation.id,
        marking_id=marking.id,
        value=marking.value,
        wb_order_id=int(order.wb_order_id),
        replace=bool((operation.request_summary_json or {}).get("replace")),
        read_first=bool((operation.request_summary_json or {}).get("read_first")),
        token=token,
    )
    _take(operation)
    await session.commit()
    return job


async def _finish_bind_refused(
    session: AsyncSession, job: _BindJob, exc: WildberriesClientError
) -> None:
    """WMS-635 R4.3: a final refusal keeps the KIZ bound; the row turns red, nothing is resent."""
    await session.rollback()
    operation = await _lock_operation(session, job.op_id)
    marking = await session.get(FbsOrderMarking, job.marking_id, with_for_update=True)
    reason: str | None = None
    if isinstance(exc, WildberriesBusinessError) and exc.meta_validation:
        reason = exc.meta_validation[0].reason
    code = (
        "meta_validation_fail"
        if isinstance(exc, WildberriesBusinessError)
        else marking_svc._wb_error_code(exc)
    )
    still_open = (
        operation is not None and operation.state == WB_OPERATION_STATE_PENDING_CONFIRMATION
    )
    if operation is not None and still_open:
        operation.state = WB_OPERATION_STATE_FAILED
        operation.failed_at = _now()
        operation.error_code = code
    if marking is not None and still_open:
        marking.meta_status = META_STATUS_REJECTED
        marking.check_status = CHECK_STATUS_ERROR
        marking.reason = reason or f"WB отклонил запись ({code})"
        order = await session.get(FbsOrder, marking.order_id, with_for_update=True)
        if order is not None:
            order.metadata_delivery_allowed = False
            order.metadata_last_checked_at = _now()
    await session.commit()


async def _deliver_bind(
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
) -> None:
    job = await _take_bind(session, tenant_id, order_id)
    if job is None:
        return
    # No lock is held from here: WB may be slow, the operator is not waiting for it.
    if job.replace:
        try:
            await _delete_kiz_in_wb(http_client, job.token, job.wb_order_id)
        except WildberriesClientError as exc:
            # The old code is still there: start again from the removal.
            await _release_operation(session, job.op_id, marking_svc.KIZ_WB_QUEUED)
            logger.info("WMS-640: old KIZ of order %s not removed yet: %s", order_id, exc)
            return
    if job.read_first:
        # A restored code may already be in WB: write it only while WB holds none.
        try:
            rows = await marking_svc.fetch_marketplace_orders_meta_batch(
                http_client, api_token=job.token, order_ids=[job.wb_order_id]
            )
        except WildberriesClientError:
            await _release_operation(session, job.op_id, marking_svc.KIZ_WB_QUEUED)
            return
        row = next((one for one in rows if one.order_id == job.wb_order_id), None)
        if row is None:
            await _release_operation(session, job.op_id, marking_svc.KIZ_WB_QUEUED)
            return
        bound = [
            detail.value for detail in row.meta_details
            if detail.key == MARKING_KIND_SGTIN and detail.value
        ]
        if bound:
            # WB has the code (or another one): the pending verdict check decides.
            await _release_operation(session, job.op_id, "wb_pending_confirmation")
            return
    try:
        await marking_svc.put_marketplace_order_meta(
            http_client,
            api_token=job.token,
            order_id=job.wb_order_id,
            kind=MARKING_KIND_SGTIN,
            value=job.value,
        )
    except WildberriesBusinessError as exc:
        await _finish_bind_refused(session, job, exc)
        return
    except WildberriesClientError as exc:
        if _is_temporary(exc):
            # The existing reconciliation reads WB first and sends the same KIZ
            # again only while WB holds no code.
            await _release_operation(session, job.op_id, marking_svc._wb_error_code(exc))
        else:
            await _finish_bind_refused(session, job, exc)
        return
    # WB took the write; its verdict is read by the existing pending-verdict check.
    await _release_operation(session, job.op_id, "wb_pending_confirmation")


# --- entry points ----------------------------------------------------------------


async def _open_unbind_ids(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> list[uuid.UUID]:
    return list(
        (
            await session.scalars(
                select(FbsWbOperation.id)
                .where(
                    FbsWbOperation.tenant_id == tenant_id,
                    FbsWbOperation.operation_kind == marking_svc.OPERATION_KIND_ORDER_KIZ_UNBIND,
                    FbsWbOperation.local_entity_id == order_id,
                    FbsWbOperation.state == WB_OPERATION_STATE_PENDING_CONFIRMATION,
                )
                .order_by(FbsWbOperation.created_at, FbsWbOperation.id)
            )
        ).all()
    )


async def deliver_order_queue(
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
) -> None:
    """Send this order's queued KIZ changes: removals first, then the write."""
    for op_id in await _open_unbind_ids(session, tenant_id, order_id):
        if not await _deliver_unbind(session, http_client, op_id):
            # The old code is still in WB: the new one must not be written yet.
            return
    await _deliver_bind(session, http_client, tenant_id, order_id)


async def deliver_order_kiz_to_wb(order_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """Background task started right after the operator's response; never raises."""
    try:
        async with httpx.AsyncClient() as http_client, SessionLocal() as session:
            await deliver_order_queue(session, http_client, tenant_id, order_id)
    except Exception:
        logger.exception("WMS-640: background KIZ delivery failed for order %s", order_id)


async def deliver_queued_for_seller(
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> int:
    """Safety net of the autopoll: whatever a lost background task left queued."""
    queued = (
        await session.execute(
            select(FbsWbOperation.local_entity_id, FbsWbOperation.local_entity_type)
            .where(
                FbsWbOperation.tenant_id == tenant_id,
                FbsWbOperation.seller_id == seller_id,
                FbsWbOperation.state == WB_OPERATION_STATE_PENDING_CONFIRMATION,
                FbsWbOperation.operation_kind.in_({
                    marking_svc.OPERATION_KIND_ORDER_KIZ_UNBIND,
                    marking_svc.OPERATION_KIND_ORDER_KIZ_BIND,
                }),
                FbsWbOperation.error_code.in_({
                    marking_svc.KIZ_WB_QUEUED, marking_svc.KIZ_WB_SENDING,
                })
                | (
                    FbsWbOperation.operation_kind == marking_svc.OPERATION_KIND_ORDER_KIZ_UNBIND
                ),
            )
        )
    ).all()
    await session.rollback()
    order_ids: dict[uuid.UUID, None] = {}
    for entity_id, entity_type in queued:
        if entity_id is None:
            continue
        if entity_type == "fbs_order":
            order_ids[entity_id] = None
        else:
            owner = await session.scalar(
                select(FbsOrderMarking.order_id).where(FbsOrderMarking.id == entity_id)
            )
            if owner is not None:
                order_ids[owner] = None
    await session.rollback()
    for order_id in order_ids:
        await deliver_order_queue(session, http_client, tenant_id, order_id)
    return len(order_ids)
