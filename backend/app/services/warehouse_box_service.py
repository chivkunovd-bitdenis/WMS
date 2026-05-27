"""Tenant-wide physical boxes with printable barcodes."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_intake import InboundIntakeBox, InboundIntakeDistributionLine
from app.models.warehouse_box import WarehouseBox


class WarehouseBoxError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _new_barcode() -> str:
    return f"WHB-{uuid.uuid4().hex[:12].upper()}"


async def create_warehouse_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID,
    storage_location_id: uuid.UUID | None = None,
) -> WarehouseBox:
    for _ in range(8):
        box = WarehouseBox(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            internal_barcode=_new_barcode(),
            storage_location_id=storage_location_id,
        )
        session.add(box)
        try:
            await session.flush()
            return box
        except IntegrityError:
            session.expunge(box)
            continue
    raise WarehouseBoxError("barcode_collision")


async def get_by_barcode(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    barcode: str,
) -> WarehouseBox | None:
    raw = barcode.strip()
    if not raw:
        return None
    stmt = select(WarehouseBox).where(
        WarehouseBox.tenant_id == tenant_id,
        WarehouseBox.internal_barcode == raw,
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def resolve_barcode(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    barcode: str,
) -> tuple[WarehouseBox | None, InboundIntakeBox | None]:
    """Warehouse box first, then inbound intake box by same barcode string."""
    raw = barcode.strip()
    if not raw:
        return None, None
    wh = await get_by_barcode(session, tenant_id, raw)
    if wh is not None:
        return wh, None
    stmt = select(InboundIntakeBox).where(
        InboundIntakeBox.tenant_id == tenant_id,
        InboundIntakeBox.internal_barcode == raw,
    )
    res = await session.execute(stmt)
    inb = res.scalar_one_or_none()
    return None, inb


async def distribution_lines_for_inbound_box(
    session: AsyncSession,
    box_id: uuid.UUID,
) -> list[InboundIntakeDistributionLine]:
    stmt = (
        select(InboundIntakeDistributionLine)
        .where(InboundIntakeDistributionLine.box_id == box_id)
        .order_by(InboundIntakeDistributionLine.created_at.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())
