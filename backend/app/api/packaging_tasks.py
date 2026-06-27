from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_packaging_access
from app.db.session import get_db
from app.models.packaging_task import PackagingTask, PackagingTaskLine
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
    quantity: int = Field(ge=1, le=1_000_000_000)


class PackagingTaskCreate(BaseModel):
    warehouse_id: uuid.UUID
    lines: list[PackagingTaskLineIn] = Field(min_length=1)
    inbound_intake_request_id: uuid.UUID | None = None


class ConfirmPackedIn(BaseModel):
    quantity: int | None = Field(default=None, ge=0, le=1_000_000_000)


class PackProgressIn(BaseModel):
    quantity: int = Field(ge=1, le=1_000_000_000)


class CompletePackagingIn(BaseModel):
    acknowledge_all_packed: bool = False


class PackagingTaskLineOut(BaseModel):
    id: str
    product_id: str
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
    marking_available_count: int = 0
    is_complete: bool


class PackagingTaskOut(BaseModel):
    id: str
    document_number: str | None = None
    warehouse_id: str
    status: str
    marketplace_unload_request_id: str | None
    inbound_intake_request_id: str | None
    is_complete: bool
    pick_resync_warning: bool = False
    lines: list[PackagingTaskLineOut]


def _line_out(ln: PackagingTaskLine, *, marking_available: int = 0) -> PackagingTaskLineOut:
    p = ln.product
    loc = ln.storage_location
    return PackagingTaskLineOut(
        id=str(ln.id),
        product_id=str(ln.product_id),
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
        marking_available_count=marking_available,
        is_complete=pkg_svc.is_line_complete(ln),
    )


async def _task_out(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task: PackagingTask,
    *,
    pick_resync_warning: bool = False,
) -> PackagingTaskOut:
    line_outs: list[PackagingTaskLineOut] = []
    for ln in task.lines:
        available = 0
        if ln.product.requires_honest_sign:
            available = await mc_svc.count_available_for_product(
                session, tenant_id, ln.product_id
            )
        line_outs.append(_line_out(ln, marking_available=available))
    return PackagingTaskOut(
        id=str(task.id),
        document_number=task.document_number,
        warehouse_id=str(task.warehouse_id),
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
        lines=line_outs,
    )


def _http_from_pkg_error(exc: pkg_svc.PackagingTaskServiceError) -> HTTPException:
    code = exc.code
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    if code == "not_found":
        status_code = status.HTTP_404_NOT_FOUND
    return HTTPException(status_code=status_code, detail=code)


@router.get("", response_model=list[PackagingTaskOut])
async def list_packaging_tasks(
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    warehouse_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[PackagingTaskOut]:
    tasks = await pkg_svc.list_open_tasks(
        session, user.tenant_id, warehouse_id=warehouse_id
    )
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
    try:
        task = await pkg_svc.ensure_task_for_unload(session, user.tenant_id, unload_id)
    except pkg_svc.PackagingTaskServiceError as exc:
        raise _http_from_pkg_error(exc) from exc
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
        task = synced.task
        pick_warning = task.pick_resync_warning
    return await _task_out(session, user.tenant_id, task, pick_resync_warning=pick_warning)


@router.post("/{task_id}/cancel", response_model=PackagingTaskOut)
async def cancel_packaging_task(
    task_id: uuid.UUID,
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PackagingTaskOut:
    try:
        task = await pkg_svc.cancel_task(session, user.tenant_id, task_id)
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


@router.post("/{task_id}/lines/{line_id}/pack", response_model=PackagingTaskOut)
async def record_pack_progress(
    task_id: uuid.UUID,
    line_id: uuid.UUID,
    body: PackProgressIn,
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PackagingTaskOut:
    try:
        task = await pkg_svc.record_pack_progress(
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
