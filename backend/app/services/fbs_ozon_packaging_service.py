from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, cast

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
from app.models.inventory_balance import InventoryBalance
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.storage_location import StorageLocation
from app.services import fbs_shipment_source_service as source_svc
from app.services import inventory_service as inv_svc
from app.services.inventory_container_service import ContainerKind


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


async def plan_shipment_sources(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    orders: list[FbsOrder],
) -> source_svc.FbsShipmentSourcePlan:
    """Preview exact Ozon sources and current shortage without staging a write-off."""
    orders = [order for order in orders if order.status != FBS_ORDER_STATUS_CANCELLED]
    ledgers = {
        ledger.fbs_order_id: ledger
        for ledger in (
            await session.scalars(
                select(FbsShipmentReversalLedger)
                .where(
                    FbsShipmentReversalLedger.tenant_id == tenant_id,
                    FbsShipmentReversalLedger.fbs_order_id.in_([order.id for order in orders]),
                )
                .with_for_update()
            )
        ).all()
    }
    recipes: dict[uuid.UUID, list[dict[str, Any]]] = {}
    requests: list[source_svc.FbsShipmentSourceRequest] = []
    consumption: dict[tuple[uuid.UUID, uuid.UUID, ContainerKind | None, uuid.UUID | None], int] = {}
    for order in orders:
        ledger = ledgers.get(order.id)
        if ledger is not None:
            if ledger.reversed_at is not None:
                raise OzonPackagingError("fbs_shipment_already_reversed")
            if ledger.shipment_movement_id is not None:
                continue
        positions = order.product_positions
        if positions and any(position.product_id is None for position in positions):
            raise OzonPackagingError("fbs_shipment_product_missing")
        expected: Counter[uuid.UUID] = Counter()
        for position in positions:
            if position.quantity <= 0:
                raise OzonPackagingError("fbs_shipment_source_missing")
            if position.product_id is not None:
                expected[position.product_id] += int(position.quantity)
        if not positions and order.product_id is not None:
            expected[order.product_id] = 1
        if not expected:
            raise OzonPackagingError("fbs_shipment_product_missing")
        if ledger is not None and ledger.ozon_positions_json:
            staged: Counter[uuid.UUID] = Counter()
            for staged_row in ledger.ozon_positions_json:
                staged[uuid.UUID(str(staged_row["product_id"]))] += int(str(staged_row["quantity"]))
            if staged == expected:
                recipes[order.id] = list(ledger.ozon_positions_json)
                continue
            # An earlier attempt may have stopped before assembly. Its source
            # recipe must not retain an older quantity after a real composition change.
        fulfillment = await active_order_fulfillment(session, order.id)
        units = packed_units(fulfillment)
        grouped: dict[tuple[uuid.UUID, uuid.UUID], int] = defaultdict(int)
        try:
            for unit in units:
                grouped[
                    (uuid.UUID(unit["product_id"]), uuid.UUID(unit["storage_location_id"]))
                ] += 1
        except (KeyError, ValueError) as exc:
            raise OzonPackagingError("invalid_ozon_packaging_fulfillment") from exc
        packed: Counter[uuid.UUID] = Counter()
        for (product_id, _), quantity in grouped.items():
            packed[product_id] += quantity
        if units and packed == expected:
            recipes[order.id] = [
                {
                    "product_id": str(product_id),
                    "storage_location_id": str(location_id),
                    "quantity": quantity,
                }
                for (product_id, location_id), quantity in grouped.items()
            ]
        else:
            # Unit requests allow the existing planner to span several stock keys
            # for a single position, without silently discarding repeated order IDs.
            requests.extend(
                source_svc.FbsShipmentSourceRequest(
                    fbs_order_id=order.id,
                    product_id=product_id,
                    quantity=1,
                )
                for product_id, quantity in expected.items()
                for _ in range(quantity)
            )
    for recipe in recipes.values():
        for row in recipe:
            consumption_key = (
                uuid.UUID(str(row["product_id"])),
                uuid.UUID(str(row["storage_location_id"])),
                cast(ContainerKind | None, row.get("container_kind")),
                uuid.UUID(str(row["container_id"])) if row.get("container_id") else None,
            )
            consumption[consumption_key] = consumption.get(consumption_key, 0) + int(
                row["quantity"]
            )
    plan = await source_svc.plan_fbs_shipment_sources(
        session,
        tenant_id=tenant_id,
        supply_warehouse_id=warehouse_id,
        requests=requests,
        initial_consumption=consumption,
    )
    grouped_resolutions: dict[
        tuple[uuid.UUID, uuid.UUID, uuid.UUID, str | None, uuid.UUID | None], dict[str, Any]
    ] = {}
    for resolution in plan.resolutions:
        key = (
            resolution.fbs_order_id,
            resolution.product_id,
            resolution.storage_location_id,
            resolution.container_kind,
            resolution.container_id,
        )
        row = grouped_resolutions.setdefault(
            key,
            {
                "product_id": str(resolution.product_id),
                "storage_location_id": str(resolution.storage_location_id),
                "source_warehouse_id": str(resolution.source_warehouse_id),
                "container_kind": resolution.container_kind,
                "container_id": str(resolution.container_id) if resolution.container_id else None,
                "source_mode": resolution.source_mode,
                "quantity": 0,
                "negative_quantity": 0,
            },
        )
        row["quantity"] += resolution.quantity
        row["negative_quantity"] += resolution.negative_quantity
    for recipe_key, row in grouped_resolutions.items():
        recipes.setdefault(recipe_key[0], []).append(row)
    # Fulfillment and durable recipes keep their exact locations. Recalculate
    # their shortage too: stock may have changed since packing or a failed attempt.
    location_ids = {uuid.UUID(str(row["storage_location_id"]))
                    for recipe in recipes.values() for row in recipe}
    locations = {location.id: location for location in (
        await session.scalars(select(StorageLocation).where(
            StorageLocation.id.in_(location_ids), StorageLocation.tenant_id == tenant_id,
        ))
    ).all()}
    balances = {(balance.product_id, balance.storage_location_id,
                 balance.container_kind, balance.container_id): int(balance.quantity)
                for balance in (await session.scalars(select(InventoryBalance).where(
                    InventoryBalance.tenant_id == tenant_id,
                    InventoryBalance.storage_location_id.in_(location_ids),
                ))).all()}
    resolutions: list[source_svc.FbsShipmentSourceResolution] = []
    for order_id, recipe in recipes.items():
        for row in recipe:
            product_id = uuid.UUID(str(row["product_id"]))
            location_id = uuid.UUID(str(row["storage_location_id"]))
            location = locations.get(location_id)
            if location is None:
                raise OzonPackagingError("fbs_shipment_source_missing")
            container_kind = cast(ContainerKind | None, row.get("container_kind"))
            container_id = uuid.UUID(str(row["container_id"])) if row.get("container_id") else None
            stock_key = (product_id, location_id, container_kind, container_id)
            quantity = int(row["quantity"])
            positive = min(quantity, max(0, balances.get(stock_key, 0)))
            balances[stock_key] = balances.get(stock_key, 0) - quantity
            shortage = quantity - positive
            resolutions.append(source_svc.FbsShipmentSourceResolution(
                fbs_order_id=order_id, product_id=product_id, quantity=quantity,
                source_warehouse_id=location.warehouse_id, storage_location_id=location_id,
                container_kind=container_kind, container_id=container_id,
                source_mode=cast(
                    source_svc.FbsShipmentSourceMode, row.get("source_mode", "legacy_ledger"),
                ),
                positive_quantity=positive, shortage_quantity=shortage, negative_quantity=shortage,
            ))
    return source_svc.FbsShipmentSourcePlan(tenant_id, warehouse_id, tuple(resolutions))


async def prepare_shipment_sources(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    orders: list[FbsOrder],
    source_plan: source_svc.FbsShipmentSourcePlan | None = None,
) -> list[FbsShipmentReversalLedger]:
    """Stage exactly the plan checked at the handoff boundary, before calling Ozon."""
    plan = source_plan or await plan_shipment_sources(
        session, tenant_id=tenant_id, warehouse_id=warehouse_id, orders=orders,
    )
    ledgers = {ledger.fbs_order_id: ledger for ledger in (await session.scalars(
        select(FbsShipmentReversalLedger).where(
            FbsShipmentReversalLedger.tenant_id == tenant_id,
            FbsShipmentReversalLedger.fbs_order_id.in_([order.id for order in orders]),
        ).with_for_update()
    )).all()}
    recipes: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
    for item in plan.resolutions:
        recipes[item.fbs_order_id].append({
            "product_id": str(item.product_id),
            "storage_location_id": str(item.storage_location_id),
            "source_warehouse_id": str(item.source_warehouse_id),
            "container_kind": item.container_kind,
            "container_id": str(item.container_id) if item.container_id else None,
            "source_mode": item.source_mode,
            "quantity": item.quantity,
            "negative_quantity": item.negative_quantity,
        })
    for order_id, recipe in recipes.items():
        ledger = ledgers.get(order_id)
        if ledger is not None and ledger.shipment_movement_id is not None:
            continue
        first = recipe[0]
        if ledger is None:
            ledger = FbsShipmentReversalLedger(tenant_id=tenant_id, fbs_order_id=order_id)
            session.add(ledger)
            ledgers[order_id] = ledger
        ledger.product_id = uuid.UUID(str(first["product_id"]))
        ledger.storage_location_id = uuid.UUID(str(first["storage_location_id"]))
        ledger.source_warehouse_id = uuid.UUID(str(first["source_warehouse_id"]))
        ledger.quantity = sum(int(row["quantity"]) for row in recipe)
        ledger.negative_quantity = sum(int(row["negative_quantity"]) for row in recipe)
        ledger.shortage_quantity = ledger.negative_quantity
        ledger.ozon_positions_json = recipe
    await session.flush()
    return list(ledgers.values())


async def write_off_order(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    order: FbsOrder,
    actor_user_id: uuid.UUID | None,
    ledger: FbsShipmentReversalLedger | None = None,
) -> FbsShipmentReversalLedger:
    """Apply the saved source recipe only after confirmed marketplace handoff."""
    if ledger is None:
        if order.warehouse_id is None:
            raise OzonPackagingError("fbs_shipment_source_missing")
        prepared = await prepare_shipment_sources(
            session,
            tenant_id=tenant_id,
            warehouse_id=order.warehouse_id,
            orders=[order],
        )
        ledger = prepared[0]
    if ledger.shipment_movement_id is not None:
        return ledger
    if not ledger.ozon_positions_json:
        raise OzonPackagingError("fbs_shipment_source_missing")
    completed_recipe = [dict(row) for row in ledger.ozon_positions_json]
    for row in completed_recipe:
        quantity = int(str(row["quantity"]))
        allow_negative = int(str(row.get("negative_quantity", 0))) > 0
        values: dict[str, Any] = {
            "fbs_order_id": order.id,
            "tenant_id": tenant_id,
            "product_id": uuid.UUID(str(row["product_id"])),
            "storage_location_id": uuid.UUID(str(row["storage_location_id"])),
            "quantity": quantity,
            "actor_user_id": actor_user_id,
            "container_kind": cast(ContainerKind | None, row.get("container_kind")),
            "container_id": uuid.UUID(str(row["container_id"]))
            if row.get("container_id")
            else None,
        }
        try:
            async with session.begin_nested():
                movement = await inv_svc.apply_fbs_supply_write_off(
                    session,
                    **values,
                    allow_negative=allow_negative,
                )
        except ValueError as exc:
            if allow_negative or str(exc) != "insufficient stock":
                raise
            # Same policy as WB: external handoff is already confirmed. Record
            # the actual shortage instead of losing the local half of delivery.
            movement = await inv_svc.apply_fbs_supply_write_off(
                session,
                **values,
                allow_negative=True,
            )
            ledger.negative_quantity += quantity
            ledger.shortage_quantity += quantity
        await session.flush()
        row["movement_id"] = str(movement.id)
        if ledger.shipment_movement_id is None:
            ledger.shipment_movement_id = movement.id
    ledger.ozon_positions_json = completed_recipe
    await session.flush()
    return ledger
