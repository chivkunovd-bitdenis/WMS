"""WMS-722 R4: a durable incoming transfer keeps its target alive until resolved."""

import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.fbs_wb_operation import FbsWbOperation
from app.services import fbs_supply_transfer_service as transfer
from app.services.wildberries_client import WildberriesClientError
from app.services.wildberries_fbs_client import MarketplaceSuppliesPage
from tests.fbs_supply_card_fixture import empty_neighbor, ready_wb_supply, snapshot


async def setup(client, monkeypatch):
    headers, tenant, source, orders = await ready_wb_supply(client, monkeypatch)
    target = await empty_neighbor(source)
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, orders[0])
        wb_id = order.wb_order_id
    monkeypatch.setattr(transfer, "_require_marketplace_token", AsyncMock(return_value="test"))
    return headers, tenant, source, target, orders[0], wb_id


async def move(client, headers, source, target, order, key="review-transfer"):
    return await client.post(
        f"/operations/fbs-supplies/{source}/transfer-orders", headers=headers,
        json={"order_ids": [str(order)], "target_supply_id": str(target) if target else None,
              "idempotency_key": key},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["patch", "readback"])
@pytest.mark.parametrize("new_target", [False, True])
async def test_delete_during_wb_wait_refuses_and_confirmed_transfer_has_live_target(
    async_client, monkeypatch, phase, new_target,
):
    headers, tenant, source, target, order, wb_id = await setup(async_client, monkeypatch)
    started, release = asyncio.Event(), asyncio.Event()

    async def patch(*args, **kwargs):
        if phase == "patch":
            started.set()
            await release.wait()

    async def read(*args, **kwargs):
        if phase == "readback":
            started.set()
            await release.wait()
        return [wb_id]

    monkeypatch.setattr(transfer, "add_orders_to_marketplace_supply", patch)
    monkeypatch.setattr(transfer, "fetch_marketplace_supply_order_ids", read)
    monkeypatch.setattr(
        transfer, "fetch_marketplace_supplies_page",
        AsyncMock(return_value=MarketplaceSuppliesPage(supplies={}, next_cursor=None)),
    )
    monkeypatch.setattr(
        transfer, "create_marketplace_supply", AsyncMock(return_value={"id": "WB-review-created"}),
    )
    moving = asyncio.create_task(move(
        async_client, headers, source, None if new_target else target, order,
    ))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        async with SessionLocal() as session:
            operation = await session.scalar(select(FbsWbOperation).where(
                FbsWbOperation.tenant_id == tenant,
                FbsWbOperation.operation_kind == "supply_transfer_orders",
            ))
            target = uuid.UUID(operation.response_summary_json["target_supply_id"])
        before = await snapshot()
        refused = await async_client.delete(f"/operations/fbs-supplies/{target}", headers=headers)
        assert refused.status_code == 409, refused.text
        assert await snapshot() == before
    finally:
        release.set()
        result = await moving
    assert result.status_code == 200, result.text
    assert result.json()["state"] == "confirmed"
    async with SessionLocal() as session:
        assert await session.get(FbsSupply, target) is not None
        assert (await session.get(FbsOrder, order)).supply_id == target


@pytest.mark.asyncio
async def test_unknown_transfer_remains_protected_until_terminal_refusal(async_client, monkeypatch):
    headers, tenant, source, target, order, _ = await setup(async_client, monkeypatch)
    patch = AsyncMock(side_effect=WildberriesClientError("transport_error"))
    monkeypatch.setattr(transfer, "add_orders_to_marketplace_supply", patch)
    monkeypatch.setattr(transfer, "fetch_marketplace_supply_order_ids", AsyncMock(return_value=[]))
    pending = await move(async_client, headers, source, target, order)
    assert pending.status_code == 200 and pending.json()["state"] == "pending_confirmation"
    response = await async_client.delete(f"/operations/fbs-supplies/{target}", headers=headers)
    assert response.status_code == 409, response.text
    async with SessionLocal() as session:
        assert (await session.get(FbsOrder, order)).supply_id == source
        operation = await session.scalar(select(FbsWbOperation).where(
            FbsWbOperation.tenant_id == tenant,
            FbsWbOperation.operation_kind == "supply_transfer_orders",
        ))
        # A definitive refusal ends this durable intent; unknown was not a refusal.
        operation.state = "failed"
        operation.response_summary_json = {
            **operation.response_summary_json, "failed_order_ids": [str(order)],
        }
        await session.commit()
    response = await async_client.delete(f"/operations/fbs-supplies/{target}", headers=headers)
    assert response.status_code == 204, response.text
    replay = await move(async_client, headers, source, target, order)
    assert replay.status_code == 200 and replay.json()["state"] == "failed"
    assert patch.await_count == 1


@pytest.mark.asyncio
async def test_deleted_target_cannot_dispatch_or_apply_stale_confirmation(
    async_client, monkeypatch,
):
    headers, _, source, target, order, _ = await setup(async_client, monkeypatch)
    patch = AsyncMock()
    monkeypatch.setattr(transfer, "add_orders_to_marketplace_supply", patch)
    async with SessionLocal() as session:
        source_row = await session.get(FbsSupply, source)
        target_row = await session.get(FbsSupply, target)
        order_row = await session.get(FbsOrder, order)
        response = await async_client.delete(f"/operations/fbs-supplies/{target}", headers=headers)
        assert response.status_code == 204, response.text
        with pytest.raises(transfer.FbsSupplyError, match="supply_not_found"):
            await transfer._apply_confirmed(session, source_row, target_row, [order_row])
        await session.rollback()
    response = await move(async_client, headers, source, target, order)
    assert response.status_code == 404, response.text
    patch.assert_not_awaited()
    async with SessionLocal() as session:
        assert (await session.get(FbsOrder, order)).supply_id == source


@pytest.mark.asyncio
async def test_delete_cannot_enter_before_transfer_intent_is_committed(async_client, monkeypatch):
    headers, _, source, target, order, wb_id = await setup(async_client, monkeypatch)
    committing, allow_commit = asyncio.Event(), asyncio.Event()
    dispatching, allow_dispatch = asyncio.Event(), asyncio.Event()
    original_commit = AsyncSession.commit

    async def commit(session):
        if any(isinstance(row, FbsWbOperation)
               and row.operation_kind == "supply_transfer_orders" for row in session.new):
            committing.set()
            await allow_commit.wait()
        await original_commit(session)

    async def patch(*args, **kwargs):
        dispatching.set()
        await allow_dispatch.wait()

    monkeypatch.setattr(AsyncSession, "commit", commit)
    monkeypatch.setattr(transfer, "add_orders_to_marketplace_supply", patch)
    monkeypatch.setattr(
        transfer, "fetch_marketplace_supply_order_ids", AsyncMock(return_value=[wb_id]),
    )
    moving = asyncio.create_task(move(async_client, headers, source, target, order))
    deleting = None
    try:
        await asyncio.wait_for(committing.wait(), timeout=5)
        deleting = asyncio.create_task(async_client.delete(
            f"/operations/fbs-supplies/{target}", headers=headers,
        ))
        # Exercise deletion before the journal becomes visible. If it is
        # blocked by the row lock, let intent commit and the refusal complete.
        await asyncio.wait({deleting}, timeout=0.1)
        allow_commit.set()
        await asyncio.wait_for(dispatching.wait(), timeout=5)
        refusal = await deleting
    finally:
        allow_commit.set()
        allow_dispatch.set()
        result = await moving
        if deleting is not None:
            await deleting
    assert refusal.status_code == 409, refusal.text
    assert result.status_code == 200 and result.json()["state"] == "confirmed", result.text
    async with SessionLocal() as session:
        assert await session.get(FbsSupply, target) is not None
        assert (await session.get(FbsOrder, order)).supply_id == target
