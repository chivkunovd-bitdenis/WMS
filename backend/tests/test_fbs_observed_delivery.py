"""WMS-627: polling confirmed delivery must consume physical stock once."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_supply import FbsSupply
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.services import fbs_shipment_service, wb_marketplace_orders_service
from app.services.fbs_tracking_service import FbsTrackingError, sync_supply_tracking
from app.services.sorting_location_service import get_or_create_sorting_location
from tests.test_fbs_shipment_warehouse_sc import _register_ff_admin, _setup_seller_with_token
from tests.test_fbs_tracking import _seed_in_delivery_supply


@pytest.fixture
async def observed_supply(async_client):
    headers, suffix = await _register_ff_admin(async_client)
    seller, warehouse, tenant = await _setup_seller_with_token(async_client, headers, suffix)
    sid = await _seed_in_delivery_supply(
        tenant_id=tenant,
        seller_id=uuid.UUID(seller),
        warehouse_id=uuid.UUID(warehouse),
        wb_order_ids=[627001, 627002],
        supply_status="assembling",
    )
    async with SessionLocal() as s:
        product = Product(
            tenant_id=tenant, seller_id=uuid.UUID(seller), name="Shipped", sku_code="WMS627"
        )
        s.add(product)
        await s.flush()
        sorting = await get_or_create_sorting_location(s, tenant, uuid.UUID(warehouse))
        s.add(
            InventoryBalance(
                tenant_id=tenant,
                product_id=product.id,
                storage_location_id=sorting.id,
                quantity=3,
                quantity_unpacked=3,
                quantity_packed=0,
            )
        )
        for o in (await s.scalars(select(FbsOrder).where(FbsOrder.supply_id == sid))).all():
            o.product_id = product.id
            o.status = "sorted"
        await s.commit()
        return tenant, uuid.UUID(seller), sid, product.id


def client_for(ids, calls, *, status=200):
    def handler(request):
        calls.append((request.method, request.url.path))
        assert request.method == "GET" and request.url.path.endswith("/order-ids")
        return httpx.Response(status, json={"orderIds": ids})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def stock_state(sid, pid):
    async with SessionLocal() as s:
        supply = await s.get(FbsSupply, sid)
        qty = await s.scalar(
            select(func.sum(InventoryBalance.quantity)).where(InventoryBalance.product_id == pid)
        )
        movements = await s.scalar(
            select(func.count())
            .select_from(InventoryMovement)
            .where(
                InventoryMovement.product_id == pid,
                InventoryMovement.movement_type == "fbs_shipment",
            )
        )
        ledgers = await s.scalar(
            select(func.count())
            .select_from(FbsShipmentReversalLedger)
            .where(FbsShipmentReversalLedger.product_id == pid)
        )
        return supply.status, qty, movements, ledgers


@pytest.mark.asyncio
async def test_poll_done_writes_once_and_repeat_makes_no_wb_request(observed_supply):
    tenant, _, sid, pid = observed_supply
    calls = []
    async with SessionLocal() as s, client_for([627001, 627002], calls) as client:
        for _ in range(2):
            await sync_supply_tracking(
                s, tenant, sid, client, sync_orders=False, wb_done_hint=True, actor_user_id=None
            )
            await s.commit()
    assert await stock_state(sid, pid) == ("done", 1, 2, 2)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_not_delivered_does_not_consume_stock(observed_supply):
    tenant, _, sid, pid = observed_supply
    calls = []
    async with SessionLocal() as s, client_for([], calls) as client:
        await sync_supply_tracking(
            s, tenant, sid, client, sync_orders=False, wb_done_hint=False, actor_user_id=None
        )
        await s.commit()
    assert await stock_state(sid, pid) == ("assembling", 3, 0, 0)
    assert not calls


@pytest.mark.asyncio
async def test_local_order_absent_from_wb_not_written_off(observed_supply):
    tenant, _, sid, pid = observed_supply
    async with SessionLocal() as s, client_for([627001], []) as client:
        await sync_supply_tracking(
            s, tenant, sid, client, sync_orders=False, wb_done_hint=True, actor_user_id=None
        )
        await s.commit()
    assert await stock_state(sid, pid) == ("done", 2, 1, 1)


@pytest.mark.asyncio
async def test_stock_failure_rolls_back_and_does_not_close(observed_supply, monkeypatch):
    tenant, _, sid, pid = observed_supply
    original = fbs_shipment_service._write_off_delivered_orders_once

    async def fail(*args, **kwargs):
        await original(*args, **kwargs)
        raise ValueError("injected stock failure")

    monkeypatch.setattr(fbs_shipment_service, "_write_off_delivered_orders_once", fail)
    async with SessionLocal() as s, client_for([627001, 627002], []) as client:
        with pytest.raises(FbsTrackingError, match="wb_delivery_stock_reconciliation_failed"):
            await sync_supply_tracking(
                s, tenant, sid, client, sync_orders=False, wb_done_hint=True, actor_user_id=None
            )
        await s.commit()
    assert await stock_state(sid, pid) == ("assembling", 3, 0, 0)


@pytest.mark.asyncio
async def test_wb_failure_keeps_supply_retryable(observed_supply):
    tenant, _, sid, pid = observed_supply
    async with SessionLocal() as s, client_for([], [], status=500) as client:
        with pytest.raises(FbsTrackingError):
            await sync_supply_tracking(
                s, tenant, sid, client, sync_orders=False, wb_done_hint=True, actor_user_id=None
            )
        await s.commit()
    assert await stock_state(sid, pid) == ("assembling", 3, 0, 0)


@pytest.mark.asyncio
async def test_existing_wb_origin_link_poll_also_writes_off(observed_supply, monkeypatch):
    tenant, seller, sid, pid = observed_supply
    async with SessionLocal() as s:
        supply = await s.get(FbsSupply, sid)
        supply.source = "wb"
        wb_id = supply.wb_supply_id
        await s.commit()

    async def supplies_map(*args, **kwargs):
        return {wb_id: ("Observed", True)}

    monkeypatch.setattr(wb_marketplace_orders_service, "fetch_seller_supplies_map", supplies_map)
    async with SessionLocal() as s, client_for([627001, 627002], []) as client:
        await wb_marketplace_orders_service.link_confirmed_orders_to_wb_supplies(
            s, tenant, seller, client, "test-token"
        )
        await s.commit()
    assert await stock_state(sid, pid) == ("done", 1, 2, 2)
