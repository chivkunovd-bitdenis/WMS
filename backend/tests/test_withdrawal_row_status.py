"""WMS-517 per-KIZ status projection (не выведен / передаётся / ожидает ЧЗ / выведен / ошибка).

The status is derived from existing durable state — no new column, no new entity.
These tests pin the mapping used by both the registry SQL projection and the
operation output shape.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from test_withdrawal_ledger import document, seed  # type: ignore[import-not-found]

from app.db.withdrawal_repository import (
    current_items,
    project_item_status,
    registry,
)
from app.models.marking_withdrawal import WithdrawalDocument
from app.services.integration_fernet import encrypt_secret
from app.services.withdrawal_service import create_operation


@pytest.mark.parametrize(
    "item_state,doc_state,doc_signed,expected",
    [
        (None, None, False, "not_withdrawn"),
        ("pending", None, False, "not_withdrawn"),
        ("pending", "pending_signature", False, "not_withdrawn"),
        ("pending", "pending_signature", True, "transferring"),
        ("pending", "submitting", True, "transferring"),
        ("pending", "submitted", True, "awaiting_crpt"),
        ("pending", "reconciling", True, "awaiting_crpt"),
        # Recovery may briefly leave the item pending after the document has
        # settled; the row must not be advertised as terminal until the item
        # itself flips, and it must never be selectable for a fresh submit.
        ("pending", "succeeded", True, "transferring"),
        ("pending", "failed", True, "transferring"),
        ("succeeded", "succeeded", True, "withdrawn"),
        ("failed", "failed", True, "error"),
    ],
)
def test_project_item_status_covers_the_full_state_machine(
    item_state: str | None, doc_state: str | None, doc_signed: bool, expected: str
) -> None:
    assert project_item_status(item_state, doc_state, doc_signed) == expected


async def test_registry_projects_signed_pending_as_transferring(
    db_session: AsyncSession,
) -> None:
    # A signed document sitting in the durable queue before the Celery worker
    # picks it up is the exact reload / post-signature case the frontend bug
    # was masking. The registry must report it as "передаётся".
    scope, marking, _, _ = await seed(db_session)
    operation = await create_operation(
        db_session, scope, row_ids=[marking.id], client_request_id=uuid.uuid4()
    )
    await db_session.commit()
    item = (await current_items(db_session, scope, operation.id))[0]
    payload = json.dumps({"cis": item.cis}).encode()
    doc = WithdrawalDocument(
        operation_id=operation.id,
        tenant_id=scope.tenant_id,
        seller_id=scope.seller_id,
        attempt=operation.attempt,
        environment="sandbox",
        pg="lp",
        participant_inn="7701234567",
        exact_payload=payload,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        certificate_thumbprint="thumb",
        state="pending_signature",
        signature="c2ln",
    )
    db_session.add(doc)
    await db_session.flush()
    item.document_id = doc.id
    await db_session.commit()

    rows, total = await registry(db_session, scope)
    assert total == 1
    assert rows[0]["status"] == "transferring"
    assert rows[0]["resume_required"] is False


async def test_registry_marks_in_flight_row_as_resumable_only_when_token_expired(
    db_session: AsyncSession,
) -> None:
    # BR7/BR14: token expiry mid-submit is the one path where an in-flight row
    # must remain reachable — for GET-only reconciliation, never a new POST.
    scope, operation, _ = await document(db_session, state="submitted")
    # Fresh token — the in-flight row is not resumable yet.
    rows, _ = await registry(db_session, scope)
    assert rows[0]["status"] == "awaiting_crpt"
    assert rows[0]["resume_required"] is False

    # Simulate token expiry as the durable worker would observe it.
    op = await db_session.get(type(operation), operation.id)
    assert op is not None
    op.token_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    op.token_enc = encrypt_secret("expired")
    await db_session.commit()
    rows, _ = await registry(db_session, scope)
    assert rows[0]["status"] == "awaiting_crpt"
    assert rows[0]["resume_required"] is True


async def test_registry_sql_does_not_select_exact_payload_or_signature_value(
    db_session: AsyncSession,
) -> None:
    # Direct evidence, not an ORM poisoning trick: capture every SQL statement
    # the registry issues and assert the SELECT list never pulls the document's
    # exact_payload column, and only ever references `signature` inside an
    # `IS NOT NULL` predicate (the boolean projection the client actually needs).
    scope, _, _ = await document(db_session, state="submitted")
    captured: list[str] = []
    bind = db_session.bind
    assert bind is not None
    engine = bind.sync_engine

    def _capture(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        captured.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        await registry(db_session, scope)
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    hits = [sql for sql in captured if "withdrawal_documents" in sql]
    assert hits, "registry must join withdrawal_documents at least once"
    for sql in hits:
        assert "withdrawal_documents.exact_payload" not in sql, (
            "registry hydrated exact_payload — up to 30 MB per row"
        )
        # `signature` may appear only as a boolean predicate. `IS NOT NULL` is the
        # only shape the projection uses; a bare `withdrawal_documents.signature`
        # in the SELECT list would fail this regex.
        for match in re.finditer(r"withdrawal_documents\.signature\b", sql):
            tail = sql[match.end() : match.end() + 24].lstrip().upper()
            assert tail.startswith("IS NOT NULL"), (
                f"withdrawal_documents.signature must be a boolean predicate, saw: {sql}"
            )
