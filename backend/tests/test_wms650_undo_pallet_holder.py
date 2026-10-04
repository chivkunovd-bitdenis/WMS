"""WMS-650 · R12: «назад» возвращает тару на ту же палету (дополнение разработчика).

Контракт тестов проверяет «назад» для тары, стоявшей прямо в месте. Здесь —
тара, которую действие сняло с палеты: квитанция «откуда» в журнале называет
палету, и отмена ставит короб обратно на неё, а не просто в то же место.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.inbound_intake import InboundIntakeBox
from tests.wms650_sorting_seed import (
    document_state,
    full_snapshot,
    holder_of,
    ok,
    place,
    posted,
    seed_world,
    undo,
    view,
)


async def _k2_on_p1(world) -> None:  # type: ignore[no-untyped-def]
    async with SessionLocal() as session:
        box = await session.get(InboundIntakeBox, world.a.boxes["К2"])
        assert box is not None
        box.pallet_id = world.a.pallets["П1"]
        await session.commit()


@pytest.mark.asyncio
async def test_take_box_off_pallet_in_sorting_and_undo(async_client: AsyncClient) -> None:
    world = await seed_world(async_client)
    await _k2_on_p1(world)
    before = await full_snapshot(world)

    op = uuid.uuid4()
    ok(await place(world, kind="box", object_id=world.a.boxes["К2"], op=op), "Вынуть К2 из П1")
    assert holder_of(await view(world), world.a.boxes["К2"]) is None

    ok(await undo(world, op), "назад")
    assert holder_of(await view(world), world.a.boxes["К2"]) == f"obj:{world.a.pallets['П1']}"
    assert await full_snapshot(world) == before


@pytest.mark.asyncio
async def test_transfer_box_off_placed_pallet_and_undo(async_client: AsyncClient) -> None:
    world = await seed_world(async_client)
    await _k2_on_p1(world)
    ok(await place(world, kind="pallet", object_id=world.a.pallets["П1"], cell="А 1.2"), "П1")
    before = await full_snapshot(world)
    progress = await posted(world)

    op = uuid.uuid4()
    ok(await place(world, kind="box", object_id=world.a.boxes["К2"], cell="Б 1.1", op=op),
       "К2 с палеты на Б 1.1 сканом")
    assert holder_of(await view(world), world.a.boxes["К2"]) == f"cell:{world.cells['Б 1.1']}"
    assert await posted(world) == progress

    ok(await undo(world, op), "назад")
    assert holder_of(await view(world), world.a.boxes["К2"]) == f"obj:{world.a.pallets['П1']}"
    after = await full_snapshot(world)
    # Служебное место короба на палете пишется так же, как при постановке на
    # палету; где короб на самом деле — показывает палета (её место и состав).
    for key in ("placement", "view_a", "view_b", "view_c", "b", "c"):
        assert after[key] == before[key], key
    for key in ("status", "posted", "box_posted", "cargo_posted", "pallets"):
        assert after["a"][key] == before["a"][key], key


@pytest.mark.asyncio
async def test_take_off_in_posted_document_moves_only(async_client: AsyncClient) -> None:
    """Д5: в оприходованном документе «Снять» — только расположение, прогресс не трогаем."""
    world = await seed_world(async_client)
    doc = world.c
    ok(await place(world, kind="box", object_id=doc.boxes["КЦ1"], cell="А 1.1", doc=doc), "КЦ1")
    state = await document_state(world, doc)
    assert state["status"] == "done"

    op = uuid.uuid4()
    ok(await place(world, kind="box", object_id=doc.boxes["КЦ1"], op=op, doc=doc), "Снять КЦ1")
    after = await document_state(world, doc)
    assert after["status"] == "done"
    assert after["posted"] == state["posted"]
    assert after["box_posted"] == state["box_posted"]

    ok(await undo(world, op, doc=doc), "назад после перестановки — только расположение")
    assert await document_state(world, doc) == state
