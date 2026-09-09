"""WMS-084: operator detach preserves the physical WB label, not print availability."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text
from test_fbs_kiz import (
    _CLEAN_CIS,
    _create_order,
    _create_supply,
    _patch_wb_acceptance,
    _register_ff_admin,
    _setup_seller_warehouse,
)
from test_fbs_order_tape_concurrency import wait_for_row_lock

from app.db.session import SessionLocal, engine
from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.inventory_movement import InventoryMovement
from app.models.marking_code import MarkingCode, MarkingCodeEvent
from app.models.packaging_task import PackagingTaskLine
from app.services import fbs_kiz_service as kiz
from app.services import fbs_marking_service as marking
from app.services.wildberries_errors import WildberriesClientError


async def seed(client, monkeypatch, *, source="external_fbs", status="applied"):
    headers, suffix = await _register_ff_admin(client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(client, headers, suffix)
    orders = []
    for number in range(3):
        supply_id = await _create_supply(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            suffix=f"{suffix}-{number}",
        )
        orders.append(
            await _create_order(
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                supply_id=supply_id,
                suffix=suffix,
                wb_order_id=84000 + number,
                sticker_code=f"DETACH{number}",
                wb_barcode=f"DETACH{number}",
                with_packaging=True,
            )
        )
    async with SessionLocal() as session:
        for order in orders:
            row = await session.get(FbsOrder, order.order_id)
            line = await session.get(PackagingTaskLine, order.packaging_task_line_id)
            row.product_id = line.product_id = orders[0].product_id
        old_line = await session.get(PackagingTaskLine, orders[0].packaging_task_line_id)
        setattr(old_line, "qty_marking_printed" if source == "pool" else "qty_marking_external", 1)
        code = MarkingCode(
            tenant_id=tenant_id,
            seller_id=seller_id,
            product_id=orders[0].product_id,
            cis_code=_CLEAN_CIS,
            source=source,
            status=status,
            packaging_task_line_id=old_line.id,
            label_artifact_pdf=b"existing-label",
        )
        session.add(code)
        await session.flush()
        session.add(
            FbsOrderMarking(
                tenant_id=tenant_id,
                order_id=orders[0].order_id,
                kind="sgtin",
                value=_CLEAN_CIS,
                marking_code_id=code.id,
                source="pool" if source == "pool" else "operator",
                meta_status="accepted",
                check_status="ok",
            )
        )
        await session.commit()
        code_id = code.id
    deleted = AsyncMock()
    monkeypatch.setattr(kiz, "delete_marketplace_order_meta", deleted)
    sent = _patch_wb_acceptance(monkeypatch)
    return headers, orders, code_id, deleted, sent


def payload(order, key):
    return {
        "idempotency_key": key,
        "pairs": [
            {"order_id": str(order.order_id), "value": _CLEAN_CIS, "confirmed": False},
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("source,status", [("external_fbs", "applied"), ("pool", "introduced")])
async def test_cancel_rescan_and_replay_preserve_code_and_move_line_counts(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    status: str,
) -> None:
    headers, orders, code_id, deleted, sent = await seed(
        async_client,
        monkeypatch,
        source=source,
        status=status,
    )
    response = await async_client.delete(
        f"/operations/fbs-orders/{orders[0].order_id}/kiz", headers=headers
    )
    assert response.status_code == 204, response.text
    deleted.assert_awaited_once()
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, code_id)
        assert code.status == status and code.packaging_task_line_id is None
        assert await session.scalar(select(func.count(FbsOrderMarking.id))) == 0
        old_line = await session.get(PackagingTaskLine, orders[0].packaging_task_line_id)
        assert old_line.qty_marking_printed == old_line.qty_marking_external == 0
        # Physical applied/introduced labels cannot enter an available-code print query.
        assert (
            await session.scalar(
                select(func.count(MarkingCode.id)).where(MarkingCode.status == "available")
            )
            == 0
        )
    validation = await async_client.post(
        "/operations/fbs-orders/kiz/validate",
        headers=headers,
        json=payload(orders[1], "new")["pairs"][0],
    )
    assert validation.status_code == 200, validation.text
    for _ in range(2):
        response = await async_client.post(
            "/operations/fbs-orders/kiz/commit",
            headers=headers,
            json=payload(orders[1], "same-scan"),
        )
        assert response.json()[0]["status"] == "ok", response.text
    duplicate = await async_client.post(
        "/operations/fbs-orders/kiz/commit",
        headers=headers,
        json=payload(orders[2], "another-order"),
    )
    assert duplicate.json()[0]["code"] == "duplicate_kiz", duplicate.text
    assert sent == {orders[1].wb_order_id: _CLEAN_CIS}
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, code_id)
        assert code.status == status and code.source == source and code.cis_code == _CLEAN_CIS
        assert code.label_artifact_pdf == b"existing-label"
        assert code.packaging_task_line_id == orders[1].packaging_task_line_id
        line = await session.get(PackagingTaskLine, orders[1].packaging_task_line_id)
        assert (line.qty_marking_printed, line.qty_marking_external) == (
            (1, 0) if source == "pool" else (0, 1)
        )
        assert line.qty_packed_in_task == 1
        assert await session.scalar(select(func.count(FbsOrderMarking.id))) == 1
        assert await session.scalar(select(func.count(InventoryMovement.id))) == 0
        assert (
            await session.scalar(
                select(func.count(MarkingCodeEvent.id)).where(
                    MarkingCodeEvent.code_id == code_id,
                    MarkingCodeEvent.reason == "отмена оператором",
                )
            )
            == 1
        )


@pytest.mark.asyncio
async def test_remote_failure_and_final_order_do_not_release_code(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, orders, code_id, deleted, _ = await seed(async_client, monkeypatch)
    deleted.side_effect = WildberriesClientError("transport_error")
    response = await async_client.delete(
        f"/operations/fbs-orders/{orders[0].order_id}/kiz", headers=headers
    )
    assert response.status_code >= 400
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, code_id)
        assert (
            code.status == "applied"
            and code.packaging_task_line_id == orders[0].packaging_task_line_id
        )
        assert await session.scalar(select(func.count(FbsOrderMarking.id))) == 1
        assert await session.scalar(select(func.count(MarkingCodeEvent.id))) == 0
        order = await session.get(FbsOrder, orders[0].order_id)
        order.status = "in_delivery"
        code.status = "shipped"
        await session.commit()
    deleted.reset_mock()
    response = await async_client.delete(
        f"/operations/fbs-orders/{orders[0].order_id}/kiz", headers=headers
    )
    assert response.status_code == 409, response.text
    deleted.assert_not_awaited()
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, code_id)
        assert (
            code.status == "shipped"
            and code.packaging_task_line_id == orders[0].packaging_task_line_id
        )
        assert await session.scalar(select(func.count(FbsOrderMarking.id))) == 1


@pytest.mark.asyncio
async def test_postgres_two_orders_claim_detached_code_only_once(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    headers, orders, code_id, _, _ = await seed(async_client, monkeypatch)
    response = await async_client.delete(
        f"/operations/fbs-orders/{orders[0].order_id}/kiz", headers=headers
    )
    assert response.status_code == 204
    entered, release, second_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    second_pid = None
    original_put, original_claim = (
        marking.put_marketplace_order_meta,
        marking._claim_pool_code_if_present,
    )

    async def paused_put(*args, **kwargs):
        if kwargs["order_id"] == orders[1].wb_order_id:
            entered.set()
            await release.wait()
        await original_put(*args, **kwargs)

    async def observed_claim(session, **kwargs):
        nonlocal second_pid
        if kwargs["order"].id == orders[2].order_id:
            second_pid = await session.scalar(text("select pg_backend_pid()"))
            second_started.set()
        return await original_claim(session, **kwargs)

    monkeypatch.setattr(marking, "put_marketplace_order_meta", paused_put)
    monkeypatch.setattr(marking, "_claim_pool_code_if_present", observed_claim)
    first = asyncio.create_task(
        async_client.post(
            "/operations/fbs-orders/kiz/commit",
            headers=headers,
            json=payload(orders[1], "race-one"),
        )
    )
    second = None
    try:
        await asyncio.wait_for(entered.wait(), 5)
        second = asyncio.create_task(
            async_client.post(
                "/operations/fbs-orders/kiz/commit",
                headers=headers,
                json=payload(orders[2], "race-two"),
            )
        )
        await asyncio.wait_for(second_started.wait(), 5)
        await wait_for_row_lock(second_pid)
        release.set()
        results = await asyncio.wait_for(asyncio.gather(first, second), 5)
        assert [result.json()[0]["status"] for result in results] == ["ok", "error"]
        assert results[1].json()[0]["code"] == "duplicate_kiz"
    finally:
        release.set()
        for task in (first, second):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(*(task for task in (first, second) if task), return_exceptions=True)
    async with SessionLocal() as session:
        assert (
            await session.scalar(
                select(func.count(FbsOrderMarking.id)).where(
                    FbsOrderMarking.marking_code_id == code_id
                )
            )
            == 1
        )
