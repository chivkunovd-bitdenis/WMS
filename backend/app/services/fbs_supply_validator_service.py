# ruff: noqa: RUF001
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
from app.services.fbs_stock_availability_service import (
    fbs_available_qty_by_product,
    fbs_stock_by_warehouse_for_products,
)
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
class SupplyStockLocationNotice:
    """I10: товар нужен на одном складе, а физически лежит (тоже) на другом.

    Не блокирует создание поставки — просто называет склад и количество
    словами прямо в preflight, а не молчит до отказа на упаковке через час.
    """

    product_id: uuid.UUID
    product_name: str
    needed_qty: int
    primary_warehouse_name: str
    primary_qty: int
    elsewhere: tuple[tuple[str, int], ...]  # (имя склада, остаток на нём)


@dataclass(frozen=True)
class SupplyPreflightResult:
    compatible: bool
    summary: SupplyPreflightSummary | None
    issues: tuple[SupplyValidationIssue, ...]
    orders: tuple[FbsOrder, ...]
    notices: tuple[SupplyStockLocationNotice, ...] = ()


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


async def _build_stock_location_notices(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    orders: list[FbsOrder],
) -> list[SupplyStockLocationNotice]:
    """I10: назвать оператору склад и количество, если товар физически лежит
    не (только) там, куда привязан заказ — до создания поставки, а не после
    отказа на упаковке через час. Ничего не блокирует: `insufficient_stock` в
    `_per_order_issues` уже отработал по остатку тенанта в целом, тут — только
    пояснение «откуда реально возьмут».
    """
    needed_by_product: dict[uuid.UUID, int] = {}
    primary_warehouse_by_product: dict[uuid.UUID, uuid.UUID] = {}
    product_name_by_id: dict[uuid.UUID, str] = {}
    for order in orders:
        if order.product_id is None or order.warehouse_id is None:
            continue
        needed_by_product[order.product_id] = needed_by_product.get(order.product_id, 0) + 1
        primary_warehouse_by_product.setdefault(order.product_id, order.warehouse_id)
        if order.product is not None:
            product_name_by_id[order.product_id] = order.product.name
    if not needed_by_product:
        return []

    breakdown = await fbs_stock_by_warehouse_for_products(
        session, tenant_id, list(needed_by_product)
    )
    relevant_warehouse_ids: set[uuid.UUID] = set(primary_warehouse_by_product.values())
    for by_wh in breakdown.values():
        relevant_warehouse_ids.update(by_wh)
    if not relevant_warehouse_ids:
        return []
    name_rows = await session.execute(
        select(Warehouse.id, Warehouse.name).where(Warehouse.id.in_(relevant_warehouse_ids))
    )
    wh_names = {wid: name for wid, name in name_rows.all()}

    notices: list[SupplyStockLocationNotice] = []
    for product_id, needed in needed_by_product.items():
        primary_wh = primary_warehouse_by_product[product_id]
        by_wh = breakdown.get(product_id, {})
        primary_qty = by_wh.get(primary_wh, 0)
        if primary_qty >= needed:
            continue
        elsewhere = tuple(
            (wh_names.get(wh_id, "Неизвестный склад"), qty)
            for wh_id, qty in sorted(by_wh.items(), key=lambda kv: -kv[1])
            if wh_id != primary_wh and qty > 0
        )
        if not elsewhere:
            continue
        notices.append(
            SupplyStockLocationNotice(
                product_id=product_id,
                product_name=product_name_by_id.get(product_id, "Товар"),
                needed_qty=needed,
                primary_warehouse_name=wh_names.get(primary_wh, "Склад не найден"),
                primary_qty=primary_qty,
                elsewhere=elsewhere,
            )
        )
    return notices


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
    return {
        "compatible": result.compatible,
        "summary": summary_out,
        "issues": [
            {
                "order_id": str(issue.order_id),
                "code": issue.code,
                "message": issue.message,
            }
            for issue in result.issues
        ],
        "notices": [
            {
                "product_id": str(n.product_id),
                "product_name": n.product_name,
                "needed_qty": n.needed_qty,
                "primary_warehouse_name": n.primary_warehouse_name,
                "primary_qty": n.primary_qty,
                "elsewhere": [
                    {"warehouse_name": name, "qty": qty} for name, qty in n.elsewhere
                ],
            }
            for n in result.notices
        ],
        "server_now": now.isoformat(),
    }


async def validate_supply_composition(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_ids: list[uuid.UUID],
    *,
    planned_delivery_type: str,
    for_update: bool = False,
    server_now: datetime | None = None,
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
    compatible = len(issues) == 0
    # I10: считаем пояснения, только если состав уже совместим — иначе на
    # заблокированном составе просто лишний шум поверх настоящей причины отказа.
    notices = (
        await _build_stock_location_notices(session, tenant_id, orders) if compatible else []
    )
    return SupplyPreflightResult(
        compatible=compatible,
        summary=summary,
        issues=tuple(issues),
        orders=tuple(orders),
        notices=tuple(notices),
    )
