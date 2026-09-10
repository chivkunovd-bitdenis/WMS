"""WMS-153/156: real PG contention during count posting, isolated test DB only."""
from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, engine
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_count import InventoryCount, InventoryCountLine
from app.models.inventory_movement import InventoryMovement
from app.models.pallet import Pallet
from app.models.user import User
from app.models.warehouse_box import WarehouseBox
from app.services import inventory_count_service as counts
from app.services import inventory_service
from tests.test_inventory_counts import (
    TenantSetup,
    _balance,
    _create_all,
    _create_container,
    _product,
    _tenant,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(
    engine.dialect.name != "postgresql", reason="real PostgreSQL required",
)]


async def _seed(
    client: AsyncClient, kind: str = "box",
) -> tuple[TenantSetup, uuid.UUID, uuid.UUID, list[uuid.UUID]]:
    setup = await _tenant(client, "CountLockReplay")
    initial = await _create_all(client, setup)
    box_id = await _create_container(client, setup, initial["id"], kind,
                                     cell_id=setup.location_id)
    products = [await _product(client, setup, name=f"Replay product {i}") for i in range(2)]
    for product in products:
        await _balance(setup, product, 3, container_kind=kind, container_id=box_id)
    count_ids = []
    async with SessionLocal() as session:
        actor = await session.scalar(select(User.id).where(User.tenant_id == setup.tenant_id))
        assert actor is not None
        for product in products:
            count = await counts.create_count(
                session, setup.tenant_id, actor, source=counts.SOURCE_PLANNED,
                object_scope=None,
                filters=counts.CountFilters(product_ids=[product], warehouse_id=setup.warehouse_id),
                comment=None,
            )
            await counts.mark_place_empty(session, setup.tenant_id, count.id,
                                          kind=kind, place_id=box_id)
            count_ids.append(count.id)
    return setup, actor, box_id, count_ids


async def _assert_unchanged(
    setup: TenantSetup, box_id: uuid.UUID, ids: list[uuid.UUID], kind: str = "box",
) -> None:
    async with SessionLocal() as session:
        assert await session.get(Pallet if kind == "pallet" else WarehouseBox, box_id) is not None
        balances = (await session.scalars(select(InventoryBalance).where(
            InventoryBalance.container_id == box_id,
        ))).all()
        assert sorted((row.quantity, row.quantity_unpacked, row.quantity_packed)
                      for row in balances) == [(3, 3, 0), (3, 3, 0)]
        assert await session.scalar(select(func.count(InventoryMovement.id))) == 0
        assert set(await session.scalars(select(InventoryCount.status).where(
            InventoryCount.id.in_(ids),
        ))) == {"draft"}
        assert set(await session.scalars(select(InventoryCountLine.posted_delta).where(
            InventoryCountLine.count_id.in_(ids),
        ))) == {None}


@pytest.mark.parametrize("kind", ["box", "cargo_place", "pallet"])
async def test_two_filtered_counts_do_not_upgrade_shared_container_locks(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, kind: str,
) -> None:
    setup, actor, box_id, count_ids = await _seed(async_client, kind)
    reached_or_finished = asyncio.Event()
    products_locked = asyncio.Barrier(2)
    initial_locks: set[int] = set()
    movements: list[int] = []
    real_lock = inventory_service.lock_stock_product
    real_move = inventory_service.record_movement_and_adjust_balance

    async def lock(session: AsyncSession, *args, **kwargs):  # type: ignore[no-untyped-def]
        result = await real_lock(session, *args, **kwargs)
        if id(session) not in initial_locks:
            initial_locks.add(id(session))
            await asyncio.wait_for(products_locked.wait(), 5)
        return result

    async def move(session: AsyncSession, *args, **kwargs):  # type: ignore[no-untyped-def]
        result = await real_move(session, *args, **kwargs)
        movements.append(id(session))
        if len(movements) == 2:
            reached_or_finished.set()
        await asyncio.wait_for(reached_or_finished.wait(), 5)
        return result

    monkeypatch.setattr(inventory_service, "lock_stock_product", lock)
    monkeypatch.setattr(inventory_service, "record_movement_and_adjust_balance", move)

    async def post(count_id: uuid.UUID) -> Exception:
        async with SessionLocal() as session:
            try:
                await counts.post_count(session, setup.tenant_id, count_id, actor)
            except Exception as exc:
                await session.rollback()
                return exc
            finally:
                reached_or_finished.set()
        raise AssertionError("A filtered count must not delete another product's stock")

    outcomes = await asyncio.wait_for(asyncio.gather(*(post(cid) for cid in count_ids)), 15)
    codes = [exc.code if isinstance(exc, counts.InventoryCountError)
             else f"{type(exc).__name__}:{getattr(getattr(exc, 'orig', None), 'sqlstate', None)}"
             for exc in outcomes]
    assert sorted(codes) == ["balance_changed_during_post", "container_not_empty"], codes
    assert len(movements) == 1, "the contender must refuse before writing a movement"
    await _assert_unchanged(setup, box_id, count_ids, kind)


@pytest.mark.parametrize("held_resource", ["container", "balance"])
async def test_post_does_not_wait_on_reverse_container_or_balance_to_product_order(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, held_resource: str,
) -> None:
    from app.services.inventory_container_service import validate_container
    from tests.test_wms156_discrepancy_concurrency import _wait_blocked

    setup, actor, box_id, count_ids = await _seed(async_client)
    product_locked = asyncio.Event()
    real_lock = inventory_service.lock_stock_product
    async with SessionLocal() as poster, SessionLocal() as writer:
        line = await writer.scalar(select(InventoryCountLine).where(
            InventoryCountLine.count_id == count_ids[0],
        ))
        assert line is not None
        product_id = line.product_id
        if held_resource == "container":
            await validate_container(writer, setup.tenant_id, setup.warehouse_id, "box", box_id)
        else:
            await writer.scalar(select(InventoryBalance.id).where(
                InventoryBalance.product_id == product_id,
                InventoryBalance.container_id == box_id,
            ).with_for_update())
        writer_pid = await writer.scalar(text("select pg_backend_pid()"))

        async def incoming() -> None:
            await asyncio.wait_for(product_locked.wait(), 5)
            await inventory_service.record_movement_and_adjust_balance(
                writer, tenant_id=setup.tenant_id, product_id=product_id,
                storage_location_id=setup.location_id, quantity_delta=1,
                movement_type="inbound_intake", actor_user_id=actor,
                container_kind="box", container_id=box_id,
            )
            await writer.commit()

        task = asyncio.create_task(incoming())

        async def lock(session: AsyncSession, *args, **kwargs):  # type: ignore[no-untyped-def]
            product = await real_lock(session, *args, **kwargs)
            if session is poster:
                product_locked.set()
                await _wait_blocked(poster, writer_pid, task)
            return product

        monkeypatch.setattr(inventory_service, "lock_stock_product", lock)
        try:
            with pytest.raises(counts.InventoryCountError, match="balance_changed_during_post"):
                await asyncio.wait_for(counts.post_count(
                    poster, setup.tenant_id, count_ids[0], actor,
                ), 10)
            assert not poster.in_transaction(), "busy refusal must release Product and all claims"
            await asyncio.wait_for(task, 5)
            await poster.commit()  # Cannot accidentally persist a partial count after refusal.
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    async with SessionLocal() as session:
        assert sorted(await session.scalars(select(InventoryBalance.quantity).where(
            InventoryBalance.container_id == box_id,
        ))) == [3, 4]
        movements = (await session.scalars(select(InventoryMovement))).all()
        assert len(movements) == 1 and movements[0].quantity_delta == 1
        assert set(await session.scalars(select(InventoryCount.status).where(
            InventoryCount.id.in_(count_ids),
        ))) == {"draft"}
        assert set(await session.scalars(select(InventoryCountLine.posted_delta).where(
            InventoryCountLine.count_id.in_(count_ids),
        ))) == {None}


async def test_normal_nonempty_refusal_rolls_back_before_returning_to_service_caller(
    async_client: AsyncClient,
) -> None:
    setup, actor, box_id, count_ids = await _seed(async_client)
    async with SessionLocal() as session:
        with pytest.raises(counts.InventoryCountError, match="container_not_empty"):
            await counts.post_count(session, setup.tenant_id, count_ids[0], actor)
        assert not session.in_transaction()
        await session.commit()
    await _assert_unchanged(setup, box_id, count_ids)


@pytest.mark.parametrize("kind", ["box", "cargo_place", "pallet"])
async def test_full_count_posts_both_products_and_removes_confirmed_container(
    async_client: AsyncClient, kind: str,
) -> None:
    setup, actor, box_id, _ = await _seed(async_client, kind)
    async with SessionLocal() as session:
        count = await counts.create_count(
            session, setup.tenant_id, actor, source=counts.SOURCE_PLANNED,
            object_scope=None, filters=counts.CountFilters(warehouse_id=setup.warehouse_id),
            comment=None,
        )
        await counts.mark_place_empty(session, setup.tenant_id, count.id,
                                      kind=kind, place_id=box_id)
        result = await counts.post_count(session, setup.tenant_id, count.id, actor)
        assert result.count.status == "posted" and result.posted_lines == 2
    async with SessionLocal() as session:
        if kind == "pallet":
            pallet = await session.get(Pallet, box_id)
            assert pallet is not None and pallet.disbanded_at is not None
        else:
            assert await session.get(WarehouseBox, box_id) is None
        assert sorted(await session.scalars(select(InventoryMovement.quantity_delta))) == [-3, -3]
        assert sum(await session.scalars(select(InventoryBalance.quantity))) == 0
