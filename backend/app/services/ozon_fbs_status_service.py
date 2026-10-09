"""Ozon display stages derived from posting facts, without warehouse operations."""
from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.fbs_wb_operation import FbsWbOperation

CONFIRMED_STAGE_KEY = "ozon_confirmed_stage"
_TERMINAL_SUBSTATUSES = {"posting_delivered", "posting_received"}
_DELIVERY_SUBSTATUSES = {
    "posting_conditionally_delivered", "posting_in_courier_service",
    "posting_transferred_to_courier_service", "posting_driver_pick_up",
    "posting_in_pickup_point", "posting_on_way_to_city", "posting_on_way_to_pickup_point",
}
_UNCERTAIN_STATUSES = {"arbitration", "client_arbitration", "not_accepted"}
_UNCERTAIN_SUBSTATUSES = {
    "posting_in_arbitration", "posting_in_client_arbitration",
    "posting_returned_to_warehouse", "posting_not_in_sort_center", "ship_failed",
}
_EARLY_STATUSES = {
    "new", "awaiting_packaging", "awaiting_approve", "awaiting_verification",
    "awaiting_registration", "awaiting_deliver",
}


def posting_stage(
    raw: str | None, sub: str | None, *, handed: bool, previous: str | None = None,
) -> str:
    """Unknown/disputed observations retain a proven, nonterminal stage."""
    raw = (raw or "").strip().lower()
    sub = (sub or "").strip().lower()
    known = {"shipped", "acceptance_in_progress", "delivery"}
    fallback = previous if previous in known else ("shipped" if handed else "active")
    if raw in {"cancelled", "canceled"}:
        return "done"
    if raw == "cancelled_from_split_pending":
        return fallback  # The caller must inspect the known children.
    if raw in {"delivered", "done"} or sub in _TERMINAL_SUBSTATUSES:
        return "done"
    if raw in _UNCERTAIN_STATUSES or sub in _UNCERTAIN_SUBSTATUSES:
        return fallback
    if sub in _DELIVERY_SUBSTATUSES:
        return "delivery"
    if raw == "acceptance_in_progress" or sub == "posting_acceptance_in_progress":
        return "delivery" if previous == "delivery" else "acceptance_in_progress"
    if raw in {"delivering", "driver_pickup", "sent_by_seller"}:
        return "delivery"
    if raw in _EARLY_STATUSES:
        if previous in {"delivery", "acceptance_in_progress", "shipped"}:
            return previous
        return "shipped" if handed else "active"
    return fallback


def order_stage(order: FbsOrder, *, handed: bool) -> str:
    previous = (order.meta_details_json or {}).get(CONFIRMED_STAGE_KEY)
    if (previous is None and order.status in {"in_delivery", "sorted"}
            and order.wb_status not in _EARLY_STATUSES - {"new", "awaiting_packaging"}):
        # Legacy raw facts take precedence over the historically sticky sorted.
        previous = "delivery" if order.status == "in_delivery" else "acceptance_in_progress"
    return posting_stage(order.wb_status, order.supplier_status, handed=handed, previous=previous)


async def supply_display_statuses(
    session: AsyncSession, supplies: Iterable[FbsSupply],
) -> dict[uuid.UUID, str]:
    supplies = list(supplies)
    ozon = {s.id: s for s in supplies if s.marketplace == "ozon"}
    evidence: dict[uuid.UUID, dict[str, Any]] = {}
    if ozon:
        for operation in await session.scalars(select(FbsWbOperation).where(
            FbsWbOperation.local_entity_id.in_(ozon),
            FbsWbOperation.operation_kind == "observed_handoff",
            FbsWbOperation.tenant_id.in_({s.tenant_id for s in ozon.values()}),
        )):
            if operation.local_entity_id not in ozon:
                continue
            assert operation.local_entity_id is not None
            supply = ozon[operation.local_entity_id]
            if operation.tenant_id == supply.tenant_id and operation.seller_id == supply.seller_id:
                evidence[supply.id] = (operation.response_summary_json or {}).get("orders") or {}
    return {
        supply.id: supply_display_status(supply, evidence.get(supply.id, {}))
        for supply in supplies
    }


def supply_display_status(supply: FbsSupply, evidence: dict[str, Any]) -> str:
    if supply.marketplace != "ozon":
        return supply.status
    orders = [o for o in supply.orders if o.tenant_id == supply.tenant_id
              and o.seller_id == supply.seller_id and o.marketplace == "ozon"]
    if not orders:
        return supply.status
    stages = []
    for order in orders:
        handed = supply.delivered_at is not None
        observation = evidence.get(str(order.id)) or {}
        if order.wb_status == "cancelled_from_split_pending":
            from app.services.fbs_observed_handoff_service import observation_scope

            children = observation.get("children") or {}
            assembly = (order.meta_details_json or {}).get("ozon_assembly") or {}
            numbers = assembly.get("posting_numbers") or []
            if (children and set(children) == set(numbers)
                    and observation.get("scope") == observation_scope(order)):
                for child in children.values():
                    stages.append(posting_stage(
                        "cancelled" if child.get("cancelled") else child.get("status"),
                        child.get("substatus"), handed=handed,
                        previous=child.get(CONFIRMED_STAGE_KEY),
                    ))
            else:
                # A cancelled parent alone never completes its outstanding children.
                stages.append(order_stage(order, handed=handed))
        else:
            stages.append(order_stage(order, handed=handed))
    unfinished = [stage for stage in stages if stage != "done"]
    if not unfinished:
        return "done"
    if "active" in unfinished:
        return supply.status if supply.status in {"draft", "assembling", "packed"} else "assembling"
    if all(stage == "acceptance_in_progress" for stage in unfinished):
        return "acceptance_in_progress"
    if any(stage in {"shipped", "acceptance_in_progress"} for stage in unfinished):
        return "shipped"
    return "in_delivery"
