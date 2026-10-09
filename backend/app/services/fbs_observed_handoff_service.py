"""Read-only marketplace observations and the recoverable local half of handover.

The existing operation journal persists evidence before accounting starts. Supply
then order locks fence cancellation, regular delivery and concurrent pollers. No
marketplace mutation belongs in this module.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Integer, cast, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_order import (
    FbsOrder,
    FbsOrderProduct,
    FbsOrderProductReservation,
    FbsOrderReservation,
)
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger as Ledger
from app.models.fbs_supply import FbsSupply
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.product import Product

OBSERVATION_KIND = "observed_handoff"
NEGATIVE = frozenset(
    {
        "cancel",
        "cancel_carrier",
        "canceled",
        "declined_by_client",
        "canceled_by_client",
        "canceled_by_carrier",
        "defect",
        "cancelled",
        "not_accepted",
        "arbitration",
    }
)


def terminal_repair_condition(session: AsyncSession) -> Any:
    """Done orders without a persisted expense stay in the bounded polling queue."""
    postgres = session.get_bind().dialect.name == "postgresql"
    elements = (
        (
            func.json_array_elements(Ledger.ozon_positions_json)
            if postgres
            else func.json_each(Ledger.ozon_positions_json)
        )
        .table_valued("value")
        .alias("observed_recipe")
    )
    movement_id = (
        elements.c.value.op("->>")("movement_id")
        if postgres
        else func.json_extract(elements.c.value, "$.movement_id")
    )
    cancellation = (
        elements.c.value.op("->>")("cancelled_postings")
        if postgres
        else func.json_extract(elements.c.value, "$.cancelled_postings")
    )
    unfinished = exists(
        select(1)
        .select_from(elements)
        .where(
            movement_id.is_(None),
            cancellation.is_(None),
        )
    )
    quantity = (
        cast(elements.c.value.op("->>")("quantity"), Integer)
        if postgres
        else func.json_extract(elements.c.value, "$.quantity")
    )
    completed = (
        select(func.coalesce(func.sum(quantity), 0))
        .select_from(elements)
        .where(
            or_(movement_id.is_not(None), cancellation.is_not(None)),
        )
        .correlate(Ledger)
        .scalar_subquery()
    )
    required = (
        select(func.coalesce(func.sum(FbsOrderProduct.quantity), 1))
        .where(
            FbsOrderProduct.order_id == FbsOrder.id,
        )
        .correlate(FbsOrder)
        .scalar_subquery()
    )
    return (
        (FbsOrder.status == "done")
        & exists(
            select(FbsSupply.id).where(
                FbsSupply.id == FbsOrder.supply_id,
                FbsSupply.source == "wms",
                FbsSupply.tenant_id == FbsOrder.tenant_id,
                FbsSupply.seller_id == FbsOrder.seller_id,
                FbsSupply.marketplace == FbsOrder.marketplace,
            )
        )
        & or_(
            ~exists(
                select(Ledger.id).where(
                    Ledger.fbs_order_id == FbsOrder.id,
                    Ledger.shipment_movement_id.is_not(None),
                )
            ),
            exists(
                select(Ledger.id).where(
                    Ledger.fbs_order_id == FbsOrder.id,
                    Ledger.reversed_at.is_(None),
                    or_(
                        unfinished, Ledger.ozon_positions_json.is_not(None) & (completed < required)
                    ),
                )
            ),
        )
    )


def expected_quantities(order: FbsOrder) -> dict[uuid.UUID, int]:
    if order.marketplace == "ozon" and order.product_positions:
        if any(p.product_id is None or p.quantity < 1 for p in order.product_positions):
            return {}
        quantities: Counter[uuid.UUID] = Counter()
        for position in order.product_positions:
            assert position.product_id is not None
            quantities[position.product_id] += position.quantity
        return dict(quantities)
    return {order.product_id: 1} if order.product_id is not None else {}


def completed_quantities(ledger: Ledger | None) -> dict[uuid.UUID, int]:
    if ledger is None or ledger.reversed_at is not None:
        return {}
    if ledger.ozon_positions_json:
        result: Counter[uuid.UUID] = Counter()
        for row in ledger.ozon_positions_json:
            if row.get("movement_id"):
                result[uuid.UUID(str(row["product_id"]))] += int(str(row["quantity"]))
        return dict(result)
    if ledger.shipment_movement_id is not None:
        return {ledger.product_id: ledger.quantity}
    return {}


def observation_scope(order: FbsOrder) -> dict[str, Any]:
    """Fence a response to the exact association and composition read before I/O."""
    return {
        "tenant_id": str(order.tenant_id),
        "seller_id": str(order.seller_id),
        "supply_id": str(order.supply_id),
        "warehouse_id": str(order.warehouse_id),
        "marketplace": order.marketplace,
        "wb_order_id": order.wb_order_id,
        "wb_supply_id": order.wb_supply_id,
        "posting_number": order.external_order_id,
        "posting_numbers": ((order.meta_details_json or {}).get("ozon_assembly") or {}).get(
            "posting_numbers",
            [],
        ),
        "positions": sorted(
            [
                [str(p.id), str(p.product_id), p.ozon_sku, p.quantity]
                for p in order.product_positions
            ],
            key=lambda row: str(row[0]),
        ),
    }


def make_observation(
    order: FbsOrder,
    targets: dict[uuid.UUID, int],
    row: dict[str, Any] | None,
    children: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = row or {}
    return {
        "scope": observation_scope(order),
        "targets": {str(pid): qty for pid, qty in targets.items()},
        "status": {
            key: raw.get(key)
            for key in (
                "status",
                "substatus",
                "supplierStatus",
                "wbStatus",
                "posting_number",
                "products",
            )
            if key in raw
        },
        "reason": None if targets else "unknown",
        "children": children or {},
    }


def wb_proves_handoff(row: dict[str, Any]) -> bool:
    supplier = str(row.get("supplierStatus") or "").lower()
    status = str(row.get("wbStatus") or "").lower()
    if supplier in NEGATIVE or status in NEGATIVE:
        return False
    return (
        supplier == "complete" and status in {"waiting", "sorted", "ready_for_pickup", "sold"}
    ) or (supplier in {"confirm", "complete"} and status in {"sorted", "ready_for_pickup", "sold"})


def ozon_proves_handoff(row: dict[str, Any]) -> bool:
    status = row.get("status")
    substatus = row.get("substatus")
    if status in NEGATIVE or substatus in NEGATIVE:
        return False
    return status in {"delivering", "driver_pickup", "delivered"} and substatus in {
        None,
        "",
        "posting_delivered",
        "posting_received",
        "posting_in_pickup_point",
        "posting_on_way_to_city",
    }


def card_quantities(order: FbsOrder, row: dict[str, Any]) -> dict[uuid.UUID, int] | None:
    """Match provider SKU and units, refusing missing, repeated or conflicting rows."""
    products = row.get("products")
    if not isinstance(products, list) or not products:
        return None
    positions = list(order.product_positions)
    result: Counter[uuid.UUID] = Counter()
    seen: set[int] = set()
    for product in products:
        if not isinstance(product, dict):
            return None
        sku = product.get("sku")
        quantity = product.get("quantity")
        if isinstance(sku, bool) or not isinstance(sku, (str, int)):
            return None
        try:
            sku = int(sku)
        except ValueError:
            return None
        if (
            sku in seen
            or isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or quantity < 1
        ):
            return None
        seen.add(sku)
        matches = [p for p in positions if p.ozon_sku == sku]
        if len(matches) != 1 or matches[0].product_id is None:
            return None
        position = matches[0]
        assert position.product_id is not None
        if product.get("offer_id") and position.offer_id != product["offer_id"]:
            return None
        result[position.product_id] += quantity
    return dict(result)


async def ozon_targets(
    order: FbsOrder,
    row: dict[str, Any] | None,
    provider: Any,
    client_id: str,
    api_key: str,
) -> tuple[dict[uuid.UUID, int], dict[str, Any]]:
    if row is None or row.get("posting_number") != order.external_order_id:
        return {}, {}
    expected = expected_quantities(order)
    if not expected:
        return {}, {}
    assembly = (order.meta_details_json or {}).get("ozon_assembly") or {}
    children = assembly.get("posting_numbers") or []
    if row.get("status") == "cancelled_from_split_pending":
        related = row.get("related_postings") or {}
        remote_children = related.get("related_posting_numbers") or []
        if (
            not children
            or len(set(children)) != len(children)
            or set(children) != set(remote_children)
            or order.external_order_id in children
        ):
            return {}, {}
        cards = await provider.fetch_statuses(
            client_id=client_id, api_key=api_key, order_ids=children
        )
        by_number = {c.get("posting_number"): c for c in cards}
        if len(cards) != len(children) or set(by_number) != set(children):
            return {}, {}
        total: Counter[uuid.UUID] = Counter()
        proved: Counter[uuid.UUID] = Counter()
        child_evidence: dict[str, Any] = {}
        for child in children:
            quantities = card_quantities(order, by_number[child])
            if quantities is None:
                return {}, {}
            total.update(quantities)
            positive = ozon_proves_handoff(by_number[child])
            cancelled = by_number[child].get("status") == "cancelled"
            child_evidence[child] = {
                "quantities": {str(pid): qty for pid, qty in quantities.items()},
                "positive": positive,
                "cancelled": cancelled,
                "prior_positive": positive,
                "status": by_number[child].get("status"),
                "substatus": by_number[child].get("substatus"),
            }
            if positive:
                proved.update(quantities)
        return (dict(proved), child_evidence) if dict(total) == expected else ({}, {})
    quantities = card_quantities(order, row)
    return (quantities, {}) if quantities == expected and ozon_proves_handoff(row) else ({}, {})


def snapshot_targets(order: FbsOrder, snapshot: dict[str, Any]) -> dict[uuid.UUID, int]:
    """Validate immutable identity and cap expense at the pre-HTTP quantities."""
    old_scope = snapshot.get("scope") or {}
    current_scope = observation_scope(order)
    if any(
        old_scope.get(key) != value
        for key, value in current_scope.items()
        if key != "positions"
    ):
        return {}
    old_positions = old_scope.get("positions") or []
    current_positions = {str(p.id): p for p in order.product_positions}
    if any(
        str(row[0]) not in current_positions
        or (
            str(current_positions[str(row[0])].product_id) != str(row[1])
            or current_positions[str(row[0])].ozon_sku != row[2]
            or current_positions[str(row[0])].quantity < row[3]
        )
        for row in old_positions
    ):
        return {}
    quantities = {
        uuid.UUID(pid): int(qty) for pid, qty in (snapshot.get("quantities") or {}).items()
    }
    expected = expected_quantities(order)
    return quantities if quantities and all(
        0 < qty <= expected.get(pid, 0) for pid, qty in quantities.items()
    ) else {}


async def checkpoint_targets(
    session: AsyncSession,
    order: FbsOrder,
    operation: FbsWbOperation,
) -> dict[uuid.UUID, int]:
    """An approve covers its saved postings and source quantities, never current totals."""
    summary = operation.request_summary_json or {}
    progress = summary.get("ozon_handoff_progress") or {}
    if progress.get("carriage_approved") is not True or not progress.get("carriage_id"):
        return {}
    assembly = (order.meta_details_json or {}).get("ozon_assembly") or {}
    numbers = assembly.get("posting_numbers") or []
    approved_numbers = summary.get("ozon_approved_postings", progress.get("posting_numbers"))
    if not numbers or len(set(numbers)) != len(numbers):
        return {}
    if isinstance(approved_numbers, list):
        if not approved_numbers or not set(numbers).issubset(set(approved_numbers)):
            return {}
    else:
        # Old singleton checkpoints did not store a posting list. Their one
        # staged recipe can identify one participant, but never an expanded supply.
        participant_ids = list(
            await session.scalars(
                select(FbsOrder.id).where(
                    FbsOrder.supply_id == operation.local_entity_id,
                    FbsOrder.tenant_id == operation.tenant_id,
                    FbsOrder.status != "cancelled",
                )
            )
        )
        if participant_ids != [order.id] or numbers != [order.external_order_id]:
            return {}
    snapshot = (summary.get("ozon_handoff_orders") or {}).get(str(order.id))
    if summary.get("ozon_handoff_orders_complete") is True and not isinstance(snapshot, dict):
        return {}
    if isinstance(snapshot, dict):
        return snapshot_targets(order, snapshot)
    else:
        # Fence and freeze the legacy source recipe before stock preparation can
        # extend it to a newly enlarged local quantity. No HTTP follows this lock.
        await session.scalar(
            select(FbsSupply.id)
            .where(
                FbsSupply.id == operation.local_entity_id,
                FbsSupply.tenant_id == operation.tenant_id,
            )
            .with_for_update()
        )
        await session.refresh(operation)
        snapshot = ((operation.request_summary_json or {}).get("ozon_handoff_orders") or {}).get(
            str(order.id),
        )
        if isinstance(snapshot, dict):
            return await checkpoint_targets(session, order, operation)
        # Existing immutable source recipe is the historical quantity snapshot.
        ledger = await session.scalar(
            select(Ledger).where(
                Ledger.tenant_id == operation.tenant_id,
                Ledger.fbs_order_id == order.id,
            )
        )
        if ledger is None or ledger.reversed_at is not None or not ledger.ozon_positions_json:
            return {}
        quantities_counter: Counter[uuid.UUID] = Counter()
        for recipe_row in ledger.ozon_positions_json:
            quantities_counter[uuid.UUID(str(recipe_row["product_id"]))] += int(
                str(recipe_row["quantity"]),
            )
        quantities = dict(quantities_counter)
        operation_summary = dict(operation.request_summary_json or {})
        if isinstance(approved_numbers, list):
            operation_summary.setdefault("ozon_approved_postings", list(approved_numbers))
        snapshots = dict(operation_summary.get("ozon_handoff_orders") or {})
        snapshots[str(order.id)] = {
            "scope": observation_scope(order),
            "quantities": {str(pid): qty for pid, qty in quantities.items()},
        }
        operation_summary["ozon_handoff_orders"] = snapshots
        operation.request_summary_json = operation_summary
    expected = expected_quantities(order)
    return (
        quantities
        if quantities and all(0 < qty <= expected.get(pid, 0) for pid, qty in quantities.items())
        else {}
    )


def child_totals(children: dict[str, Any], *, cancelled: bool) -> Counter[uuid.UUID]:
    result: Counter[uuid.UUID] = Counter()
    for child in children.values():
        selected = child.get("cancelled") if cancelled else child.get("positive")
        if selected:
            result.update({uuid.UUID(pid): int(qty) for pid, qty in child["quantities"].items()})
    return result


async def save_observations(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    observations: dict[uuid.UUID, dict[str, Any]],
) -> None:
    """Commit evidence separately, so a failed stock transaction can resume it."""
    supply_ids = list(
        await session.scalars(
            select(FbsOrder.supply_id)
            .where(
                FbsOrder.id.in_(observations),
                FbsOrder.tenant_id == tenant_id,
                FbsOrder.seller_id == seller_id,
                FbsOrder.supply_id.is_not(None),
            )
            .distinct()
        )
    )
    for supply_id in sorted(supply_ids, key=str):
        supply = await session.scalar(
            select(FbsSupply)
            .where(
                FbsSupply.id == supply_id,
                FbsSupply.tenant_id == tenant_id,
                FbsSupply.seller_id == seller_id,
                FbsSupply.source == "wms",
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if supply is None:
            continue
        operation = await session.scalar(
            select(FbsWbOperation).where(
                FbsWbOperation.tenant_id == tenant_id,
                FbsWbOperation.seller_id == seller_id,
                FbsWbOperation.operation_kind == OBSERVATION_KIND,
                FbsWbOperation.local_entity_id == supply.id,
            )
        )
        if operation is None:
            operation = FbsWbOperation(
                tenant_id=tenant_id,
                seller_id=seller_id,
                operation_kind=OBSERVATION_KIND,
                idempotency_key=f"observed:{supply.id}",
                local_entity_type="fbs_supply",
                local_entity_id=supply.id,
                wb_object_id=supply.wb_supply_id or supply.external_supply_id,
                state="pending_confirmation",
            )
            session.add(operation)
        evidence = dict((operation.response_summary_json or {}).get("orders") or {})
        local_orders = list(
            await session.scalars(
                select(FbsOrder)
                .where(
                    FbsOrder.supply_id == supply.id,
                    FbsOrder.tenant_id == tenant_id,
                    FbsOrder.seller_id == seller_id,
                    FbsOrder.marketplace == supply.marketplace,
                    FbsOrder.warehouse_id == supply.warehouse_id,
                )
                .options(selectinload(FbsOrder.product_positions))
            )
        )
        for order in local_orders:
            observation = observations.get(order.id)
            if observation is None:
                continue
            if observation.get("scope") != observation_scope(order):
                continue
            if supply.marketplace == "wb" and order.wb_supply_id != supply.wb_supply_id:
                continue
            previous = evidence.get(str(order.id)) or {}
            children = observation.get("children") or {}
            same_scope = previous.get("scope") == observation.get("scope")
            old_children = (previous.get("children") or {}) if same_scope else {}
            if children:
                for number, child in children.items():
                    old = old_children.get(number) or {}
                    if old.get("quantities") and old["quantities"] != child["quantities"]:
                        children = {}
                        observation["targets"] = {}
                        observation["reason"] = "split_composition_changed"
                        break
                    from app.services.ozon_fbs_status_service import (
                        CONFIRMED_STAGE_KEY,
                        posting_stage,
                    )

                    previous_stage = old.get(CONFIRMED_STAGE_KEY)
                    if previous_stage is None and old:
                        previous_stage = posting_stage(
                            old.get("status"), old.get("substatus"),
                            handed=bool(old.get("prior_positive")),
                        )
                    child[CONFIRMED_STAGE_KEY] = posting_stage(
                        child.get("status"), child.get("substatus"),
                        handed=bool(child.get("positive") or old.get("prior_positive")),
                        previous=previous_stage,
                    )
                    child["previous_positive"] = bool(old.get("prior_positive"))
                    child["prior_positive"] = bool(
                        old.get("prior_positive")
                        or (child["positive"] and not old.get("cancelled"))
                    )
                    if old.get("cancelled"):
                        child["cancelled"] = True
                        child["positive"] = False
                observation["children"] = children
                observation["targets"] = {
                    str(pid): qty for pid, qty in child_totals(children, cancelled=False).items()
                }
            # Preserve proven quantities through temporary read failures; cancellation
            # is fenced by the authoritative order state when accounting resumes.
            if (
                children
                or observation.get("targets")
                or not (previous.get("targets") or previous.get("children"))
            ):
                evidence[str(order.id)] = observation
        operation.response_summary_json = {"orders": evidence}
        operation.error_code = (
            "observed_handoff_unknown"
            if not any(row.get("targets") for row in evidence.values())
            else None
        )
    await session.commit()


async def reduce_ozon_reservations(
    session: AsyncSession,
    order: FbsOrder,
    ledger: Ledger | None,
    cancelled_quantities: Counter[uuid.UUID] | None = None,
) -> None:
    from app.services import inventory_service as inventory
    from app.services.fbs_stock_publish_service import schedule_seller_stock_publish

    completed = Counter(completed_quantities(ledger))
    completed.update(cancelled_quantities or {})
    expected = expected_quantities(order)
    if dict(completed) == expected:
        await inventory.update_fbs_order_reservation(session, order, reserve=False)
        return
    for row in await session.scalars(
        select(FbsOrderReservation).where(
            FbsOrderReservation.fbs_order_id == order.id,
        )
    ):
        await session.delete(row)
    reserves = {
        r.order_product_id: r
        for r in await session.scalars(
            select(FbsOrderProductReservation).where(
                FbsOrderProductReservation.order_product_id.in_(
                    [p.id for p in order.product_positions]
                ),
            )
        )
    }
    for position in order.product_positions:
        if position.product_id is None:
            continue
        consumed = min(position.quantity, completed[position.product_id])
        completed[position.product_id] -= consumed
        remainder = position.quantity - consumed
        position.reserved_quantity = remainder
        reserve = reserves.get(position.id)
        if reserve is not None:
            if remainder:
                reserve.quantity = remainder
            else:
                await session.delete(reserve)
    await session.flush()
    schedule_seller_stock_publish(session, order.tenant_id, order.seller_id)


def attribute_completed_children(ledger: Ledger | None, children: dict[str, Any]) -> None:
    """Tie existing expense rows to the exact proven child quantities in the same recipe."""
    if ledger is None or not ledger.ozon_positions_json or not children:
        return
    rows = [dict(row) for row in ledger.ozon_positions_json]
    available = {
        number: {uuid.UUID(pid): int(qty) for pid, qty in child["quantities"].items()}
        for number, child in children.items()
        if child.get("prior_positive")
    }
    for row in rows:
        allocations = row.get("posting_quantities")
        for number, qty in allocations.items() if isinstance(allocations, dict) else []:
            if number in available:
                pid = uuid.UUID(str(row["product_id"]))
                available[number][pid] = available[number].get(pid, 0) - int(qty)
    for row in rows:
        if not row.get("movement_id") or row.get("posting_quantities"):
            continue
        pid = uuid.UUID(str(row["product_id"]))
        remaining = int(str(row["quantity"]))
        allocated = {}
        for number in sorted(
            available,
            key=lambda number: (
                not bool(children[number].get("previous_positive")),
                number,
            ),
        ):
            quantity = min(remaining, max(0, available[number].get(pid, 0)))
            if quantity:
                allocated[number] = quantity
                available[number][pid] -= quantity
                remaining -= quantity
        if remaining == 0:
            row["posting_quantities"] = allocated
    ledger.ozon_positions_json = rows


def cancelled_completed(ledger: Ledger | None, children: dict[str, Any]) -> Counter[uuid.UUID]:
    result: Counter[uuid.UUID] = Counter()
    if ledger is None:
        return result
    for row in ledger.ozon_positions_json or []:
        if row.get("movement_id"):
            allocations = row.get("posting_quantities")
            for number, qty in allocations.items() if isinstance(allocations, dict) else []:
                if (children.get(number) or {}).get("cancelled"):
                    result[uuid.UUID(str(row["product_id"]))] += int(qty)
    return result


def record_cancelled_sources(ledger: Ledger | None, children: dict[str, Any]) -> None:
    """Retain exact cancellation evidence on the unused rows of the existing recipe."""
    if ledger is None or not ledger.ozon_positions_json or not children:
        return
    remaining = {
        number: {uuid.UUID(pid): int(qty) for pid, qty in child["quantities"].items()}
        for number, child in children.items()
        if child.get("cancelled")
    }
    for row in ledger.ozon_positions_json:
        key = "posting_quantities" if row.get("movement_id") else "cancelled_postings"
        allocations = row.get(key)
        if isinstance(allocations, dict):
            for number, qty in allocations.items():
                if number in remaining:
                    pid = uuid.UUID(str(row["product_id"]))
                    remaining[number][pid] = remaining[number].get(pid, 0) - int(qty)
    recipe = []
    for original in ledger.ozon_positions_json:
        row = dict(original)
        recipe.append(row)
        if row.get("movement_id") or row.get("cancelled_postings"):
            continue
        pid = uuid.UUID(str(row["product_id"]))
        quantity = int(str(row["quantity"]))
        cancelled_allocations: dict[str, int] = {}
        for number in sorted(remaining):
            cancelled = min(quantity, max(0, remaining[number].get(pid, 0)))
            if cancelled:
                cancelled_allocations[number] = cancelled
                remaining[number][pid] -= cancelled
                quantity -= cancelled
        if cancelled_allocations:
            row["quantity"] = sum(cancelled_allocations.values())
            row["cancelled_postings"] = cancelled_allocations
            if quantity:
                recipe.append(dict(original, quantity=quantity))
    ledger.ozon_positions_json = recipe


async def lock_handoff_batch_products(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    order_ids: list[uuid.UUID],
) -> None:
    """After parent locks, take the WMS batch's stock locks before any seller fence."""
    supply_ids = select(FbsOrder.supply_id).join(
        FbsSupply, FbsSupply.id == FbsOrder.supply_id,
    ).where(
        FbsOrder.id.in_(order_ids), FbsOrder.tenant_id == tenant_id,
        FbsOrder.seller_id == seller_id, FbsSupply.tenant_id == tenant_id,
        FbsSupply.seller_id == seller_id, FbsSupply.source == "wms",
    )
    # conduct_supply also resumes saved evidence for unpolled orders in these
    # parents. Fence that entire order scope before acquiring its products.
    orders = list(await session.scalars(select(FbsOrder).where(
        FbsOrder.supply_id.in_(supply_ids), FbsOrder.tenant_id == tenant_id,
    ).options(selectinload(FbsOrder.product_positions)).order_by(FbsOrder.id)
        .with_for_update().execution_options(populate_existing=True)))
    if not orders:
        return
    ids = [order.id for order in orders]
    product_ids = {order.product_id for order in orders if order.product_id is not None}
    product_ids.update(position.product_id for order in orders
                       for position in order.product_positions if position.product_id is not None)
    # Cancellation/reservation cleanup can still touch the previous mapping.
    product_ids.update(await session.scalars(select(FbsOrderReservation.product_id).where(
        FbsOrderReservation.tenant_id == tenant_id,
        FbsOrderReservation.fbs_order_id.in_(ids),
    )))
    product_ids.update(await session.scalars(
        select(FbsOrderProductReservation.product_id).join(FbsOrderProduct).where(
            FbsOrderProductReservation.tenant_id == tenant_id,
            FbsOrderProduct.order_id.in_(ids),
        )
    ))
    # Keep FOR UPDATE, matching ordinary handoff/reservation stock locks. A
    # weaker lock would allow C to hold P2 while this batch already holds Seller.
    await session.execute(select(Product.id).where(
        Product.tenant_id == tenant_id, Product.id.in_(product_ids),
    ).order_by(Product.id).with_for_update())


async def conduct_supply(session: AsyncSession, supply: FbsSupply) -> None:
    """Caller owns supply -> orders locks; accounting and reservation commit together."""
    from app.services import fbs_shipment_service as shipment
    from app.services import fbs_shipment_source_service as sources
    from app.services.fbs_order_billing_service import charge_handed_over_orders
    from app.services.fbs_ozon_packaging_service import (
        OzonPackagingError,
        prepare_shipment_sources,
        write_off_order,
    )

    operation = await session.scalar(
        select(FbsWbOperation)
        .where(
            FbsWbOperation.tenant_id == supply.tenant_id,
            FbsWbOperation.seller_id == supply.seller_id,
            FbsWbOperation.operation_kind == OBSERVATION_KIND,
            FbsWbOperation.local_entity_id == supply.id,
        )
        .execution_options(populate_existing=True)
    )
    if operation is None or supply.source != "wms":
        return
    orders = list(
        await session.scalars(
            select(FbsOrder)
            .where(
                FbsOrder.supply_id == supply.id,
                FbsOrder.tenant_id == supply.tenant_id,
            )
            .options(selectinload(FbsOrder.product_positions))
            .order_by(FbsOrder.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    evidence = (operation.response_summary_json or {}).get("orders") or {}
    completed_orders: list[FbsOrder] = []
    billing_quantities: dict[uuid.UUID, dict[uuid.UUID, int]] = {}
    all_complete = True
    for order in orders:
        if order.status in {"cancelled", "defect"}:
            continue
        if (
            order.seller_id != supply.seller_id
            or order.warehouse_id != supply.warehouse_id
            or order.marketplace != supply.marketplace
            or (order.marketplace == "wb" and order.wb_supply_id != supply.wb_supply_id)
        ):
            all_complete = False
            continue
        ledger = await session.scalar(
            select(Ledger)
            .where(
                Ledger.tenant_id == supply.tenant_id,
                Ledger.fbs_order_id == order.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        expected = expected_quantities(order)
        if ledger is not None and ledger.reversed_at is not None:
            all_complete = False
            continue
        saved_observation = evidence.get(str(order.id)) or {}
        raw_targets = saved_observation.get("targets") or {}
        children = saved_observation.get("children") or {}
        if (raw_targets or children) and saved_observation.get("scope") != observation_scope(order):
            operation.error_code = "observed_handoff_scope_changed"
            all_complete = False
            continue
        targets = {uuid.UUID(pid): int(qty) for pid, qty in raw_targets.items()}
        cancelled = child_totals(children, cancelled=True)
        attribute_completed_children(ledger, children)
        cancelled_expense = cancelled_completed(ledger, children)
        # A child cancelled after expense still points at its original movement.
        # Include that existing expense in the cumulative target, without creating
        # a new expense for a child cancelled before its stock transaction.
        if children:
            target_counter = Counter(targets)
            target_counter.update(cancelled_expense)
            targets = dict(target_counter)
        if targets and (
            not expected or any(qty > expected.get(pid, 0) for pid, qty in targets.items())
        ):
            operation.error_code = "fbs_shipment_product_missing"
            all_complete = False
            continue
        try:
            if targets and completed_quantities(ledger) != expected:
                async with session.begin_nested():
                    if order.marketplace == "ozon":
                        prepared = await prepare_shipment_sources(
                            session,
                            tenant_id=supply.tenant_id,
                            warehouse_id=supply.warehouse_id,
                            orders=[order],
                        )
                        ledger = await write_off_order(
                            session,
                            tenant_id=supply.tenant_id,
                            order=order,
                            actor_user_id=None,
                            ledger=prepared[0],
                            proved_quantities=targets,
                        )
                        ledger.wb_operation_id = operation.id
                        ledger.written_off_at = ledger.written_off_at or datetime.now(UTC)
                        attribute_completed_children(ledger, children)
                    else:
                        assert order.product_id is not None
                        plan = await sources.plan_fbs_shipment_sources(
                            session,
                            tenant_id=supply.tenant_id,
                            supply_warehouse_id=supply.warehouse_id,
                            requests=[
                                sources.FbsShipmentSourceRequest(
                                    fbs_order_id=order.id,
                                    product_id=order.product_id,
                                    quantity=1,
                                )
                            ],
                        )
                        await shipment._write_off_delivered_orders_once(
                            session,
                            supply,
                            [order],
                            None,
                            source_plan=plan,
                            operation=operation,
                        )
                        ledger = await session.scalar(
                            select(Ledger).where(Ledger.fbs_order_id == order.id)
                        )
        except (OzonPackagingError, shipment.FbsShipmentError, ValueError) as exc:
            operation.error_code = str(exc)[:64]
            all_complete = False
            continue
        completed = Counter(completed_quantities(ledger))
        cancelled_expense = cancelled_completed(ledger, children)
        cancelled_outstanding = cancelled - cancelled_expense
        record_cancelled_sources(ledger, children)
        settled = Counter(completed)
        settled.update(cancelled_outstanding)
        if children:
            await reduce_ozon_reservations(session, order, ledger, cancelled_outstanding)
        elif ledger is not None and order.marketplace == "ozon":
            await reduce_ozon_reservations(session, order, ledger)
        if expected and dict(settled) == expected:
            if not completed:
                order.status = "cancelled"
                continue
            if order.status not in {"done", "sorted"}:
                order.status = "in_delivery"
            completed_orders.append(order)
            billing_quantities[order.id] = dict(completed)
        else:
            all_complete = False
    now = operation.confirmed_at or datetime.now(UTC)
    if completed_orders:
        operation.confirmed_at = now
        operation.state = "confirmed"
        # Accounting evidence is per order. The whole document date follows only
        # once every non-cancelled unit has a persisted expense.
        await charge_handed_over_orders(
            session, completed_orders, occurred_at=now, quantities_by_order=billing_quantities
        )
    if all_complete and completed_orders:
        supply.delivered_at = supply.delivered_at or now
        if supply.status != "done":
            supply.status = "in_delivery"
        operation.state = "confirmed"
        operation.error_code = None
    await session.flush()
