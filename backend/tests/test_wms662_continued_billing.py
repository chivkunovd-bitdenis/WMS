"""F3: observed continuation accounts for both units after approving snapshot A/1.

Reuse the frozen normal-approve race and its complete first-stage assertions.
Only marketplace I/O is fake; inventory, reservations, facts and charges are real.
"""

import pytest
from sqlalchemy import select
from test_wms662_approve_scope_race import (
    ApproveRaceTransport,
    assert_snapshot_only_and_retry,
    fake_credentials_and_no_network,  # noqa: F401 -- frozen no-network fixture
    normal_handoff,
    ready_order,
    saved,
    seed,
    shipped,
)
from test_wms662_observed_handoff import OzonCards, assert_completed, sync

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder
from app.models.operation_fact import OperationFactLine
from app.services import inventory_service as inventory

pytestmark = pytest.mark.asyncio


async def fact_lines(case):
    async with SessionLocal() as reader:
        return list(await reader.scalars(select(OperationFactLine).where(
            OperationFactLine.tenant_id == case.tenant.id,
        )))


@pytest.mark.parametrize("repeat_sync", [False, True], ids=["continuation", "repeated-sync"])
async def test_f3_observed_second_unit_updates_billing_without_duplicates(db_session, repeat_sync):
    case = await seed(db_session, "ozon")
    await ready_order(db_session, case, case.orders[0], 1)

    async def increase_a():
        async with SessionLocal() as writer:
            order = await writer.get(FbsOrder, case.orders[0].id)
            await writer.refresh(order, attribute_names=["product_positions"])
            order.product_positions[0].quantity = 2
            await inventory.update_fbs_order_reservation(writer, order, reserve=True)
            await writer.commit()

    approve = ApproveRaceTransport(case, increase_a)
    await normal_handoff(case, approve)
    await assert_snapshot_only_and_retry(case, approve)
    approved_calls = list(approve.endpoint_calls)

    observed = OzonCards(case, ("delivering", None))
    observed.set(case, case.orders[0], "delivering", quantities=(2,))
    await sync(case, observed)
    first = await saved(case)
    first_lines = await fact_lines(case)
    assert_completed(case, first, quantities=(2,))

    if repeat_sync:
        for _ in range(2):
            await sync(case, observed)
        again = await saved(case)
        again_lines = await fact_lines(case)
        assert again.stock == first.stock
        assert again.reserves == first.reserves
        assert again.position_reserves == first.position_reserves
        assert {move.id for move in again.moves} == {move.id for move in first.moves}
        assert {(fact.id, fact.item_quantity) for fact in again.facts} == {
            (fact.id, fact.item_quantity) for fact in first.facts
        }
        assert {(line.id, line.product_id, line.item_quantity) for line in again_lines} == {
            (line.id, line.product_id, line.item_quantity) for line in first_lines
        }
        assert {(charge.id, charge.quantity, charge.amount) for charge in again.charges} == {
            (charge.id, charge.quantity, charge.amount) for charge in first.charges
        }
        assert_completed(case, again, quantities=(2,))
        state, lines = again, again_lines
    else:
        state, lines = first, first_lines

    assert approve.endpoint_calls == approved_calls, "continuation must never repeat approve/ship"
    assert observed.requested, "continuation must use the real observed status-sync path"
    assert all(path in {"/v3/posting/fbs/get", "/v1/carriage/get"}
               for path, _ in observed.endpoint_calls)
    assert shipped(state, case.products[0]) == 2
    charges = [charge for charge in state.charges if charge.entry_type == "charge"]
    assert len(charges) == 2 and len({charge.service_code for charge in charges}) == 2
    assert all(charge.source_id == case.orders[0].id for charge in charges)
    assert all(charge.quantity == 2 for charge in charges), (
        f"F3: completed two units but charges retain first unit only: "
        f"{[str(charge.quantity) for charge in charges]}"
    )
    facts = [fact for fact in state.facts if fact.operation_code == "fbs_order"]
    assert len(facts) == 1 and facts[0].source_event_id == case.orders[0].id
    assert facts[0].item_quantity == 2, "F3: fact must account for both proved units"
    assert lines and all(line.operation_fact_id == facts[0].id for line in lines)
    assert all(line.product_id == case.products[0].id for line in lines)
    assert sum(line.item_quantity for line in lines) == 2
