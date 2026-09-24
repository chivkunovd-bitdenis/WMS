"""Capture WB evidence and resolve exact RUB kopecks for LK_RECEIPT (BR2)."""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FbsOrder
from app.models.wb_order_price_snapshot import WbOrderPriceSnapshot

WB_ORDERS_SOURCE = "/api/v3/orders"
WB_NEW_ORDERS_SOURCE = "/api/v3/orders/new"
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
    if source not in {WB_ORDERS_SOURCE, WB_NEW_ORDERS_SOURCE}:
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
    snapshot = await session.scalar(select(WbOrderPriceSnapshot).join(
        FbsOrder, FbsOrder.id == WbOrderPriceSnapshot.order_id,
    ).where(
        FbsOrder.id == order_id, FbsOrder.tenant_id == tenant_id,
        FbsOrder.seller_id == seller_id, FbsOrder.marketplace == "wb",
    ).order_by(WbOrderPriceSnapshot.revision.desc()).limit(1))
    if snapshot is None:
        raise WbPriceDataError("missing_price_snapshot", "WB: снимок финальной цены отсутствует")
    return product_cost_from_snapshot(snapshot)
