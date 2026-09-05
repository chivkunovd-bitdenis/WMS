"""Cancelled FBS orders that still require a physical warehouse action."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_order import (
    FBS_ORDER_STATUS_CANCELLED,
    STICKER_STATUS_APPLIED,
    STICKER_STATUS_PRINT_OPENED,
    FbsOrder,
)
from app.models.fbs_order_pick import FbsOrderPick
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_packing_box import FbsPackingBox, FbsPackingBoxItem
from app.models.fbs_print_asset import PRINT_ASSET_KIND_ORDER_STICKER, FbsPrintAsset
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_DONE,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FbsSupply,
)
from app.models.fbs_trbx import FbsTrbx
from app.models.warehouse_box import WarehouseBox
from app.services.wb_marketplace_orders_service import CANCEL_LIKE_WB_STATUSES


@dataclass(frozen=True)
class CancelledAfterPackPage:
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


_CANCELLATION_REASONS = {
    "canceled_by_client": "Заказ отменён покупателем",
    "cancelled_by_client": "Заказ отменён покупателем",
    "declined_by_client": "Покупатель отказался от заказа",
    "canceled_by_carrier": "Заказ отменён перевозчиком",
    "cancelled_by_carrier": "Заказ отменён перевозчиком",
    "cancel": "Заказ отменён",
    "canceled": "Заказ отменён",
    "cancelled": "Заказ отменён",
}


def cancellation_code(order: FbsOrder) -> str:
    for raw in (order.supplier_status, order.wb_status):
        normalized = (raw or "").strip().lower()
        if normalized in CANCEL_LIKE_WB_STATUSES:
            return normalized
    return "cancelled"


def cancellation_reason(order: FbsOrder) -> str:
    return _CANCELLATION_REASONS.get(cancellation_code(order), "Заказ отменён")


def cancelled_operation_message(order: FbsOrder, action: str) -> str:
    return f"{cancellation_reason(order)}, {action}."


def _assembly_trace_condition() -> Any:
    active_pick = exists(
        select(FbsOrderPick.id).where(
            FbsOrderPick.fbs_order_id == FbsOrder.id,
            FbsOrderPick.undone_at.is_(None),
        )
    )
    active_pack = exists(
        select(FbsPackagingFulfillment.id).where(
            FbsPackagingFulfillment.fbs_order_id == FbsOrder.id,
            FbsPackagingFulfillment.undone_at.is_(None),
        )
    )
    printed_sticker = exists(
        select(FbsPrintAsset.id).where(
            FbsPrintAsset.fbs_order_id == FbsOrder.id,
            FbsPrintAsset.kind == PRINT_ASSET_KIND_ORDER_STICKER,
            or_(
                FbsPrintAsset.print_opened_at.is_not(None),
                FbsPrintAsset.applied_at.is_not(None),
            ),
        )
    )
    return or_(
        FbsOrder.picked_at.is_not(None),
        FbsOrder.packed_at.is_not(None),
        FbsOrder.sticker_applied_at.is_not(None),
        FbsOrder.sticker_status.in_((STICKER_STATUS_PRINT_OPENED, STICKER_STATUS_APPLIED)),
        active_pick,
        active_pack,
        printed_sticker,
    )


async def order_belonged_to_supply(
    session: AsyncSession,
    order: FbsOrder,
    supply: FbsSupply,
) -> bool:
    if order.tenant_id != supply.tenant_id or order.seller_id != supply.seller_id:
        return False
    if order.supply_id == supply.id:
        return True
    if order.wb_supply_id and order.wb_supply_id == supply.wb_supply_id:
        return True
    if await session.scalar(
        select(FbsOrderPick.id)
        .where(
            FbsOrderPick.fbs_order_id == order.id,
            FbsOrderPick.fbs_supply_id == supply.id,
        )
        .limit(1)
    ):
        return True
    if await session.scalar(
        select(FbsPackingBoxItem.id)
        .join(FbsPackingBox, FbsPackingBox.id == FbsPackingBoxItem.box_id)
        .where(
            FbsPackingBoxItem.fbs_order_id == order.id,
            FbsPackingBox.supply_id == supply.id,
        )
        .limit(1)
    ):
        return True
    return bool(
        supply.packaging_task_id
        and await session.scalar(
            select(FbsPackagingFulfillment.id)
            .where(
                FbsPackagingFulfillment.fbs_order_id == order.id,
                FbsPackagingFulfillment.packaging_task_id == supply.packaging_task_id,
            )
            .limit(1)
        )
    )


def _supply_filter_condition(supply: FbsSupply) -> Any:
    pick_in_supply = exists(
        select(FbsOrderPick.id).where(
            FbsOrderPick.fbs_order_id == FbsOrder.id,
            FbsOrderPick.fbs_supply_id == supply.id,
        )
    )
    box_in_supply = exists(
        select(FbsPackingBoxItem.id)
        .join(FbsPackingBox, FbsPackingBox.id == FbsPackingBoxItem.box_id)
        .where(
            FbsPackingBoxItem.fbs_order_id == FbsOrder.id,
            FbsPackingBox.supply_id == supply.id,
        )
    )
    conditions = [
        FbsOrder.supply_id == supply.id,
        pick_in_supply,
        box_in_supply,
    ]
    if supply.packaging_task_id is not None:
        conditions.append(
            exists(
                select(FbsPackagingFulfillment.id).where(
                    FbsPackagingFulfillment.fbs_order_id == FbsOrder.id,
                    FbsPackagingFulfillment.packaging_task_id == supply.packaging_task_id,
                )
            )
        )
    if supply.wb_supply_id:
        conditions.append(
            and_(
                FbsOrder.seller_id == supply.seller_id,
                FbsOrder.wb_supply_id == supply.wb_supply_id,
            )
        )
    return or_(*conditions)


async def _load_supplemental_rows(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    orders: list[FbsOrder],
) -> tuple[
    dict[uuid.UUID, datetime],
    dict[uuid.UUID, uuid.UUID],
    dict[uuid.UUID, datetime],
    dict[uuid.UUID, uuid.UUID],
    dict[uuid.UUID, list[dict[str, Any]]],
    dict[uuid.UUID, FbsSupply],
]:
    order_ids = [order.id for order in orders]
    printed_at: dict[uuid.UUID, datetime] = {}
    pick_supply: dict[uuid.UUID, uuid.UUID] = {}
    fulfilled_at: dict[uuid.UUID, datetime] = {}
    pack_task: dict[uuid.UUID, uuid.UUID] = {}
    # Заказ может лежать сразу в нескольких коробах (WMS-355), поэтому здесь
    # список, а не одно значение: словарь «короб по заказу» показал бы в отчёте
    # последний короб из семи, а остальные молча потерял.
    cargo: dict[uuid.UUID, list[dict[str, Any]]] = {}
    if not order_ids:
        return printed_at, pick_supply, fulfilled_at, pack_task, cargo, {}

    print_rows = (
        await session.execute(
            select(
                FbsPrintAsset.fbs_order_id,
                FbsPrintAsset.print_opened_at,
                FbsPrintAsset.applied_at,
            ).where(
                FbsPrintAsset.tenant_id == tenant_id,
                FbsPrintAsset.fbs_order_id.in_(order_ids),
                FbsPrintAsset.kind == PRINT_ASSET_KIND_ORDER_STICKER,
            )
        )
    ).all()
    for order_id, opened_at, applied_at in print_rows:
        moments = [moment for moment in (opened_at, applied_at) if moment is not None]
        if moments:
            printed_at[order_id] = max(moments)

    pick_rows = (
        await session.execute(
            select(
                FbsOrderPick.fbs_order_id,
                FbsOrderPick.fbs_supply_id,
                FbsOrderPick.picked_at,
            )
            .where(FbsOrderPick.fbs_order_id.in_(order_ids))
            .order_by(FbsOrderPick.picked_at.desc())
        )
    ).all()
    for order_id, supply_id, picked_at in pick_rows:
        pick_supply.setdefault(order_id, supply_id)
        if order_id not in fulfilled_at:
            fulfilled_at[order_id] = picked_at

    fulfillment_rows = (
        await session.execute(
            select(
                FbsPackagingFulfillment.fbs_order_id,
                FbsPackagingFulfillment.packaging_task_id,
                FbsPackagingFulfillment.fulfilled_at,
            )
            .where(FbsPackagingFulfillment.fbs_order_id.in_(order_ids))
            .order_by(FbsPackagingFulfillment.fulfilled_at.desc())
        )
    ).all()
    for order_id, task_id, packed_at in fulfillment_rows:
        pack_task.setdefault(order_id, task_id)
        previous = fulfilled_at.get(order_id)
        if previous is None or packed_at > previous:
            fulfilled_at[order_id] = packed_at

    box_rows = (
        await session.execute(
            select(
                FbsPackingBoxItem.fbs_order_id,
                FbsPackingBox,
                WarehouseBox,
                FbsTrbx,
            )
            .join(FbsPackingBox, FbsPackingBox.id == FbsPackingBoxItem.box_id)
            .join(WarehouseBox, WarehouseBox.id == FbsPackingBox.warehouse_box_id)
            .outerjoin(FbsTrbx, FbsTrbx.id == FbsPackingBox.trbx_id)
            .where(
                FbsPackingBoxItem.tenant_id == tenant_id,
                FbsPackingBoxItem.fbs_order_id.in_(order_ids),
            )
        )
    ).all()
    box_supply: dict[uuid.UUID, uuid.UUID] = {}
    for order_id, box, warehouse_box, trbx in sorted(box_rows, key=lambda row: row[1].box_number):
        box_supply[order_id] = box.supply_id
        cargo.setdefault(order_id, []).append(
            {
                "box_id": str(box.id),
                "box_number": box.box_number,
                "box_barcode": warehouse_box.internal_barcode,
                "trbx_id": str(trbx.id) if trbx is not None else None,
                "wb_trbx_id": trbx.wb_trbx_id if trbx is not None else None,
            }
        )

    supply_ids = {
        supply_id
        for order in orders
        for supply_id in (
            box_supply.get(order.id),
            order.supply_id,
            pick_supply.get(order.id),
        )
        if supply_id is not None
    }
    task_ids = set(pack_task.values())
    supply_stmt = select(FbsSupply).where(FbsSupply.tenant_id == tenant_id)
    if supply_ids or task_ids:
        supply_stmt = supply_stmt.where(
            or_(
                FbsSupply.id.in_(supply_ids),
                FbsSupply.packaging_task_id.in_(task_ids),
            )
        )
        supplies = list((await session.execute(supply_stmt)).scalars())
    else:
        supplies = []
    by_id = {supply.id: supply for supply in supplies}
    by_task = {
        supply.packaging_task_id: supply
        for supply in supplies
        if supply.packaging_task_id is not None
    }

    unresolved = [
        order
        for order in orders
        if not any(
            (
                box_supply.get(order.id) in by_id,
                order.supply_id in by_id,
                pick_supply.get(order.id) in by_id,
                pack_task.get(order.id) in by_task,
            )
        )
        and order.wb_supply_id
    ]
    if unresolved:
        wb_conditions = [
            and_(
                FbsSupply.seller_id == order.seller_id,
                FbsSupply.wb_supply_id == order.wb_supply_id,
            )
            for order in unresolved
        ]
        wb_supplies = list(
            (
                await session.execute(
                    select(FbsSupply).where(
                        FbsSupply.tenant_id == tenant_id,
                        or_(*wb_conditions),
                    )
                )
            ).scalars()
        )
        for supply in wb_supplies:
            by_id[supply.id] = supply
            if supply.packaging_task_id is not None:
                by_task[supply.packaging_task_id] = supply

    resolved_supply: dict[uuid.UUID, FbsSupply] = {}
    for order in orders:
        candidate_ids = (
            box_supply.get(order.id),
            order.supply_id,
            pick_supply.get(order.id),
        )
        current_supply: FbsSupply | None = next(
            (by_id[item] for item in candidate_ids if item in by_id), None
        )
        if current_supply is None and pack_task.get(order.id) in by_task:
            current_supply = by_task[pack_task[order.id]]
        if current_supply is None and order.wb_supply_id:
            current_supply = next(
                (
                    item
                    for item in by_id.values()
                    if item.seller_id == order.seller_id and item.wb_supply_id == order.wb_supply_id
                ),
                None,
            )
        if current_supply is not None:
            resolved_supply[order.id] = current_supply
    return printed_at, pick_supply, fulfilled_at, pack_task, cargo, resolved_supply


async def fetch_cancelled_after_pack_page(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None = None,
    supply_id: uuid.UUID | None = None,
    cancelled_from: datetime | None = None,
    cancelled_to: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> CancelledAfterPackPage:
    if cancelled_from is not None and cancelled_to is not None and cancelled_from > cancelled_to:
        raise ValueError("invalid_period")

    conditions = [
        FbsOrder.tenant_id == tenant_id,
        FbsOrder.status == FBS_ORDER_STATUS_CANCELLED,
        _assembly_trace_condition(),
    ]
    if seller_id is not None:
        conditions.append(FbsOrder.seller_id == seller_id)
    if cancelled_from is not None:
        conditions.append(FbsOrder.updated_at >= cancelled_from)
    if cancelled_to is not None:
        conditions.append(FbsOrder.updated_at <= cancelled_to)
    if supply_id is not None:
        supply = await session.scalar(
            select(FbsSupply).where(
                FbsSupply.id == supply_id,
                FbsSupply.tenant_id == tenant_id,
            )
        )
        if supply is None:
            raise ValueError("supply_not_found")
        conditions.append(_supply_filter_condition(supply))

    total = int(
        await session.scalar(select(func.count()).select_from(FbsOrder).where(*conditions)) or 0
    )
    orders = list(
        (
            await session.execute(
                select(FbsOrder)
                .where(*conditions)
                .options(selectinload(FbsOrder.seller), selectinload(FbsOrder.product))
                .order_by(FbsOrder.updated_at.desc(), FbsOrder.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars()
    )
    printed_at, _pick_supply, trace_at, _pack_task, cargo, supplies = await _load_supplemental_rows(
        session, tenant_id, orders
    )

    items: list[dict[str, Any]] = []
    for order in orders:
        supply = supplies.get(order.id)
        sticker_printed_at = printed_at.get(order.id) or order.sticker_applied_at
        assembled_at = order.packed_at or order.picked_at or trace_at.get(order.id)
        if assembled_at is None:
            assembled_at = sticker_printed_at
        product_name = (
            order.product.name if order.product is not None else (order.wb_article or "Товар")
        )
        product_article = order.product.sku_code if order.product is not None else order.wb_article
        items.append(
            {
                "order_id": str(order.id),
                "wb_order_id": int(order.wb_order_id),
                "product": {
                    "id": str(order.product_id) if order.product_id is not None else None,
                    "name": product_name,
                    "article": product_article,
                    "wb_article": order.wb_article,
                    "size": order.product.wb_size if order.product is not None else None,
                },
                "seller": {"id": str(order.seller_id), "name": order.seller.name},
                "supply": (
                    {
                        "id": str(supply.id),
                        "wb_supply_id": supply.wb_supply_id,
                        "name": supply.name,
                        "status": supply.status,
                    }
                    if supply is not None
                    else {
                        "id": None,
                        "wb_supply_id": order.wb_supply_id,
                        "name": None,
                        "status": None,
                    }
                ),
                "cargo_places": cargo.get(order.id, []),
                "assembled_at": assembled_at,
                "picked_at": order.picked_at,
                "packed_at": order.packed_at,
                "cancelled_at": order.updated_at,
                "cancellation_code": cancellation_code(order),
                "cancellation_reason": cancellation_reason(order),
                "sticker_printed": sticker_printed_at is not None
                or order.sticker_status in {STICKER_STATUS_PRINT_OPENED, STICKER_STATUS_APPLIED},
                "sticker_printed_at": sticker_printed_at,
                "supply_departed": (
                    supply.delivered_at is not None
                    or supply.status in {FBS_SUPPLY_STATUS_IN_DELIVERY, FBS_SUPPLY_STATUS_DONE}
                    if supply is not None
                    else None
                ),
            }
        )
    return CancelledAfterPackPage(items=items, total=total, limit=limit, offset=offset)


__all__ = [
    "CancelledAfterPackPage",
    "cancellation_code",
    "cancellation_reason",
    "cancelled_operation_message",
    "fetch_cancelled_after_pack_page",
    "order_belonged_to_supply",
]
