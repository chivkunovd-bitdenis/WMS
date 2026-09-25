"""Atomic placement of accepted intake stock; existing movements remain the evidence."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeCargoPlace,
    InboundIntakeDistributionLine,
    InboundIntakeRequest,
)
from app.models.inventory_movement import (
    MOVEMENT_TYPE_STOCK_TRANSFER_IN,
    MOVEMENT_TYPE_STOCK_TRANSFER_OUT,
    InventoryMovement,
)
from app.models.warehouse_map_event import WarehouseMapEvent
from app.services import inbound_intake_service as intake
from app.services import inventory_service as inventory
from app.services import sorting_location_service as sorting
from app.services.catalog_service import get_storage_location_in_warehouse
from app.services.defect_warehouse_service import get_or_create_defect_location


async def apply_loose_putaway(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    operation_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    quantity: int,
    performer_id: uuid.UUID | None,
    commit: bool = True,
) -> InboundIntakeRequest:
    req = await intake.get_request(session, tenant_id, request_id, for_update=True)
    if req is None:
        raise intake.InboundIntakeError("request_not_found")
    prior = await session.get(InboundIntakeDistributionLine, operation_id)
    if prior is not None:
        if (
            prior.request_id,
            prior.product_id,
            prior.storage_location_id,
            prior.quantity,
            prior.box_id,
        ) != (request_id, product_id, storage_location_id, quantity, None):
            raise intake.InboundIntakeError("operation_conflict")
        return req
    if req.status != intake.STATUS_SORTING:
        raise intake.InboundIntakeError("not_distributable")
    line = next((line for line in req.lines if line.product_id == product_id), None)
    if line is None:
        raise intake.InboundIntakeError("product_not_on_request")
    containers: list[InboundIntakeBox | InboundIntakeCargoPlace] = [*req.boxes, *req.cargo_places]
    pending_containers = sum(
        max(0, row.quantity - row.posted_qty)
        for container in containers
        for row in container.lines
        if row.product_id == product_id
    )
    remaining = intake._accepted_qty_for_line(line) - line.posted_qty - pending_containers
    if quantity < 1:
        raise intake.InboundIntakeError("invalid_qty")
    if quantity > remaining:
        raise intake.InboundIntakeError("qty_exceeds_accepted")
    loc = await get_storage_location_in_warehouse(
        session, tenant_id, req.warehouse_id, storage_location_id
    )
    if loc is None:
        raise intake.InboundIntakeError("location_not_found")
    if sorting.is_sorting_location(loc):
        raise intake.InboundIntakeError("sorting_location_reserved")
    source = await sorting.get_or_create_sorting_location(session, tenant_id, req.warehouse_id)
    good_total = max(0, intake._accepted_qty_for_line(line) - line.defective_qty)
    good = min(quantity, max(0, good_total - line.posted_qty))
    destinations = [(storage_location_id, good)] if good else []
    if quantity > good:
        defect = await get_or_create_defect_location(session, tenant_id)
        destinations.append((defect.id, quantity - good))
    # The exact loose source cannot consume another box when a stale client asks
    # for more than physically remains. Product locking serializes shared stock.
    try:
        for target, qty in destinations:
            group_id = operation_id
            await inventory.record_movement_and_adjust_balance(
                session,
                tenant_id=tenant_id,
                product_id=product_id,
                storage_location_id=source.id,
                quantity_delta=-qty,
                movement_type=MOVEMENT_TYPE_STOCK_TRANSFER_OUT,
                inbound_intake_line_id=line.id,
                transfer_group_id=group_id,
                actor_user_id=performer_id,
                _exact_source=True,
            )
            await inventory.record_movement_and_adjust_balance(
                session,
                tenant_id=tenant_id,
                product_id=product_id,
                storage_location_id=target,
                quantity_delta=qty,
                movement_type=MOVEMENT_TYPE_STOCK_TRANSFER_IN,
                inbound_intake_line_id=line.id,
                transfer_group_id=group_id,
                actor_user_id=performer_id,
            )
    except ValueError as exc:
        if str(exc) == "insufficient stock":
            raise intake.InboundIntakeError("insufficient_sorting_stock") from exc
        raise
    # The map journal is the existing visible history of a placement.  Keep its
    # id equal to the durable placement operation so a replay exits above before
    # it can add a second row or replace the original server-authenticated actor.
    session.add(
        WarehouseMapEvent(
            id=operation_id,
            tenant_id=tenant_id,
            warehouse_id=req.warehouse_id,
            actor_user_id=performer_id,
            subject=line.product.name,
            quantity=quantity,
            from_label=sorting.SORTING_LOCATION_LABEL,
            to_label=loc.code,
        )
    )
    session.add(
        InboundIntakeDistributionLine(
            id=operation_id,
            request_id=request_id,
            product_id=product_id,
            storage_location_id=storage_location_id,
            quantity=quantity,
        )
    )
    line.posted_qty += quantity
    intake._maybe_set_distribution_completed(req)
    intake._maybe_complete_request(req)
    await intake._record_charge_if_done(session, req, performer_id=performer_id)
    await session.flush()
    if commit:
        await session.commit()
    return req


async def _link_proven_historical_movements(
    session: AsyncSession,
    req: InboundIntakeRequest,
    sorting_location_id: uuid.UUID,
) -> int:
    """Recover missing document links only from unambiguous source-ledger ownership.

    A shared loose balance is not evidence of which intake moved. We replay its
    source history; once owners mix, an unlinked partial withdrawal stays unknown
    until that source is emptied. No movement or stock quantity is created here.
    """
    from collections import defaultdict
    from itertools import groupby

    from app.models.inventory_balance import InventoryBalance

    line_ids = {line.id for line in req.lines}
    inferred: dict[uuid.UUID, uuid.UUID] = {}
    group_ids: set[uuid.UUID] = set()
    for line in sorted(req.lines, key=lambda row: str(row.product_id)):
        await inventory.lock_stock_product(session, req.tenant_id, line.product_id)
        rows = list(
            (
                await session.scalars(
                    select(InventoryMovement)
                    .where(
                        InventoryMovement.tenant_id == req.tenant_id,
                        InventoryMovement.product_id == line.product_id,
                        InventoryMovement.storage_location_id == sorting_location_id,
                    )
                    .order_by(InventoryMovement.created_at, InventoryMovement.id)
                )
            ).all()
        )
        ledger_totals: dict[tuple[str | None, uuid.UUID | None], int] = defaultdict(int)
        for movement in rows:
            ledger_totals[(movement.container_kind, movement.container_id)] += (
                movement.quantity_delta
            )
        balances = list(
            (
                await session.scalars(
                    select(InventoryBalance).where(
                        InventoryBalance.tenant_id == req.tenant_id,
                        InventoryBalance.product_id == line.product_id,
                        InventoryBalance.storage_location_id == sorting_location_id,
                    )
                )
            ).all()
        )
        actual_totals = {(row.container_kind, row.container_id): row.quantity for row in balances}
        unproven_sources = {
            key
            for key in set(ledger_totals) | set(actual_totals)
            if ledger_totals.get(key, 0) != actual_totals.get(key, 0)
        }
        owners: dict[tuple[str | None, uuid.UUID | None], dict[uuid.UUID | None, int]] = (
            defaultdict(dict)
        )
        for _timestamp, batch_iter in groupby(rows, key=lambda row: row.created_at):
            batch = list(batch_iter)
            # Same-transaction timestamps carry no reliable intra-batch order.
            # Include every incoming owner before inferring any withdrawal.
            for movement in batch:
                if movement.quantity_delta > 0:
                    pool = owners[(movement.container_kind, movement.container_id)]
                    owner = movement.inbound_intake_line_id
                    pool[owner] = pool.get(owner, 0) + movement.quantity_delta
            for movement in batch:
                if movement.quantity_delta >= 0:
                    continue
                pool = owners[(movement.container_kind, movement.container_id)]
                qty = -movement.quantity_delta
                owner = movement.inbound_intake_line_id
                positive = {key: amount for key, amount in pool.items() if amount > 0}
                if owner is None and len(positive) == 1 and None not in positive:
                    owner = next(iter(positive))
                if owner is not None and pool.get(owner, 0) >= qty:
                    pool[owner] -= qty
                    if (
                        movement.movement_type == "warehouse_map_move"
                        and movement.transfer_group_id is not None
                        and (movement.container_kind, movement.container_id) not in unproven_sources
                    ):
                        inferred[movement.id] = owner
                        group_ids.add(movement.transfer_group_id)
                else:
                    remaining = max(0, sum(positive.values()) - qty)
                    pool.clear()
                    if remaining:
                        pool[None] = remaining
    linked = 0
    for group_id in sorted(group_ids, key=str):
        group_rows = list(
            (
                await session.scalars(
                    select(InventoryMovement).where(
                        InventoryMovement.tenant_id == req.tenant_id,
                        InventoryMovement.transfer_group_id == group_id,
                    )
                )
            ).all()
        )
        for product_id in {row.product_id for row in group_rows}:
            paired = [row for row in group_rows if row.product_id == product_id]
            sources = [row for row in paired if row.quantity_delta < 0]
            targets = [row for row in paired if row.quantity_delta > 0]
            owners_for_group = {inferred.get(row.id, row.inbound_intake_line_id) for row in sources}
            if len(owners_for_group) != 1:
                continue
            owner = next(iter(owners_for_group))
            if owner not in line_ids or owner is None or not targets:
                continue
            if any(row.storage_location_id != sorting_location_id for row in sources):
                continue
            if any(row.storage_location_id == sorting_location_id for row in targets):
                continue
            if sum(row.quantity_delta for row in paired) != 0 or any(
                row.inbound_intake_line_id not in {None, owner} for row in paired
            ):
                continue
            for row in paired:
                if row.inbound_intake_line_id is None:
                    row.inbound_intake_line_id = owner
                    linked += 1
    await session.flush()
    return linked


async def reconcile_linked_putaway(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> InboundIntakeRequest:
    """Repair only quantities proven by linked outbound sorting movements.

    This explicit service is for an authorized repair of one document, never a
    GET-side bulk correction or an inference from an empty warehouse map.
    """
    req = await intake.get_request(session, tenant_id, request_id, for_update=True)
    if req is None:
        raise intake.InboundIntakeError("request_not_found")
    if req.status == intake.STATUS_DONE:
        return req
    if req.status != intake.STATUS_SORTING:
        raise intake.InboundIntakeError("not_distributable")
    source = await sorting.get_or_create_sorting_location(session, tenant_id, req.warehouse_id)
    existing_rows = list(
        (
            await session.scalars(
                select(InboundIntakeDistributionLine).where(
                    InboundIntakeDistributionLine.request_id == req.id,
                )
            )
        ).all()
    )
    backed_rows = await intake._distribution_posted_quantities(session, req, existing_rows)
    actor = req.completed_by_user_id
    latest_movement = None
    changed = bool(await _link_proven_historical_movements(session, req, source.id))
    has_proof = False
    for line in req.lines:
        movements = list(
            (
                await session.scalars(
                    select(InventoryMovement)
                    .where(
                        InventoryMovement.tenant_id == tenant_id,
                        InventoryMovement.inbound_intake_line_id == line.id,
                        InventoryMovement.storage_location_id == source.id,
                        InventoryMovement.quantity_delta < 0,
                        InventoryMovement.movement_type.in_(
                            [
                                MOVEMENT_TYPE_STOCK_TRANSFER_OUT,
                                "warehouse_map_move",
                            ]
                        ),
                        InventoryMovement.transfer_group_id.is_not(None),
                    )
                    .order_by(InventoryMovement.created_at, InventoryMovement.id)
                )
            ).all()
        )
        proven = 0
        proven_destinations: dict[uuid.UUID, InventoryMovement] = {}
        proven_movements = []
        for movement in movements:
            destinations = list(
                (
                    await session.scalars(
                        select(InventoryMovement).where(
                            InventoryMovement.tenant_id == tenant_id,
                            InventoryMovement.transfer_group_id == movement.transfer_group_id,
                            InventoryMovement.product_id == line.product_id,
                            InventoryMovement.quantity_delta > 0,
                            InventoryMovement.storage_location_id != source.id,
                        )
                    )
                ).all()
            )
            group_out = sum(
                -row.quantity_delta
                for row in movements
                if row.transfer_group_id == movement.transfer_group_id
            )
            if sum(row.quantity_delta for row in destinations) != group_out:
                continue
            has_proof = True
            proven_destinations.update({row.id: row for row in destinations})
            proven_movements.append(movement)
            proven += -movement.quantity_delta
            if latest_movement is None or movement.created_at > latest_movement.created_at:
                latest_movement = movement
                actor = req.completed_by_user_id or movement.actor_user_id
        if proven > intake._accepted_qty_for_line(line):
            raise intake.InboundIntakeError("qty_exceeds_accepted")
        if proven > line.posted_qty:
            line.posted_qty = proven
            changed = True
        represented = sum(
            backed_rows.get(row.id, 0) for row in existing_rows if row.product_id == line.product_id
        )
        missing_rows_qty = max(0, proven - represented)
        represented_at: dict[uuid.UUID, int] = {}
        for row in existing_rows:
            if row.product_id == line.product_id:
                represented_at[row.storage_location_id] = represented_at.get(
                    row.storage_location_id, 0
                ) + backed_rows.get(row.id, 0)
        for target in proven_destinations.values():
            if missing_rows_qty == 0:
                break
            if any(row.id == target.id for row in existing_rows):
                continue
            covered = min(target.quantity_delta, represented_at.get(target.storage_location_id, 0))
            represented_at[target.storage_location_id] = (
                represented_at.get(target.storage_location_id, 0) - covered
            )
            quantity = min(missing_rows_qty, target.quantity_delta - covered)
            if quantity == 0:
                continue
            session.add(
                InboundIntakeDistributionLine(
                    id=target.id,
                    request_id=req.id,
                    product_id=line.product_id,
                    storage_location_id=target.storage_location_id,
                    quantity=quantity,
                    box_id=target.container_id
                    if target.container_kind == "box"
                    and any(box.id == target.container_id for box in req.boxes)
                    else None,
                )
            )
            missing_rows_qty -= quantity
            changed = True
        if proven > 0:
            containers: list[InboundIntakeBox | InboundIntakeCargoPlace] = [
                *req.boxes,
                *req.cargo_places,
            ]
            for container in containers:
                for container_row in container.lines:
                    if container_row.product_id != line.product_id:
                        continue
                    container_proven = sum(
                        -movement.quantity_delta
                        for movement in proven_movements
                        if movement.container_id == container.id
                    )
                    if container_proven > container_row.quantity:
                        raise intake.InboundIntakeError("qty_exceeds_box_remaining")
                    if container_proven > container_row.posted_qty:
                        container_row.posted_qty = container_proven
                        changed = True
    if has_proof and all(
        line.posted_qty >= intake._accepted_qty_for_line(line) for line in req.lines
    ):
        changed = True
    if not has_proof:
        raise intake.InboundIntakeError("sorting_reconciliation_unproven")
    if changed:
        if latest_movement is not None and all(
            line.posted_qty >= intake._accepted_qty_for_line(line) for line in req.lines
        ):
            if req.posted_at is None:
                req.posted_at = latest_movement.created_at
            if req.distribution_completed_at is None:
                req.distribution_completed_at = latest_movement.created_at
        intake._maybe_set_distribution_completed(req)
        intake._maybe_complete_request(req)
        await intake._record_charge_if_done(session, req, performer_id=actor)
        await session.commit()
    return req


async def apply_received_balance_putaway(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    balance_id: uuid.UUID,
    destination_location_id: uuid.UUID,
    destination_container_kind: str | None,
    destination_container_id: uuid.UUID | None,
    quantity: int,
    performer_id: uuid.UUID,
    request_id: uuid.UUID | None = None,
    transfer_group_id: uuid.UUID | None = None,
) -> bool:
    """Bridge physical cargo/pallet contents to their original accepted document."""
    from app.models.inventory_balance import InventoryBalance
    from app.models.pallet import Pallet
    from app.models.storage_location import StorageLocation
    from app.models.warehouse_box import WarehouseBox

    balance = await session.get(InventoryBalance, balance_id)
    if balance is None or balance.tenant_id != tenant_id:
        return False
    source = await session.get(StorageLocation, balance.storage_location_id)
    target = await session.get(StorageLocation, destination_location_id)
    if source is None or target is None or not sorting.is_sorting_location(source):
        return False
    if sorting.is_sorting_location(target):
        return False
    container_request_id = None
    if balance.container_kind == "box":
        box = await session.get(InboundIntakeBox, balance.container_id)
        if box is not None and box.tenant_id == tenant_id:
            container_request_id = box.request_id
    elif balance.container_kind == "cargo_place":
        cargo = await session.get(InboundIntakeCargoPlace, balance.container_id)
        if cargo is not None and cargo.tenant_id == tenant_id:
            container_request_id = cargo.request_id
    elif balance.container_kind == "pallet":
        pallet = await session.get(Pallet, balance.container_id)
        if pallet is not None and pallet.tenant_id == tenant_id:
            container_request_id = pallet.inbound_request_id
    if container_request_id is None and balance.container_id is not None:
        generic = await session.get(WarehouseBox, balance.container_id)
        if generic is not None and generic.tenant_id == tenant_id:
            container_request_id = generic.inbound_request_id
    if request_id is not None and container_request_id not in {None, request_id}:
        raise intake.InboundIntakeError("product_not_on_request")
    request_id = request_id or container_request_id
    if request_id is None:
        return False
    req = await intake.get_request(session, tenant_id, request_id, for_update=True)
    if req is None or req.warehouse_id != source.warehouse_id:
        raise intake.InboundIntakeError("request_not_found")
    if req.status != intake.STATUS_SORTING:
        return False
    line = next((row for row in req.lines if row.product_id == balance.product_id), None)
    if line is None:
        raise intake.InboundIntakeError("product_not_on_request")
    if quantity > intake._accepted_qty_for_line(line) - line.posted_qty:
        raise intake.InboundIntakeError("qty_exceeds_accepted")
    containers: list[InboundIntakeBox | InboundIntakeCargoPlace] = [*req.boxes, *req.cargo_places]
    container_line = next(
        (
            row
            for container in containers
            if container.id == balance.container_id
            for row in container.lines
            if row.product_id == line.product_id
        ),
        None,
    )
    if (
        container_line is not None
        and quantity > container_line.quantity - container_line.posted_qty
    ):
        raise intake.InboundIntakeError("qty_exceeds_box_remaining")
    from typing import cast

    from app.services.inventory_container_service import ContainerKind

    try:
        await intake._apply_line_putaway(
            session,
            tenant_id,
            line=line,
            sorting_location_id=source.id,
            normal_location_id=destination_location_id,
            quantity=quantity,
            actor_user_id=performer_id,
            source_container_kind=cast(ContainerKind | None, balance.container_kind),
            source_container_id=balance.container_id,
            destination_container_kind=cast(ContainerKind | None, destination_container_kind),
            destination_container_id=destination_container_id,
            transfer_group_id=transfer_group_id,
        )
    except ValueError as exc:
        if str(exc) == "insufficient stock":
            raise intake.InboundIntakeError("insufficient_sorting_stock") from exc
        raise
    line.posted_qty += quantity
    if container_line is not None:
        container_line.posted_qty += quantity
    session.add(
        InboundIntakeDistributionLine(
            request_id=req.id,
            product_id=line.product_id,
            storage_location_id=destination_location_id,
            quantity=quantity,
            box_id=balance.container_id
            if balance.container_kind == "box"
            and any(box.id == balance.container_id for box in req.boxes)
            else None,
        )
    )
    intake._maybe_set_distribution_completed(req)
    intake._maybe_complete_request(req)
    await intake._record_charge_if_done(session, req, performer_id=performer_id)
    await session.flush()
    return True
