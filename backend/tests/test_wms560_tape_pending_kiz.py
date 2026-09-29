"""WMS-560: the FBS tape keeps an order whose KIZ WB accepted but has not echoed yet.

27.09.2026 AVpack printed a tape of 13 orders and got only 4: for 9 orders WB
answered the KIZ write, but the readback right after it did not return the
value yet (WMS-529 ``wb_pending_confirmation``). The tape dropped those orders
with an error although their codes were already bound and a minute later WB
confirmed all nine. The code of such an order is printed now; the pending
operation keeps tracking the WB result. A lost WB answer (transport, 5xx) is a
different case: WB may not have the code, so that order still stays out of the
tape and the next print reconciles and resends it.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from test_fbs_order_tape_concurrency import Seed, print_tape, seed_tape

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.fbs_wb_operation import FbsWbOperation
from app.services import fbs_marking_service as marking_svc
from app.services import fbs_order_tape_print_service as tape
from app.services.wildberries_errors import WildberriesClientError
from app.services.wildberries_fbs_client import MarketplaceMetaDetail, MarketplaceOrderMetaRow


async def _print_all(session: Any, client: AsyncClient, seed: Seed) -> tape.FbsOrderTapePrintResult:
    return await tape.print_fbs_order_tape(
        session,
        seed.tenant_id,
        seed.supply_id,
        order_ids=list(seed.order_ids),
        layout={"units": [{"block": "cz", "copies": 1}]},
        allow_partial=False,
        include_order_qr=False,
        reprint=False,
        actor_user_id=seed.user_id,
        http_client=client,
    )


async def _wb_order_ids(seed: Seed) -> list[int]:
    async with SessionLocal() as session:
        ids = []
        for order_id in seed.order_ids:
            order = await session.get(FbsOrder, order_id)
            assert order is not None
            ids.append(int(order.wb_order_id))
        return ids


@pytest.mark.asyncio
@pytest.mark.parametrize("snapshot", ["empty_value", "absent_row"])
async def test_accepted_write_without_echo_stays_in_tape_and_confirms_later(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, snapshot: str,
) -> None:
    seed = await seed_tape(async_client, monkeypatch, 2)
    lagging_wb_id, prompt_wb_id = await _wb_order_ids(seed)
    sent: dict[int, str] = {}
    puts: list[int] = []
    echo_ready = False

    async def put(*args: Any, **kwargs: Any) -> None:
        puts.append(kwargs["order_id"])
        sent[kwargs["order_id"]] = kwargs["value"]

    async def get(*args: Any, **kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        wb_id = kwargs["order_ids"][0]
        lagging = wb_id == lagging_wb_id and not echo_ready
        if lagging and snapshot == "absent_row":
            return []
        value = None if lagging else sent[wb_id]
        return [MarketplaceOrderMetaRow(
            order_id=wb_id,
            meta={},
            meta_details=(MarketplaceMetaDetail(
                key="sgtin", value=value, decision="optional" if lagging else "filled",
            ),),
        )]

    monkeypatch.setattr(marking_svc, "put_marketplace_order_meta", put)
    monkeypatch.setattr(marking_svc, "fetch_marketplace_orders_meta_batch", get)

    async with SessionLocal() as session:
        result = await _print_all(session, async_client, seed)
        # Both labels are in the tape; the operator sees no false error.
        assert not result.order_errors
        assert {row.order_id for row in result.orders} == set(seed.order_ids)
        assert all(row.codes for row in result.orders)
        assert sorted(puts) == sorted([lagging_wb_id, prompt_wb_id])

    async with SessionLocal() as session:
        markings = {
            row.order_id: row for row in (await session.scalars(select(FbsOrderMarking))).all()
        }
        assert markings[seed.order_ids[0]].meta_status == "unknown"
        assert markings[seed.order_ids[1]].meta_status == "accepted"
        operation = (await session.scalars(select(FbsWbOperation))).one()
        assert operation.state == "pending_confirmation"
        lagging_order = await session.get(FbsOrder, seed.order_ids[0])
        assert lagging_order is not None and lagging_order.metadata_delivery_allowed is False

    # WB echoes the value a minute later; an ordinary read confirms it without
    # a second write.
    echo_ready = True
    async with SessionLocal() as session:
        await marking_svc.sync_order_marking_statuses(
            session, seed.tenant_id, seed.order_ids[0], async_client, actor_user_id=seed.user_id,
        )
        await session.commit()
    async with SessionLocal() as session:
        marking = await session.scalar(
            select(FbsOrderMarking).where(FbsOrderMarking.order_id == seed.order_ids[0])
        )
        assert marking is not None and marking.meta_status == "accepted"
        operation = (await session.scalars(select(FbsWbOperation))).one()
        assert operation.state == "confirmed" and operation.confirmed_at is not None
        assert await session.scalar(select(func.count()).select_from(FbsOrderMarking)) == 2
    assert len(puts) == 2


@pytest.mark.asyncio
async def test_lost_wb_answer_keeps_only_that_order_out_of_tape(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = await seed_tape(async_client, monkeypatch, 2)
    lost_wb_id, _prompt_wb_id = await _wb_order_ids(seed)
    sent: dict[int, str] = {}
    puts: list[int] = []

    async def put(*args: Any, **kwargs: Any) -> None:
        puts.append(kwargs["order_id"])
        sent[kwargs["order_id"]] = kwargs["value"]
        if kwargs["order_id"] == lost_wb_id and puts.count(lost_wb_id) == 1:
            raise WildberriesClientError("transport_error")

    async def get(*args: Any, **kwargs: Any) -> list[MarketplaceOrderMetaRow]:
        wb_id = kwargs["order_ids"][0]
        return [MarketplaceOrderMetaRow(
            order_id=wb_id,
            meta={},
            meta_details=(
                MarketplaceMetaDetail(key="sgtin", value=sent[wb_id], decision="filled"),
            ),
        )]

    monkeypatch.setattr(marking_svc, "put_marketplace_order_meta", put)
    monkeypatch.setattr(marking_svc, "fetch_marketplace_orders_meta_batch", get)

    async with SessionLocal() as session:
        result = await _print_all(session, async_client, seed)
        assert [row.order_id for row in result.orders] == [seed.order_ids[1]]
        assert [(err.order_id, err.code) for err in result.order_errors] == [
            (seed.order_ids[0], "wb_pending_confirmation"),
        ]
        operation = (await session.scalars(select(FbsWbOperation))).one()
        assert operation.state == "pending_confirmation"
        # The code stays bound to the order that lost the answer.
        assert await session.scalar(select(func.count()).select_from(FbsOrderMarking)) == 2

    async with SessionLocal() as session:
        recovered = await print_tape(session, async_client, seed)
        assert [row.order_id for row in recovered.orders] == [seed.order_ids[0]]
        assert not recovered.order_errors
        operation = (await session.scalars(select(FbsWbOperation))).one()
        assert operation.state == "confirmed"
    # WB already had the code: the recovery read confirmed it without resending.
    assert puts.count(lost_wb_id) == 1


@pytest.mark.asyncio
async def test_wb_rejection_still_keeps_order_out_of_tape(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = await seed_tape(async_client, monkeypatch, 2)
    rejected_wb_id, _ = await _wb_order_ids(seed)
    from test_fbs_kiz import _patch_wb_acceptance

    _patch_wb_acceptance(monkeypatch, reject_order_id=rejected_wb_id)
    async with SessionLocal() as session:
        result = await _print_all(session, async_client, seed)
        assert [row.order_id for row in result.orders] == [seed.order_ids[1]]
        assert [(err.order_id, err.code) for err in result.order_errors] == [
            (seed.order_ids[0], "meta_validation_fail"),
        ]
