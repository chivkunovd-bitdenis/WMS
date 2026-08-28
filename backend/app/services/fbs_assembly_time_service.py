"""Среднее время от появления заказа WB до отгрузки его поставки."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply


@dataclass(frozen=True)
class FbsAssemblyTime:
    hours: float
    orders: int


async def calculate_fbs_assembly_time(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    period_from: datetime,
    period_to: datetime,
    seller_id: uuid.UUID | None = None,
) -> FbsAssemblyTime:
    if period_from >= period_to:
        raise ValueError("invalid_period")

    stmt = (
        select(FbsOrder.created_at_wb, FbsSupply.delivered_at)
        .join(FbsSupply, FbsSupply.id == FbsOrder.supply_id)
        .where(
            FbsOrder.tenant_id == tenant_id,
            FbsSupply.tenant_id == tenant_id,
            FbsSupply.delivered_at.is_not(None),
            FbsOrder.created_at_wb >= period_from,
            FbsOrder.created_at_wb < period_to,
        )
    )
    if seller_id is not None:
        stmt = stmt.where(
            FbsOrder.seller_id == seller_id,
            FbsSupply.seller_id == seller_id,
        )
    rows = (await session.execute(stmt)).all()
    durations = [
        (delivered_at - created_at_wb).total_seconds()
        for created_at_wb, delivered_at in rows
        if delivered_at is not None and delivered_at >= created_at_wb
    ]
    if not durations:
        return FbsAssemblyTime(hours=0.0, orders=0)
    average_hours = sum(durations) / len(durations) / 3600
    return FbsAssemblyTime(hours=round(average_hours, 1), orders=len(durations))
