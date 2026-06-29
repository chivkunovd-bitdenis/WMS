from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeBoxLine,
    InboundIntakeLine,
    InboundIntakeRequest,
)
from app.models.product import Product
from app.services import inbound_intake_service as intake_svc
from app.services.seller_wb_catalog_service import list_seller_wb_catalog_rows

# IN-BE-01 collapsed chain — keep in sync with inbound_intake_service status constants.
BOX_STATUSES_AFTER_PRIMARY = (
    intake_svc.STATUS_RECEIVING,
    intake_svc.STATUS_SORTING,
    intake_svc.STATUS_DONE,
)

INTAKE_STATUSES = (
    intake_svc.STATUS_SUBMITTED,
    intake_svc.STATUS_RECEIVING,
)


class InboundIntakeBoxError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _new_barcode() -> str:
    return f"INB-{uuid.uuid4().hex[:12].upper()}"


async def _next_box_number(session: AsyncSession, request_id: uuid.UUID) -> int:
    stmt = select(func.coalesce(func.max(InboundIntakeBox.box_number), 0)).where(
        InboundIntakeBox.request_id == request_id,
    )
    res = await session.execute(stmt)
    return int(res.scalar_one()) + 1


async def create_open_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> InboundIntakeBox:
    """Create a new inbound box and open it for piece intake (on demand)."""
    req = await _get_request_for_intake(session, tenant_id, request_id)
    if await _open_box_for_request(session, request_id) is not None:
        raise InboundIntakeBoxError("open_box_exists")

    box_number = await _next_box_number(session, req.id)
    now = datetime.now(UTC)
    for _ in range(8):
        box = InboundIntakeBox(
            tenant_id=tenant_id,
            request_id=req.id,
            box_number=box_number,
            internal_barcode=_new_barcode(),
            intake_opened_at=now,
        )
        session.add(box)
        try:
            await session.flush()
            await session.commit()
            return await _load_box(session, box.id)
        except IntegrityError:
            session.expunge(box)
            continue
    raise InboundIntakeBoxError("barcode_collision")


async def create_boxes_for_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request: InboundIntakeRequest,
    *,
    box_count: int,
) -> list[InboundIntakeBox]:
    if box_count < 1:
        return []
    existing = await list_boxes(session, tenant_id, request.id)
    if existing:
        if len(existing) == box_count:
            return existing
        raise InboundIntakeBoxError("boxes_already_exist")

    created: list[InboundIntakeBox] = []
    for num in range(1, box_count + 1):
        for _ in range(8):
            box = InboundIntakeBox(
                tenant_id=tenant_id,
                request_id=request.id,
                box_number=num,
                internal_barcode=_new_barcode(),
            )
            session.add(box)
            try:
                await session.flush()
            except IntegrityError:
                session.expunge(box)
                continue
            created.append(box)
            break
        else:
            raise InboundIntakeBoxError("barcode_collision")
    return created


async def list_boxes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> list[InboundIntakeBox]:
    stmt = (
        select(InboundIntakeBox)
        .where(
            InboundIntakeBox.tenant_id == tenant_id,
            InboundIntakeBox.request_id == request_id,
        )
        .order_by(InboundIntakeBox.box_number.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def list_boxes_with_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> list[InboundIntakeBox]:
    stmt = (
        select(InboundIntakeBox)
        .where(
            InboundIntakeBox.tenant_id == tenant_id,
            InboundIntakeBox.request_id == request_id,
        )
        .options(
            selectinload(InboundIntakeBox.lines).selectinload(InboundIntakeBoxLine.product),
        )
        .order_by(InboundIntakeBox.box_number.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().unique().all())


async def mark_box_label_printed(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    box_id: uuid.UUID,
) -> InboundIntakeBox:
    req = await session.get(InboundIntakeRequest, request_id)
    if req is None or req.tenant_id != tenant_id:
        raise InboundIntakeBoxError("request_not_found")
    if req.status not in BOX_STATUSES_AFTER_PRIMARY:
        raise InboundIntakeBoxError("bad_status")
    box = await session.get(InboundIntakeBox, box_id)
    if box is None or box.request_id != request_id or box.tenant_id != tenant_id:
        raise InboundIntakeBoxError("box_not_found")
    box.label_printed_at = datetime.now(UTC)
    await session.flush()
    stmt = (
        select(InboundIntakeBox)
        .where(InboundIntakeBox.id == box_id)
        .options(
            selectinload(InboundIntakeBox.lines).selectinload(InboundIntakeBoxLine.product),
        )
    )
    res = await session.execute(stmt)
    loaded = res.scalar_one_or_none()
    if loaded is None:
        raise InboundIntakeBoxError("box_not_found")
    return loaded


async def _get_request_for_intake(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID
) -> InboundIntakeRequest:
    req = await intake_svc.get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeBoxError("request_not_found")
    if req.status not in INTAKE_STATUSES:
        raise InboundIntakeBoxError("bad_status")
    return req


async def _open_box_for_request(
    session: AsyncSession, request_id: uuid.UUID
) -> InboundIntakeBox | None:
    stmt = select(InboundIntakeBox).where(
        InboundIntakeBox.request_id == request_id,
        InboundIntakeBox.intake_opened_at.is_not(None),
        InboundIntakeBox.intake_closed_at.is_(None),
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def _close_open_boxes(session: AsyncSession, request_id: uuid.UUID) -> None:
    open_box = await _open_box_for_request(session, request_id)
    if open_box is None:
        return
    open_box.intake_closed_at = datetime.now(UTC)
    await session.flush()


async def _barcode_index_for_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    req: InboundIntakeRequest,
) -> dict[str, uuid.UUID]:
    product_ids = {ln.product_id for ln in req.lines}
    if not product_ids:
        return {}
    stmt = select(Product).where(
        Product.tenant_id == tenant_id,
        Product.id.in_(product_ids),
    )
    res = await session.execute(stmt)
    products = list(res.scalars().all())
    idx: dict[str, uuid.UUID] = {}
    for p in products:
        key = p.sku_code.strip()
        if key:
            idx[key] = p.id
    if req.seller_id is not None:
        rows = await list_seller_wb_catalog_rows(session, tenant_id, req.seller_id)
        for r in rows:
            if r.product_id not in product_ids:
                continue
            for b in r.wb_barcodes:
                key = str(b).strip()
                if key:
                    idx[key] = r.product_id
            if r.wb_primary_barcode:
                k = r.wb_primary_barcode.strip()
                if k:
                    idx[k] = r.product_id
    return idx


async def _expected_qty(
    session: AsyncSession, request_id: uuid.UUID, product_id: uuid.UUID
) -> int:
    stmt = select(InboundIntakeLine).where(
        InboundIntakeLine.request_id == request_id,
        InboundIntakeLine.product_id == product_id,
    )
    res = await session.execute(stmt)
    ln = res.scalar_one_or_none()
    if ln is None:
        return 0
    return int(ln.expected_qty)


async def _total_in_other_boxes(
    session: AsyncSession,
    request_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    exclude_box_id: uuid.UUID,
) -> int:
    stmt = (
        select(func.coalesce(func.sum(InboundIntakeBoxLine.quantity), 0))
        .join(InboundIntakeBox, InboundIntakeBoxLine.box_id == InboundIntakeBox.id)
        .where(
            InboundIntakeBox.request_id == request_id,
            InboundIntakeBoxLine.product_id == product_id,
            InboundIntakeBox.id != exclude_box_id,
        )
    )
    res = await session.execute(stmt)
    return int(res.scalar_one())


async def _total_scanned_for_product(
    session: AsyncSession,
    request_id: uuid.UUID,
    product_id: uuid.UUID,
) -> int:
    stmt = (
        select(func.coalesce(func.sum(InboundIntakeBoxLine.quantity), 0))
        .join(InboundIntakeBox, InboundIntakeBoxLine.box_id == InboundIntakeBox.id)
        .where(
            InboundIntakeBox.request_id == request_id,
            InboundIntakeBoxLine.product_id == product_id,
        )
    )
    res = await session.execute(stmt)
    return int(res.scalar_one())


async def _product_recorded_in_boxes(
    session: AsyncSession,
    request_id: uuid.UUID,
    product_id: uuid.UUID,
) -> bool:
    """True if the SKU was explicitly entered in any box line (including quantity 0)."""
    stmt = (
        select(InboundIntakeBoxLine.id)
        .join(InboundIntakeBox, InboundIntakeBoxLine.box_id == InboundIntakeBox.id)
        .where(
            InboundIntakeBox.request_id == request_id,
            InboundIntakeBoxLine.product_id == product_id,
        )
        .limit(1)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none() is not None


async def _sync_line_actuals_from_box_totals(
    session: AsyncSession,
    req: InboundIntakeRequest,
) -> None:
    """During receiving: validate effective fact; keep actual_qty as loose-only component."""
    for ln in req.lines:
        recorded = await _product_recorded_in_boxes(session, req.id, ln.product_id)
        if not recorded:
            continue
        effective = await intake_svc.effective_actual_qty(
            session, req.id, ln, request_status=req.status
        )
        if ln.posted_qty > effective:
            raise InboundIntakeBoxError("actual_below_posted")
    if req.status == intake_svc.STATUS_SUBMITTED:
        for ln in req.lines:
            effective = await intake_svc.effective_actual_qty(
                session, req.id, ln, request_status=req.status
            )
            if effective > 0:
                req.status = intake_svc.STATUS_RECEIVING
                break


async def open_box_by_barcode(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    barcode: str,
) -> InboundIntakeBox:
    raw = barcode.strip().upper()
    if not raw:
        raise InboundIntakeBoxError("barcode_empty")

    await _get_request_for_intake(session, tenant_id, request_id)
    boxes = await list_boxes(session, tenant_id, request_id)
    if not boxes:
        raise InboundIntakeBoxError("boxes_missing")

    box = next((b for b in boxes if b.internal_barcode.upper() == raw), None)
    if box is None:
        raise InboundIntakeBoxError("box_not_found")
    if box.intake_closed_at is not None:
        raise InboundIntakeBoxError("box_closed")

    open_box = await _open_box_for_request(session, request_id)
    if open_box is not None:
        if open_box.id == box.id:
            return await _load_box(session, box.id)
        await _close_open_boxes(session, request_id)

    if box.intake_opened_at is None:
        box.intake_opened_at = datetime.now(UTC)
    await session.flush()
    await session.commit()
    return await _load_box(session, box.id)


async def scan_product_into_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    box_id: uuid.UUID,
    *,
    barcode: str,
) -> InboundIntakeBoxLine:
    raw = barcode.strip()
    if not raw:
        raise InboundIntakeBoxError("barcode_empty")

    req = await _get_request_for_intake(session, tenant_id, request_id)
    box = await session.get(InboundIntakeBox, box_id)
    if box is None or box.request_id != request_id or box.tenant_id != tenant_id:
        raise InboundIntakeBoxError("box_not_found")
    if box.intake_closed_at is not None:
        raise InboundIntakeBoxError("box_closed")
    if box.intake_opened_at is None:
        raise InboundIntakeBoxError("no_open_box")

    open_box = await _open_box_for_request(session, request_id)
    if open_box is None or open_box.id != box.id:
        raise InboundIntakeBoxError("no_open_box")

    idx = await _barcode_index_for_request(session, tenant_id, req)
    product_id = idx.get(raw) or idx.get(raw.upper())
    if product_id is None:
        raise InboundIntakeBoxError("barcode_unknown")

    expected = await _expected_qty(session, req.id, product_id)
    if expected <= 0:
        raise InboundIntakeBoxError("product_not_on_request")

    stmt = select(InboundIntakeBoxLine).where(
        InboundIntakeBoxLine.box_id == box_id,
        InboundIntakeBoxLine.product_id == product_id,
    )
    res = await session.execute(stmt)
    line = res.scalar_one_or_none()
    if line is None:
        line = InboundIntakeBoxLine(box_id=box_id, product_id=product_id, quantity=1)
        session.add(line)
    else:
        line.quantity = int(line.quantity) + 1

    await session.flush()
    req_loaded = await intake_svc.get_request(session, tenant_id, request_id)
    if req_loaded is None:
        raise InboundIntakeBoxError("request_not_found")
    await _sync_line_actuals_from_box_totals(session, req_loaded)
    await session.commit()

    stmt2 = (
        select(InboundIntakeBoxLine)
        .where(InboundIntakeBoxLine.id == line.id)
        .options(selectinload(InboundIntakeBoxLine.product))
    )
    res2 = await session.execute(stmt2)
    return res2.scalar_one()


async def set_product_quantity_in_open_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    box_id: uuid.UUID,
    *,
    product_id: uuid.UUID,
    quantity: int,
) -> InboundIntakeBox:
    if quantity < 0:
        raise InboundIntakeBoxError("invalid_qty")

    req = await _get_request_for_intake(session, tenant_id, request_id)
    box = await session.get(InboundIntakeBox, box_id)
    if box is None or box.request_id != request_id or box.tenant_id != tenant_id:
        raise InboundIntakeBoxError("box_not_found")
    if box.intake_closed_at is not None:
        raise InboundIntakeBoxError("box_closed")
    if box.intake_opened_at is None:
        raise InboundIntakeBoxError("no_open_box")

    open_box = await _open_box_for_request(session, request_id)
    if open_box is None or open_box.id != box.id:
        raise InboundIntakeBoxError("no_open_box")

    expected = await _expected_qty(session, req.id, product_id)
    if expected <= 0:
        raise InboundIntakeBoxError("product_not_on_request")

    stmt = select(InboundIntakeBoxLine).where(
        InboundIntakeBoxLine.box_id == box_id,
        InboundIntakeBoxLine.product_id == product_id,
    )
    res = await session.execute(stmt)
    line = res.scalar_one_or_none()
    if line is None:
        session.add(
            InboundIntakeBoxLine(
                box_id=box_id,
                product_id=product_id,
                quantity=quantity,
            )
        )
    else:
        line.quantity = quantity

    await session.flush()
    req_loaded = await intake_svc.get_request(session, tenant_id, request_id)
    if req_loaded is None:
        raise InboundIntakeBoxError("request_not_found")
    await _sync_line_actuals_from_box_totals(session, req_loaded)
    await session.commit()
    return await _load_box(session, box.id)


async def close_box_intake(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    box_id: uuid.UUID,
) -> InboundIntakeBox:
    await _get_request_for_intake(session, tenant_id, request_id)
    box = await session.get(InboundIntakeBox, box_id)
    if box is None or box.request_id != request_id or box.tenant_id != tenant_id:
        raise InboundIntakeBoxError("box_not_found")
    if box.intake_closed_at is not None:
        raise InboundIntakeBoxError("box_closed")
    if box.intake_opened_at is None:
        raise InboundIntakeBoxError("no_open_box")
    box.intake_closed_at = datetime.now(UTC)
    req_loaded = await intake_svc.get_request(session, tenant_id, request_id)
    if req_loaded is None:
        raise InboundIntakeBoxError("request_not_found")
    await _sync_line_actuals_from_box_totals(session, req_loaded)
    await session.commit()
    return await _load_box(session, box.id)


async def assert_no_open_intake_box(
    session: AsyncSession,
    request_id: uuid.UUID,
) -> None:
    if await _open_box_for_request(session, request_id) is not None:
        raise InboundIntakeBoxError("open_box_exists")


async def request_has_boxes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> bool:
    boxes = await list_boxes(session, tenant_id, request_id)
    return len(boxes) > 0


async def _load_box(session: AsyncSession, box_id: uuid.UUID) -> InboundIntakeBox:
    stmt = (
        select(InboundIntakeBox)
        .where(InboundIntakeBox.id == box_id)
        .options(
            selectinload(InboundIntakeBox.lines).selectinload(InboundIntakeBoxLine.product),
        )
    )
    res = await session.execute(stmt)
    box = res.scalar_one()
    return box
