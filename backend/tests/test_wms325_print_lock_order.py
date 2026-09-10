"""WMS-325: PostgreSQL row-lock order against the actual Ozon recovery writer."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from app.db.session import SessionLocal, engine
from app.models.document_event import DocumentEvent
from app.models.fbs_order import FbsOrder
from app.models.fbs_print_asset import FbsPrintAsset
from app.models.user import User
from app.services import document_event_service as audit
from app.services import fbs_print_asset_service as printing
from app.services import ozon_box_assembly_service as ozon
from app.services.marketplace_provider import OzonMarketplaceProvider
from tests.test_ozon_box_assembly import _seed, _transport

pytestmark = [
    pytest.mark.postgresql_concurrency,
    pytest.mark.skipif(
        engine.dialect.name != "postgresql", reason="Real PostgreSQL locks required"
    ),
]


async def _seed_print(session, *, no_order=False):
    order, supply, boxes = await _seed(session)
    order.sticker_status = "ready"
    actors = [
        User(
            tenant_id=order.tenant_id,
            email=f"print-{uuid.uuid4().hex}@example.com",
            password_hash="synthetic-unused",
            role="fulfillment_admin",
        )
        for _ in range(2)
    ]
    asset = FbsPrintAsset(
        tenant_id=order.tenant_id,
        seller_id=order.seller_id,
        fbs_supply_id=supply.id,
        fbs_order_id=None if no_order else order.id,
        kind="supply_qr" if no_order else "order_sticker",
        status="ready",
        storage_path="synthetic.pdf",
        content_type="application/pdf",
    )
    session.add_all([asset, *actors])
    await session.commit()
    return order, supply, boxes, asset, actors


async def _wait_until_blocked(holder_session, waiter_pid, holder_pid):
    # Query through the lock holder itself: exactly two database connections
    # participate. Synchronize on actual PostgreSQL wait state, not a timed guess.
    async with asyncio.timeout(5):
        while not await holder_session.scalar(
            text("SELECT :holder = ANY(pg_blocking_pids(:waiter))"),
            {"holder": holder_pid, "waiter": waiter_pid},
        ):
            await asyncio.sleep(0.01)


async def _open_and_finish(session, tenant_id, asset_id, actor_id):
    try:
        with audit.document_event_actor(actor_id):
            await printing.get_asset_binary_content(
                session, tenant_id, asset_id, user_id=uuid.uuid4()
            )
            await session.commit()
        return "opened"
    except printing.FbsPrintAssetError as exc:
        await session.rollback()
        return exc.code
    except Exception:
        await session.rollback()
        raise


async def test_open_content_vs_ozon_recovery_has_no_deadlock(db_session, monkeypatch):
    order, supply, boxes, asset, actors = await _seed_print(db_session)
    tenant_id, order_id, supply_id, box_id, asset_id = (
        order.tenant_id,
        order.id,
        supply.id,
        boxes[0].id,
        asset.id,
    )
    monkeypatch.setattr(printing, "read_print_file", lambda *args, **kwargs: b"synthetic-pdf")
    transport = _transport()
    transport.endpoint_responses["/v3/posting/fbs/get"] = {
        "result": {
            "posting_number": "POSTING",
            "status": "awaiting_deliver",
            "related_postings": {"related_posting_numbers": ["POSTING-1", "POSTING-2"]},
        },
    }
    provider = OzonMarketplaceProvider(transport=transport)
    ozon_holds_order = asyncio.Event()
    real_readback = ozon._posting_readback
    async with SessionLocal() as assembly_session, SessionLocal() as open_session:
        assembly_pid = await assembly_session.scalar(text("SELECT pg_backend_pid()"))
        open_pid = await open_session.scalar(text("SELECT pg_backend_pid()"))
        assert assembly_pid != open_pid
        for session in (assembly_session, open_session):
            await session.execute(text("SET LOCAL deadlock_timeout = '100ms'"))
            await session.execute(text("SET LOCAL statement_timeout = '8s'"))

        async def paused_readback(*args, **kwargs):
            # assemble_box_order has actually locked Order before provider IO.
            ozon_holds_order.set()
            await _wait_until_blocked(assembly_session, open_pid, assembly_pid)
            return await real_readback(*args, **kwargs)

        monkeypatch.setattr(ozon, "_posting_readback", paused_readback)

        async def recover():
            try:
                return await ozon.assemble_box_order(
                    assembly_session,
                    tenant_id,
                    supply_id,
                    box_id,
                    provider=provider,
                    credentials=("synthetic-client", "synthetic-key"),
                )
            except Exception:
                await assembly_session.rollback()
                raise

        recovery = asyncio.create_task(recover())
        opening = None
        try:
            await asyncio.wait_for(ozon_holds_order.wait(), timeout=5)
            opening = asyncio.create_task(
                _open_and_finish(open_session, tenant_id, asset_id, actors[0].id)
            )
            results = await asyncio.wait_for(
                asyncio.gather(recovery, opening, return_exceptions=True),
                timeout=10,
            )
        finally:
            for task in (recovery, opening):
                if task is not None and not task.done():
                    task.cancel()
            await asyncio.gather(
                *[t for t in (recovery, opening) if t is not None], return_exceptions=True
            )
        sqlstates = [
            getattr(r.orig, "sqlstate", None) for r in results if isinstance(r, DBAPIError)
        ]
        assert not sqlstates, f"PostgreSQL transaction errors: {sqlstates}"
        assert results == [order_id, "asset_not_ready"], results
    async with SessionLocal() as session:
        refreshed_order = await session.get(FbsOrder, order_id)
        refreshed_asset = await session.get(FbsPrintAsset, asset_id)
        assert refreshed_order.meta_details_json["ozon_assembly"]["recovered_from_readback"] is True
        assert refreshed_order.sticker_status == refreshed_asset.status == "requesting"
        assert refreshed_asset.print_opened_at is None
        assert not list(
            (
                await session.scalars(
                    select(DocumentEvent).where(
                        DocumentEvent.event_type == "print_opened",
                        DocumentEvent.document_id == order_id,
                    )
                )
            ).all()
        )


@pytest.mark.parametrize("no_order", [False, True])
@pytest.mark.parametrize("first_rollback", [False, True])
async def test_two_first_opens_record_once_with_rollback(
    db_session, monkeypatch, no_order, first_rollback
):
    order, supply, _, asset, actors = await _seed_print(db_session, no_order=no_order)
    tenant_id, asset_id = order.tenant_id, asset.id
    monkeypatch.setattr(printing, "read_print_file", lambda *args, **kwargs: b"synthetic-pdf")
    async with SessionLocal() as first, SessionLocal() as second:
        first_pid = await first.scalar(text("SELECT pg_backend_pid()"))
        second_pid = await second.scalar(text("SELECT pg_backend_pid()"))
        assert first_pid != second_pid
        # Retain stale ORM objects on the second connection deliberately.
        stale_asset = await second.get(FbsPrintAsset, asset_id)
        stale_order = await second.get(FbsOrder, order.id)
        assert stale_asset.print_opened_at is None and stale_order.sticker_status == "ready"
        with audit.document_event_actor(actors[0].id):
            await printing.get_asset_binary_content(
                first, tenant_id, asset_id, user_id=actors[1].id
            )
        opening = asyncio.create_task(_open_and_finish(second, tenant_id, asset_id, actors[1].id))
        try:
            await _wait_until_blocked(first, second_pid, first_pid)
            if first_rollback:
                await first.rollback()
            else:
                await first.commit()
            assert await asyncio.wait_for(opening, timeout=5) == "opened"
        finally:
            if not opening.done():
                opening.cancel()
            await asyncio.gather(opening, return_exceptions=True)
        assert stale_asset.print_opened_at is not None
        if not no_order:
            assert stale_order.sticker_status == "print_opened"
    async with SessionLocal() as session:
        rows = list(
            (
                await session.scalars(
                    select(DocumentEvent).where(
                        DocumentEvent.event_type == "print_opened",
                        DocumentEvent.document_id == (supply.id if no_order else order.id),
                    )
                )
            ).all()
        )
        assert len(rows) == 1
        expected_actor = actors[1] if first_rollback else actors[0]
        assert rows[0].actor_user_id == expected_actor.id
        assert rows[0].source == "user"
        assert rows[0].payload_json["actor_name_snapshot"] == expected_actor.email


@pytest.mark.parametrize(
    "initial_no_order,final_no_order", [(False, False), (True, False), (False, True)]
)
async def test_unlocked_identity_hint_is_revalidated(
    db_session, monkeypatch, initial_no_order, final_no_order
):
    order, supply, _, asset, actors = await _seed_print(db_session, no_order=initial_no_order)
    # A second same-tenant order provides a different lock target.
    other = FbsOrder(
        tenant_id=order.tenant_id,
        seller_id=order.seller_id,
        warehouse_id=order.warehouse_id,
        marketplace="ozon",
        wb_order_id=-999,
        external_order_id="OTHER",
        mapping_status="mapped",
        reserve_status="reserved",
        created_at_wb=order.created_at_wb,
        deadline_at=order.deadline_at,
        sticker_status="ready",
        status="cancelled",
    )
    db_session.add(other)
    await db_session.commit()
    monkeypatch.setattr(printing, "read_print_file", lambda *args, **kwargs: b"synthetic-pdf")
    async with SessionLocal() as opening, SessionLocal() as rebinding:
        original_execute = opening.execute
        rebound = False

        async def change_after_hint(statement, *args, **kwargs):
            nonlocal rebound
            result = await original_execute(statement, *args, **kwargs)
            if not rebound and str(statement).startswith("SELECT fbs_print_assets.fbs_order_id"):
                rebound = True
                await rebinding.execute(
                    update(FbsPrintAsset)
                    .where(FbsPrintAsset.id == asset.id)
                    .values(
                        fbs_order_id=None if final_no_order else other.id,
                    )
                )
                await rebinding.commit()
            return result

        monkeypatch.setattr(opening, "execute", change_after_hint)
        result = await _open_and_finish(opening, order.tenant_id, asset.id, actors[0].id)
        assert rebound
        # The replacement cancelled order must be checked; no stale order may
        # authorize opening or receive the print_opened mutation.
        assert result == ("opened" if final_no_order else "order_cancelled")
    async with SessionLocal() as session:
        original_order = await session.get(FbsOrder, order.id)
        assert original_order.sticker_status == "ready"
        rows = list(
            (
                await session.scalars(
                    select(DocumentEvent).where(
                        DocumentEvent.event_type == "print_opened",
                    )
                )
            ).all()
        )
        assert len(rows) == (1 if final_no_order else 0)
        if rows:
            assert rows[0].document_id == supply.id


async def test_content_does_not_read_cross_tenant_order(db_session, monkeypatch):
    order, _, _, asset, actors = await _seed_print(db_session)
    from app.models.tenant import Tenant

    foreign_tenant = Tenant(name="Foreign", slug=f"foreign-{uuid.uuid4().hex}")
    db_session.add(foreign_tenant)
    await db_session.flush()
    # Simulate a corrupt cross-tenant FK: the loader must not follow it.
    order.tenant_id = foreign_tenant.id
    await db_session.commit()
    monkeypatch.setattr(
        printing, "read_print_file", lambda *args, **kwargs: pytest.fail("file read")
    )
    async with SessionLocal() as session:
        assert (
            await _open_and_finish(session, asset.tenant_id, asset.id, actors[0].id)
            == "asset_not_found"
        )
        assert (
            await _open_and_finish(session, foreign_tenant.id, asset.id, actors[0].id)
            == "asset_not_found"
        )
