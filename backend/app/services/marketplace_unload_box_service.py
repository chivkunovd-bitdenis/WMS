"""Boxes and barcode scanning for marketplace unload requests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy import func, select
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
from app.models.storage_location import StorageLocation
from app.services import marketplace_unload_collect_service as collect_svc
from app.services import marketplace_unload_service as mu_svc
from app.services import tenant_settings_service as tenant_settings_svc
from app.services import warehouse_box_service as wh_box_svc
from app.services import warehouse_map_service
from app.services.inventory_container_service import (
    ContainerKind,
    InventoryContainerScanError,
    resolve_container_scan,
    validate_container,
)
from app.services.marketplace_unload_pick_service import (
    MarketplaceUnloadPickError,
    find_location_by_barcode,
)
from app.services.marketplace_unload_status import DELETE_EDITABLE_STATUSES
from app.services.seller_wb_catalog_service import list_seller_wb_catalog_rows

ALLOWED_BOX_PRESETS = frozenset({"60_40_40", "30_20_30"})
MAX_BATCH_BOX_COUNT = 50


class MarketplaceUnloadBoxError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class BoxScanResult:
    """TSD scan flow: location (optional) → ready box / product → box line update."""

    kind: Literal["location", "container", "product", "ready_box"]
    storage_location_id: uuid.UUID | None = None
    location_code: str | None = None
    container_kind: ContainerKind | None = None
    container_id: uuid.UUID | None = None
    container_code: str | None = None
    box_line: MarketplaceUnloadBoxLine | None = None
    picked_qty: int | None = None
    lines_added: int | None = None
    total_qty: int | None = None


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
    stmt = (
        select(MarketplaceUnloadRequest)
        .where(
            MarketplaceUnloadRequest.id == request_id,
            MarketplaceUnloadRequest.tenant_id == tenant_id,
        )
        .options(selectinload(MarketplaceUnloadRequest.lines))
        .execution_options(populate_existing=True)
    )
    req = (await session.execute(stmt)).scalar_one_or_none()
    if req is None:
        raise MarketplaceUnloadBoxError("not_found")
    if req.status not in mu_svc.EXECUTION_STATUSES:
        raise MarketplaceUnloadBoxError("not_editable")
    if req.seller_id is None:
        raise MarketplaceUnloadBoxError("seller_required")
    return req


async def _open_box_for_request(
    session: AsyncSession, request_id: uuid.UUID
) -> MarketplaceUnloadBox | None:
    return await collect_svc.get_open_box(session, request_id)


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
    mu_svc.enter_collecting_if_needed(req)
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

    mu_svc.enter_collecting_if_needed(req)
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


async def _finish_box_collection(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID
) -> None:
    """Commit only after every requested line passed source and quantity checks."""
    from app.services import packaging_task_service as pkg_svc

    task = await pkg_svc.get_task_for_unload(session, tenant_id, request_id)
    if task is not None:
        # This existing synchronizer owns the final commit, including box/source changes.
        await pkg_svc.sync_lines_from_pick_allocations(
            session, tenant_id, task, reload_result=False
        )
    else:
        await session.commit()


async def _source_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    kind: ContainerKind,
    container_id: uuid.UUID,
) -> uuid.UUID:
    """INB putaway can leave stale metadata; use its sole current stock location."""
    await validate_container(session, tenant_id, warehouse_id, kind, container_id)
    locations = list((await session.scalars(
        select(StorageLocation)
        .join(InventoryBalance, InventoryBalance.storage_location_id == StorageLocation.id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.container_kind == kind,
            InventoryBalance.container_id == container_id,
            InventoryBalance.quantity > 0,
        ).distinct()
    )).all())
    if len(locations) > 1 or any(
        location.tenant_id != tenant_id or location.warehouse_id != warehouse_id
        for location in locations
    ):
        raise MarketplaceUnloadBoxError("invalid_container_reference")
    if locations:
        return locations[0].id
    # Empty sources keep their identity; availability still checks this container only.
    return await warehouse_map_service.resolve_container_location(
        session, tenant_id, warehouse_id, kind, container_id
    )


async def _collect_current_box_contents(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    req: MarketplaceUnloadRequest,
    box_id: uuid.UUID,
    barcode: str,
    *,
    allow_over_plan: bool,
    actor_user_id: uuid.UUID | None,
) -> tuple[int, int]:
    try:
        source = await resolve_container_scan(session, tenant_id, req.warehouse_id, barcode)
        location_id = await _source_location(
            session, tenant_id, req.warehouse_id, source.kind, source.id
        )
    except (
        InventoryContainerScanError, ValueError, warehouse_map_service.WarehouseMapError
    ) as exc:
        raise MarketplaceUnloadBoxError("invalid_container_reference") from exc
    if source.kind != "box":
        raise MarketplaceUnloadBoxError("box_barcode_unknown")
    balances = list((await session.scalars(
        select(InventoryBalance).where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.container_kind == source.kind,
            InventoryBalance.container_id == source.id,
            InventoryBalance.quantity > 0,
        ).order_by(InventoryBalance.product_id)
    )).all())
    if not balances:
        raise MarketplaceUnloadBoxError("box_empty")
    if any(balance.storage_location_id != location_id for balance in balances):
        raise MarketplaceUnloadBoxError("invalid_container_reference")
    total = 0
    for balance in balances:
        quantity = int(balance.quantity)
        try:
            await collect_svc.collect_into_box(
                session, tenant_id, req.id,
                box_id=box_id,
                storage_location_id=location_id,
                product_id=balance.product_id,
                quantity=quantity,
                allow_over_plan=allow_over_plan,
                actor_user_id=actor_user_id,
                container_kind=source.kind,
                container_id=source.id,
            )
        except MarketplaceUnloadPickError as exc:
            raise _map_collect_err(exc) from None
        total += quantity
    return len(balances), total


async def collect_ready_box_into_open_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box_id: uuid.UUID,
    *,
    barcode: str,
    allow_over_plan: bool = False,
    actor_user_id: uuid.UUID | None,
) -> BoxScanResult:
    """Explicit whole-box operation: consume only this container's current stock."""
    box = await session.get(MarketplaceUnloadBox, box_id)
    if box is None:
        raise MarketplaceUnloadBoxError("box_not_found")
    req = await _request_for_picking(session, tenant_id, box.request_id)
    lines_added, total_qty = await _collect_current_box_contents(
        session, tenant_id, req, box_id, barcode,
        allow_over_plan=allow_over_plan, actor_user_id=actor_user_id,
    )
    mu_svc.enter_collecting_if_needed(req)
    await _finish_box_collection(session, tenant_id, req.id)
    return BoxScanResult(kind="ready_box", lines_added=lines_added, total_qty=total_qty)


async def scan_barcode_into_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box_id: uuid.UUID,
    *,
    barcode: str,
    request_id: uuid.UUID | None = None,
    product_id_hint: uuid.UUID | None = None,
    storage_location_id: uuid.UUID | None,
    quantity: int = 1,
    allow_over_plan: bool = False,
    actor_user_id: uuid.UUID | None,
    container_kind: ContainerKind | None = None,
    container_id: uuid.UUID | None = None,
) -> BoxScanResult:
    """Scan flow for TSD/web: optional location barcode, then product → box line."""
    raw = barcode.strip()
    if not raw:
        raise MarketplaceUnloadBoxError("barcode_empty")
    if quantity < 1:
        raise MarketplaceUnloadBoxError("invalid_quantity")

    box = await session.get(MarketplaceUnloadBox, box_id)
    if box is None or (request_id is not None and box.request_id != request_id):
        raise MarketplaceUnloadBoxError("box_not_found")

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

    # A storage container selects the exact source; it does not move its contents.
    try:
        container = await resolve_container_scan(session, tenant_id, req.warehouse_id, raw)
    except InventoryContainerScanError as exc:
        if exc.code != "container_scan_not_found":
            raise MarketplaceUnloadBoxError("invalid_container_reference") from exc
    else:
        try:
            location_id = await _source_location(
                session, tenant_id, req.warehouse_id, container.kind, container.id
            )
        except (ValueError, warehouse_map_service.WarehouseMapError) as exc:
            raise MarketplaceUnloadBoxError("invalid_container_reference") from exc
        return BoxScanResult(
            kind="container",
            storage_location_id=location_id,
            container_kind=container.kind,
            container_id=container.id,
            container_code=container.code,
        )

    if product_id_hint is None:
        idx = await _barcode_index_for_seller(session, tenant_id, req.seller_id)
        product_id = idx.get(raw)
        if product_id is None:
            raise MarketplaceUnloadBoxError("barcode_unknown")
    else:
        product_id = product_id_hint

    if not await _product_in_shipment(session, req.id, product_id):
        raise MarketplaceUnloadBoxError("product_not_in_shipment")

    line = await add_manual_qty_to_box(
        session,
        tenant_id,
        box_id,
        storage_location_id=storage_location_id,
        product_id=product_id,
        quantity=quantity,
        actor_user_id=actor_user_id,
        allow_over_plan=allow_over_plan,
        container_kind=container_kind,
        container_id=container_id,
    )
    return BoxScanResult(
        kind="product",
        storage_location_id=storage_location_id,
        box_line=line,
        picked_qty=await collect_svc.picked_qty_for_product(session, box.request_id, product_id),
    )


async def boxed_qty_for_product(
    session: AsyncSession, request_id: uuid.UUID, product_id: uuid.UUID
) -> int:
    """Сколько единиц товара уже разложено по коробам этой отгрузки."""
    stmt = (
        select(func.coalesce(func.sum(MarketplaceUnloadBoxLine.quantity), 0))
        .join(MarketplaceUnloadBox, MarketplaceUnloadBox.id == MarketplaceUnloadBoxLine.box_id)
        .where(
            MarketplaceUnloadBox.request_id == request_id,
            MarketplaceUnloadBoxLine.product_id == product_id,
        )
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def _place_picked_into_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box: MarketplaceUnloadBox,
    *,
    product_id: uuid.UUID,
    quantity: int,
) -> MarketplaceUnloadBoxLine:
    """Переложить уже подобранный товар в короб.

    Подбор его со склада уже списал и создал аллокацию, поэтому второй раз
    трогать остатки нельзя — иначе одна и та же единица спишется дважды.
    Здесь только строка короба и пересчёт прогресса упаковки.
    """
    stmt = select(MarketplaceUnloadBoxLine).where(
        MarketplaceUnloadBoxLine.box_id == box.id,
        MarketplaceUnloadBoxLine.product_id == product_id,
    )
    line = (await session.execute(stmt)).scalar_one_or_none()
    if line is None:
        line = MarketplaceUnloadBoxLine(
            box_id=box.id, product_id=product_id, quantity=quantity
        )
        session.add(line)
    else:
        line.quantity = int(line.quantity) + quantity

    from app.services import packaging_task_service as pkg_svc

    task = await pkg_svc.get_task_for_unload(session, tenant_id, box.request_id)
    await session.flush()
    if task is not None:
        await pkg_svc.sync_mp_task_packed_from_boxes(session, tenant_id, task)
    line_id = line.id
    await session.flush()
    # Load the product for serialization; the public operation owns the commit.
    loaded = (
        await session.execute(
            select(MarketplaceUnloadBoxLine)
            .where(MarketplaceUnloadBoxLine.id == line_id)
            .options(selectinload(MarketplaceUnloadBoxLine.product))
        )
    ).scalar_one()
    return loaded


async def add_manual_qty_to_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box_id: uuid.UUID,
    *,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID | None,
    quantity: int,
    actor_user_id: uuid.UUID | None,
    allow_over_plan: bool = False,
    container_kind: ContainerKind | None = None,
    container_id: uuid.UUID | None = None,
) -> MarketplaceUnloadBoxLine:
    if quantity < 1:
        raise MarketplaceUnloadBoxError("invalid_quantity")

    box = await session.get(MarketplaceUnloadBox, box_id)
    if box is None:
        raise MarketplaceUnloadBoxError("box_not_found")

    req = await _request_for_picking(session, tenant_id, box.request_id)
    if not await _product_in_shipment(session, req.id, product_id):
        raise MarketplaceUnloadBoxError("product_not_in_shipment")

    if (container_kind is None) != (container_id is None):
        raise MarketplaceUnloadBoxError("invalid_container_reference")
    if container_kind is not None and container_id is not None:
        try:
            await validate_container(
                session, tenant_id, req.warehouse_id, container_kind, container_id
            )
            source_location_id = await _source_location(
                session, tenant_id, req.warehouse_id, container_kind, container_id
            )
        except (ValueError, warehouse_map_service.WarehouseMapError) as exc:
            raise MarketplaceUnloadBoxError("invalid_container_reference") from exc
        if storage_location_id is not None and storage_location_id != source_location_id:
            raise MarketplaceUnloadBoxError("invalid_container_reference")
        storage_location_id = source_location_id

    # Serialize placement with collection: two scans cannot spend the same picked unit.
    await session.execute(
        select(MarketplaceUnloadRequest.id)
        .where(MarketplaceUnloadRequest.id == req.id)
        .with_for_update()
    )

    # Упаковка идёт после подбора, и товар к этому моменту уже снят со склада.
    # Раньше любое наполнение короба шло через подбор, а тот отказывал с
    # plan_limit_exceeded, потому что план уже выбран: отгрузка, подобранная
    # россыпью, становилась незавершаемой навсегда. Поэтому сначала кладём в
    # короб то, что уже подобрано и ещё не разложено, и только недостающее
    # добираем со склада обычным подбором.
    picked = await collect_svc.picked_qty_for_product(session, box.request_id, product_id)
    boxed = await boxed_qty_for_product(session, box.request_id, product_id)
    from_picked = max(0, min(quantity, picked - boxed))
    to_collect = quantity - from_picked

    line: MarketplaceUnloadBoxLine | None = None
    if from_picked > 0:
        line = await _place_picked_into_box(
            session, tenant_id, box, product_id=product_id, quantity=from_picked
        )
    if to_collect > 0:
        try:
            result = await collect_svc.collect_into_box(
                session,
                tenant_id,
                box.request_id,
                box_id=box_id,
                storage_location_id=storage_location_id,
                product_id=product_id,
                quantity=to_collect,
                actor_user_id=actor_user_id,
                allow_over_plan=allow_over_plan,
                container_kind=container_kind,
                container_id=container_id,
            )
        except MarketplaceUnloadPickError as exc:
            raise _map_collect_err(exc) from None
        line = result.box_line
    assert line is not None
    await _finish_box_collection(session, tenant_id, req.id)
    return line


async def attach_existing_box_by_barcode(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    barcode: str,
    box_preset: str = "60_40_40",
    allow_over_plan: bool = False,
    actor_user_id: uuid.UUID | None,
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

    await _collect_current_box_contents(
        session, tenant_id, req, mp_box.id, barcode,
        allow_over_plan=allow_over_plan, actor_user_id=actor_user_id,
    )

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
    mu_svc.enter_collecting_if_needed(req)
    await _finish_box_collection(session, tenant_id, req.id)
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
            selectinload(MarketplaceUnloadBox.lines).selectinload(MarketplaceUnloadBoxLine.product),
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
    actor_user_id: uuid.UUID | None,
) -> MarketplaceUnloadBoxLine | None:
    box = await session.get(MarketplaceUnloadBox, box_id)
    if box is None:
        raise MarketplaceUnloadBoxError("box_not_found")
    req = await mu_svc.get_request(session, tenant_id, box.request_id)
    if req is None:
        raise MarketplaceUnloadBoxError("not_found")
    if req.status not in DELETE_EDITABLE_STATUSES:
        raise MarketplaceUnloadBoxError("not_draft")
    try:
        return await collect_svc.remove_from_box(
            session,
            tenant_id,
            box.request_id,
            box_id=box_id,
            line_id=line_id,
            quantity=quantity,
            actor_user_id=actor_user_id,
        )
    except MarketplaceUnloadPickError as exc:
        raise _map_collect_err(exc) from None


async def delete_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box_id: uuid.UUID,
) -> None:
    box = await session.get(MarketplaceUnloadBox, box_id)
    if box is None:
        raise MarketplaceUnloadBoxError("box_not_found")
    await session.refresh(box, attribute_names=["lines"])
    await _request_for_picking(session, tenant_id, box.request_id)
    total_stmt = select(
        func.coalesce(func.sum(MarketplaceUnloadBoxLine.quantity), 0)
    ).where(MarketplaceUnloadBoxLine.box_id == box_id)
    total_qty = int((await session.execute(total_stmt)).scalar_one())
    if total_qty > 0:
        raise MarketplaceUnloadBoxError("box_not_empty")
    await session.delete(box)
    await session.commit()


async def copy_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None,
) -> MarketplaceUnloadBox:
    """Duplicate a closed source box into a new closed box (REV-FIX-015).

    Intentionally closed: copy is a snapshot for shipping labels / repeat shipment,
    not for further manual add (use batch create for open boxes).
    """
    src_stmt = (
        select(MarketplaceUnloadBox)
        .where(MarketplaceUnloadBox.id == box_id)
        .options(
            selectinload(MarketplaceUnloadBox.lines),
            selectinload(MarketplaceUnloadBox.warehouse_box),
        )
        .execution_options(populate_existing=True)
    )
    src = (await session.execute(src_stmt)).scalar_one_or_none()
    if src is None:
        raise MarketplaceUnloadBoxError("box_not_found")
    await session.refresh(src, attribute_names=["lines"])
    req = await _request_for_picking(session, tenant_id, src.request_id)
    if not src.lines:
        raise MarketplaceUnloadBoxError("box_empty")

    picked = await collect_svc.picked_qty_by_product(session, req.id)
    plan_stmt = select(
        MarketplaceUnloadLine.product_id,
        MarketplaceUnloadLine.quantity,
    ).where(MarketplaceUnloadLine.request_id == req.id)
    plan_by_product = {
        product_id: int(quantity)
        for product_id, quantity in (await session.execute(plan_stmt)).all()
    }
    for ln in src.lines:
        pid = ln.product_id
        add_qty = int(ln.quantity)
        if add_qty < 1:
            continue
        current = picked.get(pid, 0)
        plan_qty = plan_by_product.get(pid, 0)
        if current + add_qty > plan_qty:
            raise MarketplaceUnloadBoxError("plan_limit_exceeded")

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
                    container_kind=cast(ContainerKind | None, alloc.container_kind),
                    container_id=alloc.container_id,
                    product_id=ln.product_id,
                    quantity=chunk,
                    require_open_box=False,
                    actor_user_id=actor_user_id,
                )
            except MarketplaceUnloadPickError as exc:
                raise _map_collect_err(exc) from None
            remaining -= chunk
        if remaining > 0:
            raise MarketplaceUnloadBoxError("insufficient_available")

    new_box.closed_at = datetime.now(tz=UTC)
    await _finish_box_collection(session, tenant_id, req.id)

    stmt = (
        select(MarketplaceUnloadBox)
        .where(MarketplaceUnloadBox.id == new_box.id)
        .options(
            selectinload(MarketplaceUnloadBox.lines).selectinload(MarketplaceUnloadBoxLine.product),
            selectinload(MarketplaceUnloadBox.warehouse_box),
        )
    )
    res = await session.execute(stmt)
    return res.scalars().unique().one()
