"""WMS-487: повторная и смешанная печать выдаёт недостающие обязательные коды."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from test_fbs_order_tape_concurrency import print_tape, seed_tape, stock_snapshot

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.fbs_supply import FbsSupply
from app.models.marking_code import EVENT_REPRINTED, MarkingCode, MarkingCodeEvent
from app.services import fbs_order_tape_print_service as tape
from app.services.print_template_service import parse_layout


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_count,reprint", [(0, True), (1, True), (2, True), (1, False)])
async def test_tape_allocates_only_missing_codes_and_preserves_existing_bindings(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    existing_count: int,
    reprint: bool,
) -> None:
    seed = await seed_tape(async_client, monkeypatch, 3)
    async with SessionLocal() as session:
        # Как у затронутой поставки: требование идёт от товара, у WB код необязателен.
        for order_id in seed.order_ids:
            order = await session.get(FbsOrder, order_id)
            assert order is not None
            order.required_meta_json = []
            order.optional_meta_json = ["sgtin"]
        await session.commit()
        existing_codes = {}
        for index in range(existing_count):
            initial = await print_tape(session, async_client, seed, index)
            assert initial.order_errors == []
            existing_codes[seed.order_ids[index]] = initial.orders[0].codes
            await session.commit()
        previous_bindings = dict((await session.execute(
            select(FbsOrderMarking.order_id, FbsOrderMarking.marking_code_id),
        )).all())
    before_stock = await stock_snapshot()

    async with SessionLocal() as session:
        result = await tape.print_fbs_order_tape(
            session, seed.tenant_id, seed.supply_id, order_ids=seed.order_ids,
            layout={"units": [{"block": "cz", "copies": 1}]},
            allow_partial=False, include_order_qr=False, reprint=reprint,
            actor_user_id=seed.user_id, http_client=async_client,
        )
        await session.commit()
    assert result.order_errors == []
    assert result.shortage == 0
    assert len(result.orders) == 2
    by_order = {row.order_id: row for row in result.orders}
    assert set(by_order) == set(seed.order_ids)
    for order_id, codes in existing_codes.items():
        assert by_order[order_id].codes == codes

    async with SessionLocal() as session:
        bindings = dict((await session.execute(
            select(FbsOrderMarking.order_id, FbsOrderMarking.marking_code_id),
        )).all())
        assert len(bindings) == 2
        assert len(set(bindings.values())) == 2
        assert all(bindings[order_id] == code_id for order_id, code_id in previous_bindings.items())
        for order_id, code_id in bindings.items():
            code = await session.get(MarkingCode, code_id)
            assert code is not None
            assert by_order[order_id].codes == [code.cis_code]
            assert by_order[order_id].printed_codes[0].id == code_id
        statuses = list(await session.scalars(select(MarkingCode.status)))
        assert sorted(statuses) == ["available", "printed", "printed"]
        events = list(await session.scalars(select(MarkingCodeEvent).where(
            MarkingCodeEvent.event_type == EVENT_REPRINTED,
        )))
        assert {event.code_id for event in events} == (
            set(previous_bindings.values()) if reprint else set()
        )
        assert len(events) == (existing_count if reprint else 0)
    assert await stock_snapshot() == before_stock


@pytest.mark.asyncio
async def test_reprint_without_code_or_requirement_still_has_nothing_to_reprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allocate = AsyncMock()
    monkeypatch.setattr(tape.mc_svc, "print_codes_for_packaging_line", allocate)
    order = SimpleNamespace(
        markings=[], required_meta_json=[], product=SimpleNamespace(requires_honest_sign=False),
    )
    with pytest.raises(tape.mc_svc.MarkingCodeServiceError, match="nothing_to_reprint"):
        await tape._print_or_reprint_order_code(
            AsyncMock(), uuid.uuid4(), order, SimpleNamespace(id=uuid.uuid4()),
            parse_layout({"units": [{"block": "cz", "copies": 1}]}),
            allow_partial=False, reprint=True, actor_user_id=uuid.uuid4(),
        )
    allocate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("reprint", [False, True])
async def test_skipped_tape_without_codes_does_not_allocate(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, reprint: bool,
) -> None:
    seed = await seed_tape(async_client, monkeypatch, 3)
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, seed.supply_id)
        assert supply is not None
        supply.honest_sign_skipped_at = datetime.now(UTC)
        await session.commit()
    allocate = AsyncMock(side_effect=AssertionError("Пропуск ЧЗ запрещает выдачу новых кодов"))
    monkeypatch.setattr(tape.mc_svc, "print_codes_for_packaging_line", allocate)
    async with SessionLocal() as session:
        result = await tape.print_fbs_order_tape(
            session, seed.tenant_id, seed.supply_id, order_ids=seed.order_ids,
            layout={"units": [{"block": "cz", "copies": 1}]},
            allow_partial=False, include_order_qr=False, reprint=reprint,
            actor_user_id=seed.user_id, http_client=async_client,
        )
        await session.commit()
        assert list(await session.scalars(select(MarkingCode.status))) == ["available"] * 3
        assert list(await session.scalars(select(FbsOrderMarking))) == []
    assert result.order_errors == []
    assert len(result.orders) == 2
    assert all(row.codes == [] and not row.requires_honest_sign for row in result.orders)
    allocate.assert_not_awaited()
