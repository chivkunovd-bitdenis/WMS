"""Read-only seller projection for FBS orders (WMS-616).

The warehouse worklist intentionally is not reused here: it applies operational
availability rules and exposes mutation-oriented data.  This projection is scoped
only by tenant and seller and keeps terminal/history rows visible.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast

from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.fbs_order import (
    FBS_ORDER_STATUS_ASSEMBLING,
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_DEFECT,
    FBS_ORDER_STATUS_DONE,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_IN_SUPPLY,
    FBS_ORDER_STATUS_NEW,
    FBS_ORDER_STATUS_PACKED,
    FBS_ORDER_STATUS_SORTED,
    FbsOrder,
    FbsOrderProduct,
)

SellerFbsMarketplace = Literal["wb", "ozon"]
SellerFbsStatusGroup = Literal[
    "new",
    "in_work",
    "handed",
    "accepted",
    "external_processing",
    "done",
    "cancelled",
    "defect",
]

_WB_CANCELLED = frozenset(
    {
        "cancel",
        "canceled",
        "cancelled",
        "canceled_by_client",
        "canceled_by_carrier",
        "declined_by_client",
    }
)
_OZON_CANCELLED = frozenset({"cancelled", "canceled", "cancelled_from_split_pending"})
_OZON_HANDED = frozenset({"delivering", "driver_pickup", "sent_by_seller"})
_OZON_ACCEPTED = frozenset({"acceptance_in_progress"})
_OZON_DONE = frozenset({"delivered", "done"})
_OZON_DONE_SUBSTATUSES = frozenset({"posting_delivered", "posting_received"})


@dataclass(frozen=True)
class SellerFbsOrderRow:
    id: uuid.UUID
    marketplace: SellerFbsMarketplace
    external_order_id: str | None
    status_group: SellerFbsStatusGroup
    items_quantity: int | None
    received_at: datetime


def _normalized(column: Any) -> ColumnElement[str]:
    return func.lower(func.trim(func.coalesce(column, "")))


def _status_group_expression() -> ColumnElement[str]:
    """One SQL expression shared by filtering and rendering.

    Cancellation/defect wins first, then an active local warehouse stage, then
    a marketplace-confirmed stage.  Unknown marketplace codes deliberately fall
    back to ``external_processing`` rather than leaking a raw code as a status.
    """
    local = _normalized(FbsOrder.status)
    provider = _normalized(FbsOrder.wb_status)
    provider_substatus = _normalized(FbsOrder.supplier_status)
    is_wb = FbsOrder.marketplace == "wb"
    is_ozon = FbsOrder.marketplace == "ozon"

    provider_cancelled = or_(
        and_(is_wb, or_(provider.in_(_WB_CANCELLED), provider_substatus.in_(_WB_CANCELLED))),
        and_(
            is_ozon,
            or_(provider.in_(_OZON_CANCELLED), provider_substatus.in_(_OZON_CANCELLED)),
        ),
    )
    provider_defect = and_(is_wb, or_(provider == "defect", provider_substatus == "defect"))
    local_in_work = local.in_(
        (FBS_ORDER_STATUS_IN_SUPPLY, FBS_ORDER_STATUS_ASSEMBLING, FBS_ORDER_STATUS_PACKED)
    )
    provider_done = or_(
        and_(is_wb, provider == "sold"),
        and_(
            is_ozon,
            or_(provider.in_(_OZON_DONE), provider_substatus.in_(_OZON_DONE_SUBSTATUSES)),
        ),
    )
    provider_accepted = or_(
        and_(is_wb, provider == "sorted"),
        and_(is_ozon, provider.in_(_OZON_ACCEPTED)),
    )
    provider_handed = and_(is_ozon, provider.in_(_OZON_HANDED))

    return case(
        (or_(local == FBS_ORDER_STATUS_CANCELLED, provider_cancelled), literal("cancelled")),
        (or_(local == FBS_ORDER_STATUS_DEFECT, provider_defect), literal("defect")),
        (local_in_work, literal("in_work")),
        (or_(local == FBS_ORDER_STATUS_DONE, provider_done), literal("done")),
        (or_(local == FBS_ORDER_STATUS_SORTED, provider_accepted), literal("accepted")),
        (or_(local == FBS_ORDER_STATUS_IN_DELIVERY, provider_handed), literal("handed")),
        (local == FBS_ORDER_STATUS_NEW, literal("new")),
        else_=literal("external_processing"),
    )


async def list_seller_fbs_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    marketplace: SellerFbsMarketplace | None,
    status_group: SellerFbsStatusGroup | None,
    limit: int,
    offset: int,
) -> tuple[list[SellerFbsOrderRow], int]:
    """Return one stable page using two bounded SQL statements and no N+1."""
    status_expr = _status_group_expression()
    filters: list[ColumnElement[bool]] = [
        FbsOrder.tenant_id == tenant_id,
        FbsOrder.seller_id == seller_id,
        FbsOrder.marketplace.in_(("wb", "ozon")),
    ]
    if marketplace is not None:
        filters.append(FbsOrder.marketplace == marketplace)
    if status_group is not None:
        filters.append(status_expr == status_group)

    total = int(
        await session.scalar(select(func.count(FbsOrder.id)).where(*filters)) or 0
    )

    quantities = (
        select(
            FbsOrderProduct.order_id.label("order_id"),
            func.count(FbsOrderProduct.id).label("position_count"),
            func.sum(FbsOrderProduct.quantity).label("quantity_sum"),
            func.min(FbsOrderProduct.quantity).label("minimum_quantity"),
        )
        .group_by(FbsOrderProduct.order_id)
        .subquery()
    )
    item_quantity = case(
        (FbsOrder.marketplace == "wb", literal(1)),
        (
            and_(
                quantities.c.position_count > 0,
                quantities.c.minimum_quantity > 0,
                quantities.c.quantity_sum > 0,
            ),
            quantities.c.quantity_sum,
        ),
        else_=None,
    ).label("items_quantity")

    statement = (
        select(
            FbsOrder.id,
            FbsOrder.marketplace,
            FbsOrder.external_order_id,
            FbsOrder.wb_order_id,
            FbsOrder.created_at_wb,
            status_expr.label("status_group"),
            item_quantity,
        )
        .outerjoin(quantities, quantities.c.order_id == FbsOrder.id)
        .where(*filters)
        .order_by(FbsOrder.created_at_wb.desc(), FbsOrder.id.desc())
        .limit(limit)
        .offset(offset)
    )
    records = (await session.execute(statement)).all()
    items: list[SellerFbsOrderRow] = []
    for record in records:
        raw_marketplace = str(record.marketplace)
        # Only WB/Ozon orders are valid seller FBS rows.  The model currently has
        # no enum constraint, so a damaged value is omitted instead of mislabeled.
        if raw_marketplace not in {"wb", "ozon"}:
            continue
        external_order_id = record.external_order_id
        if external_order_id is None and raw_marketplace == "wb":
            external_order_id = str(record.wb_order_id)
        items.append(
            SellerFbsOrderRow(
                id=record.id,
                marketplace=cast(SellerFbsMarketplace, raw_marketplace),
                external_order_id=external_order_id,
                status_group=cast(SellerFbsStatusGroup, record.status_group),
                items_quantity=(
                    int(record.items_quantity) if record.items_quantity is not None else None
                ),
                received_at=record.created_at_wb,
            )
        )
    return items, total
