# ruff: noqa: RUF001
"""FBS supply workspace read model — stage, progress, blockers, cargo places."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_order import (
    META_STATUS_ACCEPTED,
    META_STATUS_ALLOWED_WITHOUT_CHECK,
    PACK_STATUS_PACKED,
    PICK_STATUS_PICKED,
    STICKER_STATUS_APPLIED,
    STICKER_STATUS_PRINT_OPENED,
    STICKER_STATUS_READY,
    FbsOrder,
)
from app.models.fbs_packing_box import FbsPackingBox, FbsPackingBoxItem
from app.models.fbs_print_asset import (
    PRINT_ASSET_KIND_CARGO_PLACE_QR,
    PRINT_ASSET_KIND_SUPPLY_QR,
    PRINT_ASSET_STATUS_ERROR,
    PRINT_ASSET_STATUS_READY,
    FbsPrintAsset,
)
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_PVZ,
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_DONE,
    FBS_SUPPLY_STATUS_DRAFT,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.fbs_trbx import FbsTrbx
from app.models.tenant_wb_mp_warehouse import TenantWbMpWarehouse
from app.services.fbs_tracking_service import (
    build_partial_rejection_summary,
    build_tracking_summary,
    is_tracking_sync_stale,
)
from app.services.fbs_worklist_service import build_worklist_items, print_asset_content_url


class FbsWorkspaceError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class WorkspaceProgress:
    picked: int
    packed: int
    metadata_ready: int
    stickers_ready: int
    total: int


async def get_supply_workspace(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> dict[str, Any]:
    supply = await _load_supply_graph(session, tenant_id, supply_id)
    if supply is None:
        raise FbsWorkspaceError("supply_not_found")
    server_now = datetime.now(tz=UTC)
    orders = list(supply.orders)
    worklist_items = await build_worklist_items(session, tenant_id, orders, server_now=server_now)
    progress = _compute_progress(orders)
    packing_boxes, unassigned_order_ids = await _build_packing_boxes(
        session, tenant_id, supply, orders
    )
    stage = _compute_stage(
        supply,
        orders,
        progress,
        has_packing_boxes=bool(packing_boxes),
        unassigned_order_ids=unassigned_order_ids,
    )
    blockers = _compute_workspace_blockers(
        supply,
        orders,
        stage,
        progress,
        has_packing_boxes=bool(packing_boxes),
        unassigned_order_ids=unassigned_order_ids,
    )
    cargo_places = await _build_cargo_places(session, tenant_id, supply)
    wb_name = await _wb_warehouse_name(session, tenant_id, orders)
    nearest_deadline = min((o.deadline_at for o in orders), default=server_now)
    barcode_asset = _map_print_asset(supply.barcode_asset)
    tracking_summary = None
    partial_rejection = None
    wb_sync_stale = False
    if stage == "tracking":
        tracking_summary = build_tracking_summary(supply, orders, server_now=server_now)
        partial_rejection = build_partial_rejection_summary(orders, server_now=server_now)
        wb_sync_stale = is_tracking_sync_stale(supply.last_wb_sync_at, server_now=server_now)
    return {
        "supply": {
            "id": str(supply.id),
            "wb_supply_id": supply.wb_supply_id,
            "name": supply.name,
            "status": supply.status,
            "delivery_type": supply.delivery_type,
            "seller": {
                "id": str(supply.seller_id),
                "name": supply.seller.name if supply.seller else "Селлер не найден",
            },
            "wb_warehouse": {
                "id": int(orders[0].wb_warehouse_id) if orders and orders[0].wb_warehouse_id else 0,
                "name": wb_name,
            },
            "wms_warehouse": {
                "id": str(supply.warehouse_id),
                "name": supply.warehouse.name if supply.warehouse else "Склад не найден",
            },
            "planned_destination": _planned_destination(supply),
            "nearest_deadline_at": nearest_deadline.isoformat(),
            "packaging_task_id": (
                str(supply.packaging_task_id) if supply.packaging_task_id else None
            ),
            "barcode_asset": barcode_asset,
            "operator_finished_at": (
                supply.operator_finished_at.isoformat() if supply.operator_finished_at else None
            ),
        },
        "stage": stage,
        "progress": {
            "picked": progress.picked,
            "packed": progress.packed,
            "metadata_ready": progress.metadata_ready,
            "stickers_ready": progress.stickers_ready,
            "total": progress.total,
        },
        "blockers": blockers,
        "orders": worklist_items,
        "cargo_places": cargo_places,
        "packing_boxes": packing_boxes,
        "unassigned_order_ids": unassigned_order_ids,
        "delivery_preflight": None,
        "last_wb_sync_at": (supply.last_wb_sync_at.isoformat() if supply.last_wb_sync_at else None),
        "tracking_summary": tracking_summary,
        "partial_rejection": partial_rejection,
        "wb_sync_stale": wb_sync_stale,
        "server_now": server_now.isoformat(),
    }


async def _load_supply_graph(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> FbsSupply | None:
    stmt = (
        select(FbsSupply)
        .options(
            selectinload(FbsSupply.seller),
            selectinload(FbsSupply.warehouse),
            selectinload(FbsSupply.orders),
            selectinload(FbsSupply.trbxes),
            selectinload(FbsSupply.barcode_asset),
        )
        .where(FbsSupply.id == supply_id, FbsSupply.tenant_id == tenant_id)
        .execution_options(populate_existing=True)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def _wb_warehouse_name(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    orders: list[FbsOrder],
) -> str | None:
    wb_ids = {int(o.wb_warehouse_id) for o in orders if o.wb_warehouse_id is not None}
    if not wb_ids:
        return None
    stmt = select(TenantWbMpWarehouse).where(
        TenantWbMpWarehouse.tenant_id == tenant_id,
        TenantWbMpWarehouse.wb_warehouse_id.in_(wb_ids),
    )
    res = await session.execute(stmt)
    row = res.scalars().first()
    return row.name if row else None


def _planned_destination(supply: FbsSupply) -> dict[str, Any] | None:
    if supply.planned_destination_office_id is None:
        return None
    return {
        "office_id": int(supply.planned_destination_office_id),
        "name": supply.planned_destination_name or "",
        "zone": supply.planned_destination_zone or "",
    }


def _compute_progress(orders: list[FbsOrder]) -> WorkspaceProgress:
    total = len(orders)
    picked = sum(1 for o in orders if o.pick_status == PICK_STATUS_PICKED)
    packed = sum(1 for o in orders if o.pack_status == PACK_STATUS_PACKED)
    metadata_ready = sum(1 for o in orders if _metadata_ready(o))
    stickers_ready = sum(
        1
        for o in orders
        if o.sticker_status
        in {STICKER_STATUS_READY, STICKER_STATUS_PRINT_OPENED, STICKER_STATUS_APPLIED}
    )
    return WorkspaceProgress(
        picked=picked,
        packed=packed,
        metadata_ready=metadata_ready,
        stickers_ready=stickers_ready,
        total=total,
    )


def _metadata_ready(order: FbsOrder) -> bool:
    if order.metadata_delivery_allowed is True:
        return True
    required = order.required_meta_json or []
    if not required:
        return True
    details = order.meta_details_json if isinstance(order.meta_details_json, dict) else {}
    for kind in required:
        state = details.get(kind)
        if isinstance(state, dict):
            status = state.get("status")
            if status in {META_STATUS_ACCEPTED, META_STATUS_ALLOWED_WITHOUT_CHECK}:
                continue
        return False
    return True


def _compute_stage(
    supply: FbsSupply,
    orders: list[FbsOrder],
    progress: WorkspaceProgress,
    *,
    has_packing_boxes: bool,
    unassigned_order_ids: list[str],
) -> str:
    if (
        supply.status in {FBS_SUPPLY_STATUS_DONE, FBS_SUPPLY_STATUS_IN_DELIVERY}
        and supply.operator_finished_at is None
    ):
        return "local_finish"
    if supply.status in {FBS_SUPPLY_STATUS_DONE, FBS_SUPPLY_STATUS_IN_DELIVERY}:
        return "tracking"
    if supply.status == FBS_SUPPLY_STATUS_DRAFT or not orders:
        return "composition"
    if progress.total == 0:
        return "composition"
    if progress.picked < progress.total:
        return "picking"
    if progress.packed < progress.total:
        return "packing"
    if progress.metadata_ready < progress.total:
        return "packing"
    if progress.stickers_ready < progress.total:
        return "order_stickers"
    if not has_packing_boxes or unassigned_order_ids:
        return "handoff_prep"
    if supply.delivery_type == FBS_DELIVERY_TYPE_PVZ and not supply.trbxes:
        return "handoff_prep"
    if supply.status == FBS_SUPPLY_STATUS_PACKED:
        return "delivery"
    if supply.status == FBS_SUPPLY_STATUS_ASSEMBLING:
        return "picking"
    return "delivery"


def _compute_workspace_blockers(
    supply: FbsSupply,
    orders: list[FbsOrder],
    stage: str,
    progress: WorkspaceProgress,
    *,
    has_packing_boxes: bool,
    unassigned_order_ids: list[str],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if not orders:
        blockers.append(
            {
                "stage": "composition",
                "code": "supply_empty",
                "message": "В поставке нет заказов.",
                "order_id": None,
                "retryable": False,
            }
        )
    for order in orders:
        if order.pick_status != PICK_STATUS_PICKED and stage in {
            "packing",
            "order_stickers",
            "handoff_prep",
            "delivery",
        }:
            blockers.append(
                {
                    "stage": "picking",
                    "code": "order_not_picked",
                    "message": f"Заказ №{order.wb_order_id} не подобран.",
                    "order_id": str(order.id),
                    "retryable": True,
                }
            )
        if not _metadata_ready(order) and stage in {
            "order_stickers",
            "handoff_prep",
            "delivery",
        }:
            blockers.append(
                {
                    "stage": "packing",
                    "code": "metadata_missing",
                    "message": f"Метаданные заказа №{order.wb_order_id} не готовы.",
                    "order_id": str(order.id),
                    "retryable": True,
                }
            )
    if (
        supply.delivery_type == FBS_DELIVERY_TYPE_PVZ
        and stage in {"handoff_prep", "delivery"}
        and not supply.trbxes
    ):
        blockers.append(
            {
                "stage": "handoff_prep",
                "code": "cargo_places_required",
                "message": "Для ПВЗ нужны грузоместа.",
                "order_id": None,
                "retryable": True,
            }
        )
    if stage == "handoff_prep" and not has_packing_boxes:
        blockers.append(
            {
                "stage": "packing",
                "code": "packing_boxes_required",
                "message": "Создайте физические короба WMS.",
                "order_id": None,
                "retryable": True,
            }
        )
    if stage == "handoff_prep":
        for order_id in unassigned_order_ids:
            blockers.append(
                {
                    "stage": "packing",
                    "code": "orders_not_distributed",
                    "message": "Распределите упакованный заказ в короб.",
                    "order_id": order_id,
                    "retryable": True,
                }
            )
    if progress.total and progress.stickers_ready < progress.total and stage == "delivery":
        blockers.append(
            {
                "stage": "order_stickers",
                "code": "stickers_not_ready",
                "message": "Не все стикеры заказов готовы.",
                "order_id": None,
                "retryable": True,
            }
        )
    return blockers


async def _build_cargo_places(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
) -> list[dict[str, Any]]:
    if not supply.trbxes:
        return []
    trbx_ids = [t.id for t in supply.trbxes]
    stmt = select(FbsPrintAsset).where(
        FbsPrintAsset.tenant_id == tenant_id,
        FbsPrintAsset.fbs_trbx_id.in_(trbx_ids),
        FbsPrintAsset.kind == PRINT_ASSET_KIND_CARGO_PLACE_QR,
        FbsPrintAsset.status.in_((PRINT_ASSET_STATUS_READY, PRINT_ASSET_STATUS_ERROR)),
    )
    res = await session.execute(stmt)
    qr_by_trbx = {a.fbs_trbx_id: a for a in res.scalars().all() if a.fbs_trbx_id}
    places: list[dict[str, Any]] = []
    for trbx in supply.trbxes:
        places.append(_map_cargo_place(trbx, qr_by_trbx.get(trbx.id)))
    return places


async def _build_packing_boxes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
    orders: list[FbsOrder],
) -> tuple[list[dict[str, Any]], list[str]]:
    stmt = (
        select(FbsPackingBox)
        .options(
            selectinload(FbsPackingBox.warehouse_box),
            selectinload(FbsPackingBox.items)
            .selectinload(FbsPackingBoxItem.order)
            .selectinload(FbsOrder.product),
        )
        .where(
            FbsPackingBox.tenant_id == tenant_id,
            FbsPackingBox.supply_id == supply.id,
        )
        .order_by(FbsPackingBox.box_number)
    )
    boxes = list((await session.execute(stmt)).scalars().all())
    trbx_by_warehouse_box = {
        row.packaging_box_id: row for row in supply.trbxes if row.packaging_box_id is not None
    }
    trbx_ids = [row.id for row in trbx_by_warehouse_box.values()]
    qr_by_trbx: dict[uuid.UUID, FbsPrintAsset] = {}
    if trbx_ids:
        qr_stmt = select(FbsPrintAsset).where(
            FbsPrintAsset.tenant_id == tenant_id,
            FbsPrintAsset.fbs_trbx_id.in_(trbx_ids),
            FbsPrintAsset.kind == PRINT_ASSET_KIND_CARGO_PLACE_QR,
            FbsPrintAsset.status.in_((PRINT_ASSET_STATUS_READY, PRINT_ASSET_STATUS_ERROR)),
        )
        qr_by_trbx = {
            row.fbs_trbx_id: row
            for row in (await session.execute(qr_stmt)).scalars().all()
            if row.fbs_trbx_id is not None
        }
    assigned: set[uuid.UUID] = set()
    payload: list[dict[str, Any]] = []
    for box in boxes:
        trbx = trbx_by_warehouse_box.get(box.warehouse_box_id)
        item_rows: list[dict[str, Any]] = []
        for item in sorted(box.items, key=lambda row: (row.assigned_at, str(row.id))):
            assigned.add(item.fbs_order_id)
            item_rows.append(
                {
                    "id": str(item.order.id),
                    "wb_order_id": int(item.order.wb_order_id),
                    "product_id": (str(item.order.product_id) if item.order.product_id else None),
                    "product_name": (
                        item.order.product.name
                        if item.order.product is not None
                        else "Товар не сопоставлен"
                    ),
                }
            )
        payload.append(
            {
                "id": str(box.id),
                "box_number": int(box.box_number),
                "status": box.status,
                "internal_barcode": box.warehouse_box.internal_barcode,
                "wb_trbx_id": trbx.wb_trbx_id if trbx is not None else None,
                "qr_asset": (
                    _map_print_asset(qr_by_trbx.get(trbx.id)) if trbx is not None else None
                ),
                "items_count": len(item_rows),
                "orders": item_rows,
            }
        )
    return payload, [str(order.id) for order in orders if order.id not in assigned]


def _map_cargo_place(trbx: FbsTrbx, qr_asset: FbsPrintAsset | None) -> dict[str, Any]:
    return {
        "id": str(trbx.id),
        "wb_trbx_id": trbx.wb_trbx_id,
        "length_mm": trbx.length_mm,
        "width_mm": trbx.width_mm,
        "height_mm": trbx.height_mm,
        "weight_g": trbx.weight_g,
        "qr_asset": _map_print_asset(qr_asset),
        "applied_at": trbx.qr_applied_at.isoformat() if trbx.qr_applied_at else None,
    }


def _map_print_asset(asset: FbsPrintAsset | None) -> dict[str, Any] | None:
    if asset is None:
        return None
    url = print_asset_content_url(asset.id) if asset.status == PRINT_ASSET_STATUS_READY else None
    return {
        "id": str(asset.id),
        "kind": asset.kind,
        "status": asset.status,
        "content_type": asset.content_type,
        "width_mm": asset.width_mm,
        "height_mm": asset.height_mm,
        "preview_url": url,
        "download_url": url,
        "checksum": asset.checksum,
        "applied_at": asset.applied_at.isoformat() if asset.applied_at else None,
        "error": (
            {"code": asset.error_code or "error", "message": asset.error_message or ""}
            if asset.error_code
            else None
        ),
    }


async def load_supply_qr_asset(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> FbsPrintAsset | None:
    stmt = select(FbsPrintAsset).where(
        FbsPrintAsset.tenant_id == tenant_id,
        FbsPrintAsset.fbs_supply_id == supply_id,
        FbsPrintAsset.kind == PRINT_ASSET_KIND_SUPPLY_QR,
        FbsPrintAsset.status == PRINT_ASSET_STATUS_READY,
    )
    res = await session.execute(stmt)
    return res.scalars().first()
