from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_sequence import DocumentDisplaySequence, DocumentSequence

MSK = ZoneInfo("Europe/Moscow")

DOC_TYPE_INBOUND = "inbound"
DOC_TYPE_UNLOAD = "unload"
DOC_TYPE_PACKAGING = "packaging"
DOC_TYPE_MARKING_IMPORT = "marking_import"
DOC_TYPE_REMARK = "remark"

PREFIX_BY_DOC_TYPE: dict[str, str] = {
    DOC_TYPE_INBOUND: "ПРИЕМ",
    DOC_TYPE_UNLOAD: "ОТГР",
    DOC_TYPE_PACKAGING: "УПАК",
    DOC_TYPE_MARKING_IMPORT: "ЗАГРКМ",
    DOC_TYPE_REMARK: "ПЕРЕМАРК",
}

DISPLAY_NUMBER_PREFIX = "№"


def document_date_msk(as_of: datetime | None = None) -> date:
    when = as_of or datetime.now(MSK)
    when = when.replace(tzinfo=MSK) if when.tzinfo is None else when.astimezone(MSK)
    return when.date()


def format_document_number(doc_type: str, seq_date: date, counter: int) -> str:
    prefix = PREFIX_BY_DOC_TYPE.get(doc_type)
    if prefix is None:
        raise ValueError(f"unknown_doc_type:{doc_type}")
    yy = seq_date.year % 100
    return f"{prefix}-{yy:02d}-{seq_date.month:02d}-{seq_date.day:02d}-{counter}"


def format_display_number(counter: int) -> str:
    if counter < 1:
        raise ValueError("counter_must_be_positive")
    return f"{DISPLAY_NUMBER_PREFIX}{counter:06d}"


async def next_document_number(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    doc_type: str,
    *,
    as_of: datetime | None = None,
) -> str:
    if doc_type not in PREFIX_BY_DOC_TYPE:
        raise ValueError(f"unknown_doc_type:{doc_type}")
    seq_date = document_date_msk(as_of)

    conn = await session.connection()
    insert_cls = sqlite_insert if conn.dialect.name == "sqlite" else pg_insert
    stmt = (
        insert_cls(DocumentSequence)
        .values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            doc_type=doc_type,
            document_date=seq_date,
            counter=1,
        )
        .on_conflict_do_update(
            index_elements=["tenant_id", "doc_type", "date"],
            set_={"counter": DocumentSequence.counter + 1},
        )
        .returning(DocumentSequence.counter)
    )
    result = await session.execute(stmt)
    counter = int(result.scalar_one())
    return format_document_number(doc_type, seq_date, counter)


async def next_display_number(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    doc_type: str,
) -> str:
    if doc_type not in PREFIX_BY_DOC_TYPE:
        raise ValueError(f"unknown_doc_type:{doc_type}")

    conn = await session.connection()
    insert_cls = sqlite_insert if conn.dialect.name == "sqlite" else pg_insert
    stmt = (
        insert_cls(DocumentDisplaySequence)
        .values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            doc_type=doc_type,
            counter=1,
        )
        .on_conflict_do_update(
            index_elements=["tenant_id", "doc_type"],
            set_={"counter": DocumentDisplaySequence.counter + 1},
        )
        .returning(DocumentDisplaySequence.counter)
    )
    result = await session.execute(stmt)
    counter = int(result.scalar_one())
    return format_display_number(counter)


class HasDocumentNumber(Protocol):
    document_number: str | None


class HasDisplayDocumentNumber(Protocol):
    display_number: str | None


async def assign_document_number_if_missing(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    doc_type: str,
    entity: HasDocumentNumber,
    *,
    as_of: datetime | None = None,
) -> str | None:
    if entity.document_number:
        return entity.document_number
    number = await next_document_number(session, tenant_id, doc_type, as_of=as_of)
    entity.document_number = number
    return number


async def assign_display_number_if_missing(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    doc_type: str,
    entity: HasDisplayDocumentNumber,
) -> str | None:
    if entity.display_number:
        return entity.display_number
    number = await next_display_number(session, tenant_id, doc_type)
    entity.display_number = number
    return number


async def peek_next_counter(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    doc_type: str,
    *,
    as_of: datetime | None = None,
) -> int:
    """Test helper: current counter for tenant/type/date (0 if none)."""
    seq_date = document_date_msk(as_of)
    row = (
        await session.execute(
            select(DocumentSequence.counter).where(
                DocumentSequence.tenant_id == tenant_id,
                DocumentSequence.doc_type == doc_type,
                DocumentSequence.document_date == seq_date,
            )
        )
    ).scalar_one_or_none()
    return int(row or 0)


async def peek_next_display_counter(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    doc_type: str,
) -> int:
    row = (
        await session.execute(
            select(DocumentDisplaySequence.counter).where(
                DocumentDisplaySequence.tenant_id == tenant_id,
                DocumentDisplaySequence.doc_type == doc_type,
            )
        )
    ).scalar_one_or_none()
    return int(row or 0)
