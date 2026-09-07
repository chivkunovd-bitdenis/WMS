"""WMS-040: concurrent completion requires a disposable PostgreSQL database.

Set WMS_TEST_DATABASE_URL: SQLite cannot prove SELECT FOR UPDATE behaviour.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, engine
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.services import inbound_intake_service as svc
from app.services import inventory_service as inv_svc
from tests.test_inbound_intake_service_be01 import _auth_ids, _setup_request


@pytest.mark.asyncio
@pytest.mark.parametrize("rollback_first", [False, True], ids=["commit", "rollback"])
async def test_concurrent_completion_posts_once(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, rollback_first: bool
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks required")
    tenant_id, actor_id = await _auth_ids(async_client)
    request_id, product_id = await _setup_request(async_client, tenant_id, expected_qty=5)
    async with SessionLocal() as setup:
        req = await svc.begin_receiving(setup, tenant_id, request_id, actor_user_id=actor_id)
        await svc.set_line_actual_qty(setup, tenant_id, request_id, req.lines[0].id, actual_qty=5)

    receipt_written = asyncio.Event()
    release_first = asyncio.Event()
    original_receive = inv_svc.apply_inbound_receive

    async with SessionLocal() as first, SessionLocal() as second:
        # A client may already hold an old receiving object in its identity map.
        stale = await svc.get_request(second, tenant_id, request_id)
        assert stale is not None and stale.status == svc.STATUS_RECEIVING
        second_pid = await second.scalar(text("SELECT pg_backend_pid()"))

        async def paused_receive(session: AsyncSession, **kwargs: Any) -> None:
            await original_receive(session, **kwargs)
            if session is first:
                receipt_written.set()
                await release_first.wait()
                if rollback_first:
                    raise RuntimeError("simulate failure after receipt write")

        monkeypatch.setattr(inv_svc, "apply_inbound_receive", paused_receive)

        async def complete_first() -> str:
            try:
                await svc.complete_receiving(first, tenant_id, request_id, actor_user_id=actor_id)
                return "completed"
            except RuntimeError:
                await first.rollback()
                return "rolled_back"

        async def complete_second() -> str:
            try:
                # Legacy entry point must share the same protection.
                await svc.complete_verification(
                    second, tenant_id, request_id, actor_user_id=actor_id
                )
                return "completed"
            except svc.InboundIntakeError as exc:
                await second.rollback()
                return exc.code

        first_task = asyncio.create_task(complete_first())
        second_task = None
        try:
            await asyncio.wait_for(receipt_written.wait(), timeout=10)
            second_task = asyncio.create_task(complete_second())
            # Verify actual PostgreSQL waiting rather than assuming a delay means a lock.
            async with SessionLocal() as observer:
                async with asyncio.timeout(10):
                    while True:
                        waiting = await observer.scalar(
                            text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"),
                            {"pid": second_pid},
                        )
                        await observer.rollback()  # Refresh pg_stat_activity's snapshot.
                        if waiting == "Lock":
                            break
                        assert not second_task.done(), "Second completion bypassed the row lock"
                        await asyncio.sleep(0.01)
            release_first.set()
            assert await asyncio.wait_for(first_task, 10) == (
                "rolled_back" if rollback_first else "completed"
            )
            assert await asyncio.wait_for(second_task, 10) == (
                "completed" if rollback_first else "not_verifying"
            )
        finally:
            release_first.set()
            await asyncio.gather(
                first_task, *([second_task] if second_task else []), return_exceptions=True
            )

    async with SessionLocal() as check:
        final_req = await svc.get_request(check, tenant_id, request_id)
        assert final_req is not None and final_req.status == svc.STATUS_SORTING
        movements = list(
            (
                await check.scalars(
                    select(InventoryMovement).where(
                        InventoryMovement.inbound_intake_line_id == final_req.lines[0].id,
                    )
                )
            ).all()
        )
        assert len(movements) == 1
        assert movements[0].quantity_delta == 5
        assert (
            await check.scalar(
                select(func.sum(InventoryBalance.quantity)).where(
                    InventoryBalance.tenant_id == tenant_id,
                    InventoryBalance.product_id == product_id,
                )
            )
            == 5
        )
        with pytest.raises(svc.InboundIntakeError, match="request_not_found"):
            await svc.complete_receiving(check, uuid.uuid4(), request_id, actor_user_id=actor_id)
