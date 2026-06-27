from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inventory_reservation import InventoryReservation
from app.models.marketplace_unload import (
    MarketplaceUnloadBox,
    MarketplaceUnloadBoxLine,
    MarketplaceUnloadLine,
    MarketplaceUnloadPickAllocation,
    MarketplaceUnloadRequest,
)
from app.models.marketplace_unload_reservation import MarketplaceUnloadReservation
from app.models.outbound_shipment import OutboundShipmentLine, OutboundShipmentRequest
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.user import User
from app.services import inventory_service
from app.services.catalog_service import get_warehouse
from app.services.document_number_service import (
    DOC_TYPE_UNLOAD,
    assign_document_number_if_missing,
)
from app.services.wb_mp_warehouse_service import get_cached_mp_warehouse

STATUS_DRAFT = "draft"
STATUS_SUBMITTED = "submitted"
STATUS_CONFIRMED = "confirmed"
STATUS_SHIPPED = "shipped"
STATUS_CANCELLED = "cancelled"

RESERVE_STATUSES = (STATUS_SUBMITTED, STATUS_CONFIRMED)
CANCELLABLE_STATUSES = (STATUS_SUBMITTED, STATUS_CONFIRMED)
SELLER_EDITABLE_STATUSES = (STATUS_DRAFT,)
FF_LINE_EDITABLE_STATUSES = (STATUS_DRAFT, STATUS_CONFIRMED)


class MarketplaceUnloadError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def assert_request_visible(
    user: User,
    req: MarketplaceUnloadRequest,
    *,
    effective_seller_id: uuid.UUID | None = None,
) -> None:
    from app.core.roles import FULFILLMENT_SELLER

    seller_id = effective_seller_id if effective_seller_id is not None else user.seller_id
    if user.role == FULFILLMENT_SELLER and (
        seller_id is None or req.seller_id != seller_id
    ):
        raise MarketplaceUnloadError("not_found")


async def _sync_packaging_task_for_unload(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> None:
    from app.services import packaging_task_service as pkg_svc

    await pkg_svc.ensure_task_for_unload(session, tenant_id, request_id)


async def create_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID,
    seller_id: uuid.UUID,
    wb_mp_warehouse_id: int | None,
) -> MarketplaceUnloadRequest:
    wh = await get_warehouse(session, tenant_id, warehouse_id)
    if wh is None:
        raise MarketplaceUnloadError("warehouse_not_found")
    sl = await session.get(Seller, seller_id)
    if sl is None or sl.tenant_id != tenant_id:
        raise MarketplaceUnloadError("seller_not_found")
    if wb_mp_warehouse_id is not None:
        mpw = await get_cached_mp_warehouse(session, tenant_id, wb_mp_warehouse_id)
        if mpw is None:
            raise MarketplaceUnloadError("wb_mp_warehouse_unknown")
    req = MarketplaceUnloadRequest(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        seller_id=seller_id,
        wb_mp_warehouse_id=wb_mp_warehouse_id,
        status=STATUS_DRAFT,
        ff_modified=False,
    )
    session.add(req)
    await assign_document_number_if_missing(session, tenant_id, DOC_TYPE_UNLOAD, req)
    await session.commit()
    await session.refresh(req)
    from app.services.notification_trigger_service import notify_ff_marketplace_unload_created

    await notify_ff_marketplace_unload_created(session, req)
    await session.commit()
    await _sync_packaging_task_for_unload(session, tenant_id, req.id)
    return req


FF_DATE_EDITABLE_STATUSES = (STATUS_DRAFT, STATUS_SUBMITTED, STATUS_CONFIRMED)


async def set_wb_mp_warehouse(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    wb_mp_warehouse_id: int,
) -> MarketplaceUnloadRequest:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadError("not_found")
    if req.status not in SELLER_EDITABLE_STATUSES:
        raise MarketplaceUnloadError("not_editable")
    mpw = await get_cached_mp_warehouse(session, tenant_id, wb_mp_warehouse_id)
    if mpw is None:
        raise MarketplaceUnloadError("wb_mp_warehouse_unknown")
    req.wb_mp_warehouse_id = wb_mp_warehouse_id
    await session.commit()
    r2 = await get_request(session, tenant_id, request_id)
    assert r2 is not None
    return r2


async def patch_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    user: User,
    wb_mp_warehouse_id: int | None = None,
    planned_shipment_date: date | None = None,
    set_planned_shipment_date: bool = False,
) -> MarketplaceUnloadRequest:
    from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER

    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadError("not_found")
    assert_request_visible(user, req)

    if wb_mp_warehouse_id is not None:
        if req.status not in SELLER_EDITABLE_STATUSES:
            raise MarketplaceUnloadError("not_editable")
        if user.role == FULFILLMENT_SELLER and req.status != STATUS_DRAFT:
            raise MarketplaceUnloadError("not_editable")
        mpw = await get_cached_mp_warehouse(session, tenant_id, wb_mp_warehouse_id)
        if mpw is None:
            raise MarketplaceUnloadError("wb_mp_warehouse_unknown")
        req.wb_mp_warehouse_id = wb_mp_warehouse_id

    if set_planned_shipment_date:
        if user.role == FULFILLMENT_SELLER:
            if req.status not in SELLER_EDITABLE_STATUSES:
                raise MarketplaceUnloadError("not_editable")
        elif user.role == FULFILLMENT_ADMIN:
            if req.status not in FF_DATE_EDITABLE_STATUSES:
                raise MarketplaceUnloadError("not_editable")
        else:
            raise MarketplaceUnloadError("forbidden")
        req.planned_shipment_date = planned_shipment_date

    await session.commit()
    r2 = await get_request(session, tenant_id, request_id)
    assert r2 is not None
    return r2


async def get_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> MarketplaceUnloadRequest | None:
    stmt = (
        select(MarketplaceUnloadRequest)
        .where(MarketplaceUnloadRequest.id == request_id)
        .where(MarketplaceUnloadRequest.tenant_id == tenant_id)
        .options(
            selectinload(MarketplaceUnloadRequest.warehouse),
            selectinload(MarketplaceUnloadRequest.seller),
            selectinload(MarketplaceUnloadRequest.lines).selectinload(
                MarketplaceUnloadLine.product
            ),
            selectinload(MarketplaceUnloadRequest.lines).selectinload(
                MarketplaceUnloadLine.reservation
            ),
            selectinload(MarketplaceUnloadRequest.boxes)
            .selectinload(MarketplaceUnloadBox.lines)
            .selectinload(MarketplaceUnloadBoxLine.product),
            selectinload(MarketplaceUnloadRequest.boxes).selectinload(
                MarketplaceUnloadBox.warehouse_box
            ),
            selectinload(MarketplaceUnloadRequest.pick_allocations).selectinload(
                MarketplaceUnloadPickAllocation.product
            ),
            selectinload(MarketplaceUnloadRequest.pick_allocations).selectinload(
                MarketplaceUnloadPickAllocation.storage_location
            ),
        )
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def list_requests(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None = None,
) -> list[MarketplaceUnloadRequest]:
    stmt = (
        select(MarketplaceUnloadRequest)
        .where(MarketplaceUnloadRequest.tenant_id == tenant_id)
        .options(
            selectinload(MarketplaceUnloadRequest.warehouse),
            selectinload(MarketplaceUnloadRequest.seller),
            selectinload(MarketplaceUnloadRequest.lines),
        )
        .order_by(MarketplaceUnloadRequest.created_at.desc())
    )
    if seller_id is not None:
        stmt = stmt.where(MarketplaceUnloadRequest.seller_id == seller_id)
    res = await session.execute(stmt)
    return list(res.scalars().unique().all())


async def _mp_reserved_qty_for_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    exclude_request_id: uuid.UUID | None = None,
) -> int:
    stmt = (
        select(func.coalesce(func.sum(MarketplaceUnloadReservation.quantity), 0))
        .join(
            MarketplaceUnloadLine,
            MarketplaceUnloadLine.id
            == MarketplaceUnloadReservation.marketplace_unload_line_id,
        )
        .join(
            MarketplaceUnloadRequest,
            MarketplaceUnloadRequest.id == MarketplaceUnloadLine.request_id,
        )
        .where(
            MarketplaceUnloadReservation.tenant_id == tenant_id,
            MarketplaceUnloadReservation.warehouse_id == warehouse_id,
            MarketplaceUnloadReservation.product_id == product_id,
            MarketplaceUnloadRequest.status.in_(RESERVE_STATUSES),
        )
    )
    if exclude_request_id is not None:
        stmt = stmt.where(MarketplaceUnloadRequest.id != exclude_request_id)
    return int(await session.scalar(stmt) or 0)


async def _available_product_qty_in_warehouse(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    exclude_request_id: uuid.UUID | None = None,
) -> int:
    on_hand = await inventory_service.storage_on_hand_in_warehouse(
        session, tenant_id, warehouse_id, product_id
    )
    reserved_outbound_stmt = (
        select(func.coalesce(func.sum(InventoryReservation.quantity), 0))
        .join(
            OutboundShipmentLine,
            OutboundShipmentLine.id == InventoryReservation.outbound_shipment_line_id,
        )
        .join(
            OutboundShipmentRequest,
            OutboundShipmentRequest.id == OutboundShipmentLine.request_id,
        )
        .outerjoin(
            StorageLocation,
            StorageLocation.id == InventoryReservation.storage_location_id,
        )
        .where(
            InventoryReservation.tenant_id == tenant_id,
            InventoryReservation.product_id == product_id,
            OutboundShipmentRequest.status.in_(("draft", "submitted")),
            or_(
                and_(
                    InventoryReservation.storage_location_id.isnot(None),
                    StorageLocation.tenant_id == tenant_id,
                    StorageLocation.warehouse_id == warehouse_id,
                ),
                and_(
                    InventoryReservation.storage_location_id.is_(None),
                    InventoryReservation.warehouse_id == warehouse_id,
                ),
            ),
        )
    )
    reserved_outbound = int(await session.scalar(reserved_outbound_stmt) or 0)
    reserved_mp = await _mp_reserved_qty_for_product(
        session,
        tenant_id,
        warehouse_id,
        product_id,
        exclude_request_id=exclude_request_id,
    )
    return on_hand - reserved_outbound - reserved_mp


async def _release_reservations(session: AsyncSession, request_id: uuid.UUID) -> None:
    line_ids_stmt = select(MarketplaceUnloadLine.id).where(
        MarketplaceUnloadLine.request_id == request_id
    )
    res = await session.execute(line_ids_stmt)
    line_ids = [row[0] for row in res.all()]
    if not line_ids:
        return
    await session.execute(
        delete(MarketplaceUnloadReservation).where(
            MarketplaceUnloadReservation.marketplace_unload_line_id.in_(line_ids)
        )
    )


async def _apply_reservations(session: AsyncSession, req: MarketplaceUnloadRequest) -> None:
    await _release_reservations(session, req.id)
    for ln in req.lines:
        session.add(
            MarketplaceUnloadReservation(
                tenant_id=req.tenant_id,
                marketplace_unload_line_id=ln.id,
                product_id=ln.product_id,
                warehouse_id=req.warehouse_id,
                quantity=int(ln.quantity),
            )
        )


async def add_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    product_id: uuid.UUID,
    quantity: int,
    allow_ff_confirmed: bool = False,
) -> MarketplaceUnloadLine:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadError("not_found")
    editable = SELLER_EDITABLE_STATUSES if not allow_ff_confirmed else FF_LINE_EDITABLE_STATUSES
    if req.status not in editable:
        raise MarketplaceUnloadError("not_editable")
    prod = await session.get(Product, product_id)
    if prod is None or prod.tenant_id != tenant_id:
        raise MarketplaceUnloadError("product_not_found")
    if req.seller_id is not None and prod.seller_id != req.seller_id:
        raise MarketplaceUnloadError("product_seller_mismatch")
    available_qty = await _available_product_qty_in_warehouse(
        session,
        tenant_id,
        req.warehouse_id,
        product_id,
        exclude_request_id=req.id if req.status in RESERVE_STATUSES else None,
    )
    if available_qty < quantity:
        raise MarketplaceUnloadError("insufficient_available")
    line = MarketplaceUnloadLine(
        request_id=req.id,
        product_id=product_id,
        quantity=quantity,
    )
    session.add(line)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise MarketplaceUnloadError("duplicate_line") from None
    if allow_ff_confirmed and req.status == STATUS_CONFIRMED:
        req.ff_modified = True
    await session.commit()
    await session.refresh(line, attribute_names=["product"])
    await _sync_packaging_task_for_unload(session, tenant_id, request_id)
    return line


async def replace_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    lines: list[tuple[uuid.UUID, int]],
) -> MarketplaceUnloadRequest:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadError("not_found")
    if req.status != STATUS_DRAFT:
        raise MarketplaceUnloadError("not_editable")

    normalized: dict[uuid.UUID, int] = {}
    for product_id, qty in lines:
        if qty < 1:
            continue
        normalized[product_id] = normalized.get(product_id, 0) + qty

    for product_id, qty in normalized.items():
        available_qty = await _available_product_qty_in_warehouse(
            session, tenant_id, req.warehouse_id, product_id
        )
        if available_qty < qty:
            raise MarketplaceUnloadError("insufficient_available")

    for ln in list(req.lines):
        await session.delete(ln)
    await session.flush()

    for product_id, qty in normalized.items():
        prod = await session.get(Product, product_id)
        if prod is None or prod.tenant_id != tenant_id:
            raise MarketplaceUnloadError("product_not_found")
        if req.seller_id is not None and prod.seller_id != req.seller_id:
            raise MarketplaceUnloadError("product_seller_mismatch")
        session.add(
            MarketplaceUnloadLine(
                request_id=req.id,
                product_id=product_id,
                quantity=qty,
            )
        )
    await session.commit()
    await _sync_packaging_task_for_unload(session, tenant_id, request_id)
    r2 = await get_request(session, tenant_id, request_id)
    assert r2 is not None
    return r2


async def plan_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> MarketplaceUnloadRequest:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadError("not_found")
    if req.status != STATUS_DRAFT:
        raise MarketplaceUnloadError("bad_status")
    if req.wb_mp_warehouse_id is None:
        raise MarketplaceUnloadError("wb_mp_warehouse_required")
    if not req.lines:
        raise MarketplaceUnloadError("no_lines")
    if req.planned_shipment_date is None:
        raise MarketplaceUnloadError("planned_shipment_date_required")
    mpw = await get_cached_mp_warehouse(session, tenant_id, int(req.wb_mp_warehouse_id))
    if mpw is None:
        raise MarketplaceUnloadError("wb_mp_warehouse_unknown")
    for ln in req.lines:
        available_qty = await _available_product_qty_in_warehouse(
            session,
            tenant_id,
            req.warehouse_id,
            ln.product_id,
            exclude_request_id=req.id,
        )
        if available_qty < ln.quantity:
            raise MarketplaceUnloadError("insufficient_available")
    await _apply_reservations(session, req)
    req.status = STATUS_SUBMITTED
    await session.commit()
    r2 = await get_request(session, tenant_id, request_id)
    assert r2 is not None
    return r2


async def unplan_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> MarketplaceUnloadRequest:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadError("not_found")
    if req.status != STATUS_SUBMITTED:
        raise MarketplaceUnloadError("bad_status")
    await _release_reservations(session, req.id)
    req.status = STATUS_DRAFT
    await session.commit()
    r2 = await get_request(session, tenant_id, request_id)
    assert r2 is not None
    return r2


async def confirm_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    planned_shipment_date: date | None = None,
) -> MarketplaceUnloadRequest:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadError("not_found")
    if req.status not in (STATUS_DRAFT, STATUS_SUBMITTED):
        raise MarketplaceUnloadError("bad_status")
    if req.wb_mp_warehouse_id is None:
        raise MarketplaceUnloadError("wb_mp_warehouse_required")
    if not req.lines:
        raise MarketplaceUnloadError("no_lines")
    mpw = await get_cached_mp_warehouse(session, tenant_id, int(req.wb_mp_warehouse_id))
    if mpw is None:
        raise MarketplaceUnloadError("wb_mp_warehouse_unknown")
    effective_date = (
        planned_shipment_date
        if planned_shipment_date is not None
        else req.planned_shipment_date
    )
    if effective_date is None:
        raise MarketplaceUnloadError("planned_shipment_date_required")
    if req.status == STATUS_DRAFT:
        for ln in req.lines:
            available_qty = await _available_product_qty_in_warehouse(
                session,
                tenant_id,
                req.warehouse_id,
                ln.product_id,
                exclude_request_id=req.id,
            )
            if available_qty < ln.quantity:
                raise MarketplaceUnloadError("insufficient_available")
        await _apply_reservations(session, req)
    req.planned_shipment_date = effective_date
    req.status = STATUS_CONFIRMED
    await session.commit()

    from app.services import packaging_task_service as pkg_svc

    await pkg_svc.ensure_task_for_unload(session, tenant_id, request_id)

    r2 = await get_request(session, tenant_id, request_id)
    assert r2 is not None
    return r2


async def submit_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> MarketplaceUnloadRequest:
    """Legacy alias: FF confirms from draft or submitted."""
    return await confirm_request(session, tenant_id, request_id)


async def release_reservations_for_shipped(
    session: AsyncSession, request_id: uuid.UUID
) -> None:
    await _release_reservations(session, request_id)


async def reduce_reservation_for_collect(
    session: AsyncSession,
    request_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: int,
) -> None:
    """DEC-016: collect_into_box reduces warehouse reserve alongside on_hand deduct."""
    if quantity < 1:
        return
    stmt = (
        select(MarketplaceUnloadReservation)
        .join(
            MarketplaceUnloadLine,
            MarketplaceUnloadLine.id
            == MarketplaceUnloadReservation.marketplace_unload_line_id,
        )
        .where(
            MarketplaceUnloadLine.request_id == request_id,
            MarketplaceUnloadReservation.product_id == product_id,
            MarketplaceUnloadReservation.quantity > 0,
        )
        .with_for_update()
    )
    res = await session.execute(stmt)
    remaining = quantity
    for reservation in res.scalars().all():
        if remaining < 1:
            break
        take = min(int(reservation.quantity), remaining)
        reservation.quantity = int(reservation.quantity) - take
        remaining -= take


async def restore_reservation_for_remove(
    session: AsyncSession,
    request_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: int,
    *,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
) -> None:
    """DEC-016: remove-from-box restores warehouse reserve."""
    if quantity < 1:
        return
    line_stmt = select(MarketplaceUnloadLine).where(
        MarketplaceUnloadLine.request_id == request_id,
        MarketplaceUnloadLine.product_id == product_id,
    )
    line_res = await session.execute(line_stmt)
    unload_line = line_res.scalar_one_or_none()
    if unload_line is None:
        return
    res_stmt = (
        select(MarketplaceUnloadReservation)
        .where(
            MarketplaceUnloadReservation.marketplace_unload_line_id == unload_line.id,
        )
        .with_for_update()
    )
    res_row = await session.execute(res_stmt)
    reservation = res_row.scalar_one_or_none()
    if reservation is None:
        reservation = MarketplaceUnloadReservation(
            tenant_id=tenant_id,
            marketplace_unload_line_id=unload_line.id,
            product_id=product_id,
            warehouse_id=warehouse_id,
            quantity=0,
        )
        session.add(reservation)
        await session.flush()
    reservation.quantity = int(reservation.quantity) + quantity


async def delete_empty_boxes_for_ship(
    session: AsyncSession, req: MarketplaceUnloadRequest
) -> None:
    """DEC-002: empty boxes (no lines) are removed when shipment is posted."""
    for box in list(req.boxes):
        if not box.lines:
            await session.delete(box)


async def cancel_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> MarketplaceUnloadRequest:
    """TASK-019 / DEC-016: abandon unload before ship — restore box stock and clear reserves."""
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadError("not_found")
    if req.status not in CANCELLABLE_STATUSES:
        raise MarketplaceUnloadError("bad_status")

    from app.services import marketplace_unload_collect_service as collect_svc

    await collect_svc.rollback_all_collected_for_cancel(
        session, tenant_id, req.warehouse_id, request_id
    )
    await _release_reservations(session, request_id)
    req.status = STATUS_CANCELLED
    await session.commit()
    r2 = await get_request(session, tenant_id, request_id)
    assert r2 is not None
    return r2


async def delete_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    *,
    allow_ff_confirmed: bool = False,
) -> None:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadError("not_found")
    editable = SELLER_EDITABLE_STATUSES if not allow_ff_confirmed else FF_LINE_EDITABLE_STATUSES
    if req.status not in editable:
        raise MarketplaceUnloadError("not_editable")
    line = await session.get(MarketplaceUnloadLine, line_id)
    if line is None or line.request_id != request_id:
        raise MarketplaceUnloadError("line_not_found")
    await session.delete(line)
    if allow_ff_confirmed and req.status == STATUS_CONFIRMED:
        req.ff_modified = True
    await session.commit()
    await _sync_packaging_task_for_unload(session, tenant_id, request_id)
