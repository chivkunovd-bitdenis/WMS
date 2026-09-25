"""WMS-529: retain one binding until WB echoes its exact KIZ."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from test_fbs_order_tape_concurrency import print_tape, seed_tape, stock_snapshot

from app.db.session import SessionLocal, engine
from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.marking_code import EVENT_APPLIED, MarkingCode, MarkingCodeEvent
from app.services import fbs_marking_service as marking_svc
from app.services.wildberries_errors import WildberriesClientError
from app.services.wildberries_fbs_client import MarketplaceMetaDetail, MarketplaceOrderMetaRow


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["tape", "scan"])
@pytest.mark.parametrize(
    "resolution",
    ["resend", "empty_kind", "delayed", "pending", "other_order", "read_error", "retry_lost"],
)
async def test_optional_without_value_keeps_binding_and_recovers_exact_value(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    entry: str,
    resolution: str,
) -> None:
    seed = await seed_tape(async_client, monkeypatch, 2)
    before = await stock_snapshot()
    async with SessionLocal() as session:
        value = await session.scalar(select(MarkingCode.cis_code).order_by(MarkingCode.cis_code))
        order = await session.get(FbsOrder, seed.order_ids[0])
        assert order is not None and value is not None
        wb_order_id = int(order.wb_order_id)
    calls: list[str] = []
    phase = "optional"
    sent_values: list[str] = []

    async def put(*args: Any, **kwargs: Any) -> None:
        nonlocal phase
        calls.append("put")
        assert kwargs["order_id"] == wb_order_id
        assert kwargs["api_token"] == "test"
        sent_values.append(kwargs["value"])
        if phase in {"resend", "empty_kind"}:
            phase = "filled"
        elif phase == "retry_lost":
            phase = "filled"
            raise WildberriesClientError("transport_error")

    async def get(*args: Any, **kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        calls.append("get")
        assert kwargs["order_ids"] == [wb_order_id]
        assert kwargs["api_token"] == "test"
        if phase == "read_error":
            raise WildberriesClientError("upstream_error", status_code=503)
        exact = phase in {"filled", "pending", "other_order"}
        return [MarketplaceOrderMetaRow(
            order_id=wb_order_id + (1 if phase == "other_order" else 0),
            meta={},
            meta_details=(MarketplaceMetaDetail(
                key="sgtin", value=sent_values[0] if exact else None,
                decision=("pending" if phase == "pending" else "filled") if exact else "optional",
            ),) if phase != "empty_kind" else (),
        )]

    monkeypatch.setattr(marking_svc, "put_marketplace_order_meta", put)
    monkeypatch.setattr(marking_svc, "fetch_marketplace_orders_meta_batch", get)

    async def attempt() -> str:
        if entry == "tape":
            async with SessionLocal() as session:
                result = await print_tape(session, async_client, seed)
            return result.order_errors[0].code if result.order_errors else "ok"
        response = await async_client.post(
            "/operations/fbs-orders/kiz/commit", headers=seed.headers,
            json={"idempotency_key": "same-attempt-key", "pairs": [{
                "order_id": str(seed.order_ids[0]), "value": value, "confirmed": False,
            }]},
        )
        assert response.status_code == 200, response.text
        return str(response.json()[0]["code"])

    assert await attempt() == "wb_pending_confirmation"
    assert calls == ["put", "get"]
    async with SessionLocal() as session:
        marking = (await session.scalars(select(FbsOrderMarking))).one()
        operation = (await session.scalars(select(FbsWbOperation))).one()
        assert marking.meta_status == "unknown"
        assert marking.meta_details_json["value"] is None
        assert operation.state == "pending_confirmation"
        marking_id, code_id, operation_id = marking.id, marking.marking_code_id, operation.id
        event_count = await session.scalar(select(func.count(MarkingCodeEvent.id)))
        persisted = await session.get(FbsOrder, seed.order_ids[0])
        assert persisted is not None and persisted.metadata_delivery_allowed is False

    calls.clear()
    phase = "filled" if resolution == "delayed" else resolution
    result = await attempt()
    if resolution in {"pending", "other_order", "read_error", "retry_lost"}:
        assert result == "wb_pending_confirmation"
        assert calls == (["get", "put"] if resolution == "retry_lost" else ["get"])
        if resolution == "pending":
            async with SessionLocal() as session:
                marking = await session.get(FbsOrderMarking, marking_id)
                assert marking is not None and marking.meta_status == "pending"
        calls.clear()
        phase = "filled"
        result = await attempt()
    assert result == "ok"
    assert calls == (
        ["get", "put", "get"] if resolution in {"resend", "empty_kind"} else ["get"]
    )
    assert len(set(sent_values)) == 1
    async with SessionLocal() as session:
        marking = (await session.scalars(select(FbsOrderMarking))).one()
        operation = (await session.scalars(select(FbsWbOperation))).one()
        assert (marking.id, marking.marking_code_id) == (marking_id, code_id)
        assert marking.meta_status == "accepted"
        assert operation.id == operation_id and operation.state == "confirmed"
        # Retrying the same scan does not apply/consume the pool code again.
        assert await session.scalar(select(func.count(MarkingCodeEvent.id))) == event_count
        assert await session.scalar(select(func.count(MarkingCode.id))) == 2
    assert await stock_snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("snapshot", ["empty", "absent_kind", "absent_row"])
async def test_initial_put_without_echo_keeps_pending_operation(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, snapshot: str,
) -> None:
    seed = await seed_tape(async_client, monkeypatch, 1)

    async def get(*args: Any, **kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        if snapshot == "absent_row":
            return []
        return [MarketplaceOrderMetaRow(
            order_id=kwargs["order_ids"][0], meta={},
            meta_details=(MarketplaceMetaDetail(key="sgtin", value="", decision="optional"),)
            if snapshot == "empty" else (),
        )]

    monkeypatch.setattr(marking_svc, "fetch_marketplace_orders_meta_batch", get)
    async with SessionLocal() as session:
        result = await print_tape(session, async_client, seed)
        assert result.order_errors[0].code == "wb_pending_confirmation"
        marking = (await session.scalars(select(FbsOrderMarking))).one()
        assert marking.meta_status == "unknown"
        assert await session.scalar(select(FbsWbOperation.state)) == "pending_confirmation"


@pytest.mark.asyncio
async def test_normal_exact_echo_keeps_single_put_and_get(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = await seed_tape(async_client, monkeypatch, 1)
    original_put = marking_svc.put_marketplace_order_meta
    original_get = marking_svc.fetch_marketplace_orders_meta_batch
    calls: list[str] = []

    async def put(*args: Any, **kwargs: Any) -> None:
        calls.append("put")
        await original_put(*args, **kwargs)

    async def get(*args: Any, **kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        calls.append("get")
        return await original_get(*args, **kwargs)

    monkeypatch.setattr(marking_svc, "put_marketplace_order_meta", put)
    monkeypatch.setattr(marking_svc, "fetch_marketplace_orders_meta_batch", get)
    async with SessionLocal() as session:
        result = await print_tape(session, async_client, seed)
        assert result.orders and not result.order_errors
        assert calls == ["put", "get"]
        assert await session.scalar(select(func.count(FbsWbOperation.id))) == 0


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
async def test_concurrent_same_scan_recovery_uses_one_binding_and_one_resend(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    seed = await seed_tape(async_client, monkeypatch, 2)
    async with SessionLocal() as session:
        value = await session.scalar(select(MarkingCode.cis_code).order_by(MarkingCode.cis_code))
        order = await session.get(FbsOrder, seed.order_ids[0])
        assert order is not None
        wb_order_id = int(order.wb_order_id)
    puts = 0
    entered, release = asyncio.Event(), asyncio.Event()

    async def put(*args: Any, **kwargs: Any) -> None:
        nonlocal puts
        puts += 1
        if puts == 2:
            entered.set()
            await release.wait()

    async def get(*args: Any, **kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        return [MarketplaceOrderMetaRow(order_id=wb_order_id, meta_details=(
            MarketplaceMetaDetail(
                key="sgtin", value=value if puts == 2 else None,
                decision="filled" if puts == 2 else "optional",
            ),
        ))]

    monkeypatch.setattr(marking_svc, "put_marketplace_order_meta", put)
    monkeypatch.setattr(marking_svc, "fetch_marketplace_orders_meta_batch", get)

    async def attempt():
        return await async_client.post(
            "/operations/fbs-orders/kiz/commit", headers=seed.headers,
            json={"idempotency_key": "concurrent-retry", "pairs": [{
                "order_id": str(seed.order_ids[0]), "value": value, "confirmed": False,
            }]},
        )

    assert (await attempt()).json()[0]["code"] == "wb_pending_confirmation"
    first = asyncio.create_task(attempt())
    second = None
    try:
        await asyncio.wait_for(entered.wait(), 5)
        second = asyncio.create_task(attempt())
        await asyncio.sleep(0.1)
        assert not second.done()
        release.set()
        responses = await asyncio.wait_for(asyncio.gather(first, second), 5)
        assert all(response.json()[0]["code"] == "ok" for response in responses)
    finally:
        release.set()
        await asyncio.gather(
            first, *([second] if second is not None else []), return_exceptions=True,
        )
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count(FbsOrderMarking.id))) == 1
        assert await session.scalar(select(FbsWbOperation.state)) == "confirmed"
        assert await session.scalar(select(func.count(MarkingCodeEvent.id)).where(
            MarkingCodeEvent.event_type == EVENT_APPLIED,
        )) == 1
    assert puts == 2
