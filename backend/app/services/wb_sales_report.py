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
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
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
MOSCOW = ZoneInfo("Europe/Moscow")
PAUSE_SECONDS = 61
_local_next: dict[uuid.UUID, float] = {}
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
return 1
"""


class WbSalesError(ValueError):
    pass


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def sale_cost(row: dict[str, Any]) -> int:
    value = row.get("finishedPrice")
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise WbPriceDataError(
            "invalid_sale_price", "WB: стоимость продажи finishedPrice отсутствует"
        )
    try:
        amount = Decimal(str(value)) * 100
    except InvalidOperation:
        raise WbPriceDataError(
            "invalid_sale_price", "WB: стоимость продажи finishedPrice некорректна"
        ) from None
    if not amount.is_finite() or amount != amount.to_integral_value():
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

    def evidence(self, order: FbsOrder) -> dict[str, Any]:
        assert order.wb_rid is not None
        row = self.by_rid[order.wb_rid]
        return {
            "source": SALES_SOURCE,
            "order_id": str(order.id),
            "srid": order.wb_rid,
            "saleID": row["saleID"],
            "date": row["date"],
            "lastChangeDate": row["lastChangeDate"],
            "finishedPrice": str(row.get("finishedPrice")),
            "raw_sale": copy.deepcopy(row),
            "received_at": self.received_at.isoformat(),
            "complete": True,
            "dateFrom": self.date_from,
            "pages": self.pages,
            "row_count": self.row_count,
        }


async def _wait_slot(
    seller_id: uuid.UUID,
    redis: Redis | None,
    progress: Callable[[], Awaitable[None]] | None,
) -> None:
    if redis is not None:
        wait_ms = int(
            await cast(Awaitable[Any], redis.eval(_RESERVE, 1, f"wb:sales:rate:{seller_id}"))
        )
        delay = max(0, wait_ms / 1000)
    else:
        # Development without Redis still respects the vendor interval. Production
        # must use the shared broker, so two replicas cannot independently burst.
        now = time.monotonic()
        slot = max(now, _local_next.get(seller_id, now))
        _local_next[seller_id] = slot + PAUSE_SECONDS
        delay = max(0, slot - now)
    # Long reports preserve the existing workflow lease while waiting for vendor
    # rate slots. Each heartbeat commits before sleep, never holding row locks.
    if progress is not None:
        await progress()
    while delay > 0:
        chunk = min(delay, 30) if progress is not None else delay
        await asyncio.sleep(chunk)
        delay -= chunk
        if progress is not None:
            await progress()


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
            ),
        )
    else:
        _local_next[seller_id] = max(_local_next.get(seller_id, 0), time.monotonic() + delay)


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
    cache_key = f"wb:sales:complete:{tenant_id}:{seller_id}:{digest}"
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
                    page = json.loads(response.content, parse_float=Decimal)
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
                # Decimal keeps HTTP amounts exact; JSON evidence remains serializable.
                rows.extend(json.loads(json.dumps(page, default=str)))
        by_rid = _select_sales(rows)
        coverage_missing = frozenset(
            order.id
            for order in orders
            if _aware(order.created_at_wb) < now - timedelta(days=90) and order.wb_rid not in by_rid
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
        report = SalesReport(
            by_rid,
            datetime.now(UTC),
            initial_cursor,
            pages,
            len(rows),
            coverage_missing,
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
