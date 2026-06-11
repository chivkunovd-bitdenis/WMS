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


class PackagingTaskLineOut(BaseModel):
    id: str
    product_id: str
    sku_code: str
    product_name: str
    storage_location_id: str
    storage_location_code: str
    packaging_instructions: str | None
    qty_total: int
    qty_suggested_packed: int
    qty_confirmed_packed: int
    qty_need_pack: int
    qty_packed_in_task: int
    qty_done: int
    is_complete: bool


class PackagingTaskOut(BaseModel):
    id: str
    warehouse_id: str
    status: str
    marketplace_unload_request_id: str | None
    inbound_intake_request_id: str | None
    is_complete: bool
    pick_resync_warning: bool = False
    lines: list[PackagingTaskLineOut]


def _line_out(ln: PackagingTaskLine) -> PackagingTaskLineOut:
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
        qty_total=int(ln.qty_total),
        qty_suggested_packed=int(ln.qty_suggested_packed),
        qty_confirmed_packed=int(ln.qty_confirmed_packed),
        qty_need_pack=pkg_svc.qty_need_pack(ln),
        qty_packed_in_task=int(ln.qty_packed_in_task),
        qty_done=pkg_svc.qty_done(ln),
        is_complete=pkg_svc.is_line_complete(ln),
    )


def _task_out(task: PackagingTask, *, pick_resync_warning: bool = False) -> PackagingTaskOut:
    return PackagingTaskOut(
        id=str(task.id),
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
        lines=[_line_out(ln) for ln in task.lines],
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
    return [_task_out(t) for t in tasks]


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
    return _task_out(task)


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
    return _task_out(task, pick_resync_warning=task.pick_resync_warning)


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
    return _task_out(task, pick_resync_warning=pick_warning)


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
    return _task_out(task)


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
    return _task_out(task)


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
    return _task_out(task)
