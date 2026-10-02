from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services import packaging_task_service as svc


def _rows(values):
    result = Mock()
    result.scalars.return_value.all.return_value = values
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["picks", "plan"])
@pytest.mark.parametrize("progress", ["printed", "external", "packed", "confirmed", "none"])
async def test_resync_keeps_unpicked_marked_line(monkeypatch, source, progress):
    location_id = uuid.uuid4()
    line = SimpleNamespace(
        id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        storage_location_id=location_id,
        qty_total=15,
        qty_packed_in_task=1 if progress == "packed" else 0,
        qty_confirmed_packed=1 if progress == "confirmed" else 0,
        qty_marking_printed=15 if progress == "printed" else 0,
        qty_marking_external=15 if progress == "external" else 0,
    )
    task = SimpleNamespace(
        id=uuid.uuid4(),
        warehouse_id=uuid.uuid4(),
        marketplace_unload_request_id=uuid.uuid4(),
        status="in_progress",
    )
    # Another product has just been picked; the printed product is not picked yet.
    first_pick = SimpleNamespace(product_id=uuid.uuid4(), quantity=18)
    no_picks = Mock()
    no_picks.scalar_one_or_none.return_value = None
    results = (
        [_rows([first_pick]), _rows([line])]
        if source == "picks"
        else [no_picks, _rows([]), _rows([line])]
    )
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=results),
        delete=AsyncMock(),
        add=Mock(),
        commit=AsyncMock(),
    )
    monkeypatch.setattr(svc, "get_task", AsyncMock(return_value=task))
    monkeypatch.setattr(svc, "_get_balance_split", AsyncMock(return_value=(0, 0)))
    monkeypatch.setattr(
        svc.sorting_loc_svc,
        "get_or_create_sorting_location",
        AsyncMock(return_value=SimpleNamespace(id=location_id)),
    )

    if source == "picks":
        await svc.sync_lines_from_pick_allocations(session, uuid.uuid4(), task)
    else:
        await svc.sync_lines_from_unload_plan(session, uuid.uuid4(), task)

    if progress == "none":
        session.delete.assert_awaited_once_with(line)
    else:
        session.delete.assert_not_awaited()
        assert task.pick_resync_warning is True
    assert line.qty_total == 15
    assert line.qty_marking_printed == (15 if progress == "printed" else 0)
