"""Local operation creation/retry. B3 intentionally prevents auth and submission."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.withdrawal_repository import (
    WithdrawalError,
    WithdrawalScope,
    current_items,
    eligible_rows,
    get_operation,
    lock_seller,
)
from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.fbs_supply import FbsSupply
from app.models.marking_withdrawal import WithdrawalItem, WithdrawalOperation
from app.services.wb_order_price_service import WbPriceDataError, resolve_wb_product_cost

INTEGRATION_GATE = "B3_AUTH_PROFILE_UNCONFIRMED"


async def _new_items(
    session: AsyncSession,
    scope: WithdrawalScope,
    operation: WithdrawalOperation,
    rows: list[tuple[FbsOrderMarking, FbsOrder, FbsSupply]],
) -> None:
    for marking, order, supply in rows:
        assert supply.delivered_at is not None
        item = WithdrawalItem(
            operation_id=operation.id,
            tenant_id=scope.tenant_id,
            seller_id=scope.seller_id,
            user_id=scope.user_id,
            attempt=operation.attempt,
            marking_id=marking.id,
            marking_code_id=marking.marking_code_id,
            order_id=order.id,
            supply_id=supply.id,
            cis=marking.value,
            source=marking.source,
            delivered_at=supply.delivered_at,
            state="pending",
            holds_claim=True,
        )
        try:
            price = await resolve_wb_product_cost(
                session,
                tenant_id=scope.tenant_id,
                seller_id=scope.seller_id,
                order_id=order.id,
            )
            item.price_snapshot_id = price.snapshot_id
            item.product_cost = price.product_cost
        except WbPriceDataError as exc:
            item.price_snapshot_id = exc.snapshot_id
            item.state = "failed"
            item.error = {"source": "local", "code": exc.code, "message": str(exc)}
        session.add(item)
    await session.flush()
    items = await current_items(session, scope, operation.id)
    states = {item.state for item in items}
    operation.state = (
        "created"
        if "pending" in states
        else "partial_failed"
        if states == {"failed", "succeeded"}
        else "succeeded"
        if states == {"succeeded"}
        else "failed"
    )


async def create_operation(
    session: AsyncSession,
    scope: WithdrawalScope,
    *,
    row_ids: list[uuid.UUID],
    client_request_id: uuid.UUID,
    environment: str = "sandbox",
) -> WithdrawalOperation:
    if not row_ids or len(row_ids) > 250 or len(set(row_ids)) != len(row_ids):
        raise WithdrawalError("invalid_selection", 422)
    row_ids = sorted(row_ids)
    selection_hash = hashlib.sha256("\n".join(map(str, row_ids)).encode()).hexdigest()
    await lock_seller(session, scope)
    existing = await session.scalar(
        select(WithdrawalOperation).where(
            WithdrawalOperation.tenant_id == scope.tenant_id,
            WithdrawalOperation.seller_id == scope.seller_id,
            WithdrawalOperation.client_request_id == client_request_id,
        )
    )
    if existing:
        if existing.selection_hash != selection_hash:
            raise WithdrawalError("idempotency_selection_mismatch")
        return existing
    rows = [
        tuple(row)
        for row in (
            await session.execute(
                eligible_rows(scope)
                .where(
                    FbsOrderMarking.id.in_(row_ids),
                )
                .order_by(FbsOrderMarking.id)
                .with_for_update(of=FbsOrderMarking)
            )
        ).all()
    ]
    if len(rows) != len(row_ids):
        raise WithdrawalError("withdrawal_rows_not_found", 404)
    claims = list(
        await session.scalars(
            select(WithdrawalItem).where(
                WithdrawalItem.tenant_id == scope.tenant_id,
                WithdrawalItem.cis.in_([row[0].value for row in rows]),
                WithdrawalItem.holds_claim.is_(True),
            )
        )
    )
    if claims:
        operations = {item.operation_id for item in claims}
        # A fresh click selecting already active rows resumes their operation.
        # Mixed/new selections fail atomically instead of dropping requested rows.
        if (
            len(operations) == 1
            and len(claims) == len(rows)
            and all(item.seller_id == scope.seller_id for item in claims)
        ):
            return await get_operation(session, scope, next(iter(operations)))
        raise WithdrawalError("selection_overlaps_existing_operation")
    operation = WithdrawalOperation(
        tenant_id=scope.tenant_id,
        seller_id=scope.seller_id,
        user_id=scope.user_id,
        client_request_id=client_request_id,
        selection_hash=selection_hash,
        state="created",
        attempt=1,
        environment=environment,
        attempt_started_at=datetime.now(UTC),
    )
    session.add(operation)
    await session.flush()
    await _new_items(session, scope, operation, rows)
    return operation


async def retry_operation(
    session: AsyncSession,
    scope: WithdrawalScope,
    operation_id: uuid.UUID,
    *,
    expected_attempt: int,
) -> WithdrawalOperation:
    await lock_seller(session, scope)
    operation = await get_operation(session, scope, operation_id, lock=True)
    # expected_attempt makes a repeated retry request idempotent even if a
    # local data failure is immediate. No elapsed-time reset of unknown work.
    if expected_attempt < operation.attempt:
        return operation
    if expected_attempt != operation.attempt:
        raise WithdrawalError("attempt_mismatch")
    if operation.state not in {"failed", "partial_failed"}:
        return operation
    old_items = [
        item for item in await current_items(session, scope, operation.id) if item.state == "failed"
    ]
    if not old_items:
        return operation
    ids = [item.marking_id for item in old_items]
    rows = [
        tuple(row)
        for row in (
            await session.execute(
                eligible_rows(scope)
                .where(
                    FbsOrderMarking.id.in_(ids),
                )
                .order_by(FbsOrderMarking.id)
                .with_for_update(of=FbsOrderMarking)
            )
        ).all()
    ]
    if len(rows) != len(ids):
        raise WithdrawalError("withdrawal_rows_not_found", 404)
    for item in old_items:
        item.holds_claim = False
    await session.flush()
    operation.attempt += 1
    operation.token_enc = None
    operation.token_expires_at = None
    operation.auth_uuid = None
    operation.auth_challenge = None
    operation.certificate_thumbprint = None
    operation.certificate_metadata = None
    operation.participant_inn = None
    operation.auth_signature_hash = None
    operation.workflow_error = None
    operation.workflow_lease_id = None
    operation.workflow_lease_until = None
    operation.attempt_started_at = datetime.now(UTC)
    await _new_items(session, scope, operation, rows)
    # New pending items still need fresh cises/MOD, bytes and signatures after B3.
    return operation
