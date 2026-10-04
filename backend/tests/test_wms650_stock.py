"""WMS-650 · C18: раскладка и «назад» не меняют остаток (контракт тестов).

R14 документа docs/requirements/WMS-650.md: ни одно действие раскладки и ни
одна отмена не меняют остаток по товару (сумма по всем местам, включая
сортировку и брак), резервы FBS/FBO, свободный и публикуемый остаток FBS,
лимиты оператора; новых движений прихода или списания нет — только
перемещения. Прогоны — C7, C9, C12 (а-ж), C15, C19, C20, C23.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from tests.wms650_sorting_seed import (
    ACTION_KINDS,
    World,
    assert_only_relocations,
    balance_id,
    map_move,
    movement_ids,
    movements_except,
    ok,
    place,
    put_k1_on_a12,
    seed_world,
    stock_snapshot,
    undo,
)

# Прогон: подготовка не входит в сравнение; действие возвращает operation_id,
# который затем отменяется «назад», и ожидаемый ответ на эту отмену.
Run = Callable[[World], Awaitable[tuple[uuid.UUID, int]]]


async def _c7(world: World) -> tuple[uuid.UUID, int]:
    op = uuid.uuid4()
    ok(await place(world, kind="box", object_id=world.a.boxes["К1"], cell="А 1.2", op=op), "C7")
    return op, 200


async def _c9(world: World) -> tuple[uuid.UUID, int]:
    op = uuid.uuid4()
    ok(await place(world, kind="box", object_id=world.a.boxes["К1"], cell="Б 1.1", op=op), "C9")
    return op, 200


async def _c15(world: World) -> tuple[uuid.UUID, int]:
    op = uuid.uuid4()
    ok(await place(world, kind="box", object_id=world.a.boxes["К2"], cell="А 1.1", op=op), "C15")
    ok(await map_move(world, kind="box", object_id=world.a.boxes["К2"], to_kind="cell",
                      to_id=world.cells["Б 1.1"], headers=world.other_headers), "C15 перенос")
    return op, 409


async def _c19(world: World) -> tuple[uuid.UUID, int]:
    ok(await place(world, kind="box", object_id=world.a.boxes["К1"]), "C19 снять")
    op = uuid.uuid4()
    ok(await place(world, kind="box", object_id=world.a.boxes["К1"], cell="Б 1.1", op=op),
       "C19 снова поставить")
    return op, 200


async def _c20(world: World) -> tuple[uuid.UUID, int]:
    op = uuid.uuid4()
    for name, cell in (("К1", "А 1.1"), ("К2", "А 1.2"), ("К3", "Б 1.1")):
        op = uuid.uuid4()
        ok(await place(world, kind="box", object_id=world.a.boxes[name], cell=cell, op=op),
           f"C20 {name}")
    return op, 200


async def _c23(world: World) -> tuple[uuid.UUID, int]:
    source = await balance_id(world, product_id=world.t3, location_id=world.sorting_id,
                              container_id=None)
    op = uuid.uuid4()
    for _ in range(2):
        ok(await place(world, kind="product", object_id=source, cell="А 1.1", qty=5, op=op),
           "C23 двойное «Положить»")
    return op, 200


async def _none(world: World) -> None:
    return None


def _from_kind(act: Callable[[World, uuid.UUID], Awaitable[object]]) -> Run:
    async def run(world: World) -> tuple[uuid.UUID, int]:
        op = uuid.uuid4()
        ok(await act(world, op), "C12")  # type: ignore[arg-type]
        return op, 200

    return run


RUNS: dict[str, tuple[Callable[[World], Awaitable[None]], Run]] = {
    "C7": (_none, _c7),
    "C9": (put_k1_on_a12, _c9),
    **{f"C12{kind.key}": (kind.setup, _from_kind(kind.act)) for kind in ACTION_KINDS},
    "C15": (_none, _c15),
    "C19": (put_k1_on_a12, _c19),
    "C20": (_none, _c20),
    "C23": (_none, _c23),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("run_key", list(RUNS))
async def test_c18_sorting_actions_and_undo_never_change_stock(
    async_client: AsyncClient, run_key: str
) -> None:
    """C18 · R14: остаток, резервы, свободный/публикуемый FBS и лимиты — как до.

    Сравнение после действия и после «назад»; новые движения — только
    перемещения внутри фулфилмента с нулевой суммой по каждому товару.
    """
    world = await seed_world(async_client)
    setup, run = RUNS[run_key]
    await setup(world)
    stock_before = await stock_snapshot(world)
    moves_before = await movement_ids(world)

    op, expected_undo = await run(world)
    assert await stock_snapshot(world) == stock_before, f"{run_key}: действие изменило остаток"
    assert_only_relocations(await movements_except(world, moves_before), f"{run_key}: действие")

    response = await undo(world, op)
    assert response.status_code == expected_undo, f"{run_key}: «назад» {response.text}"
    assert await stock_snapshot(world) == stock_before, f"{run_key}: «назад» изменил остаток"
    assert_only_relocations(await movements_except(world, moves_before), f"{run_key}: «назад»")
