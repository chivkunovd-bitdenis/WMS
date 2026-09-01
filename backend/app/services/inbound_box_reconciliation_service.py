"""Restore current stock links to the original physical inbound boxes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeBoxLine,
    InboundIntakeRequest,
)
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.models.warehouse_map_event import WarehouseMapEvent
from app.services import inventory_service
from app.services.inventory_container_service import ContainerKind


class InboundBoxReconciliationError(RuntimeError):
    pass


@dataclass(frozen=True)
class InboundBoxAllocation:
    box_id: uuid.UUID
    box_number: int
    product_id: uuid.UUID
    sku_code: str
    original_qty: int
    current_box_qty: int
    target_box_qty: int

    @property
    def delta(self) -> int:
        return self.target_box_qty - self.current_box_qty


@dataclass(frozen=True)
class InboundBoxReconciliationPlan:
    tenant_id: uuid.UUID
    request_id: uuid.UUID
    storage_location_id: uuid.UUID
    warehouse_id: uuid.UUID
    allocations: tuple[InboundBoxAllocation, ...]
    original_units: int
    current_units_considered: int
    target_linked_units: int
    unchanged_loose_units: int


def _proportional_targets(
    weighted_rows: list[tuple[InboundIntakeBox, InboundIntakeBoxLine]],
    target_total: int,
) -> dict[tuple[uuid.UUID, uuid.UUID], int]:
    original_total = sum(int(line.quantity) for _box, line in weighted_rows)
    if original_total <= 0 or target_total <= 0:
        return {(box.id, line.product_id): 0 for box, line in weighted_rows}

    targets: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
    remainders: list[tuple[int, int, str, tuple[uuid.UUID, uuid.UUID]]] = []
    assigned = 0
    for box, line in weighted_rows:
        numerator = target_total * int(line.quantity)
        base, remainder = divmod(numerator, original_total)
        key = (box.id, line.product_id)
        targets[key] = base
        assigned += base
        remainders.append((-remainder, int(box.box_number), str(box.id), key))
    for _neg_remainder, _number, _box_id, key in sorted(remainders)[
        : target_total - assigned
    ]:
        targets[key] += 1
    return targets


async def build_reconciliation_plan(
    session: AsyncSession,
    *,
    request_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    lock: bool = False,
) -> InboundBoxReconciliationPlan:
    request_stmt = (
        select(InboundIntakeRequest)
        .where(InboundIntakeRequest.id == request_id)
        .options(
            selectinload(InboundIntakeRequest.boxes)
            .selectinload(InboundIntakeBox.lines)
            .selectinload(InboundIntakeBoxLine.product)
        )
    )
    if lock:
        request_stmt = request_stmt.with_for_update()
    request = (await session.execute(request_stmt)).scalar_one_or_none()
    if request is None:
        raise InboundBoxReconciliationError("request_not_found")
    location = await session.get(StorageLocation, storage_location_id)
    if location is None or location.tenant_id != request.tenant_id:
        raise InboundBoxReconciliationError("location_not_found")
    if not request.boxes:
        raise InboundBoxReconciliationError("request_has_no_boxes")

    box_ids = [box.id for box in request.boxes]
    balances_stmt = select(InventoryBalance).where(
        InventoryBalance.tenant_id == request.tenant_id,
        InventoryBalance.container_kind == "box",
        InventoryBalance.container_id.in_(box_ids),
    )
    if lock:
        balances_stmt = balances_stmt.with_for_update()
    linked_balances = list((await session.scalars(balances_stmt)).all())
    wrong_location = next(
        (
            balance
            for balance in linked_balances
            if balance.quantity != 0
            and balance.storage_location_id != storage_location_id
        ),
        None,
    )
    if wrong_location is not None:
        raise InboundBoxReconciliationError("box_stock_exists_at_other_location")
    current_by_key = {
        (balance.container_id, balance.product_id): max(0, int(balance.quantity))
        for balance in linked_balances
        if balance.storage_location_id == storage_location_id
    }

    product_rows: dict[
        uuid.UUID, list[tuple[InboundIntakeBox, InboundIntakeBoxLine]]
    ] = {}
    for box in sorted(request.boxes, key=lambda item: (item.box_number, str(item.id))):
        for line in box.lines:
            if int(line.quantity) <= 0:
                continue
            product_rows.setdefault(line.product_id, []).append((box, line))

    loose_rows = list(
        (
            await session.scalars(
                select(InventoryBalance).where(
                    InventoryBalance.tenant_id == request.tenant_id,
                    InventoryBalance.storage_location_id == storage_location_id,
                    InventoryBalance.product_id.in_(product_rows),
                    InventoryBalance.container_kind.is_(None),
                    InventoryBalance.container_id.is_(None),
                )
            )
        ).all()
    )
    loose_by_product = {
        row.product_id: max(0, int(row.quantity)) for row in loose_rows
    }

    allocations: list[InboundBoxAllocation] = []
    current_units_considered = 0
    target_linked_units = 0
    unchanged_loose_units = 0
    for product_id, rows in product_rows.items():
        original_total = sum(int(line.quantity) for _box, line in rows)
        linked_total = sum(
            current_by_key.get((box.id, product_id), 0) for box, _line in rows
        )
        loose_total = loose_by_product.get(product_id, 0)
        current_total = linked_total + loose_total
        target_total = min(original_total, current_total)
        targets = _proportional_targets(rows, target_total)
        current_units_considered += current_total
        target_linked_units += target_total
        unchanged_loose_units += current_total - target_total
        for box, line in rows:
            product = line.product
            if product is None:
                product = await session.get(Product, product_id)
            if product is None:
                raise InboundBoxReconciliationError("product_not_found")
            allocations.append(
                InboundBoxAllocation(
                    box_id=box.id,
                    box_number=int(box.box_number),
                    product_id=product_id,
                    sku_code=product.sku_code,
                    original_qty=int(line.quantity),
                    current_box_qty=current_by_key.get((box.id, product_id), 0),
                    target_box_qty=targets[(box.id, product_id)],
                )
            )

    return InboundBoxReconciliationPlan(
        tenant_id=request.tenant_id,
        request_id=request.id,
        storage_location_id=location.id,
        warehouse_id=location.warehouse_id,
        allocations=tuple(
            sorted(
                allocations,
                key=lambda row: (row.box_number, row.sku_code, str(row.product_id)),
            )
        ),
        original_units=sum(row.original_qty for row in allocations),
        current_units_considered=current_units_considered,
        target_linked_units=target_linked_units,
        unchanged_loose_units=unchanged_loose_units,
    )


async def apply_reconciliation_plan(
    session: AsyncSession,
    *,
    request_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> InboundBoxReconciliationPlan:
    plan = await build_reconciliation_plan(
        session,
        request_id=request_id,
        storage_location_id=storage_location_id,
        lock=True,
    )
    boxes = list(
        (
            await session.scalars(
                select(InboundIntakeBox)
                .where(
                    InboundIntakeBox.request_id == request_id,
                    InboundIntakeBox.tenant_id == plan.tenant_id,
                )
                .with_for_update()
            )
        ).all()
    )
    boxes_by_id = {box.id: box for box in boxes}
    for box in boxes:
        box.storage_location_id = storage_location_id

    existing_balance_rows = (
        await session.execute(
            select(InventoryBalance.container_id, InventoryBalance.product_id).where(
                InventoryBalance.tenant_id == plan.tenant_id,
                InventoryBalance.storage_location_id == storage_location_id,
                InventoryBalance.container_kind == "box",
                InventoryBalance.container_id.in_(boxes_by_id),
            )
        )
    ).all()
    existing_balance_keys = {
        (container_id, product_id)
        for container_id, product_id in existing_balance_rows
        if container_id is not None
    }
    # A zero row is deliberate: it records that this original box/product pair
    # has switched to current InventoryBalance accounting. Catalog and map code
    # must then show zero instead of resurrecting the historical intake quantity.
    for row in plan.allocations:
        key = (row.box_id, row.product_id)
        if key in existing_balance_keys:
            continue
        session.add(
            InventoryBalance(
                tenant_id=plan.tenant_id,
                product_id=row.product_id,
                storage_location_id=storage_location_id,
                container_kind="box",
                container_id=row.box_id,
                quantity=0,
                quantity_unpacked=0,
                quantity_packed=0,
            )
        )
        existing_balance_keys.add(key)
    await session.flush()

    moved_by_box: dict[uuid.UUID, int] = {}
    for row in plan.allocations:
        if row.delta == 0:
            continue
        from_kind: ContainerKind | None
        to_kind: ContainerKind | None
        if row.delta > 0:
            from_kind = None
            from_id = None
            to_kind = "box"
            to_id = row.box_id
            quantity = row.delta
        else:
            from_kind = "box"
            from_id = row.box_id
            to_kind = None
            to_id = None
            quantity = -row.delta
        await inventory_service.reclassify_balance_container(
            session,
            tenant_id=plan.tenant_id,
            product_id=row.product_id,
            storage_location_id=storage_location_id,
            quantity=quantity,
            from_container_kind=from_kind,
            from_container_id=from_id,
            to_container_kind=to_kind,
            to_container_id=to_id,
            actor_user_id=actor_user_id,
        )
        moved_by_box[row.box_id] = moved_by_box.get(row.box_id, 0) + row.delta

    for box_id, delta in moved_by_box.items():
        if delta == 0:
            continue
        box = boxes_by_id[box_id]
        session.add(
            WarehouseMapEvent(
                tenant_id=plan.tenant_id,
                warehouse_id=plan.warehouse_id,
                actor_user_id=actor_user_id,
                subject=f"Короб КР-{box.box_number:06d}",
                quantity=abs(delta),
                from_label="Россыпью" if delta > 0 else f"Короб КР-{box.box_number:06d}",
                to_label=f"Короб КР-{box.box_number:06d}" if delta > 0 else "Россыпью",
            )
        )
    await session.commit()
    return await build_reconciliation_plan(
        session,
        request_id=request_id,
        storage_location_id=storage_location_id,
    )
