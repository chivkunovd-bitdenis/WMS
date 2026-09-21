"""Persistence and validation for the FF scanned-KIZ reprint history."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kiz_reprint import KizReprint
from app.services.fbs_kiz_service import is_probably_cis, normalize_scanned_cis
from app.services.inbound_intake_service import InboundIntakeError
from app.services.inbound_marking_service import normalize_scanned_code


class KizReprintServiceError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class KizReprintCreateResult:
    row: KizReprint
    replayed: bool


@dataclass(frozen=True)
class KizReprintPrintClaimResult:
    row: KizReprint
    claimed: bool


def normalize_reprint_kiz(raw_kiz: str) -> str:
    """Validate a full KIZ while retaining its GS separators for print output."""
    try:
        scanner_value = normalize_scanned_code(raw_kiz)
    except InboundIntakeError as exc:
        raise KizReprintServiceError("not_a_kiz") from exc

    value, hints = normalize_scanned_cis(scanner_value)
    if "gs_unrestorable" in hints:
        raise KizReprintServiceError("gs_separator_lost")
    if not is_complete_reprint_kiz(value):
        raise KizReprintServiceError("not_a_kiz")
    return value


def is_complete_reprint_kiz(value: str) -> bool:
    """Accept a whole short KIZ or a structurally complete crypto KIZ only.

    ``is_probably_cis`` intentionally stays lenient for existing FBS scanner
    flows.  A saved reprint, however, must never memorialize a truncated label.
    The long form follows the same end-anchored 21/91/92 parser used to restore
    lost GS separators in ``fbs_kiz_service``; ``91``/``92`` inside a serial do
    not therefore split the value accidentally.
    """
    if not is_probably_cis(value):
        return False
    prefix_length = 18  # 01 + 14-digit GTIN + 21
    tail = value[prefix_length:]
    gs = "\x1d"
    if gs not in tail:
        # The provider's short form has no crypto fields.  Two bytes after AI
        # 21 are a partial scanner packet, not a usable reprint label.
        return 4 <= len(tail) <= 20

    compact_tail = tail.replace(gs, "")
    for signature_length in (44, 88):
        suffix_length = 2 + 4 + 2 + signature_length  # 91 + key + 92 + sign
        if len(compact_tail) <= suffix_length:
            continue
        serial = compact_tail[: len(compact_tail) - suffix_length]
        block = compact_tail[len(compact_tail) - suffix_length :]
        if not (1 <= len(serial) <= 20):
            continue
        if block[:2] != "91" or block[6:8] != "92":
            continue
        expected = f"{serial}{gs}91{block[2:6]}{gs}92{block[8:]}"
        if tail == expected:
            return True
    return False


async def list_kiz_reprints(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> list[KizReprint]:
    rows = await session.scalars(
        select(KizReprint)
        .where(
            KizReprint.tenant_id == tenant_id,
            KizReprint.seller_id == seller_id,
        )
        .order_by(KizReprint.created_at.asc(), KizReprint.id.asc())
    )
    return list(rows)


async def save_kiz_reprint(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    raw_kiz: str,
    idempotency_key: str,
    actor_user_id: uuid.UUID,
) -> KizReprintCreateResult:
    key = idempotency_key.strip()
    if not key:
        raise KizReprintServiceError("idempotency_key_required")
    if len(key) > 128:
        raise KizReprintServiceError("idempotency_key_too_long")
    kiz = normalize_reprint_kiz(raw_kiz)

    existing = await session.scalar(
        select(KizReprint).where(
            KizReprint.tenant_id == tenant_id,
            KizReprint.seller_id == seller_id,
            KizReprint.idempotency_key == key,
        )
    )
    if existing is not None:
        if existing.kiz != kiz:
            raise KizReprintServiceError("idempotency_key_reused")
        return KizReprintCreateResult(row=existing, replayed=True)

    row = KizReprint(
        tenant_id=tenant_id,
        seller_id=seller_id,
        kiz=kiz,
        idempotency_key=key,
        created_by_user_id=actor_user_id,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        # The unique index is the concurrency boundary.  A concurrent retry
        # reaches this branch only after the original write became durable.
        await session.rollback()
        existing = await session.scalar(
            select(KizReprint).where(
                KizReprint.tenant_id == tenant_id,
                KizReprint.seller_id == seller_id,
                KizReprint.idempotency_key == key,
            )
        )
        if existing is None:
            raise
        if existing.kiz != kiz:
            raise KizReprintServiceError("idempotency_key_reused") from None
        return KizReprintCreateResult(row=existing, replayed=True)
    await session.refresh(row)
    return KizReprintCreateResult(row=row, replayed=False)


async def claim_kiz_reprint_print(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    reprint_id: uuid.UUID,
    *,
    attempt_key: str,
) -> KizReprintPrintClaimResult:
    key = attempt_key.strip()
    if not key:
        raise KizReprintServiceError("print_claim_key_required")
    if len(key) > 128:
        raise KizReprintServiceError("print_claim_key_too_long")

    # The conditional update, rather than a read-then-write, makes concurrent
    # duplicate deliveries compete for one automatic physical print.
    await session.execute(
        update(KizReprint)
        .where(
            KizReprint.id == reprint_id,
            KizReprint.tenant_id == tenant_id,
            KizReprint.print_started_at.is_(None),
            (KizReprint.print_claim_key.is_(None)) | (KizReprint.print_claim_key == key),
        )
        .values(print_claim_key=key)
    )
    await session.commit()
    row = await session.scalar(
        select(KizReprint).where(
            KizReprint.id == reprint_id,
            KizReprint.tenant_id == tenant_id,
        )
    )
    if row is None:
        raise KizReprintServiceError("reprint_not_found")
    return KizReprintPrintClaimResult(
        row=row,
        claimed=row.print_started_at is None and row.print_claim_key == key,
    )


async def mark_kiz_reprint_print_started(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    reprint_id: uuid.UUID,
) -> KizReprint:
    row = await session.scalar(
        select(KizReprint).where(
            KizReprint.id == reprint_id,
            KizReprint.tenant_id == tenant_id,
        )
    )
    if row is None:
        raise KizReprintServiceError("reprint_not_found")
    if row.print_started_at is None:
        row.print_started_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(row)
    return row


async def release_kiz_reprint_print_claim(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    reprint_id: uuid.UUID,
    *,
    attempt_key: str,
) -> KizReprint:
    key = attempt_key.strip()
    if not key:
        raise KizReprintServiceError("print_claim_key_required")
    await session.execute(
        update(KizReprint)
        .where(
            KizReprint.id == reprint_id,
            KizReprint.tenant_id == tenant_id,
            KizReprint.print_started_at.is_(None),
            KizReprint.print_claim_key == key,
        )
        .values(print_claim_key=None)
    )
    await session.commit()
    row = await session.scalar(
        select(KizReprint).where(
            KizReprint.id == reprint_id,
            KizReprint.tenant_id == tenant_id,
        )
    )
    if row is None:
        raise KizReprintServiceError("reprint_not_found")
    return row
