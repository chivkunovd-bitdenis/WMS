"""Independent regression contract for Astra F1/F2 on product SHA 6330ec83.

Reuse frozen fixture builders, never replace synchronization/accounting helpers.
Marketplace transport/credentials are the only fakes; all results are reread
from the real database after the public status synchronization commits.
"""

import pytest
from test_wms662_observed_handoff import (
    checkpoint,
    external,
    fake_credentials_and_no_network,  # noqa: F401 -- imported autouse fixture
    saved,
    seed,
    shipped,
    split_cards,
    sync,
)

from app.services import inventory_service as inventory

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("current_a_quantity", [1, 2])
async def test_f1_approved_checkpoint_limits_postings_and_quantity_snapshot(
    db_session, current_a_quantity
):
    case = await seed(db_session, "ozon", count=2)
    approved, added = case.orders
    operation = await checkpoint(db_session, case)
    # Persist exact approved composition with the existing real source recipe:
    # A was approved for one unit; B belongs to the current supply but not approve.
    operation.request_summary_json = {
        **operation.request_summary_json,
        "ozon_handoff_progress": {
            "carriage_id": 901,
            "carriage_approved": True,
            "posting_numbers": [approved.external_order_id],
            "shipped_postings": [approved.external_order_id],
        },
    }
    for order in case.orders:
        order.meta_details_json = {
            **order.meta_details_json,
            "ozon_assembly": {"posting_numbers": [order.external_order_id]},
        }
    # A's current quantity must not enlarge the saved one-unit source snapshot.
    approved.product_positions[0].quantity = current_a_quantity
    await inventory.update_fbs_order_reservation(db_session, approved, reserve=True)
    await db_session.commit()
    api = external(case, ("awaiting_deliver", "posting_in_carriage"), carriage="formed")
    api.set(case, approved, "awaiting_deliver", "posting_in_carriage",
            quantities=(current_a_quantity,))

    await sync(case, api)
    first = await saved(case)
    product = case.products[0]
    assert shipped(first, product) == 1, "only approved A's saved one-unit quantity is proved"
    assert first.stock[product.id] == case.opening_stock[product.id] - 1
    assert first.position_reserves.get(product.id, 0) == current_a_quantity
    assert first.reserves == {}
    assert added.id not in first.ledgers or not first.ledgers[added.id].shipment_movement_id
    assert sum(int(row["quantity"]) for row in first.ledgers[approved.id].ozon_positions_json
               if row.get("movement_id")) == 1
    assert first.supply.delivered_at is None
    assert first.supply.status not in {"done", "in_delivery"}

    await sync(case, api)
    again = await saved(case)
    assert {move.id for move in again.moves} == {move.id for move in first.moves}
    assert again.stock == first.stock
    assert again.position_reserves == first.position_reserves
    assert again.supply.delivered_at is None


async def test_f2_split_cancelled_remainder_releases_reserve_and_finalizes_once(db_session):
    case = await seed(db_session, "ozon", quantities=(3, 2))
    api, _child_a, child_b = await split_cards(db_session, case)
    await sync(case, api)
    first = await saved(case)
    p, q = case.products
    assert (shipped(first, p), shipped(first, q)) == (2, 0)
    assert (first.position_reserves.get(p.id, 0), first.position_reserves.get(q.id, 0)) == (1, 2)
    assert first.supply.delivered_at is None

    api.cards[child_b]["status"] = "cancelled"
    await sync(case, api)
    cancelled = await saved(case)
    assert (shipped(cancelled, p), shipped(cancelled, q)) == (2, 0)
    assert cancelled.stock == first.stock, "cancelled B must never reverse delivered A"
    assert cancelled.position_reserves.get(p.id, 0) == 0
    assert cancelled.position_reserves.get(q.id, 0) == 0
    assert cancelled.reserves == {}
    assert all(position.reserved_quantity == 0 for position in cancelled.positions)
    assert cancelled.supply.delivered_at is not None
    assert cancelled.supply.status in {"done", "in_delivery"}
    ledger = cancelled.ledgers[case.orders[0].id]
    assert ledger.reversed_at is None
    assert sum(int(row["quantity"]) for row in ledger.ozon_positions_json
               if row.get("movement_id")) == 2
    assert {move.id for move in cancelled.moves} == {move.id for move in first.moves}

    await sync(case, api)
    again = await saved(case)
    assert again.stock == cancelled.stock
    assert again.position_reserves == cancelled.position_reserves
    assert {move.id for move in again.moves} == {move.id for move in cancelled.moves}
    assert again.supply.delivered_at == cancelled.supply.delivered_at
    assert again.ledgers[case.orders[0].id].reversed_at is None
