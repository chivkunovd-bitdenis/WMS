"""WMS-650 · исправления по независимому ревью (дополнение разработчика к контракту).

1. Изоляция россыпи (R18, C24): ручка документа A снимает с ячейки только
   штуки, которые туда положил сам A; чужую россыпь (документ B, другой
   селлер, общий остаток A+B сверх доли A) — 409 qty_exceeds_accepted.
2. Строки распределения (квитанции раскладки, Д2) после «Снять» и «назад»
   сходятся с «разложено»: сумма по товару = разложено, по коробу — не больше
   короба; чужие строки не освобождаются.
3. Тот же operation_id для другого объекта — operation_conflict, а не «повтор».
6. Палета A с коробом B на ней: «Снять» ручкой A не уменьшает «разложено» A
   на штуки B.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeBoxLine,
    InboundIntakeDistributionLine,
    InboundIntakeLine,
)
from app.models.pallet import Pallet
from tests.wms650_sorting_seed import (
    SortingDoc,
    World,
    balance_id,
    document_state,
    full_snapshot,
    holder_of,
    map_move,
    ok,
    place,
    posted,
    scan,
    seed_world,
    undo,
    view,
)


async def _distribution(
    world: World, doc: SortingDoc | None = None
) -> list[tuple[str, str, str, int]]:
    """Строки распределения документа: (товар, короб, место) → штук."""
    the_doc = doc or world.a
    async with SessionLocal() as session:
        rows = (
            await session.scalars(
                select(InboundIntakeDistributionLine).where(
                    InboundIntakeDistributionLine.request_id == the_doc.request_id
                )
            )
        ).all()
    total: dict[tuple[str, str, str], int] = defaultdict(int)
    for row in rows:
        total[(str(row.product_id), str(row.box_id), str(row.storage_location_id))] += row.quantity
    return sorted((*key, qty) for key, qty in total.items() if qty)


async def _assert_distribution_matches_progress(
    world: World, doc: SortingDoc | None = None
) -> None:
    the_doc = doc or world.a
    async with SessionLocal() as session:
        rows = (
            await session.scalars(
                select(InboundIntakeDistributionLine).where(
                    InboundIntakeDistributionLine.request_id == the_doc.request_id
                )
            )
        ).all()
        lines = (
            await session.scalars(
                select(InboundIntakeLine).where(InboundIntakeLine.request_id == the_doc.request_id)
            )
        ).all()
        box_lines = (
            await session.execute(
                select(InboundIntakeBoxLine.box_id, InboundIntakeBoxLine.product_id,
                       InboundIntakeBoxLine.quantity)
                .join(InboundIntakeBox, InboundIntakeBox.id == InboundIntakeBoxLine.box_id)
                .where(InboundIntakeBox.request_id == the_doc.request_id)
            )
        ).all()
    by_product: dict[uuid.UUID, int] = defaultdict(int)
    by_box: dict[tuple[uuid.UUID, uuid.UUID], int] = defaultdict(int)
    for row in rows:
        by_product[row.product_id] += row.quantity
        if row.box_id is not None:
            by_box[(row.box_id, row.product_id)] += row.quantity
    for line in lines:
        assert by_product.get(line.product_id, 0) == line.posted_qty, (
            "строки распределения разошлись с «разложено»",
            line.product_id, by_product.get(line.product_id, 0), line.posted_qty,
        )
    capacity = {(box_id, product_id): qty for box_id, product_id, qty in box_lines}
    for key, qty in by_box.items():
        assert qty <= capacity.get(key, 0), ("строки короба больше короба", key, qty)


# ── 1. Изоляция россыпи ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_cannot_take_off_loose_units_of_document_b(async_client: AsyncClient) -> None:
    world = await seed_world(async_client)
    loose_b = await balance_id(world, product_id=world.t1, location_id=world.sorting_id,
                               container_id=None)
    ok(await place(world, kind="product", object_id=loose_b, cell="Б 1.1", qty=3, doc=world.b),
       "B кладёт 3 шт Т1 россыпью на Б 1.1")
    state_b = await document_state(world, world.b)
    on_cell = await balance_id(world, product_id=world.t1, location_id=world.cells["Б 1.1"],
                               container_id=None)

    refused = await place(world, kind="product", object_id=on_cell, qty=3)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == "qty_exceeds_accepted"
    assert await document_state(world, world.b) == state_b


@pytest.mark.asyncio
async def test_a_cannot_take_off_loose_units_of_another_seller(async_client: AsyncClient) -> None:
    world = await seed_world(async_client)
    inside = await balance_id(world, product_id=world.t4, location_id=world.sorting_id,
                              container_id=world.c.boxes["КЦ1"])
    ok(await map_move(world, kind="product", object_id=inside, to_kind="cell",
                      to_id=world.cells["Б 1.1"], qty=1),
       "Т4 другого селлера россыпью на Б 1.1 через «Ячейки»")
    on_cell = await balance_id(world, product_id=world.t4, location_id=world.cells["Б 1.1"],
                               container_id=None)
    before = await full_snapshot(world)

    refused = await place(world, kind="product", object_id=on_cell, qty=1)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == "qty_exceeds_accepted"
    assert await full_snapshot(world) == before


@pytest.mark.asyncio
async def test_shared_loose_balance_a_takes_only_its_own_units(async_client: AsyncClient) -> None:
    world = await seed_world(async_client)
    loose = await balance_id(world, product_id=world.t1, location_id=world.sorting_id,
                             container_id=None)
    ok(await place(world, kind="product", object_id=loose, cell="Б 1.1", qty=2), "A: 2 шт Т1")
    ok(await place(world, kind="product", object_id=loose, cell="Б 1.1", qty=3, doc=world.b),
       "B: 3 шт Т1 туда же")
    on_cell = await balance_id(world, product_id=world.t1, location_id=world.cells["Б 1.1"],
                               container_id=None)
    state_b = await document_state(world, world.b)

    refused = await place(world, kind="product", object_id=on_cell, qty=5)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == "qty_exceeds_accepted"

    ok(await place(world, kind="product", object_id=on_cell, qty=2), "A снимает свои 2 шт")
    assert (await posted(world))[world.t1] == 0
    assert await document_state(world, world.b) == state_b


# ── 2. Строки распределения ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_take_off_after_transfer_releases_rows_of_that_box(async_client: AsyncClient) -> None:
    world = await seed_world(async_client)
    k1, k2 = world.a.boxes["К1"], world.a.boxes["К2"]
    ok(await place(world, kind="box", object_id=k1, cell="Б 1.1"), "К1 на Б 1.1")
    ok(await place(world, kind="box", object_id=k2, cell="А 1.2"), "К2 на А 1.2")
    ok(await place(world, kind="box", object_id=k2, cell="Б 1.1"), "К2 перенесён на Б 1.1")
    op = uuid.uuid4()
    ok(await place(world, kind="box", object_id=k2, op=op), "Снять К2")
    await _assert_distribution_matches_progress(world)
    rows = await _distribution(world)
    assert [row for row in rows if row[1] == str(k2)] == [], "строки К2 остались после снятия"
    assert [row[3] for row in rows if row[1] == str(k1)] == [3], "освободилась строка чужого короба"

    ok(await undo(world, op), "назад: К2 снова на Б 1.1")
    await _assert_distribution_matches_progress(world)
    ok(await place(world, kind="box", object_id=k2, op=op), "повтор снятия — без изменений")
    ok(await place(world, kind="box", object_id=k2, cell="А 1.1", op=uuid.uuid4()), "перенос")
    await _assert_distribution_matches_progress(world)


@pytest.mark.asyncio
async def test_take_off_then_place_again_keeps_box_rows_within_box(
    async_client: AsyncClient,
) -> None:
    world = await seed_world(async_client)
    k2 = world.a.boxes["К2"]
    ok(await place(world, kind="box", object_id=k2, cell="А 1.2"), "К2 на А 1.2")
    ok(await place(world, kind="box", object_id=k2, cell="Б 1.1"), "перенос на Б 1.1")
    ok(await place(world, kind="box", object_id=k2), "Снять К2")
    ok(await place(world, kind="box", object_id=k2, cell="А 1.1"), "К2 снова на А 1.1")
    await _assert_distribution_matches_progress(world)
    assert sum(row[3] for row in await _distribution(world) if row[1] == str(k2)) == 2


@pytest.mark.asyncio
async def test_undo_of_defect_scan_removes_its_distribution_row(async_client: AsyncClient) -> None:
    world = await seed_world(async_client)
    async with SessionLocal() as session:
        line = await session.scalar(select(InboundIntakeLine).where(
            InboundIntakeLine.request_id == world.a.request_id,
            InboundIntakeLine.product_id == world.t3,
        ))
        assert line is not None
        line.defective_qty = int(line.actual_qty or 0)
        await session.commit()
    before = await _distribution(world)
    op = uuid.uuid4()
    ok(await scan(world, barcode=world.t3_barcode, cell="А 1.1", op=op), "скан Т3: весь брак")
    assert (await posted(world))[world.t3] == 1
    ok(await undo(world, op), "назад")
    assert (await posted(world))[world.t3] == 0
    assert await _distribution(world) == before
    await _assert_distribution_matches_progress(world)


async def _p1_with_k2(world: World) -> None:
    async with SessionLocal() as session:
        box = await session.get(InboundIntakeBox, world.a.boxes["К2"])
        assert box is not None
        box.pallet_id = world.a.pallets["П1"]
        await session.commit()


@pytest.mark.asyncio
async def test_chain_of_actions_and_undos_keeps_distribution_rows(
    async_client: AsyncClient,
) -> None:
    world = await seed_world(async_client)
    await _p1_with_k2(world)
    k1, k3 = world.a.boxes["К1"], world.a.boxes["К3"]
    p1, g1 = world.a.pallets["П1"], world.a.cargo_places["Г1"]
    t3_loose = await balance_id(world, product_id=world.t3, location_id=world.sorting_id,
                                container_id=None)
    before = await full_snapshot(world)
    rows_before = await _distribution(world)

    steps: list[tuple[str, Any]] = [
        ("К1 на А 1.2", lambda op: place(world, kind="box", object_id=k1, cell="А 1.2", op=op)),
        ("П1 с К2 на А 1.1", lambda op: place(world, kind="pallet", object_id=p1, cell="А 1.1",
                                              op=op)),
        ("Т1 сканом в К1", lambda op: scan(world, barcode=world.t1_barcode, cell="А 1.2",
                                          to_id=k1, op=op)),
        ("К1 перенос на Б 1.1", lambda op: place(world, kind="box", object_id=k1, cell="Б 1.1",
                                                 op=op)),
        ("Т3 5 шт на А 1.2", lambda op: place(world, kind="product", object_id=t3_loose,
                                              cell="А 1.2", qty=5, op=op)),
        ("Г1 на Б 1.1", lambda op: place(world, kind="cargo_place", object_id=g1, cell="Б 1.1",
                                         op=op)),
        ("Снять П1", lambda op: place(world, kind="pallet", object_id=p1, op=op)),
        ("К3 на А 1.1", lambda op: place(world, kind="box", object_id=k3, cell="А 1.1", op=op)),
        ("Снять К1", lambda op: place(world, kind="box", object_id=k1, op=op)),
    ]
    ops: list[tuple[str, uuid.UUID]] = []
    for title, act in steps:
        op = uuid.uuid4()
        ok(await act(op), title)
        ops.append((title, op))
        await _assert_distribution_matches_progress(world)
    for title, op in reversed(ops):
        ok(await undo(world, op), f"назад: {title}")
        await _assert_distribution_matches_progress(world)
    assert await full_snapshot(world) == before
    assert await _distribution(world) == rows_before


# ── 3. Повтор — только тот же объект ───────────────────────────────────────


@pytest.mark.asyncio
async def test_same_operation_id_for_another_object_is_a_conflict(
    async_client: AsyncClient,
) -> None:
    world = await seed_world(async_client)
    op = uuid.uuid4()
    ok(await place(world, kind="box", object_id=world.a.boxes["К1"], cell="А 1.1", op=op), "К1")
    conflict = await place(world, kind="box", object_id=world.a.boxes["К2"], cell="А 1.1", op=op)
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["detail"] == "operation_conflict"
    assert holder_of(await view(world), world.a.boxes["К2"]) is None


# ── 6. Палета A с коробом B ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_take_off_pallet_of_a_does_not_count_units_of_b(async_client: AsyncClient) -> None:
    world = await seed_world(async_client)
    kb1, p1 = world.b.boxes["КБ1"], world.a.pallets["П1"]
    ok(await place(world, kind="box", object_id=kb1, cell="А 1.2", doc=world.b), "B: КБ1 на А 1.2")
    async with SessionLocal() as session:
        box = await session.get(InboundIntakeBox, kb1)
        pallet = await session.get(Pallet, p1)
        assert box is not None and pallet is not None
        box.pallet_id = p1
        pallet.storage_location_id = world.cells["А 1.2"]
        await session.commit()
    progress_a = await posted(world)
    state_b = await document_state(world, world.b)

    ok(await place(world, kind="pallet", object_id=p1), "A снимает П1 вместе с КБ1")
    assert await posted(world) == progress_a, "«Снять» засчитало A штуки документа B"
    after_b = await document_state(world, world.b)
    assert after_b["posted"] == state_b["posted"]
    assert after_b["box_posted"] == state_b["box_posted"]
