"""WMS-686: проверки исправлений по ревью бэкенда (Astra high, 09.10.2026).

Контракт `test_wms686_r4_contract.py` не меняется: здесь только то, что ревью нашло
сверх него — повтор «Допечатать» после смены привязки кода, освобождение кода,
перенесённого миграцией, и перенос короба сверх плана при старом флаге клиента.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from test_wms686_r4_contract import (  # type: ignore[import-not-found]
    BASE,
    EAN_A,
    _attach,
    _box_in_cell,
    _cell,
    _detail,
    _import_pool,
    _kiz,
    _kiz_items,
    _kiz_scan,
    _loose,
    _movements,
    _org,
    _pick_scan,
    _pick_set,
    _pick_unit,
    _picked,
    _pool_available,
    _product,
    _receive,
    _shipment,
)

from app.db.session import SessionLocal
from app.models.marking_code import STATUS_APPLIED, MarkingCode
from app.models.packaging_task import PackagingTask, PackagingTaskLine


async def _task_line_id(mid: str) -> uuid.UUID:
    """Строка задания упаковки отгрузки (его создаёт утверждение, ТЗ упаковки)."""
    async with SessionLocal() as session:
        line_id = await session.scalar(
            select(PackagingTaskLine.id)
            .join(PackagingTask, PackagingTask.id == PackagingTaskLine.task_id)
            .where(PackagingTask.marketplace_unload_request_id == uuid.UUID(mid))
            .limit(1)
        )
    assert line_id is not None, "после утверждения у отгрузки нет задания упаковки"
    return line_id


async def _bind_to_task_line(cis_head: str, task_line_id: uuid.UUID) -> None:
    """Повторить состояние кода после миграции: привязка к строке задания упаковки."""
    async with SessionLocal() as session:
        code = await session.scalar(
            select(MarkingCode).where(MarkingCode.cis_code.startswith(cis_head))
        )
        assert code is not None
        code.packaging_task_line_id = task_line_id
        await session.commit()


async def _code_row(cis_head: str) -> tuple[str, uuid.UUID | None, uuid.UUID | None]:
    async with SessionLocal() as session:
        code = await session.scalar(
            select(MarkingCode).where(MarkingCode.cis_code.startswith(cis_head))
        )
        assert code is not None
        return code.status, code.marketplace_unload_line_id, code.packaging_task_line_id


@pytest.mark.asyncio
async def test_review_issue_replay_after_code_was_unlinked_or_taken_is_conflict(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P0: повтор «Допечатать» не возвращает код, который отвязан или занят другой отгрузкой."""
    ctx = await _loose(async_client, monkeypatch, qty=3, plan=2)
    pool = [_kiz(EAN_A, f"RVPOOL0000{n}") for n in (1, 2)]
    await _import_pool(async_client, ctx.h, sid=ctx.sid, pid=ctx.pid, sku=ctx.sku, codes=pool)
    await _pick_unit(async_client, ctx, 2)

    key = str(uuid.uuid4())
    body = {"product_id": ctx.pid, "mutation_id": key}
    issue_url = f"{BASE}/{ctx.mid}/marking-codes/issue"
    issued = await async_client.post(issue_url, headers=ctx.h, json=body)
    assert issued.status_code == 200, issued.text
    items = issued.json()["items"]
    assert len(items) == 2
    same = await async_client.post(issue_url, headers=ctx.h, json=body)
    assert same.status_code == 200, same.text  # пока всё на месте — те же коды

    gone = items[0]
    removed = await async_client.delete(
        f"{BASE}/{ctx.mid}/marking-codes/{gone['marking_code_id']}", headers=ctx.h
    )
    assert removed.status_code == 200 and removed.json() == {"removed": True}
    changed = await async_client.post(issue_url, headers=ctx.h, json=body)
    assert changed.status_code == 409, changed.text
    assert changed.json()["detail"] == "issue_result_changed"

    # Тот же код привязали в другой отгрузке: повтор по-прежнему отказ, код остаётся там.
    other = await _shipment(
        async_client, ctx.h, wid=ctx.wid, sid=ctx.sid, wb_wid=ctx.wb_wid, lines={ctx.pid: 1}
    )
    unit = await _pick_scan(async_client, ctx.h, other, EAN_A, pid=ctx.pid, loc_id=ctx.loc_id)
    assert unit.status_code == 200, unit.text
    taken = await _kiz_scan(async_client, ctx.h, other, str(gone["cis_code"]), pid=ctx.pid)
    assert taken.status_code == 200, taken.text
    again = await async_client.post(issue_url, headers=ctx.h, json=body)
    assert again.status_code == 409, again.text
    assert again.json()["detail"] == "issue_result_changed"
    assert len(await _kiz_items(async_client, ctx.h, other)) == 1
    assert len(await _kiz_items(async_client, ctx.h, ctx.mid)) == 1
    assert await _pool_available(async_client, ctx.h, ctx.sid, ctx.pid) == 0  # новых не выдано


@pytest.mark.asyncio
async def test_review_release_of_migrated_code_also_frees_own_task_line_and_allows_relink(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1: у перенесённого миграцией кода ✕ снимает и привязку к заданию ЭТОЙ отгрузки."""
    ctx = await _loose(async_client, monkeypatch, qty=3, plan=2)
    other = await _shipment(
        async_client, ctx.h, wid=ctx.wid, sid=ctx.sid, wb_wid=ctx.wb_wid, lines={ctx.pid: 1}
    )
    own_line, foreign_line = await _task_line_id(ctx.mid), await _task_line_id(other)
    await _pick_unit(async_client, ctx, 2)
    own, foreign = _kiz(EAN_A, "RVMIGR000001"), _kiz(EAN_A, "RVMIGR000002")
    for code in (own, foreign):
        linked = await _kiz_scan(async_client, ctx.h, ctx.mid, code, pid=ctx.pid)
        assert linked.status_code == 200, linked.text
    await _bind_to_task_line(own.split("\x1d", 1)[0], own_line)
    await _bind_to_task_line(foreign.split("\x1d", 1)[0], foreign_line)

    items = {
        str(item["cis_code"]).split("\x1d", 1)[0]: item
        for item in await _kiz_items(async_client, ctx.h, ctx.mid)
    }
    for code in (own, foreign):
        head = code.split("\x1d", 1)[0]
        removed = await async_client.delete(
            f"{BASE}/{ctx.mid}/marking-codes/{items[head]['marking_code_id']}", headers=ctx.h
        )
        assert removed.status_code == 200 and removed.json() == {"removed": True}

    status, unload_line, task_line = await _code_row(own.split("\x1d", 1)[0])
    assert (status, unload_line, task_line) == (STATUS_APPLIED, None, None)
    relinked = await _kiz_scan(async_client, ctx.h, ctx.mid, own, pid=ctx.pid)
    assert relinked.status_code == 200, relinked.text
    assert relinked.json()["already_linked"] is False

    # Привязка к заданию ЧУЖОЙ отгрузки не снимается: код остаётся занятым.
    _, _, foreign_task_line = await _code_row(foreign.split("\x1d", 1)[0])
    assert foreign_task_line == foreign_line
    refused = await _kiz_scan(async_client, ctx.h, ctx.mid, foreign, pid=ctx.pid)
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"] == "marking_code_used_elsewhere"


@pytest.mark.asyncio
async def test_review_attach_over_plan_is_refused_even_with_allow_over_plan_true(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1 (D1.7): флаг allow_over_plan=true в теле не разрешает перенос короба сверх плана."""
    h, wid, sid, wb_wid = await _org(async_client, monkeypatch)
    loc_id = await _cell(async_client, h, wid, "A-1-1")
    pid = await _product(async_client, h, sid, barcode=EAN_A, name="Футболка 48")
    await _receive(async_client, h, wid=wid, pid=pid, qty=7, loc_id=loc_id)
    _, box_barcode = await _box_in_cell(async_client, h, wid=wid, loc_id=loc_id, contents={pid: 5})
    mid = await _shipment(async_client, h, wid=wid, sid=sid, wb_wid=wb_wid, lines={pid: 6})
    taken = await _pick_set(async_client, h, mid, pid=pid, loc_id=loc_id, qty=2)
    assert taken.status_code == 200, taken.text
    movements = await _movements(pid)

    forced = await async_client.post(
        f"{BASE}/{mid}/boxes/attach",
        headers=h,
        json={"barcode": box_barcode, "box_preset": "60_40_40", "allow_over_plan": True},
    )
    assert forced.status_code == 422, forced.text
    assert forced.json()["detail"]["code"] == "plan_limit_exceeded"
    assert (await _detail(async_client, h, mid))["boxes"] == []
    assert await _picked(async_client, h, mid, pid) == 2
    assert await _movements(pid) == movements
    plain = await _attach(async_client, h, mid, box_barcode)
    assert plain.status_code == 422, plain.text
