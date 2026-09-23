"""Tenant-scoped withdrawal queries; no external waits while row locks are held."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_supply import FbsSupply
from app.models.marking_code import MarkingCode
from app.models.marking_withdrawal import WithdrawalItem, WithdrawalOperation
from app.models.product import Product
from app.models.seller import Seller
from app.models.wb_order_price_snapshot import WbOrderPriceSnapshot
from app.services.wb_order_price_service import WbPriceDataError, product_cost_from_snapshot

MOSCOW = ZoneInfo("Europe/Moscow")


@dataclass(frozen=True)
class WithdrawalScope:
    tenant_id: uuid.UUID
    seller_id: uuid.UUID
    user_id: uuid.UUID


class WithdrawalError(ValueError):
    def __init__(self, code: str, status_code: int = 409) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


def eligible_rows(scope: WithdrawalScope) -> Select[tuple[FbsOrderMarking, FbsOrder, FbsSupply]]:
    # External scans need no MarkingCode row. A linked pool code must still belong
    # to this seller/tenant, so a corrupt cross-tenant link cannot leak its CIS.
    linked_code_owned = exists(
        select(MarkingCode.id).where(
            MarkingCode.id == FbsOrderMarking.marking_code_id,
            MarkingCode.tenant_id == scope.tenant_id,
            MarkingCode.seller_id == scope.seller_id,
        )
    )
    returned = exists(
        select(FbsShipmentReversalLedger.id).where(
            FbsShipmentReversalLedger.fbs_order_id == FbsOrder.id,
            FbsShipmentReversalLedger.tenant_id == scope.tenant_id,
            FbsShipmentReversalLedger.reversed_at.is_not(None),
        )
    )
    return (
        select(FbsOrderMarking, FbsOrder, FbsSupply)
        .join(
            FbsOrder,
            FbsOrder.id == FbsOrderMarking.order_id,
        )
        .join(FbsSupply, FbsSupply.id == FbsOrder.supply_id)
        .where(
            FbsOrderMarking.tenant_id == scope.tenant_id,
            FbsOrderMarking.kind == "sgtin",
            FbsOrderMarking.meta_status != "rejected",
            or_(FbsOrderMarking.marking_code_id.is_(None), linked_code_owned),
            FbsOrder.tenant_id == scope.tenant_id,
            FbsOrder.seller_id == scope.seller_id,
            FbsOrder.marketplace == "wb",
            FbsOrder.status != "cancelled",
            FbsOrder.pick_status != "returned",
            ~returned,
            FbsSupply.tenant_id == scope.tenant_id,
            FbsSupply.seller_id == scope.seller_id,
            FbsSupply.marketplace == "wb",
            FbsSupply.delivered_at.is_not(None),
            FbsSupply.status.in_(["in_delivery", "done"]),
        )
    )


async def lock_seller(session: AsyncSession, scope: WithdrawalScope) -> None:
    # Serializes the idempotency check even when identical request IDs name
    # disjoint selections. Held only for a short local database transaction.
    seller = await session.scalar(
        select(Seller)
        .where(
            Seller.id == scope.seller_id,
            Seller.tenant_id == scope.tenant_id,
        )
        .with_for_update()
    )
    if seller is None:
        raise WithdrawalError("seller_not_found", 404)


async def get_operation(
    session: AsyncSession,
    scope: WithdrawalScope,
    operation_id: uuid.UUID,
    *,
    lock: bool = False,
) -> WithdrawalOperation:
    query = select(WithdrawalOperation).where(
        WithdrawalOperation.id == operation_id,
        WithdrawalOperation.tenant_id == scope.tenant_id,
        WithdrawalOperation.seller_id == scope.seller_id,
    )
    if lock:
        query = query.with_for_update()
    operation = await session.scalar(query)
    if operation is None:
        raise WithdrawalError("withdrawal_not_found", 404)
    return operation


async def current_items(
    session: AsyncSession,
    scope: WithdrawalScope,
    operation_id: uuid.UUID,
) -> list[WithdrawalItem]:
    return list(
        await session.scalars(
            select(WithdrawalItem)
            .where(
                WithdrawalItem.operation_id == operation_id,
                WithdrawalItem.tenant_id == scope.tenant_id,
                WithdrawalItem.seller_id == scope.seller_id,
                WithdrawalItem.holds_claim.is_(True),
            )
            .order_by(WithdrawalItem.marking_id)
        )
    )


async def registry(
    session: AsyncSession,
    scope: WithdrawalScope,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    product_id: uuid.UUID | None = None,
    only_not_withdrawn: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, object]], int]:
    if limit not in (50, 100, 250) or offset < 0:
        raise WithdrawalError("invalid_pagination", 422)
    if date_from and date_to and date_from > date_to:
        raise WithdrawalError("invalid_date_range", 422)
    query = (
        eligible_rows(scope)
        .outerjoin(
            Product,
            and_(
                Product.id == FbsOrder.product_id,
                Product.tenant_id == scope.tenant_id,
                Product.seller_id == scope.seller_id,
            ),
        )
        .outerjoin(
            WithdrawalItem,
            and_(
                WithdrawalItem.marking_id == FbsOrderMarking.id,
                WithdrawalItem.tenant_id == scope.tenant_id,
                WithdrawalItem.seller_id == scope.seller_id,
                WithdrawalItem.holds_claim.is_(True),
            ),
        )
    )
    if date_from:
        query = query.where(
            FbsSupply.delivered_at
            >= datetime.combine(
                date_from,
                time.min,
                MOSCOW,
            ).astimezone(UTC)
        )
    if date_to:
        query = query.where(
            FbsSupply.delivered_at
            < datetime.combine(
                date_to + timedelta(days=1),
                time.min,
                MOSCOW,
            ).astimezone(UTC)
        )
    if product_id:
        query = query.where(Product.id == product_id)
    if search:
        query = query.where(
            or_(
                Product.name.icontains(search, autoescape=True),
                Product.sku_code.icontains(search, autoescape=True),
                FbsOrder.wb_article.icontains(search, autoescape=True),
                FbsOrderMarking.value.icontains(search, autoescape=True),
            )
        )
    if only_not_withdrawn:
        query = query.where(or_(WithdrawalItem.id.is_(None), WithdrawalItem.state != "succeeded"))
    total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    latest_price_id = (
        select(WbOrderPriceSnapshot.id)
        .where(
            WbOrderPriceSnapshot.order_id == FbsOrder.id,
        )
        .order_by(WbOrderPriceSnapshot.revision.desc())
        .limit(1)
        .correlate(FbsOrder)
        .scalar_subquery()
    )
    query = query.outerjoin(WbOrderPriceSnapshot, WbOrderPriceSnapshot.id == latest_price_id)
    rows = await session.execute(
        query.add_columns(Product, WithdrawalItem, WbOrderPriceSnapshot)
        .order_by(
            FbsSupply.delivered_at.desc(),
            FbsOrderMarking.id,
        )
        .offset(offset)
        .limit(limit)
    )
    result: list[dict[str, object]] = []
    for marking, order, supply, product, item, price in rows:
        error = item.error if item and item.state == "failed" else None
        if item is None:
            try:
                if price is None:
                    raise WbPriceDataError(
                        "missing_price_snapshot", "WB: снимок финальной цены отсутствует"
                    )
                product_cost_from_snapshot(price)
            except WbPriceDataError as exc:
                error = {"source": "local", "code": exc.code, "message": str(exc)}
        result.append(
            {
                "row_id": marking.id,
                "delivered_at": supply.delivered_at,
                "wb_order_id": str(order.wb_order_id),
                "sku": product.sku_code if product else order.wb_article or "",
                "product_name": product.name if product else "",
                "cis": marking.value,
                "status": (
                    "withdrawn"
                    if item and item.state == "succeeded"
                    else "error"
                    if error is not None
                    else "not_withdrawn"
                ),
                "error": error,
                "operation_id": item.operation_id if item else None,
            }
        )
    return result, total
