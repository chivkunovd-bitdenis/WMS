"""WMS-058: a late pick request must not move another order's shipped stock."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderProduct, FbsOrderProductPick
from app.models.fbs_supply import FbsSupply
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.user import User
from app.models.warehouse_box import WarehouseBox
from app.services import fbs_picking_service as picking
from app.services import fbs_shipment_service as shipment
from app.services import inventory_service
from app.services.fbs_supply_reconcile_service import create_pending_deliver_operation
from app.services.ozon_fbs_process_service import OzonHandoffResult
from app.services.sorting_location_service import get_or_create_sorting_location
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
    _seed_pick_supply,
)


@dataclass
class Case:
    headers: dict[str, str]
    tenant: uuid.UUID
    supply: uuid.UUID
    order: uuid.UUID
    product: uuid.UUID
    source: uuid.UUID
    sorting: uuid.UUID
    actor: uuid.UUID
    box: uuid.UUID


@pytest_asyncio.fixture
async def case(async_client: AsyncClient) -> Case:
    headers, suffix, tenant = await _register_ff_admin(async_client)
    seller, warehouse, source = await _create_seller_and_warehouse(async_client, headers, suffix)
    product = await _create_product(
        async_client,
        headers,
        seller,
        sku=f"terminal-{suffix}",
        barcode=f"B-{suffix}",
    )
    supply, orders, _ = await _seed_pick_supply(
        async_client,
        headers,
        tenant,
        seller,
        warehouse,
        source,
        product,
        stock_qty=0,
        order_specs=[(1, timedelta(hours=24))],
        barcode=f"B-{suffix}",
        marketplace="ozon",
        position_quantity=1,
    )
    async with SessionLocal() as session:
        actor = await session.scalar(select(User).where(User.tenant_id == tenant))
        assert actor is not None
        sorting = await get_or_create_sorting_location(session, tenant, warehouse)
        box = WarehouseBox(
            tenant_id=tenant,
            warehouse_id=warehouse,
            storage_location_id=source,
            internal_barcode=f"BOX-{suffix}",
        )
        session.add(box)
        await session.flush()
        for location, quantity, container in [(source, 2, box.id), (sorting.id, 1, None)]:
            await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=tenant,
                product_id=product,
                storage_location_id=location,
                quantity_delta=quantity,
                movement_type="inbound_intake",
                actor_user_id=actor.id,
                container_kind="box" if container else None,
                container_id=container,
            )
        order = await session.get(FbsOrder, orders[0])
        assert order is not None
        order.pack_status = "packed"
        await picking.manual_pick_product(
            session,
            tenant,
            supply,
            location_id=source,
            product_id=product,
            order_id=orders[0],
            idempotency_key="first-pick",
            actor=actor,
            container_kind="box",
            container_id=box.id,
        )
        await session.commit()
        return Case(
            headers, tenant, supply, orders[0], product, source, sorting.id, actor.id, box.id
        )


async def _snapshot(case: Case) -> tuple[list[tuple[str, str, int]], int, int]:
    async with SessionLocal() as session:
        balances = (
            (
                await session.execute(
                    select(InventoryBalance).where(
                        InventoryBalance.product_id == case.product,
                    )
                )
            )
            .scalars()
            .all()
        )
        position = await session.scalar(
            select(FbsOrderProduct).where(
                FbsOrderProduct.order_id == case.order,
            )
        )
        assert position is not None
        movements = await session.scalar(select(func.count()).select_from(InventoryMovement))
        return (
            sorted((str(b.storage_location_id), str(b.container_id), b.quantity) for b in balances),
            position.picked_quantity,
            int(movements or 0),
        )


async def _finish(case: Case) -> None:
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, case.supply)
        assert supply is not None
        orders = await shipment._load_supply_orders_read(session, case.tenant, case.supply)
        operation = await create_pending_deliver_operation(
            session,
            tenant_id=case.tenant,
            seller_id=supply.seller_id,
            idempotency_key="shipment",
            request_hash="synthetic",
            local_supply_id=case.supply,
            confirmed_preflight_version=None,
        )
        await session.commit()  # The real external handoff checkpoints release this lock too.
        await shipment._finish_ozon_delivery(
            session,
            supply=supply,
            orders=orders,
            operation=operation,
            result=OzonHandoffResult(123, False, None, "synthetic", None),
            actor_user_id=case.actor,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["in_delivery", "done", "cancelled"])
async def test_late_undo_cannot_return_other_sorting_stock_to_old_box(
    async_client: AsyncClient,
    case: Case,
    status: str,
) -> None:
    await _finish(case)
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, case.supply)
        order = await session.get(FbsOrder, case.order)
        assert supply is not None and supply.delivered_at is not None and order is not None
        supply.status = status
        if status == "cancelled":
            order.status = status  # Late cancellation must not reopen a shipped pick.
        await session.commit()
    before = await _snapshot(case)
    response = await async_client.post(
        f"/operations/fbs-supplies/{case.supply}/pick/{case.order}/undo",
        headers=case.headers,
        json={"idempotency_key": "late-undo"},
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "supply_already_submitted"
    assert await _snapshot(case) == before
    if status != "cancelled":
        for endpoint, payload in [
            (
                "manual",
                {
                    "location_id": str(case.sorting),
                    "product_id": str(case.product),
                    "order_id": str(case.order),
                    "idempotency_key": "late-pick",
                },
            ),
            (
                "set",
                {
                    "storage_location_id": str(case.source),
                    "product_id": str(case.product),
                    "quantity": 0,
                    "container_kind": "box",
                    "container_id": str(case.box),
                },
            ),
        ]:
            mutation = await async_client.post(
                f"/operations/fbs-supplies/{case.supply}/pick/{endpoint}",
                headers=case.headers,
                json=payload,
            )
            assert mutation.status_code == 409, mutation.text
            assert mutation.json()["detail"]["code"] == "supply_already_submitted"
        assert await _snapshot(case) == before
    async with SessionLocal() as session:
        pick = await session.scalar(
            select(FbsOrderProductPick).where(
                FbsOrderProductPick.fbs_supply_id == case.supply,
            )
        )
        assert pick is not None and pick.undone_at is None


@pytest.mark.asyncio
async def test_packed_ozon_undo_and_repick_still_work(
    async_client: AsyncClient, case: Case
) -> None:
    for _ in range(2):
        response = await async_client.post(
            f"/operations/fbs-supplies/{case.supply}/pick/{case.order}/undo",
            headers=case.headers,
            json={"idempotency_key": "before-shipment"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["orders"][0]["positions"][0]["picked_quantity"] == 0
    async with SessionLocal() as session:
        actor = await session.get(User, case.actor)
        assert actor is not None
        await picking.manual_pick_product(
            session,
            case.tenant,
            case.supply,
            location_id=case.source,
            product_id=case.product,
            order_id=case.order,
            idempotency_key="repick",
            actor=actor,
            container_kind="box",
            container_id=case.box,
        )
        await session.commit()
    await _finish(case)
    before = await _snapshot(case)
    replay = await async_client.post(
        f"/operations/fbs-supplies/{case.supply}/pick/{case.order}/undo",
        headers=case.headers,
        json={"idempotency_key": "before-shipment"},
    )
    assert replay.status_code == 200, replay.text
    assert await _snapshot(case) == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state, progress, blocked",
    [
        ("pending", {}, True),
        ("pending_confirmation", {}, True),
        ("confirmed", {}, True),
        ("failed", {"carriage_create_started": True}, True),
        ("failed", {"carriage_id": 123}, True),
        ("failed", {"carriage_approved": True}, True),
        ("failed", {"used_fallback": True}, True),
        ("failed", {}, False),
        ("failed", {"shipped_postings": ["ozon-1"]}, False),
    ],
)
async def test_delivery_checkpoint_protects_pick_mutations(
    async_client: AsyncClient,
    case: Case,
    state: str,
    progress: dict[str, object],
    blocked: bool,
) -> None:
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, case.supply)
        assert supply is not None
        operation = await create_pending_deliver_operation(
            session,
            tenant_id=case.tenant,
            seller_id=supply.seller_id,
            idempotency_key="checkpoint",
            request_hash="synthetic",
            local_supply_id=case.supply,
            confirmed_preflight_version=None,
        )
        operation.state = state
        operation.request_summary_json = {"ozon_handoff_progress": progress}
        await session.commit()
    before = await _snapshot(case)
    undo = await async_client.post(
        f"/operations/fbs-supplies/{case.supply}/pick/{case.order}/undo",
        headers=case.headers,
        json={"idempotency_key": "checkpoint-undo"},
    )
    assert undo.status_code == (409 if blocked else 200), undo.text
    if blocked:
        assert await _snapshot(case) == before
        pick = await async_client.post(
            f"/operations/fbs-supplies/{case.supply}/pick/manual",
            headers=case.headers,
            json={
                "location_id": str(case.sorting),
                "product_id": str(case.product),
                "order_id": str(case.order),
                "idempotency_key": "checkpoint-pick",
            },
        )
        assert pick.status_code == 409, pick.text
        assert pick.json()["detail"]["code"] == (
            "supply_already_submitted" if state == "confirmed" else "operation_in_progress"
        )
        assert await _snapshot(case) == before


async def _wait_for_supply_blocker(
    blocker_pid: int,
    task: asyncio.Task[None] | None = None,
) -> str:
    from sqlalchemy import text

    async with SessionLocal() as probe:
        for _ in range(100):
            if task is not None and task.done():
                task.result()
                pytest.fail("Finalization completed without taking the supply lock")
            blocked = await probe.scalar(
                text("SELECT query FROM pg_stat_activity WHERE :pid = ANY(pg_blocking_pids(pid))"),
                {"pid": blocker_pid},
            )
            if blocked:
                return str(blocked)
            await probe.commit()  # pg_stat_activity snapshots are transaction-scoped.
            await asyncio.sleep(0.02)
    pytest.fail("Concurrent mutation did not wait on the supply row lock")


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
async def test_late_undo_waits_and_rereads_committed_delivery(case: Case) -> None:
    from sqlalchemy import text

    async with SessionLocal() as holder, SessionLocal() as stale:
        if holder.bind is None or holder.bind.dialect.name != "postgresql":
            pytest.skip("requires PostgreSQL row locks")
        # Populate the identity map before another transaction completes delivery.
        cached = await picking._load_supply(stale, case.tenant, case.supply)
        assert cached.delivered_at is None
        actor = await stale.get(User, case.actor)
        assert actor is not None
        supply = await shipment._get_supply_for_update(holder, case.tenant, case.supply)
        assert supply is not None
        pid = await holder.scalar(text("select pg_backend_pid()"))
        assert pid is not None
        task = asyncio.create_task(
            picking.undo_pick(
                stale,
                case.tenant,
                case.supply,
                case.order,
                idempotency_key="racing-undo",
                actor=actor,
            )
        )
        try:
            await _wait_for_supply_blocker(pid)
            supply.delivered_at = datetime.now(UTC)
            supply.status = "in_delivery"
            await holder.commit()
            with pytest.raises(picking.FbsPickingError, match="supply_already_submitted"):
                await asyncio.wait_for(task, 5)
        finally:
            await holder.rollback()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
async def test_finalization_relocks_supply_after_external_checkpoint(case: Case) -> None:
    from sqlalchemy import text

    async with SessionLocal() as holder:
        if holder.bind is None or holder.bind.dialect.name != "postgresql":
            pytest.skip("requires PostgreSQL row locks")
        await shipment._get_supply_for_update(holder, case.tenant, case.supply)
        pid = await holder.scalar(text("select pg_backend_pid()"))
        assert pid is not None
        task = asyncio.create_task(_finish(case))
        try:
            query = await _wait_for_supply_blocker(pid, task)
            # An implicit UPDATE lock does not refresh state after the wait.
            assert query.lstrip().upper().startswith("SELECT"), query
            assert "FOR UPDATE" in query.upper() and "fbs_supplies" in query, query
            await holder.commit()
            await asyncio.wait_for(task, 10)
        finally:
            await holder.rollback()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, case.supply)
        assert supply is not None and supply.delivered_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("fallback_status", [400, 401, 403, 422, 429, 503, None])
@pytest.mark.parametrize("create_status", [404, 409])
async def test_known_fallback_rejection_reopens_pick_but_uncertain_outcome_does_not(
    async_client: AsyncClient,
    case: Case,
    fallback_status: int | None,
    create_status: int,
) -> None:
    from app.services.fbs_supply_reconcile_service import list_deliver_operations_for_supply
    from app.services.marketplace_provider import (
        FakeMarketplaceTransport,
        MarketplaceProviderError,
        OzonMarketplaceProvider,
    )
    from app.services.ozon_fbs_process_service import OzonHandoffProgress, handoff_supply

    fallback_error = MarketplaceProviderError("ozon", fallback_status, code="fallback_rejected")
    transport = FakeMarketplaceTransport(
        endpoint_responses={
            "/v3/posting/fbs/get": {
                "result": {"posting_number": "ozon-1", "status": "awaiting_deliver"},
            }
        },
        errors={
            "/v1/carriage/create": MarketplaceProviderError("ozon", create_status),
            "/v2/posting/fbs/awaiting-delivery": fallback_error,
        },
    )
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, case.supply)
        assert supply is not None
        orders = await shipment._load_supply_orders_read(session, case.tenant, case.supply)
        operation = await create_pending_deliver_operation(
            session,
            tenant_id=case.tenant,
            seller_id=supply.seller_id,
            idempotency_key="fallback",
            request_hash="synthetic",
            local_supply_id=case.supply,
            confirmed_preflight_version=None,
        )
        progress = OzonHandoffProgress(shipped_postings=["ozon-1"], posting_numbers=["ozon-1"])

        async def checkpoint(state: OzonHandoffProgress) -> None:
            await shipment._save_ozon_handoff_progress(session, operation, state)

        with pytest.raises(MarketplaceProviderError) as caught:
            await handoff_supply(
                session,
                supply=supply,
                orders=orders,
                provider=OzonMarketplaceProvider(transport=transport),
                client_id="synthetic",
                api_key="synthetic",
                progress=progress,
                checkpoint=checkpoint,
            )
        assert caught.value is fallback_error
        await shipment._fail_ozon_deliver_operation(
            session,
            operation,
            error_code=fallback_error.code,
            supply_id=case.supply,
        )
        attempts = await list_deliver_operations_for_supply(
            session,
            tenant_id=case.tenant,
            seller_id=supply.seller_id,
            local_supply_id=case.supply,
        )
        assert len(attempts) == 1 and attempts[0].state == "failed"
    before = await _snapshot(case)
    undo = await async_client.post(
        f"/operations/fbs-supplies/{case.supply}/pick/{case.order}/undo",
        headers=case.headers,
        json={"idempotency_key": "fallback-undo"},
    )
    known_refusal = fallback_status in {400, 401, 403, 422, 429}
    assert undo.status_code == (200 if known_refusal else 409), undo.text
    if known_refusal:
        assert undo.json()["orders"][0]["positions"][0]["picked_quantity"] == 0
    else:
        assert undo.json()["detail"]["code"] == "operation_in_progress"
        assert await _snapshot(case) == before
    assert sum(path == "/v1/carriage/create" for path, _ in transport.endpoint_calls) == 1
    assert (
        sum(path == "/v2/posting/fbs/awaiting-delivery" for path, _ in transport.endpoint_calls)
        == 1
    )
