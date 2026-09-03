"""Immutable, tenant-scoped persistence for Wave 4 invoice snapshots."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import (
    BillingInvoice,
    BillingInvoiceV2,
    BillingInvoiceV2Idempotency,
    BillingInvoiceV2Line,
    BillingInvoiceV2Source,
    BillingLedgerEntry,
    BillingProfile,
)
from app.models.seller import Seller
from app.services.billing_seller_report_service import moscow_interval
from app.services.document_number_service import DOC_TYPE_INVOICE, next_document_number

DECIMAL_RE = re.compile(r"^-?\d+(\.\d{1,2})?$")

# Печатная форма показывает услугу человеку, а не код таблицы. Подпись
# снимается в момент выставления и дальше не пересчитывается.
SERVICE_LABELS = {
    "inbound": "Приёмка",
    "marketplace_outbound": "Отгрузка",
    "storage_liter_day": "Хранение",
}

# Хранение приходит в счёт ровно одной агрегированной строкой за весь период,
# без разбивки по товарам, дням и тарифам.
STORAGE_LINE_DESCRIPTION = "Хранение товара за выбранный период"


class BillingInvoiceV2Error(ValueError):
    pass


def decimal_to_kopecks(value: str) -> int:
    if not DECIMAL_RE.fullmatch(value):
        raise BillingInvoiceV2Error("invalid_decimal_amount")
    amount = Decimal(value)
    if amount < 0:
        raise BillingInvoiceV2Error("negative_amount")
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _canonical(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


async def _profiles(
    session: AsyncSession, *, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> tuple[dict[str, str | None], dict[str, str | None]]:
    seller = await session.scalar(
        select(Seller).where(Seller.id == seller_id, Seller.tenant_id == tenant_id)
    )
    if seller is None:
        raise BillingInvoiceV2Error("seller_not_found")
    rows = list(
        (
            await session.scalars(
                select(BillingProfile).where(
                    BillingProfile.tenant_id == tenant_id,
                    BillingProfile.seller_id.in_([None, seller_id]),
                )
            )
        ).all()
    )
    by_seller = {row.seller_id: row for row in rows}
    fields = (
        "legal_name",
        "inn",
        "kpp",
        "bank_name",
        "bik",
        "settlement_account",
        "correspondent_account",
    )

    def snapshot(profile: BillingProfile | None) -> dict[str, str | None]:
        return {field: getattr(profile, field) if profile is not None else None for field in fields}

    return snapshot(by_seller.get(None)), snapshot(by_seller.get(seller_id))


def invoice_v2_out(invoice: BillingInvoiceV2) -> dict[str, Any]:
    return {
        "id": invoice.id,
        "seller_id": invoice.seller_id,
        "number": invoice.number,
        "creation_mode": invoice.creation_mode,
        "period_start": invoice.period_start,
        "period_end": invoice.period_end,
        "status": invoice.status,
        "issued_at": invoice.issued_at,
        "total_amount_kopecks": invoice.total_amount_kopecks,
        "ff_profile": invoice.ff_profile_snapshot,
        "seller_profile": invoice.seller_profile_snapshot,
        "lines": [
            {
                "id": row.id,
                "description": row.description_snapshot,
                "unit_price_kopecks": row.unit_price_kopecks,
                "total_amount_kopecks": row.total_amount_kopecks,
                "sort_order": row.sort_order,
            }
            for row in sorted(invoice.lines_v2, key=lambda row: row.sort_order)
        ],
    }


async def preview_invoice_v2(
    session: AsyncSession, *, tenant_id: uuid.UUID, request: dict[str, Any]
) -> dict[str, Any]:
    if request.get("creation_mode") == "selected_operations":
        return await _preview_selected_operations(session, tenant_id=tenant_id, request=request)
    if request.get("creation_mode") != "manual":
        raise BillingInvoiceV2Error("invalid_creation_mode")
    seller_id = uuid.UUID(str(request["seller_id"]))
    ff_profile, seller_profile = await _profiles(session, tenant_id=tenant_id, seller_id=seller_id)
    lines: list[dict[str, Any]] = []
    for index, line in enumerate(request.get("lines", [])):
        description = str(line.get("description", "")).strip()
        if not description:
            raise BillingInvoiceV2Error("manual_description_required")
        amount = decimal_to_kopecks(str(line.get("amount", "")))
        unit_price = line.get("unit_price")
        lines.append(
            {
                "id": uuid.uuid4(),
                "description": description,
                "unit_price_kopecks": decimal_to_kopecks(str(unit_price))
                if unit_price not in (None, "")
                else None,
                "total_amount_kopecks": amount,
                "sort_order": index,
            }
        )
    if not 1 <= len(lines) <= 10:
        raise BillingInvoiceV2Error("manual_line_count")
    return {
        "id": uuid.uuid4(),
        "seller_id": seller_id,
        "number": "Новый счёт",
        "creation_mode": "manual",
        "period_start": None,
        "period_end": None,
        "status": "issued",
        "issued_at": None,
        "total_amount_kopecks": sum(line["total_amount_kopecks"] for line in lines),
        "ff_profile": ff_profile,
        "seller_profile": seller_profile,
        "lines": lines,
    }


async def _storage_line(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    date_from: date,
    date_to: date,
    include_storage: bool,
    sort_order: int,
) -> dict[str, Any] | None:
    """Собрать строку хранения из ночных начислений.

    Раньше счёт пересчитывал хранение сам и сверял результат с подписанным
    токеном из отчёта. Это был второй источник цифры: ночная задача писала
    начисления, а счёт их не читал. Две правды об одних и тех же сутках рано
    или поздно разошлись бы, и разобраться, какая настоящая, было бы нельзя.
    Теперь источник один — то, что записала ночь.
    """
    if not include_storage:
        return None
    start, end = moscow_interval(date_from, date_to)
    entries = list(
        (
            await session.scalars(
                select(BillingLedgerEntry).where(
                    BillingLedgerEntry.tenant_id == tenant_id,
                    BillingLedgerEntry.seller_id == seller_id,
                    BillingLedgerEntry.service_code == "storage",
                    BillingLedgerEntry.entry_type == "charge",
                    BillingLedgerEntry.occurred_at >= start,
                    BillingLedgerEntry.occurred_at < end,
                )
            )
        ).all()
    )
    if not entries:
        return None
    # Сутки без заданной ставки идут в счёт нулём, а не отказом: отчёт и счёт
    # показывают одно и то же, а разбираться с незаведённым тарифом — работа
    # человека, а не повод не дать выставить счёт.
    return {
        "id": uuid.uuid4(),
        "description": STORAGE_LINE_DESCRIPTION,
        "unit_price_kopecks": None,
        "total_amount_kopecks": sum(int(entry.amount or 0) for entry in entries),
        "sort_order": sort_order,
        "sources": [
            {
                "billing_ledger_entry_id": entry.id,
                "signed_amount_kopecks_snapshot": int(entry.amount or 0),
            }
            for entry in entries
        ],
    }


async def _preview_selected_operations(
    session: AsyncSession, *, tenant_id: uuid.UUID, request: dict[str, Any]
) -> dict[str, Any]:
    seller_id = uuid.UUID(str(request["seller_id"]))
    date_from = date.fromisoformat(str(request["date_from"]))
    date_to = date.fromisoformat(str(request["date_to"]))
    if date_to < date_from:
        raise BillingInvoiceV2Error("invalid_date_range")
    ff_profile, seller_profile = await _profiles(session, tenant_id=tenant_id, seller_id=seller_id)
    root_ids = {uuid.UUID(str(value)) for value in request.get("selected_root_ids", [])}
    roots = list(
        (
            await session.scalars(
                select(BillingLedgerEntry).where(
                    BillingLedgerEntry.tenant_id == tenant_id, BillingLedgerEntry.id.in_(root_ids)
                )
            )
        ).all()
    )
    if len(roots) != len(root_ids):
        raise BillingInvoiceV2Error("selected_source_not_found")
    selected: dict[uuid.UUID, BillingLedgerEntry] = {}
    for root in roots:
        if root.seller_id != seller_id:
            raise BillingInvoiceV2Error("selected_source_not_found")
        if root.entry_type == "reversal" or root.reversal_of_id is not None:
            raise BillingInvoiceV2Error("standalone_reversal")
        if not date_from <= root.occurred_at.date() <= date_to:
            raise BillingInvoiceV2Error("selected_source_outside_period")
        frontier = {root.id}
        while frontier:
            members = list(
                (
                    await session.scalars(
                        select(BillingLedgerEntry).where(
                            BillingLedgerEntry.tenant_id == tenant_id,
                            (BillingLedgerEntry.id.in_(frontier))
                            | (BillingLedgerEntry.reversal_of_id.in_(frontier)),
                        )
                    )
                ).all()
            )
            next_frontier: set[uuid.UUID] = set()
            for member in members:
                if member.seller_id != seller_id or member.amount is None:
                    raise BillingInvoiceV2Error("unpriced_or_cross_seller_chain")
                if member.id not in selected:
                    selected[member.id] = member
                    next_frontier.add(member.id)
            frontier = next_frontier - set(selected)
    grouped: dict[str, list[BillingLedgerEntry]] = {}
    for entry in selected.values():
        grouped.setdefault(entry.service_code, []).append(entry)
    lines: list[dict[str, Any]] = []
    for order, (service_code, entries) in enumerate(sorted(grouped.items())):
        lines.append(
            {
                "id": uuid.uuid4(),
                "description": SERVICE_LABELS.get(service_code, service_code),
                "unit_price_kopecks": None,
                "total_amount_kopecks": sum(int(entry.amount or 0) for entry in entries),
                "sort_order": order,
                "sources": [
                    {
                        "billing_ledger_entry_id": entry.id,
                        "signed_amount_kopecks_snapshot": int(entry.amount or 0),
                    }
                    for entry in entries
                ],
            }
        )
    storage_line = await _storage_line(
        session,
        tenant_id=tenant_id,
        seller_id=seller_id,
        date_from=date_from,
        date_to=date_to,
        include_storage=bool(request.get("include_storage")),
        sort_order=len(lines),
    )
    if storage_line is not None:
        lines.append(storage_line)
    if not lines:
        raise BillingInvoiceV2Error("selected_operations_required")
    return {
        "id": uuid.uuid4(),
        "seller_id": seller_id,
        "number": "Новый счёт",
        "creation_mode": "selected_operations",
        "period_start": date_from,
        "period_end": date_to,
        "status": "issued",
        "issued_at": None,
        "total_amount_kopecks": sum(line["total_amount_kopecks"] for line in lines),
        "ff_profile": ff_profile,
        "seller_profile": seller_profile,
        "lines": lines,
    }


async def create_invoice_v2(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    request: dict[str, Any],
    idempotency_key: str,
) -> BillingInvoiceV2:
    if not idempotency_key.strip():
        raise BillingInvoiceV2Error("idempotency_key_required")
    canonical = _canonical(request)
    request_hash = hashlib.sha256(canonical.encode()).hexdigest()
    existing = await session.scalar(
        select(BillingInvoiceV2Idempotency).where(
            BillingInvoiceV2Idempotency.tenant_id == tenant_id,
            BillingInvoiceV2Idempotency.user_id == user_id,
            BillingInvoiceV2Idempotency.request_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise BillingInvoiceV2Error("idempotency_key_payload_mismatch")
        invoice = await session.scalar(
            select(BillingInvoiceV2).where(
                BillingInvoiceV2.tenant_id == tenant_id, BillingInvoiceV2.id == existing.invoice_id
            )
        )
        if invoice is None:
            raise BillingInvoiceV2Error("idempotency_invoice_missing")
        await session.refresh(invoice, attribute_names=["lines_v2"])
        return invoice
    preview = await preview_invoice_v2(session, tenant_id=tenant_id, request=request)
    invoice = BillingInvoiceV2(
        tenant_id=tenant_id,
        seller_id=preview["seller_id"],
        number=await next_document_number(session, tenant_id, DOC_TYPE_INVOICE),
        creation_mode=preview["creation_mode"],
        period_start=preview["period_start"],
        period_end=preview["period_end"],
        issued_by_user_id=user_id,
        ff_profile_snapshot=preview["ff_profile"],
        seller_profile_snapshot=preview["seller_profile"],
        total_amount_kopecks=preview["total_amount_kopecks"],
    )
    session.add(invoice)
    await session.flush()
    for line in preview["lines"]:
        persisted_line = BillingInvoiceV2Line(
            tenant_id=tenant_id,
            invoice_id=invoice.id,
            description_snapshot=line["description"],
            unit_price_kopecks=line["unit_price_kopecks"],
            total_amount_kopecks=line["total_amount_kopecks"],
            sort_order=line["sort_order"],
        )
        session.add(persisted_line)
        await session.flush()
        for source in line.get("sources", []):
            session.add(
                BillingInvoiceV2Source(
                    tenant_id=tenant_id,
                    invoice_line_id=persisted_line.id,
                    operation_fact_id=None,
                    billing_ledger_entry_id=source.get("billing_ledger_entry_id"),
                    storage_calculation_token=source.get("storage_calculation_token"),
                    signed_amount_kopecks_snapshot=source["signed_amount_kopecks_snapshot"],
                )
            )
    session.add(
        BillingInvoiceV2Idempotency(
            tenant_id=tenant_id,
            user_id=user_id,
            request_key=idempotency_key,
            request_hash=request_hash,
            invoice_id=invoice.id,
        )
    )
    try:
        await session.flush()
    except IntegrityError as exc:
        raise BillingInvoiceV2Error("idempotency_conflict") from exc
    await session.refresh(invoice, attribute_names=["lines_v2"])
    return invoice


async def get_invoice_v2(
    session: AsyncSession, *, tenant_id: uuid.UUID, invoice_id: uuid.UUID
) -> BillingInvoiceV2:
    invoice = await session.scalar(
        select(BillingInvoiceV2).where(
            BillingInvoiceV2.tenant_id == tenant_id, BillingInvoiceV2.id == invoice_id
        )
    )
    if invoice is None:
        raise BillingInvoiceV2Error("invoice_not_found")
    await session.refresh(invoice, attribute_names=["lines_v2"])
    return invoice


async def cancel_invoice_v2(
    session: AsyncSession, *, tenant_id: uuid.UUID, invoice_id: uuid.UUID
) -> BillingInvoiceV2:
    invoice = await get_invoice_v2(session, tenant_id=tenant_id, invoice_id=invoice_id)
    if invoice.status == "issued":
        invoice.status = "cancelled"
    return invoice


def _list_cursor(issued_at: datetime, origin: str, invoice_id: uuid.UUID) -> str:
    """Позиция в объединённой истории.

    Курсор не подписывается намеренно: в отличие от токена хранения он не
    заявляет сумму и не влияет на фильтры. Арендатор берётся из токена
    доступа, фильтры приходят явными параметрами, поэтому подделать здесь
    нечего — курсор указывает только место в уже разрешённой выборке.
    """
    payload = {"issued_at": issued_at.isoformat(), "origin": origin, "id": str(invoice_id)}
    return base64.urlsafe_b64encode(_canonical(payload).encode()).decode().rstrip("=")


def _parse_list_cursor(cursor: str) -> tuple[datetime, str, uuid.UUID]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        return (
            datetime.fromisoformat(payload["issued_at"]),
            str(payload["origin"]),
            uuid.UUID(str(payload["id"])),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise BillingInvoiceV2Error("invalid_cursor") from None


def _sort_key(row: dict[str, Any]) -> tuple[datetime, str, str]:
    # Убывание по дате выставления; origin и id только разводят совпадения,
    # чтобы страница не «дрожала» между запросами.
    return (row["issued_at"], row["origin"], str(row["id"]))


async def list_invoices_v2(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID | None = None,
    status: str | None = None,
    number: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Единая история выставленных счетов: старые месячные и новые вместе.

    Разрыв истории на «до» и «после» смены механизма — это потерянные для
    оператора документы, поэтому обе таблицы читаются в один список.
    Обе таблицы уже в копейках: legacy держит их в `Numeric(14, 2)`, новый
    счёт — целым числом.
    """
    limit = max(1, min(limit, 200))
    after = _parse_list_cursor(cursor) if cursor else None

    legacy_query = (
        select(BillingInvoice, Seller.name)
        .join(Seller, BillingInvoice.seller_id == Seller.id)
        .where(BillingInvoice.tenant_id == tenant_id)
    )
    v2_query = (
        select(BillingInvoiceV2, Seller.name)
        .join(Seller, BillingInvoiceV2.seller_id == Seller.id)
        .where(BillingInvoiceV2.tenant_id == tenant_id)
    )
    if seller_id is not None:
        legacy_query = legacy_query.where(BillingInvoice.seller_id == seller_id)
        v2_query = v2_query.where(BillingInvoiceV2.seller_id == seller_id)
    if status not in (None, "", "all"):
        legacy_query = legacy_query.where(BillingInvoice.status == status)
        v2_query = v2_query.where(BillingInvoiceV2.status == status)
    if number:
        legacy_query = legacy_query.where(BillingInvoice.number.ilike(f"%{number}%"))
        v2_query = v2_query.where(BillingInvoiceV2.number.ilike(f"%{number}%"))

    rows: list[dict[str, Any]] = []
    for invoice, seller_name in (
        await session.execute(
            legacy_query.order_by(BillingInvoice.issued_at.desc()).limit(limit + 1)
        )
    ).all():
        month_start = invoice.period.replace(day=1)
        next_month = date(
            month_start.year + (month_start.month == 12),
            1 if month_start.month == 12 else month_start.month + 1,
            1,
        )
        rows.append(
            {
                "id": invoice.id,
                "origin": "legacy",
                "number": invoice.number,
                "seller_id": invoice.seller_id,
                "seller_name": seller_name,
                "issued_at": invoice.issued_at,
                "period_start": month_start,
                "period_end": next_month - timedelta(days=1),
                "creation_mode": "monthly",
                "status": invoice.status,
                # Legacy держит копейки в колонке Numeric(14, 2): всё денежное
                # ядро биллинга считает в целых копейках. Умножать на 100 здесь
                # значит завысить каждую строку истории в сто раз.
                "total_amount_kopecks": int(
                    Decimal(invoice.total_amount).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                ),
            }
        )
    for invoice, seller_name in (
        await session.execute(
            v2_query.order_by(BillingInvoiceV2.issued_at.desc()).limit(limit + 1)
        )
    ).all():
        rows.append(
            {
                "id": invoice.id,
                "origin": "v2",
                "number": invoice.number,
                "seller_id": invoice.seller_id,
                "seller_name": seller_name,
                "issued_at": invoice.issued_at,
                "period_start": invoice.period_start,
                "period_end": invoice.period_end,
                "creation_mode": invoice.creation_mode,
                "status": invoice.status,
                "total_amount_kopecks": invoice.total_amount_kopecks,
            }
        )

    rows.sort(key=_sort_key, reverse=True)
    if after is not None:
        rows = [row for row in rows if _sort_key(row) < (after[0], after[1], str(after[2]))]
    page, tail = rows[:limit], rows[limit:]
    next_cursor = (
        _list_cursor(page[-1]["issued_at"], page[-1]["origin"], page[-1]["id"]) if tail else None
    )
    return {"invoices": page, "next_cursor": next_cursor}
