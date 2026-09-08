"""Resume releases its real SQLAlchemy pool slot during each WB request."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.session import engine as fixture_engine
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services import fbs_supply_service as service
from app.services.wildberries_client import WildberriesClientError


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "timeout", "concurrent_confirmed"])
async def test_resume_http_releases_pool_and_rereads_before_finalizing(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    tenant = Tenant(name="Resume QA", slug=f"resume-{uuid.uuid4().hex}")
    db_session.add(tenant)
    await db_session.flush()
    seller = Seller(tenant_id=tenant.id, name="Synthetic seller")
    warehouse = Warehouse(tenant_id=tenant.id, name="Synthetic warehouse", code="RESUME")
    db_session.add_all([seller, warehouse])
    await db_session.flush()
    supply = FbsSupply(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        name="Existing supply",
        wb_supply_id="WB-GI-272",
        delivery_type="warehouse_sc",
    )
    db_session.add(supply)
    await db_session.flush()
    order = FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        wb_order_id=272,
        status="new",
        mapping_status="unmapped",
        reserve_status="released",
        created_at_wb=datetime.now(UTC),
        deadline_at=datetime.now(UTC),
    )
    db_session.add(order)
    await db_session.flush()
    operation = FbsWbOperation(
        tenant_id=tenant.id,
        seller_id=seller.id,
        operation_kind="supply_from_orders",
        idempotency_key="resume-272",
        state="pending_confirmation",
        local_entity_type="fbs_supply",
        local_entity_id=supply.id,
        wb_object_kind="supply",
        wb_object_id=supply.wb_supply_id,
    )
    db_session.add(operation)
    await db_session.commit()
    tenant_id, order_id, supply_id, operation_id = tenant.id, order.id, supply.id, operation.id

    tiny_engine = create_async_engine(
        fixture_engine.url, pool_size=1, max_overflow=0, pool_timeout=0.2
    )
    sessions = async_sessionmaker(tiny_engine, expire_on_commit=False)
    calls: asyncio.Queue[tuple[str, asyncio.Event]] = asyncio.Queue()
    http_calls: list[str] = []

    async def pause_http(name: str) -> None:
        http_calls.append(name)
        release = asyncio.Event()
        await calls.put((name, release))
        await asyncio.wait_for(release.wait(), timeout=3)

    read_count = 0

    async def readback(*args: Any, **kwargs: Any) -> tuple[str, set[int]]:
        nonlocal read_count
        read_count += 1
        await pause_http(f"get-{read_count}")
        return ("pending_confirmation", set()) if read_count == 1 else ("confirmed", {272})

    async def add(*args: Any, **kwargs: Any) -> None:
        await pause_http("add")
        if outcome == "timeout":
            raise WildberriesClientError("transport_error")

    async def token(*args: Any, **kwargs: Any) -> str:
        return "synthetic-no-remote-access"

    async def never_create(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Resume must never create another WB supply")

    async def workspace(
        session: AsyncSession, tenant: uuid.UUID, supply: uuid.UUID
    ) -> dict[str, Any]:
        row = await session.get(FbsOrder, order_id)
        assert row
        return {"supply_id": str(supply), "order_status": row.status}

    monkeypatch.setattr(service, "_require_marketplace_token", token)
    monkeypatch.setattr(service, "reconcile_supply_orders", readback)
    monkeypatch.setattr(service, "_execute_wb_batch_add", add)
    monkeypatch.setattr(service, "create_marketplace_supply", never_create)
    monkeypatch.setattr(service, "get_supply_workspace", workspace)

    async def run_resume() -> dict[str, Any]:
        async with sessions() as session, httpx.AsyncClient() as client:
            op = await session.get(FbsWbOperation, operation_id)
            loaded_order = await session.get(FbsOrder, order_id)
            assert op and loaded_order
            result = await service._resume_from_orders_operation(
                session, tenant_id, op, orders=[loaded_order], http_client=client
            )
            await session.commit()
            return result

    task = asyncio.create_task(run_resume())
    try:
        expected_calls = ["get-1", "add"] + ([] if outcome == "timeout" else ["get-2"])
        for expected in expected_calls:
            name, release = await asyncio.wait_for(calls.get(), timeout=3)
            assert name == expected
            # With just one slot, this SELECT fails if the HTTP owner keeps it.
            async with sessions() as other_screen:
                assert await other_screen.scalar(text("select 1")) == 1
                if outcome == "concurrent_confirmed" and name == "get-2":
                    winner = await other_screen.get(FbsWbOperation, operation_id)
                    progressed_order = await other_screen.get(FbsOrder, order_id)
                    assert winner and progressed_order
                    winner.state = "confirmed"
                    progressed_order.supply_id = supply_id
                    progressed_order.status = "done"
                    await other_screen.commit()
            release.set()
        if outcome == "timeout":
            with pytest.raises(service.FbsSupplyError) as error:
                await task
            assert error.value.code == "wb_timeout"
        else:
            result = await task
            assert result["supply_id"] == str(supply_id)
            assert result["order_status"] == (
                "done" if outcome == "concurrent_confirmed" else "in_supply"
            )
        async with sessions() as reread:
            op = await reread.get(FbsWbOperation, operation_id)
            assert op and op.state == (
                "pending_confirmation" if outcome == "timeout" else "confirmed"
            )
            assert len(list(await reread.scalars(select(FbsSupply)))) == 1
            assert len(list(await reread.scalars(select(FbsWbOperation)))) == 1
        assert http_calls == expected_calls
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await tiny_engine.dispose()
