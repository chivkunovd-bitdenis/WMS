"""Shared FBS supply composition validator for selection, preflight, and create-under-lock."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_order import (
    FBS_ORDER_STATUS_NEW,
    FbsOrder,
)
from app.models.seller import Seller
from app.models.tenant_wb_mp_warehouse import TenantWbMpWarehouse
from app.models.warehouse import Warehouse
from app.services.fbs_stock_availability_service import fbs_available_qty_by_product
from app.services.fbs_worklist_service import compute_selection_blockers


class FbsSupplyValidationError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SupplyValidationIssue:
    order_id: uuid.UUID
    code: str
    message: str


@dataclass(frozen=True)
class SupplyPreflightSummary:
    seller_id: uuid.UUID
    seller_name: str
    wb_warehouse_id: int
    wb_warehouse_name: str | None
    wms_warehouse_id: uuid.UUID
    wms_warehouse_name: str
    buyer_type: str
    cargo_type: str
    orders_count: int
    required_marking_count: int
    pvz_allowed_count: int
    pvz_blocked_count: int
    nearest_deadline_at: datetime


@dataclass(frozen=True)
class SupplyPreflightResult:
    compatible: bool
    summary: SupplyPreflightSummary | None
    issues: tuple[SupplyValidationIssue, ...]
    orders: tuple[FbsOrder, ...]
    stock: SupplyStockPreflight


@dataclass(frozen=True)
class SupplyStockLine:
    product_id: uuid.UUID
    product_name: str
    required: int
    current: int
    total: int
    shortage: int
    source_warehouse_id: uuid.UUID | None = None
    source_warehouse_name: str | None = None


@dataclass(frozen=True)
class SupplyStockPreflight:
    compatible: bool
    recommended_warehouse_id: uuid.UUID | None
    recommended_warehouse_name: str | None
    warning_lines: tuple[SupplyStockLine, ...]
    blocking_lines: tuple[SupplyStockLine, ...]


_BLOCKER_TO_ISSUE: dict[str, tuple[str, str]] = {
    "order_cancelled": ("order_cancelled", "Заказ отменён или брак."),
    "already_in_supply": ("already_in_supply", "Заказ уже в поставке."),
    "product_not_mapped": ("product_not_mapped", "Товар не сопоставлен с карточкой."),
    "warehouse_unmapped": ("warehouse_unmapped", "Склад WB не привязан к WMS."),
    "insufficient_stock": ("insufficient_stock", "Недостаточно неупакованного остатка."),
    "deadline_passed": ("deadline_passed", "Срок сборки истёк."),
    "order_external_processing": ("order_bad_status", "Заказ уже ушёл в кабинете WB."),
}


def _buyer_type(order: FbsOrder) -> str:
    return "legal" if order.is_legal else "individual"


def _order_requires_marking(order: FbsOrder) -> bool:
    return bool(order.required_meta_json)


async def load_orders_for_validation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_ids: list[uuid.UUID],
    *,
    for_update: bool = False,
) -> list[FbsOrder]:
    if not order_ids:
        raise FbsSupplyValidationError("empty_order_set")
    unique_ids = list(dict.fromkeys(order_ids))
    stmt = (
        select(FbsOrder)
        .where(
            FbsOrder.tenant_id == tenant_id,
            FbsOrder.id.in_(unique_ids),
        )
        .options(
            selectinload(FbsOrder.product),
            selectinload(FbsOrder.seller),
            selectinload(FbsOrder.warehouse),
            selectinload(FbsOrder.reservation),
        )
    )
    if for_update:
        # `create_supply_from_orders` preloads these rows for the preview.  A
        # concurrent request can commit while this request waits on FOR UPDATE;
        # refresh the existing ORM identities after the lock so validation sees
        # the winner's `in_supply` status rather than its own stale preview.
        stmt = (
            stmt.order_by(FbsOrder.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    result = await session.execute(stmt)
    orders = list(result.scalars().all())
    if len(orders) != len(unique_ids):
        raise FbsSupplyValidationError("order_not_found")
    by_id = {order.id: order for order in orders}
    return [by_id[oid] for oid in unique_ids]


async def _availability_by_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    orders: list[FbsOrder],
) -> dict[uuid.UUID, int]:
    by_wh_product: dict[tuple[uuid.UUID, uuid.UUID], list[uuid.UUID]] = {}
    for order in orders:
        if order.warehouse_id is None or order.product_id is None:
            continue
        key = (order.warehouse_id, order.product_id)
        by_wh_product.setdefault(key, []).append(order.id)
    out: dict[uuid.UUID, int] = {}
    for (warehouse_id, product_id), order_ids in by_wh_product.items():
        avail_map = await fbs_available_qty_by_product(
            session,
            tenant_id,
            warehouse_id,
            [product_id],
            exclude_fbs_order_ids=frozenset(order_ids),
        )
        qty = int(avail_map.get(product_id, 0))
        for oid in order_ids:
            out[oid] = qty
    return out


async def _stock_preflight(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    orders: list[FbsOrder],
    *,
    selected_warehouse_id: uuid.UUID | None = None,
) -> SupplyStockPreflight:
    required: dict[uuid.UUID, int] = {}
    products: dict[uuid.UUID, Any] = {}
    for order in orders:
        if order.product_id is not None:
            quantity = int(order.reservation.quantity) if order.reservation is not None else 1
            required[order.product_id] = required.get(order.product_id, 0) + quantity
            if order.product is not None:
                products[order.product_id] = order.product
    warehouses = list((await session.execute(
        select(Warehouse).where(
            Warehouse.tenant_id == tenant_id, Warehouse.is_operational.is_(True)
        ).order_by(Warehouse.id)
    )).scalars().all())
    availability: dict[uuid.UUID, dict[uuid.UUID, int]] = {}
    for warehouse in warehouses:
        # Selected orders already consume their own reservations. Exclude
        # those reservations so preflight does not subtract them twice.
        selected_order_ids = frozenset(
            order.id for order in orders if order.warehouse_id == warehouse.id
        )
        availability[warehouse.id] = await fbs_available_qty_by_product(
            session,
            tenant_id,
            warehouse.id,
            list(required),
            exclude_fbs_order_ids=selected_order_ids or None,
        )
    current_id = selected_warehouse_id or (orders[0].warehouse_id if orders else None)
    def coverage(warehouse: Warehouse) -> int:
        return sum(availability[warehouse.id].get(pid, 0) >= qty for pid, qty in required.items())
    recommended = max(warehouses, key=lambda w: (coverage(w), w.id == current_id), default=None)
    warning: list[SupplyStockLine] = []
    blocking: list[SupplyStockLine] = []
    for pid, qty in required.items():
        current = availability.get(current_id, {}).get(pid, 0) if current_id else 0
        total = sum(values.get(pid, 0) for values in availability.values())
        shortage = max(qty - total, 0)
        source = max(
            (
                w for w in warehouses
                if w.id != current_id and availability[w.id].get(pid, 0) > 0
            ),
            key=lambda w: availability[w.id].get(pid, 0),
            default=None,
        )
        line = SupplyStockLine(
            pid, getattr(products.get(pid), "name", "Товар"), qty, current, total, shortage,
            source.id if source else None, source.name if source else None,
        )
        if shortage:
            blocking.append(line)
        elif current < qty:
            warning.append(line)
    return SupplyStockPreflight(
        not blocking,
        recommended.id if recommended else None,
        recommended.name if recommended else None,
        tuple(warning),
        tuple(blocking),
    )


async def _wb_warehouse_name(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    wb_warehouse_id: int,
) -> str | None:
    stmt = select(TenantWbMpWarehouse.name).where(
        TenantWbMpWarehouse.tenant_id == tenant_id,
        TenantWbMpWarehouse.wb_warehouse_id == wb_warehouse_id,
    )
    return cast(str | None, await session.scalar(stmt))


def _cross_order_issues(orders: list[FbsOrder]) -> list[SupplyValidationIssue]:
    if not orders:
        return []
    first = orders[0]
    issues: list[SupplyValidationIssue] = []
    ref_seller = first.seller_id
    ref_wb_wh = first.wb_warehouse_id
    ref_wms_wh = first.warehouse_id
    ref_buyer = _buyer_type(first)
    ref_cargo = first.cargo_type or "unknown"
    for order in orders[1:]:
        if order.seller_id != ref_seller:
            issues.append(
                SupplyValidationIssue(
                    order_id=order.id,
                    code="different_seller",
                    message="Заказы принадлежат разным селлерам.",
                )
            )
        if order.wb_warehouse_id != ref_wb_wh:
            issues.append(
                SupplyValidationIssue(
                    order_id=order.id,
                    code="different_wb_warehouse",
                    message="Заказы относятся к разным складам WB.",
                )
            )
        if order.warehouse_id != ref_wms_wh:
            issues.append(
                SupplyValidationIssue(
                    order_id=order.id,
                    code="different_wms_warehouse",
                    message="Заказы относятся к разным WMS-складам.",
                )
            )
        if _buyer_type(order) != ref_buyer:
            issues.append(
                SupplyValidationIssue(
                    order_id=order.id,
                    code="legal_type_mismatch",
                    message="Нельзя смешивать B2C и B2B заказы в одной поставке.",
                )
            )
        cargo = order.cargo_type or "unknown"
        if cargo != ref_cargo:
            issues.append(
                SupplyValidationIssue(
                    order_id=order.id,
                    code="different_cargo_type",
                    message="Заказы имеют разный тип груза.",
                )
            )
    return issues


def _per_order_issues(
    orders: list[FbsOrder],
    *,
    availability: dict[uuid.UUID, int],
    server_now: datetime,
    planned_delivery_type: str,
) -> list[SupplyValidationIssue]:
    issues: list[SupplyValidationIssue] = []
    for order in orders:
        if order.status != FBS_ORDER_STATUS_NEW:
            issues.append(
                SupplyValidationIssue(
                    order_id=order.id,
                    code="order_bad_status",
                    message=f"Заказ №{order.wb_order_id} недоступен для добавления.",
                )
            )
        avail = availability.get(order.id, 0)
        for blocker in compute_selection_blockers(
            order,
            available_unpacked=avail,
            server_now=server_now,
        ):
            code_raw = blocker["code"]
            mapped = _BLOCKER_TO_ISSUE.get(code_raw)
            if mapped is None:
                code, message = "order_incompatible", blocker["message"]
            else:
                code, message = mapped
            issues.append(
                SupplyValidationIssue(
                    order_id=order.id,
                    code=code,
                    message=message,
                )
            )
    return issues


async def _build_summary(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    orders: list[FbsOrder],
) -> SupplyPreflightSummary:
    first = orders[0]
    seller: Seller | None = first.seller
    warehouse: Warehouse | None = first.warehouse
    wb_wh_id = int(first.wb_warehouse_id or 0)
    wb_name = await _wb_warehouse_name(session, tenant_id, wb_wh_id) if wb_wh_id else None
    required_marking = sum(1 for o in orders if _order_requires_marking(o))
    nearest = min(o.deadline_at for o in orders)
    return SupplyPreflightSummary(
        seller_id=first.seller_id,
        seller_name=seller.name if seller else "Селлер не найден",
        wb_warehouse_id=wb_wh_id,
        wb_warehouse_name=wb_name,
        wms_warehouse_id=first.warehouse_id or uuid.UUID(int=0),
        wms_warehouse_name=warehouse.name if warehouse else "Склад не найден",
        buyer_type=_buyer_type(first),
        cargo_type=first.cargo_type or "unknown",
        orders_count=len(orders),
        required_marking_count=required_marking,
        pvz_allowed_count=len(orders),
        pvz_blocked_count=0,
        nearest_deadline_at=nearest,
    )


def preflight_to_dict(
    result: SupplyPreflightResult,
    *,
    server_now: datetime | None = None,
) -> dict[str, Any]:
    now = server_now or datetime.now(tz=UTC)
    summary_out: dict[str, Any] | None = None
    if result.summary is not None:
        s = result.summary
        summary_out = {
            "seller": {"id": str(s.seller_id), "name": s.seller_name},
            "wb_warehouse": {"id": s.wb_warehouse_id, "name": s.wb_warehouse_name},
            "wms_warehouse": {"id": str(s.wms_warehouse_id), "name": s.wms_warehouse_name},
            "buyer_type": s.buyer_type,
            "cargo_type": s.cargo_type,
            "orders_count": s.orders_count,
            "required_marking_count": s.required_marking_count,
            "pvz_allowed_count": s.pvz_allowed_count,
            "pvz_blocked_count": s.pvz_blocked_count,
            "nearest_deadline_at": s.nearest_deadline_at.isoformat(),
        }
    stock = result.stock
    def stock_line(line: SupplyStockLine) -> dict[str, Any]:
        return {"product_id": str(line.product_id), "product_name": line.product_name,
                "required": line.required, "current": line.current, "total": line.total,
                "shortage": line.shortage,
                "source_warehouse": (
                    {"id": str(line.source_warehouse_id), "name": line.source_warehouse_name}
                    if line.source_warehouse_id else None
                )}
    return {
        "compatible": result.compatible and stock.compatible,
        "summary": summary_out,
        "issues": [
            {
                "order_id": str(issue.order_id),
                "code": issue.code,
                "message": issue.message,
            }
            for issue in result.issues
        ],
        "server_now": now.isoformat(),
        "stock_preflight": {
            "compatible": stock.compatible,
            "recommended_warehouse": (
                {
                    "id": str(stock.recommended_warehouse_id),
                    "name": stock.recommended_warehouse_name,
                }
                if stock.recommended_warehouse_id else None
            ),
            "warning_lines": [stock_line(line) for line in stock.warning_lines],
            "blocking_lines": [stock_line(line) for line in stock.blocking_lines],
        },
    }


async def validate_supply_composition(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_ids: list[uuid.UUID],
    *,
    planned_delivery_type: str,
    for_update: bool = False,
    server_now: datetime | None = None,
    selected_warehouse_id: uuid.UUID | None = None,
) -> SupplyPreflightResult:
    if planned_delivery_type not in {"warehouse_sc", "pvz"}:
        raise FbsSupplyValidationError("invalid_delivery_type")
    now = server_now or datetime.now(tz=UTC)
    orders = await load_orders_for_validation(
        session,
        tenant_id,
        order_ids,
        for_update=for_update,
    )
    availability = await _availability_by_order(session, tenant_id, orders)
    issues = [
        *_cross_order_issues(orders),
        *_per_order_issues(
            orders,
            availability=availability,
            server_now=now,
            planned_delivery_type=planned_delivery_type,
        ),
    ]
    summary = await _build_summary(session, tenant_id, orders)
    stock = await _stock_preflight(
        session,
        tenant_id,
        orders,
        selected_warehouse_id=selected_warehouse_id,
    )
    compatible = len(issues) == 0 and stock.compatible
    return SupplyPreflightResult(
        compatible=compatible,
        summary=summary,
        issues=tuple(issues),
        orders=tuple(orders),
        stock=stock,
    )
