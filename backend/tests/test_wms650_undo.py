"""WMS-650 · «назад» на сервере: отмена последнего действия раскладки (контракт тестов).

Проверки C12, C15, C16, C28 документа docs/requirements/WMS-650.md (и серверная
часть C13, C17). Ручка отмены ещё не существует — контракт описан в
tests/wms650_sorting_seed.py: POST /warehouses/{id}/sorting-objects/undo с
inbound_request_id, собственным operation_id и target_operation_id.

Коды отказа (новые, фиксируются этим контрактом, экран переводит их в текст):
- undo_target_moved — то, что действие переместило, уже переместили ещё раз (C15, Д4);
- undo_document_posted — действие оприходовало документ, отмена не переоткрывает его (C28, Д5).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.wms650_sorting_seed import (
    ACTION_KINDS,
    ActionKind,
    billing_snapshot,
    document_state,
    full_snapshot,
    holder_of,
    map_move,
    movement_ids,
    ok,
    place,
    put_k1_on_a12,
    remaining_total,
    request_status,
    scan,
    seed_world,
    undo,
    view,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ACTION_KINDS, ids=[one.key for one in ACTION_KINDS])
async def test_c12_undo_restores_state_before_each_action_kind(
    async_client: AsyncClient, kind: ActionKind
) -> None:
    """C12 · R12, Д2: «назад» после каждого вида действия возвращает снимок «до».

    Расположение каждой штуки и тары, «осталось»/«разложено» документа и состав
    экрана после отмены (и после повторного чтения — «обновления страницы»)
    равны снимку до действия. Документы B и C при этом не меняются.
    """
    world = await seed_world(async_client)
    await kind.setup(world)
    before = await full_snapshot(world)
    remaining_before = await remaining_total(world)

    action_op = uuid.uuid4()
    ok(await kind.act(world, action_op), f"{kind.title}: само действие раскладки")
    assert await full_snapshot(world) != before, f"{kind.title}: действие ничего не изменило"

    ok(await undo(world, action_op), f"{kind.title}: «назад»")

    after = await full_snapshot(world)
    assert after == before, f"{kind.title}: после «назад» состояние не равно снимку до действия"
    assert await remaining_total(world) == remaining_before
    # «После обновления страницы — то же»: повторное чтение состава.
    assert (await full_snapshot(world))["view_a"] == before["view_a"]


@pytest.mark.asyncio
async def test_c13_server_undoes_three_actions_in_reverse_order(async_client: AsyncClient) -> None:
    """C13 (серверная часть) · R12: три действия и три отмены в обратном порядке.

    Порядок нажатий задаёт экран (DOM-тест C13); сервер обязан принять отмены
    в обратном порядке и после третьей вернуть снимок до первого действия.
    """
    world = await seed_world(async_client)
    await put_k1_on_a12(world)
    s0 = await full_snapshot(world)
    op1, op2, op3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ok(await place(world, kind="box", object_id=world.a.boxes["К2"], cell="А 1.1", op=op1),
       "К2 на А 1.1")
    s1 = await full_snapshot(world)
    ok(await scan(world, barcode=world.t1_barcode, cell="А 1.1", to_id=world.a.boxes["К2"],
                  op=op2), "Т1 в К2")
    s2 = await full_snapshot(world)
    ok(await place(world, kind="box", object_id=world.a.boxes["К1"], op=op3), "Снять К1")

    ok(await undo(world, op3), "назад 1 (снятие К1)")
    assert await full_snapshot(world) == s2
    ok(await undo(world, op2), "назад 2 (Т1 в К2)")
    assert await full_snapshot(world) == s1
    ok(await undo(world, op1), "назад 3 (К2 на А 1.1)")
    assert await full_snapshot(world) == s0


@pytest.mark.asyncio
async def test_c15_undo_refused_when_object_moved_after_action(async_client: AsyncClient) -> None:
    """C15 · R13, Д4: тару после действия переставил другой сотрудник в «Ячейках».

    «Назад» ничего не меняет и отвечает undo_target_moved; более раннее действие
    после этого отменяется обычным образом.
    """
    world = await seed_world(async_client)
    earlier_op = uuid.uuid4()
    s_before_earlier = await full_snapshot(world)
    ok(await place(world, kind="box", object_id=world.a.boxes["К3"], cell="Б 1.1",
                   op=earlier_op), "раннее действие: К3 на Б 1.1")
    s_before_k2 = await full_snapshot(world)

    k2_op = uuid.uuid4()
    ok(await place(world, kind="box", object_id=world.a.boxes["К2"], cell="А 1.1", op=k2_op),
       "К2 на А 1.1")
    ok(
        await map_move(world, kind="box", object_id=world.a.boxes["К2"], to_kind="cell",
                       to_id=world.cells["Б 1.1"], headers=world.other_headers),
        "другой сотрудник переносит К2 на Б 1.1 в разделе «Ячейки»",
    )
    moved = await full_snapshot(world)
    moves_before = await movement_ids(world)

    refused = await undo(world, k2_op)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == "undo_target_moved"
    assert await full_snapshot(world) == moved, "отказанная отмена что-то изменила"
    assert await movement_ids(world) == moves_before
    assert holder_of(await view(world), world.a.boxes["К2"]) == f"cell:{world.cells['Б 1.1']}"

    # Следующее «назад» — более раннее действие: К3 снова в «осталось».
    ok(await undo(world, earlier_op), "отмена более раннего действия")
    after = await full_snapshot(world)
    assert after["a"]["boxes"] != s_before_k2["a"]["boxes"]
    k3 = str(world.a.boxes["К3"])
    assert [row for row in after["a"]["boxes"] if row[0] == k3] == [
        row for row in s_before_earlier["a"]["boxes"] if row[0] == k3
    ]


@pytest.mark.asyncio
async def test_c16_repeated_undo_request_reverses_once(async_client: AsyncClient) -> None:
    """C16 · R13, R17: ответ на отмену потерян — повтор с тем же operation_id.

    Итог — ровно одна отмена: второго обратного движения нет, состояние то же.
    Вторая отмена того же действия с новым operation_id (двойной клик, дошедший
    до сервера) тоже не отменяет второй раз.
    """
    world = await seed_world(async_client)
    before = await full_snapshot(world)
    action_op = uuid.uuid4()
    ok(await place(world, kind="box", object_id=world.a.boxes["К2"], cell="А 1.1",
                   op=action_op), "К2 на А 1.1")

    undo_op = uuid.uuid4()
    ok(await undo(world, action_op, op=undo_op), "назад")
    after_first = await full_snapshot(world)
    assert after_first == before
    moves = await movement_ids(world)

    ok(await undo(world, action_op, op=undo_op), "повтор той же отмены после потери ответа")
    assert await movement_ids(world) == moves, "повтор отмены записал второе обратное движение"
    assert await full_snapshot(world) == before

    second = await undo(world, action_op)
    assert second.status_code < 500, second.text
    assert await movement_ids(world) == moves, "вторая отмена того же действия сработала"
    assert await full_snapshot(world) == before


@pytest.mark.asyncio
async def test_c17_rejected_action_cannot_be_undone(async_client: AsyncClient) -> None:
    """C17 (серверная часть) · R13: отклонённое действие в историю не попадает.

    Если экран всё же пришлёт отмену операции, которую сервер отклонил, отмена
    ничего не меняет и не отвечает успехом.
    """
    world = await seed_world(async_client)
    before = await full_snapshot(world)
    rejected_op = uuid.uuid4()
    rejected = await place(world, kind="box", object_id=world.a.boxes["К3"], cell="А 1.1",
                           to_id=world.a.pallets["П1"], op=rejected_op)
    assert rejected.status_code >= 400, rejected.text
    response = await undo(world, rejected_op)
    assert response.status_code in {404, 409}, response.text
    # Ответ самой ручки отмены, а не «маршрута нет»: отмену неизвестной операции
    # сервер отклоняет своим кодом.
    assert response.json().get("detail") != "Not Found", "ручки отмены нет"
    assert await full_snapshot(world) == before


@pytest.mark.asyncio
async def test_c28_undo_does_not_reopen_posted_document(async_client: AsyncClient) -> None:
    """C28 · R12, R13, Д5: последний короб оприходовал документ — «назад» отказывает.

    Документ остаётся «Оприходовано», начисление одно и не меняется, короб на
    месте; переставить его сканом другой ячейки можно — это только расположение.
    """
    world = await seed_world(async_client)
    doc = world.c  # единственный короб КЦ1, россыпи нет
    last_op = uuid.uuid4()
    ok(await place(world, kind="box", object_id=doc.boxes["КЦ1"], cell="А 1.1", op=last_op,
                   doc=doc), "последний короб на А 1.1")
    assert await request_status(world, doc) == "done"
    billing = await billing_snapshot(world, doc)
    state = await document_state(world, doc)
    moves = await movement_ids(world)

    refused = await undo(world, last_op, doc=doc)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == "undo_document_posted"
    assert await request_status(world, doc) == "done"
    assert await billing_snapshot(world, doc) == billing
    assert await document_state(world, doc) == state
    assert await movement_ids(world) == moves

    ok(await place(world, kind="box", object_id=doc.boxes["КЦ1"], cell="Б 1.1", doc=doc),
       "перестановка сканом в другую ячейку после оприходования")
    assert holder_of(await view(world, doc), doc.boxes["КЦ1"]) == f"cell:{world.cells['Б 1.1']}"
    assert await request_status(world, doc) == "done"
    assert await billing_snapshot(world, doc) == billing
    after = await document_state(world, doc)
    assert after["posted"] == state["posted"]
    assert after["box_posted"] == state["box_posted"]
