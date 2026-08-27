# ruff: noqa: E501
"""Read-only typed projection for the Wave 3 seller billing report."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.models.billing import (
    BillingInvoice,
    BillingInvoiceV2Line,
    BillingInvoiceV2Source,
    BillingLedgerEntry,
    BillingLedgerLine,
    BillingTariffVersionV2,
)
from app.models.inventory_movement import InventoryMovement
from app.models.operation_fact import OperationFact, OperationFactCutover, OperationFactLine
from app.models.product import Product
from app.models.product_dimension_event import ProductDimensionEvent
from app.models.seller import Seller
from app.models.warehouse import Warehouse
from app.services.storage_measurement_service import MOSCOW, interval_liter_days


class SellerReportError(ValueError):
    pass


def moscow_interval(date_from: date, date_to: date, *, today: date | None = None) -> tuple[datetime, datetime]:
    today = today or datetime.now(MOSCOW).date()
    if date_to < date_from:
        raise SellerReportError("invalid_date_range")
    if (date_to - date_from).days > 365:
        raise SellerReportError("date_range_too_long")
    if date_to > today:
        raise SellerReportError("future_date_range")
    return (
        datetime.combine(date_from, time.min, MOSCOW),
        datetime.combine(date_to + timedelta(days=1), time.min, MOSCOW),
    )


def _as_moscow(value: datetime) -> datetime:
    return value.replace(tzinfo=MOSCOW) if value.tzinfo is None else value.astimezone(MOSCOW)


def _source_target(source_type: str, source_id: uuid.UUID) -> dict[str, str] | None:
    if source_type == "inbound_intake":
        return {"kind": "inbound", "source_id": str(source_id)}
    if source_type == "marketplace_unload":
        return {"kind": "route", "to": f"/app/ff/mp-shipments?open_mp={source_id}"}
    return None


def _token(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    fingerprint = hashlib.sha256(canonical).hexdigest()
    signed = {"version": 1, "fingerprint": fingerprint, "payload": payload}
    message = json.dumps(signed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    key = hmac.new(settings.jwt_secret_key.encode(), b"wms:seller-storage:v1", hashlib.sha256).digest()
    signature = hmac.new(key, message, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(json.dumps({**signed, "signature": signature}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).decode().rstrip("=")


async def verify_storage_calculation_token(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    date_from: date,
    date_to: date,
    token: str,
) -> int:
    """Recompute the signed Wave 3 interval; a token is never a trusted price."""
    try:
        decoded = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
        payload = decoded["payload"]
        if not isinstance(payload, dict) or _token(payload) != token:
            raise ValueError
        if payload.get("tenant_id") != str(tenant_id) or payload.get("seller_id") != str(seller_id):
            raise ValueError
        if payload.get("date_from") != date_from.isoformat() or payload.get("date_to") != date_to.isoformat():
            raise ValueError
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise SellerReportError("storage_calculation_stale") from None
    start, end = moscow_interval(date_from, date_to)
    current = await _storage_row(session, tenant_id=tenant_id, seller_id=seller_id, date_from=date_from, date_to=date_to, start=start, end=end, include_finance=True)
    # Причины разделены намеренно: «нет габаритов» чинит каталог, «расчёт
    # устарел» чинит перезагрузка отчёта. Общий текст заставлял бы гадать.
    if current["status"] == "missing_dimensions":
        raise SellerReportError("storage_missing_dimensions")
    if current["status"] != "calculated" or current["calculation_token"] != token:
        raise SellerReportError("storage_calculation_stale")
    return int(current["amount_kopecks"])


def _signed_cursor(payload: dict[str, Any]) -> str:
    """Return an opaque cursor bound to its tenant and report filters."""
    message = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    key = hmac.new(settings.jwt_secret_key.encode(), b"wms:seller-report-cursor:v1", hashlib.sha256).digest()
    signature = hmac.new(key, message, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(
        json.dumps({"payload": payload, "signature": signature}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).decode().rstrip("=")


def _read_signed_cursor(cursor: str) -> dict[str, Any]:
    try:
        decoded = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        payload = decoded["payload"]
        signature = decoded["signature"]
        message = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        key = hmac.new(settings.jwt_secret_key.encode(), b"wms:seller-report-cursor:v1", hashlib.sha256).digest()
        expected = hmac.new(key, message, hashlib.sha256).hexdigest()
        if not isinstance(payload, dict) or not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
            raise ValueError
        return payload
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        raise SellerReportError("invalid_cursor") from None


def _amount(value: int | None) -> int:
    return int(value or 0)


def _financial_totals(entries: list[dict[str, Any]]) -> dict[str, int]:
    gross = sum(_amount(row.get("amount_kopecks")) for row in entries if row.get("result") == "completed")
    reversal = sum(abs(_amount(row.get("amount_kopecks"))) for row in entries if row.get("result") == "reversed")
    net = sum(_amount(row.get("amount_kopecks")) for row in entries if row.get("result") != "unpriced")
    return {
        "unpriced_count": sum(1 for row in entries if row.get("result") == "unpriced"),
        "gross_total_kopecks": gross,
        "reversal_total_kopecks": reversal,
        "net_total_kopecks": net,
    }


def _totals(entries: list[dict[str, Any]], *, include_finance: bool) -> dict[str, int]:
    result: dict[str, int] = {
        "operation_count": len(entries),
        "item_quantity": sum(int(row.get("item_quantity") or 0) for row in entries),
        "not_billable_count": sum(1 for row in entries if row.get("result") == "not_billable"),
    }
    if include_finance:
        result.update(_financial_totals(entries))
    return result


async def _cutover(session: AsyncSession) -> datetime | None:
    return cast(
        datetime | None,
        await session.scalar(
            select(OperationFactCutover.occurred_at).where(OperationFactCutover.id == 1)
        ),
    )


async def _operation_entries(
    session: AsyncSession,
    *, tenant_id: uuid.UUID, start: datetime, end: datetime, seller_id: uuid.UUID | None, include_finance: bool,
) -> list[dict[str, Any]]:
    cutover = await _cutover(session)
    facts_query = select(OperationFact).where(
        OperationFact.tenant_id == tenant_id, OperationFact.seller_id.is_not(None),
        OperationFact.occurred_at >= start, OperationFact.occurred_at < end,
    )
    if cutover is not None:
        facts_query = facts_query.where(OperationFact.occurred_at >= cutover)
    if seller_id is not None:
        facts_query = facts_query.where(OperationFact.seller_id == seller_id)
    facts = list((await session.scalars(facts_query.order_by(OperationFact.occurred_at.desc(), OperationFact.id.desc()))).all())
    fact_ids = {fact.id for fact in facts}
    pricing: dict[uuid.UUID, list[BillingLedgerEntry]] = defaultdict(list)
    if fact_ids:
        rows = await session.execute(
            select(OperationFactLine.operation_fact_id, BillingLedgerEntry)
            .join(BillingLedgerLine, BillingLedgerLine.operation_fact_line_id == OperationFactLine.id)
            .join(BillingLedgerEntry, BillingLedgerEntry.id == BillingLedgerLine.ledger_entry_id)
            .where(BillingLedgerEntry.tenant_id == tenant_id, OperationFactLine.operation_fact_id.in_(fact_ids))
        )
        for fact_id, entry in rows:
            pricing[fact_id].append(entry)
    fact_lines: dict[uuid.UUID, list[OperationFactLine]] = defaultdict(list)
    if fact_ids:
        lines = await session.scalars(
            select(OperationFactLine).where(OperationFactLine.operation_fact_id.in_(fact_ids))
            .order_by(OperationFactLine.id)
        )
        for line in lines:
            fact_lines[line.operation_fact_id].append(line)
    result: list[dict[str, Any]] = []
    for fact in facts:
        priced = pricing.get(fact.id, [])
        money = sum(_amount(entry.amount) for entry in priced) if priced else None
        product_lines = fact_lines[fact.id]
        product_names = [line.product_name_snapshot for line in product_lines if line.product_name_snapshot]
        skus = [line.sku_snapshot for line in product_lines if line.sku_snapshot]
        finance_result = "unpriced" if money is None else "completed"
        row: dict[str, Any] = {
            "id": f"operation_fact:{fact.id}", "kind": "operation_fact", "seller_id": str(fact.seller_id),
            "seller_name": fact.seller_name_snapshot or "Не указан", "occurred_at": _as_moscow(fact.occurred_at).isoformat(),
            "service_code": fact.billable_service_code or fact.operation_code, "item_quantity": fact.item_quantity,
            "source_type": fact.document_type, "source_id": str(fact.document_id),
            "document_number": fact.document_number_snapshot,
            "product_name": ", ".join(dict.fromkeys(product_names)) or None,
            "sku": ", ".join(dict.fromkeys(skus)) or None,
            "source_target": _source_target(fact.document_type, fact.document_id),
            "result": "reversed" if fact.reversal_of_id else ("not_billable" if not fact.billable_service_code else (finance_result if include_finance else "completed")),
        }
        if include_finance:
            row["rate_kopecks"] = priced[0].rate if priced and len({entry.rate for entry in priced}) == 1 else None
            row["amount_kopecks"] = money
            row["unit"] = priced[0].unit if priced else None
            row["invoice_history"] = {"state": "unknown"}
        result.append(row)
    return result


async def _legacy_entries(
    session: AsyncSession,
    *, tenant_id: uuid.UUID, start: datetime, end: datetime, seller_id: uuid.UUID | None, include_finance: bool,
) -> list[dict[str, Any]]:
    cutover = await _cutover(session)
    query = select(BillingLedgerEntry, Seller.name).outerjoin(Seller, Seller.id == BillingLedgerEntry.seller_id).where(
        BillingLedgerEntry.tenant_id == tenant_id, BillingLedgerEntry.seller_id.is_not(None),
        BillingLedgerEntry.service_code != "storage_liter_day", BillingLedgerEntry.occurred_at >= start,
        BillingLedgerEntry.occurred_at < end,
    )
    if cutover is not None:
        query = query.where(BillingLedgerEntry.occurred_at < cutover)
    if seller_id is not None:
        query = query.where(BillingLedgerEntry.seller_id == seller_id)
    rows = (await session.execute(query.order_by(BillingLedgerEntry.occurred_at.desc(), BillingLedgerEntry.id.desc()))).all()
    entry_ids = {entry.id for entry, _seller_name in rows}
    line_snapshots: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
    if entry_ids:
        for line in (await session.scalars(
            select(BillingLedgerLine).where(BillingLedgerLine.ledger_entry_id.in_(entry_ids)).order_by(BillingLedgerLine.id)
        )).all():
            line_snapshots[line.ledger_entry_id].append(line.product_snapshot)
    result: list[dict[str, Any]] = []
    for entry, seller_name in rows:
        snapshots = line_snapshots[entry.id]
        product_names = [str(snapshot[key]) for snapshot in snapshots for key in ("name", "product_name", "product_name_snapshot") if snapshot.get(key)]
        skus = [str(snapshot[key]) for snapshot in snapshots for key in ("sku", "sku_code", "sku_snapshot") if snapshot.get(key)]
        finance_result = "unpriced" if entry.amount is None else "completed"
        row: dict[str, Any] = {
            "id": f"legacy_billing:{entry.id}", "kind": "legacy_billing", "seller_id": str(entry.seller_id),
            "seller_name": seller_name or "Не указан", "occurred_at": _as_moscow(entry.occurred_at).isoformat(),
            "service_code": entry.service_code, "item_quantity": int(entry.quantity) if entry.unit == "item" else None,
            "source_type": entry.source_type, "source_id": str(entry.source_id),
            "document_number": None,
            "product_name": ", ".join(dict.fromkeys(product_names)) or None,
            "sku": ", ".join(dict.fromkeys(skus)) or None,
            "source_target": _source_target(entry.source_type, entry.source_id),
            "result": "reversed" if entry.entry_type == "reversal" else (finance_result if include_finance else "completed"),
        }
        if include_finance:
            row.update({"unit": entry.unit, "rate_kopecks": entry.rate, "amount_kopecks": entry.amount, "billing_ledger_entry_id": str(entry.id)})
        result.append(row)
    return result


async def _invoice_history(session: AsyncSession, *, tenant_id: uuid.UUID, seller_id: uuid.UUID, entry_id: str) -> dict[str, Any]:
    invoices = list((await session.scalars(select(BillingInvoice).where(BillingInvoice.tenant_id == tenant_id, BillingInvoice.seller_id == seller_id))).all())
    known_ids: set[str] = set()
    for invoice in invoices:
        for line in invoice.lines:
            if not isinstance(line, dict):
                return {"state": "unknown"}
            docs = line.get("documents", [])
            if not isinstance(docs, list):
                return {"state": "unknown"}
            for document in docs:
                raw = document.get("id") if isinstance(document, dict) else None
                try:
                    known_ids.add(str(uuid.UUID(str(raw))))
                except (ValueError, TypeError, AttributeError):
                    return {"state": "unknown"}
    chain = {entry_id}
    try:
        entry_uuid = uuid.UUID(entry_id)
        frontier = {entry_uuid}
        while frontier:
            related = await session.execute(select(BillingLedgerEntry.id, BillingLedgerEntry.reversal_of_id).where(
                BillingLedgerEntry.tenant_id == tenant_id,
                (BillingLedgerEntry.id.in_(frontier)) | (BillingLedgerEntry.reversal_of_id.in_(frontier)),
            ))
            next_frontier: set[uuid.UUID] = set()
            for current, reversal_of in related:
                for related_id in (current, reversal_of):
                    if related_id is not None and str(related_id) not in chain:
                        chain.add(str(related_id))
                        next_frontier.add(related_id)
            frontier = next_frontier
    except ValueError:
        return {"state": "unknown"}
    count = 0
    for invoice in invoices:
        invoice_ids: set[str] = set()
        for line in invoice.lines:
            for document in line.get("documents", []):
                invoice_ids.add(str(document["id"]))
        if chain & invoice_ids:
            count += 1
    # Счета V2 держат источники строками, а не JSON внутри счёта. Без этого
    # запроса операция, уже включённая в новый счёт, выглядела бы невыставленной,
    # и оператор спокойно выставил бы её второй раз.
    v2_rows = await session.execute(
        select(BillingInvoiceV2Line.invoice_id)
        .join(BillingInvoiceV2Source, BillingInvoiceV2Source.invoice_line_id == BillingInvoiceV2Line.id)
        .where(
            BillingInvoiceV2Line.tenant_id == tenant_id,
            BillingInvoiceV2Source.billing_ledger_entry_id.in_({uuid.UUID(value) for value in chain}),
        )
        .distinct()
    )
    count += len(list(v2_rows))
    return {"state": "known", "count": count}


async def _storage_matrix_rates(
    session: AsyncSession, *, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> list[BillingTariffVersionV2]:
    """Ставки хранения из общей матрицы: свои у селлера и общие.

    Старые складские тарифы (`BillingTariffVersion` с `storage_liter_day`) здесь
    больше не читаются: владелец 27.08.2026 решил, что все тарифы задаются в
    Настройках, а привязка к складу отключается. Строки остаются в базе как
    история начислений и на расчёт не влияют.
    """
    rows = await session.scalars(
        select(BillingTariffVersionV2).where(
            BillingTariffVersionV2.tenant_id == tenant_id,
            BillingTariffVersionV2.service_code == "storage",
            BillingTariffVersionV2.employee_user_id.is_(None),
            BillingTariffVersionV2.product_id.is_(None),
            BillingTariffVersionV2.enabled.is_(True),
            (BillingTariffVersionV2.seller_id == seller_id)
            | BillingTariffVersionV2.seller_id.is_(None),
        )
    )
    return list(rows.all())


def _storage_rate_for_day(rates: list[BillingTariffVersionV2], day: date) -> int | None:
    """Ставка на конкретный день: своя у селлера бьёт общую независимо от дат.

    Внутри одного уровня точности решает дата: побеждает последняя версия,
    начавшаяся не позже конца этого дня.
    """
    day_end = datetime.combine(day, time.max, MOSCOW)
    day_start = datetime.combine(day, time.min, MOSCOW)
    best: tuple[int, datetime] | None = None
    best_rate: int | None = None
    for row in rates:
        started = _as_moscow(row.valid_from_at)
        if started > day_end:
            continue
        if row.valid_to_at is not None and _as_moscow(row.valid_to_at) <= day_start:
            continue
        specificity = 0 if row.seller_id is not None else 1
        candidate = (specificity, started)
        if best is None or (specificity, -started.timestamp()) < (best[0], -best[1].timestamp()):
            best = candidate
            best_rate = row.rate
    return best_rate


async def _storage_row(
    session: AsyncSession, *, tenant_id: uuid.UUID, seller_id: uuid.UUID, date_from: date, date_to: date, start: datetime, end: datetime, include_finance: bool,
) -> dict[str, Any]:
    warehouse_ids = set((await session.scalars(select(Warehouse.id).where(Warehouse.tenant_id == tenant_id, Warehouse.is_operational.is_(True)))).all())
    movements = list((await session.scalars(select(InventoryMovement).where(
        InventoryMovement.tenant_id == tenant_id, InventoryMovement.seller_id == seller_id,
        InventoryMovement.warehouse_id.in_(warehouse_ids or {uuid.UUID(int=0)}), InventoryMovement.created_at < end,
    ).order_by(InventoryMovement.created_at, InventoryMovement.id))).all())
    product_ids = {movement.product_id for movement in movements}
    products = {product.id: product for product in (await session.scalars(select(Product).where(Product.tenant_id == tenant_id, Product.id.in_(product_ids or {uuid.UUID(int=0)})))).all()}
    events_by_product: dict[uuid.UUID, list[ProductDimensionEvent]] = defaultdict(list)
    if product_ids:
        for event in (await session.scalars(select(ProductDimensionEvent).where(ProductDimensionEvent.tenant_id == tenant_id, ProductDimensionEvent.product_id.in_(product_ids)).order_by(ProductDimensionEvent.observed_at, ProductDimensionEvent.id))).all():
            events_by_product[event.product_id].append(event)
    grouped: dict[uuid.UUID, list[InventoryMovement]] = defaultdict(list)
    for movement in movements:
        grouped[movement.product_id].append(movement)
    liter_days = Decimal(0)
    missing = False
    fingerprint_sources: list[dict[str, Any]] = []
    for product_id, product_movements in grouped.items():
        product = products.get(product_id)
        if product is None:
            continue
        calculated, product_missing = interval_liter_days(product_movements, events_by_product[product_id], legacy_volume_liters=product.volume_liters, start=start, end=end)
        liter_days += calculated
        missing = missing or product_missing
        fingerprint_sources.append({"product": str(product_id), "moves": [(str(m.id), _as_moscow(m.created_at).isoformat(), m.quantity_delta) for m in product_movements], "dimensions": [(str(e.id), _as_moscow(e.observed_at).isoformat(), str(e.volume_liters)) for e in events_by_product[product_id]]})
    tariff_rows = await _storage_matrix_rates(session, tenant_id=tenant_id, seller_id=seller_id)
    amount = 0
    if not missing:
        for offset in range((date_to - date_from).days + 1):
            day = date_from + timedelta(days=offset)
            daily_liters = Decimal(0)
            day_start = datetime.combine(day, time.min, MOSCOW)
            day_end = day_start + timedelta(days=1)
            for product_id, product_movements in grouped.items():
                product = products.get(product_id)
                if product:
                    value, absent = interval_liter_days(product_movements, events_by_product[product_id], legacy_volume_liters=product.volume_liters, start=max(start, day_start), end=min(end, day_end))
                    if absent:
                        missing = True
                    daily_liters += value
            rate = _storage_rate_for_day(tariff_rows, day)
            if rate is not None:
                amount += int((daily_liters * Decimal(rate)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    payload = {"tenant_id": str(tenant_id), "seller_id": str(seller_id), "date_from": date_from.isoformat(), "date_to": date_to.isoformat(), "liter_days": str(liter_days), "amount_kopecks": None if missing else amount, "sources": fingerprint_sources, "tariffs": [(str(t.id), _as_moscow(t.valid_from_at).isoformat(), _as_moscow(t.valid_to_at).isoformat() if t.valid_to_at else None, t.rate, str(t.seller_id) if t.seller_id else None) for t in tariff_rows]}
    row: dict[str, Any] = {"kind": "storage", "date_from": date_from.isoformat(), "date_to": date_to.isoformat(), "liter_days": float(liter_days), "status": "missing_dimensions" if missing else "calculated", "calculation_token": _token(payload)}
    if include_finance and not missing:
        row["amount_kopecks"] = amount
    return row


async def build_seller_report(
    session: AsyncSession, *, tenant_id: uuid.UUID, date_from: date, date_to: date, include_finance: bool, seller_id: uuid.UUID | None = None, search: str | None = None,
) -> dict[str, Any]:
    start, end = moscow_interval(date_from, date_to)
    entries = await _operation_entries(session, tenant_id=tenant_id, start=start, end=end, seller_id=seller_id, include_finance=include_finance)
    entries.extend(await _legacy_entries(session, tenant_id=tenant_id, start=start, end=end, seller_id=seller_id, include_finance=include_finance))
    entries.sort(key=lambda row: (row["occurred_at"], row["kind"], row["id"]), reverse=True)
    if include_finance:
        for row in entries:
            if row["kind"] == "legacy_billing":
                row["invoice_history"] = await _invoice_history(session, tenant_id=tenant_id, seller_id=uuid.UUID(row["seller_id"]), entry_id=row["billing_ledger_entry_id"])
    sellers = list((await session.scalars(select(Seller).where(Seller.tenant_id == tenant_id).order_by(Seller.name))).all())
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        grouped[entry["seller_id"]].append(entry)
    rows: list[dict[str, Any]] = []
    for seller in sellers:
        if seller_id is not None and seller.id != seller_id:
            continue
        if search and search.lower() not in seller.name.lower():
            continue
        seller_entries = grouped[str(seller.id)]
        if not seller_entries:
            continue
        total = _totals(seller_entries, include_finance=include_finance)
        rows.append({"seller_id": str(seller.id), "seller_name": seller.name, **total, "details_target": f"/api/billing/seller-report/sellers/{seller.id}/details"})
    totals = _totals(entries, include_finance=include_finance)
    return {"rows": rows, "totals": {"seller_count": len(rows), **totals}, "entries": entries, "start": start, "end": end}


async def seller_details(
    session: AsyncSession, *, tenant_id: uuid.UUID, seller_id: uuid.UUID, date_from: date, date_to: date, include_finance: bool, limit: int = 50, cursor: str | None = None,
) -> dict[str, Any]:
    seller = await session.scalar(select(Seller).where(Seller.id == seller_id, Seller.tenant_id == tenant_id))
    if seller is None:
        raise SellerReportError("seller_not_found")
    report = await build_seller_report(session, tenant_id=tenant_id, seller_id=seller_id, date_from=date_from, date_to=date_to, include_finance=include_finance)
    entries = report["entries"]
    # Stable multi-key ordering: occurrence desc, source kind asc, UUID desc.
    entries.sort(key=lambda row: row["id"], reverse=True)
    entries.sort(key=lambda row: row["kind"])
    entries.sort(key=lambda row: row["occurred_at"], reverse=True)
    offset = 0
    if cursor:
        decoded = _read_signed_cursor(cursor)
        if (
            decoded.get("tenant_id") != str(tenant_id)
            or decoded.get("seller_id") != str(seller_id)
            or decoded.get("date_from") != date_from.isoformat()
            or decoded.get("date_to") != date_to.isoformat()
            or decoded.get("include_finance") is not include_finance
        ):
            raise SellerReportError("invalid_cursor")
        key = decoded.get("key")
        if not isinstance(key, dict):
            raise SellerReportError("invalid_cursor")
        try:
            offset = next(
                index + 1
                for index, entry in enumerate(entries)
                if entry["occurred_at"] == key["occurred_at"]
                and entry["id"] == key["id"]
                and entry["kind"] == key["kind"]
            )
        except (KeyError, StopIteration):
            raise SellerReportError("invalid_cursor") from None
    page = entries[offset:offset + limit]
    next_cursor = None
    if offset + limit < len(entries):
        tail = page[-1]
        next_cursor = _signed_cursor({
            "tenant_id": str(tenant_id),
            "seller_id": str(seller_id),
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "include_finance": include_finance,
            "key": {"occurred_at": tail["occurred_at"], "id": tail["id"], "kind": tail["kind"]},
        })
    storage = None if cursor else await _storage_row(session, tenant_id=tenant_id, seller_id=seller_id, date_from=date_from, date_to=date_to, start=report["start"], end=report["end"], include_finance=include_finance)
    return {"seller_id": str(seller_id), "seller_name": seller.name, "entries": page, "next_cursor": next_cursor, "storage_row": storage, "totals": _totals(entries, include_finance=include_finance)}
