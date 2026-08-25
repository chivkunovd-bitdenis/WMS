from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_order import (
    FBS_ORDER_STATUS_CANCELLED,
    PACK_STATUS_PACKED,
    PACK_STATUS_PENDING,
    PICK_STATUS_PICKED,
    FbsOrder,
)
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_supply import FbsSupply
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.services import inventory_service as inv_svc

logger = logging.getLogger(__name__)


class OzonPackagingError(Exception):
    pass


async def active_order_fulfillment(
    session: AsyncSession,
    order_id: uuid.UUID,
) -> FbsPackagingFulfillment | None:
    return cast(
        FbsPackagingFulfillment | None,
        await session.scalar(
            select(FbsPackagingFulfillment)
            .where(
                FbsPackagingFulfillment.fbs_order_id == order_id,
                FbsPackagingFulfillment.undone_at.is_(None),
            )
            .options(selectinload(FbsPackagingFulfillment.order))
        ),
    )


def packed_units(fulfillment: FbsPackagingFulfillment | None) -> list[dict[str, str]]:
    return list(fulfillment.ozon_packed_units_json or []) if fulfillment is not None else []


def required_quantity(order: FbsOrder, product_id: uuid.UUID | None = None) -> int:
    return sum(
        int(position.quantity)
        for position in order.product_positions
        if position.product_id is not None
        and (product_id is None or position.product_id == product_id)
    )


def packed_quantity(
    fulfillment: FbsPackagingFulfillment | None,
    product_id: uuid.UUID | None = None,
) -> int:
    return sum(
        1
        for unit in packed_units(fulfillment)
        if product_id is None or unit.get("product_id") == str(product_id)
    )


async def resolve_order_for_pack_unit(
    session: AsyncSession,
    supply: FbsSupply,
    product_id: uuid.UUID,
    *,
    explicit_order_id: uuid.UUID | None,
) -> tuple[FbsOrder, FbsPackagingFulfillment | None]:
    candidates = [
        order
        for order in supply.orders
        if order.marketplace == "ozon"
        and order.status != FBS_ORDER_STATUS_CANCELLED
        and (explicit_order_id is None or order.id == explicit_order_id)
        and required_quantity(order, product_id) > 0
    ]
    if explicit_order_id is not None and not candidates:
        raise OzonPackagingError("order_product_mismatch")
    for order in candidates:
        if order.pick_status != PICK_STATUS_PICKED:
            continue
        fulfillment = await active_order_fulfillment(session, order.id)
        if packed_quantity(fulfillment, product_id) < required_quantity(order, product_id):
            return order, fulfillment
    if any(order.pick_status != PICK_STATUS_PICKED for order in candidates):
        raise OzonPackagingError("order_not_picked")
    raise OzonPackagingError("no_eligible_order")


async def order_pack_complete(session: AsyncSession, order: FbsOrder) -> bool:
    if any(position.product_id is None for position in order.product_positions):
        return False
    fulfillment = await active_order_fulfillment(session, order.id)
    return packed_quantity(fulfillment) == required_quantity(order)


def record_pack_unit(
    *,
    tenant_id: uuid.UUID,
    target_order: FbsOrder,
    fulfillment: FbsPackagingFulfillment | None,
    task: PackagingTask,
    line: PackagingTaskLine,
    acting_user_id: uuid.UUID | None,
    unit_key: str,
    packed_at: datetime,
) -> FbsPackagingFulfillment:
    packed_unit = {
        "product_id": str(line.product_id),
        "packaging_task_line_id": str(line.id),
        "storage_location_id": str(line.storage_location_id),
        "idempotency_key": unit_key,
        "packed_at": packed_at.isoformat(),
    }
    if fulfillment is None:
        fulfillment = FbsPackagingFulfillment(
            tenant_id=tenant_id,
            fbs_order_id=target_order.id,
            packaging_task_id=task.id,
            packaging_task_line_id=line.id,
            fulfilled_by_user_id=acting_user_id,
            fulfilled_at=packed_at,
            pack_idempotency_key=unit_key,
            ozon_packed_units_json=[packed_unit],
        )
    else:
        fulfillment.ozon_packed_units_json = [*packed_units(fulfillment), packed_unit]
    if packed_quantity(fulfillment) == required_quantity(target_order):
        target_order.pack_status = PACK_STATUS_PACKED
        target_order.packed_at = packed_at
    else:
        target_order.pack_status = PACK_STATUS_PENDING
        target_order.packed_at = None
    return fulfillment


async def write_off_order(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    order: FbsOrder,
) -> None:
    fulfillment = await active_order_fulfillment(session, order.id)
    units = packed_units(fulfillment)
    if not units or not await order_pack_complete(session, order):
        raise OzonPackagingError("missing_fbs_packaging_location")
    grouped: dict[tuple[uuid.UUID, uuid.UUID], int] = defaultdict(int)
    for unit in units:
        try:
            product_id = uuid.UUID(unit["product_id"])
            storage_location_id = uuid.UUID(unit["storage_location_id"])
        except (KeyError, ValueError) as exc:
            raise OzonPackagingError("invalid_ozon_packaging_fulfillment") from exc
        grouped[(product_id, storage_location_id)] += 1
    positions_json = [
        {
            "product_id": str(product_id),
            "storage_location_id": str(storage_location_id),
            "quantity": quantity,
        }
        for (product_id, storage_location_id), quantity in sorted(
            grouped.items(), key=lambda item: (str(item[0][0]), str(item[0][1]))
        )
    ]
    first_product_id, first_storage_location_id = next(iter(grouped))
    session.add(
        FbsShipmentReversalLedger(
            tenant_id=tenant_id,
            fbs_order_id=order.id,
            product_id=first_product_id,
            storage_location_id=first_storage_location_id,
            quantity=sum(grouped.values()),
            ozon_positions_json=positions_json,
        )
    )
    await session.flush()
    for (product_id, storage_location_id), quantity in grouped.items():
        try:
            await inv_svc.apply_fbs_supply_write_off(
                session,
                tenant_id=tenant_id,
                product_id=product_id,
                storage_location_id=storage_location_id,
                quantity=quantity,
            )
        except ValueError as exc:
            if str(exc) != "insufficient stock":
                raise
            logger.warning(
                "Ozon FBS write-off skipped, no stock: tenant=%s product=%s "
                "location=%s order=%s quantity=%s",
                tenant_id,
                product_id,
                storage_location_id,
                order.id,
                quantity,
            )
