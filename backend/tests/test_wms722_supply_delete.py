"""WMS-722 local deletion: real API, saved records, and concurrent requests."""

import asyncio

import httpx
import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.fbs_assembly_task import FbsAssemblyTask, FbsAssemblyTaskSupply
from app.models.fbs_order import FbsOrder
from app.models.fbs_packing_box import FbsPackingBox
from app.models.fbs_print_asset import FbsPrintAsset
from app.models.fbs_supply import FbsSupply
from app.models.fbs_trbx import FbsTrbx
from app.models.user import User
from app.models.warehouse_box import WarehouseBox
from tests.fbs_supply_card_fixture import boxes, empty_neighbor, seed, snapshot


async def delete(client, headers, supply):
    return await client.delete(f"/operations/fbs-supplies/{supply}", headers=headers)


@pytest.mark.asyncio
@pytest.mark.parametrize("marketplace", ["wb", "ozon"])
async def test_c1_local_delete_disappears_from_worklists_and_old_id(
    async_client, monkeypatch, marketplace
):
    headers, _tenant, supply, _ = await seed(async_client, marketplace, count=0)
    calls = []
    original = httpx.AsyncClient.send

    async def send(self, request, **kwargs):
        if request.url.host != "test":
            calls.append((request.method, str(request.url)))
            raise AssertionError("Local deletion must not call a marketplace")
        return await original(self, request, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    response = await delete(async_client, headers, supply)
    assert response.status_code in (200, 204), response.text
    for group in ("active", "delivery", "done"):
        response = await async_client.get(
            "/operations/fbs-supplies/worklist", headers=headers, params={"status_group": group}
        )
        assert response.status_code == 200, response.text
        assert str(supply) not in {r["id"] for r in response.json()["items"]}
    for suffix in ("", "/workspace"):
        response = await async_client.get(
            f"/operations/fbs-supplies/{supply}{suffix}", headers=headers
        )
        assert response.status_code == 404, response.text
    assert calls == []
    async with SessionLocal() as session:
        assert await session.get(FbsSupply, supply) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["draft", "assembling", "packed", "in_delivery", "done"])
async def test_c2_empty_auxiliary_records_do_not_block_any_status(async_client, status):
    headers, tenant, supply, _ = await seed(async_client, count=0)
    box_ids = await boxes(tenant, supply, 1)
    async with SessionLocal() as session:
        row = await session.get(FbsSupply, supply)
        row.status = status
        box = await session.get(FbsPackingBox, box_ids[0])
        physical_id = box.warehouse_box_id
        trbx = FbsTrbx(
            supply_id=supply, wb_trbx_id="EXTERNAL-MUST-STAY", packaging_box_id=physical_id
        )
        session.add(trbx)
        await session.flush()
        box.trbx_id = trbx.id
        asset = FbsPrintAsset(
            tenant_id=tenant, seller_id=row.seller_id, kind="supply_qr", fbs_supply_id=supply
        )
        session.add(asset)
        await session.commit()
        trbx_id, asset_id = trbx.id, asset.id
    response = await delete(async_client, headers, supply)
    assert response.status_code in (200, 204), response.text
    async with SessionLocal() as session:
        assert await session.get(FbsSupply, supply) is None
        assert await session.get(FbsPackingBox, box_ids[0]) is None
        assert await session.get(FbsTrbx, trbx_id) is None
        assert await session.get(FbsPrintAsset, asset_id) is None
        assert await session.get(WarehouseBox, physical_id) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("order_status", ["new", "packed", "cancelled"])
async def test_c3_every_linked_order_blocks_direct_deletion(async_client, order_status):
    headers, tenant, supply, ids = await seed(async_client, count=1)
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, ids[0])
        order.status = order_status
        await session.commit()
    before = await snapshot()
    response = await delete(async_client, headers, supply)
    assert response.status_code == 409, response.text
    assert await snapshot() == before
    # The independent fixture transition uses the existing cancellation detach service.
    from app.services.fbs_packaging_integration_service import detach_cancelled_order_from_supply

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, ids[0])
        order.status = "cancelled"
        await detach_cancelled_order_from_supply(session, tenant, order, actor_user_id=None)
        await session.commit()
    response = await delete(async_client, headers, supply)
    assert response.status_code in (200, 204), response.text
    async with SessionLocal() as session:
        assert await session.get(FbsSupply, supply) is None
        assert (await session.get(FbsOrder, ids[0])).supply_id is None


@pytest.mark.asyncio
async def test_c4_empty_deletion_preserves_neighbor_orders_stock_reserves_and_movements(
    async_client,
):
    headers, tenant, neighbor, ids = await seed(async_client)
    target = await empty_neighbor(neighbor)
    async with SessionLocal() as session:
        task = FbsAssemblyTask(tenant_id=tenant, number="722", idempotency_key="shared-task")
        session.add(task)
        await session.flush()
        session.add_all(
            [
                FbsAssemblyTaskSupply(task_id=task.id, supply_id=target),
                FbsAssemblyTaskSupply(task_id=task.id, supply_id=neighbor),
            ]
        )
        await session.commit()
        task_id = task.id
    before = await snapshot(exclude=("fbs_supplies", "fbs_assembly_task_supplies"))
    response = await delete(async_client, headers, target)
    assert response.status_code in (200, 204), response.text
    assert await snapshot(exclude=("fbs_supplies", "fbs_assembly_task_supplies")) == before
    async with SessionLocal() as session:
        assert await session.get(FbsAssemblyTask, task_id) is not None
        links = list((await session.scalars(select(FbsAssemblyTaskSupply))).all())
        assert [(link.task_id, link.supply_id) for link in links] == [(task_id, neighbor)]
        assert await session.get(FbsSupply, neighbor) is not None
        for oid in ids:
            assert (await session.get(FbsOrder, oid)).supply_id == neighbor


@pytest.mark.asyncio
async def test_c5_duplicate_and_concurrent_deletes_are_idempotent(async_client):
    headers, _tenant, supply, _ = await seed(async_client, count=0)
    results = await asyncio.gather(
        delete(async_client, headers, supply), delete(async_client, headers, supply)
    )
    assert [r.status_code for r in results] == [204, 204] or all(
        r.status_code in (200, 204) for r in results
    ), [r.text for r in results]
    response = await delete(async_client, headers, supply)
    assert response.status_code in (200, 204), response.text
    async with SessionLocal() as session:
        assert await session.get(FbsSupply, supply) is None


@pytest.mark.asyncio
async def test_c7_unauthenticated_and_foreign_tenant_cannot_delete(async_client):
    headers, tenant, supply, _ = await seed(async_client, count=0)
    other_headers, _, _other, _ = await seed(async_client, count=0)
    before = await snapshot()
    no_access = await delete(async_client, {}, supply)
    assert no_access.status_code in (401, 403), no_access.text
    foreign = await delete(async_client, other_headers, supply)
    assert foreign.status_code in (403, 404), foreign.text
    assert await snapshot() == before
    async with SessionLocal() as session:
        user = (await session.scalars(select(User).where(User.tenant_id == tenant))).one()
        user.role = "fulfillment_staff"
        await session.commit()
    before = await snapshot()
    denied = await delete(async_client, headers, supply)
    assert denied.status_code == 403, denied.text
    assert await snapshot() == before


@pytest.mark.asyncio
async def test_c5_adding_and_deleting_share_one_consistent_outcome(async_client, monkeypatch):
    from app.services import fbs_supply_service as svc
    from tests.fbs_supply_card_fixture import add_orders as add
    from tests.fbs_supply_card_fixture import ready_wb_supply as setup

    headers, _tenant, neighbor, orders = await setup(async_client, monkeypatch)
    target = await empty_neighbor(neighbor)
    confirmed = set()

    async def read(client, **kwargs):
        return "confirmed", set(confirmed)

    async def write(client, *, order_ids, **kwargs):
        confirmed.update(order_ids)

    monkeypatch.setattr(svc, "reconcile_supply_orders", read)
    monkeypatch.setattr(svc, "add_orders_to_marketplace_supply", write)
    responses = await asyncio.gather(
        delete(async_client, headers, target), add(async_client, headers, target, orders[1:2])
    )
    deletion, addition = responses
    assert deletion.status_code in (200, 204, 409), deletion.text
    assert addition.status_code in (200, 404, 409), addition.text
    async with SessionLocal() as session:
        row = await session.get(FbsSupply, target)
        order = await session.get(FbsOrder, orders[1])
        if addition.status_code == 200:
            assert row is not None and order.supply_id == target
            assert deletion.status_code == 409
        else:
            assert row is None and order.supply_id is None
            assert deletion.status_code in (200, 204)
