"""WMS-272: durable create identity while WB waits without a database connection."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
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
@pytest.mark.parametrize(
    "outcome",
    [
        "success",
        "transport",
        "invalid",
        "rejected",
        "cancelled",
        "readback_timeout",
        "owner_cancelled",
        "same_key",
        "rotated_key",
        "loser_failed",
        "partial_winner",
    ],
)
async def test_create_http_releases_pool_and_persists_identity(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    tenant = Tenant(name="Create QA", slug=f"create-{uuid.uuid4().hex}")
    db_session.add(tenant)
    await db_session.flush()
    seller = Seller(tenant_id=tenant.id, name="Synthetic seller")
    warehouse = Warehouse(tenant_id=tenant.id, name="Synthetic warehouse", code="CREATE")
    db_session.add_all([seller, warehouse])
    await db_session.flush()
    orders = [
        FbsOrder(
            tenant_id=tenant.id,
            seller_id=seller.id,
            warehouse_id=warehouse.id,
            wb_order_id=27200 + index,
            status="new",
            mapping_status="unmapped",
            reserve_status="released",
            created_at_wb=datetime.now(UTC),
            deadline_at=datetime.now(UTC),
        )
        for index in range(3)
    ]
    db_session.add_all(orders)
    await db_session.commit()
    tenant_id, warehouse_id = tenant.id, warehouse.id
    order_ids = [order.id for order in orders]
    tiny_engine = create_async_engine(
        fixture_engine.url, pool_size=1, max_overflow=0, pool_timeout=0.2
    )
    sessions = async_sessionmaker(tiny_engine, expire_on_commit=False)
    calls: asyncio.Queue[tuple[str, asyncio.Event]] = asyncio.Queue()
    create_calls: list[str] = []
    add_calls: list[str] = []

    async def pause_http(name: str) -> None:
        release = asyncio.Event()
        await calls.put((name, release))
        await asyncio.wait_for(release.wait(), timeout=5)

    async def token(*args: Any, **kwargs: Any) -> str:
        return "synthetic-no-remote-access"

    async def validate(
        session: AsyncSession, tenant: uuid.UUID, ids: list[uuid.UUID], **kwargs: Any
    ) -> Any:
        rows = await service.load_orders_for_validation(
            session, tenant, ids, for_update=kwargs.get("for_update", False)
        )
        return SimpleNamespace(
            compatible=True,
            orders=rows,
            summary=SimpleNamespace(
                wms_warehouse_id=warehouse_id, cargo_type="MGT", wb_warehouse_id=1
            ),
        )

    async def create(*args: Any, name: str, **kwargs: Any) -> dict[str, Any]:
        create_calls.append(name)
        if name == "main" and create_calls.count("main") > 1:
            return {"id": "WB-GI-winner"}
        if name == "main":
            await pause_http("create")
            if outcome in {"transport", "loser_failed"}:
                raise WildberriesClientError("transport_error")
            if outcome == "invalid":
                return {}
            if outcome == "rejected":
                raise WildberriesClientError("upstream_error", status_code=400)
        return {"id": f"WB-GI-{name}"}

    async def add(*args: Any, wb_supply_id: str, **kwargs: Any) -> None:
        add_calls.append(wb_supply_id)
        if wb_supply_id == "WB-GI-main":
            await pause_http("add")

    async def readback(
        *args: Any, wb_supply_id: str, expected_wb_order_ids: set[int], **kwargs: Any
    ) -> tuple[str, set[int]]:
        if outcome == "partial_winner" and wb_supply_id == "WB-GI-winner":
            return "pending_confirmation", {27200}
        if wb_supply_id == "WB-GI-main":
            await pause_http("readback")
            if outcome == "readback_timeout":
                raise WildberriesClientError("transport_error")
        return "confirmed", expected_wb_order_ids

    async def workspace(
        session: AsyncSession, tenant: uuid.UUID, supply_id: uuid.UUID
    ) -> dict[str, Any]:
        supply = await session.get(FbsSupply, supply_id)
        assert supply
        return {"id": str(supply_id), "wb_id": supply.wb_supply_id}

    monkeypatch.setattr(service, "_require_marketplace_token", token)
    monkeypatch.setattr(service, "validate_supply_composition", validate)
    monkeypatch.setattr(service, "create_marketplace_supply", create)
    monkeypatch.setattr(service, "_execute_wb_batch_add", add)
    monkeypatch.setattr(service, "reconcile_supply_orders", readback)
    monkeypatch.setattr(service, "get_supply_workspace", workspace)

    async def run(name: str, key: str, order_index: int = 0) -> dict[str, Any]:
        async with sessions() as session, httpx.AsyncClient() as client:
            result = await service.create_supply_from_orders(
                session,
                tenant_id,
                name=name,
                order_ids=order_ids[:2] if order_index == 0 else [order_ids[order_index]],
                planned_delivery_type="warehouse_sc",
                planned_destination=None,
                idempotency_key=key,
                http_client=client,
            )
            await session.commit()
            return result

    task = asyncio.create_task(run("main", "original-key"))
    try:
        name, release = await asyncio.wait_for(calls.get(), timeout=5)
        assert name == "create"
        async with sessions() as observer:
            assert await observer.scalar(text("select 1")) == 1
            assert await observer.scalar(select(FbsWbOperation)) is None
            assert await observer.scalar(select(FbsSupply)) is None
        # The operation owns only its order set, not the whole seller.
        other = await run("other", "disjoint-key", 2)
        assert other["wb_id"] == "WB-GI-other"
        assert create_calls == ["main", "other"]
        if outcome in {"same_key", "rotated_key", "loser_failed", "partial_winner"}:
            retry_key = "original-key" if outcome == "same_key" else "rotated-key"
            winner = await run("main", retry_key)
            assert winner["wb_id"] == "WB-GI-winner"
            release.set()
            if outcome == "loser_failed":
                with pytest.raises(service.FbsSupplyError):
                    await task
            else:
                assert await task == winner
            async with sessions() as observer:
                assert await observer.scalar(text("select 1")) == 1
                own_operations = list(
                    (
                        await observer.scalars(
                            select(FbsWbOperation).where(
                                FbsWbOperation.wb_object_id != "WB-GI-other"
                            )
                        )
                    ).all()
                )
                assert len(own_operations) == 1
                assert own_operations[0].state == "confirmed"
                assert own_operations[0].wb_object_id == "WB-GI-winner"
                for order_id in order_ids[:2]:
                    order = await observer.get(FbsOrder, order_id)
                    assert order
                    if outcome == "partial_winner" and order.wb_order_id == 27201:
                        assert order.supply_id is None and order.status == "new"
                    else:
                        assert str(order.supply_id) == winner["id"]
                if outcome == "partial_winner":
                    assert [
                        row["wb_order_id"] for row in winner["partial_rejection"]["accepted_orders"]
                    ] == [27200]
                    assert [
                        row["wb_order_id"] for row in winner["partial_rejection"]["rejected_orders"]
                    ] == [27201]
            assert "WB-GI-main" not in add_calls
            assert add_calls.count("WB-GI-winner") == 1
            return
        if outcome == "owner_cancelled":
            task.cancel()
        release.set()
        if outcome in {"transport", "invalid", "rejected", "owner_cancelled"}:
            error_type = (
                asyncio.CancelledError if outcome == "owner_cancelled" else service.FbsSupplyError
            )
            with pytest.raises(error_type):
                await task
            async with sessions() as observer:
                operations = list((await observer.scalars(select(FbsWbOperation))).all())
                assert len(operations) == 1 and operations[0].wb_object_id == "WB-GI-other"
                assert (
                    await observer.scalar(select(FbsSupply).where(FbsSupply.name == "main")) is None
                )
            # The same browser key works after a failed or cancelled empty-draft HTTP.
            retried = await run("retry", "original-key")
            assert retried["wb_id"] == "WB-GI-retry"
            assert "WB-GI-main" not in add_calls
        else:
            for expected in ("add", "readback"):
                name, release = await asyncio.wait_for(calls.get(), timeout=5)
                assert name == expected
                async with sessions() as observer:
                    assert await observer.scalar(text("select 1")) == 1
                    op = await observer.scalar(
                        select(FbsWbOperation).where(FbsWbOperation.wb_object_id == "WB-GI-main")
                    )
                    assert op
                    operation_id, supply_id = op.id, op.local_entity_id
                    supply = await observer.get(FbsSupply, supply_id)
                    assert op and op.state == "pending_confirmation"
                    assert op.wb_object_id == "WB-GI-main"
                    assert supply and supply.wb_supply_id == "WB-GI-main"
                    if name == "add":
                        for readback_ids in ([], [27200]):
                            await service._close_pending_operation_if_complete(
                                observer, supply, wb_order_ids=readback_ids, unresolved=[]
                            )
                            await observer.commit()
                            await observer.refresh(op)
                            assert op.state == "pending_confirmation"
                    if outcome == "cancelled" and name == "readback":
                        cancelled = await observer.get(FbsOrder, order_ids[0])
                        assert cancelled
                        cancelled.status = "cancelled"
                        await observer.commit()
                release.set()
            if outcome == "readback_timeout":
                with pytest.raises(service.FbsSupplyError) as unavailable:
                    await task
                assert unavailable.value.context["wb_supply_id"] == "WB-GI-main"
                async with sessions() as observer:
                    op = await observer.get(FbsWbOperation, operation_id)
                    assert op and op.state == "pending_confirmation"
                    assert op.wb_object_id == "WB-GI-main"
                assert create_calls == ["main", "other"]
                return
            result = await task
            assert result["id"] == str(supply_id)
            async with sessions() as observer:
                op = await observer.get(FbsWbOperation, operation_id)
                order = await observer.get(FbsOrder, order_ids[0])
                assert op and op.state == "confirmed"
                assert order and order.status == (
                    "cancelled" if outcome == "cancelled" else "in_supply"
                )
                assert order.reserve_status == "released"
            assert (await run("main", "original-key"))["id"] == str(supply_id)
            assert create_calls == ["main", "other"]
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await tiny_engine.dispose()


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
async def test_transaction_claim_shares_key_and_releases_pool_atomically() -> None:
    from app.services.marketplace_seller_lock_service import marketplace_seller_lock

    if fixture_engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL advisory transaction lock compatibility proof")
    tiny = create_async_engine(fixture_engine.url, pool_size=1, max_overflow=0, pool_timeout=0.2)
    others = create_async_engine(fixture_engine.url, pool_size=1, max_overflow=0)
    sessions = async_sessionmaker(tiny)
    outsiders = async_sessionmaker(others)
    seller_id = uuid.uuid4()
    try:
        async with sessions() as claim, outsiders() as outsider:
            async with marketplace_seller_lock(
                claim, seller_id, "wb", transaction_scoped=True
            ) as acquired:
                assert acquired
            # Leaving the context cannot expose an uncommitted claim to a peer.
            async with marketplace_seller_lock(outsider, seller_id, "wb") as acquired:
                assert not acquired
            await outsider.rollback()
            await claim.commit()
            # Commit both ends the claim's lock and gives its only slot back.
            async with sessions() as unrelated:
                assert await unrelated.scalar(text("select 1")) == 1
            async with marketplace_seller_lock(outsider, seller_id, "wb") as acquired:
                assert acquired
            await outsider.rollback()
            async with marketplace_seller_lock(
                claim, seller_id, "wb", transaction_scoped=True
            ) as acquired:
                assert acquired
            await claim.rollback()
            async with marketplace_seller_lock(outsider, seller_id, "wb") as acquired:
                assert acquired
    finally:
        await tiny.dispose()
        await others.dispose()
