"""Real PostgreSQL replay of stale act and balance objects; isolated DB only."""
from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.db.session import SessionLocal, engine
from app.models.discrepancy_act import DiscrepancyAct, DiscrepancyActLine
from app.models.inbound_intake import InboundIntakeRequest
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.user import User
from app.services import discrepancy_act_service as acts
from app.services import inventory_service
from app.services.sorting_location_service import get_or_create_sorting_location
from tests.test_inventory_counts import _balance, _product, _tenant

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(engine.dialect.name != "postgresql", reason="real PostgreSQL required"),
]


async def _seed(
    client: AsyncClient,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    setup = await _tenant(client, "ActReplay")
    product = await _product(client, setup, name="Isolated replay product")
    async with SessionLocal() as session:
        actor = await session.scalar(select(User.id).where(User.tenant_id == setup.tenant_id))
        assert actor is not None
        location = await get_or_create_sorting_location(
            session, setup.tenant_id, setup.warehouse_id,
        )
        inbound = InboundIntakeRequest(tenant_id=setup.tenant_id, warehouse_id=setup.warehouse_id,
                                      status="sorting")
        session.add(inbound)
        await session.flush()
        act = DiscrepancyAct(tenant_id=setup.tenant_id, inbound_intake_request_id=inbound.id,
                             status="confirmed")
        session.add(act)
        await session.flush()
        session.add(DiscrepancyActLine(act_id=act.id, product_id=product, quantity=-1))
        await session.commit()
        ids = setup.tenant_id, actor, act.id, product, location.id
    await _balance(setup, product, 5, location_id=ids[4])
    return ids


async def _wait_blocked(observer, pid, task) -> None:  # type: ignore[no-untyped-def]
    async with asyncio.timeout(5):
        while not await observer.scalar(text("select cardinality(pg_blocking_pids(:pid)) > 0"),
                                        {"pid": pid}):
            assert not task.done(), "operation did not wait for the required row lock"
            await asyncio.sleep(0.01)


async def test_postgres_two_approvals_reread_stale_act(async_client: AsyncClient) -> None:
    tenant, actor, act_id, product, location = await _seed(async_client)
    async with SessionLocal() as first, SessionLocal() as second:
        stale = await acts.get_act(second, tenant, act_id)
        assert stale is not None and stale.status == "confirmed"
        pid = await second.scalar(text("select pg_backend_pid()"))
        await acts.get_act(first, tenant, act_id, lock=True)
        task = asyncio.create_task(acts.approve_act(second, tenant, act_id, actor_user_id=actor))
        try:
            await _wait_blocked(first, pid, task)
            approved = await acts.approve_act(first, tenant, act_id, actor_user_id=actor)
            assert approved.status == "approved"
            with pytest.raises(acts.DiscrepancyActError, match="bad_status"):
                await asyncio.wait_for(task, timeout=10)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    async with SessionLocal() as check:
        assert await check.scalar(select(InventoryBalance.quantity).where(
            InventoryBalance.product_id == product,
            InventoryBalance.storage_location_id == location,
        )) == 4
        movements = (await check.scalars(select(InventoryMovement).where(
            InventoryMovement.product_id == product,
        ))).all()
        assert len(movements) == 1 and movements[0].quantity_delta == -1


async def test_postgres_approve_rereads_balance_after_product_wait(
    async_client: AsyncClient,
) -> None:
    tenant, actor, act_id, product, location = await _seed(async_client)
    async with SessionLocal() as approver, SessionLocal() as writer:
        stale = (await approver.scalars(select(InventoryBalance).where(
            InventoryBalance.product_id == product,
        ))).one()
        assert stale.quantity == 5
        pid = await approver.scalar(text("select pg_backend_pid()"))
        await inventory_service.record_movement_and_adjust_balance(
            writer, tenant_id=tenant, product_id=product, storage_location_id=location,
            quantity_delta=3, movement_type="inbound_intake", actor_user_id=actor,
        )
        task = asyncio.create_task(acts.approve_act(approver, tenant, act_id, actor_user_id=actor))
        try:
            await _wait_blocked(writer, pid, task)
            await writer.commit()
            assert (await asyncio.wait_for(task, timeout=10)).status == "approved"
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    async with SessionLocal() as check:
        assert await check.scalar(select(InventoryBalance.quantity).where(
            InventoryBalance.product_id == product,
            InventoryBalance.storage_location_id == location,
        )) == 7
        movements = (await check.scalars(select(InventoryMovement).where(
            InventoryMovement.product_id == product,
        ))).all()
        assert sorted(row.quantity_delta for row in movements) == [-1, 3]


async def test_postgres_empty_container_delete_waits_for_stock_writer(
    async_client: AsyncClient,
) -> None:
    from app.models.warehouse_box import WarehouseBox
    from app.services import inventory_count_service as counts
    from tests.test_inventory_counts import _create_all, _create_container

    setup = await _tenant(async_client, "DeleteReplay")
    product = await _product(async_client, setup, name="Concurrent container receipt")
    count = await _create_all(async_client, setup)
    cid = await _create_container(async_client, setup, count["id"], "box",
                                  cell_id=setup.location_id)
    async with SessionLocal() as deleter, SessionLocal() as writer:
        actor = await writer.scalar(select(User.id).where(User.tenant_id == setup.tenant_id))
        pid = await deleter.scalar(text("select pg_backend_pid()"))
        await inventory_service.record_movement_and_adjust_balance(
            writer, tenant_id=setup.tenant_id, product_id=product,
            storage_location_id=setup.location_id, quantity_delta=3,
            movement_type="inbound_intake", actor_user_id=actor,
            container_kind="box", container_id=cid,
        )
        task = asyncio.create_task(counts.delete_document_container(
            deleter, setup.tenant_id, uuid.UUID(count["id"]), kind="box", container_id=cid,
        ))
        try:
            await _wait_blocked(writer, pid, task)
            await writer.commit()
            with pytest.raises(counts.InventoryCountError, match="container_not_empty"):
                await asyncio.wait_for(task, timeout=10)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    async with SessionLocal() as check:
        assert await check.get(WarehouseBox, cid) is not None
        assert await check.scalar(select(InventoryBalance.quantity).where(
            InventoryBalance.product_id == product,
        )) == 3
