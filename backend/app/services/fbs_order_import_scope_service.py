"""Отсев чужих WB-заказов до записи в локальную FBS-базу."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_warehouse_binding import FbsWarehouseBinding


@dataclass
class FbsOrderImportStats:
    received: int = 0
    upserted: int = 0
    created: int = 0
    skipped_unserved: int = 0


def _warehouse_id(row: dict[str, Any]) -> int | None:
    value = row.get("warehouseId")
    return int(value) if value is not None else None


async def import_wb_order_rows(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    rows: list[dict[str, Any]],
    pool_debit_totals: dict[str, int],
    stats: FbsOrderImportStats,
) -> None:
    """Импортировать наши и непривязанные заказы, не сохраняя явно чужие."""
    from app.services.wb_marketplace_orders_service import upsert_order_from_wb_row

    warehouse_ids = {
        warehouse_id for row in rows if (warehouse_id := _warehouse_id(row)) is not None
    }
    scopes: dict[int, bool] = {}
    if warehouse_ids:
        stmt = select(FbsWarehouseBinding).where(
            FbsWarehouseBinding.tenant_id == tenant_id,
            FbsWarehouseBinding.seller_id == seller_id,
            FbsWarehouseBinding.wb_warehouse_id.in_(warehouse_ids),
        )
        scopes = {
            int(binding.wb_warehouse_id): bool(binding.is_active and binding.served)
            for binding in (await session.execute(stmt)).scalars().all()
        }

    stats.received += len(rows)
    for row in rows:
        warehouse_id = _warehouse_id(row)
        scope = scopes.get(warehouse_id) if warehouse_id is not None else None
        if scope is False:
            stats.skipped_unserved += 1
            continue
        _order, was_created = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_id,
            row,
            pool_debit_totals=pool_debit_totals,
            # An unknown WB warehouse is not explicitly foreign. Let the normal
            # resolver bind it when the fulfillment center has one physical
            # warehouse. Existing bindings with served=False remain excluded
            # above and are never silently re-enabled.
            preserve_unmapped_warehouse=False,
        )
        stats.upserted += 1
        stats.created += int(was_created)
