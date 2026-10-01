"""Capture WB evidence and resolve exact RUB kopecks for LK_RECEIPT (BR2)."""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FbsOrder
from app.models.wb_order_price_snapshot import WbOrderPriceSnapshot

WB_ORDERS_SOURCE = "/api/v3/orders"
WB_NEW_ORDERS_SOURCE = "/api/v3/orders/new"
WB_STATISTICS_ORDERS_SOURCE = "/api/v1/supplier/orders"
WB_STATISTICS_ORDERS_URL = (
    "https://statistics-api.wildberries.ru/api/v1/supplier/orders"
)
CRPT_MAX_PRODUCT_COST = 99_999_999_999_999_999
_FIELDS = {
    "finalPrice": "final_price",
    "currencyCode": "currency_code",
    "convertedFinalPrice": "converted_final_price",
    "convertedCurrencyCode": "converted_currency_code",
}


class WbPriceDataError(ValueError):
    def __init__(self, code: str, message: str, snapshot_id: uuid.UUID | None = None) -> None:
        self.code = code
        self.snapshot_id = snapshot_id
        super().__init__(message)


@dataclass(frozen=True)
class WbProductCost:
    product_cost: int
    snapshot_id: uuid.UUID


def product_cost_from_snapshot(snapshot: WbOrderPriceSnapshot) -> WbProductCost:
    """No float conversion, x100 multiplication, or legacy FbsOrder.price fallback."""
    rub_values: list[int] = []
    for amount, currency, field in (
        (snapshot.final_price, snapshot.currency_code, "finalPrice"),
        (snapshot.converted_final_price, snapshot.converted_currency_code, "convertedFinalPrice"),
    ):
        if type(currency) is not int or currency != 643:
            continue
        if amount is None:
            raise WbPriceDataError(
                "missing_rub_final_price", f"WB {field}: финальная цена в RUB отсутствует",
                snapshot.id,
            )
        if type(amount) is not int:
            raise WbPriceDataError(
                "invalid_rub_price", f"WB {field}: сумма должна быть целым числом копеек",
                snapshot.id,
            )
        if not 0 <= amount <= CRPT_MAX_PRODUCT_COST:
            raise WbPriceDataError(
                "rub_price_out_of_range", f"WB {field}: сумма вне диапазона Честного знака",
                snapshot.id,
            )
        rub_values.append(amount)
    if not rub_values:
        raise WbPriceDataError(
            "missing_rub_final_price", "WB: финальная цена в RUB отсутствует", snapshot.id
        )
    if len(set(rub_values)) != 1:
        raise WbPriceDataError(
            "conflicting_rub_prices", "WB: finalPrice и convertedFinalPrice в RUB различаются",
            snapshot.id,
        )
    return WbProductCost(product_cost=rub_values[0], snapshot_id=snapshot.id)


async def capture_wb_price_snapshot(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    order_id: uuid.UUID,
    row: dict[str, Any],
    source: str = WB_ORDERS_SOURCE,
) -> WbOrderPriceSnapshot | None:
    if source not in {
        WB_ORDERS_SOURCE,
        WB_NEW_ORDERS_SOURCE,
        WB_STATISTICS_ORDERS_SOURCE,
    }:
        raise ValueError("unsupported_wb_price_source")
    # /orders/new may omit final prices. Never erase history with that partial feed.
    if source == WB_NEW_ORDERS_SOURCE and not any(field in row for field in _FIELDS):
        return None
    order = await session.scalar(select(FbsOrder).where(
        FbsOrder.id == order_id, FbsOrder.tenant_id == tenant_id,
        FbsOrder.seller_id == seller_id, FbsOrder.marketplace == "wb",
    ).with_for_update())
    if order is None:
        raise WbPriceDataError("order_not_found", "WB-заказ не найден")
    previous = await session.scalar(select(WbOrderPriceSnapshot).where(
        WbOrderPriceSnapshot.order_id == order_id,
    ).order_by(WbOrderPriceSnapshot.revision.desc()).limit(1))
    values = {attr: copy.deepcopy(row.get(field)) for field, attr in _FIELDS.items()}
    if previous is not None and all(
        # JSON distinguishes integer, bool and floating point: 1 != true != 1.0 here.
        type(getattr(previous, attr)) is type(value) and getattr(previous, attr) == value
        for attr, value in values.items()
    ):
        return previous
    snapshot = WbOrderPriceSnapshot(
        order_id=order_id, revision=1 if previous is None else previous.revision + 1,
        source=source, received_at=datetime.now(UTC), **values,
    )
    session.add(snapshot)
    await session.flush()
    return snapshot


async def resolve_wb_product_cost(
    session: AsyncSession, *, tenant_id: uuid.UUID, seller_id: uuid.UUID, order_id: uuid.UUID
) -> WbProductCost:
    snapshots = list(await session.scalars(select(WbOrderPriceSnapshot).join(
        FbsOrder, FbsOrder.id == WbOrderPriceSnapshot.order_id,
    ).where(
        FbsOrder.id == order_id, FbsOrder.tenant_id == tenant_id,
        FbsOrder.seller_id == seller_id, FbsOrder.marketplace == "wb",
    ).order_by(WbOrderPriceSnapshot.revision.desc())))
    if not snapshots:
        raise WbPriceDataError("missing_price_snapshot", "WB: снимок финальной цены отсутствует")
    latest_error: WbPriceDataError | None = None
    for snapshot in snapshots:
        try:
            return product_cost_from_snapshot(snapshot)
        except WbPriceDataError as exc:
            # /api/v3/orders does not expose finalPrice. Such a later partial
            # snapshot must not hide valid evidence captured earlier from
            # /api/v3/orders/new. Invalid or conflicting values remain fatal.
            if exc.code != "missing_rub_final_price":
                raise
            if latest_error is None:
                latest_error = exc
    assert latest_error is not None
    raise latest_error


def statistics_finished_price_to_kopecks(value: object) -> int:
    """Convert WB Statistics finishedPrice RUB to exact integer kopecks."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise WbPriceDataError(
            "invalid_wb_statistics_price",
            "WB Statistics: finishedPrice имеет неверный формат",
        )
    try:
        rubles = Decimal(str(value))
    except InvalidOperation as exc:
        raise WbPriceDataError(
            "invalid_wb_statistics_price",
            "WB Statistics: finishedPrice имеет неверный формат",
        ) from exc
    kopecks = rubles * 100
    if not rubles.is_finite() or kopecks != kopecks.to_integral_value():
        raise WbPriceDataError(
            "invalid_wb_statistics_price",
            "WB Statistics: finishedPrice нельзя точно перевести в копейки",
        )
    result = int(kopecks)
    # WB documents that zero can be returned temporarily while the report is filling.
    if result == 0:
        raise WbPriceDataError(
            "wb_statistics_price_not_ready",
            "WB Statistics: цена заказа ещё не рассчитана",
        )
    if not 0 < result <= CRPT_MAX_PRODUCT_COST:
        raise WbPriceDataError(
            "rub_price_out_of_range",
            "WB Statistics: finishedPrice вне диапазона Честного знака",
        )
    return result


async def fetch_statistics_order_prices(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    date_from: datetime,
    rids: set[str],
) -> dict[str, int]:
    """Fetch one WB orders report and return exact sale prices keyed by FBS rid/srid."""
    if not api_token or not rids:
        return {}
    if date_from.tzinfo is None:
        date_from = date_from.replace(tzinfo=UTC)
    date_from_value = date_from.astimezone(UTC).isoformat().replace("+00:00", "Z")
    try:
        response = await client.get(
            WB_STATISTICS_ORDERS_URL,
            headers={"Authorization": api_token},
            params={"dateFrom": date_from_value, "flag": 0},
        )
    except httpx.HTTPError as exc:
        raise WbPriceDataError(
            "wb_statistics_unavailable",
            "WB Statistics: не удалось получить цены заказов",
        ) from exc
    if response.status_code in {401, 403}:
        raise WbPriceDataError(
            "wb_statistics_access_denied",
            "WB Statistics: у сохранённого ключа нет доступа к отчёту заказов",
        )
    if response.status_code >= 400:
        raise WbPriceDataError(
            "wb_statistics_unavailable",
            f"WB Statistics: отчёт заказов недоступен (HTTP {response.status_code})",
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise WbPriceDataError(
            "wb_statistics_invalid_response",
            "WB Statistics: отчёт заказов вернул некорректный ответ",
        ) from exc
    if not isinstance(payload, list):
        raise WbPriceDataError(
            "wb_statistics_invalid_response",
            "WB Statistics: отчёт заказов вернул некорректный ответ",
        )
    result: dict[str, int] = {}
    errors: dict[str, WbPriceDataError] = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        rid = row.get("srid")
        if not isinstance(rid, str) or rid not in rids or row.get("isCancel") is True:
            continue
        try:
            price = statistics_finished_price_to_kopecks(row.get("finishedPrice"))
        except WbPriceDataError as exc:
            errors[rid] = exc
            continue
        existing = result.get(rid)
        if existing is not None and existing != price:
            raise WbPriceDataError(
                "wb_statistics_price_conflict",
                f"WB Statistics: для заказа {rid} получены разные цены",
            )
        result[rid] = price
    if not result and len(rids) == 1:
        only_rid = next(iter(rids))
        if only_rid in errors:
            raise errors[only_rid]
    return result
