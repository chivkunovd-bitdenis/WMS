# ruff: noqa: E501
"""Read-only typed projection for the Wave 3 seller billing report."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.models.billing import (
    BillingInvoice,
    BillingInvoiceV2Line,
    BillingInvoiceV2Source,
    BillingLedgerEntry,
    BillingLedgerLine,
)
from app.models.fbs_order import (
    FBS_ORDER_STATUS_EXTERNAL_PROCESSING,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_PACKED,
    FbsOrder,
)
from app.models.fbs_supply import FbsSupply
from app.models.operation_fact import OperationFact, OperationFactCutover, OperationFactLine
from app.models.seller import Seller
from app.services.billing_ledger_service import _resolve_v2_tariff
from app.services.marketplace_scope import MARKETPLACE_NAMES, order_display_number
from app.services.storage_measurement_service import (
    MOSCOW,
)


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
    return value.replace(tzinfo=UTC).astimezone(MOSCOW) if value.tzinfo is None else value.astimezone(MOSCOW)


def _source_target(source_type: str, source_id: uuid.UUID) -> dict[str, str] | None:
    if source_type == "inbound_intake":
        return {"kind": "inbound", "source_id": str(source_id)}
    if source_type == "marketplace_unload":
        return {"kind": "route", "to": f"/app/ff/mp-shipments?open_mp={source_id}"}
    # Документ заказа FBS — это его история: кто подобрал, упаковал, печатал и
    # передавал. Открывается тем же кликом по номеру, что и остальные документы.
    if source_type == "fbs_order":
        return {"kind": "fbs_order", "source_id": str(source_id)}
    if source_type == "fbs_supply":
        return {"kind": "route", "to": f"/app/ff/fbs?supply_id={source_id}"}
    return None


def _token(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    fingerprint = hashlib.sha256(canonical).hexdigest()
    signed = {"version": 1, "fingerprint": fingerprint, "payload": payload}
    message = json.dumps(signed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    key = hmac.new(settings.jwt_secret_key.encode(), b"wms:seller-storage:v1", hashlib.sha256).digest()
    signature = hmac.new(key, message, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(json.dumps({**signed, "signature": signature}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).decode().rstrip("=")


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


_NATURAL_GROUPS: dict[str, tuple[str, ...]] = {
    "inbound_items": ("inbound",),
    "packing_items": ("packing", "packaging"),
    "outbound_items": ("marketplace_outbound",),
    "fbs_items": ("fbs_order",),
}


def _natural_totals(entries: list[dict[str, Any]]) -> dict[str, int]:
    """Сколько штук товара прошло через каждый участок за период.

    Считаем только сделанную работу: сторно вычитать нечего, а строки без
    ставки — это всё равно принятый и упакованный товар, просто ещё не
    оценённый деньгами.
    """
    result = {key: 0 for key in _NATURAL_GROUPS}
    for row in entries:
        if row.get("result") in {"reversed", "not_billable"}:
            continue
        code = str(row.get("service_code") or "")
        quantity = int(row.get("item_quantity") or 0)
        for key, codes in _NATURAL_GROUPS.items():
            if code in codes:
                result[key] += quantity
    return result


def _totals(entries: list[dict[str, Any]], *, include_finance: bool) -> dict[str, int]:
    result: dict[str, int] = {
        "operation_count": len(entries),
        "item_quantity": sum(int(row.get("item_quantity") or 0) for row in entries),
        "not_billable_count": sum(1 for row in entries if row.get("result") == "not_billable"),
        **_natural_totals(entries),
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


async def _live_price(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    fact: OperationFact,
    product_id: uuid.UUID | None = None,
) -> tuple[int | None, str | None, int | None]:
    """Цена операции по истории ставок: ставка, единица, сумма.

    Начисление пишется в момент события и задним числом не чинится: не нашлась
    ставка, не отработал фон — строки нет навсегда, и отчёт показывает ноль.
    Ставки при этом версионные: у каждой есть срок действия, старые не стираются.
    Значит цену прошлой операции можно спросить заново и получить ровно ту же
    цифру — снимок для отчёта не нужен.
    """
    if fact.billable_service_code is None or fact.seller_id is None:
        return None, None, None
    tariff = await _resolve_v2_tariff(
        session,
        tenant_id=tenant_id,
        seller_id=fact.seller_id,
        product_id=product_id,
        service_code=fact.billable_service_code,
        occurred_at=fact.occurred_at,
    )
    if tariff is None:
        return None, None, None
    # «За документ» стоит одинаково, сколько бы строк в документе ни было.
    quantity = 1 if tariff.unit == "document" else int(fact.item_quantity or 0)
    if quantity <= 0:
        # Ноль штук — это не «бесплатно», это нечего считать. Иначе строка
        # выпадает из счётчика непроценённых и дырку никто не замечает.
        return None, None, None
    return tariff.rate, tariff.unit, tariff.rate * quantity


async def _operation_entries(
    session: AsyncSession,
    *, tenant_id: uuid.UUID, start: datetime, end: datetime, seller_id: uuid.UUID | None, include_finance: bool,
) -> tuple[list[dict[str, Any]], set[tuple[str, uuid.UUID]]]:
    """Строки расчётов по фактам операций и деньги, начисленные по их документам.

    Вторым значением возвращается набор документов, которые уже показаны здесь:
    по ним начисления не должны второй раз приезжать старой веткой отчёта.
    """
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
    # Деньги ищем по документу, а не по строке операции. Раньше начисление
    # связывалось с фактом через `operation_fact_line_id`, но это поле не
    # заполняет ни один боевой путь — оно всегда пустое. Соединение по нему не
    # находило ничего: суммы в отчёте считались на лету, а в счёт не попадала ни
    # одна операция, потому что у строки не было id начисления. Документ же у
    # факта и у начисления один и тот же: `document_type`/`document_id` против
    # `source_type`/`source_id`.
    charges: dict[tuple[str, uuid.UUID], list[BillingLedgerEntry]] = defaultdict(list)
    if facts:
        document_ids = {fact.document_id for fact in facts}
        own_charges = list(
            (
                await session.scalars(
                    select(BillingLedgerEntry).where(
                        BillingLedgerEntry.tenant_id == tenant_id,
                        BillingLedgerEntry.source_id.in_(document_ids),
                    )
                )
            ).all()
        )
        for entry in own_charges:
            charges[(entry.source_type, entry.source_id)].append(entry)
        # Сторно документом не адресуется: оно ссылается на отменяемое
        # начисление (`source_type='billing_reversal'`, `source_id` — id той
        # строки). Поэтому его находим вторым шагом и кладём к тому же
        # документу — иначе у отменённой операции остаётся только «плюс», а
        # «минус» не показывает никто.
        document_of_charge = {
            entry.id: (entry.source_type, entry.source_id) for entry in own_charges
        }
        if document_of_charge:
            for reversal in (
                await session.scalars(
                    select(BillingLedgerEntry).where(
                        BillingLedgerEntry.tenant_id == tenant_id,
                        BillingLedgerEntry.reversal_of_id.in_(document_of_charge),
                    )
                )
            ).all():
                if reversal.reversal_of_id is None:
                    continue
                charges[document_of_charge[reversal.reversal_of_id]].append(reversal)
    fact_lines: dict[uuid.UUID, list[OperationFactLine]] = defaultdict(list)
    if fact_ids:
        lines = await session.scalars(
            select(OperationFactLine).where(OperationFactLine.operation_fact_id.in_(fact_ids))
            .order_by(OperationFactLine.id)
        )
        for line in lines:
            fact_lines[line.operation_fact_id].append(line)
    # Имя поставки FBS для старых фактов. Снимок номера пишется в момент
    # события, и у фактов, созданных до того, как витрина научилась брать
    # отображаемый номер, там пусто — в расчётах строка выходила «Документ без
    # номера». Достраиваем на чтении, чтобы починились и уже накопленные записи.
    # Поставка заказа FBS: по ней открывается и карточка поставки, и её история.
    # Отдельного экрана заказа в системе нет, поэтому «документ» заказа — это
    # поставка, в которой он уехал.
    order_supplies: dict[uuid.UUID, tuple[uuid.UUID, str]] = {}
    fbs_order_ids = {
        fact.document_id for fact in facts if fact.document_type == FBS_ORDER_DOCUMENT_TYPE
    }
    if fbs_order_ids:
        supply_rows = await session.execute(
            select(
                FbsOrder.id, FbsSupply.id, FbsSupply.display_number,
                FbsSupply.wb_supply_id, FbsSupply.name,
            )
            .join(FbsSupply, FbsSupply.id == FbsOrder.supply_id)
            .where(FbsOrder.tenant_id == tenant_id, FbsOrder.id.in_(fbs_order_ids))
        )
        for supply_row in supply_rows:
            label = next(
                (str(value).strip() for value in supply_row[2:] if str(value or "").strip()),
                None,
            )
            if label is not None:
                order_supplies[supply_row[0]] = (supply_row[1], label)

    supply_names: dict[uuid.UUID, str] = {}
    supply_ids = {
        fact.document_id
        for fact in facts
        if fact.document_type == "fbs_supply" and not fact.document_number_snapshot
    }
    if supply_ids:
        supply_rows = await session.execute(
            select(
                FbsSupply.id, FbsSupply.document_number, FbsSupply.display_number,
                FbsSupply.wb_supply_id, FbsSupply.name,
            ).where(FbsSupply.tenant_id == tenant_id, FbsSupply.id.in_(supply_ids))
        )
        for supply_row in supply_rows:
            label = next(
                (str(value).strip() for value in supply_row[1:] if str(value or "").strip()),
                None,
            )
            if label is not None:
                supply_names[supply_row[0]] = f"Поставка {label}"

    result: list[dict[str, Any]] = []
    covered: set[tuple[str, uuid.UUID]] = set()
    consumed: set[uuid.UUID] = set()
    by_document: dict[tuple[str, uuid.UUID], dict[str, Any]] = {}
    for fact in facts:
        document = (fact.document_type, fact.document_id)
        covered.add(document)
        # Сторно берёт себе строку сторно, обычный факт — строку начисления:
        # у отменённого документа в журнале лежат обе, и без разбора по типу
        # запись сторно приписалась бы исходной операции.
        wanted_entry_type = "reversal" if fact.reversal_of_id else "charge"
        priced = [
            entry for entry in charges[document]
            if entry.service_code == fact.billable_service_code
            and entry.entry_type == wanted_entry_type
        ]
        consumed.update(entry.id for entry in priced)
        # Строка начисления, показанная здесь, не должна приехать второй раз
        # старой веткой отчёта: у сторно свой адрес источника, и по документу
        # оно бы не отсеклось.
        covered.update((entry.source_type, entry.source_id) for entry in priced)
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
            "document_number": fact.document_number_snapshot or supply_names.get(fact.document_id),
            "product_name": ", ".join(dict.fromkeys(product_names)) or None,
            "sku": ", ".join(dict.fromkeys(skus)) or None,
            "source_target": _source_target(fact.document_type, fact.document_id),
            "supply": (
                {"id": str(order_supplies[fact.document_id][0]),
                 "number": order_supplies[fact.document_id][1]}
                if fact.document_id in order_supplies
                else None
            ),
            "result": "reversed" if fact.reversal_of_id else ("not_billable" if not fact.billable_service_code else (finance_result if include_finance else "completed")),
        }
        if fact.document_type == FBS_ORDER_DOCUMENT_TYPE:
            row["fbs_status_label"] = _confirmed_label(fact.marketplace)
        if include_finance:
            row["rate_kopecks"] = priced[0].rate if priced and len({entry.rate for entry in priced}) == 1 else None
            row["amount_kopecks"] = money
            row["unit"] = priced[0].unit if priced else None
            row["invoice_history"] = {"state": "unknown"}
            if len(priced) == 1:
                # Id начисления — это то, чем операцию кладут в счёт. Без него
                # галочка выбора остаётся выключенной, даже когда деньги есть.
                row["billing_ledger_entry_id"] = str(priced[0].id)
            if money is None and not fact.reversal_of_id:
                single_product = (
                    product_lines[0].product_id if len(product_lines) == 1 else None
                )
                rate, unit, amount = await _live_price(
                    session, tenant_id=tenant_id, fact=fact, product_id=single_product
                )
                if amount is not None:
                    row["rate_kopecks"] = rate
                    row["unit"] = unit
                    row["amount_kopecks"] = amount
                    row["result"] = "completed"
                    # Начисления у операции нет, поэтому в счёт её пока не
                    # выбрать: галочка объяснит причину сама.
                    row["priced_live"] = True
        result.append(row)
        by_document[document] = row

    # Упаковка своего факта не пишет: она начисляется по тому же документу, что
    # и отгрузка или заказ FBS. Без отдельной строки эти деньги не видел никто —
    # ни отчёт, ни счёт. Строку собираем из начисления, а имя документа,
    # товары и переход берём у факта, к которому оно относится.
    for document, document_charges in charges.items():
        host = by_document.get(document)
        if host is None:
            continue
        for entry in document_charges:
            if entry.id in consumed or entry.seller_id is None:
                continue
            consumed.add(entry.id)
            covered.add((entry.source_type, entry.source_id))
            extra: dict[str, Any] = {
                **host,
                "id": f"billing_entry:{entry.id}",
                "occurred_at": _as_moscow(entry.occurred_at).isoformat(),
                "service_code": entry.service_code,
                "item_quantity": int(entry.quantity) if entry.unit == "item" else None,
                "result": "reversed" if entry.entry_type == "reversal" else "completed",
            }
            if include_finance:
                extra["rate_kopecks"] = entry.rate
                extra["amount_kopecks"] = entry.amount
                extra["unit"] = entry.unit
                extra["billing_ledger_entry_id"] = str(entry.id)
                extra["invoice_history"] = {"state": "unknown"}
                extra.pop("priced_live", None)
                if entry.amount is None:
                    extra["result"] = "unpriced"
            result.append(extra)
    return result, covered




FBS_ORDER_DOCUMENT_TYPE = "fbs_order"
FBS_STATUS_CONFIRMED_LABEL = "ВБ получил"
FBS_STATUS_HANDED_LABEL = "Передан ВБ"


def _confirmed_label(marketplace: str | None) -> str:
    """«Маркетплейс забрал заказ» — с именем того маркетплейса, который забрал.

    Подписи были зашиты вайлдберрисовскими константами, и заказ Ozon приезжал в
    расчёты с надписью «ВБ получил».
    """
    if not marketplace or marketplace == "wb":
        return FBS_STATUS_CONFIRMED_LABEL
    return f"{MARKETPLACE_NAMES.get(marketplace, marketplace)} получил"


def _handed_label(marketplace: str | None) -> str:
    if not marketplace or marketplace == "wb":
        return FBS_STATUS_HANDED_LABEL
    return f"Передан {MARKETPLACE_NAMES.get(marketplace, marketplace)}"
_FBS_HANDED_STATUSES = (
    FBS_ORDER_STATUS_PACKED,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_EXTERNAL_PROCESSING,
)


async def _fbs_handed_entries(
    session: AsyncSession,
    *, tenant_id: uuid.UUID, start: datetime, end: datetime, seller_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Переданные, но ещё не подтверждённые заказы FBS.

    В сумму раздела они не идут: работа считается сделанной только когда
    маркетплейс подтвердил, что забрал заказ. Но спрятать их нельзя — оператор
    должен видеть, что заказ уехал и ждёт подтверждения, а не потерялся.
    """
    orders = list(
        (
            await session.scalars(
                select(FbsOrder)
                .where(
                    FbsOrder.tenant_id == tenant_id,
                    FbsOrder.seller_id == seller_id,
                    FbsOrder.status.in_(_FBS_HANDED_STATUSES),
                    FbsOrder.updated_at >= start,
                    FbsOrder.updated_at < end,
                )
                .order_by(FbsOrder.updated_at.desc())
                .limit(200)
            )
        ).all()
    )
    # Поставка, в которой заказ уехал: по ней открывается история. Без неё
    # номер заказа в расчётах рисовался ссылкой, но нажатие ничего не делало —
    # у строки просто не было, куда вести.
    supplies: dict[uuid.UUID, tuple[uuid.UUID, str]] = {}
    supply_ids = {order.supply_id for order in orders if order.supply_id is not None}
    if supply_ids:
        for supply_row in await session.execute(
            select(
                FbsSupply.id, FbsSupply.display_number, FbsSupply.wb_supply_id, FbsSupply.name
            ).where(FbsSupply.tenant_id == tenant_id, FbsSupply.id.in_(supply_ids))
        ):
            label = next(
                (str(value).strip() for value in supply_row[1:] if str(value or "").strip()),
                None,
            )
            if label is not None:
                supplies[supply_row[0]] = (supply_row[0], label)
    rows: list[dict[str, Any]] = []
    for order in orders:
        supply = supplies.get(order.supply_id) if order.supply_id is not None else None
        rows.append(
            {
                "id": f"fbs_order:{order.id}",
                "kind": "fbs_order_handed",
                "supply": (
                    {"id": str(supply[0]), "number": supply[1]} if supply is not None else None
                ),
                "seller_id": str(order.seller_id),
                "seller_name": "",
                "occurred_at": _as_moscow(order.updated_at).isoformat(),
                "service_code": FBS_ORDER_DOCUMENT_TYPE,
                "item_quantity": None,
                "source_type": FBS_ORDER_DOCUMENT_TYPE,
                "source_id": str(order.id),
                "document_number": f"Заказ {order_display_number(order)}",
                "product_name": None,
                "sku": None,
                "source_target": {"kind": "fbs_order", "source_id": str(order.id)},
                "result": "not_billable",
                "fbs_status_label": _handed_label(order.marketplace),
            }
        )
    return rows

async def _legacy_entries(
    session: AsyncSession,
    *, tenant_id: uuid.UUID, start: datetime, end: datetime, seller_id: uuid.UUID | None, include_finance: bool,
    exclude_documents: set[tuple[str, uuid.UUID]] | None = None,
) -> list[dict[str, Any]]:
    cutover = await _cutover(session)
    query = select(BillingLedgerEntry, Seller.name).outerjoin(Seller, Seller.id == BillingLedgerEntry.seller_id).where(
        BillingLedgerEntry.tenant_id == tenant_id, BillingLedgerEntry.seller_id.is_not(None),
        # Хранение показывается отдельной строкой раскрывашки и отдельной
        # суммой в сводке. Строкой операции оно приезжало вторым разом и
        # удваивало деньги там, где точка отсечки не проставлена.
        BillingLedgerEntry.service_code.not_in(("storage_liter_day", "storage")),
        BillingLedgerEntry.occurred_at >= start,
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
    skip = exclude_documents or set()
    for entry, seller_name in rows:
        # Документ, у которого есть факт операции, уже показан строкой факта
        # вместе со своими деньгами. Здесь он дал бы вторую строку и удвоил
        # сумму — в средах, где точка отсечки не проставлена, это как раз и
        # происходило бы после перехода на поиск денег по документу.
        if (entry.source_type, entry.source_id) in skip:
            continue
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


async def _invoice_history_map(
    session: AsyncSession, *, tenant_id: uuid.UUID, seller_id: uuid.UUID, entry_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """В скольких счетах уже стоит каждое из начислений страницы.

    Считается сразу по всей странице, а не по строке за раз: счета селлера и
    источники счетов V2 читаются по одному разу на страницу. Построчный вариант
    открывал пятьдесят одинаковых чтений на каждое открытие раскрывашки.

    Сторно и его начисление считаются одной и той же работой, поэтому цепочка
    взаимных ссылок раскручивается целиком: счёт, где лежит любое звено,
    считается счётом всей цепочки.
    """
    if not entry_ids:
        return {}
    invoices = list(
        (
            await session.scalars(
                select(BillingInvoice).where(
                    BillingInvoice.tenant_id == tenant_id, BillingInvoice.seller_id == seller_id
                )
            )
        ).all()
    )
    invoice_documents: list[set[str]] = []
    for invoice in invoices:
        invoice_ids: set[str] = set()
        for line in invoice.lines:
            if not isinstance(line, dict):
                return {entry_id: {"state": "unknown"} for entry_id in entry_ids}
            docs = line.get("documents", [])
            if not isinstance(docs, list):
                return {entry_id: {"state": "unknown"} for entry_id in entry_ids}
            for document in docs:
                raw = document.get("id") if isinstance(document, dict) else None
                try:
                    invoice_ids.add(str(uuid.UUID(str(raw))))
                except (ValueError, TypeError, AttributeError):
                    return {entry_id: {"state": "unknown"} for entry_id in entry_ids}
        invoice_documents.append(invoice_ids)

    try:
        roots = {uuid.UUID(value) for value in entry_ids}
    except ValueError:
        return {entry_id: {"state": "unknown"} for entry_id in entry_ids}

    # Цепочки всех строк страницы раскручиваем одним волновым обходом: связей у
    # начисления одна-две, и волн получается столько же, а не по волне на строку.
    chains: dict[uuid.UUID, set[str]] = {root: {str(root)} for root in roots}
    owner: dict[uuid.UUID, set[uuid.UUID]] = {root: {root} for root in roots}
    frontier = set(roots)
    seen = set(roots)
    while frontier:
        related = await session.execute(
            select(BillingLedgerEntry.id, BillingLedgerEntry.reversal_of_id).where(
                BillingLedgerEntry.tenant_id == tenant_id,
                (BillingLedgerEntry.id.in_(frontier))
                | (BillingLedgerEntry.reversal_of_id.in_(frontier)),
            )
        )
        next_frontier: set[uuid.UUID] = set()
        for current, reversal_of in related:
            for known, discovered in ((current, reversal_of), (reversal_of, current)):
                if known is None or discovered is None:
                    continue
                for root in owner.get(known, set()):
                    if str(discovered) in chains[root]:
                        continue
                    chains[root].add(str(discovered))
                    owner.setdefault(discovered, set()).add(root)
                    if discovered not in seen:
                        seen.add(discovered)
                        next_frontier.add(discovered)
        frontier = next_frontier

    all_ids = {uuid.UUID(value) for chain in chains.values() for value in chain}
    v2_by_entry: dict[str, set[uuid.UUID]] = defaultdict(set)
    if all_ids:
        for invoice_id, ledger_entry_id in (
            await session.execute(
                select(
                    BillingInvoiceV2Line.invoice_id,
                    BillingInvoiceV2Source.billing_ledger_entry_id,
                )
                .join(
                    BillingInvoiceV2Source,
                    BillingInvoiceV2Source.invoice_line_id == BillingInvoiceV2Line.id,
                )
                .where(
                    BillingInvoiceV2Line.tenant_id == tenant_id,
                    BillingInvoiceV2Source.billing_ledger_entry_id.in_(all_ids),
                )
                .distinct()
            )
        ).all():
            v2_by_entry[str(ledger_entry_id)].add(invoice_id)

    history: dict[str, dict[str, Any]] = {}
    for entry_id in entry_ids:
        chain = chains[uuid.UUID(entry_id)]
        count = sum(1 for invoice_ids in invoice_documents if chain & invoice_ids)
        v2_invoices: set[uuid.UUID] = set()
        for value in chain:
            v2_invoices |= v2_by_entry.get(value, set())
        history[entry_id] = {"state": "known", "count": count + len(v2_invoices)}
    return history


async def _storage_row(
    session: AsyncSession, *, tenant_id: uuid.UUID, seller_id: uuid.UUID, date_from: date, date_to: date, start: datetime, end: datetime, include_finance: bool,
) -> dict[str, Any]:
    """Хранение за период — сумма ночных начислений, а не пересчёт на лету.

    Раньше экран пересчитывал литро-дни по движениям при каждом открытии, а
    ночная задача писала свои. Две цифры об одном и том же расходились бы при
    первом же расхождении формул, и никто бы не понял, какая настоящая.
    Источник один: что ночь записала, то экран и счёт и показывают.
    """
    rows = list(
        (
            await session.execute(
                select(
                    func.coalesce(func.sum(BillingLedgerEntry.quantity), 0),
                    func.coalesce(func.sum(BillingLedgerEntry.amount), 0),
                ).where(
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
    quantity, amount_sum = rows[0]
    liter_days = float(quantity or 0)
    row: dict[str, Any] = {
        "kind": "storage",
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "liter_days": liter_days,
        "status": "calculated",
    }
    if include_finance:
        # Сутки без ставки дают ноль — это видно и в отчёте, и в счёте, и не
        # мешает выставить счёт за то, что посчитано.
        row["amount_kopecks"] = int(amount_sum or 0)
    return row


async def build_seller_report(
    session: AsyncSession, *, tenant_id: uuid.UUID, date_from: date, date_to: date, include_finance: bool, seller_id: uuid.UUID | None = None, search: str | None = None,
) -> dict[str, Any]:
    start, end = moscow_interval(date_from, date_to)
    entries, covered = await _operation_entries(session, tenant_id=tenant_id, start=start, end=end, seller_id=seller_id, include_finance=include_finance)
    entries.extend(await _legacy_entries(session, tenant_id=tenant_id, start=start, end=end, seller_id=seller_id, include_finance=include_finance, exclude_documents=covered))
    entries.sort(key=lambda row: (row["occurred_at"], row["kind"], row["id"]), reverse=True)
    sellers = list((await session.scalars(select(Seller).where(Seller.tenant_id == tenant_id).order_by(Seller.name))).all())
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        grouped[entry["seller_id"]].append(entry)
    # Хранение живёт отдельной строкой раскрывашки, а не записью операции.
    # Поэтому в сводке его нет ни в строке селлера, ни в её деньгах: селлер, у
    # которого за период было только хранение, исчезал совсем, а у остальных
    # «Стоимость услуг» расходилась с суммой выставленного счёта — счёт-то
    # хранение включает.
    storage_money: dict[uuid.UUID, int] = {
        row[0]: int(row[1] or 0)
        for row in (
            await session.execute(
                select(
                    BillingLedgerEntry.seller_id,
                    func.coalesce(func.sum(BillingLedgerEntry.amount), 0),
                )
                .where(
                    BillingLedgerEntry.tenant_id == tenant_id,
                    BillingLedgerEntry.service_code == "storage",
                    BillingLedgerEntry.entry_type == "charge",
                    BillingLedgerEntry.occurred_at >= start,
                    BillingLedgerEntry.occurred_at < end,
                    BillingLedgerEntry.seller_id.is_not(None),
                )
                .group_by(BillingLedgerEntry.seller_id)
            )
        ).all()
    }
    rows: list[dict[str, Any]] = []
    tenant_storage_money = 0
    for seller in sellers:
        if seller_id is not None and seller.id != seller_id:
            continue
        if search and search.lower() not in seller.name.lower():
            continue
        seller_entries = grouped[str(seller.id)]
        seller_storage = storage_money.get(seller.id, 0)
        if not seller_entries and seller.id not in storage_money:
            continue
        total = _totals(seller_entries, include_finance=include_finance)
        if include_finance and seller_storage:
            total["gross_total_kopecks"] += seller_storage
            total["net_total_kopecks"] += seller_storage
            tenant_storage_money += seller_storage
        rows.append({"seller_id": str(seller.id), "seller_name": seller.name, **total, "details_target": f"/api/billing/seller-report/sellers/{seller.id}/details"})
    totals = _totals(entries, include_finance=include_finance)
    if include_finance and tenant_storage_money:
        totals["gross_total_kopecks"] += tenant_storage_money
        totals["net_total_kopecks"] += tenant_storage_money
    return {"rows": rows, "totals": {"seller_count": len(rows), **totals}, "entries": entries, "start": start, "end": end}


async def storage_totals(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    date_from: date,
    date_to: date,
    seller_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Литро-дни хранения за период — по всем селлерам или по одному.

    Считается отдельным запросом, а не вместе со сводкой: расчёт хранения
    прокручивает движения товара с самого начала, и тащить его в основную
    таблицу значило бы заставлять оператора ждать ради одной плашки.
    """
    start, end = moscow_interval(date_from, date_to)
    if seller_id is not None:
        seller_ids = [seller_id]
    else:
        seller_ids = list(
            (
                await session.scalars(select(Seller.id).where(Seller.tenant_id == tenant_id))
            ).all()
        )
    liter_days = 0.0
    amount = 0
    complete = True
    for current in seller_ids:
        row = await _storage_row(
            session,
            tenant_id=tenant_id,
            seller_id=current,
            date_from=date_from,
            date_to=date_to,
            start=start,
            end=end,
            include_finance=True,
        )
        liter_days += float(row.get("liter_days") or 0)
        money = row.get("amount_kopecks")
        if isinstance(money, int):
            amount += money
        elif row.get("status") == "missing_dimensions":
            complete = False
    return {"liter_days": liter_days, "amount_kopecks": amount, "complete": complete}


async def seller_details(
    session: AsyncSession, *, tenant_id: uuid.UUID, seller_id: uuid.UUID, date_from: date, date_to: date, include_finance: bool, limit: int = 50, cursor: str | None = None,
) -> dict[str, Any]:
    seller = await session.scalar(select(Seller).where(Seller.id == seller_id, Seller.tenant_id == tenant_id))
    if seller is None:
        raise SellerReportError("seller_not_found")
    report = await build_seller_report(session, tenant_id=tenant_id, seller_id=seller_id, date_from=date_from, date_to=date_to, include_finance=include_finance)
    entries = report["entries"]
    # Итоги считаем до того, как подмешаем переданные заказы FBS: они денег не
    # приносят и не должны раздувать ни суммы, ни счётчики документов.
    totals = _totals(entries, include_finance=include_finance)
    entries = entries + await _fbs_handed_entries(
        session, tenant_id=tenant_id, seller_id=seller_id, start=report["start"], end=report["end"]
    )
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
    if include_finance:
        # Историю счетов спрашиваем только по видимой странице и одним заходом
        # на всю страницу. Раньше она считалась по каждой строке за весь период
        # — отдельным чтением всех счетов селлера на строку, — и то же самое
        # повторялось на экране сводки, где её никто не показывает.
        page_entry_ids = [
            str(row["billing_ledger_entry_id"])
            for row in page
            if row.get("billing_ledger_entry_id")
        ]
        history = await _invoice_history_map(
            session, tenant_id=tenant_id, seller_id=seller_id, entry_ids=page_entry_ids
        )
        for row in page:
            entry_id = row.get("billing_ledger_entry_id")
            if entry_id and str(entry_id) in history:
                row["invoice_history"] = history[str(entry_id)]
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
    return {"seller_id": str(seller_id), "seller_name": seller.name, "entries": page, "next_cursor": next_cursor, "storage_row": storage, "totals": totals}
