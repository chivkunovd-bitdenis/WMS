"""R2/R4/R12: normal Ozon handoff expenses only its pre-HTTP snapshot.

The concurrent writer runs inside the fake approve transport, after the real
operation checkpoint commits. Shipment, reservations and billing are real;
every result is read through a fresh database session.
"""

import copy
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from test_wms662_observed_handoff import (
    fake_credentials_and_no_network,  # noqa: F401 -- same isolated boundary fixture
    saved,
    seed,
    shipped,
)

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderProduct
from app.models.fbs_packing_box import FbsPackingBox, FbsPackingBoxItem
from app.models.warehouse_box import WarehouseBox
from app.services import fbs_shipment_service as shipment
from app.services import inventory_service as inventory
from app.services.marketplace_provider import FakeMarketplaceTransport, OzonMarketplaceProvider

pytestmark = pytest.mark.asyncio


async def ready_order(session, case, order, number):
    physical = WarehouseBox(
        tenant_id=case.tenant.id, warehouse_id=case.warehouse.id,
        internal_barcode=f"WMS662-approve-{number}",
    )
    session.add(physical)
    await session.flush()
    box = FbsPackingBox(
        tenant_id=case.tenant.id, supply_id=case.supply.id,
        warehouse_box_id=physical.id, box_number=number,
    )
    session.add(box)
    await session.flush()
    await session.refresh(order, attribute_names=["product_positions"])
    for position in order.product_positions:
        session.add(FbsPackingBoxItem(
            tenant_id=case.tenant.id, box_id=box.id,
            fbs_order_id=order.id, order_product_id=position.id,
        ))
    order.meta_details_json = {
        **(order.meta_details_json or {}),
        "ozon_assembly": {"posting_numbers": [order.external_order_id]},
    }
    await session.commit()


class ApproveRaceTransport(FakeMarketplaceTransport):
    def __init__(self, case, mutate):
        super().__init__()
        self.case = case
        self.mutate = mutate
        self.approved = False
        self.snapshot = None

    async def call(self, *, client_id, api_key, path, payload):
        self.endpoint_calls.append((path, dict(payload)))
        if path == "/v3/posting/fbs/get":
            return {"result": {
                "posting_number": payload["posting_number"],
                "status": "awaiting_deliver", "substatus": "posting_in_carriage",
                "products": [{"sku": 3000, "quantity": 1,
                              "offer_id": self.case.products[0].sku_code}],
            }}
        if path == "/v1/carriage/create":
            return {"carriage_id": 901}
        if path == "/v1/carriage/get":
            return {"carriage_id": 901, "status": "sended" if self.approved else "new"}
        if path == "/v1/carriage/approve":
            before = await saved(self.case)
            assert len(before.operations) == 1
            self.snapshot = copy.deepcopy(before.operations[0].request_summary_json)
            scope = self.snapshot["ozon_handoff_orders"]
            assert set(scope) == {str(self.case.orders[0].id)}
            assert scope[str(self.case.orders[0].id)]["quantities"] == {
                str(self.case.products[0].id): 1,
            }
            assert self.snapshot["ozon_handoff_progress"]["posting_numbers"] == [
                self.case.orders[0].external_order_id,
            ]
            assert not self.approved
            await self.mutate()
            self.approved = True
            return {}  # The successful HTTP body confirms the old snapshot.
        if path in {"/v2/posting/fbs/act/get-barcode", "/v2/posting/fbs/act/get-pdf"}:
            return {"file_content": "", "file_name": "fixture"}
        if path == "/v2/posting/fbs/act/get-barcode/text":
            return {"result": "OZON-ACT-901"}
        raise AssertionError(f"Unexpected marketplace request: {path}")


async def normal_handoff(case, api):
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        await shipment.deliver_supply(
            session, case.tenant.id, case.supply.id, client,
            idempotency_key="wms662-approve-race", actor_user_id=None,
            ozon_provider=OzonMarketplaceProvider(transport=api),
        )
        await session.commit()


async def assert_snapshot_only_and_retry(case, api, added_id=None):
    first = await saved(case)
    product = case.products[0]
    approved_id = case.orders[0].id
    assert shipped(first, product) == 1, "normal handoff must expense only approved one-unit A"
    assert first.stock[product.id] == case.opening_stock[product.id] - 1
    assert first.position_reserves.get(product.id, 0) == 1
    assert first.reserves == {}
    assert first.supply.delivered_at is None
    assert first.supply.status not in {"done", "in_delivery"}
    assert sum(int(row["quantity"]) for row in first.ledgers[approved_id].ozon_positions_json
               if row.get("movement_id")) == 1
    if added_id is not None:
        assert added_id not in first.ledgers or not first.ledgers[added_id].shipment_movement_id
        assert first.orders[added_id].status not in {"done", "in_delivery"}
    facts = [fact for fact in first.facts if fact.operation_code == "fbs_order"]
    assert len(facts) == 1
    assert facts[0].source_event_id == approved_id and facts[0].item_quantity == 1
    charges = [charge for charge in first.charges if charge.entry_type == "charge"]
    assert charges and all(charge.source_id == approved_id and charge.quantity == 1
                           for charge in charges)
    calls = list(api.endpoint_calls)
    await normal_handoff(case, api)
    again = await saved(case)
    assert api.endpoint_calls == calls, "same-key recovery must not repeat external handoff"
    assert again.stock == first.stock
    assert again.position_reserves == first.position_reserves
    assert {move.id for move in again.moves} == {move.id for move in first.moves}
    assert {fact.id for fact in again.facts} == {fact.id for fact in first.facts}
    assert {charge.id for charge in again.charges} == {charge.id for charge in first.charges}
    assert again.supply.delivered_at is None


async def test_normal_approve_does_not_expense_order_added_during_http(db_session):
    case = await seed(db_session, "ozon")
    await ready_order(db_session, case, case.orders[0], 1)
    added_ids = []

    async def add_b():
        async with SessionLocal() as writer:
            added = FbsOrder(
                tenant_id=case.tenant.id, seller_id=case.seller.id,
                warehouse_id=case.warehouse.id, product_id=case.products[0].id,
                supply_id=case.supply.id, marketplace="ozon", wb_order_id=662001,
                external_order_id="662-new-B", status="in_supply",
                mapping_status="mapped", reserve_status="reserved",
                created_at_wb=datetime.now(UTC), deadline_at=datetime.now(UTC) + timedelta(days=1),
                meta_details_json={"ozon_requirements": {"kinds": []}},
            )
            writer.add(added)
            await writer.flush()
            writer.add(FbsOrderProduct(
                order_id=added.id, product_id=case.products[0].id,
                ozon_sku=3000, offer_id=case.products[0].sku_code,
                position_index=0, quantity=1,
            ))
            await writer.flush()
            await inventory.update_fbs_order_reservation(writer, added, reserve=True)
            await ready_order(writer, case, added, 2)
            added_ids.append(added.id)

    api = ApproveRaceTransport(case, add_b)
    await normal_handoff(case, api)
    assert len(added_ids) == 1
    await assert_snapshot_only_and_retry(case, api, added_ids[0])


async def test_normal_approve_does_not_expense_quantity_added_during_http(db_session):
    case = await seed(db_session, "ozon")
    await ready_order(db_session, case, case.orders[0], 1)

    async def increase_a():
        async with SessionLocal() as writer:
            order = await writer.get(FbsOrder, case.orders[0].id)
            await writer.refresh(order, attribute_names=["product_positions"])
            order.product_positions[0].quantity = 2
            await inventory.update_fbs_order_reservation(writer, order, reserve=True)
            await writer.commit()

    api = ApproveRaceTransport(case, increase_a)
    await normal_handoff(case, api)
    await assert_snapshot_only_and_retry(case, api)
