"""WMS-721 C1-C10: posting sync, supply membership and accounting contract.

Baseline 9c0ff7d41b47d3e2b4168afb6401c09e993b3ee2, initially clean worktree.
SQLite pytest environment; only Ozon client transport/credentials are fixtures.
No pre-existing red checks were run. New shipped membership/aggregation is
expected red before implementation. Frontend labels have a separate DOM contract.

Baseline: 81 cases, 40 product failures and 41 preserved-behaviour passes.
Mutation proof: all 41 green cases fail if the worklist loses supplies and status
polls consume stock; C5/C8 also fail for rollback of local progress / tenant leak;
C7/C10 fail for repeated stock consumption with the correct worklist retained.
Each mutation is restored byte-for-byte; no product changes form this contract.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrderProduct
from app.services import fbs_shipment_service as shipment
from app.services import fbs_supply_service as supplies
from app.services import fbs_worklist_service as worklist
from app.services import ozon_fbs_sync_service as ozon_sync
from app.services.marketplace_provider import (
    FakeMarketplaceTransport,
    MarketplaceProviderError,
    OzonMarketplaceProvider,
)
from tests.test_fbs_ozon_lane import (
    _ozon_handoff_responses,
    _seed_ozon_supply_case,
    _seed_physical_ozon_packaging,
)
from tests.test_ozon_box_assembly import seed_boxes
from tests.test_wms662_observed_handoff import (
    OzonCards,
    assert_completed,
    checkpoint,
    saved,
    seed,
    split_cards,
    sync,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def client_boundary(monkeypatch):
    async def credentials(*args, **kwargs):
        return "wms721-fixture-client", "wms721-fixture-key"

    async def no_network(*args, **kwargs):
        raise AssertionError("WMS-721 must not contact an external API")

    monkeypatch.setattr(ozon_sync, "_credentials", credentials)
    monkeypatch.setattr(shipment, "_ozon_credentials", credentials)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_network)


async def membership(case, *, tenant_id=None, seller_id=None, marketplace=None):
    """Read each public list twice in fresh sessions; do not prescribe status storage.

    `shipped` follows the existing `active`/`delivery`/`done` group API convention.
    Missing support is represented as empty membership so terminal aggregation
    failures are still diagnosed independently on the pre-implementation code.
    """
    readings = []
    for _ in range(2):
        groups = {}
        async with SessionLocal() as reader:
            for group in ("active", "shipped", "delivery", "done"):
                try:
                    page = await supplies.list_supply_worklist(
                        reader, tenant_id or case.tenant.id,
                        seller_id=seller_id, marketplace=marketplace, status_group=group,
                    )
                except supplies.FbsSupplyError as exc:
                    if group != "shipped" or exc.code != "invalid_status_group":
                        raise
                    page = {"items": []}
                groups[group] = {row["id"]: row for row in page["items"]}
            await reader.commit()
        readings.append(groups)
    assert readings[0] == readings[1], "repeated reads must preserve membership and contents"
    return readings[1]


async def assert_group(case, expected):
    groups = await membership(case)
    found = [group for group, items in groups.items() if str(case.supply.id) in items]
    assert found == [expected], f"supply must appear once in {expected}; actual groups: {found}"
    async with SessionLocal() as reader:
        detail = await supplies.get_supply(reader, case.tenant.id, case.supply.id)
        row = groups[expected][str(case.supply.id)]
        assert row["status"] == detail.status, "list and reopened document must agree"
        assert row["marketplace"] == "ozon"
        await reader.commit()


async def arrange_stage(session, case, *, handed=False, status="assembling"):
    case.supply.status = status
    case.supply.delivered_at = datetime(2026, 10, 9, 8, tzinfo=UTC) if handed else None
    for order in case.orders:
        order.status = "in_delivery" if handed else "in_supply"
        order.wb_status = "delivering" if status == "in_delivery" else "awaiting_deliver"
        order.supplier_status = order.wb_status
    await session.commit()


# Groups are observable business stages. Local order.status may intentionally
# remain sorted after delivering; raw Ozon facts must still move the supply.
STATUS_STAGES = [
    ("awaiting_packaging", None, False, "active"),
    ("new", None, False, "active"),
    ("awaiting_approve", None, False, "active"),
    ("awaiting_verification", None, False, "active"),
    ("awaiting_registration", None, False, "active"),
    ("awaiting_deliver", None, False, "active"),
    ("awaiting_registration", None, True, "shipped"),
    ("awaiting_deliver", None, True, "shipped"),
    ("awaiting_deliver", "posting_transferring_to_delivery", True, "shipped"),
    ("acceptance_in_progress", None, True, "shipped"),
    ("driver_pickup", None, True, "delivery"),
    ("delivering", None, True, "delivery"),
    ("sent_by_seller", None, True, "delivery"),
    ("delivered", None, True, "done"),
    ("done", None, True, "done"),
    ("delivering", "posting_delivered", True, "done"),
    ("delivering", "posting_received", True, "done"),
    ("cancelled", None, True, "done"),
    ("canceled", None, True, "done"),
    ("cancelled", "posting_received", True, "done"),
    ("arbitration", None, True, "delivery"),
    ("client_arbitration", None, True, "delivery"),
    ("not_accepted", None, True, "delivery"),
    (None, None, True, "delivery"),
    ("new-unknown-status", None, True, "delivery"),
]
# Every nonterminal substatus from A2, using the documented main status.
STATUS_STAGES += [
    ("awaiting_deliver", sub, True, "shipped") for sub in (
        "posting_created", "posting_split_pending", "posting_in_carriage",
        "posting_not_in_carriage", "posting_registered", "posting_awaiting_passport_data",
        "posting_awaiting_registration", "posting_registration_error", "posting_canceled",
        "ship_failed",
    )
] + [("awaiting_registration", "posting_transferring_to_delivery", True, "shipped")]
STATUS_STAGES += [("delivering", "posting_acceptance_in_progress", True, "shipped")]
STATUS_STAGES += [
    ("delivering", sub, True, "delivery") for sub in (
        "posting_in_arbitration", "posting_in_client_arbitration",
        "posting_conditionally_delivered", "posting_in_courier_service",
        "posting_transferred_to_courier_service", "posting_driver_pick_up",
        "posting_in_pickup_point", "posting_on_way_to_city", "posting_on_way_to_pickup_point",
        "posting_returned_to_warehouse", "posting_not_in_sort_center",
    )
]


@pytest.mark.parametrize("raw,sub,handed,group", STATUS_STAGES)
async def test_c1_status_and_substatus_determine_supply_tab(db_session, raw, sub, handed, group):
    case = await seed(db_session, "ozon")
    # No previous delivery proof for acceptance; unknown/dispute retains delivery.
    prior = "in_delivery" if group == "delivery" else "assembling"
    await arrange_stage(db_session, case, handed=handed, status=prior)
    api = OzonCards(case, (raw, sub))
    await sync(case, api)
    await sync(case, api)
    state = await saved(case)
    order = state.orders[case.orders[0].id]
    if raw in {"cancelled", "canceled"}:
        assert order.status == "cancelled", "explicit cancellation overrides delivered substatus"
    elif group == "done":
        assert order.status == "done"
    else:
        assert order.status not in {"done", "cancelled"}
    await assert_group(case, group)
    assert all(path in {"/v3/posting/fbs/get", "/v1/carriage/get"}
               for path, _ in api.endpoint_calls)


async def normal_handoff(session):
    tenant, seller, warehouse, product, order, supply = await _seed_ozon_supply_case(
        session, packed=True,
    )
    from types import SimpleNamespace
    case = SimpleNamespace(tenant=tenant, seller=seller, warehouse=warehouse,
                           products=[product], supply=supply, orders=[order], quantities=(1,))
    session.add(FbsOrderProduct(order_id=order.id, product_id=product.id,
                                ozon_sku=3001, offer_id=product.sku_code,
                                position_index=0, quantity=1))
    await session.commit()
    await _seed_physical_ozon_packaging(session, order, supply, [(product, 1)])
    await seed_boxes(session, order, supply)
    responses = _ozon_handoff_responses()
    transport = FakeMarketplaceTransport(
        endpoint_responses=responses,
        endpoint_response_queues={"/v1/carriage/get": [{"carriage_id": 901, "status": "new"}]},
    )
    provider = OzonMarketplaceProvider(transport=transport)
    for _ in range(2):
        async with SessionLocal() as worker:
            await shipment.deliver_supply(
                worker, tenant.id, supply.id, AsyncMock(), idempotency_key="wms721-normal",
                actor_user_id=None, ozon_provider=provider,
            )
    assert sum(path == "/v1/carriage/approve" for path, _ in transport.endpoint_calls) == 1
    return case, transport


async def test_c2_confirmed_handoff_then_acceptance_then_delivery(db_session):
    case, transport = await normal_handoff(db_session)
    await assert_group(case, "shipped")
    api = OzonCards(case, ("acceptance_in_progress", None))
    await sync(case, api)
    await assert_group(case, "shipped")
    api.set(case, case.orders[0], "delivering")
    await sync(case, api)
    await assert_group(case, "delivery")
    assert sum(path == "/v1/carriage/approve" for path, _ in transport.endpoint_calls) == 1


@pytest.mark.parametrize("carriage", ["unknown", "new"])
async def test_c2_unconfirmed_handoff_does_not_display_shipped(db_session, carriage):
    case = await seed(db_session, "ozon")
    case.supply.external_supply_id = "901"
    await db_session.commit()
    api = OzonCards(case, ("awaiting_deliver", None), carriage=carriage)
    await sync(case, api)
    await assert_group(case, "active")
    state = await saved(case)
    assert state.supply.delivered_at is None
    assert not state.moves and not state.charges


MIXTURES = [
    ([("delivered", None), ("delivered", None)], True, "done"),
    ([("delivered", None), ("cancelled", None)], True, "done"),
    ([("cancelled", None), ("cancelled", None)], True, "done"),
    ([("delivered", None), ("delivering", "posting_on_way_to_city")], True, "delivery"),
    ([("delivered", None), ("acceptance_in_progress", None)], True, "shipped"),
    ([("awaiting_deliver", None), ("delivering", None)], True, "shipped"),
    ([("awaiting_packaging", None), ("delivering", None)], False, "active"),
]


@pytest.mark.parametrize("states,handed,group", MIXTURES)
async def test_c3_earliest_unfinished_posting_defines_one_supply_tab(
    db_session, states, handed, group,
):
    case = await seed(db_session, "ozon", count=2)
    await arrange_stage(db_session, case, handed=handed)
    api = OzonCards(case)
    for order, (raw, sub) in zip(case.orders, states, strict=True):
        api.set(case, order, raw, sub)
    await sync(case, api)
    await assert_group(case, group)
    await sync(case, api)
    await assert_group(case, group)


@pytest.mark.parametrize("supply_status,raw,sub,expected", [
    ("in_delivery", "delivered", None, "done"),
    ("done", "delivering", "posting_on_way_to_city", "delivery"),
    ("done", "delivering", "posting_in_pickup_point", "delivery"),
])
async def test_c4_read_repairs_saved_inconsistent_supply_without_handoff(
    db_session, supply_status, raw, sub, expected,
):
    case = await seed(db_session, "ozon")
    await arrange_stage(db_session, case, handed=True, status=supply_status)
    case.orders[0].status = "done" if raw == "delivered" else "sorted"
    case.orders[0].wb_status = raw
    case.orders[0].supplier_status = sub or raw
    await db_session.commit()
    before = await saved(case)
    await assert_group(case, expected)
    api = OzonCards(case, (raw, sub))
    await sync(case, api)
    await assert_group(case, expected)
    after = await saved(case)
    assert accounting(after) == accounting(before)
    assert all(path in {"/v3/posting/fbs/get", "/v1/carriage/get"}
               for path, _ in api.endpoint_calls)


@pytest.mark.parametrize("local", ["draft", "assembling", "packed", "in_delivery"])
async def test_c4_empty_supply_retains_local_stage(db_session, local):
    case = await seed(db_session, "ozon")
    case.orders[0].supply_id = None
    case.supply.status = local
    await db_session.commit()
    before = await saved(case)
    await assert_group(case, "delivery" if local == "in_delivery" else "active")
    assert accounting(await saved(case)) == accounting(before)


@pytest.mark.parametrize("local", ["in_supply", "assembling", "packed", "in_delivery", "sorted"])
async def test_c5_old_packaging_snapshot_does_not_reset_local_progress(db_session, local):
    case = await seed(db_session, "ozon")
    case.orders[0].status = local
    case.orders[0].wb_status = (
        "delivering" if local in {"in_delivery", "sorted"} else "awaiting_deliver"
    )
    case.supply.status = "in_delivery" if local in {"in_delivery", "sorted"} else "assembling"
    case.supply.delivered_at = datetime.now(UTC) if local in {"in_delivery", "sorted"} else None
    await db_session.commit()
    api = OzonCards(case, ("awaiting_packaging", None))
    for _ in range(2):
        await sync(case, api)
        state = await saved(case)
        assert state.orders[case.orders[0].id].status == local
        async with SessionLocal() as reader:
            page = await worklist.fetch_worklist_page(reader, case.tenant.id, status_group="new")
            assert str(case.orders[0].id) not in {row["id"] for row in page.items}
        await assert_group(case, "delivery" if local in {"in_delivery", "sorted"} else "active")


@pytest.mark.parametrize(
    "failure", ["500", "timeout", "missing", "empty", "unknown", "arbitration"],
)
async def test_c6_poll_failure_retains_stage_and_recovers(db_session, failure):
    case = await seed(db_session, "ozon")
    await arrange_stage(db_session, case, handed=True, status="in_delivery")
    api = OzonCards(case, ("delivering", None))
    if failure == "500":
        api.failure = MarketplaceProviderError("ozon", 500, {"message": "fixture failure"})
    elif failure == "timeout":
        api.failure = httpx.ReadTimeout("fixture timeout")
    elif failure == "missing":
        api.cards.clear()
    else:
        api.set(case, case.orders[0], {"empty": "", "unknown": "future-status",
                                    "arbitration": "arbitration"}[failure])
    await sync(case, api)
    await assert_group(case, "delivery")
    state = await saved(case)
    assert state.orders[case.orders[0].id].status not in {"done", "cancelled"}
    neighbour = await seed(db_session, "ozon")
    await arrange_stage(db_session, neighbour)
    await sync(neighbour, OzonCards(neighbour, ("awaiting_deliver", None)))
    await assert_group(neighbour, "active")
    api.failure = None
    api.set(case, case.orders[0], "delivering", "posting_received")
    await sync(case, api)
    await assert_group(case, "done")


def accounting(state):
    def rows_snapshot(rows):
        return {str(row.id): {column.key: getattr(row, column.key)
                             for column in row.__table__.columns} for row in rows}

    return {
        "stock": state.stock, "reserves": state.reserves,
        "position_reserves": state.position_reserves,
        "positions": sorted((str(p.id), p.quantity, p.reserved_quantity) for p in state.positions),
        "moves": rows_snapshot(state.moves),
        "charges": rows_snapshot(state.charges),
        "facts": rows_snapshot(state.facts),
        "ledgers": sorted((str(k), str(v.shipment_movement_id), v.ozon_positions_json)
                          for k, v in state.ledgers.items()),
    }


async def test_c7_repeated_poll_and_concurrent_reads_have_one_composition_and_no_extra_accounting(
    db_session,
):
    case = await seed(db_session, "ozon", count=2)
    api = OzonCards(case, ("delivering", None))
    await sync(case, api)
    before = await saved(case)
    await sync(case, api)
    # Two independent sessions enter the actual read/recalculation path together.
    gate = asyncio.Event()
    async def read():
        await gate.wait()
        return await membership(case)
    readers = [asyncio.create_task(read()) for _ in range(2)]
    gate.set()
    first, second = await asyncio.gather(*readers)
    assert first == second
    await assert_group(case, "delivery")
    after = await saved(case)
    assert len(after.supplies) == 1 and set(after.orders) == set(before.orders)
    assert accounting(after) == accounting(before)
    assert all(path in {"/v3/posting/fbs/get", "/v1/carriage/get"}
               for path, _ in api.endpoint_calls)


async def test_c8_filters_preserve_wb_and_tenant_seller_boundaries(db_session):
    case = await seed(db_session, "ozon")
    other_seller = await seed(db_session, "ozon")
    other_tenant = await seed(db_session, "ozon")
    wb = await seed(db_session, "wb")
    # Two sellers and both marketplaces inside the same fulfillment, plus outsider.
    for related in (other_seller, wb):
        related.seller.tenant_id = case.tenant.id
        related.warehouse.tenant_id = case.tenant.id
        related.supply.tenant_id = case.tenant.id
        for order in related.orders:
            order.tenant_id = case.tenant.id
    wb.supply.status = "in_delivery"
    await db_session.commit()
    wb_before = await membership(case, marketplace="wb")
    await sync(case, OzonCards(case, ("delivering", None)))
    assert await membership(case, marketplace="wb") == wb_before
    for seller_id, marketplace in ((None, None), (case.seller.id, None), (None, "ozon"),
                                    (case.seller.id, "ozon")):
        groups = await membership(case, seller_id=seller_id, marketplace=marketplace)
        assert str(case.supply.id) in groups["delivery"]
        assert sum(str(case.supply.id) in items for items in groups.values()) == 1
        assert all(str(other_tenant.supply.id) not in items for items in groups.values())
    groups = await membership(case, seller_id=other_seller.seller.id, marketplace="ozon")
    assert all(str(case.supply.id) not in items for items in groups.values())
    async with SessionLocal() as reader:
        with pytest.raises(supplies.FbsSupplyError, match="supply_not_found"):
            await supplies.get_supply(reader, other_tenant.tenant.id, case.supply.id)


async def test_c9_observed_and_ordinary_checkpoint_use_ozon_stages(db_session):
    case = await seed(db_session, "ozon")
    await checkpoint(db_session, case)
    api = OzonCards(case, ("awaiting_deliver", "posting_in_carriage"), carriage="formed")
    await sync(case, api)
    assert_completed(case, await saved(case))
    await assert_group(case, "shipped")
    api.set(case, case.orders[0], "delivering")
    await sync(case, api)
    await assert_group(case, "delivery")
    api.set(case, case.orders[0], "delivered")
    await sync(case, api)
    await assert_group(case, "done")


async def test_c9_split_parent_follows_unfinished_children_then_completes(db_session):
    case = await seed(db_session, "ozon", quantities=(3, 2))
    api, a, b = await split_cards(db_session, case)
    api.set(case, case.orders[0], "delivering", number=b, quantities=(1, 2))
    await sync(case, api)
    before = await saved(case)
    assert_completed(case, before)
    await assert_group(case, "delivery")
    api.set(case, case.orders[0], "delivered", number=a, quantities=(2, 0))
    api.set(case, case.orders[0], "delivering", "posting_received", number=b, quantities=(1, 2))
    await sync(case, api)
    await assert_group(case, "done")
    assert accounting(await saved(case)) == accounting(before)


async def test_c10_status_only_polls_and_real_cancellation_preserve_handoff_accounting(db_session):
    case = await seed(db_session, "ozon")
    before = await saved(case)
    api = OzonCards(case, ("awaiting_deliver", None))
    await sync(case, api)
    assert accounting(await saved(case)) == accounting(before)
    api.set(case, case.orders[0], "delivering")
    await sync(case, api)
    handed = await saved(case)
    assert_completed(case, handed)
    for raw, sub in (("delivering", None), ("acceptance_in_progress", None),
                     ("delivering", "posting_received")):
        api.set(case, case.orders[0], raw, sub)
        await sync(case, api)
        await membership(case)
        assert accounting(await saved(case)) == accounting(handed)
    # Cancellation is a separate existing business operation, not tab recalculation.
    # Use another handed-over order so its cancellation is still polled after delivery.
    cancellable = await seed(db_session, "ozon")
    cancel_api = OzonCards(cancellable, ("delivering", None))
    await sync(cancellable, cancel_api)
    charged = await saved(cancellable)
    cancel_api.set(cancellable, cancellable.orders[0], "cancelled")
    await sync(cancellable, cancel_api)
    cancelled = await saved(cancellable)
    assert cancelled.stock == charged.stock
    assert cancelled.reserves == {} and cancelled.position_reserves == {}
    assert cancelled.orders[cancellable.orders[0].id].status == "cancelled"
    charge_ids = {c.id for c in charged.charges if c.entry_type == "charge"}
    reversals = [c.reversal_of_id for c in cancelled.charges if c.entry_type == "reversal"]
    assert charge_ids and set(reversals) == charge_ids and len(reversals) == len(charge_ids)
    await sync(cancellable, cancel_api)
    assert accounting(await saved(cancellable)) == accounting(cancelled)
