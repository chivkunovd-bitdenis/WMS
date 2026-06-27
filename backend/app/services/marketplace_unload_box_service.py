"""Boxes and barcode scanning for marketplace unload requests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inbound_intake import InboundIntakeBoxLine
from app.models.marketplace_unload import (
    MarketplaceUnloadBox,
    MarketplaceUnloadBoxLine,
    MarketplaceUnloadLine,
    MarketplaceUnloadPickAllocation,
    MarketplaceUnloadRequest,
)
from app.services import marketplace_unload_collect_service as collect_svc
from app.services import marketplace_unload_service as mu_svc
from app.services import tenant_settings_service as tenant_settings_svc
from app.services import warehouse_box_service as wh_box_svc
from app.services.marketplace_unload_pick_service import (
    MarketplaceUnloadPickError,
    find_location_by_barcode,
)
from app.services.seller_wb_catalog_service import list_seller_wb_catalog_rows

ALLOWED_BOX_PRESETS = frozenset({"60_40_40", "30_20_30"})
MAX_BATCH_BOX_COUNT = 50


class MarketplaceUnloadBoxError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class BoxScanResult:
    """TSD scan flow: location (optional) → product → box line update."""

    kind: Literal["location", "product"]
    storage_location_id: uuid.UUID | None = None
    location_code: str | None = None
    box_line: MarketplaceUnloadBoxLine | None = None
    picked_qty: int | None = None


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


async def _assert_packaging_done_for_boxes(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID
) -> None:
    from app.services import packaging_task_service as pkg_svc

    try:
        await pkg_svc.assert_unload_packaging_done(session, tenant_id, request_id)
    except pkg_svc.PackagingTaskServiceError as exc:
        if exc.code in ("task_not_done", "marking_not_done"):
            raise MarketplaceUnloadBoxError(
                "packaging_not_done"
                if exc.code == "task_not_done"
                else "marking_not_done"
            ) from exc
        raise


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

    await _assert_packaging_done_for_boxes(session, tenant_id, request_id)

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


async def create_boxes_batch(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    count: int,
    box_preset: str,
) -> list[MarketplaceUnloadBox]:
    """Create N empty open boxes with barcodes (batch flow; no open_box_exists gate)."""
    if count < 1 or count > MAX_BATCH_BOX_COUNT:
        raise MarketplaceUnloadBoxError("invalid_batch_count")
    preset = box_preset.strip()
    if preset not in ALLOWED_BOX_PRESETS:
        raise MarketplaceUnloadBoxError("invalid_preset")
    req = await _request_for_picking(session, tenant_id, request_id)
    await _assert_packaging_done_for_boxes(session, tenant_id, request_id)

    created_ids: list[uuid.UUID] = []
    for _ in range(count):
        wh_box = await wh_box_svc.create_warehouse_box(
            session,
            tenant_id,
            warehouse_id=req.warehouse_id,
        )
        box = MarketplaceUnloadBox(
            request_id=request_id,
            box_preset=preset,
            warehouse_box_id=wh_box.id,
            closed_at=None,
        )
        session.add(box)
        await session.flush()
        created_ids.append(box.id)

    await session.commit()
    stmt = (
        select(MarketplaceUnloadBox)
        .where(MarketplaceUnloadBox.id.in_(created_ids))
        .options(selectinload(MarketplaceUnloadBox.warehouse_box))
        .order_by(MarketplaceUnloadBox.created_at.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


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
) -> BoxScanResult:
    """Scan flow for TSD/web: optional location barcode, then product → box line."""
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

    address_on = await tenant_settings_svc.is_address_storage_enabled(session, tenant_id)
    if address_on:
        loc = await find_location_by_barcode(session, tenant_id, req.warehouse_id, raw)
        if loc is not None:
            return BoxScanResult(
                kind="location",
                storage_location_id=loc.id,
                location_code=loc.code,
            )

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
    return BoxScanResult(
        kind="product",
        storage_location_id=result.allocation.storage_location_id,
        box_line=result.box_line,
        picked_qty=result.picked_qty,
    )


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


def _box_total_qty(box: MarketplaceUnloadBox) -> int:
    return sum(int(ln.quantity) for ln in box.lines)


async def remove_box_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box_id: uuid.UUID,
    line_id: uuid.UUID,
    *,
    quantity: int | None = None,
) -> MarketplaceUnloadBoxLine | None:
    box = await session.get(MarketplaceUnloadBox, box_id)
    if box is None:
        raise MarketplaceUnloadBoxError("box_not_found")
    try:
        return await collect_svc.remove_from_box(
            session,
            tenant_id,
            box.request_id,
            box_id=box_id,
            line_id=line_id,
            quantity=quantity,
        )
    except MarketplaceUnloadPickError as exc:
        raise _map_collect_err(exc) from None


async def delete_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box_id: uuid.UUID,
) -> None:
    box = await session.get(
        MarketplaceUnloadBox,
        box_id,
        options=[selectinload(MarketplaceUnloadBox.lines)],
    )
    if box is None:
        raise MarketplaceUnloadBoxError("box_not_found")
    await _request_for_picking(session, tenant_id, box.request_id)
    if _box_total_qty(box) > 0:
        raise MarketplaceUnloadBoxError("box_not_empty")
    await session.delete(box)
    await session.commit()


async def copy_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box_id: uuid.UUID,
) -> MarketplaceUnloadBox:
    """Duplicate a closed source box into a new closed box (REV-FIX-015).

    Intentionally closed: copy is a snapshot for shipping labels / repeat shipment,
    not for further manual add (use batch create for open boxes).
    """
    src = await session.get(
        MarketplaceUnloadBox,
        box_id,
        options=[
            selectinload(MarketplaceUnloadBox.lines),
            selectinload(MarketplaceUnloadBox.warehouse_box),
        ],
    )
    if src is None:
        raise MarketplaceUnloadBoxError("box_not_found")
    req = await _request_for_picking(session, tenant_id, src.request_id)
    if not src.lines:
        raise MarketplaceUnloadBoxError("box_empty")

    picked = await collect_svc.picked_qty_by_product(session, req.id)
    plan_by_product = {ln.product_id: int(ln.quantity) for ln in req.lines}
    for ln in src.lines:
        pid = ln.product_id
        add_qty = int(ln.quantity)
        if add_qty < 1:
            continue
        current = picked.get(pid, 0)
        plan_qty = plan_by_product.get(pid, 0)
        if current + add_qty > plan_qty:
            raise MarketplaceUnloadBoxError("plan_limit_exceeded")

    await _assert_packaging_done_for_boxes(session, tenant_id, req.id)

    wh_box = await wh_box_svc.create_warehouse_box(
        session,
        tenant_id,
        warehouse_id=req.warehouse_id,
    )
    new_box = MarketplaceUnloadBox(
        request_id=req.id,
        box_preset=src.box_preset,
        warehouse_box_id=wh_box.id,
    )
    session.add(new_box)
    await session.flush()

    for ln in src.lines:
        qty = int(ln.quantity)
        if qty < 1:
            continue
        remaining = qty
        alloc_stmt = (
            select(MarketplaceUnloadPickAllocation)
            .where(
                MarketplaceUnloadPickAllocation.request_id == req.id,
                MarketplaceUnloadPickAllocation.product_id == ln.product_id,
                MarketplaceUnloadPickAllocation.quantity > 0,
            )
            .order_by(MarketplaceUnloadPickAllocation.quantity.desc())
        )
        alloc_res = await session.execute(alloc_stmt)
        allocs = list(alloc_res.scalars().all())
        if not allocs:
            raise MarketplaceUnloadBoxError("insufficient_available")
        for alloc in allocs:
            if remaining < 1:
                break
            chunk = min(int(alloc.quantity), remaining)
            try:
                await collect_svc.collect_into_box(
                    session,
                    tenant_id,
                    req.id,
                    box_id=new_box.id,
                    storage_location_id=alloc.storage_location_id,
                    product_id=ln.product_id,
                    quantity=chunk,
                    require_open_box=False,
                )
            except MarketplaceUnloadPickError as exc:
                raise _map_collect_err(exc) from None
            remaining -= chunk
        if remaining > 0:
            raise MarketplaceUnloadBoxError("insufficient_available")

    new_box.closed_at = datetime.now(tz=UTC)
    await session.commit()

    stmt = (
        select(MarketplaceUnloadBox)
        .where(MarketplaceUnloadBox.id == new_box.id)
        .options(
            selectinload(MarketplaceUnloadBox.lines).selectinload(
                MarketplaceUnloadBoxLine.product
            ),
            selectinload(MarketplaceUnloadBox.warehouse_box),
        )
    )
    res = await session.execute(stmt)
    return res.scalars().unique().one()
