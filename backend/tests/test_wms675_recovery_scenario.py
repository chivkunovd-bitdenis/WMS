"""Bambook incident: real WMS-662 accounting, frozen live Ozon cards, private DB.

Only external HTTP and the stock-publish dispatch are replaced in this test.
Inventory, source recipes, observations, reservations and billing remain real.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from test_wms662_observed_handoff import saved, seed, shipped

from app.db.session import SessionLocal, engine
from app.models.billing import BillingLedgerLine
from app.models.fbs_order import FbsOrder, FbsOrderProduct
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger as Ledger
from app.models.fbs_supply import FbsSupply
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.services import fbs_observed_handoff_service as observed
from app.services import fbs_stock_publish_service as publish
from app.services import inventory_service as inventory
from app.services.fbs_order_billing_service import record_fbs_order_confirmed
from app.services.marketplace_provider import OzonMarketplaceProvider
from app.services.ozon_marketplace_transport import HttpxOzonMarketplaceTransport

pytestmark = pytest.mark.asyncio
EVIDENCE = Path(__file__).resolve().parents[2] / "docs/reviews/wms675-evidence-20261006"
ACCOUNTING = EVIDENCE / "accounting-refresh-20261006-attempt1"
# Explicit incident expectations, independent of the classifier under test.
DELTAS = {1586484429: 4, 1697770458: 8, 1586466682: 5, 1695134284: 0, 1695128938: 2, 1589998415: 7}


def csv_rows(name):
    with (ACCOUNTING / f"{name}.csv").open(newline="") as source:
        return list(csv.DictReader(source))


@pytest.fixture(autouse=True)
def external_boundaries_only(monkeypatch):
    publications = []
    monkeypatch.setattr(publish, "_dispatch", lambda *args: publications.append(args))

    async def no_socket(*args, **kwargs):
        raise AssertionError("WMS-675 incident test must never open an external socket")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_socket)
    return publications


@pytest_asyncio.fixture
async def incident_db(db_session):
    # conftest validates the URL before creating/resetting the schema. Confirm
    # the actual server as well; SQLite remains usable by ordinary test CI.
    if engine.dialect.name == "postgresql":
        identity = (
            await db_session.execute(
                text("select current_database(), host(inet_server_addr()), inet_server_port()")
            )
        ).one()
        assert identity[0].startswith("wms_test")
        assert identity[1] in {"127.0.0.1", "::1"} or engine.url.host == "postgres"
        print(f"WMS675 isolated database: {identity[0]} {identity[1]}:{identity[2]}")
    yield db_session
    await db_session.close()
    await engine.dispose()


async def seed_incident(session):
    positions = json.loads((EVIDENCE / "fresh-read-position-classification.json").read_text())[
        "positions"
    ]
    local = {row["external_order_id"]: row for row in csv_rows("orders_positions_reserves")}
    recipes = {row["external_order_id"]: row for row in csv_rows("ledger")}
    balances = csv_rows("balances_locations")
    assert len(positions) == len(local) == len(recipes) == 31
    assert Counter(row["local_status"] for row in positions) == {
        "in_delivery": 15,
        "done": 11,
        "cancelled": 4,
        "in_supply": 1,
    }
    assert Counter(row["ozon_substatus"] for row in positions) == {
        "posting_in_pickup_point": 9,
        "posting_on_way_to_city": 6,
        "posting_received": 11,
        "posting_canceled": 4,
        "posting_created": 1,
    }
    assert len(csv_rows("operation_facts")) == 11
    assert len(csv_rows("billing_entries")) == 22
    assert {row["source_event_id"] for row in csv_rows("operation_facts")} == {
        row["order_id"] for row in positions if row["local_status"] == "done"
    }
    case = await seed(session, "ozon", quantities=(1,) * 6, count=0)
    case.supply.status = "draft"
    case.location.code = "__SORTING__"
    products = dict(zip((row["product_id"] for row in balances), case.products, strict=True))
    case.by_sku = {}
    case.opening_stock = {}
    for row in balances:
        product = products[row["product_id"]]
        balance = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.product_id == product.id,
            )
        )
        balance.quantity = balance.quantity_unpacked = int(row["quantity"])
        case.opening_stock[product.id] = balance.quantity
        # Opening history is condensed to its saved net balance; incident
        # shipment expense is zero. No production movement is copied or applied.
        session.add(
            InventoryMovement(
                tenant_id=case.tenant.id,
                seller_id=case.seller.id,
                product_id=product.id,
                storage_location_id=case.location.id,
                warehouse_id=case.warehouse.id,
                quantity_delta=balance.quantity,
                movement_type="inbound_intake",
            )
        )
    case.cards = {}
    for row in positions:
        number = row["posting_number"]
        source = local[number]
        card = json.loads((EVIDENCE / row["evidence_file"]).read_text())["card"]
        assert card["products"] == [{"sku": row["sku"], "quantity": 1, "offer_id": row["offer_id"]}]
        product = products[row["product_id"]]
        case.by_sku[row["sku"]] = product
        product.sku_code = row["offer_id"]
        order = FbsOrder(
            tenant_id=case.tenant.id,
            seller_id=case.seller.id,
            warehouse_id=case.warehouse.id,
            supply_id=case.supply.id,
            product_id=product.id,
            marketplace="ozon",
            wb_order_id=int(source["wb_order_id"]),
            external_order_id=number,
            status=source["status"],
            wb_status=source["wb_status"],
            supplier_status=source["supplier_status"],
            mapping_status="mapped",
            reserve_status="reserved" if row["local_reserved_quantity"] else "released",
            created_at_wb=datetime.fromisoformat(source["created_at_wb"]),
            deadline_at=datetime.fromisoformat(card["shipment_date"]),
            meta_details_json={"ozon_requirements": {"kinds": []}},
        )
        session.add(order)
        await session.flush()
        session.add(
            FbsOrderProduct(
                order_id=order.id,
                product_id=product.id,
                ozon_sku=row["sku"],
                offer_id=row["offer_id"],
                position_index=0,
                quantity=1,
            )
        )
        await session.flush()
        await session.refresh(order, attribute_names=["product_positions"])
        await inventory.update_fbs_order_reservation(
            session,
            order,
            reserve=bool(row["local_reserved_quantity"]),
        )
        recipe = recipes[number]
        assert not any(
            recipe[key]
            for key in (
                "shipment_movement_id",
                "written_off_at",
                "reversed_at",
                "reversal_movement_id",
            )
        )
        original = json.loads(recipe["ozon_positions_json"])
        assert len(original) == 1 and original[0]["quantity"] == 1
        assert not original[0].get("movement_id")
        session.add(
            Ledger(
                tenant_id=case.tenant.id,
                fbs_order_id=order.id,
                product_id=product.id,
                storage_location_id=case.location.id,
                source_warehouse_id=case.warehouse.id,
                quantity=1,
                ozon_positions_json=[
                    {
                        **original[0],
                        "product_id": str(product.id),
                        "storage_location_id": str(case.location.id),
                        "source_warehouse_id": str(case.warehouse.id),
                    }
                ],
            )
        )
        if order.status == "done":
            await record_fbs_order_confirmed(session, order)
        case.orders.append(order)
        case.cards[number] = card
    await session.commit()
    return case


async def recover_exact_supply(case, calls):
    def wire(request):
        assert request.method == "POST" and request.url.path == "/v3/posting/fbs/get"
        number = json.loads(request.content)["posting_number"]
        calls.append(number)
        return httpx.Response(200, json={"result": case.cards[number]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
        provider = OzonMarketplaceProvider(transport=HttpxOzonMarketplaceTransport(client=client))
        cards = await provider.fetch_statuses(
            client_id="wms675-test-client",
            api_key="wms675-test-key",
            order_ids=list(case.cards),
        )
        async with SessionLocal() as session:
            orders = list(
                await session.scalars(
                    select(FbsOrder)
                    .where(
                        FbsOrder.supply_id == case.supply.id,
                        FbsOrder.tenant_id == case.tenant.id,
                        FbsOrder.seller_id == case.seller.id,
                    )
                    .options(selectinload(FbsOrder.product_positions))
                )
            )
            by_number = {card["posting_number"]: card for card in cards}
            observations = {}
            for order in orders:
                targets, children = await observed.ozon_targets(
                    order,
                    by_number[order.external_order_id],
                    provider,
                    "wms675-test-client",
                    "wms675-test-key",
                )
                observations[order.id] = observed.make_observation(
                    order,
                    targets,
                    by_number[order.external_order_id],
                    children,
                )
            assert sum(sum(row["targets"].values()) for row in observations.values()) == 26
            await observed.save_observations(session, case.tenant.id, case.seller.id, observations)
            supply = await session.scalar(
                select(FbsSupply)
                .where(
                    FbsSupply.id == case.supply.id,
                    FbsSupply.tenant_id == case.tenant.id,
                    FbsSupply.seller_id == case.seller.id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            await observed.lock_handoff_batch_products(
                session,
                case.tenant.id,
                case.seller.id,
                [order.id for order in orders],
            )
            await observed.conduct_supply(session, supply)
            await session.commit()


def billing_snapshot(state):
    return {
        (
            row.id,
            row.source_id,
            row.service_code,
            row.quantity,
            row.amount,
            row.reversal_of_id,
        )
        for row in state.charges
    }


async def billing_lines(case):
    async with SessionLocal() as reader:
        rows = await reader.scalars(
            select(BillingLedgerLine).where(
                BillingLedgerLine.tenant_id == case.tenant.id,
            )
        )
        return {
            (
                row.id,
                row.ledger_entry_id,
                row.product_id,
                row.physical_quantity,
                row.billing_quantity,
                row.amount,
            )
            for row in rows
        }


async def test_bambook_exact_31_recovers_26_once(incident_db, external_boundaries_only):
    case = await seed_incident(incident_db)
    before = await saved(case)
    assert sum(before.position_reserves.values()) == 16
    assert sum(before.reserves.values()) == 0
    assert len(before.facts) == 11 and len(before.charges) == 22
    assert all(shipped(before, product) == 0 for product in case.products)
    assert all(not observed.completed_quantities(ledger) for ledger in before.ledgers.values())
    old_facts = {(fact.id, fact.source_event_id, fact.item_quantity) for fact in before.facts}
    old_charges = billing_snapshot(before)
    old_lines = await billing_lines(case)
    assert len(old_lines) == 22
    calls = []
    await recover_exact_supply(case, calls)
    first = await saved(case)
    first_lines = await billing_lines(case)
    assert Counter(calls) == Counter(case.cards.keys())
    positive_ids = {order.id for order in case.orders if order.status in {"done", "in_delivery"}}
    excluded_ids = {order.id for order in case.orders} - positive_ids
    for sku, delta in DELTAS.items():
        product = case.by_sku[sku]
        assert shipped(first, product) == delta, f"SKU {sku}: wrong incident expense"
        assert first.stock[product.id] == case.opening_stock[product.id] - delta
        assert first.stock[product.id] == sum(
            move.quantity_delta for move in first.moves if move.product_id == product.id
        )
    expenses = [move for move in first.moves if move.movement_type == "fbs_shipment"]
    assert len(expenses) == 26 and all(move.quantity_delta == -1 for move in expenses)
    for order_id, ledger in first.ledgers.items():
        completed = observed.completed_quantities(ledger)
        assert sum(completed.values()) == (1 if order_id in positive_ids else 0)
        assert ledger.reversed_at is None and ledger.reversal_movement_id is None
    assert sum(first.position_reserves.values()) == 1 and not first.reserves
    assert {p.order_id for p in first.positions if p.reserved_quantity} == {
        order.id for order in case.orders if order.status == "in_supply"
    }
    assert all(first.orders[oid].status == before.orders[oid].status for oid in excluded_ids)
    assert first.supply.status == "draft" and first.supply.delivered_at is None
    assert len(first.facts) == 26 and len(first.charges) == 52
    assert old_facts <= {
        (fact.id, fact.source_event_id, fact.item_quantity) for fact in first.facts
    }
    assert old_charges <= billing_snapshot(first)
    assert {fact.source_event_id for fact in first.facts} == positive_ids
    assert all(fact.item_quantity == 1 for fact in first.facts)
    assert Counter((row.source_id, row.service_code) for row in first.charges) == Counter(
        {(oid, code): 1 for oid in positive_ids for code in ("fbs_order", "packing")}
    )
    assert all(
        row.quantity == 1 and row.entry_type == "charge" and row.reversal_of_id is None
        for row in first.charges
    )
    assert len(first_lines) == 52 and old_lines <= first_lines
    assert Counter(line[1] for line in first_lines) == Counter({row.id: 1 for row in first.charges})
    assert all(line[3] == line[4] == 1 for line in first_lines)
    assert external_boundaries_only, "normal stock-publish intentions must remain scheduled"
    assert all(args[:2] == (case.tenant.id, case.seller.id) for args in external_boundaries_only)

    await recover_exact_supply(case, calls)
    again = await saved(case)
    assert Counter(calls) == Counter({number: 2 for number in case.cards})
    assert again.stock == first.stock and again.position_reserves == first.position_reserves
    assert again.reserves == first.reserves
    assert {move.id for move in again.moves} == {move.id for move in first.moves}
    assert {(fact.id, fact.source_event_id, fact.item_quantity) for fact in again.facts} == {
        (fact.id, fact.source_event_id, fact.item_quantity) for fact in first.facts
    }
    assert billing_snapshot(again) == billing_snapshot(first)
    assert await billing_lines(case) == first_lines
    assert {
        oid: observed.completed_quantities(ledger) for oid, ledger in again.ledgers.items()
    } == {oid: observed.completed_quantities(ledger) for oid, ledger in first.ledgers.items()}
    print(
        "WMS675 recovery verified: expense=26 reserve=16->1 facts=11->26 charges=22->52 "
        "existing IDs preserved; repeat expense/facts/charges delta=0; SKU deltas=4/8/5/0/2/7"
    )
