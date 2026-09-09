"""WMS-080/WMS-392: real tape transactions share one order's code and packing facts."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from test_fbs_kiz import (
    _cis,
    _create_order,
    _create_supply,
    _patch_wb_acceptance,
    _register_ff_admin,
)

from app.db.session import SessionLocal, engine
from app.models.fbs_order import FbsOrder, FbsOrderMarking, FbsOrderReservation
from app.models.fbs_supply import FbsSupply
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.marking_code import MarkingCode
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.services import fbs_kiz_service as kiz
from app.services import fbs_order_tape_print_service as tape
from app.services import marking_code_service as mc
from app.services import packaging_task_service as packaging
from app.services.tokens import decode_access_token


@dataclass(frozen=True)
class Seed:
    headers: dict[str, str]
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    supply_id: uuid.UUID
    task_id: uuid.UUID
    line_id: uuid.UUID
    order_ids: list[uuid.UUID]


async def seed_tape(client: AsyncClient, monkeypatch: pytest.MonkeyPatch, code_count: int) -> Seed:
    headers, suffix = await _register_ff_admin(client)
    claims = decode_access_token(headers["Authorization"].removeprefix("Bearer "))
    tenant_id, user_id = uuid.UUID(claims["tenant_id"]), uuid.UUID(claims["sub"])
    seller = await client.post("/sellers", headers=headers, json={"name": "Tape race"})
    warehouse = await client.post(
        "/warehouses",
        headers=headers,
        json={
            "name": "Tape race",
            "code": "tape-race",
        },
    )
    seller_id, warehouse_id = uuid.UUID(seller.json()["id"]), uuid.UUID(warehouse.json()["id"])
    supply_id = await _create_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        suffix=suffix,
    )
    orders = [
        await _create_order(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            supply_id=supply_id,
            suffix=suffix,
            wb_order_id=800392 + i,
            sticker_code=None,
            wb_barcode=None,
            status="assembling",
        )
        for i in range(2)
    ]
    async with SessionLocal() as session:
        location = StorageLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            code="TAPE",
            barcode="TAPE",
        )
        task = PackagingTask(tenant_id=tenant_id, warehouse_id=warehouse_id, status="in_progress")
        session.add_all([location, task])
        await session.flush()
        line = PackagingTaskLine(
            task_id=task.id,
            product_id=orders[0].product_id,
            storage_location_id=location.id,
            qty_total=2,
            qty_suggested_packed=0,
            qty_confirmed_packed=0,
            qty_packed_in_task=0,
            qty_marking_printed=0,
            qty_marking_external=0,
        )
        session.add(line)
        supply = await session.get(FbsSupply, supply_id)
        assert supply
        supply.status, supply.packaging_task_id = "assembling", task.id
        product = await session.get(Product, orders[0].product_id)
        assert product
        product.requires_honest_sign = True
        for seeded in orders:
            order = await session.get(FbsOrder, seeded.order_id)
            assert order
            order.product_id, order.required_meta_json = product.id, ["sgtin"]
            session.add(
                FbsOrderReservation(
                    tenant_id=tenant_id,
                    fbs_order_id=order.id,
                    product_id=product.id,
                    warehouse_id=warehouse_id,
                    quantity=1,
                )
            )
        session.add(
            InventoryBalance(
                tenant_id=tenant_id,
                product_id=product.id,
                storage_location_id=location.id,
                quantity=3,
                quantity_unpacked=3,
                quantity_packed=0,
            )
        )
        session.add_all(
            [
                MarkingCode(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    product_id=product.id,
                    cis_code=_cis(f"TAPE{i:010d}"),
                    source="pool",
                    status="available",
                )
                for i in range(code_count)
            ]
        )
        await session.commit()
        seeded = Seed(
            headers,
            tenant_id,
            user_id,
            supply_id,
            task.id,
            line.id,
            [order.order_id for order in orders],
        )
    _patch_wb_acceptance(monkeypatch)
    monkeypatch.setattr(
        tape.marking_svc, "require_marketplace_token", AsyncMock(return_value="test")
    )
    monkeypatch.setattr(kiz, "delete_marketplace_order_meta", AsyncMock())
    return seeded


async def print_tape(session: AsyncSession, client: AsyncClient, seed: Seed, index: int = 0):
    return await tape.print_fbs_order_tape(
        session,
        seed.tenant_id,
        seed.supply_id,
        order_ids=[seed.order_ids[index]],
        layout={"units": [{"block": "cz", "copies": 1}]},
        allow_partial=False,
        include_order_qr=False,
        reprint=False,
        actor_user_id=seed.user_id,
        http_client=client,
    )


async def stock_snapshot():
    async with SessionLocal() as session:
        return (
            (
                await session.execute(
                    select(
                        InventoryBalance.id,
                        InventoryBalance.quantity,
                        InventoryBalance.quantity_unpacked,
                        InventoryBalance.quantity_packed,
                    ).order_by(InventoryBalance.id)
                )
            ).all(),
            (
                await session.execute(
                    select(FbsOrderReservation.id, FbsOrderReservation.quantity).order_by(
                        FbsOrderReservation.id
                    )
                )
            ).all(),
            await session.scalar(select(func.count()).select_from(InventoryMovement)),
        )


async def wait_for_row_lock(pid: int) -> None:
    """Wait for PostgreSQL's actual lock wait, not an arbitrary race timing."""

    async def wait():
        async with engine.connect() as connection:
            while True:
                waiting = await connection.scalar(
                    text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"),
                    {"pid": pid},
                )
                if waiting:
                    return
                await asyncio.sleep(0.01)

    await asyncio.wait_for(wait(), timeout=5)


@pytest.mark.asyncio
@pytest.mark.parametrize("code_count", [1, 2, 4])
async def test_postgres_order_tape_reuses_binding_after_wait(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    code_count: int,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    seed = await seed_tape(async_client, monkeypatch, code_count)
    before = await stock_snapshot()
    allocated, proceed = asyncio.Event(), asyncio.Event()
    original_assign = tape._assign_printed_code_to_order

    async def pause_assignment(session, order, code):
        await original_assign(session, order, code)
        allocated.set()
        await proceed.wait()

    monkeypatch.setattr(tape, "_assign_printed_code_to_order", pause_assignment)
    async with SessionLocal() as first, SessionLocal() as second:
        # Both identity maps contain the very same order with an empty collection.
        stmt = (
            select(FbsOrder)
            .where(FbsOrder.id == seed.order_ids[0])
            .options(
                selectinload(FbsOrder.markings).selectinload(FbsOrderMarking.marking_code),
            )
        )
        a, b = await first.scalar(stmt), await second.scalar(stmt)
        assert a and b and a.markings == b.markings == []
        pid = await second.scalar(text("select pg_backend_pid()"))
        printing = asyncio.create_task(print_tape(first, async_client, seed))
        await asyncio.wait_for(allocated.wait(), 5)
        pending = asyncio.create_task(print_tape(second, async_client, seed))
        try:
            await wait_for_row_lock(pid)
            proceed.set()
            printed, repeated = await asyncio.wait_for(asyncio.gather(printing, pending), 5)
            assert len(printed.orders) == 1 and not printed.order_errors
        finally:
            proceed.set()
            for running in (printing, pending):
                if not running.done():
                    running.cancel()
            await asyncio.gather(printing, pending, return_exceptions=True)
        assert repeated.shortage == 0 and not repeated.order_errors
        assert repeated.orders[0].codes == printed.orders[0].codes
        assert len(b.markings) == 1
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(FbsOrderMarking)) == 1
        line = await session.get(PackagingTaskLine, seed.line_id)
        assert line and line.qty_marking_printed == 1
        if code_count > 1:
            other = await print_tape(session, async_client, seed, 1)
            assert other.orders[0].codes != printed.orders[0].codes
            await session.commit()
            assert line.qty_marking_printed == 2
    assert await stock_snapshot() == before


@pytest.mark.asyncio
async def test_pack_all_then_first_order_tape_and_done_task_reprint(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = await seed_tape(async_client, monkeypatch, 3)
    before = await stock_snapshot()
    response = await async_client.post(
        f"/operations/packaging-tasks/{seed.task_id}/pack-all-and-complete",
        headers=seed.headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["packaging_task"]["status"] == "done"
    printed = await async_client.post(
        f"/operations/fbs-supplies/{seed.supply_id}/order-print-tape",
        headers=seed.headers,
        json={
            "order_ids": [str(seed.order_ids[0])],
            "include_order_qr": False,
            "reprint": False,
            "layout_json": {"units": [{"block": "cz", "copies": 1}]},
        },
    )
    assert printed.status_code == 200, printed.text
    assert printed.json()["ready"] == 1, printed.text
    code = printed.json()["orders"][0]["codes"][0]
    # The common service also permits reprint from a completed ordinary task.
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, seed.supply_id)
        assert supply
        supply.packaging_task_id = None
        await session.commit()
        repeated = await mc.print_codes_for_packaging_line(
            session,
            seed.tenant_id,
            seed.line_id,
            acting_user_id=seed.user_id,
            reprint=True,
        )
        assert repeated.codes == [code]
        task = await session.get(PackagingTask, seed.task_id)
        assert task and task.status == "done"
        task.status = "cancelled"
        await session.commit()
        with pytest.raises(mc.MarkingCodeServiceError, match="task_not_active"):
            await mc.print_codes_for_packaging_line(
                session,
                seed.tenant_id,
                seed.line_id,
                acting_user_id=seed.user_id,
                reprint=True,
            )
        await session.rollback()
        assert await session.scalar(select(func.count()).select_from(FbsOrderMarking)) == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MarkingCode)
                .where(
                    MarkingCode.status == "available",
                )
            )
            == 2
        )
    assert await stock_snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["pack_all", "scan", "unbind"])
async def test_postgres_tape_with_concurrent_packing_or_kiz(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    seed = await seed_tape(async_client, monkeypatch, 3)
    before = await stock_snapshot()
    attached, proceed = asyncio.Event(), asyncio.Event()
    original_attach = tape.marking_svc.attach_order_meta_to_wb_and_sync
    values: list[str] = []

    async def pause_before_wb(*args, **kwargs):
        values.append(args[3].value)
        attached.set()
        await proceed.wait()
        return await original_attach(*args, **kwargs)

    monkeypatch.setattr(tape.marking_svc, "attach_order_meta_to_wb_and_sync", pause_before_wb)
    async with SessionLocal() as first, SessionLocal() as second:
        printing = asyncio.create_task(print_tape(first, async_client, seed))
        await asyncio.wait_for(attached.wait(), 5)
        value = values[0]
        pid = await second.scalar(text("select pg_backend_pid()"))

        async def change():
            if operation == "pack_all":
                await packaging.pack_all_and_complete_fbs_task(
                    second,
                    seed.tenant_id,
                    seed.task_id,
                    acting_user_id=seed.user_id,
                )
            elif operation == "scan":
                await kiz._commit_one_kiz_pair(
                    second,
                    seed.tenant_id,
                    seed.user_id,
                    kiz.FbsKizCommitPair(order_id=seed.order_ids[0], value=value, confirmed=False),
                    async_client,
                    "race-scan",
                )
                await second.commit()
            else:
                await kiz.cancel_order_kiz(
                    second,
                    seed.tenant_id,
                    seed.user_id,
                    seed.order_ids[0],
                    async_client,
                )

        pending = asyncio.create_task(change())
        try:
            await wait_for_row_lock(pid)
            proceed.set()
            printed = await asyncio.wait_for(printing, 5)
            assert printed.orders and not printed.order_errors
            await first.commit()
            await asyncio.wait_for(pending, 5)
        finally:
            proceed.set()
            for running in (printing, pending):
                if not running.done():
                    running.cancel()
            await asyncio.gather(printing, pending, return_exceptions=True)
    async with SessionLocal() as session:
        line = await session.get(PackagingTaskLine, seed.line_id)
        code = await session.scalar(select(MarkingCode).where(MarkingCode.cis_code == value))
        assert line and code
        assert line.qty_marking_printed == (0 if operation == "unbind" else 1)
        assert line.qty_marking_external == 0
        assert (
            code.status
            == {"scan": "applied", "unbind": "applied", "pack_all": "printed"}[operation]
        )
        following = await print_tape(session, async_client, seed)
        assert following.orders and not following.order_errors
        assert (following.orders[0].codes == [value]) is (operation != "unbind")
        await session.commit()
        assert line.qty_marking_printed == 1
    assert await stock_snapshot() == before


@pytest.mark.asyncio
async def test_postgres_unbind_then_waiting_tape_refreshes_deleted_binding(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    seed = await seed_tape(async_client, monkeypatch, 2)
    before = await stock_snapshot()
    async with SessionLocal() as initial:
        original = await print_tape(initial, async_client, seed)
        await initial.commit()
    deleted, proceed = asyncio.Event(), asyncio.Event()
    original_void = kiz.void_existing_sgtin_marking

    async def pause_after_void(*args, **kwargs):
        await original_void(*args, **kwargs)
        deleted.set()
        await proceed.wait()

    monkeypatch.setattr(kiz, "void_existing_sgtin_marking", pause_after_void)
    async with SessionLocal() as first, SessionLocal() as second:
        stale_order = await second.scalar(
            select(FbsOrder)
            .where(
                FbsOrder.id == seed.order_ids[0],
            )
            .options(selectinload(FbsOrder.markings).selectinload(FbsOrderMarking.marking_code))
        )
        assert stale_order and len(stale_order.markings) == 1
        cancelling = asyncio.create_task(
            kiz.cancel_order_kiz(
                first,
                seed.tenant_id,
                seed.user_id,
                seed.order_ids[0],
                async_client,
            )
        )
        await asyncio.wait_for(deleted.wait(), 5)
        pid = await second.scalar(text("select pg_backend_pid()"))
        printing = asyncio.create_task(print_tape(second, async_client, seed))
        try:
            await wait_for_row_lock(pid)
            proceed.set()
            await asyncio.wait_for(cancelling, 5)
            repeated = await asyncio.wait_for(printing, 5)
            await second.commit()
        finally:
            proceed.set()
            for running in (cancelling, printing):
                if not running.done():
                    running.cancel()
            await asyncio.gather(cancelling, printing, return_exceptions=True)
        assert repeated.orders and not repeated.order_errors
        assert repeated.orders[0].codes != original.orders[0].codes
        assert len(stale_order.markings) == 1
    async with SessionLocal() as session:
        line = await session.get(PackagingTaskLine, seed.line_id)
        assert line and line.qty_marking_printed == 1 and line.qty_marking_external == 0
        assert await session.scalar(select(func.count()).select_from(FbsOrderMarking)) == 1
        statuses = dict(
            (
                await session.execute(
                    select(MarkingCode.status, func.count()).group_by(MarkingCode.status)
                )
            ).all()
        )
        assert statuses == {"applied": 1, "printed": 1}
    assert await stock_snapshot() == before
