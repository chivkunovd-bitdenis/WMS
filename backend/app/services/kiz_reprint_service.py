"""Persistence and validation for the FF scanned-KIZ reprint history."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
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


def normalize_reprint_kiz(raw_kiz: str) -> str:
    """Validate a full KIZ while retaining its GS separators for print output."""
    try:
        scanner_value = normalize_scanned_code(raw_kiz)
    except InboundIntakeError as exc:
        raise KizReprintServiceError("not_a_kiz") from exc

    value, hints = normalize_scanned_cis(scanner_value)
    if "gs_unrestorable" in hints:
        raise KizReprintServiceError("gs_separator_lost")
    if not is_probably_cis(value):
        raise KizReprintServiceError("not_a_kiz")
    return value


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
