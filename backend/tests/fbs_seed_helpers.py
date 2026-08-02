"""Shared FBS test seed helpers: WB warehouse binding + order row warehouseId."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_warehouse_binding import FbsWarehouseBinding

DEFAULT_WB_WAREHOUSE_ID = 501001


async def seed_fbs_warehouse_binding(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    wms_warehouse_id: uuid.UUID,
    wb_warehouse_id: int = DEFAULT_WB_WAREHOUSE_ID,
) -> None:
    existing = await session.scalar(
        select(FbsWarehouseBinding.id).where(
            FbsWarehouseBinding.seller_id == seller_id,
            FbsWarehouseBinding.wb_warehouse_id == wb_warehouse_id,
        )
    )
    if existing is not None:
        return
    session.add(
        FbsWarehouseBinding(
            tenant_id=tenant_id,
            seller_id=seller_id,
            wb_warehouse_id=wb_warehouse_id,
            wms_warehouse_id=wms_warehouse_id,
            stock_sync_enabled=True,
            is_active=True,
        )
    )
    await session.flush()


def wb_order_row_with_warehouse(
    row: dict[str, Any],
    *,
    wb_warehouse_id: int = DEFAULT_WB_WAREHOUSE_ID,
) -> dict[str, Any]:
    out = dict(row)
    out["warehouseId"] = wb_warehouse_id
    return out
