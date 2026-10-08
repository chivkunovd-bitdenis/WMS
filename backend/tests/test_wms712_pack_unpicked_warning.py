"""WMS-712: при незавершённом подборе сервер не запирает вкладки и не публикует блокеры.

Проверки C3 (этап сервера не меняется) и C4 (список блокеров рабочей поверхности
при недоборе остаётся пустым). Предупреждение строится на фронте из уже
загруженных позиций, поэтому здесь проверяется только то, что сервер не отдаёт
навигационных блокеров и не переводит оператора на другой этап.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.services.fbs_workspace_service import (
    WorkspaceProgress,
    _compute_stage,
    _compute_workspace_blockers,
)


def _supply(marketplace: str) -> SimpleNamespace:
    return SimpleNamespace(
        marketplace=marketplace,
        status="assembling",
        delivery_type="warehouse_sc",
        trbxes=[],
    )


def _order(*, pick_status: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        wb_order_id=712001,
        pick_status=pick_status,
        pack_status="pending",
        sticker_status="ready",
        metadata_delivery_allowed=True,
        required_meta_json=[],
    )


def test_wms712_partial_pick_wb_keeps_server_stage_and_publishes_no_blockers() -> None:
    supply = _supply("wb")
    orders = [_order(pick_status="picked"), _order(pick_status="pending")]
    progress = WorkspaceProgress(picked=1, packed=0, metadata_ready=2, stickers_ready=2, total=2)

    stage = _compute_stage(supply, orders, progress, has_physical_boxes=False)
    blockers = _compute_workspace_blockers(
        supply, orders, stage, progress, has_physical_boxes=False
    )

    assert stage == "picking"
    assert blockers == []


def test_wms712_partial_pick_ozon_keeps_server_stage_and_publishes_no_blockers() -> None:
    supply = _supply("ozon")
    orders = [_order(pick_status="pending")]
    progress = WorkspaceProgress(picked=2, packed=0, metadata_ready=1, stickers_ready=1, total=3)

    stage = _compute_stage(supply, orders, progress, has_physical_boxes=False)
    blockers = _compute_workspace_blockers(
        supply, orders, stage, progress, has_physical_boxes=False
    )

    assert stage == "picking"
    assert blockers == []
