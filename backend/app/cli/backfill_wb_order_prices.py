"""WMS-517: one-off backfill of WB order prices for orders older than price capture.

WMS stores the buyer price (finalPrice) only since 27.09.2026, and WB returns it
only while an order is new. For older WB orders with Chestny Znak codes this
command looks the price up and appends a snapshot that withdrawal reads:

1. WB Statistics /api/v1/supplier/orders, field finishedPrice — the price paid
   with all discounts (matches finalPrice to the kopeck).
2. If the order is absent there (WB omits orders without confirmed payment):
   WB Marketplace /api/v3/orders, field convertedPrice — the order price in RUB
   with all discounts except the WB wallet one.

Read-only by default; pass ``--apply`` to write. Never prints the WB token.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.wb_order_price_snapshot import WbOrderPriceSnapshot
from app.services.wb_order_price_service import CRPT_MAX_PRODUCT_COST, has_price
from app.services.wildberries_credentials_service import get_decrypted_marketplace_token

STATISTICS_URL = "https://statistics-api.wildberries.ru/api/v1/supplier/orders"
ORDERS_URL = "https://marketplace-api.wildberries.ru/api/v3/orders"
STATISTICS_SOURCE = "backfill /api/v1/supplier/orders finishedPrice"
ORDERS_SOURCE = "backfill /api/v3/orders convertedPrice"
STATISTICS_PAUSE_SECONDS = 61  # WB Statistics: 1 request per minute per seller
STATISTICS_ATTEMPTS = 3
ORDERS_WINDOW = timedelta(days=29)  # /api/v3/orders: at most 30 days per request
RUB = 643


@dataclass(frozen=True)
class OrderRef:
    id: uuid.UUID
    wb_order_id: int
    wb_rid: str | None
    created_at_wb: datetime


@dataclass
class SellerReport:
    tenant_id: str
    seller_id: str
    orders_without_price: int = 0
    statistics_found: int = 0
    orders_api_found: int = 0
    not_found: list[int] = field(default_factory=list)
    written: int = 0
    statistics_error: str | None = None
    error: str | None = None


def _kopecks(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        amount = Decimal(str(value)) * 100
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount != amount.to_integral_value():
        return None
    result = int(amount)
    return result if 0 < result <= CRPT_MAX_PRODUCT_COST else None


async def _orders_without_price(
    session: AsyncSession, seller_id: uuid.UUID | None
) -> dict[tuple[uuid.UUID, uuid.UUID], list[OrderRef]]:
    since = datetime.now(UTC) - timedelta(days=89)  # WB keeps report rows for 90 days
    has_kiz = exists(
        select(FbsOrderMarking.id).where(
            FbsOrderMarking.order_id == FbsOrder.id,
            FbsOrderMarking.kind == "sgtin",
            FbsOrderMarking.meta_status != "rejected",
        )
    )
    priced = exists(
        select(WbOrderPriceSnapshot.id).where(
            WbOrderPriceSnapshot.order_id == FbsOrder.id, has_price()
        )
    )
    query = select(
        FbsOrder.tenant_id,
        FbsOrder.seller_id,
        FbsOrder.id,
        FbsOrder.wb_order_id,
        FbsOrder.wb_rid,
        FbsOrder.created_at_wb,
    ).where(
        FbsOrder.marketplace == "wb",
        FbsOrder.created_at_wb >= since,
        has_kiz,
        ~priced,
    )
    if seller_id is not None:
        query = query.where(FbsOrder.seller_id == seller_id)
    grouped: dict[tuple[uuid.UUID, uuid.UUID], list[OrderRef]] = defaultdict(list)
    for tenant_id, seller_id_, order_id, wb_order_id, wb_rid, created in await session.execute(
        query
    ):
        created_utc = created if created.tzinfo else created.replace(tzinfo=UTC)
        grouped[(tenant_id, seller_id_)].append(
            OrderRef(order_id, int(wb_order_id), wb_rid, created_utc)
        )
    return grouped


async def _statistics_prices(
    client: httpx.AsyncClient, token: str, date_from: datetime, rids: set[str]
) -> dict[str, int]:
    found: dict[str, int] = {}
    cursor = date_from.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    while True:
        for attempt in range(STATISTICS_ATTEMPTS):
            response = await client.get(
                STATISTICS_URL,
                headers={"Authorization": token},
                params={"dateFrom": cursor, "flag": 0},
            )
            if response.status_code != 429 or attempt == STATISTICS_ATTEMPTS - 1:
                break
            await asyncio.sleep(STATISTICS_PAUSE_SECONDS)
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list) or not rows:
            return found
        for row in rows:
            rid = row.get("srid")
            if rid in rids and row.get("isCancel") is not True:
                price = _kopecks(row.get("finishedPrice"))
                if price is not None:
                    found[rid] = price
        last = rows[-1].get("lastChangeDate")
        # One page holds up to ~80 000 rows; the next page starts at lastChangeDate.
        if len(rows) < 80_000 or not isinstance(last, str) or last == cursor:
            return found
        cursor = last
        await asyncio.sleep(STATISTICS_PAUSE_SECONDS)


async def _orders_api_prices(
    client: httpx.AsyncClient, token: str, orders: list[OrderRef]
) -> dict[int, int]:
    wanted = {int(order.wb_order_id) for order in orders}
    start = min(order.created_at_wb for order in orders) - timedelta(hours=1)
    end = max(order.created_at_wb for order in orders) + timedelta(hours=1)
    found: dict[int, int] = {}
    while start < end:
        window_end = min(start + ORDERS_WINDOW, end)
        next_token = 0
        while True:
            response = await client.get(
                ORDERS_URL,
                headers={"Authorization": token},
                params={
                    "limit": 1000,
                    "next": next_token,
                    "dateFrom": int(start.timestamp()),
                    "dateTo": int(window_end.timestamp()),
                },
            )
            response.raise_for_status()
            data = response.json()
            rows = data.get("orders") or []
            for row in rows:
                order_id = row.get("id")
                price = row.get("convertedPrice")
                if (
                    order_id in wanted
                    and row.get("convertedCurrencyCode") == RUB
                    and isinstance(price, int)
                    and not isinstance(price, bool)
                    and 0 < price <= CRPT_MAX_PRODUCT_COST
                ):
                    found[order_id] = price
            next_token = data.get("next") or 0
            if not rows or not next_token:
                break
            await asyncio.sleep(0.3)
        start = window_end
    return found


async def _write(session: AsyncSession, order_id: uuid.UUID, price: int, source: str) -> bool:
    order = await session.scalar(
        select(FbsOrder).where(FbsOrder.id == order_id).with_for_update()
    )
    if order is None:
        return False
    # Re-check under the row lock: the regular sync may have captured a price meanwhile.
    if await session.scalar(
        select(WbOrderPriceSnapshot.id).where(
            WbOrderPriceSnapshot.order_id == order_id, has_price()
        ).limit(1)
    ):
        return False
    revision = await session.scalar(
        select(func.max(WbOrderPriceSnapshot.revision)).where(
            WbOrderPriceSnapshot.order_id == order_id
        )
    )
    session.add(
        WbOrderPriceSnapshot(
            order_id=order_id,
            revision=(revision or 0) + 1,
            final_price=price,
            currency_code=RUB,
            converted_final_price=price,
            converted_currency_code=RUB,
            source=source,
            received_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return True


async def run(*, apply: bool, seller_id: uuid.UUID | None) -> list[SellerReport]:
    reports: list[SellerReport] = []
    async with SessionLocal() as session:
        grouped = await _orders_without_price(session, seller_id)
        await session.rollback()
    async with httpx.AsyncClient(timeout=120.0) as client:
        for index, ((tenant, seller), orders) in enumerate(sorted(grouped.items())):
            report = SellerReport(str(tenant), str(seller), orders_without_price=len(orders))
            reports.append(report)
            try:
                async with SessionLocal() as session:
                    token = await get_decrypted_marketplace_token(session, tenant, seller)
                if not token:
                    report.error = "no_wb_token"
                    continue
                if index:
                    await asyncio.sleep(STATISTICS_PAUSE_SECONDS)
                try:
                    by_rid = await _statistics_prices(
                        client,
                        token,
                        min(order.created_at_wb for order in orders) - timedelta(hours=1),
                        {order.wb_rid for order in orders if order.wb_rid},
                    )
                except httpx.HTTPStatusError as exc:
                    # A key without the Statistics category still reads /api/v3/orders.
                    report.statistics_error = f"wb_http_{exc.response.status_code}"
                    by_rid = {}
                prices: dict[uuid.UUID, tuple[int, str]] = {}
                for order in orders:
                    if order.wb_rid in by_rid:
                        prices[order.id] = (by_rid[order.wb_rid], STATISTICS_SOURCE)
                report.statistics_found = len(prices)
                rest = [order for order in orders if order.id not in prices]
                if rest:
                    by_id = await _orders_api_prices(client, token, rest)
                    for order in rest:
                        if int(order.wb_order_id) in by_id:
                            prices[order.id] = (by_id[int(order.wb_order_id)], ORDERS_SOURCE)
                            report.orders_api_found += 1
                        else:
                            report.not_found.append(int(order.wb_order_id))
                if apply:
                    async with SessionLocal() as session:
                        for order_id, (price, source) in prices.items():
                            report.written += int(await _write(session, order_id, price, source))
                        await session.commit()
            except httpx.HTTPStatusError as exc:
                report.error = f"wb_http_{exc.response.status_code}"
            except httpx.HTTPError as exc:
                report.error = f"wb_transport_{type(exc).__name__}"
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write snapshots")
    parser.add_argument("--seller-id", type=uuid.UUID, default=None)
    args = parser.parse_args()
    reports = asyncio.run(run(apply=args.apply, seller_id=args.seller_id))
    print(json.dumps(
        {"mode": "apply" if args.apply else "dry-run", "sellers": [asdict(r) for r in reports]},
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
