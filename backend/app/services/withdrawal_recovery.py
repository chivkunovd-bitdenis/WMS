"""Durable, leased read-only recovery. This module has no document-create call."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.withdrawal_repository import WithdrawalError, WithdrawalScope, get_operation
from app.models.marking_withdrawal import (
    WithdrawalDocument,
    WithdrawalItem,
    WithdrawalObservation,
    WithdrawalOperation,
)
from app.services.integration_fernet import decrypt_secret
from app.services.true_api_withdrawal import (
    AuthSession,
    CreateOutcome,
    DocumentCursor,
    DocumentInfo,
    DocumentOutcome,
    Environment,
    TrueApiError,
    TrueApiWithdrawalClient,
)


def aware(value: datetime) -> datetime:
    # SQLite test storage loses offsets; application writes UTC instants.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def poll_delay(poll_count: int) -> int:
    return (2, 5, 10, 30)[poll_count] if poll_count < 4 else 60


def _identity(body: Any) -> tuple[Any, ...] | None:
    if isinstance(body, (bytes, str)):
        try:
            body = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return None
    if not isinstance(body, dict) or body.get("action") != "DISTANCE":
        return None
    products = body.get("products")
    if not isinstance(products, list) or not products:
        return None
    costs: dict[str, int] = {}
    for product in products:
        if not isinstance(product, dict):
            return None
        cis, cost = product.get("cis"), product.get("product_cost")
        if not isinstance(cis, str) or not cis or type(cost) is not int or cis in costs:
            return None
        costs[cis] = cost
    for key in ("inn", "action_date"):
        if not isinstance(body.get(key), str) or not body[key]:
            return None
    return (
        body["action"],
        body["inn"],
        body["action_date"],
        body.get("fias_id"),
        body.get("kpp"),
        tuple(sorted(costs.items())),
    )


def body_matches(exact_payload: bytes, body: Any) -> bool:
    original = _identity(exact_payload)
    return original is not None and original == _identity(body)


@dataclass(frozen=True)
class RecoveryWork:
    document_id: uuid.UUID
    operation_id: uuid.UUID
    scope: WithdrawalScope
    lease_id: uuid.UUID
    environment: Environment
    pg: str
    participant_inn: str
    gis_document_id: str | None
    request_started_at: datetime | None
    request_finished_at: datetime | None
    exact_payload: bytes = field(repr=False)
    token_enc: str | None = field(repr=False)
    token_expires_at: datetime | None
    auth_matches: bool


async def claim_work(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> RecoveryWork | None:
    now = now or datetime.now(UTC)
    document = await session.scalar(
        select(WithdrawalDocument)
        .where(
            WithdrawalDocument.state.in_(["submitting", "submitted", "reconciling"]),
            WithdrawalDocument.next_poll_at <= now,
            or_(WithdrawalDocument.lease_until.is_(None), WithdrawalDocument.lease_until <= now),
        )
        .order_by(WithdrawalDocument.next_poll_at, WithdrawalDocument.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if document is None:
        await session.commit()
        return None
    operation = await session.scalar(
        select(WithdrawalOperation).where(
            WithdrawalOperation.id == document.operation_id,
            WithdrawalOperation.tenant_id == document.tenant_id,
            WithdrawalOperation.seller_id == document.seller_id,
        )
    )
    if operation is None:
        raise WithdrawalError("withdrawal_scope_corruption")
    lease = uuid.uuid4()
    document.lease_id = lease
    document.lease_until = now + timedelta(minutes=5)
    # A process dying during a POST must only recover by reads.
    if document.state == "submitting":
        document.state = "reconciling"
    work = RecoveryWork(
        document.id,
        operation.id,
        WithdrawalScope(document.tenant_id, document.seller_id, operation.user_id),
        lease,
        Environment(document.environment),
        document.pg,
        document.participant_inn,
        document.gis_document_id,
        document.request_started_at,
        document.request_finished_at,
        document.exact_payload,
        operation.token_enc,
        operation.token_expires_at,
        operation.environment == document.environment
        and operation.participant_inn == document.participant_inn
        and operation.certificate_thumbprint == document.certificate_thumbprint
        and hashlib.sha256(document.exact_payload).hexdigest() == document.payload_sha256,
    )
    await session.commit()
    return work


async def reconcile(
    client: TrueApiWithdrawalClient,
    auth: AuthSession,
    work: RecoveryWork,
) -> tuple[DocumentInfo | None, str | None, list[str]]:
    if work.gis_document_id:
        info = await client.document_info(auth, pg=work.pg, document_id=work.gis_document_id)
        # A known ID is enough for PARSE_ERROR, which may have no parseable body.
        return info, None, []
    if work.request_started_at is None:
        return None, "missing_request_timestamp", []
    start = aware(work.request_started_at)
    end = (
        aware(work.request_finished_at)
        if work.request_finished_at
        else start + timedelta(minutes=5)
    )
    cursor: DocumentCursor | None = None
    seen_cursors: set[DocumentCursor] = set()
    matches: dict[str, DocumentInfo] = {}
    # Bound each pass, but never interpret an incomplete scan as one exact match.
    for _page in range(100):
        page = await client.list_documents(
            auth,
            pg=work.pg,
            date_from=start - timedelta(minutes=2),
            date_to=end + timedelta(minutes=2),
            cursor=cursor,
        )
        for candidate in page.results:
            external_id = candidate.get("number")
            if not isinstance(external_id, str):
                return None, "invalid_reconciliation_candidate", list(matches)
            info = await client.document_info(auth, pg=work.pg, document_id=external_id)
            if info.raw.get("type") == "LK_RECEIPT" and body_matches(work.exact_payload, info.body):
                matches[info.document_id] = info
        if not page.next_page:
            break
        if page.next_cursor is None or page.next_cursor in seen_cursors:
            return None, "incomplete_reconciliation", list(matches)
        seen_cursors.add(page.next_cursor)
        cursor = page.next_cursor
    else:
        return None, "incomplete_reconciliation", list(matches)
    if len(matches) == 1:
        return next(iter(matches.values())), None, list(matches)
    return None, "possible_duplicate" if matches else None, list(matches)


async def _project(
    session: AsyncSession,
    operation: WithdrawalOperation,
    document: WithdrawalDocument,
) -> None:
    if document.state in {"failed", "succeeded"}:
        items = list(
            await session.scalars(
                select(WithdrawalItem).where(
                    WithdrawalItem.document_id == document.id,
                    WithdrawalItem.operation_id == operation.id,
                    WithdrawalItem.tenant_id == operation.tenant_id,
                    WithdrawalItem.seller_id == operation.seller_id,
                    WithdrawalItem.holds_claim.is_(True),
                )
            )
        )
        for item in items:
            item.state = document.state
            item.error = (
                None
                if document.state == "succeeded"
                else {
                    "source": "crpt",
                    "scope": "document",
                    "status": document.gis_status,
                    "http_status": document.http_status,
                    "errors": document.errors,
                    "commonErrors": document.common_errors,
                }
            )
    await session.flush()
    states = list(
        await session.scalars(
            select(WithdrawalItem.state).where(
                WithdrawalItem.operation_id == operation.id,
                WithdrawalItem.tenant_id == operation.tenant_id,
                WithdrawalItem.seller_id == operation.seller_id,
                WithdrawalItem.holds_claim.is_(True),
            )
        )
    )
    if states and all(state == "succeeded" for state in states):
        operation.state = "succeeded"
    elif states and all(state in {"failed", "succeeded"} for state in states):
        operation.state = "partial_failed" if "succeeded" in states else "failed"
    else:
        reconciling = await session.scalar(
            select(WithdrawalDocument.id)
            .where(
                WithdrawalDocument.operation_id == operation.id,
                WithdrawalDocument.tenant_id == operation.tenant_id,
                WithdrawalDocument.seller_id == operation.seller_id,
                WithdrawalDocument.state.in_(["reconciling", "submitting"]),
            )
            .limit(1)
        )
        operation.state = "reconciling" if reconciling else "submitted"


async def apply_recovery(
    session: AsyncSession,
    work: RecoveryWork,
    *,
    info: DocumentInfo | None = None,
    error: TrueApiError | None = None,
    incident: str | None = None,
    reconciliation_ids: list[str] | None = None,
    now: datetime | None = None,
) -> bool:
    now = now or datetime.now(UTC)
    operation = await get_operation(session, work.scope, work.operation_id, lock=True)
    document = await session.scalar(
        select(WithdrawalDocument)
        .where(
            WithdrawalDocument.id == work.document_id,
            WithdrawalDocument.operation_id == operation.id,
            WithdrawalDocument.tenant_id == work.scope.tenant_id,
            WithdrawalDocument.seller_id == work.scope.seller_id,
        )
        .with_for_update()
    )
    if document is None or document.lease_id != work.lease_id:
        await session.commit()
        return False  # An expired worker may not overwrite its successor.
    if document.state in {"succeeded", "failed"}:
        await session.commit()
        return False
    # Once two exact matches have been observed, disappearance from a later list
    # is not evidence that the duplicate disappeared. Preserve operator review.
    duplicate_incident = (
        document.incident == "possible_duplicate" or incident == "possible_duplicate"
    )
    document.incident = "possible_duplicate" if duplicate_incident else incident
    if reconciliation_ids:
        document.reconciliation_ids = sorted(
            set((document.reconciliation_ids or []) + reconciliation_ids)
        )
    if duplicate_incident:
        document.state = "reconciling"
    elif info:
        document.gis_document_id = info.document_id
        document.gis_status = info.status
        document.errors = info.errors
        document.common_errors = info.common_errors
        document.http_status = 200
        document.response_body = json.dumps(info.raw, ensure_ascii=False).encode()
        document.state = {
            DocumentOutcome.SUCCEEDED: "succeeded",
            DocumentOutcome.FAILED: "failed",
            DocumentOutcome.PENDING: "submitted",
            DocumentOutcome.UNKNOWN: "reconciling",
        }[info.outcome]
    elif error:
        # Read errors (including 401/403) never prove a create was rejected.
        document.http_status = error.status_code
        document.response_body = error.response_body
        document.incident = error.reason
        document.state = "reconciling"
    else:
        document.state = "reconciling"
    if incident == "auth_required" or (error and error.status_code in {401, 403}):
        operation.token_enc = None
        operation.token_expires_at = None
    session.add(
        WithdrawalObservation(
            document_id=document.id,
            status=info.status if info else None,
            http_status=200 if info else error.status_code if error else None,
            response_body=(
                json.dumps(info.raw, ensure_ascii=False).encode()
                if info
                else error.response_body
                if error
                else None
            ),
            errors=info.errors if info else None,
            common_errors=info.common_errors if info else None,
            incident=document.incident,
            reconciliation_ids=reconciliation_ids,
        )
    )
    document.next_poll_at = (
        None
        if document.state in {"failed", "succeeded"}
        else now + timedelta(seconds=poll_delay(document.poll_count + 1))
    )
    document.poll_count += 1
    document.lease_id = None
    document.lease_until = None
    await _project(session, operation, document)
    await session.commit()
    return True


async def record_create_result(
    session: AsyncSession,
    scope: WithdrawalScope,
    *,
    operation_id: uuid.UUID,
    document_id: uuid.UUID,
    gis_document_id: str | None = None,
    error: TrueApiError | None = None,
) -> None:
    """Persist one already-started submit result. Never sends or retries a POST.

    Future submit integration must persist state=submitting, request_started_at
    and next_poll_at before network I/O. That path remains gated by B1/B3.
    """
    if (gis_document_id is None) == (error is None):
        raise WithdrawalError("invalid_create_result")
    operation = await get_operation(session, scope, operation_id, lock=True)
    document = await session.scalar(
        select(WithdrawalDocument)
        .where(
            WithdrawalDocument.id == document_id,
            WithdrawalDocument.operation_id == operation.id,
            WithdrawalDocument.tenant_id == scope.tenant_id,
            WithdrawalDocument.seller_id == scope.seller_id,
        )
        .with_for_update()
    )
    if document is None:
        raise WithdrawalError("withdrawal_document_not_found", 404)
    if document.state != "submitting" or document.request_started_at is None:
        raise WithdrawalError("create_not_started")
    now = datetime.now(UTC)
    document.request_finished_at = now
    if gis_document_id:
        document.gis_document_id = str(uuid.UUID(gis_document_id))
        document.state = "submitted"
    elif error:
        document.http_status = error.status_code
        document.response_body = error.response_body
        document.state = (
            "failed" if error.create_outcome == CreateOutcome.DEFINITE_REJECT else "reconciling"
        )
        try:
            document.errors = json.loads(error.response_body)
        except (ValueError, UnicodeDecodeError):
            document.errors = {"message": error.response_body.decode("utf-8", errors="replace")}
        session.add(
            WithdrawalObservation(
                document_id=document.id,
                http_status=error.status_code,
                response_body=error.response_body,
                errors=document.errors,
            )
        )
    document.next_poll_at = None if document.state == "failed" else now + timedelta(seconds=2)
    await _project(session, operation, document)
    await session.commit()


async def recover_one(
    sessions: async_sessionmaker[AsyncSession],
    work: RecoveryWork,
    client: TrueApiWithdrawalClient,
) -> None:
    """Network work runs outside a database transaction; the final write is fenced."""
    info = None
    error = None
    incident = None
    reconciliation_ids: list[str] = []
    if (
        not work.auth_matches
        or work.token_enc is None
        or work.token_expires_at is None
        or aware(work.token_expires_at) <= datetime.now(UTC)
    ):
        incident = "auth_required"
    else:
        try:
            auth = AuthSession(
                work.environment,
                work.participant_inn,
                aware(work.token_expires_at),
                decrypt_secret(work.token_enc),
            )
            info, incident, reconciliation_ids = await reconcile(client, auth, work)
        except TrueApiError as exc:
            error = exc
        except Exception:
            # Unexpected parse/limiter/decryption failure must not expose a token
            # through exception logging, and can never authorize a new create.
            incident = "recovery_read_unavailable"
    async with sessions() as session:
        await apply_recovery(
            session,
            work,
            info=info,
            error=error,
            incident=incident,
            reconciliation_ids=reconciliation_ids,
        )


async def purge_expired_tokens(session: AsyncSession) -> None:
    await session.execute(
        update(WithdrawalOperation)
        .where(
            WithdrawalOperation.token_enc.is_not(None),
            or_(
                WithdrawalOperation.token_expires_at.is_(None),
                WithdrawalOperation.token_expires_at <= datetime.now(UTC),
            ),
        )
        .values(token_enc=None, token_expires_at=None)
    )
    await session.commit()
