from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inventory_balance import InventoryBalance
from app.models.marketplace_unload import (
    MarketplaceUnloadBox,
    MarketplaceUnloadBoxLine,
    MarketplaceUnloadLine,
    MarketplaceUnloadPickAllocation,
    MarketplaceUnloadRequest,
)
from app.models.packaging_task import (
    PACKAGING_EVENT_CANCEL,
    PACKAGING_EVENT_COMPLETE,
    PACKAGING_EVENT_MANUAL_PACK,
    PACKAGING_EVENT_PREPACKED_EXTERNAL,
    PACKAGING_EVENT_PRODUCT_LABEL_PRINT,
    PACKAGING_EVENT_SCAN_PACK,
    PACKAGING_EVENT_UNDO_LAST,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_DRAFT,
    STATUS_IN_PROGRESS,
    PackagingTask,
    PackagingTaskEvent,
    PackagingTaskLine,
)
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
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
    "order_not_picked",
    "order_already_packed",
    "order_not_in_supply",
    "order_product_mismatch",
    "no_eligible_order",
    "supply_not_found",
    "fbs_acknowledge_not_allowed",
    "mixed_seller",
    "unknown_barcode",
    "line_already_packed",
    "undo_not_available",
    "undo_not_supported",
    "invalid_status_filter",
]

REVERSIBLE_PACK_EVENTS = (PACKAGING_EVENT_SCAN_PACK, PACKAGING_EVENT_MANUAL_PACK)


class PackagingTaskServiceError(Exception):
    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        self.message = message
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
class PackProgressResult:
    task: PackagingTask
    fulfilled_order: object | None = None
    # Предупреждения по остатку: упаковка FBS их больше не превращает в отказ.
    warnings: list[str] = field(default_factory=list)


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
    if _is_mp_unload_task(task):
        await sync_mp_task_packed_from_boxes(session, tenant_id, task)
        await session.commit()
        loaded = await get_task(session, tenant_id, task.id)
        assert loaded is not None
        task = loaded
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


async def _add_task_event(
    session: AsyncSession,
    task: PackagingTask,
    *,
    action: str,
    quantity: int = 0,
    line: PackagingTaskLine | None = None,
    acting_user_id: uuid.UUID | None = None,
    note: str | None = None,
) -> PackagingTaskEvent:
    await session.execute(
        select(PackagingTask.id)
        .where(PackagingTask.id == task.id, PackagingTask.tenant_id == task.tenant_id)
        .with_for_update()
    )
    next_sequence = await session.scalar(
        select(func.coalesce(func.max(PackagingTaskEvent.event_sequence), 0) + 1).where(
            PackagingTaskEvent.tenant_id == task.tenant_id,
            PackagingTaskEvent.task_id == task.id,
        )
    )
    event = PackagingTaskEvent(
        tenant_id=task.tenant_id,
        task_id=task.id,
        event_sequence=int(next_sequence or 1),
        line_id=line.id if line else None,
        product_id=line.product_id if line else None,
        storage_location_id=line.storage_location_id if line else None,
        action=action,
        quantity=quantity,
        note=note,
        created_by_user_id=acting_user_id,
    )
    session.add(event)
    await session.flush()
    return event


async def get_task(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task_id: uuid.UUID,
) -> PackagingTask | None:
    stmt = (
        select(PackagingTask)
        .where(PackagingTask.id == task_id, PackagingTask.tenant_id == tenant_id)
        .options(
            selectinload(PackagingTask.lines)
            .selectinload(PackagingTaskLine.product)
            .selectinload(Product.seller),
            selectinload(PackagingTask.lines).selectinload(PackagingTaskLine.storage_location),
            selectinload(PackagingTask.warehouse),
            selectinload(PackagingTask.events).selectinload(PackagingTaskEvent.line),
            selectinload(PackagingTask.events).selectinload(PackagingTaskEvent.product),
            selectinload(PackagingTask.events).selectinload(
                PackagingTaskEvent.storage_location
            ),
            selectinload(PackagingTask.events).selectinload(
                PackagingTaskEvent.created_by_user
            ),
        )
        .execution_options(populate_existing=True)
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
            selectinload(PackagingTask.lines)
            .selectinload(PackagingTaskLine.product)
            .selectinload(Product.seller),
            selectinload(PackagingTask.lines).selectinload(PackagingTaskLine.storage_location),
            selectinload(PackagingTask.warehouse),
            selectinload(PackagingTask.events).selectinload(PackagingTaskEvent.created_by_user),
        )
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _status_filter_values(status_filter: str) -> tuple[str, ...]:
    if status_filter == "open":
        return (STATUS_DRAFT, STATUS_IN_PROGRESS)
    if status_filter in {STATUS_DRAFT, STATUS_IN_PROGRESS, STATUS_DONE, STATUS_CANCELLED}:
        return (status_filter,)
    if status_filter == "all":
        return (STATUS_DRAFT, STATUS_IN_PROGRESS, STATUS_DONE, STATUS_CANCELLED)
    raise PackagingTaskServiceError("invalid_status_filter")


async def list_tasks(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID | None = None,
    status_filter: str = "open",
    search: str | None = None,
) -> list[PackagingTask]:
    statuses = _status_filter_values(status_filter)
    stmt = (
        select(PackagingTask)
        .where(
            PackagingTask.tenant_id == tenant_id,
            PackagingTask.status.in_(statuses),
        )
        .options(
            selectinload(PackagingTask.lines)
            .selectinload(PackagingTaskLine.product)
            .selectinload(Product.seller),
            selectinload(PackagingTask.lines).selectinload(
                PackagingTaskLine.storage_location
            ),
            selectinload(PackagingTask.warehouse),
            selectinload(PackagingTask.events).selectinload(PackagingTaskEvent.created_by_user),
        )
        .execution_options(populate_existing=True)
        .order_by(PackagingTask.updated_at.desc())
    )
    if warehouse_id is not None:
        stmt = stmt.where(PackagingTask.warehouse_id == warehouse_id)
    query = search.strip() if search else ""
    if query:
        pattern = f"%{query.lower()}%"
        stmt = (
            stmt.outerjoin(PackagingTaskLine, PackagingTaskLine.task_id == PackagingTask.id)
            .outerjoin(Product, Product.id == PackagingTaskLine.product_id)
            .outerjoin(StorageLocation, StorageLocation.id == PackagingTaskLine.storage_location_id)
            .outerjoin(Seller, Seller.id == Product.seller_id)
            .where(
                or_(
                    PackagingTask.document_number.ilike(pattern),
                    PackagingTask.display_number.ilike(pattern),
                    Product.sku_code.ilike(pattern),
                    Product.name.ilike(pattern),
                    Product.wb_barcode.ilike(pattern),
                    StorageLocation.code.ilike(pattern),
                    Seller.name.ilike(pattern),
                )
            )
            .distinct()
        )
    return list((await session.execute(stmt)).scalars().all())


async def list_open_tasks(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID | None = None,
) -> list[PackagingTask]:
    return await list_tasks(
        session,
        tenant_id,
        warehouse_id=warehouse_id,
        status_filter="open",
    )


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
    product_ids = {product_id for product_id, _location_id, _qty in lines}
    products = list(
        (
            await session.execute(
                select(Product).where(
                    Product.tenant_id == tenant_id,
                    Product.id.in_(product_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    if len(products) != len(product_ids):
        raise PackagingTaskServiceError("not_found")
    seller_keys = {product.seller_id for product in products}
    if len(seller_keys) > 1:
        raise PackagingTaskServiceError("mixed_seller")
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

    task.pick_resync_warning = pick_changed_with_progress
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
    """Rebuild packaging lines for an MP-unload task, one row per product.

    Packaging never tracks storage cells, only product quantity. A pick
    allocation can source one product from several cells, but on the
    packaging task that must always collapse into a single row per
    product with the summed quantity.
    """
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

    sorting_loc = await sorting_loc_svc.get_or_create_sorting_location(
        session, tenant_id, task.warehouse_id
    )
    location_id = sorting_loc.id

    qty_by_product: dict[uuid.UUID, int] = {}
    for alloc in allocs:
        qty_by_product[alloc.product_id] = (
            qty_by_product.get(alloc.product_id, 0) + int(alloc.quantity)
        )

    line_stmt = select(PackagingTaskLine).where(PackagingTaskLine.task_id == task.id)
    db_lines = list((await session.execute(line_stmt)).scalars().all())

    by_product: dict[uuid.UUID, list[PackagingTaskLine]] = {}
    for ln in db_lines:
        by_product.setdefault(ln.product_id, []).append(ln)

    existing: dict[uuid.UUID, PackagingTaskLine] = {}
    for product_id, group in by_product.items():
        primary = group[0]
        for dup in group[1:]:
            # Legacy per-cell duplicates from before packaging stopped
            # tracking storage cells: fold progress into one surviving row.
            primary.qty_packed_in_task += dup.qty_packed_in_task
            primary.qty_confirmed_packed += dup.qty_confirmed_packed
            primary.qty_marking_printed += dup.qty_marking_printed
            await session.delete(dup)
        existing[product_id] = primary

    seen: set[uuid.UUID] = set()
    for product_id, qty in qty_by_product.items():
        seen.add(product_id)
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
            ln.storage_location_id = location_id
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

    task.pick_resync_warning = pick_changed_with_progress
    _touch_task(task)
    await session.commit()
    loaded = await get_task(session, tenant_id, task.id)
    assert loaded is not None
    return SyncPickResult(task=loaded, pick_changed_with_progress=pick_changed_with_progress)


async def sync_mp_task_packed_from_boxes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task: PackagingTask,
) -> PackagingTask:
    if task.marketplace_unload_request_id is None:
        return task
    stmt = (
        select(
            MarketplaceUnloadBoxLine.product_id,
            func.coalesce(func.sum(MarketplaceUnloadBoxLine.quantity), 0),
        )
        .join(MarketplaceUnloadBox, MarketplaceUnloadBox.id == MarketplaceUnloadBoxLine.box_id)
        .join(
            MarketplaceUnloadRequest,
            MarketplaceUnloadRequest.id == MarketplaceUnloadBox.request_id,
        )
        .where(
            MarketplaceUnloadBox.request_id == task.marketplace_unload_request_id,
            MarketplaceUnloadRequest.tenant_id == tenant_id,
        )
        .group_by(MarketplaceUnloadBoxLine.product_id)
    )
    boxed_by_product = {
        product_id: int(quantity or 0)
        for product_id, quantity in (await session.execute(stmt)).all()
    }
    if not boxed_by_product:
        return task
    changed = False
    for line in task.lines:
        boxed = boxed_by_product.get(line.product_id)
        if boxed is None:
            continue
        target = min(int(line.qty_total) - int(line.qty_confirmed_packed), boxed)
        if int(line.qty_packed_in_task) != target:
            line.qty_packed_in_task = target
            changed = True
    if changed:
        _touch_task(task)
    return task


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
    *,
    acting_user_id: uuid.UUID | None = None,
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
    await _add_task_event(
        session,
        task,
        action=PACKAGING_EVENT_CANCEL,
        acting_user_id=acting_user_id,
    )
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


async def mark_line_prepacked_external(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task_id: uuid.UUID,
    line_id: uuid.UUID,
    qty: int,
    *,
    acting_user_id: uuid.UUID | None = None,
) -> PackagingTask:
    """«Пришло готовым»: товар уже упакован и промаркирован поставщиком/селлером до
    поступления на упаковку. Прибавляет к qty_packed_in_task, а при
    requires_honest_sign — честно к qty_marking_external (НЕ к qty_marking_printed,
    иначе исказится учёт расхода кодов ЧЗ). Именно qty_marking_external уже учитывает
    assert_packaging_line_marking_done при проверке готовности задания."""
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

    from app.services.fbs_packaging_integration_service import get_supply_for_packaging_task

    fbs_supply = await get_supply_for_packaging_task(session, tenant_id, task_id)
    if fbs_supply is not None:
        raise PackagingTaskServiceError("bad_status")

    need = qty_need_pack(line)
    remaining = need - int(line.qty_packed_in_task)
    if remaining <= 0:
        raise PackagingTaskServiceError("line_already_packed")
    if qty > remaining:
        raise PackagingTaskServiceError("invalid_qty")

    line.qty_packed_in_task = int(line.qty_packed_in_task) + qty
    if line.product.requires_honest_sign:
        line.qty_marking_external = int(line.qty_marking_external) + qty
    _touch_task(task)
    await _add_task_event(
        session,
        task,
        action=PACKAGING_EVENT_PREPACKED_EXTERNAL,
        quantity=qty,
        line=line,
        acting_user_id=acting_user_id,
    )
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
    order_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
    action: str = PACKAGING_EVENT_MANUAL_PACK,
) -> PackProgressResult:
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

    from app.services.fbs_packaging_integration_service import (
        FbsPackagingIntegrationError,
        get_supply_for_packaging_task,
        record_fbs_pack_progress,
    )

    fbs_supply = await get_supply_for_packaging_task(session, tenant_id, task_id)
    if remaining <= 0:
        if fbs_supply is not None:
            raise PackagingTaskServiceError("invalid_qty")
        raise PackagingTaskServiceError("line_already_packed")
    if qty > remaining:
        raise PackagingTaskServiceError("invalid_qty")
    before_packed = int(line.qty_packed_in_task)
    if fbs_supply is not None:
        try:
            pack_result = await record_fbs_pack_progress(
                session,
                tenant_id,
                task,
                line,
                qty,
                order_id=order_id,
                acting_user_id=acting_user_id,
                idempotency_key=idempotency_key,
            )
        except FbsPackagingIntegrationError as exc:
            raise PackagingTaskServiceError(exc.code, message=exc.message) from exc
        _touch_task(task)
        packed_delta = int(line.qty_packed_in_task) - before_packed
        if packed_delta > 0:
            await _add_task_event(
                session,
                task,
                action=action,
                quantity=packed_delta,
                line=line,
                acting_user_id=acting_user_id,
            )
        if acting_user_id is not None:
            await billing_svc.finalize_task_billing(
                session, task, completed_by_user_id=acting_user_id
            )
        await session.commit()
        loaded = await get_task(session, tenant_id, task_id)
        assert loaded is not None
        fulfilled_order = pack_result.units[-1].order if pack_result.units else None
        return PackProgressResult(
            task=loaded,
            fulfilled_order=fulfilled_order,
            warnings=pack_result.warnings,
        )

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
    await _add_task_event(
        session,
        task,
        action=action,
        quantity=qty,
        line=line,
        acting_user_id=acting_user_id,
    )
    if acting_user_id is not None:
        await billing_svc.finalize_task_billing(
            session, task, completed_by_user_id=acting_user_id
        )
    await session.commit()
    loaded = await get_task(session, tenant_id, task_id)
    assert loaded is not None
    return PackProgressResult(task=loaded)


def _line_matches_barcode(line: PackagingTaskLine, barcode: str) -> bool:
    product = line.product
    return barcode in {product.sku_code, product.wb_barcode}


async def record_pack_scan(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task_id: uuid.UUID,
    barcode: str,
    *,
    acting_user_id: uuid.UUID | None = None,
) -> PackProgressResult:
    cleaned = barcode.strip()
    if not cleaned:
        raise PackagingTaskServiceError("invalid_qty")
    task = await get_task(session, tenant_id, task_id)
    if task is None:
        raise PackagingTaskServiceError("not_found")
    if task.status in (STATUS_DONE, STATUS_CANCELLED):
        raise PackagingTaskServiceError("bad_status")
    matching = [line for line in task.lines if _line_matches_barcode(line, cleaned)]
    if not matching:
        raise PackagingTaskServiceError("unknown_barcode")
    open_line = next(
        (
            line
            for line in matching
            if qty_need_pack(line) - int(line.qty_packed_in_task) > 0
        ),
        None,
    )
    if open_line is None:
        raise PackagingTaskServiceError("line_already_packed")
    return await record_pack_progress(
        session,
        tenant_id,
        task_id,
        open_line.id,
        1,
        acting_user_id=acting_user_id,
        action=PACKAGING_EVENT_SCAN_PACK,
    )


async def mark_product_label_printed(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task_id: uuid.UUID,
    line_id: uuid.UUID,
    *,
    quantity: int,
    acting_user_id: uuid.UUID | None = None,
) -> PackagingTask:
    if quantity < 1:
        raise PackagingTaskServiceError("invalid_qty")
    task = await get_task(session, tenant_id, task_id)
    if task is None:
        raise PackagingTaskServiceError("not_found")
    if task.status == STATUS_CANCELLED:
        raise PackagingTaskServiceError("bad_status")
    line = next((ln for ln in task.lines if ln.id == line_id), None)
    if line is None:
        raise PackagingTaskServiceError("line_not_found")
    await _add_task_event(
        session,
        task,
        action=PACKAGING_EVENT_PRODUCT_LABEL_PRINT,
        quantity=quantity,
        line=line,
        acting_user_id=acting_user_id,
    )
    _touch_task(task)
    await session.commit()
    loaded = await get_task(session, tenant_id, task_id)
    assert loaded is not None
    return loaded


async def undo_last_pack_action(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task_id: uuid.UUID,
    *,
    acting_user_id: uuid.UUID | None = None,
) -> PackagingTask:
    task = await get_task(session, tenant_id, task_id)
    if task is None:
        raise PackagingTaskServiceError("not_found")
    if task.status in (STATUS_DONE, STATUS_CANCELLED):
        raise PackagingTaskServiceError("bad_status")

    from app.services.fbs_packaging_integration_service import (
        get_supply_for_packaging_task,
    )

    if await get_supply_for_packaging_task(session, tenant_id, task_id) is not None:
        raise PackagingTaskServiceError("undo_not_supported")

    event = await session.scalar(
        select(PackagingTaskEvent)
        .where(
            PackagingTaskEvent.tenant_id == tenant_id,
            PackagingTaskEvent.task_id == task_id,
            PackagingTaskEvent.action.in_(REVERSIBLE_PACK_EVENTS),
            PackagingTaskEvent.reversed_at.is_(None),
        )
        .order_by(PackagingTaskEvent.event_sequence.desc())
        .limit(1)
    )
    if event is None or event.line_id is None or event.quantity < 1:
        raise PackagingTaskServiceError("undo_not_available")

    line = next((ln for ln in task.lines if ln.id == event.line_id), None)
    if line is None:
        raise PackagingTaskServiceError("undo_not_available")
    qty = int(event.quantity)
    if int(line.qty_packed_in_task) < qty:
        raise PackagingTaskServiceError("undo_not_available")

    if _is_mp_unload_task(task):
        line.qty_packed_in_task = int(line.qty_packed_in_task) - qty
    else:
        try:
            await inv_svc.reverse_packaging_convert(
                session,
                tenant_id=tenant_id,
                product_id=line.product_id,
                storage_location_id=line.storage_location_id,
                quantity=qty,
            )
        except ValueError as exc:
            if str(exc) == "insufficient_packed":
                raise PackagingTaskServiceError("undo_not_available") from exc
            raise
        line.qty_packed_in_task = int(line.qty_packed_in_task) - qty

    now = datetime.now(UTC)
    event.reversed_at = now
    event.reversed_by_user_id = acting_user_id
    _touch_task(task)
    await _add_task_event(
        session,
        task,
        action=PACKAGING_EVENT_UNDO_LAST,
        quantity=qty,
        line=line,
        acting_user_id=acting_user_id,
        note=f"undo {event.action}",
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

    from app.services.fbs_packaging_integration_service import (
        get_supply_for_packaging_task,
    )

    fbs_supply = await get_supply_for_packaging_task(session, tenant_id, task_id)
    if acknowledge_all_packed and fbs_supply is not None:
        raise PackagingTaskServiceError("fbs_acknowledge_not_allowed")

    if _is_mp_unload_task(task):
        await sync_mp_task_packed_from_boxes(session, tenant_id, task)

    if not is_task_complete(task):
        raise PackagingTaskServiceError("packaging_incomplete")

    await _assert_marking_done_for_task(session, tenant_id, task)

    task.status = STATUS_DONE
    task.updated_at = datetime.now(UTC)
    await _add_task_event(
        session,
        task,
        action=PACKAGING_EVENT_COMPLETE,
        quantity=sum(qty_done(line) for line in task.lines),
        acting_user_id=acting_user_id,
    )
    if acting_user_id is not None:
        await billing_svc.finalize_task_billing(
            session, task, completed_by_user_id=acting_user_id
        )
    else:
        task.completed_at = datetime.now(UTC)
        task.completed_by_user_id = None
    from app.services.fbs_packaging_integration_service import (
        sync_fbs_supply_on_packaging_done,
    )

    await sync_fbs_supply_on_packaging_done(session, tenant_id, task.id)
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
