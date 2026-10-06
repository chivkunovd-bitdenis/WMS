"""WMS-662 frozen behavioural contract, C1-C18 (C19 is manual).

Only marketplace I/O and explicit crash boundaries are faked. All synchronization,
source selection, movement, reservation, billing and cancellation code is real.
Every accounting assertion opens a new database session after the worker exits.
G1/G4: no invented positive formed/carriage get-postings wire contract.
"""

from __future__ import annotations

import contextlib
import copy
import json
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.billing import BillingLedgerEntry
from app.models.fbs_order import (
    FbsOrder,
    FbsOrderProduct,
    FbsOrderProductReservation,
    FbsOrderReservation,
)
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger as Ledger
from app.models.fbs_supply import FbsSupply
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.operation_fact import OperationFact
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services import fbs_shipment_service as shipment
from app.services import inventory_service as inventory
from app.services import ozon_fbs_sync_service as ozon_sync
from app.services import wb_marketplace_orders_service as wb_sync
from app.services.fbs_ozon_packaging_service import prepare_shipment_sources
from app.services.fbs_supply_reconcile_service import (
    create_pending_deliver_operation,
    request_hash_for_deliver,
)
from app.services.marketplace_provider import (
    FakeMarketplaceTransport,
    MarketplaceProviderError,
    OzonMarketplaceProvider,
)
from app.services.wildberries_errors import WildberriesClientError

pytestmark = pytest.mark.asyncio

OZON_POSITIVE = (
    ("delivering", None),
    ("driver_pickup", None),
    ("delivered", None),
    ("delivered", "posting_delivered"),
    ("delivering", "posting_received"),
)
OZON_NEGATIVE = (
    ("awaiting_packaging", None),
    ("awaiting_deliver", None),
    ("awaiting_deliver", "posting_in_carriage"),
    ("awaiting_deliver", "posting_transferring_to_delivery"),
    ("sent_by_seller", None),
    ("done", None),
    ("new", None),
    ("unknown", None),
    (None, None),
    ("arbitration", None),
    ("not_accepted", None),
)
WB_NEGATIVE = (
    ("confirm", "waiting"),
    (None, None),
    ("complete", "mystery"),
    ("confirm", "reshipment"),
    ("complete", "crossborder"),
)
READ_PATHS = {"/v3/posting/fbs/get", "/v1/carriage/get"}


@pytest.fixture(autouse=True)
def fake_credentials_and_no_network(monkeypatch):
    # Test-only credential boundary; no stored real account is inspected.
    async def ozon_credentials(*args, **kwargs):
        return "wms662-test-client", "wms662-test-key"

    async def wb_credentials(*args, **kwargs):
        return "wms662-test-token"

    monkeypatch.setattr(ozon_sync, "_credentials", ozon_credentials)
    monkeypatch.setattr(shipment, "_ozon_credentials", ozon_credentials)
    monkeypatch.setattr(shipment, "_require_marketplace_token", wb_credentials)

    async def no_socket(*args, **kwargs):
        raise AssertionError("WMS-662 tests must never open a network connection")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_socket)


async def seed(session, marketplace="wb", quantities=(1,), count=1):
    suffix = uuid.uuid4().hex
    tenant = Tenant(
        name="WMS662 isolated", slug=f"wms662-{suffix}", billing_enabled_from=date(2020, 1, 1)
    )
    seller = Seller(tenant=tenant, name="WMS662 seller")
    warehouse = Warehouse(tenant=tenant, name="WMS662 warehouse", code=suffix)
    location = StorageLocation(
        tenant=tenant, warehouse=warehouse, code="A-01", barcode=f"LOC-{suffix}"
    )
    products = [
        Product(tenant=tenant, seller=seller, name=f"SKU {i}", sku_code=f"SKU-{suffix}-{i}")
        for i in range(len(quantities))
    ]
    supply = FbsSupply(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        marketplace=marketplace,
        source="wms",
        name="Observed handoff",
        status="assembling",
        delivery_type="warehouse_sc",
        wb_supply_id="WB-GI-662" if marketplace == "wb" else None,
        external_supply_id="WB-GI-662" if marketplace == "wb" else None,
    )
    session.add_all([tenant, seller, warehouse, location, supply, *products])
    await session.flush()
    for product, qty in zip(products, quantities, strict=True):
        session.add(
            InventoryBalance(
                tenant_id=tenant.id,
                product_id=product.id,
                storage_location_id=location.id,
                quantity=qty * count + 10,
                quantity_unpacked=qty * count + 10,
                quantity_packed=0,
            )
        )
    orders = []
    now = datetime.now(UTC)
    for i in range(count):
        order = FbsOrder(
            tenant_id=tenant.id,
            seller_id=seller.id,
            warehouse_id=warehouse.id,
            product_id=products[0].id,
            supply_id=supply.id,
            marketplace=marketplace,
            wb_order_id=662000 + i,
            wb_nm_id=3000,
            external_order_id=f"662-{i}-1" if marketplace == "ozon" else None,
            wb_supply_id=supply.wb_supply_id,
            status="in_supply",
            mapping_status="mapped",
            reserve_status="reserved",
            created_at_wb=now,
            deadline_at=now + timedelta(days=1),
            meta_details_json={"ozon_requirements": {"kinds": []}},
        )
        session.add(order)
        await session.flush()
        if marketplace == "ozon":
            for k, (p, qty) in enumerate(zip(products, quantities, strict=True)):
                session.add(
                    FbsOrderProduct(
                        order_id=order.id,
                        product_id=p.id,
                        ozon_sku=3000 + k,
                        offer_id=p.sku_code,
                        position_index=k,
                        quantity=qty,
                    )
                )
            await session.flush()
        await inventory.update_fbs_order_reservation(session, order, reserve=True)
        await session.refresh(order, attribute_names=["product_positions"])
        orders.append(order)
    await session.commit()
    return SimpleNamespace(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        location=location,
        products=products,
        supply=supply,
        orders=orders,
        quantities=quantities,
        opening_stock={p.id: q * count + 10 for p, q in zip(products, quantities, strict=True)},
    )


class OzonCards(FakeMarketplaceTransport):
    """Known posting-card contract; never implements the unknown G4 endpoint."""

    def __init__(self, case, statuses=None, *, carriage="closed"):
        super().__init__()
        self.cards = {}
        self.requested = []
        self.carriage = carriage
        self.failure = None
        self.before_reply = None
        for order in case.orders:
            self.set(case, order, *(statuses or ("delivering", None)))

    def set(self, case, order, status, substatus=None, *, number=None, quantities=None):
        number = number or order.external_order_id
        self.cards[number] = {
            "posting_number": number,
            "status": status,
            "substatus": substatus,
            "products": [
                {"sku": 3000 + i, "offer_id": p.sku_code, "quantity": qty}
                for i, (p, qty) in enumerate(
                    zip(case.products, quantities or case.quantities, strict=True)
                )
                if qty
            ],
        }

    async def _read(self, number):
        self.requested.append(number)
        snapshot = copy.deepcopy(self.cards.get(number))
        if self.before_reply:
            await self.before_reply()
        if self.failure:
            raise self.failure
        return snapshot

    async def fetch_statuses(self, *, client_id, api_key, order_ids):
        rows = [await self._read(number) for number in order_ids]
        return [row for row in rows if row is not None]

    async def call(self, *, client_id, api_key, path, payload):
        self.endpoint_calls.append((path, dict(payload)))
        assert path in READ_PATHS, f"observed sync attempted external mutation: {path}"
        if path == "/v3/posting/fbs/get":
            return {"result": await self._read(str(payload["posting_number"]))}
        return {"carriage_id": 901, "status": self.carriage, "is_partial": True}


class WbAPI:
    def __init__(self, case, statuses=None, *, done=True):
        self.case = case
        self.rows = {
            o.wb_order_id: {
                "id": o.wb_order_id,
                "supplierStatus": (statuses or ("complete", "waiting"))[0],
                "wbStatus": (statuses or ("complete", "waiting"))[1],
            }
            for o in case.orders
        }
        self.members = [o.wb_order_id for o in case.orders]
        self.done = done
        self.calls = []
        self.failure = None
        self.before_reply = None

    async def handle(self, request):
        path = request.url.path
        self.calls.append((request.method, path))
        if path == "/api/v3/orders/status" and request.method == "POST":
            payload = json.loads(request.content)
            rows = [copy.deepcopy(self.rows[i]) for i in payload["orders"] if i in self.rows]
            if self.before_reply:
                await self.before_reply()
            if isinstance(self.failure, Exception):
                raise self.failure
            if self.failure == "bad_json":
                return httpx.Response(200, content=b"{not-json")
            if isinstance(self.failure, int):
                return httpx.Response(self.failure, json={"message": "fixture failure"})
            return httpx.Response(200, json={"orders": rows})
        assert request.method == "GET", f"unexpected external mutation {request.method} {path}"
        if path.endswith("/order-ids"):
            return httpx.Response(200, json={"orderIds": self.members})
        if path.endswith("/orders"):
            return httpx.Response(200, json={"orders": self.members})
        if path.endswith("/reshipment"):
            return httpx.Response(200, json={"orders": []})
        row = {
            "id": self.case.supply.wb_supply_id,
            "name": "Observed handoff",
            "done": self.done,
            "closedAt": "2026-10-05T10:00:00Z" if self.done else None,
        }
        if path == "/api/v3/supplies":
            return httpx.Response(200, json={"supplies": [row], "next": 0})
        if path.endswith(str(self.case.supply.wb_supply_id)):
            return httpx.Response(200, json=row)
        raise AssertionError(f"unspecified WB read: {path}")


def external(case, statuses=None, **kwargs):
    return (WbAPI if case.supply.marketplace == "wb" else OzonCards)(case, statuses, **kwargs)


async def sync(case, api):
    async with (
        SessionLocal() as session,
        httpx.AsyncClient(
            transport=httpx.MockTransport(
                api.handle if isinstance(api, WbAPI) else lambda request: httpx.Response(599)
            )
        ) as client,
    ):
        if isinstance(api, WbAPI):
            await wb_sync.sync_order_statuses(
                session,
                case.tenant.id,
                case.seller.id,
                client,
                "wms662-test-token",
                actor_user_id=None,
            )
            await wb_sync.link_confirmed_orders_to_wb_supplies(
                session, case.tenant.id, case.seller.id, client, "wms662-test-token"
            )
        else:
            await ozon_sync.sync_ozon_order_statuses(
                session,
                case.tenant.id,
                case.seller.id,
                OzonMarketplaceProvider(transport=api),
                client,
            )
        await session.commit()


async def saved(case):
    async with SessionLocal() as reader:
        orders = list(
            await reader.scalars(select(FbsOrder).where(FbsOrder.tenant_id == case.tenant.id))
        )
        ids = [o.id for o in orders]
        ledgers = list(await reader.scalars(select(Ledger).where(Ledger.fbs_order_id.in_(ids))))
        moves = list(
            await reader.scalars(
                select(InventoryMovement).where(InventoryMovement.tenant_id == case.tenant.id)
            )
        )
        stock = defaultdict(int)
        for balance in await reader.scalars(
            select(InventoryBalance).where(InventoryBalance.tenant_id == case.tenant.id)
        ):
            stock[balance.product_id] += balance.quantity
        reserves = defaultdict(int)
        for row in await reader.scalars(
            select(FbsOrderReservation).where(FbsOrderReservation.fbs_order_id.in_(ids))
        ):
            reserves[row.product_id] += row.quantity
        position_reserves = defaultdict(int)
        for row in await reader.scalars(
            select(FbsOrderProductReservation)
            .join(FbsOrderProduct)
            .where(FbsOrderProduct.order_id.in_(ids))
        ):
            position_reserves[row.product_id] += row.quantity
        positions = list(
            await reader.scalars(select(FbsOrderProduct).where(FbsOrderProduct.order_id.in_(ids)))
        )
        return SimpleNamespace(
            stock=dict(stock),
            reserves=dict(reserves),
            position_reserves=dict(position_reserves),
            positions=positions,
            orders={o.id: o for o in orders},
            ledgers={ledger.fbs_order_id: ledger for ledger in ledgers},
            moves=moves,
            supply=await reader.get(FbsSupply, case.supply.id),
            supplies=list(
                await reader.scalars(select(FbsSupply).where(FbsSupply.tenant_id == case.tenant.id))
            ),
            operations=list(
                await reader.scalars(
                    select(FbsWbOperation).where(FbsWbOperation.tenant_id == case.tenant.id)
                )
            ),
            facts=list(
                await reader.scalars(
                    select(OperationFact).where(OperationFact.tenant_id == case.tenant.id)
                )
            ),
            charges=list(
                await reader.scalars(
                    select(BillingLedgerEntry).where(BillingLedgerEntry.tenant_id == case.tenant.id)
                )
            ),
            packaging=list(
                await reader.scalars(
                    select(FbsPackagingFulfillment).where(
                        FbsPackagingFulfillment.tenant_id == case.tenant.id
                    )
                )
            ),
        )


def shipped(state, product):
    return -sum(
        m.quantity_delta
        for m in state.moves
        if m.product_id == product.id and m.movement_type == "fbs_shipment" and m.quantity_delta < 0
    )


def assert_no_shipment(before, after):
    assert after.stock == before.stock
    assert not [m for m in after.moves if m.movement_type == "fbs_shipment"]
    assert not any(ledger.shipment_movement_id for ledger in after.ledgers.values())
    assert after.supply.delivered_at is None


def assert_completed(case, state, quantities=None):
    quantities = quantities or tuple(q * len(case.orders) for q in case.quantities)
    for product, qty in zip(case.products, quantities, strict=True):
        assert shipped(state, product) == qty, "proved handoff must create exact physical expense"
        assert state.stock[product.id] == case.opening_stock[product.id] - qty
        assert state.reserves.get(product.id, 0) == 0
        assert state.position_reserves.get(product.id, 0) == 0
    assert all(p.reserved_quantity == 0 for p in state.positions)
    assert all(state.ledgers[o.id].shipment_movement_id is not None for o in case.orders)
    moves = {move.id: move for move in state.moves}
    for order in case.orders:
        ledger = state.ledgers[order.id]
        assert ledger.shipment_movement_id in moves
        for row in ledger.ozon_positions_json or []:
            assert row.get("movement_id"), "completed recipe must point at persisted movements"
            move = moves[uuid.UUID(row["movement_id"])]
            assert move.product_id == uuid.UUID(row["product_id"])
            assert move.storage_location_id == uuid.UUID(row["storage_location_id"])
            assert move.quantity_delta == -int(row["quantity"])
    assert state.supply.delivered_at is not None
    assert len(state.supplies) == 1


@pytest.mark.parametrize(
    "statuses",
    [
        ("complete", "waiting"),
        ("complete", "sorted"),
        ("complete", "ready_for_pickup"),
        ("complete", "sold"),
    ],
)
async def test_c1_wb_complete_waiting_exactly_once(db_session, statuses):
    case = await seed(db_session, count=2)
    api = external(case, statuses)
    await sync(case, api)
    first = await saved(case)
    assert_completed(case, first)
    if statuses[1] == "sold":
        assert all(order.status == "done" for order in first.orders.values())
    assert len(first.ledgers) == 2
    assert len([m for m in first.moves if m.movement_type == "fbs_shipment"]) == 2
    await sync(case, api)
    again = await saved(case)
    assert {m.id for m in again.moves} == {m.id for m in first.moves}
    assert again.stock == first.stock


@pytest.mark.parametrize("supplier,wb", WB_NEGATIVE)
async def test_c2_wb_parent_and_preparation_are_not_handoff(db_session, supplier, wb):
    case = await seed(db_session)
    before = await saved(case)
    await sync(case, external(case, (supplier, wb)))
    after = await saved(case)
    assert_no_shipment(before, after)
    assert after.reserves == before.reserves


@pytest.mark.parametrize("status,substatus", OZON_NEGATIVE)
async def test_c2_ozon_preparation_and_unsupported_words(db_session, status, substatus):
    case = await seed(db_session, "ozon")
    # A saved assembly/QR label is deliberately insufficient evidence.
    case.orders[0].meta_details_json = {
        "ozon_requirements": {"kinds": []},
        "ozon_assembly": {"posting_numbers": [case.orders[0].external_order_id]},
    }
    case.supply.barcode_file = "isolated-test-qr.png"
    await db_session.commit()
    before = await saved(case)
    await sync(case, external(case, (status, substatus)))
    after = await saved(case)
    assert_no_shipment(before, after)
    assert after.position_reserves == before.position_reserves


async def test_c3_wb_partial_then_remaining_same_document(db_session):
    case = await seed(db_session, count=3)
    api = external(case)
    api.rows[case.orders[1].wb_order_id]["supplierStatus"] = "confirm"
    api.rows[case.orders[2].wb_order_id]["supplierStatus"] = "cancel"
    await sync(case, api)
    first = await saved(case)
    assert shipped(first, case.products[0]) == 1
    assert first.reserves[case.products[0].id] == 1
    assert first.orders[case.orders[2].id].status == "cancelled"
    assert first.supply.delivered_at is None
    assert first.supply.status not in {"done", "in_delivery"}
    api.rows[case.orders[1].wb_order_id]["supplierStatus"] = "complete"
    await sync(case, api)
    final = await saved(case)
    assert shipped(final, case.products[0]) == 2
    assert final.reserves.get(case.products[0].id, 0) == 0
    assert final.supply.delivered_at is not None
    assert len(final.supplies) == 1
    await sync(case, api)
    assert {m.id for m in (await saved(case)).moves} == {m.id for m in final.moves}


@pytest.mark.parametrize("status,substatus", OZON_POSITIVE)
async def test_c4_ozon_proved_posting_stages(db_session, status, substatus):
    case = await seed(db_session, "ozon", quantities=(2,))
    api = external(case, (status, substatus))
    await sync(case, api)
    first = await saved(case)
    assert_completed(case, first)
    if status == "delivered" or substatus == "posting_delivered":
        assert first.orders[case.orders[0].id].status == "done"
    await sync(case, api)
    assert {m.id for m in (await saved(case)).moves} == {m.id for m in first.moves}


async def test_c5_ozon_closed_parent_only_card_a_is_proved(db_session):
    case = await seed(db_session, "ozon", count=2)
    case.supply.external_supply_id = "901"  # A real saved ID, never derived from UUID.
    await db_session.commit()
    api = external(case, carriage="closed")
    api.set(case, case.orders[1], "awaiting_deliver")
    await sync(case, api)
    state = await saved(case)
    assert shipped(state, case.products[0]) == 1
    assert state.position_reserves[case.products[0].id] == 1
    assert (
        case.orders[1].id not in state.ledgers
        or not state.ledgers[case.orders[1].id].shipment_movement_id
    )
    assert state.supply.delivered_at is None
    assert state.supply.status not in {"done", "in_delivery"}


@pytest.mark.parametrize("carriage", ["formed", "new", "unknown", None])
async def test_c6_unconfirmed_carriage_is_unknown(db_session, carriage):
    case = await seed(db_session, "ozon")
    case.supply.external_supply_id = "901"
    await db_session.commit()
    before = await saved(case)
    api = external(case, ("awaiting_deliver", None), carriage=carriage)
    await sync(case, api)
    after = await saved(case)
    assert_no_shipment(before, after)
    assert after.position_reserves == before.position_reserves


async def checkpoint(session, case):
    operation = await create_pending_deliver_operation(
        session,
        tenant_id=case.tenant.id,
        seller_id=case.seller.id,
        local_supply_id=case.supply.id,
        idempotency_key="wms662-approved",
        request_hash=request_hash_for_deliver(
            supply_id=case.supply.id, confirmed_preflight_version=None
        ),
        confirmed_preflight_version=None,
    )
    operation.request_summary_json = {
        **(operation.request_summary_json or {}),
        "ozon_handoff_progress": {"carriage_id": 901, "carriage_approved": True},
    }
    order = case.orders[0]
    order.meta_details_json = {
        **(order.meta_details_json or {}),
        "ozon_assembly": {"posting_numbers": [order.external_order_id]},
    }
    await prepare_shipment_sources(
        session, tenant_id=case.tenant.id, warehouse_id=case.warehouse.id, orders=case.orders
    )
    await session.commit()
    return operation


async def test_c6_confirmed_checkpoint_local_recovery(db_session):
    case = await seed(db_session, "ozon")
    await checkpoint(db_session, case)
    api = external(case, ("awaiting_deliver", "posting_in_carriage"), carriage="formed")
    await sync(case, api)
    assert_completed(case, await saved(case))


async def split_cards(session, case, *, broken=None):
    order = case.orders[0]
    a, b = "662-child-A", "662-child-B"
    order.meta_details_json = {
        **(order.meta_details_json or {}),
        "ozon_assembly": {"posting_numbers": [a, b]},
    }
    await session.commit()
    api = external(case, ("cancelled_from_split_pending", None))
    api.cards[order.external_order_id]["related_postings"] = {"related_posting_numbers": [a, b]}
    api.set(case, order, "delivering", number=a, quantities=(2, 0))
    api.set(case, order, "awaiting_deliver", number=b, quantities=(1, 2))
    if broken == "missing":
        del api.cards[b]
    elif broken == "overlap":
        api.set(case, order, "delivering", number=b, quantities=(3, 2))
    elif broken == "unmapped":
        api.cards[a]["products"][0]["sku"] = 999999
        api.cards[a]["products"][0]["offer_id"] = "not-a-local-product"
    return api, a, b


async def test_c7_split_quantity_remainder_and_recipe(db_session):
    case = await seed(db_session, "ozon", quantities=(3, 2))
    api, _a, b = await split_cards(db_session, case)
    await sync(case, api)
    first = await saved(case)
    p, q = case.products
    assert (shipped(first, p), shipped(first, q)) == (2, 0)
    assert (first.position_reserves.get(p.id, 0), first.position_reserves.get(q.id, 0)) == (1, 2)
    assert first.reserves == {}  # No duplicate legacy whole-order reservation.
    assert sorted(pos.reserved_quantity for pos in first.positions) == [1, 2]
    recipe = first.ledgers[case.orders[0].id].ozon_positions_json
    assert sum(int(r["quantity"]) for r in recipe if r.get("movement_id")) == 2
    assert first.supply.delivered_at is None
    api.cards[b]["status"] = "delivering"
    await sync(case, api)
    final = await saved(case)
    assert_completed(case, final)
    assert {m.id for m in first.moves} <= {m.id for m in final.moves}
    recipe = final.ledgers[case.orders[0].id].ozon_positions_json
    ids = [r["movement_id"] for r in recipe if r.get("movement_id")]
    assert len(ids) == len(set(ids))
    assert sum(int(r["quantity"]) for r in recipe if r.get("movement_id")) == 5
    await sync(case, api)
    assert {m.id for m in (await saved(case)).moves} == {m.id for m in final.moves}


@pytest.mark.parametrize("broken", ["missing", "overlap", "unmapped"])
async def test_c8_split_incomplete_never_expenses_parent(db_session, broken):
    case = await seed(db_session, "ozon", quantities=(3, 2))
    api, _, _ = await split_cards(db_session, case, broken=broken)
    await sync(case, api)
    after = await saved(case)
    # Mapping/composition is contradictory or incomplete: do not guess any full parent.
    p, q = case.products
    spent = shipped(after, p)
    assert 0 <= spent <= 2
    assert shipped(after, q) == 0
    assert after.position_reserves.get(p.id, 0) == 3 - spent
    assert after.position_reserves.get(q.id, 0) == 2
    assert after.supply.delivered_at is None
    assert after.orders[case.orders[0].id].status != "done"


async def local_post(session, case):
    """Real local half of the normal handover; used only to arrange pre-existing history."""
    operation = await checkpoint(session, case)
    await shipment._persist_confirmed_delivery(session, case.supply, case.orders, operation, None)


@pytest.mark.parametrize("history", ["staged", "full", "partial", "reversed"])
async def test_c11_existing_ledger_repair(db_session, history):
    case = await seed(db_session, "ozon", quantities=(3, 2))
    if history == "staged":
        await prepare_shipment_sources(
            db_session, tenant_id=case.tenant.id, warehouse_id=case.warehouse.id, orders=case.orders
        )
        await db_session.commit()
    elif history == "partial":
        # Existing persisted partial recipe: real stock write-off of two first-SKU units.
        ledgers = await prepare_shipment_sources(
            db_session, tenant_id=case.tenant.id, warehouse_id=case.warehouse.id, orders=case.orders
        )
        movement = await inventory.apply_fbs_supply_write_off(
            db_session,
            fbs_order_id=case.orders[0].id,
            tenant_id=case.tenant.id,
            product_id=case.products[0].id,
            storage_location_id=case.location.id,
            quantity=2,
            actor_user_id=None,
        )
        ledger = ledgers[0]
        recipe = [dict(row) for row in ledger.ozon_positions_json]
        row = next(r for r in recipe if r["product_id"] == str(case.products[0].id))
        remaining = dict(row, quantity=1)
        row.update(quantity=2, movement_id=str(movement.id))
        recipe.append(remaining)
        ledger.shipment_movement_id = movement.id
        ledger.ozon_positions_json = recipe
        for reserve in await db_session.scalars(
            select(FbsOrderProductReservation).where(
                FbsOrderProductReservation.product_id == case.products[0].id
            )
        ):
            reserve.quantity = 1
        for position in await db_session.scalars(
            select(FbsOrderProduct).where(FbsOrderProduct.product_id == case.products[0].id)
        ):
            position.reserved_quantity = 1
        await db_session.commit()
    else:
        await local_post(db_session, case)
        if history == "reversed":
            # Historical reversed ledger, not a new automatic stock return on cancellation.
            ledger = await db_session.scalar(
                select(Ledger).where(Ledger.fbs_order_id == case.orders[0].id)
            )
            ledger.reversed_at = datetime.now(UTC)
            case.orders[0].status = "cancelled"
            await db_session.commit()
    before = await saved(case)
    await sync(case, external(case))
    after = await saved(case)
    if history == "reversed":
        assert after.stock == before.stock
        assert {m.id for m in after.moves} == {m.id for m in before.moves}
        assert after.ledgers[case.orders[0].id].reversed_at is not None
        assert after.orders[case.orders[0].id].status == "cancelled"
    else:
        assert_completed(case, after)
        if history == "full":
            assert {m.id for m in after.moves} == {m.id for m in before.moves}


@pytest.mark.parametrize("marketplace", ["wb", "ozon"])
@pytest.mark.parametrize("already_shipped", [False, True])
async def test_c12_cancel_before_after_handoff(db_session, marketplace, already_shipped):
    case = await seed(db_session, marketplace)
    if already_shipped:
        if marketplace == "ozon":
            await local_post(db_session, case)
        else:
            await sync(case, external(case))
            assert_completed(case, await saved(case))
    before_cancel = await saved(case)
    api = external(case, ("cancel", "canceled") if marketplace == "wb" else ("cancelled", None))
    if marketplace == "ozon":
        api.cards[case.orders[0].external_order_id]["cancellation"] = {"cancelled_after_ship": True}
    await sync(case, api)
    first = await saved(case)
    assert first.stock == before_cancel.stock  # Cancellation is not a physical return document.
    assert first.reserves.get(case.products[0].id, 0) == 0
    assert first.position_reserves.get(case.products[0].id, 0) == 0
    assert first.orders[case.orders[0].id].status == "cancelled"
    if already_shipped:
        original_charges = {
            charge.id for charge in before_cancel.charges if charge.entry_type == "charge"
        }
        assert len(original_charges) == 2
        reversals = [
            charge.reversal_of_id for charge in first.charges if charge.entry_type == "reversal"
        ]
        if marketplace == "ozon":
            assert set(reversals) == original_charges and len(reversals) == 2
        else:
            assert reversals == []  # Confirmed WB warehouse work remains billable.
    await sync(case, api)
    await sync(case, external(case))  # Old positive observation must not resurrect it.
    final = await saved(case)
    assert final.stock == first.stock
    assert {m.id for m in final.moves} == {m.id for m in first.moves}
    assert final.orders[case.orders[0].id].status == "cancelled"
    assert {charge.id for charge in final.charges} == {charge.id for charge in first.charges}


async def test_c13_done_repair_is_bounded_and_stops_polling_completed(db_session, monkeypatch):
    case = await seed(db_session, "ozon", count=3)
    case.orders[0].status = "done"
    case.orders[1].status = "done"
    # A neighbour that already has a full real handoff history.
    sibling = SimpleNamespace(**{**vars(case), "orders": [case.orders[1]]})
    await local_post(db_session, sibling)
    # Keep the third row in the live bounded queue, but not positively confirmed.
    for order in case.orders[:2]:
        order.status = "done"
    case.supply.delivered_at = None
    case.supply.status = "assembling"
    await db_session.commit()
    monkeypatch.setattr(ozon_sync, "OZON_STATUS_SYNC_BATCH_LIMIT", 1)
    api = external(case, ("delivered", None))
    api.set(case, case.orders[2], "awaiting_deliver")
    for _ in range(4):
        start = len(api.requested)
        await sync(case, api)
        assert len(api.requested) - start <= 1
    state = await saved(case)
    assert shipped(state, case.products[0]) == 2
    assert state.orders[case.orders[0].id].status == "done"
    assert state.orders[case.orders[1].id].status == "done"
    start = len(api.requested)
    for _ in range(3):
        await sync(case, api)
    assert case.orders[0].external_order_id not in api.requested[start:]
    assert case.orders[1].external_order_id not in api.requested[start:]


@pytest.mark.parametrize("marketplace", ["wb", "ozon"])
@pytest.mark.parametrize(
    "scope", ["tenant", "seller", "marketplace", "imported", "warehouse", "supply"]
)
async def test_c14_scope_isolation(db_session, marketplace, scope):
    case = await seed(db_session, marketplace)
    other = await seed(db_session, marketplace)
    if scope != "tenant":
        for row in [
            other.seller,
            other.warehouse,
            other.location,
            other.products[0],
            other.orders[0],
            other.supply,
        ]:
            row.tenant_id = case.tenant.id
        for model in (InventoryBalance, FbsOrderReservation, FbsOrderProductReservation):
            for row in await db_session.scalars(
                select(model).where(model.tenant_id == other.tenant.id)
            ):
                row.tenant_id = case.tenant.id
        other.tenant = case.tenant
    if scope not in {"tenant", "seller"}:
        other.orders[0].seller_id = case.seller.id
        other.supply.seller_id = case.seller.id
        other.products[0].seller_id = case.seller.id
        other.seller = case.seller
        # Keep unique external identity across documents within the same seller.
        other.supply.external_supply_id = "different-local-supply"
        other.orders[0].wb_order_id += 20
        other.orders[0].external_order_id = "662-other-posting"
    if scope == "marketplace":
        other.orders[0].marketplace = other.supply.marketplace = (
            "ozon" if marketplace == "wb" else "wb"
        )
    if scope == "imported":
        other.supply.source = "wb"
    if scope in {"warehouse", "supply"}:
        # Bad local association must not allow a handoff from another warehouse/document.
        other.orders[0].supply_id = case.supply.id
        if scope == "supply":
            other.orders[0].wb_supply_id = "WB-GI-NOT-662"
    await db_session.commit()
    before = await saved(other)
    api = external(case)
    if scope in {"marketplace", "imported", "warehouse", "supply"}:
        if marketplace == "wb":
            api.rows[other.orders[0].wb_order_id] = {
                "id": other.orders[0].wb_order_id,
                "supplierStatus": "complete",
                "wbStatus": "waiting",
            }
        else:
            api.set(other, other.orders[0], "delivering")
    await sync(case, api)
    after = await saved(other)
    assert after.stock[other.products[0].id] == before.stock[other.products[0].id]
    assert other.orders[0].id not in after.ledgers
    assert (await saved(case)).orders[case.orders[0].id].supply_id == case.supply.id
    target = await saved(case)
    assert target.supply.external_supply_id != str(target.supply.id)
    assert all(op.wb_object_id != str(target.supply.id) for op in target.operations)
    assert shipped(target, case.products[0]) == 1


@pytest.mark.parametrize("marketplace", ["wb", "ozon"])
@pytest.mark.parametrize("source", ["real_stock", "shortage", "unmapped"])
async def test_c15_unpacked_sources_shortage_and_unmapped(db_session, marketplace, source):
    case = await seed(db_session, marketplace)
    if source == "shortage":
        case.opening_stock = {p.id: 0 for p in case.products}
        for balance in await db_session.scalars(select(InventoryBalance)):
            balance.quantity = balance.quantity_unpacked = 0
    elif source == "unmapped":
        case.orders[0].product_id = None
        case.orders[0].mapping_status = "unmapped"
        for position in await db_session.scalars(select(FbsOrderProduct)):
            position.product_id = None
    await db_session.commit()
    await sync(case, external(case))
    state = await saved(case)
    assert state.packaging == []
    if source == "unmapped":
        assert not any(ledger.shipment_movement_id for ledger in state.ledgers.values())
        assert state.supply.delivered_at is None
        assert any(op.error_code or op.error_context_json for op in state.operations), (
            "unmapped confirmed handoff must remain a recorded unresolved problem"
        )
    else:
        assert_completed(case, state)
        ledger = state.ledgers[case.orders[0].id]
        if source == "shortage":
            assert state.stock[case.products[0].id] == -1
            assert ledger.shortage_quantity == 1
        else:
            assert ledger.storage_location_id == case.location.id


@pytest.mark.parametrize("failure", [403, 429, 500, "timeout", "bad_json", "missing"])
@pytest.mark.parametrize("marketplace", ["wb", "ozon"])
async def test_c16_unknown_then_success(db_session, marketplace, failure):
    case = await seed(db_session, marketplace)
    api = external(case)
    before = await saved(case)
    if failure == "missing":
        if marketplace == "wb":
            api.rows.clear()
        else:
            api.cards.clear()
    elif marketplace == "wb":
        api.failure = httpx.ReadTimeout("fixture timeout") if failure == "timeout" else failure
    else:
        api.failure = (
            json.JSONDecodeError("fixture broken JSON", "{", 1)
            if failure == "bad_json"
            else MarketplaceProviderError(
                "ozon", failure if isinstance(failure, int) else None, code="fixture_read_failure"
            )
        )
    # Scheduler owns retry; unknown may be represented by a raised read error.
    with contextlib.suppress(
        MarketplaceProviderError, WildberriesClientError, httpx.HTTPError, json.JSONDecodeError
    ):
        await sync(case, api)
    after = await saved(case)
    assert_no_shipment(before, after)
    assert after.reserves == before.reserves
    assert after.position_reserves == before.position_reserves
    await sync(case, external(case))
    first = await saved(case)
    assert_completed(case, first)
    await sync(case, external(case))
    assert {m.id for m in (await saved(case)).moves} == {m.id for m in first.moves}


async def test_c18_saved_official_contract_and_gaps():
    path = (
        Path(__file__).resolve().parents[2]
        / "tasks/ozon-integration-20260825/OZON_FBS_OPENAPI.json"
    )
    spec = json.loads(path.read_text())
    schemas = spec["components"]["schemas"]
    carriage = schemas["carriageCarriageGetResponse"]["properties"]["status"]["description"]
    assert all(status in carriage for status in ("received", "closed", "sended", "cancelled"))
    assert "formed" not in carriage  # G1 negative contract, not invented official success.
    assert "/v2/posting/fbs/act/get-postings" not in spec["paths"]  # G4 remains explicit.
    detail = schemas["v3FbsPostingDetail"]["properties"]
    descriptions = str(detail)
    for status in ("delivering", "driver_pickup", "delivered"):
        assert status in descriptions
    assert {s for s, _ in OZON_POSITIVE}.isdisjoint({"formed", "sent_by_seller", "done"})
    assert "/v2/posting/fbs/act/get-postings" not in READ_PATHS
    # WB fixtures follow the analyst's official-source matrix, not parent done.
    requirements = (path.parents[2] / "docs/requirements/WMS-662.md").read_text()
    assert "supplierStatus=complete" in requirements and "wbStatus=waiting" in requirements
    assert "G1" in requirements and "G4" in requirements


@pytest.mark.parametrize("preparation", ["packed", "qr"])
async def test_c2_wb_local_preparation(db_session, preparation):
    case = await seed(db_session)
    if preparation == "packed":
        case.orders[0].pack_status = "packed"
        case.orders[0].status = "packed"
    else:
        case.supply.barcode_file = "wms662-saved-qr.png"
    await db_session.commit()
    before = await saved(case)
    await sync(case, external(case, ("confirm", "waiting")))
    after = await saved(case)
    assert_no_shipment(before, after)
    assert after.reserves == before.reserves


async def test_c6_unknown_has_durable_reason(db_session):
    case = await seed(db_session, "ozon")
    await sync(case, external(case, ("unknown", None)))
    state = await saved(case)
    assert any(
        op.error_code
        or op.error_context_json
        or "unknown" in json.dumps(op.response_summary_json or {})
        for op in state.operations
    ), "unknown handoff needs persisted diagnostic evidence"


async def test_c13_wb_already_done_missing_expense(db_session):
    case = await seed(db_session)
    case.orders[0].status = "done"
    case.orders[0].wb_status = "sold"
    case.orders[0].supplier_status = "complete"
    await db_session.commit()
    await sync(case, external(case, ("complete", "sold")))
    state = await saved(case)
    assert_completed(case, state)
    assert state.orders[case.orders[0].id].status == "done"


@pytest.mark.parametrize(
    "supplier,wb",
    [
        ("cancel", "waiting"),
        ("cancel_carrier", "waiting"),
        ("complete", "canceled"),
        ("complete", "declined_by_client"),
        ("complete", "canceled_by_client"),
        ("complete", "canceled_by_carrier"),
        ("confirm", "defect"),
    ],
)
async def test_c12_wb_negative_terminal_is_not_handoff(db_session, supplier, wb):
    case = await seed(db_session)
    before = await saved(case)
    await sync(case, external(case, (supplier, wb)))
    after = await saved(case)
    assert_no_shipment(before, after)
    assert after.reserves.get(case.products[0].id, 0) == 0


async def test_c4_ozon_import_and_unchanged_status_also_conduct(db_session):
    from app.models.fbs_warehouse_binding import FbsWarehouseBinding
    from app.models.product_marketplace_link import ProductMarketplaceLink

    case = await seed(db_session, "ozon", quantities=(2,))
    order = case.orders[0]
    order.status = "in_delivery"
    order.wb_status = "delivering"  # No status transition: still must repair accounting.
    db_session.add(
        FbsWarehouseBinding(
            tenant_id=case.tenant.id,
            seller_id=case.seller.id,
            marketplace="ozon",
            wb_warehouse_id=11,
            external_warehouse_id="11",
            wms_warehouse_id=case.warehouse.id,
        )
    )
    db_session.add(
        ProductMarketplaceLink(
            tenant_id=case.tenant.id,
            seller_id=case.seller.id,
            product_id=case.products[0].id,
            marketplace="ozon",
            external_sku="3000",
            external_offer_id=case.products[0].sku_code,
        )
    )
    await db_session.commit()
    api = external(case)
    api.cards[order.external_order_id]["delivery_method"] = {"warehouse_id": 11}
    async with (
        SessionLocal() as worker,
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(599))
        ) as http,
    ):
        result = await ozon_sync.sync_ozon_orders(
            worker,
            case.tenant.id,
            case.seller.id,
            OzonMarketplaceProvider(transport=api),
            http,
            selected_posting_numbers=frozenset({order.external_order_id}),
        )
        assert result["orders_upserted"] == 1, "fixture must enter the actual import path"
    assert_completed(case, await saved(case))


async def test_c14_wb_complete_outside_exact_supply_composition(db_session):
    case = await seed(db_session)
    api = external(case)
    api.members = []
    before = await saved(case)
    await sync(case, api)
    after = await saved(case)
    assert_no_shipment(before, after)
    assert after.reserves == before.reserves


@pytest.mark.parametrize("products", [None, [], [{"sku": 3000, "quantity": 2}]])
async def test_c16_ozon_incomplete_or_conflicting_composition(db_session, products):
    case = await seed(db_session, "ozon")
    api = external(case)
    api.cards[case.orders[0].external_order_id]["products"] = products
    before = await saved(case)
    await sync(case, api)
    after = await saved(case)
    assert_no_shipment(before, after)
    assert after.position_reserves == before.position_reserves
