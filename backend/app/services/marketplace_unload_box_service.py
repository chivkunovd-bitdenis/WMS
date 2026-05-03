"""Boxes and barcode scanning for marketplace unload requests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.marketplace_unload import (
    MarketplaceUnloadBox,
    MarketplaceUnloadBoxLine,
    MarketplaceUnloadLine,
    MarketplaceUnloadRequest,
)
from app.services import marketplace_unload_service as mu_svc
from app.services.seller_wb_catalog_service import list_seller_wb_catalog_rows

ALLOWED_BOX_PRESETS = frozenset({"60_40_40", "30_20_30"})


class MarketplaceUnloadBoxError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


async def _barcode_index_for_seller(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> dict[str, uuid.UUID]:
    rows = await list_seller_wb_catalog_rows(session, tenant_id, seller_id)
    idx: dict[str, uuid.UUID] = {}
    for r in rows:
        for b in r.wb_barcodes:
            key = str(b).strip()
            if key:
                idx[key] = r.product_id
        if r.wb_primary_barcode:
            k = r.wb_primary_barcode.strip()
            if k:
                idx[k] = r.product_id
    return idx


async def _request_draft(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID
) -> MarketplaceUnloadRequest:
    req = await mu_svc.get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadBoxError("not_found")
    if req.status != mu_svc.STATUS_DRAFT:
        raise MarketplaceUnloadBoxError("not_editable")
    if req.seller_id is None:
        raise MarketplaceUnloadBoxError("seller_required")
    return req


async def _open_box_for_request(
    session: AsyncSession, request_id: uuid.UUID
) -> MarketplaceUnloadBox | None:
    stmt = select(MarketplaceUnloadBox).where(
        MarketplaceUnloadBox.request_id == request_id,
        MarketplaceUnloadBox.closed_at.is_(None),
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def create_open_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    box_preset: str,
) -> MarketplaceUnloadBox:
    preset = box_preset.strip()
    if preset not in ALLOWED_BOX_PRESETS:
        raise MarketplaceUnloadBoxError("invalid_preset")
    await _request_draft(session, tenant_id, request_id)
    existing = await _open_box_for_request(session, request_id)
    if existing is not None:
        raise MarketplaceUnloadBoxError("open_box_exists")
    box = MarketplaceUnloadBox(request_id=request_id, box_preset=preset)
    session.add(box)
    await session.commit()
    await session.refresh(box)
    return box


async def _total_scanned_for_product(
    session: AsyncSession,
    request_id: uuid.UUID,
    product_id: uuid.UUID,
) -> int:
    stmt = (
        select(func.coalesce(func.sum(MarketplaceUnloadBoxLine.quantity), 0))
        .join(MarketplaceUnloadBox, MarketplaceUnloadBoxLine.box_id == MarketplaceUnloadBox.id)
        .where(
            MarketplaceUnloadBox.request_id == request_id,
            MarketplaceUnloadBoxLine.product_id == product_id,
        )
    )
    res = await session.execute(stmt)
    return int(res.scalar_one())


async def _planned_qty(
    session: AsyncSession, request_id: uuid.UUID, product_id: uuid.UUID
) -> int:
    stmt = select(MarketplaceUnloadLine).where(
        MarketplaceUnloadLine.request_id == request_id,
        MarketplaceUnloadLine.product_id == product_id,
    )
    res = await session.execute(stmt)
    ln = res.scalar_one_or_none()
    if ln is None:
        return 0
    return int(ln.quantity)


async def scan_barcode_into_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box_id: uuid.UUID,
    *,
    barcode: str,
) -> MarketplaceUnloadBoxLine:
    raw = barcode.strip()
    if not raw:
        raise MarketplaceUnloadBoxError("barcode_empty")

    box = await session.get(MarketplaceUnloadBox, box_id)
    if box is None:
        raise MarketplaceUnloadBoxError("box_not_found")
    if box.closed_at is not None:
        raise MarketplaceUnloadBoxError("box_closed")

    req = await _request_draft(session, tenant_id, box.request_id)
    if req.seller_id is None:
        raise MarketplaceUnloadBoxError("seller_required")

    idx = await _barcode_index_for_seller(session, tenant_id, req.seller_id)
    product_id = idx.get(raw)
    if product_id is None:
        raise MarketplaceUnloadBoxError("barcode_unknown")

    planned = await _planned_qty(session, req.id, product_id)
    if planned <= 0:
        raise MarketplaceUnloadBoxError("product_not_in_shipment")

    scanned = await _total_scanned_for_product(session, req.id, product_id)
    if scanned >= planned:
        raise MarketplaceUnloadBoxError("qty_exceeded")

    stmt = select(MarketplaceUnloadBoxLine).where(
        MarketplaceUnloadBoxLine.box_id == box_id,
        MarketplaceUnloadBoxLine.product_id == product_id,
    )
    res = await session.execute(stmt)
    line = res.scalar_one_or_none()
    if line is None:
        line = MarketplaceUnloadBoxLine(box_id=box_id, product_id=product_id, quantity=1)
        session.add(line)
    else:
        line.quantity = int(line.quantity) + 1
    await session.commit()
    stmt2 = (
        select(MarketplaceUnloadBoxLine)
        .where(MarketplaceUnloadBoxLine.id == line.id)
        .options(selectinload(MarketplaceUnloadBoxLine.product))
    )
    res2 = await session.execute(stmt2)
    out = res2.scalar_one()
    return out


async def close_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box_id: uuid.UUID,
) -> MarketplaceUnloadBox:
    box = await session.get(MarketplaceUnloadBox, box_id)
    if box is None:
        raise MarketplaceUnloadBoxError("box_not_found")
    await _request_draft(session, tenant_id, box.request_id)
    if box.closed_at is not None:
        raise MarketplaceUnloadBoxError("box_closed")
    box.closed_at = datetime.now(tz=UTC)
    await session.commit()
    await session.refresh(box)
    return box


async def list_boxes_with_lines(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID
) -> list[MarketplaceUnloadBox]:
    req = await mu_svc.get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadBoxError("not_found")
    stmt = (
        select(MarketplaceUnloadBox)
        .where(MarketplaceUnloadBox.request_id == request_id)
        .options(
            selectinload(MarketplaceUnloadBox.lines).selectinload(MarketplaceUnloadBoxLine.product),
        )
        .order_by(MarketplaceUnloadBox.created_at.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().unique().all())
