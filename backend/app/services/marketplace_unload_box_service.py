"""Boxes and barcode scanning for marketplace unload requests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inbound_intake import InboundIntakeBoxLine
from app.models.marketplace_unload import (
    MarketplaceUnloadBox,
    MarketplaceUnloadBoxLine,
    MarketplaceUnloadLine,
    MarketplaceUnloadRequest,
)
from app.services import marketplace_unload_collect_service as collect_svc
from app.services import marketplace_unload_service as mu_svc
from app.services import warehouse_box_service as wh_box_svc
from app.services.marketplace_unload_pick_service import MarketplaceUnloadPickError
from app.services.seller_wb_catalog_service import list_seller_wb_catalog_rows

ALLOWED_BOX_PRESETS = frozenset({"60_40_40", "30_20_30"})


class MarketplaceUnloadBoxError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _map_collect_err(exc: MarketplaceUnloadPickError) -> MarketplaceUnloadBoxError:
    return MarketplaceUnloadBoxError(exc.code)


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


async def _request_for_picking(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID
) -> MarketplaceUnloadRequest:
    req = await mu_svc.get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadBoxError("not_found")
    if req.status != mu_svc.STATUS_CONFIRMED:
        raise MarketplaceUnloadBoxError("not_editable")
    if req.seller_id is None:
        raise MarketplaceUnloadBoxError("seller_required")
    return req


async def _open_box_for_request(
    session: AsyncSession, request_id: uuid.UUID
) -> MarketplaceUnloadBox | None:
    return await collect_svc.get_open_box(session, request_id)


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
    req = await _request_for_picking(session, tenant_id, request_id)
    existing = await _open_box_for_request(session, request_id)
    if existing is not None:
        raise MarketplaceUnloadBoxError("open_box_exists")
    wh_box = await wh_box_svc.create_warehouse_box(
        session,
        tenant_id,
        warehouse_id=req.warehouse_id,
    )
    box = MarketplaceUnloadBox(
        request_id=request_id,
        box_preset=preset,
        warehouse_box_id=wh_box.id,
    )
    session.add(box)
    await session.commit()
    stmt = (
        select(MarketplaceUnloadBox)
        .where(MarketplaceUnloadBox.id == box.id)
        .options(selectinload(MarketplaceUnloadBox.warehouse_box))
    )
    res = await session.execute(stmt)
    return res.scalar_one()


async def _product_in_shipment(
    session: AsyncSession, request_id: uuid.UUID, product_id: uuid.UUID
) -> bool:
    stmt = select(MarketplaceUnloadLine.id).where(
        MarketplaceUnloadLine.request_id == request_id,
        MarketplaceUnloadLine.product_id == product_id,
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none() is not None


async def scan_barcode_into_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box_id: uuid.UUID,
    *,
    barcode: str,
    storage_location_id: uuid.UUID,
    quantity: int = 1,
) -> MarketplaceUnloadBoxLine:
    raw = barcode.strip()
    if not raw:
        raise MarketplaceUnloadBoxError("barcode_empty")
    if quantity < 1:
        raise MarketplaceUnloadBoxError("invalid_quantity")

    box = await session.get(MarketplaceUnloadBox, box_id)
    if box is None:
        raise MarketplaceUnloadBoxError("box_not_found")
    if box.closed_at is not None:
        raise MarketplaceUnloadBoxError("box_closed")

    req = await _request_for_picking(session, tenant_id, box.request_id)
    if req.seller_id is None:
        raise MarketplaceUnloadBoxError("seller_required")

    idx = await _barcode_index_for_seller(session, tenant_id, req.seller_id)
    product_id = idx.get(raw)
    if product_id is None:
        raise MarketplaceUnloadBoxError("barcode_unknown")

    if not await _product_in_shipment(session, req.id, product_id):
        raise MarketplaceUnloadBoxError("product_not_in_shipment")

    try:
        result = await collect_svc.collect_into_box(
            session,
            tenant_id,
            box.request_id,
            box_id=box_id,
            storage_location_id=storage_location_id,
            product_id=product_id,
            quantity=quantity,
        )
    except MarketplaceUnloadPickError as exc:
        raise _map_collect_err(exc) from None
    return result.box_line


async def add_manual_qty_to_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box_id: uuid.UUID,
    *,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    quantity: int,
) -> MarketplaceUnloadBoxLine:
    if quantity < 1:
        raise MarketplaceUnloadBoxError("invalid_quantity")

    box = await session.get(MarketplaceUnloadBox, box_id)
    if box is None:
        raise MarketplaceUnloadBoxError("box_not_found")
    if box.closed_at is not None:
        raise MarketplaceUnloadBoxError("box_closed")

    req = await _request_for_picking(session, tenant_id, box.request_id)
    if not await _product_in_shipment(session, req.id, product_id):
        raise MarketplaceUnloadBoxError("product_not_in_shipment")

    try:
        result = await collect_svc.collect_into_box(
            session,
            tenant_id,
            box.request_id,
            box_id=box_id,
            storage_location_id=storage_location_id,
            product_id=product_id,
            quantity=quantity,
        )
    except MarketplaceUnloadPickError as exc:
        raise _map_collect_err(exc) from None
    return result.box_line


async def attach_existing_box_by_barcode(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    barcode: str,
    box_preset: str = "60_40_40",
) -> MarketplaceUnloadBox:
    """Привязать существующий короб (WHB или приёмочный) и развернуть состав в подбор."""
    preset = box_preset.strip()
    if preset not in ALLOWED_BOX_PRESETS:
        raise MarketplaceUnloadBoxError("invalid_preset")
    req = await _request_for_picking(session, tenant_id, request_id)

    wh_box, inb_box = await wh_box_svc.resolve_barcode(session, tenant_id, barcode)
    if wh_box is None and inb_box is None:
        raise MarketplaceUnloadBoxError("box_barcode_unknown")

    if wh_box is not None and wh_box.warehouse_id != req.warehouse_id:
        raise MarketplaceUnloadBoxError("warehouse_mismatch")

    mp_box = MarketplaceUnloadBox(
        request_id=request_id,
        box_preset=preset,
        warehouse_box_id=wh_box.id if wh_box is not None else None,
    )
    session.add(mp_box)
    await session.flush()

    picks_added = 0
    if inb_box is not None:
        distro = await wh_box_svc.distribution_lines_for_inbound_box(session, inb_box.id)
        if distro:
            for dl in distro:
                if not await _product_in_shipment(session, req.id, dl.product_id):
                    continue
                try:
                    await collect_svc.collect_into_box(
                        session,
                        tenant_id,
                        request_id,
                        box_id=mp_box.id,
                        storage_location_id=dl.storage_location_id,
                        product_id=dl.product_id,
                        quantity=int(dl.quantity),
                        require_open_box=False,
                    )
                except MarketplaceUnloadPickError as exc:
                    raise _map_collect_err(exc) from None
                picks_added += 1
        else:
            stmt = select(InboundIntakeBoxLine).where(
                InboundIntakeBoxLine.box_id == inb_box.id
            )
            res = await session.execute(stmt)
            for bl in res.scalars().all():
                qty = int(bl.posted_qty) if int(bl.posted_qty) > 0 else int(bl.quantity)
                if qty < 1:
                    continue
                if not await _product_in_shipment(session, req.id, bl.product_id):
                    continue
                if wh_box is not None and wh_box.storage_location_id is not None:
                    try:
                        await collect_svc.collect_into_box(
                            session,
                            tenant_id,
                            request_id,
                            box_id=mp_box.id,
                            storage_location_id=wh_box.storage_location_id,
                            product_id=bl.product_id,
                            quantity=qty,
                            require_open_box=False,
                        )
                    except MarketplaceUnloadPickError as exc:
                        raise _map_collect_err(exc) from None
                    picks_added += 1

    if inb_box is not None and picks_added < 1:
        raise MarketplaceUnloadBoxError("box_needs_location")

    if wh_box is not None and inb_box is None:
        dup_stmt = select(MarketplaceUnloadBox).where(
            MarketplaceUnloadBox.warehouse_box_id == wh_box.id,
            MarketplaceUnloadBox.request_id == request_id,
            MarketplaceUnloadBox.id != mp_box.id,
        )
        res = await session.execute(dup_stmt)
        if res.scalar_one_or_none() is not None:
            raise MarketplaceUnloadBoxError("box_already_attached")

    mp_box.closed_at = datetime.now(tz=UTC)
    await session.commit()
    await session.refresh(mp_box, attribute_names=["warehouse_box", "lines"])
    return mp_box


async def close_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box_id: uuid.UUID,
) -> MarketplaceUnloadBox:
    box = await session.get(MarketplaceUnloadBox, box_id)
    if box is None:
        raise MarketplaceUnloadBoxError("box_not_found")
    await _request_for_picking(session, tenant_id, box.request_id)
    if box.closed_at is not None:
        raise MarketplaceUnloadBoxError("box_closed")
    box.closed_at = datetime.now(tz=UTC)
    await session.commit()
    await session.refresh(box, attribute_names=["warehouse_box"])
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
            selectinload(MarketplaceUnloadBox.lines).selectinload(
                MarketplaceUnloadBoxLine.product
            ),
            selectinload(MarketplaceUnloadBox.warehouse_box),
        )
        .order_by(MarketplaceUnloadBox.created_at.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().unique().all())
