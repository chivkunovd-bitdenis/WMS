"""At-most-once create dispatcher for the durable signed-document queue."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.withdrawal_repository import WithdrawalError, WithdrawalScope
from app.models.marking_withdrawal import WithdrawalDocument, WithdrawalOperation
from app.services.true_api_withdrawal import AuthSession, CreateOutcome, TrueApiError
from app.services.withdrawal_orchestration import current_auth
from app.services.withdrawal_recovery import record_create_result
from app.services.withdrawal_runtime import WithdrawalRuntime


@dataclass(frozen=True)
class SubmitWork:
    scope: WithdrawalScope
    operation_id: uuid.UUID
    document_id: uuid.UUID
    environment: str
    pg: str
    auth: AuthSession = field(repr=False)
    exact_payload: bytes = field(repr=False)
    signature: str = field(repr=False)


async def claim_submit(session: AsyncSession, runtime: WithdrawalRuntime) -> SubmitWork | None:
    if not runtime.enabled:
        return None
    now = datetime.now(UTC)
    eligible = (
        WithdrawalDocument.state == "pending_signature",
        WithdrawalDocument.signature.is_not(None),
        or_(WithdrawalDocument.next_poll_at.is_(None), WithdrawalDocument.next_poll_at <= now),
    )
    operation = await session.scalar(
        select(WithdrawalOperation)
        .where(
            WithdrawalOperation.environment == runtime.config.environment,
            exists(
                select(WithdrawalDocument.id).where(
                    WithdrawalDocument.operation_id == WithdrawalOperation.id,
                    *eligible,
                )
            ),
        )
        .order_by(WithdrawalOperation.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if operation is None:
        await session.commit()
        return None
    document = await session.scalar(
        select(WithdrawalDocument)
        .where(
            WithdrawalDocument.operation_id == operation.id,
            WithdrawalDocument.tenant_id == operation.tenant_id,
            WithdrawalDocument.seller_id == operation.seller_id,
            *eligible,
        )
        .order_by(WithdrawalDocument.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if document is None:
        await session.commit()
        return None
    try:
        auth = current_auth(operation)
        if (
            document.environment != operation.environment
            or document.participant_inn != auth.participant_inn
            or document.certificate_thumbprint != operation.certificate_thumbprint
            or hashlib.sha256(document.exact_payload).hexdigest() != document.payload_sha256
        ):
            raise WithdrawalError("withdrawal_submission_binding_mismatch")
    except WithdrawalError as exc:
        operation.workflow_error = {"code": exc.code}
        document.next_poll_at = now + timedelta(seconds=60)
        await session.commit()
        return None
    assert document.signature is not None
    work = SubmitWork(
        WithdrawalScope(operation.tenant_id, operation.seller_id, operation.user_id),
        operation.id,
        document.id,
        operation.environment,
        document.pg,
        auth,
        document.exact_payload,
        document.signature,
    )
    # Commit intent before crossing the provider boundary. A crash anywhere after
    # this point goes to the existing read-only recovery path, never another POST.
    document.state = "submitting"
    document.request_started_at = now
    document.next_poll_at = now + timedelta(seconds=2)
    document.lease_id = uuid.uuid4()
    document.lease_until = now + timedelta(minutes=5)
    operation.state = "submitting"
    await session.commit()
    return work


async def submit_one(
    sessions: async_sessionmaker[AsyncSession],
    runtime: WithdrawalRuntime,
) -> bool:
    if not runtime.enabled:
        return False
    async with sessions() as session:
        work = await claim_submit(session, runtime)
    if work is None:
        return False
    client = runtime.client(work.auth.participant_inn, work.environment)
    external_id = None
    error = None
    try:
        external_id = await client.create_document(
            work.auth,
            pg=work.pg,
            exact_payload=work.exact_payload,
            detached_signature=work.signature,
        )
    except TrueApiError as exc:
        error = exc
    except Exception:
        # Do not log transport/request details. Even an unexpected exception
        # after dispatch intent is conservative unknown, not permission to POST.
        error = TrueApiError("submit_interrupted", create_outcome=CreateOutcome.UNCERTAIN)
    async with sessions() as session:
        await record_create_result(
            session,
            work.scope,
            operation_id=work.operation_id,
            document_id=work.document_id,
            gis_document_id=external_id,
            error=error,
        )
    return True
