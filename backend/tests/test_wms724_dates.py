"""WMS-724 one-time protection of neighboring dates and compatible FBS storage."""

from datetime import UTC, date, datetime, time

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.inventory_balance import InventoryBalance
from app.models.tenant import Tenant
from app.services.fbs_supply_service import planned_shipment_date_for_orders
from tests.fbs_supply_card_fixture import seed


@pytest.mark.asyncio
async def test_c6_fbo_and_marketplace_dates_still_save_and_read(async_client):
    headers, _tenant, supply, orders = await seed(async_client)
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, orders[0])
        row = await session.get(FbsSupply, supply)
        warehouse, seller, product = row.warehouse_id, row.seller_id, order.product_id
        balance = (
            await session.scalars(
                select(InventoryBalance).where(
                    InventoryBalance.product_id == product, InventoryBalance.quantity > 0
                )
            )
        ).first()
        location = balance.storage_location_id
    fbo = await async_client.post(
        "/operations/outbound-shipment-requests",
        headers=headers,
        json={"warehouse_id": str(warehouse)},
    )
    assert fbo.status_code == 201, fbo.text
    fid = fbo.json()["id"]
    line = await async_client.post(
        f"/operations/outbound-shipment-requests/{fid}/lines",
        headers=headers,
        json={"product_id": str(product), "quantity": 1, "storage_location_id": str(location)},
    )
    assert line.status_code == 201, line.text
    submitted = await async_client.post(
        f"/operations/outbound-shipment-requests/{fid}/submit",
        headers=headers,
        json={"planned_shipment_date": "2026-10-12"},
    )
    assert submitted.status_code == 200, submitted.text
    reread = await async_client.get(
        f"/operations/outbound-shipment-requests/{fid}", headers=headers
    )
    assert reread.json()["planned_shipment_date"] == "2026-10-12"
    mp = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=headers,
        json={"warehouse_id": str(warehouse), "seller_id": str(seller), "marketplace": "ozon"},
    )
    assert mp.status_code == 201, mp.text
    mid = mp.json()["id"]
    patched = await async_client.patch(
        f"/operations/marketplace-unload-requests/{mid}",
        headers=headers,
        json={"planned_shipment_date": "2026-10-13"},
    )
    assert patched.status_code == 200, patched.text
    reread = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}", headers=headers
    )
    assert reread.json()["planned_shipment_date"] == "2026-10-13"


@pytest.mark.asyncio
async def test_c5_c6_fbs_stored_date_deadlines_and_cutoff_stay_compatible(async_client):
    headers, tenant, supply, orders = await seed(async_client)
    async with SessionLocal() as session:
        tenant_row = await session.get(Tenant, tenant)
        tenant_row.fbs_shipment_cutoff_time = time(12, 0)
        order = await session.get(FbsOrder, orders[0])
        order.created_at_wb = datetime(2026, 10, 9, 10, 0, tzinfo=UTC)
        row = await session.get(FbsSupply, supply)
        row.planned_shipment_date = date(2026, 10, 15)
        deadline, reserve = order.deadline_at, order.reserve_status
        calculated = await planned_shipment_date_for_orders(session, tenant, [order])
        assert calculated == date(2026, 10, 10)  # 10:00 UTC is after the Moscow 12:00 cutoff.
        await session.commit()
    for path in (
        f"/operations/fbs-supplies/{supply}/workspace",
        "/operations/fbs-supplies/worklist?status_group=active",
    ):
        response = await async_client.get(path, headers=headers)
        assert response.status_code == 200, response.text
        payload = response.json()
        serialized = (
            payload["supply"]
            if path.endswith("/workspace")
            else next(item for item in payload["items"] if item["id"] == str(supply))
        )
        assert serialized["planned_shipment_date"] == "2026-10-15"
    async with SessionLocal() as session:
        row = await session.get(FbsSupply, supply)
        order = await session.get(FbsOrder, orders[0])
        assert row.planned_shipment_date == date(2026, 10, 15)
        assert order.deadline_at.replace(tzinfo=UTC) == deadline.replace(tzinfo=UTC)
        assert order.reserve_status == reserve
        assert (await session.get(Tenant, tenant)).fbs_shipment_cutoff_time == time(12, 0)
