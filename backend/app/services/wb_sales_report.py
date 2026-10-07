"""Complete seller-scoped WB sale evidence, without order/status/price fallbacks."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, DecimalException, InvalidOperation
from email.utils import parsedate_to_datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

import httpx
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.models.fbs_order import FbsOrder
from app.services.wb_order_price_service import CRPT_MAX_PRODUCT_COST, WbPriceDataError
from app.services.wildberries_credentials_service import get_decrypted_marketplace_token

SALES_SOURCE = "/api/v1/supplier/sales"
SALES_URL = "https://statistics-api.wildberries.ru" + SALES_SOURCE
FINANCE_SOURCE = "/api/finance/v1/sales-reports/detailed"
FINANCE_URL = "https://finance-api.wildberries.ru" + FINANCE_SOURCE
FINANCE_HISTORY_START = datetime(2024, 1, 29, tzinfo=ZoneInfo("Europe/Moscow"))
MOSCOW = ZoneInfo("Europe/Moscow")
PAUSE_SECONDS = 61
_local_next: dict[uuid.UUID, float] = {}
_local_defer: dict[uuid.UUID, str] = {}
# Reserve a request slot atomically across API replicas, using Redis server time.
_RESERVE = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local slot = math.max(now, tonumber(redis.call('GET', KEYS[1]) or '0'))
redis.call('SET', KEYS[1], slot + 61000, 'PX', slot - now + 122000)
return slot - now
"""
_DEFER = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local slot = math.max(now + tonumber(ARGV[1]), tonumber(redis.call('GET', KEYS[1]) or '0'))
redis.call('SET', KEYS[1], slot, 'PX', slot - now + 122000)
redis.call('SET', KEYS[1] .. ':defer', ARGV[2], 'PX', slot - now + 122000)
return 1
"""


class WbSalesError(ValueError):
    pass


def _json_integer(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        # Preserve an integer lexeme rejected by Python's conversion-size guard.
        # Normal integers retain their type; the global safety limit stays intact.
        return value


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def sale_cost(row: dict[str, Any]) -> int:
    value = row.get("finishedPrice")
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise WbPriceDataError(
            "invalid_sale_price", "WB: стоимость продажи finishedPrice отсутствует"
        )
    try:
        price = Decimal(str(value))
    except DecimalException:
        raise WbPriceDataError(
            "invalid_sale_price", "WB: стоимость продажи finishedPrice некорректна"
        ) from None
    if not price.is_finite():
        raise WbPriceDataError("invalid_sale_price", "WB: стоимость продажи некорректна")
    if not 0 < price <= Decimal(CRPT_MAX_PRODUCT_COST) / 100:
        raise WbPriceDataError(
            "invalid_sale_price", "WB: стоимость продажи вне допустимого диапазона"
        )
    # Tuple construction shifts the exponent exactly, independently of Decimal's
    # default 28-digit arithmetic context. Never round a fractional kopek away.
    sign, digits, exponent = price.as_tuple()
    amount = Decimal((sign, digits, cast(int, exponent) + 2))
    if amount != amount.to_integral_value():
        raise WbPriceDataError("invalid_sale_price", "WB: стоимость продажи требует точных копеек")
    if not 0 < amount <= CRPT_MAX_PRODUCT_COST:
        raise WbPriceDataError(
            "invalid_sale_price", "WB: стоимость продажи вне допустимого диапазона"
        )
    return int(amount)


def _stamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise WbSalesError("wb_sales_incomplete_timestamp")
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        raise WbSalesError("wb_sales_incomplete_timestamp") from None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=MOSCOW)


def _cursor_value(value: Any) -> Decimal:
    stamp = _stamp(value)
    fraction = re.search(r"[T ]\d{2}:\d{2}:\d{2}[.,](\d+)", value)
    # datetime supports only microseconds; WB may include more cursor digits.
    return Decimal(int(stamp.timestamp())) + (
        Decimal("0." + fraction[1]) if fraction else Decimal(0)
    )


@dataclass(frozen=True)
class SalesOrder:
    id: uuid.UUID
    wb_rid: str
    created_at_wb: datetime


@dataclass(frozen=True)
class SalesReport:
    by_rid: dict[str, dict[str, Any]]
    received_at: datetime
    date_from: str
    pages: int
    row_count: int
    coverage_missing: frozenset[uuid.UUID] = frozenset()
    excluded_rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def evidence(self, order: FbsOrder) -> dict[str, Any]:
        assert order.wb_rid is not None
        row = self.by_rid[order.wb_rid]
        return {
            "source": row.get("_source", SALES_SOURCE),
            "order_id": str(order.id),
            "srid": order.wb_rid,
            "saleID": row["saleID"],
            "date": row["date"],
            "lastChangeDate": row["lastChangeDate"],
            "finishedPrice": str(row.get("finishedPrice")),
            "raw_sale": copy.deepcopy(row.get("_financial_row", row)),
            "price_field": "retailAmount"
            if row.get("_source") == FINANCE_SOURCE
            else "finishedPrice",
            "received_at": self.received_at.isoformat(),
            "complete": True,
            "dateFrom": self.date_from,
            "pages": self.pages,
            "row_count": self.row_count,
        }

    def exclusion_evidence(self, order: FbsOrder) -> dict[str, Any]:
        rows = self.excluded_rows.get(order.wb_rid or "", [])
        kinds = [str(row.get("saleID", "")) for row in rows]
        code = (
            "wb_sales_returned"
            if any(kind.startswith("R") for kind in kinds)
            else "wb_sales_unknown_type"
            if any(not kind.startswith("S") for kind in kinds)
            else "wb_sales_conflicting_or_ambiguous"
            if rows
            else "wb_sales_sale_not_found"
        )
        return {
            "source": SALES_SOURCE,
            "order_id": str(order.id),
            "srid": order.wb_rid,
            "code": code,
            "raw_sales": copy.deepcopy(rows),
            "received_at": self.received_at.isoformat(),
            "dateFrom": self.date_from,
            "complete": True,
            "pages": self.pages,
            "row_count": self.row_count,
        }


async def _wait_slot(
    seller_id: uuid.UUID,
    redis: Redis | None,
    progress: Callable[[], Awaitable[None]] | None,
) -> None:
    key = f"wb:sales:rate:{seller_id}"
    while True:
        generation = (
            await redis.get(key + ":defer") if redis is not None else _local_defer.get(seller_id)
        )
        if redis is not None:
            wait_ms = int(await cast(Awaitable[Any], redis.eval(_RESERVE, 1, key)))
            delay = max(0, wait_ms / 1000)
        else:
            # Production must use the shared broker, never replica-local slots.
            now = time.monotonic()
            slot = max(now, _local_next.get(seller_id, now))
            _local_next[seller_id] = slot + PAUSE_SECONDS
            delay = max(0, slot - now)
        # Every heartbeat commits before sleeping, never holding row locks.
        if progress is not None:
            await progress()
        while delay > 0:
            chunk = min(delay, 30) if progress is not None else delay
            await asyncio.sleep(chunk)
            delay -= chunk
            if progress is not None:
                await progress()
        latest = (
            await redis.get(key + ":defer") if redis is not None else _local_defer.get(seller_id)
        )
        if latest is None or latest == generation:
            return
        # A 429 invalidates reservations made before it. Reserve again atomically
        # instead of moving all waiting readers onto the same cooldown deadline.


async def _defer(seller_id: uuid.UUID, redis: Redis | None, retry_after: str | None) -> None:
    delay = float(PAUSE_SECONDS)
    if retry_after:
        try:
            seconds = Decimal(retry_after)
            if seconds.is_finite() and seconds >= 0:
                delay = max(delay, float(seconds))
        except InvalidOperation:
            with suppress(TypeError, ValueError, OverflowError):
                delay = max(
                    delay, (parsedate_to_datetime(retry_after) - datetime.now(UTC)).total_seconds()
                )
    # Delay subsequent reads in every replica, not just the caller receiving 429.
    if redis is not None:
        await cast(
            Awaitable[Any],
            redis.eval(
                _DEFER,
                1,
                f"wb:sales:rate:{seller_id}",
                str(int(delay * 1000)),
                uuid.uuid4().hex,
            ),
        )
    else:
        _local_next[seller_id] = max(_local_next.get(seller_id, 0), time.monotonic() + delay)
        _local_defer[seller_id] = uuid.uuid4().hex


def _select_sales(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_rid: dict[str, dict[str, dict[str, Any]]] = {}
    blocked: set[str] = set()
    sale_rids: dict[str, set[str]] = {}
    for row in rows:
        rid, identifier = row.get("srid"), row.get("saleID")
        if not isinstance(rid, str) or not rid or not isinstance(identifier, str) or not identifier:
            # An unidentified row could be a return of any candidate. The report
            # is unusable, rather than silently ignoring incomplete identity.
            raise WbSalesError("wb_sales_incomplete_identity")
        sale_rids.setdefault(identifier, set()).add(rid)
        if not identifier.startswith("S"):
            blocked.add(rid)  # Returns and unknown kinds never authorize a sale.
            continue
        _stamp(row.get("date"))
        _stamp(row.get("lastChangeDate"))
        previous = by_rid.setdefault(rid, {}).get(identifier)
        if previous is not None:
            # A boundary repeat/change is the same unit only when its identity,
            # event date and sale price agree. Update time itself may advance.
            if any(
                previous.get(key) != row.get(key)
                for key in ("finishedPrice", "date", "nmId", "barcode")
            ):
                blocked.add(rid)
            if _cursor_value(row["lastChangeDate"]) <= _cursor_value(previous["lastChangeDate"]):
                continue
        by_rid[rid][identifier] = row
    for rids in sale_rids.values():
        if len(rids) != 1:
            blocked.update(rids)
    return {
        rid: next(iter(sales.values()))
        for rid, sales in by_rid.items()
        if len(sales) == 1 and rid not in blocked
    }


def _finance_events(rows: list[dict[str, Any]], rids: set[str]) -> list[dict[str, Any]]:
    """Finance fees are not sales; retain exact one-unit sale/return evidence."""
    events: list[dict[str, Any]] = []
    for row in rows:
        rid = row.get("srid")
        operation = str(row.get("sellerOperName", "")).strip()
        if rid not in rids:
            continue
        correction = "сторно" in operation.lower() or (
            "корректиров" in operation.lower()
            and any(word in operation.lower() for word in ("продаж", "возврат"))
        )
        if operation not in {"Продажа", "Возврат"} and not correction:
            continue
        identifier = row.get("rrdId")
        if not isinstance(identifier, int) or isinstance(identifier, bool) or identifier <= 0:
            raise WbSalesError("wb_finance_history_incomplete_identity")
        sale = operation == "Продажа" and row.get("docTypeName") == "Продажа"
        price = (
            row.get("retailAmount")
            if (
                row.get("quantity") == 1
                and not isinstance(row.get("quantity"), bool)
                and row.get("currency") == "RUB"
            )
            else None
        )
        events.append(
            {
                "srid": rid,
                "saleID": ("SF" if sale else "RF") + str(identifier),
                "date": row.get("saleDt"),
                "lastChangeDate": row.get("saleDt"),
                "finishedPrice": price,
                "nmId": row.get("nmId"),
                "barcode": row.get("sku"),
                "_source": FINANCE_SOURCE,
                "_financial_row": copy.deepcopy(row),
            }
        )
    return events


async def _read_finance_history(
    http: httpx.AsyncClient,
    token: str,
    seller_id: uuid.UUID,
    redis: Redis | None,
    since: datetime,
    until: datetime,
    progress: Callable[[], Awaitable[None]] | None,
) -> tuple[list[dict[str, Any]], int]:
    # This POST only reads a report; it neither submits a document nor mutates WB.
    cursor = 0
    pages = 0
    rows: list[dict[str, Any]] = []
    while True:
        await _wait_slot(seller_id, redis, progress)
        response = await http.post(
            FINANCE_URL,
            headers={"Authorization": token},
            json={
                "dateFrom": max(since, FINANCE_HISTORY_START).astimezone(MOSCOW).date().isoformat(),
                "dateTo": until.astimezone(MOSCOW).date().isoformat(),
                "limit": 100000,
                "rrdId": cursor,
                "period": "weekly",
                "fields": [
                    "rrdId",
                    "srid",
                    "sellerOperName",
                    "docTypeName",
                    "quantity",
                    "retailAmount",
                    "currency",
                    "nmId",
                    "sku",
                    "saleDt",
                    "reportId",
                    "rrDate",
                ],
            },
        )
        pages += 1
        if response.status_code == 204:
            return rows, pages
        if response.status_code != 200:
            if response.status_code == 429:
                await _defer(seller_id, redis, response.headers.get("Retry-After"))
            raise WbSalesError(f"wb_finance_history_incomplete_http_{response.status_code}")
        try:
            page = json.loads(
                response.content, parse_float=str, parse_int=_json_integer, parse_constant=str
            )
        except (ValueError, UnicodeDecodeError):
            raise WbSalesError("wb_finance_history_incomplete_json") from None
        if not isinstance(page, list) or any(not isinstance(row, dict) for row in page):
            raise WbSalesError("wb_finance_history_incomplete_response")
        if not page:
            # WB documents 204 as the complete terminal response for this API.
            raise WbSalesError("wb_finance_history_incomplete_empty_page")
        next_cursor = page[-1].get("rrdId")
        if (
            not isinstance(next_cursor, int)
            or isinstance(next_cursor, bool)
            or next_cursor <= cursor
        ):
            raise WbSalesError("wb_finance_history_incomplete_stalled_cursor")
        rows.extend(page)
        cursor = next_cursor


async def read_sales_report(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    orders: list[SalesOrder],
    fresh: bool = True,
    progress: Callable[[], Awaitable[None]] | None = None,
) -> SalesReport:
    now = datetime.now(UTC)
    earliest = min((_aware(order.created_at_wb) for order in orders), default=now)
    since = max(earliest, now - timedelta(days=90))
    cursor = since.astimezone(MOSCOW).isoformat()
    initial_cursor = cursor
    token = await get_decrypted_marketplace_token(session, tenant_id, seller_id)
    # Credentials/order reads are finished before any vendor wait: callers re-lock
    # and revalidate local scope/bindings after the report is complete.
    await session.commit()
    if token is None:
        raise WbSalesError("wb_sales_credentials_missing")
    broker = settings.celery_broker_url
    redis = Redis.from_url(broker, decode_responses=True) if broker else None
    if redis is None and settings.withdrawal_environment == "production":
        raise WbSalesError("wb_sales_shared_limiter_not_configured")
    identity = "\n".join(
        sorted(f"{order.id}:{order.wb_rid}:{order.created_at_wb.isoformat()}" for order in orders)
    )
    digest = hashlib.sha256(identity.encode()).hexdigest()
    cache_key = f"wb:sales:complete:history-v2:{tenant_id}:{seller_id}:{digest}"
    rows: list[dict[str, Any]] = []
    pages = 0
    try:
        # Only completed reads can serve pagination. Preparation always bypasses
        # this short cache, and failed refresh never publishes partial data.
        if redis is not None and not fresh:
            cached = await redis.get(cache_key)
            if cached:
                try:
                    saved = json.loads(cached)
                    return SalesReport(
                        saved["by_rid"],
                        datetime.fromisoformat(saved["received_at"]),
                        saved["date_from"],
                        saved["pages"],
                        saved["row_count"],
                        frozenset(uuid.UUID(value) for value in saved["coverage_missing"]),
                        saved.get("excluded_rows", {}),
                    )
                except (KeyError, TypeError, ValueError):
                    pass
        async with httpx.AsyncClient(timeout=30) as http:
            while True:
                await _wait_slot(seller_id, redis, progress)
                response = await http.get(
                    SALES_URL,
                    headers={"Authorization": token},
                    params={"dateFrom": cursor, "flag": 0},
                )
                if response.status_code != 200:
                    # GET is safe to retry explicitly later. No body/header/token
                    # logging and no automatic burst after a vendor 429.
                    if response.status_code == 429:
                        await _defer(seller_id, redis, response.headers.get("Retry-After"))
                    raise WbSalesError(f"wb_sales_incomplete_http_{response.status_code}")
                try:
                    # Preserve numeric lexemes without constructing Decimal here:
                    # an unsupported price exponent is an item error, not a reason
                    # to discard a complete page and its healthy neighboring sales.
                    page = json.loads(
                        response.content,
                        parse_float=str,
                        parse_int=_json_integer,
                        parse_constant=str,
                    )
                except (ValueError, UnicodeDecodeError):
                    raise WbSalesError("wb_sales_incomplete_json") from None
                pages += 1
                if not isinstance(page, list) or any(not isinstance(row, dict) for row in page):
                    raise WbSalesError("wb_sales_incomplete_response")
                if not page:
                    break
                last = page[-1].get("lastChangeDate")
                if _cursor_value(last) <= _cursor_value(cursor):
                    raise WbSalesError("wb_sales_incomplete_stalled_cursor")
                # Keep every digit of the provider cursor, never datetime-format it.
                cursor = last
                # Numeric lexemes stay exact and JSON evidence remains serializable.
                rows.extend(json.loads(json.dumps(page, default=str)))
        by_rid = _select_sales(rows)
        old_orders = [
            order for order in orders if _aware(order.created_at_wb) < now - timedelta(days=90)
        ]
        archive_row_count = 0
        if old_orders:
            async with httpx.AsyncClient(timeout=60) as finance_http:
                archive, archive_pages = await _read_finance_history(
                    finance_http,
                    token,
                    seller_id,
                    redis,
                    earliest,
                    now,
                    progress,
                )
            archive_row_count = len(archive)
            pages += archive_pages
            events = _finance_events(archive, {order.wb_rid for order in old_orders})
            archived_sales = _select_sales(events)
            blocked = {event["srid"] for event in events} - archived_sales.keys()
            # A recent operational return still excludes a historical sale.
            operational_excluded = {row["srid"] for row in rows} - by_rid.keys()
            for rid, row in archived_sales.items():
                if rid not in operational_excluded:
                    by_rid.setdefault(rid, row)
            for rid in blocked:
                by_rid.pop(rid, None)
            rows.extend(events)
        coverage_missing = frozenset(
            order.id
            for order in old_orders
            if _aware(order.created_at_wb) < FINANCE_HISTORY_START and order.wb_rid not in by_rid
        )
        # A report unit cannot authorize multiple local orders with the same rid.
        rid_orders: dict[str, set[uuid.UUID]] = {}
        for order in orders:
            if order.wb_rid:
                rid_orders.setdefault(order.wb_rid, set()).add(order.id)
        by_rid = {
            rid: row
            for rid, row in by_rid.items()
            if rid in rid_orders and len(rid_orders[rid]) == 1
        }
        excluded_rows: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            rid = row["srid"]
            if rid in rid_orders and rid not in by_rid:
                excluded_rows.setdefault(rid, []).append(row)
        report = SalesReport(
            by_rid,
            datetime.now(UTC),
            max(earliest, FINANCE_HISTORY_START).astimezone(MOSCOW).isoformat()
            if old_orders
            else initial_cursor,
            pages,
            len(rows) + archive_row_count - (len(events) if old_orders else 0),
            coverage_missing,
            excluded_rows,
        )
        if redis is not None:
            await redis.set(
                cache_key,
                json.dumps(
                    {
                        "by_rid": report.by_rid,
                        "received_at": report.received_at.isoformat(),
                        "date_from": report.date_from,
                        "pages": report.pages,
                        "row_count": report.row_count,
                        "coverage_missing": [str(value) for value in report.coverage_missing],
                        "excluded_rows": report.excluded_rows,
                    }
                ),
                ex=300,
            )
        return report
    except (httpx.HTTPError, RedisError):
        raise WbSalesError("wb_sales_incomplete_transport") from None
    finally:
        if redis is not None:
            await redis.aclose()
