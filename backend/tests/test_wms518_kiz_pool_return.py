"""WMS-518: explicit WB cancellation releases the same transient pool code."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text
from test_fbs_kiz_operator_detach import payload, seed
from test_fbs_order_tape_concurrency import wait_for_row_lock

from app.db.session import SessionLocal, engine
from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.inventory_movement import InventoryMovement
from app.models.marking_code import MarkingCode, MarkingCodeEvent, MarkingPool
from app.models.packaging_task import PackagingTaskLine
from app.models.user import User
from app.services import fbs_kiz_service as kiz
from app.services import marking_code_service as mc
from app.services.wildberries_errors import WildberriesClientError


@pytest.mark.parametrize("status", ["reserved", "printed", "applied"])
@pytest.mark.parametrize("with_pool", [False, True])
async def test_cancel_returns_same_code_with_printed_history_and_replay(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, status: str, with_pool: bool,
) -> None:
    headers, orders, code_id, deleted, _ = await seed(
        async_client, monkeypatch, source="pool", status=status,
    )
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, code_id)
        if with_pool:
            pool = MarkingPool(
                tenant_id=code.tenant_id, seller_id=code.seller_id,
                gtin="04600000000000", title="Original pool",
            )
            session.add(pool)
            await session.flush()
            code.pool_id = pool.id
        identity = (code.tenant_id, code.seller_id, code.product_id, code.pool_id, code.cis_code)
        code.printed_at = code.applied_at = code.reserved_at = datetime.now(UTC)
        user_id = await session.scalar(select(User.id).limit(1))
        code.printed_by_user_id = code.reserved_by_user_id = user_id
        for event_type in ("imported", "printed", "returned_to_pool"):
            session.add(MarkingCodeEvent(
                tenant_id=code.tenant_id, seller_id=code.seller_id,
                code_id=code.id, pool_id=code.pool_id, event_type=event_type,
            ))
        await session.commit()

    url = f"/operations/fbs-orders/{orders[0].order_id}/kiz"
    response = await async_client.delete(url, headers=headers)
    assert response.status_code == 204, response.text
    # Replaying after a lost response cannot create another available unit or event.
    replay = await async_client.delete(url, headers=headers)
    assert replay.status_code == 404, replay.text
    deleted.assert_awaited_once()
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, code_id)
        assert code.status == "available" and code.packaging_task_line_id is None
        assert (
            code.tenant_id, code.seller_id, code.product_id, code.pool_id, code.cis_code,
        ) == identity
        assert code.source == "pool" and code.label_artifact_pdf == b"existing-label"
        assert code.reserved_at is code.reserved_by_user_id is None
        assert code.printed_at is code.printed_by_user_id is code.applied_at is None
        assert await session.scalar(select(func.count(MarkingCode.id))) == 1
        assert await session.scalar(select(func.count(FbsOrderMarking.id))) == 0
        assert await session.scalar(select(func.count(InventoryMovement.id))) == 0
        events = list((await session.scalars(
            select(MarkingCodeEvent).where(MarkingCodeEvent.code_id == code_id)
        )).all())
        assert sorted(event.event_type for event in events) == [
            "imported", "printed", "returned_to_pool", "voided",
        ]
        assert next(event for event in events if event.event_type == "voided").reason == (
            "отмена оператором"
        )
        line = await session.get(PackagingTaskLine, orders[0].packaging_task_line_id)
        assert line.qty_marking_printed == line.qty_marking_external == 0
    response = await async_client.post(
        "/operations/fbs-orders/kiz/commit", headers=headers,
        json=payload(orders[1], "reclaim-returned-pool-code"),
    )
    assert response.json()[0]["status"] == "ok", response.text
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, code_id)
        assert code.status == "applied"
        assert code.packaging_task_line_id == orders[1].packaging_task_line_id
        assert await session.scalar(select(func.count(MarkingCode.id))) == 1


@pytest.mark.parametrize("source,status", [
    ("external", "reserved"), ("external_fbs", "printed"),
    ("external_fbs", "applied"), ("pool", "introduced"),
    ("pool", "shipped"), ("pool", "transferred"), ("pool", "defective"),
    ("pool", "replaced"), ("pool", "void"), ("pool", "unknown_terminal"),
])
async def test_cancel_never_releases_external_or_terminal_code(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, source: str, status: str,
) -> None:
    headers, orders, code_id, _, _ = await seed(
        async_client, monkeypatch, source=source, status=status,
    )
    response = await async_client.delete(
        f"/operations/fbs-orders/{orders[0].order_id}/kiz", headers=headers,
    )
    assert response.status_code == 204, response.text
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, code_id)
        expected = "applied" if status in {"reserved", "printed"} else status
        assert code.status == expected and code.source == source
        assert await session.scalar(select(func.count(MarkingCode.id)).where(
            MarkingCode.status == "available",
        )) == 0


@pytest.mark.parametrize("failure", ["wb", "local"])
async def test_failed_cancel_is_atomic_and_can_be_retried(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    _, orders, code_id, deleted, _ = await seed(async_client, monkeypatch, source="pool")
    original_record = mc.record_event

    async def fail_after_flush(session, **kwargs):
        await original_record(session, **kwargs)
        await session.flush()
        raise RuntimeError("Injected failure after state and audit flush")

    if failure == "wb":
        deleted.side_effect = WildberriesClientError("transport_error")
    else:
        monkeypatch.setattr(mc, "record_event", fail_after_flush)
    async with SessionLocal() as session, AsyncClient() as http:
        tenant_id = (await session.get(MarkingCode, code_id)).tenant_id
        with pytest.raises(kiz.FbsKizError if failure == "wb" else RuntimeError):
            await kiz.cancel_order_kiz(session, tenant_id, None, orders[0].order_id, http)
        assert not session.in_transaction()
        code = await session.get(MarkingCode, code_id)
        assert code.status == "applied"
        assert code.packaging_task_line_id == orders[0].packaging_task_line_id
        assert await session.scalar(select(func.count(FbsOrderMarking.id))) == 1
        assert await session.scalar(select(func.count(MarkingCodeEvent.id))) == 0
        deleted.side_effect = None
        monkeypatch.setattr(mc, "record_event", original_record)
        await kiz.cancel_order_kiz(session, tenant_id, None, orders[0].order_id, http)
        code = await session.get(MarkingCode, code_id)
        assert code.status == "available" and code.packaging_task_line_id is None


@pytest.mark.parametrize("contender", ["cancel", "claim"])
async def test_postgres_cancel_serializes_replay_and_new_claim(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, contender: str,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    _, orders, code_id, deleted, _ = await seed(async_client, monkeypatch, source="pool")
    entered, release, second_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original_record = mc.record_event
    second_pid = None

    async def pause_under_code_lock(session, **kwargs):
        await original_record(session, **kwargs)
        entered.set()
        await release.wait()

    monkeypatch.setattr(mc, "record_event", pause_under_code_lock)
    async with SessionLocal() as session:
        tenant_id = (await session.get(MarkingCode, code_id)).tenant_id

    async def cancel():
        async with SessionLocal() as session, AsyncClient() as http:
            await kiz.cancel_order_kiz(session, tenant_id, None, orders[0].order_id, http)

    async def compete():
        nonlocal second_pid
        async with SessionLocal() as session, AsyncClient() as http:
            second_pid = await session.scalar(text("select pg_backend_pid()"))
            second_started.set()
            if contender == "cancel":
                with pytest.raises(kiz.FbsKizError, match="kiz_not_found"):
                    await kiz.cancel_order_kiz(session, tenant_id, None, orders[0].order_id, http)
            else:
                order = await session.get(FbsOrder, orders[1].order_id)
                code = await kiz.marking_svc._claim_pool_code_if_present(
                    session, tenant_id=tenant_id, order=order,
                    cis_raw=payload(orders[1], "unused")["pairs"][0]["value"],
                    printed_for_line_id=orders[1].packaging_task_line_id,
                )
                assert code.id == code_id and code.status == "reserved"
                code.packaging_task_line_id = orders[1].packaging_task_line_id
                session.add(FbsOrderMarking(
                    tenant_id=tenant_id, order_id=order.id, kind="sgtin", value=code.cis_code,
                    marking_code_id=code.id, source="pool", meta_status="accepted",
                ))
                await session.commit()

    first = asyncio.create_task(cancel())
    second = None
    try:
        await asyncio.wait_for(entered.wait(), 5)
        second = asyncio.create_task(compete())
        await asyncio.wait_for(second_started.wait(), 5)
        await wait_for_row_lock(second_pid)
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second), 5)
    finally:
        release.set()
        for task in (first, second):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(*(task for task in (first, second) if task), return_exceptions=True)
    deleted.assert_awaited_once()
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, code_id)
        assert code.status == ("available" if contender == "cancel" else "reserved")
        assert code.packaging_task_line_id == (
            None if contender == "cancel" else orders[1].packaging_task_line_id
        )
        assert await session.scalar(select(func.count(MarkingCode.id))) == 1
        assert await session.scalar(select(func.count(FbsOrderMarking.id))) == (
            0 if contender == "cancel" else 1
        )
        assert await session.scalar(select(func.count(MarkingCodeEvent.id))) == 1
