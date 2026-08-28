"""Pick allocations and ship (stock deduction) for marketplace unload."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.marketplace_unload import (
    MarketplaceUnloadLine,
    MarketplaceUnloadPickAllocation,
    MarketplaceUnloadRequest,
)
from app.models.storage_location import StorageLocation
from app.services import inventory_service
from app.services import marketplace_unload_service as mu_svc
from app.services import tenant_settings_service as tenant_settings_svc
from app.services.seller_wb_catalog_service import list_seller_wb_catalog_rows

PICK_EDITABLE_STATUSES = mu_svc.EXECUTION_STATUSES


class MarketplaceUnloadPickError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class PickAllocationRow:
    product_id: uuid.UUID
    storage_location_id: uuid.UUID | None
    quantity: int


@dataclass(frozen=True)
class PickOptionLocation:
    storage_location_id: uuid.UUID
    location_code: str
    quantity: int
    reserved: int
    available: int
    picked: int


@dataclass(frozen=True)
class PickOptionProduct:
    product_id: uuid.UUID
    sku_code: str
    product_name: str
    planned_qty: int
    picked_qty: int
    locations: list[PickOptionLocation]


@dataclass(frozen=True)
class PickScanResult:
    kind: Literal["location", "product"]
    storage_location_id: uuid.UUID | None = None
    location_code: str | None = None
    product_id: uuid.UUID | None = None
    sku_code: str | None = None
    product_name: str | None = None
    picked_qty: int | None = None
    allocation_quantity: int | None = None


async def _picked_qty_by_product(
    session: AsyncSession, request_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    from app.services import marketplace_unload_collect_service as collect_svc

    return await collect_svc.picked_qty_by_product(session, request_id)


async def _picked_qty_by_product_location(
    session: AsyncSession, request_id: uuid.UUID
) -> dict[tuple[uuid.UUID, uuid.UUID], int]:
    """Снято по каждой паре товар+ячейка этого документа (PICK-01)."""
    stmt = select(
        MarketplaceUnloadPickAllocation.product_id,
        MarketplaceUnloadPickAllocation.storage_location_id,
        MarketplaceUnloadPickAllocation.quantity,
    ).where(MarketplaceUnloadPickAllocation.request_id == request_id)
    res = await session.execute(stmt)
    return {(pid, loc_id): int(qty) for pid, loc_id, qty in res.all()}


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
        .options(
            selectinload(MarketplaceUnloadRequest.lines).selectinload(MarketplaceUnloadLine.product)
        )
        .execution_options(populate_existing=True)
    )
    req = (await session.execute(stmt)).scalar_one_or_none()
    if req is None:
        raise MarketplaceUnloadPickError("not_found")
    if req.status not in PICK_EDITABLE_STATUSES:
        raise MarketplaceUnloadPickError("not_editable")
    if req.seller_id is None:
        raise MarketplaceUnloadPickError("seller_required")
    return req


async def find_location_by_barcode(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    barcode: str,
) -> StorageLocation | None:
    raw = barcode.strip()
    if not raw:
        return None
    # Ячейку можно и отсканировать, и набрать кодом руками. Ограничения БД допускают,
    # что одна строка окажется штрихкодом одной ячейки и кодом другой на том же складе
    # (uq_storage_locations_wh_code — код уникален по складу, а
    # uq_storage_locations_tenant_barcode — штрихкод по организации). Раньше такой ввод
    # возвращал две строки и ронял подбор через scalar_one_or_none(). Побеждает штрихкод:
    # сканер важнее клавиатуры (SORT-01).
    stmt = (
        select(StorageLocation)
        .where(
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.warehouse_id == warehouse_id,
            or_(StorageLocation.barcode == raw, StorageLocation.code == raw),
        )
        .order_by(case((StorageLocation.barcode == raw, 0), else_=1))
        .limit(1)
    )
    res = await session.execute(stmt)
    return res.scalars().first()


async def get_pick_options(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> list[PickOptionProduct]:
    req = await _request_for_picking(session, tenant_id, request_id)
    product_ids = [ln.product_id for ln in req.lines]
    if not product_ids:
        return []

    picked = await _picked_qty_by_product(session, req.id)
    picked_by_loc = await _picked_qty_by_product_location(session, req.id)
    bal_rows = await inventory_service.list_location_balances_for_products_in_warehouse(
        session,
        tenant_id,
        req.warehouse_id,
        product_ids,
    )
    loc_by_product: dict[uuid.UUID, list[PickOptionLocation]] = {pid: [] for pid in product_ids}
    seen_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for pid, loc_id, code, on_hand, rsv in bal_rows:
        seen_pairs.add((pid, loc_id))
        loc_by_product.setdefault(pid, []).append(
            PickOptionLocation(
                storage_location_id=loc_id,
                location_code=code,
                quantity=on_hand,
                reserved=rsv,
                available=max(0, on_hand - rsv),
                picked=picked_by_loc.get((pid, loc_id), 0),
            )
        )

    # Ячейки, по которым уже есть подбор, но остаток в них стал нулевым, не попадают
    # в bal_rows (там фильтр quantity > 0) — без них оператор не смог бы вернуть
    # снятое обратно в ячейку (PICK-01).
    for (pid, loc_id), qty in picked_by_loc.items():
        if (pid, loc_id) in seen_pairs or pid not in loc_by_product:
            continue
        loc = await session.get(StorageLocation, loc_id)
        if loc is None:
            continue
        available = await inventory_service.available_at_location(session, tenant_id, pid, loc_id)
        reserved = await inventory_service.total_reserved_at_location(
            session, tenant_id, pid, loc_id
        )
        loc_by_product[pid].append(
            PickOptionLocation(
                storage_location_id=loc_id,
                location_code=loc.code,
                quantity=available + reserved,
                reserved=reserved,
                available=max(0, available),
                picked=qty,
            )
        )

    for _pid, locs in loc_by_product.items():
        locs.sort(key=lambda loc: loc.location_code)

    out: list[PickOptionProduct] = []
    for ln in req.lines:
        p = ln.product
        out.append(
            PickOptionProduct(
                product_id=ln.product_id,
                sku_code=p.sku_code,
                product_name=p.name,
                planned_qty=int(ln.quantity),
                picked_qty=picked.get(ln.product_id, 0),
                locations=loc_by_product.get(ln.product_id, []),
            )
        )
    return out


async def list_pick_allocations(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> list[MarketplaceUnloadPickAllocation]:
    req = await session.get(MarketplaceUnloadRequest, request_id)
    if req is None or req.tenant_id != tenant_id:
        raise MarketplaceUnloadPickError("not_found")
    stmt = (
        select(MarketplaceUnloadPickAllocation)
        .where(MarketplaceUnloadPickAllocation.request_id == request_id)
        .options(
            selectinload(MarketplaceUnloadPickAllocation.product),
            selectinload(MarketplaceUnloadPickAllocation.storage_location),
        )
        .order_by(MarketplaceUnloadPickAllocation.created_at.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def add_pick_qty(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    storage_location_id: uuid.UUID | None,
    product_id: uuid.UUID,
    quantity: int,
) -> MarketplaceUnloadPickAllocation:
    from app.services import marketplace_unload_collect_service as collect_svc

    result = await collect_svc.record_pick_allocation(
        session,
        tenant_id,
        request_id,
        storage_location_id=storage_location_id,
        product_id=product_id,
        quantity=quantity,
    )
    # record_pick_allocation уже синхронизирует задание на упаковку сама —
    # отдельного вызова здесь не нужно.
    return result.allocation


async def pick_scan(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    barcode: str,
    product_id_hint: uuid.UUID | None = None,
    storage_location_id: uuid.UUID | None,
) -> PickScanResult:
    raw = barcode.strip()
    if not raw:
        raise MarketplaceUnloadPickError("barcode_empty")

    req = await _request_for_picking(session, tenant_id, request_id)

    address_enabled = await tenant_settings_svc.is_address_storage_enabled(
        session, tenant_id
    )
    if address_enabled:
        loc = await find_location_by_barcode(session, tenant_id, req.warehouse_id, raw)
        if loc is not None:
            return PickScanResult(
                kind="location",
                storage_location_id=loc.id,
                location_code=loc.code,
            )

    if address_enabled and storage_location_id is None:
        raise MarketplaceUnloadPickError("location_required")

    from app.services import marketplace_unload_collect_service as collect_svc

    if req.seller_id is None:
        raise MarketplaceUnloadPickError("seller_required")
    if product_id_hint is None:
        idx = await _barcode_index_for_seller(session, tenant_id, req.seller_id)
        product_id = idx.get(raw)
        if product_id is None:
            raise MarketplaceUnloadPickError("barcode_unknown")
    else:
        product_id = product_id_hint

    # Подбор не трогает короба (решение заказчика 2026-08-16) — только storage →
    # pick allocation. Короб появляется отдельно и явно на упаковке.
    result = await collect_svc.record_pick_allocation(
        session,
        tenant_id,
        request_id,
        storage_location_id=storage_location_id,
        product_id=product_id,
        quantity=1,
    )
    p = result.product
    return PickScanResult(
        kind="product",
        storage_location_id=storage_location_id,
        product_id=product_id,
        sku_code=p.sku_code,
        product_name=p.name,
        picked_qty=result.picked_qty,
        allocation_quantity=int(result.allocation.quantity),
    )


async def save_pick_allocations(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    rows: list[PickAllocationRow],
) -> list[MarketplaceUnloadPickAllocation]:
    req = await _request_for_picking(session, tenant_id, request_id)
    line_products = {ln.product_id for ln in req.lines}
    if not line_products:
        raise MarketplaceUnloadPickError("no_lines")

    from app.services import marketplace_unload_collect_service as collect_svc

    merged: dict[tuple[uuid.UUID, uuid.UUID | None], int] = {}
    for row in rows:
        if row.quantity < 1:
            raise MarketplaceUnloadPickError("invalid_quantity")
        if row.product_id not in line_products:
            raise MarketplaceUnloadPickError("product_not_in_shipment")
        key = (row.product_id, row.storage_location_id)
        merged[key] = merged.get(key, 0) + row.quantity

    # Подбор не трогает короба (решение заказчика 2026-08-16) — только storage →
    # pick allocation для каждой пары товар/ячейка.
    for (product_id, loc_id), qty in merged.items():
        await collect_svc.record_pick_allocation(
            session,
            tenant_id,
            request_id,
            storage_location_id=loc_id,
            product_id=product_id,
            quantity=qty,
        )
    return await list_pick_allocations(session, tenant_id, request_id)


def has_incomplete_distribution(req: MarketplaceUnloadRequest) -> bool:
    """DEC-010: ship only when box quantities match plan lines exactly."""
    return mu_svc.has_incomplete_distribution(req)


def has_pick_discrepancy(req: MarketplaceUnloadRequest) -> bool:
    """Legacy alias for detail/UI flags."""
    return mu_svc.compute_has_discrepancy(req)


async def ship_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    acknowledge_discrepancy: bool = False,
    performer_id: uuid.UUID | None = None,
) -> MarketplaceUnloadRequest:
    try:
        return await mu_svc.complete_unload(
            session,
            tenant_id,
            request_id,
            acknowledge_discrepancy=acknowledge_discrepancy,
            performer_id=performer_id,
        )
    except mu_svc.MarketplaceUnloadError as exc:
        raise MarketplaceUnloadPickError(exc.code) from None


async def picked_qty_for_lines(
    session: AsyncSession, request_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    return await _picked_qty_by_product(session, request_id)
