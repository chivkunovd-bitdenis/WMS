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
    unfinished = exists(select(1).select_from(elements).where(movement_id.is_(None)))
    quantity = (
        cast(elements.c.value.op("->>")("quantity"), Integer)
        if postgres
        else func.json_extract(elements.c.value, "$.quantity")
    )
    completed = (
        select(func.coalesce(func.sum(quantity), 0))
        .select_from(elements)
        .where(
            movement_id.is_not(None),
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
) -> dict[uuid.UUID, int]:
    if row is None or row.get("posting_number") != order.external_order_id:
        return {}
    expected = expected_quantities(order)
    if not expected:
        return {}
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
            return {}
        cards = await provider.fetch_statuses(
            client_id=client_id, api_key=api_key, order_ids=children
        )
        by_number = {c.get("posting_number"): c for c in cards}
        if len(cards) != len(children) or set(by_number) != set(children):
            return {}
        total: Counter[uuid.UUID] = Counter()
        proved: Counter[uuid.UUID] = Counter()
        for child in children:
            quantities = card_quantities(order, by_number[child])
            if quantities is None:
                return {}
            total.update(quantities)
            if ozon_proves_handoff(by_number[child]):
                proved.update(quantities)
        return dict(proved) if dict(total) == expected else {}
    quantities = card_quantities(order, row)
    return quantities if quantities == expected and ozon_proves_handoff(row) else {}


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
            # Preserve proven quantities through temporary read failures; cancellation
            # is fenced by the authoritative order state when accounting resumes.
            if observation.get("targets") or not previous.get("targets"):
                evidence[str(order.id)] = observation
        operation.response_summary_json = {"orders": evidence}
        operation.error_code = (
            "observed_handoff_unknown"
            if not any(row.get("targets") for row in evidence.values())
            else None
        )
    await session.commit()


async def reduce_ozon_reservations(session: AsyncSession, order: FbsOrder, ledger: Ledger) -> None:
    from app.services import inventory_service as inventory
    from app.services.fbs_stock_publish_service import schedule_seller_stock_publish

    completed = Counter(completed_quantities(ledger))
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
        if raw_targets and saved_observation.get("scope") != observation_scope(order):
            operation.error_code = "observed_handoff_scope_changed"
            all_complete = False
            continue
        targets = {uuid.UUID(pid): int(qty) for pid, qty in raw_targets.items()}
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
                        await reduce_ozon_reservations(session, order, ledger)
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
        if expected and completed_quantities(ledger) == expected:
            if order.status not in {"done", "sorted"}:
                order.status = "in_delivery"
            completed_orders.append(order)
        else:
            all_complete = False
    now = operation.confirmed_at or datetime.now(UTC)
    if completed_orders:
        operation.confirmed_at = now
        operation.state = "confirmed"
        # Accounting evidence is per order. The whole document date follows only
        # once every non-cancelled unit has a persisted expense.
        await charge_handed_over_orders(session, completed_orders, occurred_at=now)
    if all_complete and completed_orders:
        supply.delivered_at = supply.delivered_at or now
        if supply.status != "done":
            supply.status = "in_delivery"
        operation.state = "confirmed"
        operation.error_code = None
    await session.flush()
