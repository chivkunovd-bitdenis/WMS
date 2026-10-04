"""WMS-650 · постановка, перенос, снятие и повторы на сервере (контракт тестов).

Проверки C9, C19, C20, C23, C24, C25 документа docs/requirements/WMS-650.md
(и серверная часть C7). Все действия — через ручки экрана раскладки
(`…/sorting-objects/place`, `…/scan`), общий перенос — через раздел «Ячейки»
(`…/map/move`). Ручка «назад» — контракт из tests/wms650_sorting_seed.py.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.inbound_intake import InboundIntakeBox
from tests.wms650_sorting_seed import (
    SortingDoc,
    World,
    balance_id,
    cell_ids_holding,
    document_state,
    full_snapshot,
    holder_of,
    map_move,
    movement_ids,
    movements_except,
    normalized_view,
    ok,
    place,
    placement,
    posted,
    remaining_total,
    scan,
    seed_world,
    undo,
    unplaced_object_ids,
    view,
)


def _cell(world: World, code: str) -> str:
    return f"cell:{world.cells[code]}"


async def _object_qty_in_view(world: World, object_id: uuid.UUID) -> int:
    data = await view(world)
    return sum(
        int(row["qty"]) for row in data["lines"] if row["holder"] == f"obj:{object_id}"
    )


@pytest.mark.asyncio
async def test_c7_server_scan_placement_moves_box_out_of_remaining(
    async_client: AsyncClient,
) -> None:
    """C7 (серверная часть) · R8, R9: К1 поставлен сканом на А 1.2.

    В составе документа К1 стоит на А 1.2 и не числится в «осталось»;
    «осталось» уменьшилось, «разложено» выросло на количество К1; повторное
    чтение («обновление страницы») показывает то же.
    """
    world = await seed_world(async_client)
    k1 = world.a.boxes["К1"]
    remaining = await remaining_total(world)
    before_posted = await posted(world)
    ok(await place(world, kind="box", object_id=k1, cell="А 1.2"), "скан К1 на А 1.2")
    data = await view(world)
    assert str(k1) not in unplaced_object_ids(data)
    assert cell_ids_holding(data, k1) == [str(world.cells["А 1.2"])]
    assert await remaining_total(world) == remaining - 3
    assert (await posted(world))[world.t1] == before_posted[world.t1] + 3
    assert normalized_view(await view(world)) == normalized_view(data)


@pytest.mark.asyncio
async def test_c9_explicit_transfer_is_one_move_and_replay_changes_nothing(
    async_client: AsyncClient,
) -> None:
    """C9 · R10, R17: явный перенос К1 с А 1.2 на Б 1.1.

    К1 только под Б 1.1; «осталось», «размещено» и «разложено» не изменились;
    на сервере одно перемещение (одна группа движений), количество на ячейках
    не удвоилось. Повтор того же запроса (тот же operation_id) — успех без
    изменений: подтверждение повтором после потери ответа (R13).
    """
    world = await seed_world(async_client)
    k1 = world.a.boxes["К1"]
    ok(await place(world, kind="box", object_id=k1, cell="А 1.2"), "К1 на А 1.2")
    state_before = await document_state(world)
    remaining = await remaining_total(world)
    stock_before = await placement(world)
    on_cells_before = sum(
        qty for (loc, _k, _c, _p), qty in stock_before.items() if loc != str(world.sorting_id)
    )
    moves_before = await movement_ids(world)

    op = uuid.uuid4()
    ok(await place(world, kind="box", object_id=k1, cell="Б 1.1", op=op), "перенос К1 на Б 1.1")

    data = await view(world)
    assert cell_ids_holding(data, k1) == [str(world.cells["Б 1.1"])]
    assert holder_of(data, k1) == _cell(world, "Б 1.1")
    after = await document_state(world)
    assert after["posted"] == state_before["posted"], "перенос изменил «разложено» документа"
    assert after["box_posted"] == state_before["box_posted"]
    assert await remaining_total(world) == remaining
    new_moves = await movements_except(world, moves_before)
    groups = {row.transfer_group_id for row in new_moves}
    assert len(groups) == 1 and None not in groups, f"перенос записан не одной группой: {groups}"
    stock_after = await placement(world)
    on_cells_after = sum(
        qty for (loc, _k, _c, _p), qty in stock_after.items() if loc != str(world.sorting_id)
    )
    assert on_cells_after == on_cells_before, "количество на ячейках удвоилось"

    moves_after = await movement_ids(world)
    snapshot = await full_snapshot(world)
    replay = await place(world, kind="box", object_id=k1, cell="Б 1.1", op=op)
    assert replay.status_code == 200, f"повтор того же переноса: {replay.text}"
    assert await movement_ids(world) == moves_after
    assert await full_snapshot(world) == snapshot


async def _take_off_and_replace(
    world: World,
    *,
    kind: str,
    object_id: uuid.UUID,
    second_cell: str,
    expect_returned: dict[uuid.UUID, int],
) -> None:
    posted_on_cell = await posted(world)
    remaining_on_cell = await remaining_total(world)

    ok(await place(world, kind=kind, object_id=object_id), "«Снять с ячейки»")
    data = await view(world)
    assert str(object_id) in unplaced_object_ids(data), "снятое не вернулось в основной список"
    taken = await posted(world)
    for product_id, qty in expect_returned.items():
        assert taken[product_id] == posted_on_cell[product_id] - qty, (
            "«разложено» документа не уменьшилось на снятое"
        )
    assert await remaining_total(world) == remaining_on_cell + sum(expect_returned.values())

    ok(await place(world, kind=kind, object_id=object_id, cell=second_cell),
       "повторная постановка снятого")
    replaced = await posted(world)
    for product_id, qty in expect_returned.items():
        assert replaced[product_id] == taken[product_id] + qty, "двойной учёт «разложено»"
    assert await remaining_total(world) == remaining_on_cell
    assert cell_ids_holding(await view(world), object_id) == [str(world.cells[second_cell])]


async def _c19_box(world: World) -> None:
    k1 = world.a.boxes["К1"]
    ok(await place(world, kind="box", object_id=k1, cell="А 1.2"), "К1 на А 1.2")
    await _take_off_and_replace(
        world, kind="box", object_id=k1, second_cell="Б 1.1",
        expect_returned={world.t1: 3},
    )
    # «Со всем содержимым»: в основном списке после снятия был весь К1.
    assert await _object_qty_in_view(world, k1) == 3


async def _c19_box_contents_visible(world: World) -> None:
    k1 = world.a.boxes["К1"]
    ok(await place(world, kind="box", object_id=k1, cell="А 1.2"), "К1 на А 1.2")
    ok(await place(world, kind="box", object_id=k1), "Снять К1")
    data = await view(world)
    assert await _object_qty_in_view(world, k1) == 3, "снятый К1 показан не со всем содержимым"
    # Остальное «осталось» (К2, россыпь Т1) не потеряло своих штук.
    loose_t1 = sum(int(r["qty"]) for r in data["lines"]
                   if r["holder"] is None and r["productId"] == str(world.t1))
    k2_t1 = sum(int(r["qty"]) for r in data["lines"]
                if r["holder"] == f"obj:{world.a.boxes['К2']}")
    assert (loose_t1, k2_t1) == (2, 2), (
        f"снятие К1 «съело» соседнее: россыпь {loose_t1}, К2 {k2_t1}"
    )


async def _c19_cargo(world: World) -> None:
    g1 = world.a.cargo_places["Г1"]
    ok(await place(world, kind="cargo_place", object_id=g1, cell="А 1.1"), "Г1 на А 1.1")
    await _take_off_and_replace(
        world, kind="cargo_place", object_id=g1, second_cell="Б 1.1",
        expect_returned={world.t2: 2},
    )


async def _c19_pallet(world: World) -> None:
    p1 = world.a.pallets["П1"]
    # Подготовка: К2 и К3 собраны на П1 ещё при приёмке (как «Объединить в
    # палету»). Это предусловие, а не проверяемое действие, поэтому задано
    # данными; само размещение и снятие идут через ручку экрана.
    async with SessionLocal() as session:
        for name in ("К2", "К3"):
            box = await session.get(InboundIntakeBox, world.a.boxes[name])
            assert box is not None
            box.pallet_id = p1
        await session.commit()
    ok(await place(world, kind="pallet", object_id=p1, cell="А 1.2"), "П1 на А 1.2")
    await _take_off_and_replace(
        world, kind="pallet", object_id=p1, second_cell="Б 1.1",
        expect_returned={world.t1: 2, world.t2: 4},
    )


async def _c19_screen_box(world: World) -> None:
    created = await world.client.post(
        f"/warehouses/{world.warehouse_id}/sorting-objects",
        headers=world.headers,
        json={"kind": "box", "inbound_request_id": str(world.a.request_id)},
    )
    assert created.status_code == 201, created.text
    new_box = uuid.UUID(created.json()["id"])
    loose = await balance_id(world, product_id=world.t1, location_id=world.sorting_id,
                             container_id=None)
    ok(await place(world, kind="product", object_id=loose, to_id=new_box, qty=1),
       "Т1 из россыпи в «Новый короб»")
    ok(await place(world, kind="box", object_id=new_box, cell="А 1.1"), "новый короб на А 1.1")
    # Россыпь Т1 (1 шт) ещё не разложена — именно при ней прежде был двойной учёт.
    await _take_off_and_replace(
        world, kind="box", object_id=new_box, second_cell="Б 1.1",
        expect_returned={world.t1: 1},
    )


async def _c19_take_out_of_box(world: World) -> None:
    k2 = world.a.boxes["К2"]
    ok(await place(world, kind="box", object_id=k2, cell="А 1.1"), "К2 на А 1.1")
    before_posted = await posted(world)
    remaining = await remaining_total(world)
    inside = await balance_id(world, product_id=world.t1, location_id=world.cells["А 1.1"],
                              container_id=k2)
    ok(await place(world, kind="product", object_id=inside, qty=2), "Вынуть Т1 из К2")
    data = await view(world)
    loose_t1 = sum(int(r["qty"]) for r in data["lines"]
                   if r["holder"] is None and r["productId"] == str(world.t1))
    assert loose_t1 == 2 + 2, "вынутое не вернулось в «осталось» россыпью"
    assert (await posted(world))[world.t1] == before_posted[world.t1] - 2
    assert await remaining_total(world) == remaining + 2


C19_VARIANTS: dict[str, Callable[[World], Awaitable[None]]] = {
    "box": _c19_box,
    "box_contents": _c19_box_contents_visible,
    "cargo_place": _c19_cargo,
    "pallet_with_boxes": _c19_pallet,
    "screen_box": _c19_screen_box,
    "take_out": _c19_take_out_of_box,
}


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", list(C19_VARIANTS))
async def test_c19_taken_off_returns_to_remaining_and_replaces_without_double_count(
    async_client: AsyncClient, variant: str
) -> None:
    """C19 · R15: снятое с ячейки — в «осталось»; повторная постановка без отказа.

    Короб приёмки, грузоместо, палета с коробами, короб, созданный на экране,
    и «Вынуть из короба» у тары на ячейке. «Разложено» уменьшается на снятое и
    при повторной постановке растёт ровно на него же.
    """
    world = await seed_world(async_client)
    await C19_VARIANTS[variant](world)


async def _place_three(world: World, *, order: tuple[str, ...]) -> None:
    targets = {"К1": "А 1.1", "К2": "А 1.2", "К3": "Б 1.1"}
    for name in order:
        response = await place(world, kind="box", object_id=world.a.boxes[name],
                               cell=targets[name], op=uuid.uuid4())
        ok(response, f"{name} на {targets[name]}")
    data = await view(world)
    for name, cell in targets.items():
        box = world.a.boxes[name]
        assert str(box) not in unplaced_object_ids(data), f"{name} остался в «осталось»"
        assert cell_ids_holding(data, box) == [str(world.cells[cell])], f"{name} не под {cell}"
    assert normalized_view(await view(world)) == normalized_view(data)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "order", [("К1", "К2", "К3"), ("К3", "К2", "К1")], ids=["scan_order", "plus_order"]
)
async def test_c20_second_and_next_boxes_are_placed(
    async_client: AsyncClient, order: tuple[str, ...]
) -> None:
    """C20 · R16: подряд К1→А 1.1, К2→А 1.2 (тот же Т1), К3→Б 1.1 (другой товар).

    Каждый встаёт на свою ячейку и уходит из «осталось»; после повторного
    чтения — то же; отказов нет. Обе последовательности — сканом и через «+» —
    это одна и та же ручка экрана с собственным operation_id.
    """
    world = await seed_world(async_client)
    await _place_three(world, order=order)
    assert await remaining_total(world) == 23 - 9


@pytest.mark.asyncio
async def test_c23_repeated_requests_are_one_action_and_new_scans_are_new_units(
    async_client: AsyncClient,
) -> None:
    """C23 · R17: повтор того же запроса — одно действие; новые сканы — новые штуки.

    «Положить» Т3 (5 шт) и К3 дважды с одним operation_id, двойное «Снять с
    ячейки» с одним operation_id: одно перемещение, «разложено» один раз, повтор
    подтверждается успехом. Два отдельных скана Т1 кладут две штуки.
    """
    world = await seed_world(async_client)

    t3_source = await balance_id(world, product_id=world.t3, location_id=world.sorting_id,
                                 container_id=None)
    op = uuid.uuid4()
    ok(await place(world, kind="product", object_id=t3_source, cell="А 1.1", qty=5, op=op),
       "Т3 5 шт")
    moves = await movement_ids(world)
    ok(await place(world, kind="product", object_id=t3_source, cell="А 1.1", qty=5, op=op),
       "повтор Т3 5 шт")
    assert await movement_ids(world) == moves
    assert (await posted(world))[world.t3] == 5

    op = uuid.uuid4()
    ok(await place(world, kind="box", object_id=world.a.boxes["К3"], cell="Б 1.1", op=op), "К3")
    moves = await movement_ids(world)
    snapshot = await full_snapshot(world)
    replay = await place(world, kind="box", object_id=world.a.boxes["К3"], cell="Б 1.1", op=op)
    assert replay.status_code == 200, f"повтор постановки К3 после потери ответа: {replay.text}"
    assert await movement_ids(world) == moves
    assert await full_snapshot(world) == snapshot
    assert (await posted(world))[world.t2] == 4

    ok(await place(world, kind="box", object_id=world.a.boxes["К1"], cell="А 1.2"), "К1")
    op = uuid.uuid4()
    ok(await place(world, kind="box", object_id=world.a.boxes["К1"], op=op), "Снять К1")
    moves = await movement_ids(world)
    snapshot = await full_snapshot(world)
    replay = await place(world, kind="box", object_id=world.a.boxes["К1"], op=op)
    assert replay.status_code == 200, f"повтор «Снять с ячейки»: {replay.text}"
    assert await movement_ids(world) == moves
    assert await full_snapshot(world) == snapshot

    # Две отдельные штуки Т1 сканом в ячейку (К2 уже стоит, источник — россыпь).
    ok(await place(world, kind="box", object_id=world.a.boxes["К2"], cell="А 1.1"), "К2")
    ok(await place(world, kind="box", object_id=world.a.boxes["К1"], cell="А 1.2"), "К1 снова")
    t1_before = (await posted(world))[world.t1]
    ok(await scan(world, barcode=world.t1_barcode, cell="Б 1.1"), "скан Т1 №1")
    ok(await scan(world, barcode=world.t1_barcode, cell="Б 1.1"), "скан Т1 №2")
    assert (await posted(world))[world.t1] == t1_before + 2


async def _other_documents(world: World) -> dict[str, object]:
    return {
        "b": await document_state(world, world.b),
        "c": await document_state(world, world.c),
        "view_b": normalized_view(await view(world, world.b)),
        "view_c": normalized_view(await view(world, world.c)),
    }


@pytest.mark.asyncio
async def test_c24_actions_and_undo_in_a_do_not_touch_b_and_c(async_client: AsyncClient) -> None:
    """C24 · R18: действия и «назад» в A не меняют документы B и C.

    Список, «разложено» и расположение B (тот же селлер, тот же Т1) и C (другой
    селлер) не меняются; их тара в составе A не видна и ручкой A не двигается.
    """
    world = await seed_world(async_client)
    others = await _other_documents(world)
    data_a = await view(world)
    foreign = {str(world.b.boxes["КБ1"]), str(world.c.boxes["КЦ1"])}
    assert foreign.isdisjoint({row["id"] for row in data_a["objects"]})
    for doc, name in ((world.b, "КБ1"), (world.c, "КЦ1")):
        response = await place(world, kind="box", object_id=doc.boxes[name], cell="А 1.1")
        assert response.status_code >= 400, f"тару {name} сдвинули ручкой документа A"
    assert await _other_documents(world) == others

    ops = []
    for body in (
        dict(kind="box", object_id=world.a.boxes["К1"], cell="А 1.2"),
        dict(kind="box", object_id=world.a.boxes["К1"], cell="Б 1.1"),
        dict(kind="box", object_id=world.a.boxes["К1"]),
    ):
        op = uuid.uuid4()
        ok(await place(world, op=op, **body), f"действие в A {body}")  # type: ignore[arg-type]
        ops.append(op)
    ok(await scan(world, barcode=world.t3_barcode, cell="А 1.1"), "скан Т3 в A")
    assert await _other_documents(world) == others, "действия в A изменили B или C"

    for op in reversed(ops):
        ok(await undo(world, op), "«назад» в A")
    assert await _other_documents(world) == others, "«назад» в A изменил B или C"



async def _a_progress(world: World, doc: SortingDoc) -> dict[str, object]:
    state = await document_state(world, doc)
    return {"posted": state["posted"], "box_posted": state["box_posted"],
            "cargo_posted": state["cargo_posted"], "status": state["status"]}


@pytest.mark.asyncio
async def test_c25_general_moves_do_not_change_inbound_progress(async_client: AsyncClient) -> None:
    """C25 · R19, Д3: общие перемещения прогресс приёмки не меняют.

    После раскладки (как в C19/C12) перенос штуки Т1 с ячейки на сортировку
    (как подбор FBS) и перенос короба в разделе «Ячейки» не меняют «разложено»
    документов приёмки; раздел «Ячейки» показывает тару там, где её оставили.
    """
    world = await seed_world(async_client)
    ok(await place(world, kind="box", object_id=world.a.boxes["К1"], cell="А 1.2"), "К1")
    ok(await place(world, kind="box", object_id=world.a.boxes["К2"], cell="А 1.1"), "К2")
    loose = await balance_id(world, product_id=world.t1, location_id=world.sorting_id,
                             container_id=None)
    ok(await place(world, kind="product", object_id=loose, cell="Б 1.1", qty=2), "россыпь Т1")
    progress_a = await _a_progress(world, world.a)
    progress_b = await _a_progress(world, world.b)

    unit = await balance_id(world, product_id=world.t1, location_id=world.cells["Б 1.1"],
                            container_id=None)
    ok(await map_move(world, kind="product", object_id=unit, to_kind="sorting", qty=1),
       "штука Т1 с ячейки на сортировку (как подбор FBS)")
    ok(await map_move(world, kind="box", object_id=world.a.boxes["К2"], to_kind="sorting"),
       "К2 с ячейки на сортировку в разделе «Ячейки»")
    ok(await map_move(world, kind="box", object_id=world.a.boxes["К1"], to_kind="cell",
                      to_id=world.cells["Б 1.1"]), "К1 на Б 1.1 в разделе «Ячейки»")

    assert await _a_progress(world, world.a) == progress_a, "общий перенос изменил прогресс A"
    assert await _a_progress(world, world.b) == progress_b
    cells_map = await world.client.get(f"/warehouses/{world.warehouse_id}/map",
                                       headers=world.headers)
    assert cells_map.status_code == 200, cells_map.text
    b11 = next(cell for cell in cells_map.json()["cells"]
               if cell["id"] == str(world.cells["Б 1.1"]))
    assert str(world.a.boxes["К1"]) in {child["id"] for child in b11["children"]}
