from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inventory_balance import InventoryBalance
from app.models.marketplace_unload import (
    MarketplaceUnloadLine,
    MarketplaceUnloadPickAllocation,
    MarketplaceUnloadRequest,
)
from app.models.packaging_task import (
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_DRAFT,
    STATUS_IN_PROGRESS,
    PackagingTask,
    PackagingTaskLine,
)
from app.services import inventory_service as inv_svc
from app.services import marketplace_unload_service as mu_svc
from app.services import sorting_location_service as sorting_loc_svc
from app.services import staff_packaging_billing_service as billing_svc
from app.services.document_number_service import (
    DOC_TYPE_PACKAGING,
    assign_display_number_if_missing,
    assign_document_number_if_missing,
)

PackagingTaskError = Literal[
    "not_found",
    "bad_status",
    "line_not_found",
    "invalid_qty",
    "insufficient_unpacked",
    "task_not_done",
    "packaging_incomplete",
    "marking_not_done",
    "unload_not_found",
    "unload_not_confirmed",
    "no_lines",
    "linked_unload",
]


class PackagingTaskServiceError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class PackagingTaskProgress:
    task_id: uuid.UUID
    status: str
    qty_done: int
    qty_total: int
    is_complete: bool


def task_progress(task: PackagingTask) -> PackagingTaskProgress:
    total = sum(int(ln.qty_total) for ln in task.lines)
    done = sum(qty_done(ln) for ln in task.lines)
    return PackagingTaskProgress(
        task_id=task.id,
        status=task.status,
        qty_done=done,
        qty_total=total,
        is_complete=is_task_complete(task),
    )


@dataclass(frozen=True)
class SyncPickResult:
    task: PackagingTask
    pick_changed_with_progress: bool


async def progress_for_unload(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    unload_id: uuid.UUID,
    *,
    sync_from_pick: bool = False,
) -> PackagingTaskProgress | None:
    task = await get_task_for_unload(session, tenant_id, unload_id)
    if task is None:
        return None
    if sync_from_pick:
        synced = await sync_lines_from_pick_allocations(session, tenant_id, task)
        task = synced.task
    return task_progress(task)


async def _get_balance_split(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
) -> tuple[int, int]:
    stmt = select(
        InventoryBalance.quantity_unpacked,
        InventoryBalance.quantity_packed,
    ).where(
        InventoryBalance.tenant_id == tenant_id,
        InventoryBalance.product_id == product_id,
        InventoryBalance.storage_location_id == storage_location_id,
    )
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        return 0, 0
    return int(row[0] or 0), int(row[1] or 0)


def qty_need_pack(line: PackagingTaskLine) -> int:
    return max(0, int(line.qty_total) - int(line.qty_confirmed_packed))


def qty_done(line: PackagingTaskLine) -> int:
    return int(line.qty_confirmed_packed) + int(line.qty_packed_in_task)


def is_line_complete(line: PackagingTaskLine) -> bool:
    return qty_done(line) >= int(line.qty_total)


def _is_mp_unload_task(task: PackagingTask) -> bool:
    return task.marketplace_unload_request_id is not None


def is_task_complete(task: PackagingTask) -> bool:
    if not task.lines:
        return False
    return all(is_line_complete(ln) for ln in task.lines)


def _touch_task(task: PackagingTask) -> None:
    task.updated_at = datetime.now(UTC)
    if task.status == STATUS_DRAFT and any(
        ln.qty_confirmed_packed > 0 or ln.qty_packed_in_task > 0 for ln in task.lines
    ):
        task.status = STATUS_IN_PROGRESS


async def get_task(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task_id: uuid.UUID,
) -> PackagingTask | None:
    stmt = (
        select(PackagingTask)
        .where(PackagingTask.id == task_id, PackagingTask.tenant_id == tenant_id)
        .options(
            selectinload(PackagingTask.lines).selectinload(PackagingTaskLine.product),
            selectinload(PackagingTask.lines).selectinload(PackagingTaskLine.storage_location),
            selectinload(PackagingTask.marketplace_unload_request),
        )
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_task_for_unload(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    unload_id: uuid.UUID,
) -> PackagingTask | None:
    stmt = (
        select(PackagingTask)
        .where(
            PackagingTask.tenant_id == tenant_id,
            PackagingTask.marketplace_unload_request_id == unload_id,
            PackagingTask.status != STATUS_CANCELLED,
        )
        .options(
            selectinload(PackagingTask.lines).selectinload(PackagingTaskLine.product),
            selectinload(PackagingTask.lines).selectinload(PackagingTaskLine.storage_location),
        )
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_open_tasks(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID | None = None,
) -> list[PackagingTask]:
    stmt = (
        select(PackagingTask)
        .where(
            PackagingTask.tenant_id == tenant_id,
            PackagingTask.status.in_((STATUS_DRAFT, STATUS_IN_PROGRESS)),
        )
        .options(
            selectinload(PackagingTask.lines).selectinload(PackagingTaskLine.product),
            selectinload(PackagingTask.lines).selectinload(
                PackagingTaskLine.storage_location
            ),
            selectinload(PackagingTask.marketplace_unload_request),
        )
        .order_by(PackagingTask.updated_at.desc())
    )
    if warehouse_id is not None:
        stmt = stmt.where(PackagingTask.warehouse_id == warehouse_id)
    return list((await session.execute(stmt)).scalars().all())


async def create_manual_task(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID,
    lines: list[tuple[uuid.UUID, uuid.UUID | None, int]],
    inbound_intake_request_id: uuid.UUID | None = None,
    created_by_user_id: uuid.UUID | None = None,
) -> PackagingTask:
    if not lines:
        raise PackagingTaskServiceError("no_lines")
    task = PackagingTask(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        status=STATUS_DRAFT,
        inbound_intake_request_id=inbound_intake_request_id,
        created_by_user_id=created_by_user_id,
    )
    session.add(task)
    await session.flush()
    await assign_document_number_if_missing(
        session, tenant_id, DOC_TYPE_PACKAGING, task
    )
    await assign_display_number_if_missing(
        session, tenant_id, DOC_TYPE_PACKAGING, task
    )
    for product_id, location_id, qty in lines:
        if qty < 1:
            raise PackagingTaskServiceError("invalid_qty")
        if location_id is None:
            loc = await sorting_loc_svc.get_or_create_sorting_location(
                session, tenant_id, warehouse_id
            )
            location_id = loc.id
        _unpacked, packed = await _get_balance_split(
            session, tenant_id, product_id, location_id
        )
        if qty > _unpacked:
            raise PackagingTaskServiceError("insufficient_unpacked")
        suggested = min(packed, qty)
        session.add(
            PackagingTaskLine(
                task_id=task.id,
                product_id=product_id,
                storage_location_id=location_id,
                qty_total=qty,
                qty_suggested_packed=suggested,
            )
        )
    await session.commit()
    loaded = await get_task(session, tenant_id, task.id)
    assert loaded is not None
    return loaded


async def sync_lines_from_unload_plan(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task: PackagingTask,
) -> SyncPickResult:
    pick_changed_with_progress = False
    loaded = await get_task(session, tenant_id, task.id)
    if loaded is None:
        return SyncPickResult(task=task, pick_changed_with_progress=False)
    task = loaded
    if task.marketplace_unload_request_id is None:
        return SyncPickResult(task=task, pick_changed_with_progress=False)

    unload_id = task.marketplace_unload_request_id
    pick_exists_stmt = (
        select(MarketplaceUnloadPickAllocation.id)
        .where(
            MarketplaceUnloadPickAllocation.request_id == unload_id,
            MarketplaceUnloadPickAllocation.quantity > 0,
        )
        .limit(1)
    )
    if (await session.execute(pick_exists_stmt)).scalar_one_or_none() is not None:
        return SyncPickResult(task=task, pick_changed_with_progress=False)

    unload_lines = list(
        (
            await session.execute(
                select(MarketplaceUnloadLine).where(
                    MarketplaceUnloadLine.request_id == unload_id
                )
            )
        )
        .scalars()
        .all()
    )

    sorting_loc = await sorting_loc_svc.get_or_create_sorting_location(
        session, tenant_id, task.warehouse_id
    )
    location_id = sorting_loc.id

    line_stmt = select(PackagingTaskLine).where(PackagingTaskLine.task_id == task.id)
    db_lines = list((await session.execute(line_stmt)).scalars().all())
    existing = {
        ln.product_id: ln for ln in db_lines if ln.storage_location_id == location_id
    }
    plan_qty_before = {pid: int(ln.qty_total) for pid, ln in existing.items()}
    seen: set[uuid.UUID] = set()

    for ul in unload_lines:
        product_id = ul.product_id
        seen.add(product_id)
        qty = int(ul.quantity)
        _unpacked, packed = await _get_balance_split(
            session, tenant_id, product_id, location_id
        )
        suggested = min(packed, qty)
        if product_id in existing:
            ln = existing[product_id]
            has_progress = ln.qty_packed_in_task > 0 or ln.qty_confirmed_packed > 0
            if has_progress and (
                ln.qty_total != qty or ln.qty_suggested_packed != suggested
            ):
                pick_changed_with_progress = True
            if (ln.qty_packed_in_task == 0 and ln.qty_confirmed_packed == 0) or has_progress:
                ln.qty_total = qty
                ln.qty_suggested_packed = suggested
        else:
            session.add(
                PackagingTaskLine(
                    task_id=task.id,
                    product_id=product_id,
                    storage_location_id=location_id,
                    qty_total=qty,
                    qty_suggested_packed=suggested,
                )
            )

    for product_id, ln in existing.items():
        if product_id not in seen:
            if ln.qty_packed_in_task > 0 or ln.qty_confirmed_packed > 0:
                pick_changed_with_progress = True
            if ln.qty_packed_in_task == 0 and ln.qty_confirmed_packed == 0:
                await session.delete(ln)

    if pick_changed_with_progress:
        task.pick_resync_warning = True
    if task.status == STATUS_DONE:
        plan_qty_after = {ul.product_id: int(ul.quantity) for ul in unload_lines}
        if plan_qty_after != plan_qty_before:
            task.status = STATUS_IN_PROGRESS
            task.completed_at = None
            task.completed_by_user_id = None
    _touch_task(task)
    await session.commit()
    loaded = await get_task(session, tenant_id, task.id)
    assert loaded is not None
    return SyncPickResult(task=loaded, pick_changed_with_progress=pick_changed_with_progress)


async def sync_lines_from_pick_allocations(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task: PackagingTask,
) -> SyncPickResult:
    pick_changed_with_progress = False
    loaded = await get_task(session, tenant_id, task.id)
    if loaded is None:
        return SyncPickResult(task=task, pick_changed_with_progress=False)
    task = loaded
    if task.marketplace_unload_request_id is None:
        return SyncPickResult(task=task, pick_changed_with_progress=False)
    unload_id = task.marketplace_unload_request_id
    stmt = select(MarketplaceUnloadPickAllocation).where(
        MarketplaceUnloadPickAllocation.request_id == unload_id,
        MarketplaceUnloadPickAllocation.quantity > 0,
    )
    allocs = list((await session.execute(stmt)).scalars().all())
    if not allocs:
        return SyncPickResult(task=task, pick_changed_with_progress=False)

    line_stmt = select(PackagingTaskLine).where(PackagingTaskLine.task_id == task.id)
    db_lines = list((await session.execute(line_stmt)).scalars().all())
    existing = {
        (ln.product_id, ln.storage_location_id): ln for ln in db_lines
    }
    seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for alloc in allocs:
        key = (alloc.product_id, alloc.storage_location_id)
        seen.add(key)
        _unpacked, packed = await _get_balance_split(
            session, tenant_id, alloc.product_id, alloc.storage_location_id
        )
        qty = int(alloc.quantity)
        suggested = min(packed, qty)
        if key in existing:
            ln = existing[key]
            has_progress = ln.qty_packed_in_task > 0 or ln.qty_confirmed_packed > 0
            if has_progress and (
                ln.qty_total != qty or ln.qty_suggested_packed != suggested
            ):
                pick_changed_with_progress = True
            if (ln.qty_packed_in_task == 0 and ln.qty_confirmed_packed == 0) or has_progress:
                ln.qty_total = qty
                ln.qty_suggested_packed = suggested
        else:
            session.add(
                PackagingTaskLine(
                    task_id=task.id,
                    product_id=alloc.product_id,
                    storage_location_id=alloc.storage_location_id,
                    qty_total=qty,
                    qty_suggested_packed=suggested,
                )
            )
    for key, ln in existing.items():
        if key not in seen:
            if ln.qty_packed_in_task > 0 or ln.qty_confirmed_packed > 0:
                pick_changed_with_progress = True
            if ln.qty_packed_in_task == 0 and ln.qty_confirmed_packed == 0:
                await session.delete(ln)

    sorting_loc = await sorting_loc_svc.get_or_create_sorting_location(
        session, tenant_id, task.warehouse_id
    )
    sorting_id = sorting_loc.id
    picked_products = {alloc.product_id for alloc in allocs}
    refreshed_lines = list((await session.execute(line_stmt)).scalars().all())
    for ln in refreshed_lines:
        if (
            ln.storage_location_id == sorting_id
            and ln.product_id in picked_products
            and ln.qty_packed_in_task == 0
            and ln.qty_confirmed_packed == 0
        ):
            await session.delete(ln)

    if pick_changed_with_progress:
        task.pick_resync_warning = True
    _touch_task(task)
    await session.commit()
    loaded = await get_task(session, tenant_id, task.id)
    assert loaded is not None
    return SyncPickResult(task=loaded, pick_changed_with_progress=pick_changed_with_progress)


async def ensure_task_for_unload(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    unload_id: uuid.UUID,
    *,
    created_by_user_id: uuid.UUID | None = None,
) -> PackagingTask:
    existing = await get_task_for_unload(session, tenant_id, unload_id)
    if existing is not None:
        synced = await sync_lines_from_unload_plan(session, tenant_id, existing)
        return synced.task

    req = await session.get(MarketplaceUnloadRequest, unload_id)
    if req is None or req.tenant_id != tenant_id:
        raise PackagingTaskServiceError("unload_not_found")
    if req.status not in mu_svc.PACKAGING_SYNC_STATUSES:
        raise PackagingTaskServiceError("unload_not_confirmed")

    task = PackagingTask(
        tenant_id=tenant_id,
        warehouse_id=req.warehouse_id,
        status=STATUS_DRAFT,
        marketplace_unload_request_id=unload_id,
        created_by_user_id=created_by_user_id,
    )
    session.add(task)
    await session.flush()
    await assign_document_number_if_missing(
        session, tenant_id, DOC_TYPE_PACKAGING, task
    )
    await assign_display_number_if_missing(
        session, tenant_id, DOC_TYPE_PACKAGING, task
    )
    await sync_lines_from_unload_plan(session, tenant_id, task)
    await session.commit()
    loaded = await get_task(session, tenant_id, task.id)
    assert loaded is not None
    return loaded


async def cancel_task(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task_id: uuid.UUID,
) -> PackagingTask:
    task = await get_task(session, tenant_id, task_id)
    if task is None:
        raise PackagingTaskServiceError("not_found")
    if task.status in (STATUS_DONE, STATUS_CANCELLED):
        raise PackagingTaskServiceError("bad_status")
    if task.marketplace_unload_request_id is not None:
        raise PackagingTaskServiceError("linked_unload")
    task.status = STATUS_CANCELLED
    task.updated_at = datetime.now(UTC)
    await session.commit()
    loaded = await get_task(session, tenant_id, task_id)
    assert loaded is not None
    return loaded


async def confirm_line_packed_from_shelf(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task_id: uuid.UUID,
    line_id: uuid.UUID,
    qty: int | None = None,
    *,
    acting_user_id: uuid.UUID | None = None,
) -> PackagingTask:
    task = await get_task(session, tenant_id, task_id)
    if task is None:
        raise PackagingTaskServiceError("not_found")
    if task.status == STATUS_DONE:
        raise PackagingTaskServiceError("bad_status")
    line = next((ln for ln in task.lines if ln.id == line_id), None)
    if line is None:
        raise PackagingTaskServiceError("line_not_found")
    confirmed = int(line.qty_suggested_packed if qty is None else qty)
    if confirmed < 0 or confirmed > line.qty_total:
        raise PackagingTaskServiceError("invalid_qty")
    _, packed_on_hand = await _get_balance_split(
        session, tenant_id, line.product_id, line.storage_location_id
    )
    if confirmed > packed_on_hand:
        raise PackagingTaskServiceError("invalid_qty")
    line.qty_confirmed_packed = confirmed
    _touch_task(task)
    if acting_user_id is not None:
        await billing_svc.finalize_task_billing(
            session, task, completed_by_user_id=acting_user_id
        )
    await session.commit()
    loaded = await get_task(session, tenant_id, task_id)
    assert loaded is not None
    return loaded


async def record_pack_progress(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task_id: uuid.UUID,
    line_id: uuid.UUID,
    qty: int,
    *,
    acting_user_id: uuid.UUID | None = None,
) -> PackagingTask:
    if qty < 1:
        raise PackagingTaskServiceError("invalid_qty")
    task = await get_task(session, tenant_id, task_id)
    if task is None:
        raise PackagingTaskServiceError("not_found")
    if task.status == STATUS_DONE:
        raise PackagingTaskServiceError("bad_status")
    line = next((ln for ln in task.lines if ln.id == line_id), None)
    if line is None:
        raise PackagingTaskServiceError("line_not_found")
    need = qty_need_pack(line)
    remaining = need - int(line.qty_packed_in_task)
    if qty > remaining:
        raise PackagingTaskServiceError("invalid_qty")
    if _is_mp_unload_task(task):
        line.qty_packed_in_task = int(line.qty_packed_in_task) + qty
    else:
        try:
            await inv_svc.apply_packaging_convert(
                session,
                tenant_id=tenant_id,
                product_id=line.product_id,
                storage_location_id=line.storage_location_id,
                quantity=qty,
            )
        except ValueError as exc:
            if str(exc) == "insufficient_unpacked":
                raise PackagingTaskServiceError("insufficient_unpacked") from exc
            raise
        line.qty_packed_in_task = int(line.qty_packed_in_task) + qty
    _touch_task(task)
    if acting_user_id is not None:
        await billing_svc.finalize_task_billing(
            session, task, completed_by_user_id=acting_user_id
        )
    await session.commit()
    loaded = await get_task(session, tenant_id, task_id)
    assert loaded is not None
    return loaded


async def _apply_acknowledge_all_packed(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task: PackagingTask,
) -> None:
    if _is_mp_unload_task(task):
        for line in task.lines:
            if is_line_complete(line):
                continue
            need = qty_need_pack(line)
            if need > 0:
                line.qty_packed_in_task = int(line.qty_packed_in_task) + need
        return
    for line in task.lines:
        if is_line_complete(line):
            continue
        unpacked, packed_on_hand = await _get_balance_split(
            session, tenant_id, line.product_id, line.storage_location_id
        )
        shelf_target = min(int(line.qty_total), packed_on_hand)
        if shelf_target > int(line.qty_confirmed_packed):
            if shelf_target > packed_on_hand:
                raise PackagingTaskServiceError("packaging_incomplete")
            line.qty_confirmed_packed = shelf_target
        need = qty_need_pack(line)
        if need > 0:
            if unpacked < need:
                raise PackagingTaskServiceError("packaging_incomplete")
            try:
                await inv_svc.apply_packaging_convert(
                    session,
                    tenant_id=tenant_id,
                    product_id=line.product_id,
                    storage_location_id=line.storage_location_id,
                    quantity=need,
                )
            except ValueError as exc:
                if str(exc) == "insufficient_unpacked":
                    raise PackagingTaskServiceError("packaging_incomplete") from exc
                raise
            line.qty_packed_in_task = int(line.qty_packed_in_task) + need


async def _assert_marking_done_for_task(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task: PackagingTask,
) -> None:
    from app.services import marking_code_service as mc_svc

    for line in task.lines:
        try:
            await mc_svc.assert_packaging_line_marking_done(session, tenant_id, line)
        except mc_svc.MarkingCodeServiceError as exc:
            if exc.code == "marking_not_done":
                raise PackagingTaskServiceError("marking_not_done") from exc
            raise


async def complete_task(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task_id: uuid.UUID,
    *,
    acknowledge_all_packed: bool = False,
    acting_user_id: uuid.UUID | None = None,
) -> PackagingTask:
    task = await get_task(session, tenant_id, task_id)
    if task is None:
        raise PackagingTaskServiceError("not_found")
    if task.status == STATUS_DONE:
        loaded = await get_task(session, tenant_id, task_id)
        assert loaded is not None
        return loaded
    if task.status == STATUS_CANCELLED:
        raise PackagingTaskServiceError("bad_status")
    if not task.lines:
        raise PackagingTaskServiceError("no_lines")

    if acknowledge_all_packed:
        await _apply_acknowledge_all_packed(session, tenant_id, task)
        _touch_task(task)

    if not is_task_complete(task):
        raise PackagingTaskServiceError("packaging_incomplete")

    await _assert_marking_done_for_task(session, tenant_id, task)

    task.status = STATUS_DONE
    task.updated_at = datetime.now(UTC)
    if acting_user_id is not None:
        await billing_svc.finalize_task_billing(
            session, task, completed_by_user_id=acting_user_id
        )
    else:
        task.completed_at = datetime.now(UTC)
        task.completed_by_user_id = None
    await session.commit()
    loaded = await get_task(session, tenant_id, task_id)
    assert loaded is not None
    return loaded


async def assert_unload_packaging_done(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    unload_id: uuid.UUID,
) -> None:
    task = await get_task_for_unload(session, tenant_id, unload_id)
    if task is None:
        raise PackagingTaskServiceError("task_not_done")
    if task.status != STATUS_DONE:
        raise PackagingTaskServiceError("task_not_done")
    await _assert_marking_done_for_task(session, tenant_id, task)
