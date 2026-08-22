from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, StrictInt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_packaging_access
from app.db.session import get_db
from app.models.fbs_order import MARKING_KIND_SGTIN, current_order_marking
from app.models.packaging_task import (
    PACKAGING_EVENT_PRODUCT_LABEL_PRINT,
    PackagingTask,
    PackagingTaskLine,
)
from app.models.seller import Seller
from app.models.user import User
from app.services import marking_code_service as mc_svc
from app.services import packaging_task_service as pkg_svc

router = APIRouter(
    prefix="/operations/packaging-tasks",
    tags=["operations"],
)


class PackagingTaskLineIn(BaseModel):
    product_id: uuid.UUID
    storage_location_id: uuid.UUID | None = None
    quantity: StrictInt = Field(ge=1, le=1_000_000_000)


class PackagingTaskCreate(BaseModel):
    warehouse_id: uuid.UUID
    lines: list[PackagingTaskLineIn] = Field(min_length=1)
    inbound_intake_request_id: uuid.UUID | None = None


class ConfirmPackedIn(BaseModel):
    quantity: StrictInt | None = Field(default=None, ge=0, le=1_000_000_000)


class PrepackedExternalIn(BaseModel):
    quantity: StrictInt = Field(ge=1, le=1_000_000_000)


class PackProgressIn(BaseModel):
    quantity: StrictInt = Field(ge=1, le=1_000_000_000)
    order_id: uuid.UUID | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class ScanPackIn(BaseModel):
    barcode: str = Field(min_length=1, max_length=128)


class CompletePackagingIn(BaseModel):
    acknowledge_all_packed: bool = False


class ProductLabelPrintedIn(BaseModel):
    quantity: StrictInt = Field(ge=1, le=1_000_000_000)


class FulfilledOrderOut(BaseModel):
    id: str
    wb_order_id: int
    pack_status: str
    marking_status: str | None = None
    sticker_status: str


class PackProgressOut(BaseModel):
    packaging_task: PackagingTaskOut
    fulfilled_order: FulfilledOrderOut | None = None
    warnings: list[str] | None = None


class PackagingTaskLineOut(BaseModel):
    id: str
    product_id: str
    seller_id: str | None = None
    seller_name: str | None = None
    sku_code: str
    product_name: str
    storage_location_id: str
    storage_location_code: str
    packaging_instructions: str | None
    requires_honest_sign: bool
    qty_total: int
    qty_suggested_packed: int
    qty_confirmed_packed: int
    qty_need_pack: int
    qty_packed_in_task: int
    qty_done: int
    qty_marking_printed: int
    qty_marking_external: int
    qty_product_label_printed: int
    marking_available_count: int = 0
    is_complete: bool


class PackagingTaskEventOut(BaseModel):
    id: str
    event_sequence: int
    action: str
    line_id: str | None = None
    product_id: str | None = None
    product_name: str | None = None
    storage_location_id: str | None = None
    storage_location_code: str | None = None
    quantity: int
    note: str | None = None
    created_by_user_id: str | None = None
    created_by_user_email: str | None = None
    created_at: str
    reversed_at: str | None = None


class PackagingTaskOut(BaseModel):
    id: str
    document_number: str | None = None
    display_number: str | None = None
    warehouse_id: str
    warehouse_name: str | None = None
    warehouse_code: str | None = None
    seller_id: str | None = None
    seller_name: str | None = None
    status: str
    marketplace_unload_request_id: str | None
    inbound_intake_request_id: str | None
    is_complete: bool
    pick_resync_warning: bool = False
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    completed_by_user_id: str | None = None
    lines: list[PackagingTaskLineOut]
    events: list[PackagingTaskEventOut] = Field(default_factory=list)


def _line_out(
    ln: PackagingTaskLine,
    *,
    seller_names: dict[uuid.UUID, str],
    marking_available: int = 0,
    product_label_printed: int = 0,
) -> PackagingTaskLineOut:
    p = ln.product
    loc = ln.storage_location
    seller_name = seller_names.get(p.seller_id) if p.seller_id else None
    return PackagingTaskLineOut(
        id=str(ln.id),
        product_id=str(ln.product_id),
        seller_id=str(p.seller_id) if p.seller_id else None,
        seller_name=seller_name,
        sku_code=p.sku_code,
        product_name=p.name,
        storage_location_id=str(ln.storage_location_id),
        storage_location_code=loc.code,
        packaging_instructions=p.packaging_instructions,
        requires_honest_sign=bool(p.requires_honest_sign),
        qty_total=int(ln.qty_total),
        qty_suggested_packed=int(ln.qty_suggested_packed),
        qty_confirmed_packed=int(ln.qty_confirmed_packed),
        qty_need_pack=pkg_svc.qty_need_pack(ln),
        qty_packed_in_task=int(ln.qty_packed_in_task),
        qty_done=pkg_svc.qty_done(ln),
        qty_marking_printed=int(ln.qty_marking_printed),
        qty_marking_external=int(ln.qty_marking_external),
        qty_product_label_printed=product_label_printed,
        marking_available_count=marking_available,
        is_complete=pkg_svc.is_line_complete(ln),
    )


def _event_out(event: object) -> PackagingTaskEventOut:
    from app.models.packaging_task import PackagingTaskEvent

    assert isinstance(event, PackagingTaskEvent)
    return PackagingTaskEventOut(
        id=str(event.id),
        event_sequence=int(event.event_sequence),
        action=event.action,
        line_id=str(event.line_id) if event.line_id else None,
        product_id=str(event.product_id) if event.product_id else None,
        product_name=event.product.name if event.product else None,
        storage_location_id=str(event.storage_location_id) if event.storage_location_id else None,
        storage_location_code=event.storage_location.code if event.storage_location else None,
        quantity=int(event.quantity),
        note=event.note,
        created_by_user_id=str(event.created_by_user_id) if event.created_by_user_id else None,
        created_by_user_email=event.created_by_user.email if event.created_by_user else None,
        created_at=event.created_at.isoformat(),
        reversed_at=event.reversed_at.isoformat() if event.reversed_at else None,
    )


async def _task_out(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task: PackagingTask,
    *,
    pick_resync_warning: bool = False,
    reload: bool = True,
) -> PackagingTaskOut:
    if reload:
        loaded = await pkg_svc.get_task(session, tenant_id, task.id)
        if loaded is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
        task = loaded
    seller_ids = {ln.product.seller_id for ln in task.lines if ln.product.seller_id}
    seller_names: dict[uuid.UUID, str] = {}
    if seller_ids:
        seller_rows = (
            await session.execute(
                select(Seller.id, Seller.name).where(
                    Seller.tenant_id == tenant_id,
                    Seller.id.in_(seller_ids),
                )
            )
        ).all()
        seller_names = {seller_id: name for seller_id, name in seller_rows}
    product_label_printed_by_line: dict[uuid.UUID, int] = {}
    for event in task.events:
        if event.action != PACKAGING_EVENT_PRODUCT_LABEL_PRINT or event.line_id is None:
            continue
        if event.reversed_at is not None:
            continue
        product_label_printed_by_line[event.line_id] = (
            product_label_printed_by_line.get(event.line_id, 0) + int(event.quantity)
        )
    line_outs: list[PackagingTaskLineOut] = []
    for ln in task.lines:
        available = 0
        if ln.product.requires_honest_sign:
            available = await mc_svc.count_available_for_product(
                session, tenant_id, ln.product_id
            )
        line_outs.append(
            _line_out(
                ln,
                seller_names=seller_names,
                marking_available=available,
                product_label_printed=product_label_printed_by_line.get(ln.id, 0),
            )
        )
    sellers: set[tuple[uuid.UUID | None, str | None]] = set()
    for ln in task.lines:
        line_seller_id = ln.product.seller_id
        sellers.add(
            (
                line_seller_id,
                seller_names.get(line_seller_id) if line_seller_id else None,
            )
        )
    seller_id: str | None = None
    seller_name: str | None = None
    if len(sellers) == 1:
        only_id, only_name = next(iter(sellers))
        seller_id = str(only_id) if only_id else None
        seller_name = only_name
    elif len(sellers) > 1:
        seller_name = "Несколько селлеров"
    return PackagingTaskOut(
        id=str(task.id),
        document_number=task.document_number,
        display_number=task.display_number,
        warehouse_id=str(task.warehouse_id),
        warehouse_name=task.warehouse.name if task.warehouse else None,
        warehouse_code=task.warehouse.code if task.warehouse else None,
        seller_id=seller_id,
        seller_name=seller_name,
        status=task.status,
        marketplace_unload_request_id=(
            str(task.marketplace_unload_request_id)
            if task.marketplace_unload_request_id
            else None
        ),
        inbound_intake_request_id=(
            str(task.inbound_intake_request_id) if task.inbound_intake_request_id else None
        ),
        is_complete=pkg_svc.is_task_complete(task),
        pick_resync_warning=pick_resync_warning,
        created_at=task.created_at.isoformat() if task.created_at else None,
        updated_at=task.updated_at.isoformat() if task.updated_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        completed_by_user_id=(
            str(task.completed_by_user_id) if task.completed_by_user_id else None
        ),
        lines=line_outs,
        events=[_event_out(event) for event in task.events],
    )


def _http_from_pkg_error(exc: pkg_svc.PackagingTaskServiceError) -> HTTPException:
    code = exc.code
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    if code == "not_found":
        status_code = status.HTTP_404_NOT_FOUND
    elif code in {
        "order_not_picked",
        "order_already_packed",
        "order_not_in_supply",
        "order_product_mismatch",
        "no_eligible_order",
        "fbs_acknowledge_not_allowed",
        "mixed_seller",
        "unknown_barcode",
        "line_already_packed",
        "undo_not_available",
        "undo_not_supported",
        "insufficient_packaging_stock",
    }:
        status_code = status.HTTP_409_CONFLICT
    detail: object = code
    if exc.message:
        detail = {"code": code, "message": exc.message}
    return HTTPException(status_code=status_code, detail=detail)


def _fulfilled_order_out(order: object) -> FulfilledOrderOut:
    from app.models.fbs_order import FbsOrder

    assert isinstance(order, FbsOrder)
    marking_status: str | None = None
    marking = current_order_marking(
        list(order.markings),
        MARKING_KIND_SGTIN,
        include_rejected=True,
    )
    if marking is not None:
        marking_status = marking.meta_status
    return FulfilledOrderOut(
        id=str(order.id),
        wb_order_id=int(order.wb_order_id),
        pack_status=order.pack_status,
        marking_status=marking_status,
        sticker_status=order.sticker_status,
    )


@router.get("", response_model=list[PackagingTaskOut])
async def list_packaging_tasks(
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    warehouse_id: Annotated[uuid.UUID | None, Query()] = None,
    status_filter: Annotated[str, Query(alias="status")] = "open",
    search: Annotated[str | None, Query(max_length=128)] = None,
) -> list[PackagingTaskOut]:
    try:
        tasks = await pkg_svc.list_tasks(
            session,
            user.tenant_id,
            warehouse_id=warehouse_id,
            status_filter=status_filter,
            search=search,
        )
    except pkg_svc.PackagingTaskServiceError as exc:
        raise _http_from_pkg_error(exc) from exc
    out: list[PackagingTaskOut] = []
    for t in tasks:
        out.append(await _task_out(session, user.tenant_id, t))
    return out


@router.post("", response_model=PackagingTaskOut, status_code=status.HTTP_201_CREATED)
async def create_packaging_task(
    body: PackagingTaskCreate,
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PackagingTaskOut:
    try:
        task = await pkg_svc.create_manual_task(
            session,
            user.tenant_id,
            warehouse_id=body.warehouse_id,
            lines=[
                (ln.product_id, ln.storage_location_id, ln.quantity) for ln in body.lines
            ],
            inbound_intake_request_id=body.inbound_intake_request_id,
            created_by_user_id=user.id,
        )
    except pkg_svc.PackagingTaskServiceError as exc:
        raise _http_from_pkg_error(exc) from exc
    return await _task_out(session, user.tenant_id, task)


@router.get("/by-unload/{unload_id}", response_model=PackagingTaskOut)
async def get_packaging_task_for_unload(
    unload_id: uuid.UUID,
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PackagingTaskOut:
    task = await pkg_svc.get_task_for_unload(session, user.tenant_id, unload_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    synced = await pkg_svc.sync_lines_from_pick_allocations(session, user.tenant_id, task)
    task = await pkg_svc.sync_mp_task_packed_from_boxes(session, user.tenant_id, synced.task)
    await session.commit()
    return await _task_out(
        session,
        user.tenant_id,
        task,
        pick_resync_warning=task.pick_resync_warning,
    )


@router.get("/{task_id}", response_model=PackagingTaskOut)
async def get_packaging_task(
    task_id: uuid.UUID,
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PackagingTaskOut:
    task = await pkg_svc.get_task(session, user.tenant_id, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    pick_warning = task.pick_resync_warning
    if task.marketplace_unload_request_id is not None:
        synced = await pkg_svc.sync_lines_from_pick_allocations(
            session, user.tenant_id, task
        )
        task = await pkg_svc.sync_mp_task_packed_from_boxes(
            session, user.tenant_id, synced.task
        )
        await session.commit()
        pick_warning = task.pick_resync_warning
    return await _task_out(session, user.tenant_id, task, pick_resync_warning=pick_warning)


@router.post("/{task_id}/cancel", response_model=PackagingTaskOut)
async def cancel_packaging_task(
    task_id: uuid.UUID,
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PackagingTaskOut:
    try:
        task = await pkg_svc.cancel_task(
            session,
            user.tenant_id,
            task_id,
            acting_user_id=user.id,
        )
    except pkg_svc.PackagingTaskServiceError as exc:
        raise _http_from_pkg_error(exc) from exc
    return await _task_out(session, user.tenant_id, task)


@router.post("/{task_id}/lines/{line_id}/confirm-packed", response_model=PackagingTaskOut)
async def confirm_packed_from_shelf(
    task_id: uuid.UUID,
    line_id: uuid.UUID,
    body: ConfirmPackedIn,
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PackagingTaskOut:
    try:
        task = await pkg_svc.confirm_line_packed_from_shelf(
            session,
            user.tenant_id,
            task_id,
            line_id,
            qty=body.quantity,
            acting_user_id=user.id,
        )
    except pkg_svc.PackagingTaskServiceError as exc:
        raise _http_from_pkg_error(exc) from exc
    return await _task_out(session, user.tenant_id, task)


@router.post("/{task_id}/lines/{line_id}/mark-prepacked", response_model=PackagingTaskOut)
async def mark_line_prepacked_external(
    task_id: uuid.UUID,
    line_id: uuid.UUID,
    body: PrepackedExternalIn,
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PackagingTaskOut:
    try:
        task = await pkg_svc.mark_line_prepacked_external(
            session,
            user.tenant_id,
            task_id,
            line_id,
            body.quantity,
            acting_user_id=user.id,
        )
    except pkg_svc.PackagingTaskServiceError as exc:
        raise _http_from_pkg_error(exc) from exc
    return await _task_out(session, user.tenant_id, task)


@router.post("/{task_id}/lines/{line_id}/pack", response_model=PackProgressOut)
async def record_pack_progress(
    task_id: uuid.UUID,
    line_id: uuid.UUID,
    body: PackProgressIn,
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PackProgressOut:
    try:
        result = await pkg_svc.record_pack_progress(
            session,
            user.tenant_id,
            task_id,
            line_id,
            body.quantity,
            acting_user_id=user.id,
            order_id=body.order_id,
            idempotency_key=body.idempotency_key,
        )
    except pkg_svc.PackagingTaskServiceError as exc:
        raise _http_from_pkg_error(exc) from exc
    fulfilled_order: FulfilledOrderOut | None = None
    if result.fulfilled_order is not None:
        from app.models.fbs_order import FbsOrder

        order = result.fulfilled_order
        if isinstance(order, FbsOrder):
            await session.refresh(order, attribute_names=["markings"])
            fulfilled_order = _fulfilled_order_out(order)
    return PackProgressOut(
        packaging_task=await _task_out(session, user.tenant_id, result.task),
        fulfilled_order=fulfilled_order,
        warnings=result.warnings if result.warnings else None,
    )


@router.post("/{task_id}/scan", response_model=PackProgressOut)
async def record_pack_scan(
    task_id: uuid.UUID,
    body: ScanPackIn,
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PackProgressOut:
    try:
        result = await pkg_svc.record_pack_scan(
            session,
            user.tenant_id,
            task_id,
            body.barcode,
            acting_user_id=user.id,
        )
    except pkg_svc.PackagingTaskServiceError as exc:
        raise _http_from_pkg_error(exc) from exc
    return PackProgressOut(
        packaging_task=await _task_out(
            session, user.tenant_id, result.task, reload=False
        ),
        fulfilled_order=None,
    )


@router.post(
    "/{task_id}/lines/{line_id}/product-label-printed",
    response_model=PackagingTaskOut,
)
async def mark_product_label_printed(
    task_id: uuid.UUID,
    line_id: uuid.UUID,
    body: ProductLabelPrintedIn,
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PackagingTaskOut:
    try:
        task = await pkg_svc.mark_product_label_printed(
            session,
            user.tenant_id,
            task_id,
            line_id,
            quantity=body.quantity,
            acting_user_id=user.id,
        )
    except pkg_svc.PackagingTaskServiceError as exc:
        raise _http_from_pkg_error(exc) from exc
    return await _task_out(session, user.tenant_id, task)


@router.post("/{task_id}/undo-last", response_model=PackagingTaskOut)
async def undo_last_pack_action(
    task_id: uuid.UUID,
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PackagingTaskOut:
    try:
        task = await pkg_svc.undo_last_pack_action(
            session,
            user.tenant_id,
            task_id,
            acting_user_id=user.id,
        )
    except pkg_svc.PackagingTaskServiceError as exc:
        raise _http_from_pkg_error(exc) from exc
    return await _task_out(session, user.tenant_id, task)


@router.post("/{task_id}/complete", response_model=PackagingTaskOut)
async def complete_packaging_task(
    task_id: uuid.UUID,
    body: CompletePackagingIn,
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PackagingTaskOut:
    try:
        task = await pkg_svc.complete_task(
            session,
            user.tenant_id,
            task_id,
            acknowledge_all_packed=body.acknowledge_all_packed,
            acting_user_id=user.id,
        )
    except pkg_svc.PackagingTaskServiceError as exc:
        raise _http_from_pkg_error(exc) from exc
    return await _task_out(session, user.tenant_id, task)
