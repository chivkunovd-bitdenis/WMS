"""Unified collect: take from storage location into shipment box (+ pick allocation)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.marketplace_unload import (
    MarketplaceUnloadBox,
    MarketplaceUnloadBoxLine,
    MarketplaceUnloadLine,
    MarketplaceUnloadPickAllocation,
    MarketplaceUnloadRequest,
)
from app.models.packaging_task import PackagingTaskLine
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.services import inventory_service
from app.services import marketplace_unload_service as mu_svc
from app.services import sorting_location_service as sort_loc_svc
from app.services import tenant_settings_service as tenant_settings_svc
from app.services.inventory_container_service import ContainerKind
from app.services.marketplace_unload_pick_service import (
    PICK_EDITABLE_STATUSES,
    MarketplaceUnloadPickError,
)
from app.services.pick_option_location_service import (
    available_pick_source_quantity,
    list_pick_option_locations,
)


@dataclass(frozen=True)
class CollectResult:
    box_line: MarketplaceUnloadBoxLine
    allocation: MarketplaceUnloadPickAllocation
    picked_qty: int


@dataclass(frozen=True)
class PickAllocationResult:
    allocation: MarketplaceUnloadPickAllocation
    product: Product
    picked_qty: int


@dataclass(frozen=True)
class SetPickAllocationResult:
    """Ответ set_pick_allocation. Не привязан к ORM-объекту аллокации, потому что
    при обнулении строка удаляется — обращаться к ней после commit небезопасно."""

    id: uuid.UUID
    product: Product
    storage_location_id: uuid.UUID
    location_code: str
    quantity: int
    picked_qty: int


@dataclass
class _AllocationRollback:
    allocation: MarketplaceUnloadPickAllocation
    quantity: int = 0
    quantity_packed: int = 0
    quantity_source_known: int = 0


async def picked_qty_by_product(
    session: AsyncSession, request_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    """Источник истины — аллокации подбора (MarketplaceUnloadPickAllocation), а не
    содержимое коробов. Подбор больше не создаёт и не трогает короба (решение
    заказчика 2026-08-16: «автосоздавать короба не надо, и блокировать их тоже не
    надо без коробов») — короб теперь исключительно явное действие оператора на
    упаковке, поэтому «сколько подобрано» не может зависеть от того, лежит ли товар
    физически в коробе."""
    stmt = (
        select(
            MarketplaceUnloadPickAllocation.product_id,
            func.coalesce(func.sum(MarketplaceUnloadPickAllocation.quantity), 0),
        )
        .where(MarketplaceUnloadPickAllocation.request_id == request_id)
        .group_by(MarketplaceUnloadPickAllocation.product_id)
    )
    res = await session.execute(stmt)
    return {row[0]: int(row[1]) for row in res.all()}


async def picked_qty_for_product(
    session: AsyncSession, request_id: uuid.UUID, product_id: uuid.UUID
) -> int:
    stmt = select(
        func.coalesce(func.sum(MarketplaceUnloadPickAllocation.quantity), 0)
    ).where(
        MarketplaceUnloadPickAllocation.request_id == request_id,
        MarketplaceUnloadPickAllocation.product_id == product_id,
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def get_open_box(
    session: AsyncSession, request_id: uuid.UUID
) -> MarketplaceUnloadBox | None:
    stmt = select(MarketplaceUnloadBox).where(
        MarketplaceUnloadBox.request_id == request_id,
        MarketplaceUnloadBox.closed_at.is_(None),
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


DEFAULT_PICK_BOX_PRESET = "60_40_40"


async def get_or_create_open_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    warehouse_id: uuid.UUID,
) -> MarketplaceUnloadBox:
    """Подбор больше не требует, чтобы оператор открывал короб вручную (итерация
    2026-08-14, MP/FBO пункт 3): состав короба определяется на упаковке. Короб как
    внутренний контейнер для подобранного количества создаётся прозрачно, если его
    ещё нет."""
    existing = await get_open_box(session, request_id)
    if existing is not None:
        return existing
    from app.services import warehouse_box_service as wh_box_svc

    wh_box = await wh_box_svc.create_warehouse_box(
        session, tenant_id, warehouse_id=warehouse_id
    )
    box = MarketplaceUnloadBox(
        request_id=request_id,
        box_preset=DEFAULT_PICK_BOX_PRESET,
        warehouse_box_id=wh_box.id,
    )
    session.add(box)
    await session.flush()
    return box


async def _request_for_collect(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID
) -> MarketplaceUnloadRequest:
    req = await mu_svc.get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadPickError("not_found")
    if req.status not in PICK_EDITABLE_STATUSES:
        raise MarketplaceUnloadPickError("not_editable")
    if req.seller_id is None:
        raise MarketplaceUnloadPickError("seller_required")
    return req


async def _request_and_plan_for_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    product_id: uuid.UUID,
) -> tuple[MarketplaceUnloadRequest, int]:
    stmt = select(MarketplaceUnloadRequest).where(
        MarketplaceUnloadRequest.id == request_id,
        MarketplaceUnloadRequest.tenant_id == tenant_id,
    )
    req = (await session.execute(stmt)).scalar_one_or_none()
    if req is None:
        raise MarketplaceUnloadPickError("not_found")
    if req.status not in PICK_EDITABLE_STATUSES:
        raise MarketplaceUnloadPickError("not_editable")
    if req.seller_id is None:
        raise MarketplaceUnloadPickError("seller_required")
    plan_stmt = select(MarketplaceUnloadLine.quantity).where(
        MarketplaceUnloadLine.request_id == request_id,
        MarketplaceUnloadLine.product_id == product_id,
    )
    plan_qty = (await session.execute(plan_stmt)).scalar_one_or_none()
    if plan_qty is None:
        raise MarketplaceUnloadPickError("product_not_in_shipment")
    return req, int(plan_qty)


async def _product_in_shipment(
    session: AsyncSession, request_id: uuid.UUID, product_id: uuid.UUID
) -> bool:
    stmt = select(MarketplaceUnloadLine.id).where(
        MarketplaceUnloadLine.request_id == request_id,
        MarketplaceUnloadLine.product_id == product_id,
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none() is not None


async def _validate_storage_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    storage_location_id: uuid.UUID,
) -> StorageLocation:
    loc = await session.get(StorageLocation, storage_location_id)
    if loc is None or loc.tenant_id != tenant_id or loc.warehouse_id != warehouse_id:
        raise MarketplaceUnloadPickError("location_not_found")
    return loc


async def resolve_collect_storage_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID | None,
    *,
    request_id: uuid.UUID,
    increment_qty: int,
) -> uuid.UUID:
    """Single path: address-storage flag drives cell requirement (DEC-005)."""
    address_on = await tenant_settings_svc.is_address_storage_enabled(session, tenant_id)
    if not address_on:
        if storage_location_id is not None:
            await _validate_storage_location(
                session, tenant_id, warehouse_id, storage_location_id
            )
            return storage_location_id
        rows = await list_pick_option_locations(
            session, tenant_id, warehouse_id, [product_id], {},
            marketplace_unload_request_id=request_id,
        )
        candidates = [(row.storage_location_id, row.available)
                      for row in rows[product_id] if row.available >= increment_qty]
        if not candidates:
            raise MarketplaceUnloadPickError("insufficient_available")
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    if storage_location_id is not None:
        await _validate_storage_location(
            session, tenant_id, warehouse_id, storage_location_id
        )
        return storage_location_id

    cell_rows = await inventory_service.list_locations_for_product_in_warehouse(
        session, tenant_id, warehouse_id, product_id
    )
    if cell_rows:
        raise MarketplaceUnloadPickError("location_required")

    sorting = await sort_loc_svc.get_or_create_sorting_location(
        session, tenant_id, warehouse_id
    )
    return sorting.id


async def collect_into_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    box_id: uuid.UUID | None = None,
    storage_location_id: uuid.UUID | None = None,
    product_id: uuid.UUID,
    quantity: int,
    require_open_box: bool = False,
    allow_over_plan: bool = False,
    actor_user_id: uuid.UUID | None,
    container_kind: ContainerKind | None = None,
    container_id: uuid.UUID | None = None,
) -> CollectResult:
    if quantity < 1:
        raise MarketplaceUnloadPickError("invalid_quantity")

    req, plan_qty = await _request_and_plan_for_product(
        session, tenant_id, request_id, product_id
    )

    box: MarketplaceUnloadBox | None
    if box_id is not None:
        box = await session.get(MarketplaceUnloadBox, box_id)
        if box is None or box.request_id != request_id:
            raise MarketplaceUnloadPickError("box_not_found")
        if require_open_box and box.closed_at is not None:
            raise MarketplaceUnloadPickError("box_closed")
    else:
        box = await get_or_create_open_box(session, tenant_id, request_id, req.warehouse_id)
        box_id = box.id

    prod = await session.get(Product, product_id)
    if prod is None or prod.tenant_id != tenant_id:
        raise MarketplaceUnloadPickError("product_not_found")
    if req.seller_id is not None and prod.seller_id != req.seller_id:
        raise MarketplaceUnloadPickError("product_seller_mismatch")

    lock_stmt = (
        select(MarketplaceUnloadRequest.id)
        .where(
            MarketplaceUnloadRequest.id == request_id,
            MarketplaceUnloadRequest.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    await session.execute(lock_stmt)

    picked = await picked_qty_for_product(session, request_id, product_id)
    if not allow_over_plan and picked + quantity > plan_qty:
        raise MarketplaceUnloadPickError("plan_limit_exceeded")

    effective_location_id = await resolve_collect_storage_location(
        session,
        tenant_id,
        req.warehouse_id,
        product_id,
        storage_location_id,
        request_id=request_id,
        increment_qty=quantity,
    )

    alloc_stmt = (
        select(MarketplaceUnloadPickAllocation)
        .where(
            MarketplaceUnloadPickAllocation.request_id == request_id,
            MarketplaceUnloadPickAllocation.product_id == product_id,
            MarketplaceUnloadPickAllocation.storage_location_id == effective_location_id,
            MarketplaceUnloadPickAllocation.container_kind.is_(None)
            if container_kind is None
            else MarketplaceUnloadPickAllocation.container_kind == container_kind,
            MarketplaceUnloadPickAllocation.container_id.is_(None)
            if container_id is None
            else MarketplaceUnloadPickAllocation.container_id == container_id,
        )
        .with_for_update()
    )
    alloc_res = await session.execute(alloc_stmt)
    alloc = alloc_res.scalar_one_or_none()
    current_pick = int(alloc.quantity) if alloc is not None else 0
    new_pick = current_pick + quantity

    await inventory_service.lock_stock_product(session, tenant_id, product_id)
    available = await available_pick_source_quantity(
        session, tenant_id, product_id, effective_location_id, container_kind, container_id,
        marketplace_unload_request_id=request_id,
    )
    if available < quantity:
        raise MarketplaceUnloadPickError("insufficient_available")

    try:
        packed_quantity = await inventory_service.apply_marketplace_unload_pick(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=effective_location_id,
            quantity=quantity,
            marketplace_unload_request_id=request_id,
            actor_user_id=actor_user_id,
            container_kind=container_kind,
            container_id=container_id,
        )
    except ValueError as exc:
        if str(exc) == "insufficient stock":
            raise MarketplaceUnloadPickError("insufficient_available") from exc
        raise

    await mu_svc.reduce_reservation_for_collect(
        session, request_id, product_id, quantity
    )

    if alloc is None:
        alloc = MarketplaceUnloadPickAllocation(
            request_id=request_id,
            product_id=product_id,
            storage_location_id=effective_location_id,
            container_kind=container_kind,
            container_id=container_id,
            quantity=new_pick,
            quantity_packed=packed_quantity,
            quantity_source_known=quantity,
        )
        session.add(alloc)
    else:
        alloc.quantity = new_pick
        alloc.quantity_packed = int(alloc.quantity_packed or 0) + packed_quantity
        if alloc.quantity_source_known is None:
            alloc.quantity_source_known = quantity
        else:
            alloc.quantity_source_known = int(alloc.quantity_source_known) + quantity

    box_line_stmt = select(MarketplaceUnloadBoxLine).where(
        MarketplaceUnloadBoxLine.box_id == box_id,
        MarketplaceUnloadBoxLine.product_id == product_id,
    )
    box_line_res = await session.execute(box_line_stmt)
    box_line = box_line_res.scalar_one_or_none()
    if box_line is None:
        box_line = MarketplaceUnloadBoxLine(
            box_id=box_id,
            product_id=product_id,
            quantity=quantity,
            quantity_packed=packed_quantity,
            quantity_source_known=quantity,
        )
        session.add(box_line)
    else:
        box_line.quantity = int(box_line.quantity) + quantity
        box_line.quantity_packed = int(box_line.quantity_packed or 0) + packed_quantity
        if box_line.quantity_source_known is None:
            box_line.quantity_source_known = quantity
        else:
            box_line.quantity_source_known = int(box_line.quantity_source_known) + quantity

    mu_svc.enter_collecting_if_needed(req)
    await session.flush()

    picked = await picked_qty_for_product(session, request_id, product_id)
    stmt_alloc = (
        select(MarketplaceUnloadPickAllocation)
        .where(MarketplaceUnloadPickAllocation.id == alloc.id)
        .options(
            selectinload(MarketplaceUnloadPickAllocation.product),
            selectinload(MarketplaceUnloadPickAllocation.storage_location),
        )
    )
    res_alloc = await session.execute(stmt_alloc)
    alloc_loaded = res_alloc.scalar_one()
    stmt_line = (
        select(MarketplaceUnloadBoxLine)
        .where(MarketplaceUnloadBoxLine.id == box_line.id)
        .options(selectinload(MarketplaceUnloadBoxLine.product))
    )
    res_line = await session.execute(stmt_line)
    line_loaded = res_line.scalar_one()

    return CollectResult(
        box_line=line_loaded,
        allocation=alloc_loaded,
        picked_qty=picked,
    )


async def record_pick_allocation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    storage_location_id: uuid.UUID | None,
    product_id: uuid.UUID,
    quantity: int,
    allow_over_plan: bool = False,
    actor_user_id: uuid.UUID | None,
    container_kind: ContainerKind | None = None,
    container_id: uuid.UUID | None = None,
) -> PickAllocationResult:
    """Подбор двигает товар со склада в аллокацию подбора и НЕ трогает короба.

    Решение заказчика 2026-08-16: «автосоздавать короба не надо, и блокировать их
    тоже не надо без коробов». Раньше эта функция называлась collect_into_box и
    попутно создавала/находила открытый короб и строку в нём — так на подборе
    незаметно для оператора плодились короба (get_or_create_open_box). Короб теперь
    заводится только явным действием на упаковке (кнопка «Создать короб» или
    привязка готового короба сканом), а подбор — только storage → pick allocation.
    """
    if quantity < 1:
        raise MarketplaceUnloadPickError("invalid_quantity")

    req = await _request_for_collect(session, tenant_id, request_id)
    if not await _product_in_shipment(session, req.id, product_id):
        raise MarketplaceUnloadPickError("product_not_in_shipment")

    prod = await session.get(Product, product_id)
    if prod is None or prod.tenant_id != tenant_id:
        raise MarketplaceUnloadPickError("product_not_found")
    if req.seller_id is not None and prod.seller_id != req.seller_id:
        raise MarketplaceUnloadPickError("product_seller_mismatch")

    lock_stmt = (
        select(MarketplaceUnloadRequest.id)
        .where(
            MarketplaceUnloadRequest.id == request_id,
            MarketplaceUnloadRequest.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    await session.execute(lock_stmt)

    picked = await picked_qty_by_product(session, request_id)
    plan_qty = next(
        (int(ln.quantity) for ln in req.lines if ln.product_id == product_id),
        0,
    )
    if not allow_over_plan and picked.get(product_id, 0) + quantity > plan_qty:
        raise MarketplaceUnloadPickError("plan_limit_exceeded")

    effective_location_id = await resolve_collect_storage_location(
        session,
        tenant_id,
        req.warehouse_id,
        product_id,
        storage_location_id,
        request_id=request_id,
        increment_qty=quantity,
    )

    # Строка подбора заводится на связку «место + тара»: из одной ячейки можно
    # снять и россыпь, и содержимое короба, и это разные строки.
    alloc_stmt = (
        select(MarketplaceUnloadPickAllocation)
        .where(
            MarketplaceUnloadPickAllocation.request_id == request_id,
            MarketplaceUnloadPickAllocation.product_id == product_id,
            MarketplaceUnloadPickAllocation.storage_location_id == effective_location_id,
            MarketplaceUnloadPickAllocation.container_id.is_(None)
            if container_id is None
            else MarketplaceUnloadPickAllocation.container_id == container_id,
        )
        .with_for_update()
    )
    alloc_res = await session.execute(alloc_stmt)
    alloc = alloc_res.scalar_one_or_none()
    current_pick = int(alloc.quantity) if alloc is not None else 0
    new_pick = current_pick + quantity

    await inventory_service.lock_stock_product(session, tenant_id, product_id)
    available = await available_pick_source_quantity(
        session, tenant_id, product_id, effective_location_id, container_kind, container_id,
        marketplace_unload_request_id=request_id,
    )
    if available < quantity:
        raise MarketplaceUnloadPickError("insufficient_available")

    try:
        packed_quantity = await inventory_service.apply_marketplace_unload_pick(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=effective_location_id,
            quantity=quantity,
            marketplace_unload_request_id=request_id,
            actor_user_id=actor_user_id,
            container_kind=container_kind,
            container_id=container_id,
        )
    except ValueError as exc:
        if str(exc) == "insufficient stock":
            raise MarketplaceUnloadPickError("insufficient_available") from exc
        raise

    await mu_svc.reduce_reservation_for_collect(
        session, request_id, product_id, quantity
    )

    if alloc is None:
        alloc = MarketplaceUnloadPickAllocation(
            request_id=request_id,
            product_id=product_id,
            storage_location_id=effective_location_id,
            container_kind=container_kind,
            container_id=container_id,
            quantity=new_pick,
            quantity_packed=packed_quantity,
            quantity_source_known=quantity,
        )
        session.add(alloc)
    else:
        alloc.quantity = new_pick
        alloc.quantity_packed = int(alloc.quantity_packed or 0) + packed_quantity
        if alloc.quantity_source_known is None:
            alloc.quantity_source_known = quantity
        else:
            alloc.quantity_source_known = int(alloc.quantity_source_known) + quantity

    mu_svc.enter_collecting_if_needed(req)
    await session.commit()

    picked_after = await picked_qty_by_product(session, request_id)
    stmt_alloc = (
        select(MarketplaceUnloadPickAllocation)
        .where(MarketplaceUnloadPickAllocation.id == alloc.id)
        .options(
            selectinload(MarketplaceUnloadPickAllocation.product),
            selectinload(MarketplaceUnloadPickAllocation.storage_location),
        )
    )
    res_alloc = await session.execute(stmt_alloc)
    alloc_loaded = res_alloc.scalar_one()

    from app.services import packaging_task_service as pkg_svc

    pkg_task = await pkg_svc.get_task_for_unload(session, tenant_id, request_id)
    if pkg_task is not None:
        await pkg_svc.sync_lines_from_pick_allocations(session, tenant_id, pkg_task)

    return PickAllocationResult(
        allocation=alloc_loaded,
        product=prod,
        picked_qty=picked_after.get(product_id, 0),
    )


async def set_pick_allocation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    quantity: int,
    actor_user_id: uuid.UUID | None,
    container_kind: ContainerKind | None = None,
    container_id: uuid.UUID | None = None,
) -> SetPickAllocationResult:
    """Задать итоговое количество подбора по паре товар+ячейка (не прибавку, а
    итог) — PICK-01. Разница > 0 идёт через record_pick_allocation как есть,
    разница < 0 — тем же способом, каким remove_from_box возвращает товар в
    ячейку (reverse_marketplace_unload_pick + restore_reservation_for_remove),
    но по конкретной строке подбора, а не через _rollback_pick_allocations,
    которая разносит количество по всем ячейкам товара подряд.
    """
    if quantity < 0:
        raise MarketplaceUnloadPickError("invalid_quantity")

    req = await _request_for_collect(session, tenant_id, request_id)
    if not await _product_in_shipment(session, req.id, product_id):
        raise MarketplaceUnloadPickError("product_not_in_shipment")

    prod = await session.get(Product, product_id)
    if prod is None or prod.tenant_id != tenant_id:
        raise MarketplaceUnloadPickError("product_not_found")
    if req.seller_id is not None and prod.seller_id != req.seller_id:
        raise MarketplaceUnloadPickError("product_seller_mismatch")

    loc = await _validate_storage_location(
        session, tenant_id, req.warehouse_id, storage_location_id
    )

    lock_stmt = (
        select(MarketplaceUnloadRequest.id)
        .where(
            MarketplaceUnloadRequest.id == request_id,
            MarketplaceUnloadRequest.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    await session.execute(lock_stmt)

    # Итог задаётся по конкретному месту снятия: россыпь и каждый короб — своя
    # строка, иначе ввод в короб перетирал бы снятое россыпью.
    alloc_stmt = (
        select(MarketplaceUnloadPickAllocation)
        .where(
            MarketplaceUnloadPickAllocation.request_id == request_id,
            MarketplaceUnloadPickAllocation.product_id == product_id,
            MarketplaceUnloadPickAllocation.storage_location_id == storage_location_id,
            MarketplaceUnloadPickAllocation.container_id.is_(None)
            if container_id is None
            else MarketplaceUnloadPickAllocation.container_id == container_id,
        )
        .with_for_update()
    )
    alloc_res = await session.execute(alloc_stmt)
    alloc = alloc_res.scalar_one_or_none()
    current_qty = int(alloc.quantity) if alloc is not None else 0
    diff = quantity - current_qty

    if diff > 0:
        result = await record_pick_allocation(
            session,
            tenant_id,
            request_id,
            storage_location_id=storage_location_id,
            product_id=product_id,
            quantity=diff,
            actor_user_id=actor_user_id,
            container_kind=container_kind,
            container_id=container_id,
        )
        return SetPickAllocationResult(
            id=result.allocation.id,
            product=result.product,
            storage_location_id=result.allocation.storage_location_id,
            location_code=result.allocation.storage_location.code,
            quantity=int(result.allocation.quantity),
            picked_qty=result.picked_qty,
        )

    if diff == 0:
        picked_now = await picked_qty_by_product(session, request_id)
        return SetPickAllocationResult(
            id=alloc.id if alloc is not None else uuid.uuid4(),
            product=prod,
            storage_location_id=storage_location_id,
            location_code=loc.code,
            quantity=current_qty,
            picked_qty=picked_now.get(product_id, 0),
        )

    # diff < 0: current_qty > quantity >= 0, значит строка подбора существует.
    assert alloc is not None
    alloc_id = alloc.id
    remove_qty = -diff
    unknown_available = int(alloc.quantity) - int(alloc.quantity_source_known or 0)
    source_known_removed = max(0, remove_qty - unknown_available)
    packed_removed = min(int(alloc.quantity_packed or 0), source_known_removed)
    new_qty = current_qty - remove_qty
    if new_qty < 1:
        await session.delete(alloc)
    else:
        alloc.quantity = new_qty
        if alloc.quantity_packed is not None:
            alloc.quantity_packed = int(alloc.quantity_packed) - packed_removed
        if alloc.quantity_source_known is not None:
            alloc.quantity_source_known = (
                int(alloc.quantity_source_known) - source_known_removed
            )

    await inventory_service.reverse_marketplace_unload_pick(
        session,
        tenant_id=tenant_id,
        product_id=product_id,
        storage_location_id=storage_location_id,
        quantity=remove_qty,
        marketplace_unload_request_id=request_id,
        actor_user_id=actor_user_id,
        container_kind=container_kind,
        container_id=container_id,
        quantity_packed=packed_removed,
    )
    await mu_svc.restore_reservation_for_remove(
        session,
        request_id,
        product_id,
        remove_qty,
        tenant_id=tenant_id,
        warehouse_id=req.warehouse_id,
    )

    await session.commit()

    from app.services import packaging_task_service as pkg_svc

    pkg_task = await pkg_svc.get_task_for_unload(session, tenant_id, request_id)
    if pkg_task is not None:
        await pkg_svc.sync_lines_from_pick_allocations(session, tenant_id, pkg_task)

    picked_after = await picked_qty_by_product(session, request_id)
    return SetPickAllocationResult(
        id=alloc_id,
        product=prod,
        storage_location_id=storage_location_id,
        location_code=loc.code,
        quantity=max(0, new_qty),
        picked_qty=picked_after.get(product_id, 0),
    )


async def _rollback_pick_allocations(
    session: AsyncSession,
    request_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: int,
    quantity_packed: int,
    quantity_source_known: int,
) -> list[tuple[uuid.UUID, int, int]]:
    if (
        quantity_packed < 0
        or quantity_source_known < quantity_packed
        or quantity_source_known > quantity
    ):
        raise MarketplaceUnloadPickError("invalid_quantity")
    stmt = (
        select(MarketplaceUnloadPickAllocation)
        .where(
            MarketplaceUnloadPickAllocation.request_id == request_id,
            MarketplaceUnloadPickAllocation.product_id == product_id,
            MarketplaceUnloadPickAllocation.quantity > 0,
        )
        .with_for_update()
        .order_by(MarketplaceUnloadPickAllocation.quantity.desc())
    )
    res = await session.execute(stmt)
    allocations = list(res.scalars().all())
    chunks: dict[uuid.UUID, _AllocationRollback] = {}

    def take_from(
        alloc: MarketplaceUnloadPickAllocation,
        qty: int,
        packed: int,
        source_known: int,
    ) -> None:
        chunk = chunks.setdefault(alloc.id, _AllocationRollback(alloc))
        chunk.quantity += qty
        chunk.quantity_packed += packed
        chunk.quantity_source_known += source_known

    remaining_packed = quantity_packed
    for alloc in allocations:
        if remaining_packed < 1:
            break
        packed_available = int(alloc.quantity_packed or 0)
        already_taken = chunks.get(alloc.id, _AllocationRollback(alloc)).quantity_packed
        take = min(max(0, packed_available - already_taken), remaining_packed)
        if take:
            take_from(alloc, take, take, take)
            remaining_packed -= take
    if remaining_packed > 0:
        raise MarketplaceUnloadPickError("insufficient_picked")

    remaining_known_unpacked = quantity_source_known - quantity_packed
    for alloc in allocations:
        if remaining_known_unpacked < 1:
            break
        chunk = chunks.get(alloc.id, _AllocationRollback(alloc))
        known_available = int(alloc.quantity_source_known or 0) - int(
            alloc.quantity_packed or 0
        )
        take = min(
            max(0, known_available - (chunk.quantity_source_known - chunk.quantity_packed)),
            remaining_known_unpacked,
        )
        if take:
            take_from(alloc, take, 0, take)
            remaining_known_unpacked -= take
    if remaining_known_unpacked > 0:
        raise MarketplaceUnloadPickError("insufficient_picked")

    remaining_unknown = quantity - quantity_source_known
    for alloc in allocations:
        if remaining_unknown < 1:
            break
        chunk = chunks.get(alloc.id, _AllocationRollback(alloc))
        unknown_available = int(alloc.quantity) - int(alloc.quantity_source_known or 0)
        available_after_chunk = unknown_available - (
            chunk.quantity - chunk.quantity_source_known
        )
        take = min(max(0, available_after_chunk), remaining_unknown)
        if take:
            take_from(alloc, take, 0, 0)
            remaining_unknown -= take
    if remaining_unknown > 0:
        raise MarketplaceUnloadPickError("insufficient_picked")

    result: list[tuple[uuid.UUID, int, int]] = []
    for chunk in chunks.values():
        alloc = chunk.allocation
        alloc.quantity = int(alloc.quantity) - chunk.quantity
        if alloc.quantity_packed is not None:
            alloc.quantity_packed = int(alloc.quantity_packed) - chunk.quantity_packed
        if alloc.quantity_source_known is not None:
            alloc.quantity_source_known = (
                int(alloc.quantity_source_known) - chunk.quantity_source_known
            )
        if int(alloc.quantity) < 1:
            await session.delete(alloc)
        result.append((alloc.storage_location_id, chunk.quantity, chunk.quantity_packed))
    return result


async def _unknown_box_quantity(
    session: AsyncSession, request_id: uuid.UUID, product_id: uuid.UUID
) -> int:
    stmt = (
        select(
            func.coalesce(func.sum(MarketplaceUnloadBoxLine.quantity), 0),
            func.coalesce(func.sum(MarketplaceUnloadBoxLine.quantity_source_known), 0),
        )
        .join(MarketplaceUnloadBox, MarketplaceUnloadBox.id == MarketplaceUnloadBoxLine.box_id)
        .where(
            MarketplaceUnloadBox.request_id == request_id,
            MarketplaceUnloadBoxLine.product_id == product_id,
        )
    )
    boxed, known = (await session.execute(stmt)).one()
    return max(0, int(boxed or 0) - int(known or 0))


async def _boxed_quantity(
    session: AsyncSession, request_id: uuid.UUID, product_id: uuid.UUID
) -> int:
    stmt = (
        select(func.coalesce(func.sum(MarketplaceUnloadBoxLine.quantity), 0))
        .join(MarketplaceUnloadBox, MarketplaceUnloadBox.id == MarketplaceUnloadBoxLine.box_id)
        .where(
            MarketplaceUnloadBox.request_id == request_id,
            MarketplaceUnloadBoxLine.product_id == product_id,
        )
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


def _reduce_historical_baseline(
    line: PackagingTaskLine, *, historical_before: int, removed_unknown: int
) -> None:
    """Preserve the historic ready-first result when historic units are removed.

    This corrects the recorded historic calculation; it never claims a source
    for the removed physical unit or changes provenance fields on the box and
    allocation.
    """
    if removed_unknown < 1:
        return
    legacy_ready = line.qty_legacy_confirmed_packed
    legacy_work = line.qty_legacy_packed_in_task
    if legacy_ready is None or legacy_work is None:
        current_ready = int(line.qty_confirmed_packed)
        current_work = int(line.qty_packed_in_task)
        if current_ready + current_work != historical_before:
            return
        legacy_ready = current_ready
        legacy_work = current_work
    ready = int(legacy_ready)
    work = int(legacy_work)
    historical_total = ready + work
    if historical_total != historical_before:
        return
    remaining_historical = max(0, historical_total - removed_unknown)
    remaining_ready = min(ready, remaining_historical)
    line.qty_legacy_confirmed_packed = remaining_ready
    line.qty_legacy_packed_in_task = remaining_historical - remaining_ready
    line.qty_confirmed_packed = remaining_ready
    line.qty_packed_in_task = remaining_historical - remaining_ready


async def remove_from_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    box_id: uuid.UUID,
    line_id: uuid.UUID,
    quantity: int | None = None,
    actor_user_id: uuid.UUID | None,
) -> MarketplaceUnloadBoxLine | None:
    """Remove qty from box line and reverse inventory/reservation (DEC-016)."""
    req = await _request_for_collect(session, tenant_id, request_id)
    box = await session.get(MarketplaceUnloadBox, box_id)
    if box is None or box.request_id != request_id:
        raise MarketplaceUnloadPickError("box_not_found")

    line = await session.get(MarketplaceUnloadBoxLine, line_id)
    if line is None or line.box_id != box_id:
        raise MarketplaceUnloadPickError("line_not_found")

    line_qty = int(line.quantity)
    if line_qty < 1:
        raise MarketplaceUnloadPickError("line_empty")
    remove_qty = line_qty if quantity is None else quantity
    if remove_qty < 1 or remove_qty > line_qty:
        raise MarketplaceUnloadPickError("invalid_quantity")

    lock_stmt = (
        select(MarketplaceUnloadRequest.id)
        .where(
            MarketplaceUnloadRequest.id == request_id,
            MarketplaceUnloadRequest.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    await session.execute(lock_stmt)

    from app.services import packaging_task_service as pkg_svc

    pkg_task = await pkg_svc.get_task_for_unload(session, tenant_id, request_id)
    if pkg_task is not None:
        # Capture the historic baseline before changing the box composition.
        # A direct collect can reach this operation before a progress reread.
        await pkg_svc.sync_mp_task_packed_from_boxes(session, tenant_id, pkg_task)

    historical_before = await _unknown_box_quantity(session, request_id, line.product_id)
    unknown_available = line_qty - int(line.quantity_source_known or 0)
    source_known_removed = max(0, remove_qty - unknown_available)
    unknown_removed = remove_qty - source_known_removed
    packed_removed = min(int(line.quantity_packed or 0), source_known_removed)
    location_chunks = await _rollback_pick_allocations(
        session,
        request_id,
        line.product_id,
        remove_qty,
        packed_removed,
        source_known_removed,
    )
    for loc_id, chunk_qty, packed_qty in location_chunks:
        await inventory_service.reverse_marketplace_unload_pick(
            session,
            tenant_id=tenant_id,
            product_id=line.product_id,
            storage_location_id=loc_id,
            quantity=chunk_qty,
            marketplace_unload_request_id=request_id,
            actor_user_id=actor_user_id,
            quantity_packed=packed_qty,
        )

    await mu_svc.restore_reservation_for_remove(
        session,
        request_id,
        line.product_id,
        remove_qty,
        tenant_id=tenant_id,
        warehouse_id=req.warehouse_id,
    )

    new_qty = line_qty - remove_qty
    deleted_line_id = line.id
    if new_qty < 1:
        await session.delete(line)
    else:
        line.quantity = new_qty
        if line.quantity_packed is not None:
            line.quantity_packed = int(line.quantity_packed) - packed_removed
        if line.quantity_source_known is not None:
            line.quantity_source_known = int(line.quantity_source_known) - source_known_removed

    if pkg_task is not None:
        task_line = next((ln for ln in pkg_task.lines if ln.product_id == line.product_id), None)
        if task_line is not None:
            if await _boxed_quantity(session, request_id, line.product_id) == 0:
                # The last physical box unit has been returned. Keep the plan
                # line for recollection, but do not leave stale packed work.
                task_line.qty_confirmed_packed = 0
                task_line.qty_packed_in_task = 0
                task_line.qty_legacy_confirmed_packed = 0
                task_line.qty_legacy_packed_in_task = 0
            else:
                _reduce_historical_baseline(
                    task_line,
                    historical_before=historical_before,
                    removed_unknown=unknown_removed,
                )

    await session.commit()

    if pkg_task is not None:
        synced = await pkg_svc.sync_lines_from_pick_allocations(session, tenant_id, pkg_task)
        await pkg_svc.sync_mp_task_packed_from_boxes(session, tenant_id, synced.task)
        await session.commit()

    if new_qty < 1:
        return None
    stmt_line = (
        select(MarketplaceUnloadBoxLine)
        .where(MarketplaceUnloadBoxLine.id == deleted_line_id)
        .options(selectinload(MarketplaceUnloadBoxLine.product))
    )
    res_line = await session.execute(stmt_line)
    return res_line.scalar_one_or_none()


async def rollback_all_collected_for_cancel(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None,
) -> None:
    """TASK-019: on cancel, box stock returns to sorting (virtual buffer), not source cells."""
    lock_stmt = (
        select(MarketplaceUnloadRequest.id)
        .where(
            MarketplaceUnloadRequest.id == request_id,
            MarketplaceUnloadRequest.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    await session.execute(lock_stmt)

    alloc_stmt = (
        select(MarketplaceUnloadPickAllocation)
        .where(MarketplaceUnloadPickAllocation.request_id == request_id)
        .with_for_update()
    )
    alloc_res = await session.execute(alloc_stmt)
    product_qty: dict[uuid.UUID, tuple[int, int]] = {}
    for alloc in alloc_res.scalars().all():
        qty = int(alloc.quantity)
        if qty > 0:
            prior_qty, prior_packed = product_qty.get(alloc.product_id, (0, 0))
            product_qty[alloc.product_id] = (
                prior_qty + qty,
                prior_packed + int(alloc.quantity_packed or 0),
            )
        await session.delete(alloc)

    if product_qty:
        sorting_loc = await sort_loc_svc.get_or_create_sorting_location(
            session, tenant_id, warehouse_id
        )
        for product_id, (qty, packed_qty) in product_qty.items():
            await inventory_service.reverse_marketplace_unload_pick(
                session,
                tenant_id=tenant_id,
                product_id=product_id,
                storage_location_id=sorting_loc.id,
                quantity=qty,
                marketplace_unload_request_id=request_id,
                actor_user_id=actor_user_id,
                quantity_packed=packed_qty,
            )

    box_line_stmt = (
        select(MarketplaceUnloadBoxLine)
        .join(MarketplaceUnloadBox, MarketplaceUnloadBoxLine.box_id == MarketplaceUnloadBox.id)
        .where(MarketplaceUnloadBox.request_id == request_id)
    )
    line_res = await session.execute(box_line_stmt)
    for line in line_res.scalars().all():
        await session.delete(line)
