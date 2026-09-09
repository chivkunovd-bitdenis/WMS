"""Immutable, tenant-scoped persistence for Wave 4 invoice snapshots."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.billing import (
    BillingInvoice,
    BillingInvoiceV2,
    BillingInvoiceV2Idempotency,
    BillingInvoiceV2Line,
    BillingInvoiceV2Source,
    BillingLedgerEntry,
    BillingProfile,
)
from app.models.fbs_order import FbsOrder
from app.models.marketplace_unload import MarketplaceUnloadRequest
from app.models.operation_fact import OperationFact
from app.models.seller import Seller
from app.services.billing_ledger_service import (
    BillingLedgerError,
    OperationalBillingLine,
    _active_charge_for_source,
    postgres_integer,
    record_operational_charge,
)
from app.services.billing_seller_report_service import moscow_interval
from app.services.document_number_service import DOC_TYPE_INVOICE, next_document_number
from app.services.fbs_order_billing_service import _positions, confirmed_order_handover_dates

DECIMAL_RE = re.compile(r"^-?\d+(\.\d{1,2})?$")

# Печатная форма показывает услугу человеку, а не код таблицы. Подпись
# снимается в момент выставления и дальше не пересчитывается.
SERVICE_LABELS = {
    "inbound": "Приёмка",
    "fbs_order": "FBS",
    "packing": "Упаковка",
    "marketplace_outbound": "Отгрузка",
    "storage_liter_day": "Хранение",
}

# Хранение приходит в счёт ровно одной агрегированной строкой за весь период,
# без разбивки по товарам, дням и тарифам.
STORAGE_LINE_DESCRIPTION = "Хранение товара за выбранный период"


class BillingInvoiceV2Error(ValueError):
    pass


def _invoice_integer(value: int) -> int:
    try:
        return postgres_integer(Decimal(value), field="billing_amount")
    except BillingLedgerError as exc:
        raise BillingInvoiceV2Error("invalid_decimal_amount") from exc


def decimal_to_kopecks(value: str) -> int:
    if not DECIMAL_RE.fullmatch(value):
        raise BillingInvoiceV2Error("invalid_decimal_amount")
    amount = Decimal(value)
    if amount < 0:
        raise BillingInvoiceV2Error("negative_amount")
    return _invoice_integer(int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


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
                "total_amount_kopecks": None
                if "Нет ставки; сумма не рассчитана" in row.description_snapshot
                else row.total_amount_kopecks,
                "sort_order": row.sort_order,
            }
            for row in sorted(invoice.lines_v2, key=lambda row: row.sort_order)
        ],
    }


def _manual_lines(
    raw_lines: list[dict[str, Any]] | Any, *, first_sort_order: int
) -> list[dict[str, Any]]:
    """Строки, введённые человеком: описание и сумма, без ссылки на начисление.

    Одна и та же сборка нужна и пустому счёту, и счёту по выбранным операциям:
    к отгруженным заказам добавляют короба, доставку, разовую работу. Строка без
    `sources` — это нормально: за ней не стоит начисления, и в базе она хранится
    так же, просто без источников.
    """
    lines: list[dict[str, Any]] = []
    for index, line in enumerate(raw_lines or []):
        description = str(line.get("description", "")).strip()
        if not description:
            raise BillingInvoiceV2Error("manual_description_required")
        unit_price = line.get("unit_price")
        lines.append(
            {
                "id": uuid.uuid4(),
                "description": description,
                "unit_price_kopecks": decimal_to_kopecks(str(unit_price))
                if unit_price not in (None, "")
                else None,
                "total_amount_kopecks": decimal_to_kopecks(str(line.get("amount", ""))),
                "sort_order": first_sort_order + index,
            }
        )
    return lines


async def preview_invoice_v2(
    session: AsyncSession, *, tenant_id: uuid.UUID, request: dict[str, Any]
) -> dict[str, Any]:
    if request.get("creation_mode") == "selected_operations":
        return await _preview_selected_operations(session, tenant_id=tenant_id, request=request)
    if request.get("creation_mode") != "manual":
        raise BillingInvoiceV2Error("invalid_creation_mode")
    seller_id = uuid.UUID(str(request["seller_id"]))
    ff_profile, seller_profile = await _profiles(session, tenant_id=tenant_id, seller_id=seller_id)
    lines = _manual_lines(request.get("lines", []), first_sort_order=0)
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
                    # Только ночные начисления. Старые зафиксированные ведомости
                    # лежат тем же кодом услуги, но другим источником
                    # (`storage_measurement`), и без этого фильтра счёт сложил бы
                    # обе строки за одни и те же сутки — заплатили бы дважды.
                    BillingLedgerEntry.source_type == "storage_day",
                    BillingLedgerEntry.entry_type == "charge",
                    BillingLedgerEntry.occurred_at >= start,
                    BillingLedgerEntry.occurred_at < end,
                )
            )
        ).all()
    )
    if not entries:
        return None
    # Сутки, уже попавшие в выставленный счёт, второй раз в счёт не идут.
    # Хранение — ежесуточное начисление, и повторно взять за него деньги нельзя
    # ни при каком сценарии. До 03.09.2026 эта дыра была недостижима только
    # потому, что галочка хранения вообще не доезжала до запроса.
    invoiced = set(
        (
            await session.scalars(
                select(BillingInvoiceV2Source.billing_ledger_entry_id).where(
                    BillingInvoiceV2Source.tenant_id == tenant_id,
                    BillingInvoiceV2Source.billing_ledger_entry_id.in_(
                        {entry.id for entry in entries}
                    ),
                )
            )
        ).all()
    )
    entries = [entry for entry in entries if entry.id not in invoiced]
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


async def _selected_shipment_charge(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    source: dict[str, Any],
    start: datetime,
    end: datetime,
    orders: dict[uuid.UUID, FbsOrder],
    handovers: dict[uuid.UUID, datetime],
) -> BillingLedgerEntry:
    source_type = source["source_type"]
    source_id = uuid.UUID(str(source["source_id"]))
    service_code = source["service_code"]
    if source_type == "fbs_order" and service_code in {"fbs_order", "packing"}:
        order = orders.get(source_id)
        if order is None or order.seller_id != seller_id:
            raise BillingInvoiceV2Error("selected_source_not_found")
        moment = handovers.get(order.id)
        if order.marketplace == "ozon":
            # WMS-406 tightens WB proof only. Ozon's report still uses its
            # historical confirmed operation, or the existing charge's date.
            fact_moment = await session.scalar(
                select(OperationFact.occurred_at).where(
                    OperationFact.tenant_id == tenant_id,
                    OperationFact.seller_id == seller_id,
                    OperationFact.marketplace == "ozon",
                    OperationFact.document_type == "fbs_order",
                    OperationFact.document_id == order.id,
                    OperationFact.operation_code == "fbs_order",
                )
            )
            existing = await _active_charge_for_source(
                session,
                tenant_id=tenant_id,
                source_type="fbs_order",
                source_id=order.id,
                service_code=service_code,
            )
            moment = fact_moment or (existing.occurred_at if existing is not None else moment)
        warehouse_id = order.warehouse_id
        positions = await _positions(session, order)
        lines = [
            OperationalBillingLine(
                product_id=pid,
                quantity=Decimal(qty),
                source_snapshot={"fbs_order_id": str(order.id)},
            )
            for pid, qty in positions
        ]
    elif source_type == "marketplace_unload" and service_code in {
        "marketplace_outbound",
        "packing",
    }:
        document = await session.scalar(
            select(MarketplaceUnloadRequest).where(
                MarketplaceUnloadRequest.tenant_id == tenant_id,
                MarketplaceUnloadRequest.seller_id == seller_id,
                MarketplaceUnloadRequest.id == source_id,
                MarketplaceUnloadRequest.status == "shipped",
            )
        )
        fact = await session.scalar(
            select(OperationFact)
            .options(selectinload(OperationFact.lines))
            .where(
                OperationFact.tenant_id == tenant_id,
                OperationFact.seller_id == seller_id,
                OperationFact.document_id == source_id,
                OperationFact.operation_code == "marketplace_outbound_completed",
            )
        )
        if document is None or fact is None:
            raise BillingInvoiceV2Error("selected_source_not_found")
        moment = document.shipped_at
        warehouse_id = document.warehouse_id
        lines = [
            OperationalBillingLine(
                product_id=line.product_id,
                quantity=Decimal(line.item_quantity),
                source_snapshot={},
                operation_fact_line_id=line.id,
            )
            for line in fact.lines
        ]
    else:
        raise BillingInvoiceV2Error("selected_source_not_found")
    if moment is None:
        raise BillingInvoiceV2Error("selected_source_not_found")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    if not start <= moment < end:
        raise BillingInvoiceV2Error("selected_source_outside_period")
    entry = await record_operational_charge(
        session,
        tenant_id=tenant_id,
        seller_id=seller_id,
        source_type=source_type,
        source_id=source_id,
        source="fbs" if source_type == "fbs_order" else "marketplace",
        service_code=service_code,
        quantity=sum((line.quantity for line in lines), Decimal(0)),
        occurred_at=moment,
        performer_id=None,
        warehouse_id=warehouse_id,
        lines=lines,
        respect_billing_start=False,
    )
    if entry is None:
        raise BillingInvoiceV2Error("selected_source_not_found")
    return entry


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
    period_start, period_end = moscow_interval(date_from, date_to)
    shipment_roots: set[uuid.UUID] = set()
    sources = list(request.get("selected_sources", []))
    # A stored charge must not bypass the same proof required for a document.
    sources.extend(
        {
            "source_type": root.source_type,
            "source_id": root.source_id,
            "service_code": root.service_code,
        }
        for root in roots
        if root.source_type in {"fbs_order", "marketplace_unload"}
    )
    sources = list(
        {
            (source["source_type"], str(source["source_id"]), source["service_code"]): source
            for source in sources
        }.values()
    )
    order_ids = {
        uuid.UUID(str(source["source_id"]))
        for source in sources
        if source["source_type"] == "fbs_order"
    }
    orders = (
        {
            order.id: order
            for order in await session.scalars(
                select(FbsOrder).where(
                    FbsOrder.tenant_id == tenant_id,
                    FbsOrder.seller_id == seller_id,
                    FbsOrder.id.in_(order_ids),
                )
            )
        }
        if order_ids
        else {}
    )
    handovers = (
        await confirmed_order_handover_dates(
            session,
            tenant_id=tenant_id,
            orders=list(orders.values()),
        )
        if orders
        else {}
    )
    for source in sources:
        entry = await _selected_shipment_charge(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            source=source,
            start=period_start,
            end=period_end,
            orders=orders,
            handovers=handovers,
        )
        shipment_roots.add(entry.id)
        if entry.id not in root_ids:
            roots.append(entry)
            root_ids.add(entry.id)
    selected: dict[uuid.UUID, BillingLedgerEntry] = {}
    for root in roots:
        if root.seller_id != seller_id:
            raise BillingInvoiceV2Error("selected_source_not_found")
        if root.entry_type == "reversal" or root.reversal_of_id is not None:
            raise BillingInvoiceV2Error("standalone_reversal")
        # Границы периода — московские, как и во всём отчёте (`moscow_interval`).
        # Сравнение по календарной дате UTC отвергало операцию, которая по Москве
        # попадает в выбранный день: 3 сентября 22:30 UTC — это 4 сентября 01:30
        # по Москве. Оператор видел её в отчёте, а счёт по ней не выставлялся.
        occurred_at = root.occurred_at
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=UTC)
        if root.id not in shipment_roots and not period_start <= occurred_at < period_end:
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
                if member.seller_id != seller_id:
                    raise BillingInvoiceV2Error("unpriced_or_cross_seller_chain")
                if member.id not in selected:
                    selected[member.id] = member
                    next_frontier.add(member.id)
            frontier = next_frontier - set(selected)
    # История отменённого счёта остаётся неизменной, но не занимает операции.
    # Проверяем всю выбранную цепочку; частичный счёт вместо запрошенного
    # молча не собираем.
    already_invoiced = await session.scalar(
        select(BillingInvoiceV2Source.id)
        .join(
            BillingInvoiceV2Line,
            BillingInvoiceV2Source.invoice_line_id == BillingInvoiceV2Line.id,
        )
        .join(BillingInvoiceV2, BillingInvoiceV2Line.invoice_id == BillingInvoiceV2.id)
        .where(
            BillingInvoiceV2Source.tenant_id == tenant_id,
            BillingInvoiceV2Line.tenant_id == tenant_id,
            BillingInvoiceV2.tenant_id == tenant_id,
            BillingInvoiceV2.status != "cancelled",
            BillingInvoiceV2Source.billing_ledger_entry_id.in_(selected),
        )
        .limit(1)
    )
    if already_invoiced is not None:
        raise BillingInvoiceV2Error("selected_source_already_invoiced")
    grouped: dict[tuple[str, bool], list[BillingLedgerEntry]] = {}
    for entry in selected.values():
        grouped.setdefault((entry.service_code, entry.amount is None), []).append(entry)
    lines: list[dict[str, Any]] = []
    for order, ((service_code, unpriced), entries) in enumerate(sorted(grouped.items())):
        lines.append(
            {
                "id": uuid.uuid4(),
                "description": SERVICE_LABELS.get(service_code, service_code)
                + (" — Нет ставки; сумма не рассчитана" if unpriced else ""),
                "unit_price_kopecks": None,
                "total_amount_kopecks": None
                if unpriced
                else sum(int(entry.amount or 0) for entry in entries),
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
    # Ручные строки идут последними: сначала то, за что уже начислено, потом
    # добавленное человеком.
    extra_lines = _manual_lines(request.get("manual_lines", []), first_sort_order=len(lines))
    if len(extra_lines) > 10:
        raise BillingInvoiceV2Error("manual_line_count")
    lines.extend(extra_lines)
    if not lines:
        raise BillingInvoiceV2Error("selected_operations_required")
    incomplete = any(line["total_amount_kopecks"] is None for line in lines)
    known_total = sum(line["total_amount_kopecks"] or 0 for line in lines)
    calculated_total = None if incomplete else known_total
    final_amount = request.get("final_amount")
    total = calculated_total
    if final_amount is not None:
        total = decimal_to_kopecks(str(final_amount))
        difference = _invoice_integer(total - known_total)
        if difference or incomplete:
            lines.append(
                {
                    "id": uuid.uuid4(),
                    "unit_price_kopecks": None,
                    "description": "Сумма задана вручную; исходный расчёт неполный"
                    if incomplete
                    else "Ручная корректировка итога",
                    "total_amount_kopecks": difference,
                    "sort_order": len(lines),
                }
            )
    if total is not None:
        _invoice_integer(total)
    return {
        "id": uuid.uuid4(),
        "seller_id": seller_id,
        "number": "Новый счёт",
        "creation_mode": "selected_operations",
        "period_start": date_from,
        "period_end": date_to,
        "status": "issued",
        "issued_at": None,
        "total_amount_kopecks": total,
        "calculated_amount_kopecks": calculated_total,
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
    if request.get("creation_mode") == "selected_operations" and (
        request.get("selected_root_ids") or request.get("selected_sources")
    ):
        # Оба запроса одного селлера проходят проверку последовательно, до
        # записи счёта и до проверки повторного ключа. В PostgreSQL блокировка
        # живёт до commit вызывающего API; следующий запрос увидит его счёт.
        # NO KEY UPDATE не мешает обычным вставкам со ссылкой на селлера.
        seller_id = uuid.UUID(str(request["seller_id"]))
        seller = await session.scalar(
            select(Seller.id)
            .where(Seller.tenant_id == tenant_id, Seller.id == seller_id)
            .with_for_update(key_share=True)
        )
        if seller is None:
            raise BillingInvoiceV2Error("seller_not_found")
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
    if preview["total_amount_kopecks"] is None:
        raise BillingInvoiceV2Error("unpriced_or_cross_seller_chain")
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
            total_amount_kopecks=line["total_amount_kopecks"] or 0,
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
        await session.execute(v2_query.order_by(BillingInvoiceV2.issued_at.desc()).limit(limit + 1))
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
