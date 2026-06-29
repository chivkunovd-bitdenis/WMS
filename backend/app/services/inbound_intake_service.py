from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeBoxLine,
    InboundIntakeDistributionLine,
    InboundIntakeLine,
    InboundIntakeRequest,
)
from app.models.inventory_movement import MOVEMENT_TYPE_INBOUND_INTAKE
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.services import inventory_service as inv_svc
from app.services import sorting_location_service as sorting_loc_svc
from app.services.catalog_service import (
    get_storage_location_in_warehouse,
    get_warehouse,
)
from app.services.document_number_service import (
    DOC_TYPE_INBOUND,
    assign_document_number_if_missing,
)

STATUS_DRAFT = "draft"
STATUS_SUBMITTED = "submitted"
STATUS_RECEIVING = "receiving"
STATUS_SORTING = "sorting"
STATUS_DONE = "done"

# Collapsed legacy names (same values — IN-BE-03 updates API labels)
STATUS_PRIMARY_ACCEPTED = STATUS_RECEIVING
STATUS_VERIFYING = STATUS_RECEIVING
STATUS_VERIFIED = STATUS_SORTING
STATUS_POSTED = STATUS_DONE

RECEIVING_STATUSES = frozenset({STATUS_RECEIVING})
SORTING_STATUSES = frozenset({STATUS_SORTING})
DONE_STATUSES = frozenset({STATUS_DONE})


class InboundIntakeError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _loose_qty(line: InboundIntakeLine) -> int:
    """General (non-box) intake quantity; default 0 — never falls back to expected."""
    return line.actual_qty if line.actual_qty is not None else 0


async def _box_total_for_product(
    session: AsyncSession,
    request_id: uuid.UUID,
    product_id: uuid.UUID,
) -> int:
    stmt = (
        select(sa.func.coalesce(sa.func.sum(InboundIntakeBoxLine.quantity), 0))
        .join(InboundIntakeBox, InboundIntakeBoxLine.box_id == InboundIntakeBox.id)
        .where(
            InboundIntakeBox.request_id == request_id,
            InboundIntakeBoxLine.product_id == product_id,
        )
    )
    res = await session.execute(stmt)
    return int(res.scalar_one())


async def effective_actual_qty(
    session: AsyncSession,
    request_id: uuid.UUID,
    line: InboundIntakeLine,
) -> int:
    """Accepted fact = loose intake + sum of box lines for the product."""
    box_total = await _box_total_for_product(session, request_id, line.product_id)
    loose = _loose_qty(line)
    if box_total <= 0:
        return loose
    if loose > box_total:
        return loose + box_total
    if loose < box_total:
        return box_total + loose
    return box_total


def _accepted_qty_for_line(line: InboundIntakeLine) -> int:
    """Accepted quantity for sorting/posting; default 0 — never falls back to expected."""
    return line.actual_qty if line.actual_qty is not None else 0


async def sync_request_actuals_from_boxes(
    session: AsyncSession,
    req: InboundIntakeRequest,
) -> None:
    """Validate posted qty against loose + boxes; does not overwrite loose intake."""
    for ln in req.lines:
        total = await effective_actual_qty(session, req.id, ln)
        if ln.posted_qty > total:
            raise InboundIntakeError("actual_below_posted")


async def create_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID,
    seller_id: uuid.UUID | None = None,
    planned_delivery_date: date | None = None,
) -> InboundIntakeRequest:
    wh = await get_warehouse(session, tenant_id, warehouse_id)
    if wh is None:
        raise InboundIntakeError("warehouse_not_found")
    if seller_id is not None:
        sl = await session.get(Seller, seller_id)
        if sl is None or sl.tenant_id != tenant_id:
            raise InboundIntakeError("seller_not_found")
    req = InboundIntakeRequest(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        status=STATUS_DRAFT,
        seller_id=seller_id,
        planned_delivery_date=planned_delivery_date,
        planned_box_count=None,
    )
    session.add(req)
    await assign_document_number_if_missing(
        session, tenant_id, DOC_TYPE_INBOUND, req
    )
    await session.commit()
    reloaded = await get_request(session, tenant_id, req.id)
    if reloaded is None:
        raise InboundIntakeError("request_not_found")
    if seller_id is not None:
        from app.services.notification_trigger_service import notify_ff_inbound_created

        await notify_ff_inbound_created(session, reloaded)
        await session.commit()
    return reloaded


async def list_requests(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_product_owner_id: uuid.UUID | None = None,
) -> list[InboundIntakeRequest]:
    stmt = (
        select(InboundIntakeRequest)
        .where(InboundIntakeRequest.tenant_id == tenant_id)
        .options(
            selectinload(InboundIntakeRequest.lines),
            selectinload(InboundIntakeRequest.seller),
            selectinload(InboundIntakeRequest.boxes),
        )
        .order_by(InboundIntakeRequest.created_at.desc())
    )
    if seller_product_owner_id is not None:
        stmt = stmt.where(
            InboundIntakeRequest.seller_id == seller_product_owner_id,
        )
    res = await session.execute(stmt)
    return list(res.scalars().unique().all())


async def get_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    seller_product_owner_id: uuid.UUID | None = None,
) -> InboundIntakeRequest | None:
    stmt = (
        select(InboundIntakeRequest)
        .where(
            InboundIntakeRequest.id == request_id,
            InboundIntakeRequest.tenant_id == tenant_id,
        )
        .options(
            selectinload(InboundIntakeRequest.seller),
            selectinload(InboundIntakeRequest.lines).options(
                selectinload(InboundIntakeLine.product),
                selectinload(InboundIntakeLine.storage_location),
            ),
            selectinload(InboundIntakeRequest.boxes).options(
                selectinload(InboundIntakeBox.lines).selectinload(
                    InboundIntakeBoxLine.product
                ),
            ),
        )
    )
    res = await session.execute(stmt)
    req = res.scalar_one_or_none()
    if req is None:
        return None
    if (
        seller_product_owner_id is not None
        and req.seller_id != seller_product_owner_id
    ):
        return None
    return req


async def _line_on_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
) -> tuple[InboundIntakeRequest, InboundIntakeLine] | None:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        return None
    for ln in req.lines:
        if ln.id == line_id:
            return req, ln
    return None


async def add_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    product_id: uuid.UUID,
    expected_qty: int,
    storage_location_id: uuid.UUID | None = None,
    seller_product_owner_id: uuid.UUID | None = None,
) -> InboundIntakeLine:
    if expected_qty < 1:
        raise InboundIntakeError("invalid_qty")
    req = await get_request(
        session,
        tenant_id,
        request_id,
        seller_product_owner_id=seller_product_owner_id,
    )
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status != STATUS_DRAFT:
        raise InboundIntakeError("not_draft")
    prod_stmt = select(Product).where(
        Product.id == product_id,
        Product.tenant_id == tenant_id,
    )
    prod_res = await session.execute(prod_stmt)
    product = prod_res.scalar_one_or_none()
    if product is None:
        raise InboundIntakeError("product_not_found")
    if (
        seller_product_owner_id is not None
        and product.seller_id != seller_product_owner_id
    ):
        raise InboundIntakeError("product_seller_mismatch")
    if req.seller_id is None:
        req.seller_id = product.seller_id
    elif product.seller_id != req.seller_id:
        raise InboundIntakeError("mixed_seller_lines")
    loc_id: uuid.UUID | None = None
    if storage_location_id is not None:
        loc = await get_storage_location_in_warehouse(
            session, tenant_id, req.warehouse_id, storage_location_id
        )
        if loc is None:
            raise InboundIntakeError("location_not_found")
        if sorting_loc_svc.is_sorting_location(loc):
            raise InboundIntakeError("sorting_location_reserved")
        loc_id = storage_location_id
    line = InboundIntakeLine(
        request_id=request_id,
        product_id=product_id,
        expected_qty=expected_qty,
        posted_qty=0,
        storage_location_id=loc_id,
    )
    session.add(line)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise InboundIntakeError("duplicate_line") from exc
    await session.refresh(line)
    return line


async def update_line_expected_qty(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    *,
    expected_qty: int,
    seller_product_owner_id: uuid.UUID | None = None,
) -> InboundIntakeLine:
    if expected_qty < 1:
        raise InboundIntakeError("invalid_qty")
    pair = await _line_on_request(session, tenant_id, request_id, line_id)
    if pair is None:
        raise InboundIntakeError("line_not_found")
    req, line = pair
    if seller_product_owner_id is not None and req.seller_id != seller_product_owner_id:
        raise InboundIntakeError("line_not_found")
    if req.status != STATUS_DRAFT:
        raise InboundIntakeError("not_draft")
    if line.posted_qty != 0:
        raise InboundIntakeError("line_already_posted")
    line.expected_qty = expected_qty
    await session.commit()
    await session.refresh(line)
    return line


async def delete_draft_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    *,
    seller_product_owner_id: uuid.UUID | None = None,
) -> None:
    pair = await _line_on_request(session, tenant_id, request_id, line_id)
    if pair is None:
        raise InboundIntakeError("line_not_found")
    req, line = pair
    if seller_product_owner_id is not None and req.seller_id != seller_product_owner_id:
        raise InboundIntakeError("line_not_found")
    if req.status != STATUS_DRAFT:
        raise InboundIntakeError("not_draft")
    if line.posted_qty != 0:
        raise InboundIntakeError("line_already_posted")
    await session.delete(line)
    await session.commit()


async def patch_request_draft(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    planned_delivery_date: date | None = None,
    planned_delivery_date_set: bool = False,
    planned_box_count: int | None = None,
    planned_box_count_set: bool = False,
    seller_product_owner_id: uuid.UUID | None = None,
) -> InboundIntakeRequest:
    req = await get_request(
        session,
        tenant_id,
        request_id,
        seller_product_owner_id=seller_product_owner_id,
    )
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status != STATUS_DRAFT:
        raise InboundIntakeError("not_draft")
    if planned_delivery_date_set:
        req.planned_delivery_date = planned_delivery_date
    if planned_box_count_set:
        if planned_box_count is not None and planned_box_count < 1:
            raise InboundIntakeError("invalid_planned_box_count")
        req.planned_box_count = planned_box_count
    await session.commit()
    await session.refresh(req)
    return req


async def patch_request_planned_delivery(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    planned_delivery_date: date | None,
    seller_product_owner_id: uuid.UUID | None = None,
) -> InboundIntakeRequest:
    return await patch_request_draft(
        session,
        tenant_id,
        request_id,
        planned_delivery_date=planned_delivery_date,
        planned_delivery_date_set=True,
        seller_product_owner_id=seller_product_owner_id,
    )


async def set_line_storage_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    *,
    storage_location_id: uuid.UUID,
) -> InboundIntakeLine:
    pair = await _line_on_request(session, tenant_id, request_id, line_id)
    if pair is None:
        raise InboundIntakeError("line_not_found")
    req, line = pair
    if req.status not in (
        STATUS_DRAFT,
        STATUS_SUBMITTED,
        *RECEIVING_STATUSES,
        *SORTING_STATUSES,
    ):
        raise InboundIntakeError("not_editable")
    if (
        req.status in SORTING_STATUSES | DONE_STATUSES
        and line.posted_qty >= _accepted_qty_for_line(line)
    ):
        raise InboundIntakeError("line_closed")
    loc = await get_storage_location_in_warehouse(
        session, tenant_id, req.warehouse_id, storage_location_id
    )
    if loc is None:
        raise InboundIntakeError("location_not_found")
    if sorting_loc_svc.is_sorting_location(loc):
        raise InboundIntakeError("sorting_location_reserved")
    line.storage_location_id = storage_location_id
    await session.commit()
    await session.refresh(line)
    return line


async def submit_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    seller_product_owner_id: uuid.UUID | None = None,
) -> InboundIntakeRequest:
    req = await get_request(
        session,
        tenant_id,
        request_id,
        seller_product_owner_id=seller_product_owner_id,
    )
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status != STATUS_DRAFT:
        raise InboundIntakeError("not_draft")
    if len(req.lines) == 0:
        raise InboundIntakeError("submit_empty")
    req.status = STATUS_SUBMITTED
    req.submitted_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(req)
    return req


def _maybe_complete_request(req: InboundIntakeRequest) -> None:
    if req.status != STATUS_SORTING:
        return
    if all(ln.posted_qty >= _accepted_qty_for_line(ln) for ln in req.lines):
        req.status = STATUS_DONE
        if req.posted_at is None:
            req.posted_at = datetime.now(UTC)


async def primary_accept_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    actual_box_count: int | None = None,
) -> InboundIntakeRequest:
    """Start receiving (legacy primary-accept entry point; no auto-box creation)."""
    if actual_box_count is not None and actual_box_count < 0:
        raise InboundIntakeError("invalid_actual_box_count")
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status != STATUS_SUBMITTED:
        raise InboundIntakeError("not_submitted")
    if actual_box_count is not None:
        req.actual_box_count = actual_box_count
        if req.planned_box_count is not None:
            req.boxes_discrepancy = actual_box_count != req.planned_box_count
    req.status = STATUS_RECEIVING
    req.primary_accepted_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(req)
    return req


async def begin_receiving(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> InboundIntakeRequest:
    return await primary_accept_request(
        session, tenant_id, request_id, actual_box_count=None
    )


async def set_line_actual_qty(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    *,
    actual_qty: int,
) -> InboundIntakeLine:
    if actual_qty < 0:
        raise InboundIntakeError("invalid_qty")
    pair = await _line_on_request(session, tenant_id, request_id, line_id)
    if pair is None:
        raise InboundIntakeError("line_not_found")
    req, line = pair
    if req.status == STATUS_SUBMITTED:
        req.status = STATUS_RECEIVING
        req.primary_accepted_at = datetime.now(UTC)
    elif req.status not in RECEIVING_STATUSES:
        raise InboundIntakeError("not_verifying")
    if line.posted_qty > actual_qty:
        raise InboundIntakeError("actual_below_posted")
    line.actual_qty = actual_qty
    await session.commit()
    await session.refresh(line)
    return line


async def complete_receiving(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> InboundIntakeRequest:
    from app.services import inbound_intake_box_service as inbound_box_svc

    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status not in RECEIVING_STATUSES:
        raise InboundIntakeError("not_verifying")
    try:
        await inbound_box_svc.assert_no_open_intake_box(session, request_id)
    except inbound_box_svc.InboundIntakeBoxError as exc:
        if exc.code == "open_box_exists":
            raise InboundIntakeError("open_box_exists") from None
        raise
    await sync_request_actuals_from_boxes(session, req)
    line_discrepancy = False
    for line in req.lines:
        effective = await effective_actual_qty(session, req.id, line)
        line.actual_qty = effective
        if effective != line.expected_qty:
            line_discrepancy = True
    req.has_discrepancy = bool(req.boxes_discrepancy) or line_discrepancy
    req.status = STATUS_SORTING
    req.verified_at = datetime.now(UTC)
    sorting_loc = await sorting_loc_svc.get_or_create_sorting_location(
        session, tenant_id, req.warehouse_id
    )
    for line in req.lines:
        qty = _accepted_qty_for_line(line)
        if qty < 1:
            continue
        await inv_svc.apply_inbound_receive(
            session,
            tenant_id=tenant_id,
            product_id=line.product_id,
            storage_location_id=sorting_loc.id,
            quantity=qty,
            movement_type=MOVEMENT_TYPE_INBOUND_INTAKE,
            inbound_intake_line_id=line.id,
        )
    await session.commit()
    await session.refresh(req)
    return req


async def complete_verification(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> InboundIntakeRequest:
    """Legacy alias for complete_receiving."""
    return await complete_receiving(session, tenant_id, request_id)


async def receive_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    *,
    quantity: int,
) -> InboundIntakeRequest:
    pair = await _line_on_request(session, tenant_id, request_id, line_id)
    if pair is None:
        raise InboundIntakeError("line_not_found")
    req, line = pair
    if req.status == STATUS_DONE:
        raise InboundIntakeError("already_posted")
    if req.status != STATUS_SORTING:
        raise InboundIntakeError("not_verified")
    accepted = _accepted_qty_for_line(line)
    remaining = accepted - line.posted_qty
    if remaining <= 0:
        raise InboundIntakeError("nothing_to_receive")
    if line.storage_location_id is None:
        raise InboundIntakeError("storage_not_assigned")
    if quantity < 1 or quantity > remaining:
        raise InboundIntakeError("invalid_qty")
    target_loc = await session.get(StorageLocation, line.storage_location_id)
    if target_loc is None or sorting_loc_svc.is_sorting_location(target_loc):
        raise InboundIntakeError("sorting_location_reserved")
    sorting_loc = await sorting_loc_svc.get_or_create_sorting_location(
        session, tenant_id, req.warehouse_id
    )
    await inv_svc.apply_putaway_from_sorting(
        session,
        tenant_id,
        from_storage_location_id=sorting_loc.id,
        to_storage_location_id=line.storage_location_id,
        product_id=line.product_id,
        quantity=quantity,
        inbound_intake_line_id=line.id,
    )
    line.posted_qty += quantity
    _maybe_complete_request(req)
    await session.commit()
    await session.refresh(req)
    return req


async def post_all_remaining(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> InboundIntakeRequest:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status == STATUS_DONE:
        raise InboundIntakeError("already_posted")
    if req.status != STATUS_SORTING:
        raise InboundIntakeError("not_verified")
    sorting_loc = await sorting_loc_svc.get_or_create_sorting_location(
        session, tenant_id, req.warehouse_id
    )
    to_receive: list[tuple[InboundIntakeLine, int]] = []
    for line in req.lines:
        accepted = _accepted_qty_for_line(line)
        rem = accepted - line.posted_qty
        if rem <= 0:
            continue
        if line.storage_location_id is None:
            raise InboundIntakeError("lines_missing_storage")
        target_loc = await session.get(StorageLocation, line.storage_location_id)
        if target_loc is None or sorting_loc_svc.is_sorting_location(target_loc):
            raise InboundIntakeError("sorting_location_reserved")
        to_receive.append((line, rem))
    if not to_receive:
        raise InboundIntakeError("nothing_to_receive")
    for line, rem in to_receive:
        sid = line.storage_location_id
        assert sid is not None
        await inv_svc.apply_putaway_from_sorting(
            session,
            tenant_id,
            from_storage_location_id=sorting_loc.id,
            to_storage_location_id=sid,
            product_id=line.product_id,
            quantity=rem,
            inbound_intake_line_id=line.id,
        )
        line.posted_qty += rem
    _maybe_complete_request(req)
    await session.commit()
    await session.refresh(req)
    return req


def sorting_remaining_qty(req: InboundIntakeRequest) -> int:
    """Сколько штук ещё не разложено по ячейкам хранения (остаётся в зоне сортировки)."""
    if req.status != STATUS_SORTING:
        return 0
    total = 0
    for ln in req.lines:
        accepted = _accepted_qty_for_line(ln)
        total += max(0, accepted - ln.posted_qty)
    return total


def box_line_remaining_qty(box_line: InboundIntakeBoxLine) -> int:
    return max(0, int(box_line.quantity) - int(box_line.posted_qty))


def box_remaining_qty(box: InboundIntakeBox) -> int:
    return sum(box_line_remaining_qty(ln) for ln in box.lines)


def _box_remainder_total_for_product(
    req: InboundIntakeRequest,
    product_id: uuid.UUID,
) -> int:
    total = 0
    for box in req.boxes:
        for bl in box.lines:
            if bl.product_id == product_id:
                total += box_line_remaining_qty(bl)
    return total


def _loose_pool_for_product(
    req: InboundIntakeRequest,
    product_id: uuid.UUID,
    accepted: int,
) -> int:
    """Portion of accepted qty not tied to open box remainders (rosyp / loose)."""
    return max(0, accepted - _box_remainder_total_for_product(req, product_id))


def _box_lines_by_key(
    req: InboundIntakeRequest,
) -> dict[tuple[uuid.UUID, uuid.UUID], InboundIntakeBoxLine]:
    out: dict[tuple[uuid.UUID, uuid.UUID], InboundIntakeBoxLine] = {}
    for box in req.boxes:
        for bl in box.lines:
            out[(box.id, bl.product_id)] = bl
    return out


def _maybe_set_distribution_completed(req: InboundIntakeRequest) -> None:
    if req.status != STATUS_SORTING:
        return
    if (
        all(
            _accepted_qty_for_line(ln) <= 0 or ln.posted_qty >= _accepted_qty_for_line(ln)
            for ln in req.lines
        )
        and req.distribution_completed_at is None
    ):
        req.distribution_completed_at = datetime.now(UTC)


async def _get_box_for_putaway(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    box_id: uuid.UUID,
) -> tuple[InboundIntakeRequest, InboundIntakeBox]:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status != STATUS_SORTING:
        raise InboundIntakeError("not_distributable")
    box = await session.get(InboundIntakeBox, box_id)
    if box is None or box.request_id != request_id or box.tenant_id != tenant_id:
        raise InboundIntakeError("box_not_found")
    if box.intake_closed_at is None:
        raise InboundIntakeError("box_not_closed")
    stmt = (
        select(InboundIntakeBox)
        .where(InboundIntakeBox.id == box_id)
        .options(selectinload(InboundIntakeBox.lines).selectinload(InboundIntakeBoxLine.product))
    )
    res = await session.execute(stmt)
    loaded = res.scalar_one()
    return req, loaded


async def _top_up_sorting_for_putaway(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    sorting_location_id: uuid.UUID,
    line: InboundIntakeLine,
    product_id: uuid.UUID,
    qty: int,
) -> None:
    """Служебный буфер: перед разкладкой в ячейку гарантируем остаток по строке заявки."""
    accepted = _accepted_qty_for_line(line)
    pool = max(0, accepted - line.posted_qty)
    if qty > pool:
        raise InboundIntakeError("qty_exceeds_accepted")
    avail = await inv_svc.available_quantity_at_location(
        session, tenant_id, product_id, sorting_location_id
    )
    if avail >= qty:
        return
    shortfall = min(qty - avail, max(0, pool - avail))
    if shortfall < 1:
        raise InboundIntakeError("qty_exceeds_accepted")
    await inv_svc.apply_inbound_receive(
        session,
        tenant_id=tenant_id,
        product_id=product_id,
        storage_location_id=sorting_location_id,
        quantity=shortfall,
        movement_type=MOVEMENT_TYPE_INBOUND_INTAKE,
        inbound_intake_line_id=line.id,
    )


async def apply_box_putaway(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    box_id: uuid.UUID,
    *,
    storage_location_id: uuid.UUID,
    line_items: list[tuple[uuid.UUID, int]] | None = None,
) -> InboundIntakeRequest:
    """
    Разложить принятый по заявке товар из короба в ячейку хранения.

    line_items: (product_id, qty); None — весь остаток по коробу.
    """
    from app.services import inbound_intake_box_service as inbound_box_svc

    req, box = await _get_box_for_putaway(session, tenant_id, request_id, box_id)

    if await inbound_box_svc.request_has_boxes(session, tenant_id, request_id):
        await sync_request_actuals_from_boxes(session, req)

    loc = await get_storage_location_in_warehouse(
        session, tenant_id, req.warehouse_id, storage_location_id
    )
    if loc is None:
        raise InboundIntakeError("location_not_found")
    if sorting_loc_svc.is_sorting_location(loc):
        raise InboundIntakeError("sorting_location_reserved")

    if line_items is None:
        line_items = [
            (bl.product_id, box_line_remaining_qty(bl))
            for bl in box.lines
            if box_line_remaining_qty(bl) > 0
        ]
    if not line_items:
        raise InboundIntakeError("nothing_to_putaway")

    lines_by_product = {ln.product_id: ln for ln in req.lines}
    box_lines_by_product = {bl.product_id: bl for bl in box.lines}
    sorting_loc = await sorting_loc_svc.get_or_create_sorting_location(
        session, tenant_id, req.warehouse_id
    )

    for product_id, qty in line_items:
        if qty < 1:
            raise InboundIntakeError("invalid_qty")
        bl = box_lines_by_product.get(product_id)
        if bl is None:
            raise InboundIntakeError("product_not_in_box")
        if qty > box_line_remaining_qty(bl):
            raise InboundIntakeError("qty_exceeds_box_remaining")
        line = lines_by_product.get(product_id)
        if line is None:
            raise InboundIntakeError("product_not_on_request")
        accepted = _accepted_qty_for_line(line)
        if accepted <= 0:
            raise InboundIntakeError("product_not_accepted")
        if line.posted_qty + qty > accepted:
            raise InboundIntakeError("qty_exceeds_accepted")

        await _top_up_sorting_for_putaway(
            session, tenant_id, sorting_loc.id, line, product_id, qty
        )

        try:
            await inv_svc.apply_putaway_from_sorting(
                session,
                tenant_id,
                from_storage_location_id=sorting_loc.id,
                to_storage_location_id=storage_location_id,
                product_id=product_id,
                quantity=qty,
                inbound_intake_line_id=line.id,
            )
        except ValueError as exc:
            if str(exc) == "insufficient stock":
                raise InboundIntakeError("qty_exceeds_accepted") from None
            raise
        line.posted_qty += qty
        bl.posted_qty += qty
        session.add(
            InboundIntakeDistributionLine(
                request_id=request_id,
                product_id=product_id,
                storage_location_id=storage_location_id,
                quantity=qty,
                box_id=box_id,
            )
        )

    _maybe_set_distribution_completed(req)
    _maybe_complete_request(req)
    await session.commit()
    reloaded = await get_request(session, tenant_id, request_id)
    if reloaded is None:
        raise InboundIntakeError("request_not_found")
    return reloaded


async def resync_sorting_stock_for_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> InboundIntakeRequest:
    """
    Довести остаток в зоне «Сортировка» до (принято - уже разложено) по каждому SKU.

    Нужно, если пересчёт делали до закрытия всех коробов или остаток в сортировке разъехался.
    """
    from app.services import inbound_intake_box_service as inbound_box_svc

    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status != STATUS_SORTING:
        raise InboundIntakeError("not_distributable")
    if await inbound_box_svc.request_has_boxes(session, tenant_id, request_id):
        await sync_request_actuals_from_boxes(session, req)

    sorting_loc = await sorting_loc_svc.get_or_create_sorting_location(
        session, tenant_id, req.warehouse_id
    )
    for line in req.lines:
        accepted = _accepted_qty_for_line(line)
        if accepted <= 0:
            continue
        need = max(0, accepted - line.posted_qty)
        if need <= 0:
            continue
        await _top_up_sorting_for_putaway(
            session,
            tenant_id,
            sorting_loc.id,
            line,
            line.product_id,
            need,
        )
    await session.commit()
    reloaded = await get_request(session, tenant_id, request_id)
    if reloaded is None:
        raise InboundIntakeError("request_not_found")
    return reloaded


async def list_distribution_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> list[InboundIntakeDistributionLine]:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    stmt = (
        select(InboundIntakeDistributionLine)
        .where(InboundIntakeDistributionLine.request_id == request_id)
        .order_by(InboundIntakeDistributionLine.created_at, InboundIntakeDistributionLine.id)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def replace_distribution_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    lines: list[tuple[uuid.UUID | None, uuid.UUID, uuid.UUID, int]],
) -> list[InboundIntakeDistributionLine]:
    """
    Полностью заменяет строки распределения (черновик).

    lines: список (box_id | None, product_id, storage_location_id, quantity).
    """
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.distribution_completed_at is not None:
        raise InboundIntakeError("distribution_completed")
    if req.status != STATUS_SORTING:
        raise InboundIntakeError("not_distributable")

    box_lines_by_key = _box_lines_by_key(req)

    accepted_by_product: dict[uuid.UUID, int] = {}
    for ln in req.lines:
        accepted_by_product[ln.product_id] = _accepted_qty_for_line(ln)

    sum_by_product: dict[uuid.UUID, int] = {}
    sum_by_box_product: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
    sum_loose_by_product: dict[uuid.UUID, int] = {}
    for box_id, product_id, storage_location_id, qty in lines:
        if qty < 1:
            raise InboundIntakeError("invalid_qty")
        accepted = accepted_by_product.get(product_id)
        if accepted is None:
            raise InboundIntakeError("product_not_on_request")
        if accepted <= 0:
            raise InboundIntakeError("product_not_accepted")
        if box_id is not None:
            box_line = box_lines_by_key.get((box_id, product_id))
            if box_line is None:
                raise InboundIntakeError("product_not_in_box")
            next_box_sum = sum_by_box_product.get((box_id, product_id), 0) + qty
            if next_box_sum > box_line_remaining_qty(box_line):
                raise InboundIntakeError("qty_exceeds_box_remaining")
            sum_by_box_product[(box_id, product_id)] = next_box_sum
        else:
            next_loose_sum = sum_loose_by_product.get(product_id, 0) + qty
            if next_loose_sum > _loose_pool_for_product(req, product_id, accepted):
                raise InboundIntakeError("qty_exceeds_accepted")
            sum_loose_by_product[product_id] = next_loose_sum
        loc = await get_storage_location_in_warehouse(
            session, tenant_id, req.warehouse_id, storage_location_id
        )
        if loc is None:
            raise InboundIntakeError("location_not_found")
        if sorting_loc_svc.is_sorting_location(loc):
            raise InboundIntakeError("sorting_location_reserved")
        next_sum = sum_by_product.get(product_id, 0) + qty
        if next_sum > accepted:
            raise InboundIntakeError("qty_exceeds_accepted")
        sum_by_product[product_id] = next_sum

    await session.execute(
        sa.delete(InboundIntakeDistributionLine).where(
            InboundIntakeDistributionLine.request_id == request_id
        )
    )
    for box_id, product_id, storage_location_id, qty in lines:
        session.add(
            InboundIntakeDistributionLine(
                request_id=request_id,
                product_id=product_id,
                storage_location_id=storage_location_id,
                quantity=qty,
                box_id=box_id,
            )
        )
    await session.commit()
    return await list_distribution_lines(session, tenant_id, request_id)


async def complete_distribution(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> InboundIntakeRequest:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status != STATUS_SORTING:
        raise InboundIntakeError("not_distributable")

    # Safety net: validate saved distribution lines against accepted quantities
    # right before locking. Even though PUT validates, this protects against races
    # and inconsistent states.
    accepted_by_product: dict[uuid.UUID, int] = {}
    lines_by_product: dict[uuid.UUID, InboundIntakeLine] = {}
    for ln in req.lines:
        accepted_by_product[ln.product_id] = _accepted_qty_for_line(ln)
        lines_by_product[ln.product_id] = ln

    stmt = select(InboundIntakeDistributionLine).where(
        InboundIntakeDistributionLine.request_id == request_id
    )
    res = await session.execute(stmt)
    rows = list(res.scalars().all())

    if not rows:
        raise InboundIntakeError("distribution_incomplete")

    box_lines_by_key = _box_lines_by_key(req)

    sorting_loc = await sorting_loc_svc.get_or_create_sorting_location(
        session, tenant_id, req.warehouse_id
    )

    sum_by_product: dict[uuid.UUID, int] = {}
    sum_by_box_product: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
    sum_loose_by_product: dict[uuid.UUID, int] = {}
    for r in rows:
        if r.quantity < 1:
            raise InboundIntakeError("invalid_qty")
        accepted = accepted_by_product.get(r.product_id)
        if accepted is None:
            raise InboundIntakeError("product_not_on_request")
        if accepted <= 0:
            raise InboundIntakeError("product_not_accepted")
        if r.box_id is not None:
            box_line = box_lines_by_key.get((r.box_id, r.product_id))
            if box_line is None:
                raise InboundIntakeError("product_not_in_box")
            next_box_sum = sum_by_box_product.get((r.box_id, r.product_id), 0) + r.quantity
            if next_box_sum > box_line_remaining_qty(box_line):
                raise InboundIntakeError("qty_exceeds_box_remaining")
            sum_by_box_product[(r.box_id, r.product_id)] = next_box_sum
        else:
            next_loose_sum = sum_loose_by_product.get(r.product_id, 0) + r.quantity
            if next_loose_sum > _loose_pool_for_product(req, r.product_id, accepted):
                raise InboundIntakeError("qty_exceeds_accepted")
            sum_loose_by_product[r.product_id] = next_loose_sum
        target_loc = await session.get(StorageLocation, r.storage_location_id)
        if target_loc is None or target_loc.tenant_id != tenant_id:
            raise InboundIntakeError("location_not_found")
        if sorting_loc_svc.is_sorting_location(target_loc):
            raise InboundIntakeError("sorting_location_reserved")
        sum_by_product[r.product_id] = sum_by_product.get(r.product_id, 0) + r.quantity
        line = lines_by_product[r.product_id]
        if max(line.posted_qty, sum_by_product[r.product_id]) > accepted:
            raise InboundIntakeError("qty_exceeds_accepted")

    distributed_before_by_product: dict[uuid.UUID, int] = {}
    for r in rows:
        line = lines_by_product[r.product_id]
        distributed_before = distributed_before_by_product.get(r.product_id, 0)
        distributed_after = distributed_before + r.quantity
        distributed_before_by_product[r.product_id] = distributed_after
        quantity_to_post = min(
            r.quantity,
            max(0, distributed_after - line.posted_qty),
        )
        if quantity_to_post < 1:
            continue
        if r.box_id is not None:
            bl = box_lines_by_key[(r.box_id, r.product_id)]
            quantity_to_post = min(quantity_to_post, box_line_remaining_qty(bl))
            if quantity_to_post < 1:
                continue
        await inv_svc.apply_putaway_from_sorting(
            session,
            tenant_id,
            from_storage_location_id=sorting_loc.id,
            to_storage_location_id=r.storage_location_id,
            product_id=r.product_id,
            quantity=quantity_to_post,
            inbound_intake_line_id=line.id,
        )
        line.posted_qty += quantity_to_post
        if r.box_id is not None:
            bl = box_lines_by_key[(r.box_id, r.product_id)]
            bl.posted_qty += quantity_to_post

    _maybe_set_distribution_completed(req)
    _maybe_complete_request(req)
    await session.commit()
    await session.refresh(req)
    return req


async def reopen_distribution(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> InboundIntakeRequest:
    """Снять фиксацию распределения, если оприходование ещё не выполнялось."""
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status != STATUS_SORTING:
        raise InboundIntakeError("not_reopenable")
    if req.distribution_completed_at is None:
        raise InboundIntakeError("distribution_not_completed")
    if any(ln.posted_qty > 0 for ln in req.lines):
        raise InboundIntakeError("already_posted_partial")
    req.distribution_completed_at = None
    await session.commit()
    reloaded = await get_request(session, tenant_id, request_id)
    if reloaded is None:
        raise InboundIntakeError("request_not_found")
    return reloaded
