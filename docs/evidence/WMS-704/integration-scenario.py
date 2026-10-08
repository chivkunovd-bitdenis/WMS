"""WMS-704: exercise recovered Rurua orders using SQLite and fake Ozon only."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient, AsyncHTTPTransport
from sqlalchemy import func, select

from app.api.fbs_supplies import retry_fbs_packing_box_qr
from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderProduct, FbsOrderProductPick
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_supply import FbsSupply
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.marketplace_account import MarketplaceAccount
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.user import User
from app.services import fbs_packing_box_service as boxes_svc
from app.services import fbs_print_asset_service as print_svc
from app.services import fbs_shipment_service as shipment_svc
from app.services import ozon_box_assembly_service as assembly_svc
from app.services.fbs_supply_service import start_supply_work
from app.services.fbs_workspace_service import get_supply_workspace
from app.services.integration_fernet import encrypt_secret
from app.services.marketplace_provider import FakeMarketplaceTransport, OzonMarketplaceProvider
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
    _seed_pick_supply,
)
from tests.test_ozon_box_assembly import _pdf_label_row

POSTINGS = ("0125883568-0126-1", "41767844-0042-2", "0157163931-0186-1")
OZON_SKU = 5282514171


class RecoveredPostingsTransport(FakeMarketplaceTransport):
    async def call(self, *, client_id, api_key, path, payload):
        # Fail closed: this validation must never perform even a fake /ship/carriage.
        assert path == "/v3/posting/fbs/get", path
        posting = payload["posting_number"]
        assert posting in POSTINGS
        self.endpoint_responses[path] = {
            "result": {
                "posting_number": posting,
                "status": "awaiting_deliver",
                "substatus": "posting_transferring_to_delivery",
                "related_postings": {"related_posting_numbers": []},
                "products": [{"sku": OZON_SKU, "quantity": 1}],
                "delivery_method": {"id": 1020005025459970},
                "shipment_date": "2026-10-08T13:30:00Z",
            }
        }
        return await super().call(client_id=client_id, api_key=api_key, path=path, payload=payload)


@pytest.mark.asyncio
async def test_recovered_three_postings_pick_pack_complete_boxes_and_repeat_qr(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def forbid_network(*args, **kwargs):
        pytest.fail("An isolated validation attempted a real HTTP request")

    monkeypatch.setattr(AsyncHTTPTransport, "handle_async_request", forbid_network)
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix, seller_name="Rurua isolated validation"
    )
    product_id = await _create_product(
        async_client, headers, seller_id, sku="OZN5282514171", barcode="OZN5282514171"
    )
    supply_id, order_ids, _ = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=48,
        order_specs=[(index, timedelta(hours=24)) for index in range(1, 4)],
        barcode="OZN5282514171",
        marketplace="ozon",
        position_quantity=1,
    )
    transport = RecoveredPostingsTransport(
        order_labels=[_pdf_label_row(posting) for posting in POSTINGS]
    )
    provider = OzonMarketplaceProvider(transport=transport)
    monkeypatch.setattr(assembly_svc, "ozon_live_api_enabled", lambda: True)
    monkeypatch.setattr(assembly_svc, "build_ozon_provider", lambda: provider)
    monkeypatch.setattr(print_svc, "ozon_live_api_enabled", lambda: True)
    monkeypatch.setattr(print_svc, "build_ozon_provider", lambda: provider)

    async with SessionLocal() as session:
        actor = await session.scalar(select(User).where(User.tenant_id == tenant_id))
        assert actor is not None
        actor_id = actor.id
        supply = await session.get(FbsSupply, supply_id)
        supply.wb_supply_id = f"PENDING-RURUA-{suffix}"
        supply.source = "wms"
        supply.external_supply_id = None
        for order_id, posting in zip(order_ids, POSTINGS, strict=True):
            order = await session.get(FbsOrder, order_id)
            order.external_order_id = posting
            order.wb_status = "awaiting_deliver"
            order.supplier_status = "posting_transferring_to_delivery"
            order.reserve_status = "no_stock"
            order.pick_status = "pending"
            order.pack_status = "pending"
            order.meta_details_json = {
                "ozon_products": [{"sku": OZON_SKU, "quantity": 1}],
                "ozon_delivery_method_id": 1020005025459970,
                "ozon_delivery_method_name": "Rurua route",
                "ozon_requirements": {},
            }
            position = await session.scalar(
                select(FbsOrderProduct).where(FbsOrderProduct.order_id == order_id)
            )
            position.ozon_sku = OZON_SKU
            position.reserved_quantity = 0
        session.add(
            MarketplaceAccount(
                tenant_id=tenant_id,
                seller_id=seller_id,
                marketplace="ozon",
                account_slot="primary",
                external_account_id="isolated-fake-client",
                secret_encrypted=encrypt_secret("isolated-fake-key"),
                is_active=True,
                validation_status="valid",
            )
        )
        workspace = await start_supply_work(session, tenant_id, supply_id, actor_user_id=actor_id)
        await session.commit()
        task_id = supply.packaging_task_id
        assert workspace["progress"]["picked"] == workspace["progress"]["packed"] == 0
        assert workspace["blockers"] == []
        assert not transport.endpoint_calls and not transport.calls
        assert await session.scalar(select(func.count(FbsPackagingFulfillment.id))) == 0

    for index, order_id in enumerate(order_ids):
        pick = await async_client.post(
            f"/operations/fbs-supplies/{supply_id}/pick/manual",
            headers=headers,
            json={
                "location_id": str(location_id),
                "product_id": str(product_id),
                "order_id": str(order_id),
                "idempotency_key": f"rurua-pick-{index}",
            },
        )
        assert pick.status_code == 200, pick.text
    task = await async_client.get(f"/operations/packaging-tasks/{task_id}", headers=headers)
    assert task.status_code == 200, task.text
    assert len(task.json()["lines"]) == 1
    line = task.json()["lines"][0]
    assert line["qty_total"] == 3
    for index, order_id in enumerate(order_ids):
        pack = await async_client.post(
            f"/operations/packaging-tasks/{task_id}/lines/{line['id']}/pack",
            headers=headers,
            json={
                "quantity": 1,
                "order_id": str(order_id),
                "idempotency_key": f"rurua-pack-{index}",
            },
        )
        assert pack.status_code == 200, pack.text
    complete = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/complete",
        headers=headers,
        json={"acknowledge_all_packed": False},
    )
    assert complete.status_code == 200, complete.text

    async with SessionLocal() as session:
        actor = await session.get(User, actor_id)
        supply = await session.get(FbsSupply, supply_id)
        task = await session.get(PackagingTask, task_id)
        task_line = await session.get(PackagingTaskLine, uuid.UUID(line["id"]))
        assert supply.status == "packed" and task.status == "done"
        assert task_line.qty_packed_in_task == 3
        assert await session.scalar(select(func.count(FbsOrderProductPick.id))) == 3
        assert await session.scalar(select(func.count(FbsPackagingFulfillment.id))) == 3
        boxes = await boxes_svc.create_boxes(
            session, tenant_id, supply_id, 3, "rurua-three-boxes", actor_user_id=actor_id
        )
        for order_id, box in zip(order_ids, boxes, strict=True):
            position = await session.scalar(
                select(FbsOrderProduct).where(FbsOrderProduct.order_id == order_id)
            )
            await boxes_svc.assign_orders(
                session,
                tenant_id,
                supply_id,
                box.id,
                [],
                actor_user_id=actor_id,
                order_product_ids=[position.id],
            )
        await session.commit()
        movement_count = await session.scalar(select(func.count(InventoryMovement.id)))
        for box in boxes:
            await retry_fbs_packing_box_qr(supply_id, box.id, actor, session)
            await retry_fbs_packing_box_qr(supply_id, box.id, actor, session)
        batch = await print_svc.request_supply_print_batch(
            session,
            tenant_id,
            supply_id,
            kind="order_sticker",
            order_ids=order_ids,
            retry_missing=True,
            http_client=async_client,
        )
        assert (batch.requested, batch.ready, batch.missing, batch.failed) == (3, 3, 0, 0)
        for order_id, posting in zip(order_ids, POSTINGS, strict=True):
            order = await session.get(FbsOrder, order_id)
            assert order.meta_details_json["ozon_assembly"] == {
                "posting_numbers": [posting],
                "recovered_from_readback": True,
            }
        workspace = await get_supply_workspace(session, tenant_id, supply_id)
        assert workspace["progress"] == {
            "picked": 3,
            "packed": 3,
            "metadata_ready": 3,
            "stickers_ready": 3,
            "total": 3,
        }
        preflight = await shipment_svc.preflight_delivery(
            session, tenant_id, supply_id, async_client, actor_user_id=actor_id
        )
        assert preflight.can_deliver, shipment_svc.delivery_preflight_to_dict(preflight)
        assert await session.scalar(select(func.sum(InventoryBalance.quantity))) == 48
        assert await session.scalar(select(func.sum(InventoryBalance.quantity_packed))) == 0
        assert await session.scalar(select(func.count(InventoryMovement.id))) == movement_count
        assert await session.scalar(select(func.count(FbsShipmentReversalLedger.id))) == 0
        assert len(transport.endpoint_calls) == 6
        assert all(path == "/v3/posting/fbs/get" for path, _ in transport.endpoint_calls)
        assert not transport.published_stocks
        # A supply QR belongs to an actual handover/carriage. Packed is not handover.
        with pytest.raises(shipment_svc.FbsShipmentError) as error:
            await shipment_svc.get_supply_barcode(session, tenant_id, supply_id, async_client)
        assert error.value.code == "supply_bad_status"
