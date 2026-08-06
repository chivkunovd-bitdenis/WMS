"""Local physical packing boxes for FBS supplies (separate from WB cargo places)."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_order import PACK_STATUS_PACKED
from app.models.fbs_packing_box import FbsPackingBox, FbsPackingBoxItem
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_PVZ,
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.fbs_wb_operation import (
    WB_OPERATION_STATE_CONFIRMED,
    WB_OPERATION_STATE_PENDING,
    FbsWbOperation,
)
from app.models.user import User
from app.models.warehouse_box import WarehouseBox
from app.services import fbs_shipment_pvz_service as pvz_svc
from app.services.fbs_workspace_service import get_supply_workspace
from app.services.warehouse_box_service import create_warehouse_box

OP_CREATE = "local_packing_boxes_create"
OP_DELETE = "local_packing_box_delete"
OP_ASSIGN = "local_packing_box_assign"
OP_UNASSIGN = "local_packing_box_unassign"


@dataclass
class FbsPackingBoxError(Exception):
    code: str
    message: str = ""
    http_status: int = 409
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__init__(self.code)


def _request_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _wb_child_key(idempotency_key: str) -> str:
    return f"packing-box:{hashlib.sha256(idempotency_key.encode()).hexdigest()}"


async def _load_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> FbsSupply:
    stmt = (
        select(FbsSupply)
        .options(selectinload(FbsSupply.orders), selectinload(FbsSupply.trbxes))
        .where(FbsSupply.tenant_id == tenant_id, FbsSupply.id == supply_id)
        .with_for_update()
    )
    supply = (await session.execute(stmt)).scalar_one_or_none()
    if supply is None:
        raise FbsPackingBoxError("supply_not_found", http_status=404)
    return supply


def _require_mutable(supply: FbsSupply) -> None:
    if supply.status not in {FBS_SUPPLY_STATUS_ASSEMBLING, FBS_SUPPLY_STATUS_PACKED}:
        raise FbsPackingBoxError("supply_not_editable")
    if supply.delivered_at is not None:
        raise FbsPackingBoxError("supply_not_editable")


async def _operation(
    session: AsyncSession,
    supply: FbsSupply,
    *,
    kind: str,
    idempotency_key: str,
    request_hash: str,
) -> FbsWbOperation:
    existing = await session.scalar(
        select(FbsWbOperation).where(
            FbsWbOperation.seller_id == supply.seller_id,
            FbsWbOperation.operation_kind == kind,
            FbsWbOperation.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise FbsPackingBoxError("idempotency_key_reused")
        return existing
    op = FbsWbOperation(
        tenant_id=supply.tenant_id,
        seller_id=supply.seller_id,
        operation_kind=kind,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        local_entity_type="fbs_supply",
        local_entity_id=supply.id,
        state=WB_OPERATION_STATE_PENDING,
    )
    session.add(op)
    await session.flush()
    return op


async def _confirm_operation(
    session: AsyncSession,
    operation: FbsWbOperation,
    *,
    response_summary: dict[str, Any] | None = None,
) -> None:
    operation.state = WB_OPERATION_STATE_CONFIRMED
    operation.confirmed_at = datetime.now(tz=UTC)
    operation.response_summary_json = response_summary
    operation.error_code = None
    await session.flush()


async def create_packing_boxes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    count: int,
    idempotency_key: str,
    actor: User,
    http_client: httpx.AsyncClient,
) -> dict[str, Any]:
    if count < 1 or count > 100:
        raise FbsPackingBoxError("invalid_box_count", http_status=422)
    supply = await _load_supply(session, tenant_id, supply_id)
    _require_mutable(supply)
    if count > len(supply.orders) + (1 if supply.delivery_type == FBS_DELIVERY_TYPE_PVZ else 0):
        raise FbsPackingBoxError("invalid_box_count", http_status=422)

    req_hash = _request_hash({"supply_id": str(supply_id), "count": count})
    operation = await _operation(
        session,
        supply,
        kind=OP_CREATE,
        idempotency_key=idempotency_key,
        request_hash=req_hash,
    )
    if operation.state == WB_OPERATION_STATE_CONFIRMED:
        return await get_supply_workspace(session, tenant_id, supply_id)

    summary = operation.request_summary_json or {}
    raw_ids = summary.get("packing_box_ids")
    boxes: list[FbsPackingBox] = []
    if isinstance(raw_ids, list) and raw_ids:
        stmt = (
            select(FbsPackingBox)
            .where(
                FbsPackingBox.tenant_id == tenant_id,
                FbsPackingBox.supply_id == supply_id,
                FbsPackingBox.id.in_([uuid.UUID(str(row)) for row in raw_ids]),
            )
            .order_by(FbsPackingBox.box_number)
        )
        boxes = list((await session.execute(stmt)).scalars().all())
    if not boxes:
        max_number = int(
            await session.scalar(
                select(func.max(FbsPackingBox.box_number)).where(
                    FbsPackingBox.supply_id == supply_id
                )
            )
            or 0
        )
        for offset in range(count):
            warehouse_box = await create_warehouse_box(
                session, tenant_id, warehouse_id=supply.warehouse_id
            )
            box = FbsPackingBox(
                tenant_id=tenant_id,
                supply_id=supply_id,
                warehouse_box_id=warehouse_box.id,
                box_number=max_number + offset + 1,
            )
            session.add(box)
            await session.flush()
            boxes.append(box)
        operation.request_summary_json = {
            "supply_id": str(supply_id),
            "count": count,
            "packing_box_ids": [str(box.id) for box in boxes],
        }
        await session.flush()

    if supply.delivery_type == FBS_DELIVERY_TYPE_PVZ:
        box_by_warehouse_id = {box.warehouse_box_id: box for box in boxes}
        mapped_ids = {
            trbx.packaging_box_id
            for trbx in supply.trbxes
            if trbx.packaging_box_id in box_by_warehouse_id
        }
        unbound_trbxes = [row for row in supply.trbxes if row.packaging_box_id is None]
        for box, trbx in zip(
            [row for row in boxes if row.warehouse_box_id not in mapped_ids],
            unbound_trbxes,
            strict=False,
        ):
            trbx.packaging_box_id = box.warehouse_box_id
            mapped_ids.add(box.warehouse_box_id)
        missing = [box for box in boxes if box.warehouse_box_id not in mapped_ids]
        if missing:
            drafts = [
                pvz_svc.CargoPlaceDraft(
                    client_id=str(box.id),
                    length_mm=None,
                    width_mm=None,
                    height_mm=None,
                    weight_g=None,
                    measurements_confirmed=True,
                    packaging_box_id=box.warehouse_box_id,
                )
                for box in missing
            ]
            await pvz_svc.create_cargo_places(
                session,
                tenant_id,
                supply_id,
                len(missing),
                drafts,
                _wb_child_key(idempotency_key),
                http_client,
                actor_user_id=actor.id,
                confirmation_source="local_packing_boxes",
            )

    await _confirm_operation(
        session,
        operation,
        response_summary={"packing_box_ids": [str(box.id) for box in boxes]},
    )
    await session.flush()
    return await get_supply_workspace(session, tenant_id, supply_id)


async def assign_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    box_id: uuid.UUID,
    *,
    order_ids: list[uuid.UUID],
    idempotency_key: str,
    actor: User,
) -> dict[str, Any]:
    return await _change_assignment(
        session,
        tenant_id,
        supply_id,
        box_id,
        order_ids=order_ids,
        idempotency_key=idempotency_key,
        actor=actor,
        assign=True,
    )


async def unassign_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    box_id: uuid.UUID,
    *,
    order_ids: list[uuid.UUID],
    idempotency_key: str,
    actor: User,
) -> dict[str, Any]:
    return await _change_assignment(
        session,
        tenant_id,
        supply_id,
        box_id,
        order_ids=order_ids,
        idempotency_key=idempotency_key,
        actor=actor,
        assign=False,
    )


async def _change_assignment(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    box_id: uuid.UUID,
    *,
    order_ids: list[uuid.UUID],
    idempotency_key: str,
    actor: User,
    assign: bool,
) -> dict[str, Any]:
    if not order_ids or len(set(order_ids)) != len(order_ids):
        raise FbsPackingBoxError("invalid_order_ids", http_status=422)
    supply = await _load_supply(session, tenant_id, supply_id)
    _require_mutable(supply)
    box = await session.scalar(
        select(FbsPackingBox).where(
            FbsPackingBox.id == box_id,
            FbsPackingBox.tenant_id == tenant_id,
            FbsPackingBox.supply_id == supply_id,
        )
    )
    if box is None:
        raise FbsPackingBoxError("packing_box_not_found", http_status=404)
    req_hash = _request_hash(
        {
            "supply_id": str(supply_id),
            "box_id": str(box_id),
            "order_ids": sorted(str(row) for row in order_ids),
        }
    )
    operation = await _operation(
        session,
        supply,
        kind=OP_ASSIGN if assign else OP_UNASSIGN,
        idempotency_key=idempotency_key,
        request_hash=req_hash,
    )
    if operation.state == WB_OPERATION_STATE_CONFIRMED:
        return await get_supply_workspace(session, tenant_id, supply_id)

    by_id = {order.id: order for order in supply.orders}
    if any(order_id not in by_id for order_id in order_ids):
        raise FbsPackingBoxError("order_not_in_supply", http_status=404)
    existing_rows = list(
        (
            await session.execute(
                select(FbsPackingBoxItem).where(FbsPackingBoxItem.fbs_order_id.in_(order_ids))
            )
        ).scalars()
    )
    existing_by_order = {row.fbs_order_id: row for row in existing_rows}
    if assign:
        not_packed = [
            str(order_id)
            for order_id in order_ids
            if by_id[order_id].pack_status != PACK_STATUS_PACKED
        ]
        if not_packed:
            raise FbsPackingBoxError("orders_not_packed", context={"order_ids": not_packed})
        if existing_rows:
            raise FbsPackingBoxError(
                "orders_already_assigned",
                context={"order_ids": [str(row.fbs_order_id) for row in existing_rows]},
            )
        for order_id in order_ids:
            session.add(
                FbsPackingBoxItem(
                    tenant_id=tenant_id,
                    box_id=box_id,
                    fbs_order_id=order_id,
                    assigned_by_user_id=actor.id,
                )
            )
    else:
        missing = [
            str(order_id)
            for order_id in order_ids
            if order_id not in existing_by_order or existing_by_order[order_id].box_id != box_id
        ]
        if missing:
            raise FbsPackingBoxError("orders_not_in_box", context={"order_ids": missing})
        for order_id in order_ids:
            await session.delete(existing_by_order[order_id])

    await _confirm_operation(session, operation)
    await session.flush()
    return await get_supply_workspace(session, tenant_id, supply_id)


async def delete_packing_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    box_id: uuid.UUID,
    *,
    idempotency_key: str,
    http_client: httpx.AsyncClient,
) -> dict[str, Any]:
    supply = await _load_supply(session, tenant_id, supply_id)
    _require_mutable(supply)
    req_hash = _request_hash({"supply_id": str(supply_id), "box_id": str(box_id)})
    operation = await _operation(
        session,
        supply,
        kind=OP_DELETE,
        idempotency_key=idempotency_key,
        request_hash=req_hash,
    )
    if operation.state == WB_OPERATION_STATE_CONFIRMED:
        return await get_supply_workspace(session, tenant_id, supply_id)

    box = await session.scalar(
        select(FbsPackingBox)
        .options(selectinload(FbsPackingBox.items))
        .where(
            FbsPackingBox.id == box_id,
            FbsPackingBox.tenant_id == tenant_id,
            FbsPackingBox.supply_id == supply_id,
        )
    )
    if box is None:
        raise FbsPackingBoxError("packing_box_not_found", http_status=404)
    if box.items:
        raise FbsPackingBoxError("packing_box_not_empty")

    linked_trbx = next(
        (row for row in supply.trbxes if row.packaging_box_id == box.warehouse_box_id),
        None,
    )
    if linked_trbx is not None:
        await pvz_svc.delete_cargo_places(
            session,
            tenant_id,
            supply_id,
            [linked_trbx.wb_trbx_id],
            _wb_child_key(idempotency_key),
            http_client,
        )
    warehouse_box = await session.get(WarehouseBox, box.warehouse_box_id)
    await session.delete(box)
    await session.flush()
    if warehouse_box is not None:
        await session.delete(warehouse_box)
    await _confirm_operation(session, operation)
    await session.flush()
    return await get_supply_workspace(session, tenant_id, supply_id)
