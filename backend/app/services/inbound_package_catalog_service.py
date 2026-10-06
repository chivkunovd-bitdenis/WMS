from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeBoxLine,
    InboundIntakeCargoPlace,
    InboundIntakeCargoPlaceLine,
    InboundIntakeRequest,
)
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse

PackageKind = Literal["box", "cargo_place"]


@dataclass(frozen=True)
class InboundPackageCatalogLine:
    product_id: uuid.UUID
    remaining_qty: int
    name: str
    sku_code: str
    wb_vendor_code: str | None
    wb_barcode: str | None
    wb_size: str | None
    seller_name: str | None


@dataclass(frozen=True)
class PackageSourceDocument:
    """Stable UI contract; each future stock-source type supplies its own adapter."""

    kind: str
    id: uuid.UUID
    number: str | None
    date: datetime


@dataclass(frozen=True)
class InboundPackageCatalogItem:
    id: uuid.UUID
    kind: PackageKind
    number: int
    internal_barcode: str
    request_id: uuid.UUID
    request_display_number: str | None
    warehouse_name: str | None
    intake_status: str
    composition_tracked: bool
    fully_distributed: bool
    remaining_qty: int | None
    lines: tuple[InboundPackageCatalogLine, ...]
    request_created_at: datetime
    source_document: PackageSourceDocument


def _box_line_remaining_qty(line: InboundIntakeBoxLine) -> int:
    return max(0, int(line.quantity) - int(line.posted_qty))


def _cargo_place_line_remaining_qty(line: InboundIntakeCargoPlaceLine) -> int:
    return max(0, int(line.quantity) - int(line.posted_qty))


def _request_display_number(request: InboundIntakeRequest) -> str | None:
    return request.display_number or request.document_number


def _inbound_source_document(request: InboundIntakeRequest) -> PackageSourceDocument:
    return PackageSourceDocument(
        kind="inbound_intake",
        id=request.id,
        number=_request_display_number(request),
        date=request.created_at,
    )


def _box_catalog_line(line: InboundIntakeBoxLine, remaining_qty: int) -> InboundPackageCatalogLine:
    product = line.product
    return InboundPackageCatalogLine(
        product_id=line.product_id,
        remaining_qty=remaining_qty,
        name=product.name,
        sku_code=product.sku_code,
        wb_vendor_code=product.wb_vendor_code,
        wb_barcode=product.wb_barcode,
        wb_size=product.wb_size,
        seller_name=product.seller.name if product.seller is not None else None,
    )


def _box_item(
    box: InboundIntakeBox,
    request: InboundIntakeRequest,
    *,
    warehouse_name: str | None,
    current_lines: tuple[InboundPackageCatalogLine, ...] | None = None,
) -> InboundPackageCatalogItem:
    lines = (
        current_lines
        if current_lines is not None
        else tuple(
            _box_catalog_line(line, remaining)
            for line in box.lines
            if (remaining := _box_line_remaining_qty(line)) > 0
        )
    )
    return InboundPackageCatalogItem(
        id=box.id,
        kind="box",
        number=int(box.box_number),
        internal_barcode=box.internal_barcode,
        request_id=request.id,
        request_display_number=_request_display_number(request),
        warehouse_name=warehouse_name,
        intake_status=request.status,
        composition_tracked=True,
        fully_distributed=bool(box.lines) and all(
            _box_line_remaining_qty(line) == 0 for line in box.lines
        ),
        remaining_qty=sum(line.remaining_qty for line in lines),
        lines=lines,
        request_created_at=request.created_at,
        source_document=_inbound_source_document(request),
    )


def _cargo_place_item(
    place: InboundIntakeCargoPlace,
    request: InboundIntakeRequest,
    *,
    warehouse_name: str | None,
) -> InboundPackageCatalogItem:
    lines = tuple(
        InboundPackageCatalogLine(
            product_id=line.product_id,
            remaining_qty=remaining,
            name=line.product.name,
            sku_code=line.product.sku_code,
            wb_vendor_code=line.product.wb_vendor_code,
            wb_barcode=line.product.wb_barcode,
            wb_size=line.product.wb_size,
            seller_name=(
                line.product.seller.name if line.product.seller is not None else None
            ),
        )
        for line in place.lines
        if (remaining := _cargo_place_line_remaining_qty(line)) > 0
    )
    return InboundPackageCatalogItem(
        id=place.id,
        kind="cargo_place",
        number=int(place.place_number),
        internal_barcode=place.internal_barcode,
        request_id=request.id,
        request_display_number=_request_display_number(request),
        warehouse_name=warehouse_name,
        intake_status=request.status,
        composition_tracked=True,
        fully_distributed=bool(place.lines) and all(
            _cargo_place_line_remaining_qty(line) == 0 for line in place.lines
        ),
        remaining_qty=sum(line.remaining_qty for line in lines),
        lines=lines,
        request_created_at=request.created_at,
        source_document=_inbound_source_document(request),
    )


async def _warehouse_names_for_tenant(
    session: AsyncSession, tenant_id: uuid.UUID
) -> dict[uuid.UUID, str]:
    result = await session.execute(
        select(Warehouse.id, Warehouse.name).where(Warehouse.tenant_id == tenant_id)
    )
    return {warehouse_id: name for warehouse_id, name in result.all()}


async def _load_tenant_packages(
    session: AsyncSession, tenant_id: uuid.UUID
) -> tuple[list[InboundIntakeBox], list[InboundIntakeCargoPlace], dict[uuid.UUID, str]]:
    boxes_result = await session.execute(
        select(InboundIntakeBox)
        .join(InboundIntakeBox.request)
        .where(InboundIntakeBox.tenant_id == tenant_id)
        .options(
            selectinload(InboundIntakeBox.lines)
            .selectinload(InboundIntakeBoxLine.product)
            .selectinload(Product.seller),
            selectinload(InboundIntakeBox.request),
        )
    )
    cargo_places_result = await session.execute(
        select(InboundIntakeCargoPlace)
        .join(InboundIntakeCargoPlace.request)
        .where(
            InboundIntakeCargoPlace.tenant_id == tenant_id,
            InboundIntakeRequest.status != "done",
        )
        .options(
            selectinload(InboundIntakeCargoPlace.request),
            selectinload(InboundIntakeCargoPlace.lines)
            .selectinload(InboundIntakeCargoPlaceLine.product)
            .selectinload(Product.seller),
        )
    )
    warehouse_names = await _warehouse_names_for_tenant(session, tenant_id)
    return (
        list(boxes_result.scalars()),
        list(cargo_places_result.scalars()),
        warehouse_names,
    )


async def _current_box_contents(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    box_ids: list[uuid.UUID],
) -> tuple[
    dict[uuid.UUID, tuple[InboundPackageCatalogLine, ...]],
    dict[uuid.UUID, str],
    set[uuid.UUID],
]:
    if not box_ids:
        return {}, {}, set()
    rows = list(
        (
            await session.execute(
                select(
                    InventoryBalance.container_id,
                    Product,
                    Seller,
                    Warehouse.name,
                    func.sum(InventoryBalance.quantity),
                )
                .join(Product, Product.id == InventoryBalance.product_id)
                .outerjoin(Seller, Seller.id == Product.seller_id)
                .join(
                    StorageLocation,
                    StorageLocation.id == InventoryBalance.storage_location_id,
                )
                .join(Warehouse, Warehouse.id == StorageLocation.warehouse_id)
                .where(
                    InventoryBalance.tenant_id == tenant_id,
                    InventoryBalance.container_kind == "box",
                    InventoryBalance.container_id.in_(box_ids),
                )
                .group_by(
                    InventoryBalance.container_id,
                    Product.id,
                    Seller.id,
                    Warehouse.name,
                )
                .order_by(Product.sku_code)
            )
        ).all()
    )
    lines_by_box: dict[uuid.UUID, list[InboundPackageCatalogLine]] = {}
    warehouses_by_box: dict[uuid.UUID, set[str]] = {}
    tracked_box_ids: set[uuid.UUID] = set()
    for box_id, product, seller, warehouse_name, quantity in rows:
        if box_id is None:
            continue
        tracked_box_ids.add(box_id)
        if int(quantity) > 0:
            lines_by_box.setdefault(box_id, []).append(
                InboundPackageCatalogLine(
                    product_id=product.id,
                    remaining_qty=int(quantity),
                    name=product.name,
                    sku_code=product.sku_code,
                    wb_vendor_code=product.wb_vendor_code,
                    wb_barcode=product.wb_barcode,
                    wb_size=product.wb_size,
                    seller_name=seller.name if seller is not None else None,
                )
            )
        warehouses_by_box.setdefault(box_id, set()).add(warehouse_name)
    current_lines = {
        box_id: tuple(lines) for box_id, lines in lines_by_box.items()
    }
    current_warehouses = {
        box_id: next(iter(names)) if len(names) == 1 else "Несколько складов"
        for box_id, names in warehouses_by_box.items()
    }
    return current_lines, current_warehouses, tracked_box_ids


def _conditional_warehouse_name(
    request: InboundIntakeRequest, warehouse_names: dict[uuid.UUID, str]
) -> str | None:
    if len(warehouse_names) < 2:
        return None
    return warehouse_names.get(request.warehouse_id)


def _sort_items(items: list[InboundPackageCatalogItem]) -> list[InboundPackageCatalogItem]:
    # The stable second sort keeps object numbers ascending inside every intake.
    items.sort(key=lambda item: (item.number, item.kind, str(item.id)))
    items.sort(key=lambda item: item.request_created_at, reverse=True)
    return items


async def list_current_packages(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[InboundPackageCatalogItem]:
    """Return catalog-visible packages without changing intake state."""
    boxes, cargo_places, warehouse_names = await _load_tenant_packages(session, tenant_id)
    current_lines_by_box, current_warehouse_by_box, tracked_box_ids = await _current_box_contents(
        session, tenant_id, [box.id for box in boxes]
    )
    items: list[InboundPackageCatalogItem] = []
    for box in boxes:
        request = box.request
        if request is None:
            continue
        item = _box_item(
            box,
            request,
            warehouse_name=current_warehouse_by_box.get(box.id)
            or _conditional_warehouse_name(request, warehouse_names),
            current_lines=(
                current_lines_by_box.get(box.id, ())
                if box.id in tracked_box_ids
                else None
            ),
        )
        items.append(item)

    for place in cargo_places:
        request = place.request
        if request is None or request.status == "done":
            continue
        item = _cargo_place_item(
            place,
            request,
            warehouse_name=_conditional_warehouse_name(request, warehouse_names),
        )
        if (item.remaining_qty is not None and item.remaining_qty > 0) or not place.lines:
            items.append(item)
    return _sort_items(items)


async def lookup_package_by_barcode(
    session: AsyncSession, tenant_id: uuid.UUID, barcode: str
) -> InboundPackageCatalogItem | None:
    """Find one package within a tenant. This is intentionally read-only."""
    normalized = barcode.strip().upper()
    if not normalized:
        return None

    warehouse_names = await _warehouse_names_for_tenant(session, tenant_id)
    box_result = await session.execute(
        select(InboundIntakeBox)
        .where(
            InboundIntakeBox.tenant_id == tenant_id,
            InboundIntakeBox.internal_barcode == normalized,
        )
        .options(
            selectinload(InboundIntakeBox.lines)
            .selectinload(InboundIntakeBoxLine.product)
            .selectinload(Product.seller),
            selectinload(InboundIntakeBox.request),
        )
    )
    box = box_result.scalar_one_or_none()
    if box is not None and box.request is not None:
        (
            current_lines_by_box,
            current_warehouse_by_box,
            tracked_box_ids,
        ) = await _current_box_contents(session, tenant_id, [box.id])
        return _box_item(
            box,
            box.request,
            warehouse_name=current_warehouse_by_box.get(box.id)
            or _conditional_warehouse_name(box.request, warehouse_names),
            current_lines=(
                current_lines_by_box.get(box.id, ())
                if box.id in tracked_box_ids
                else None
            ),
        )

    cargo_place_result = await session.execute(
        select(InboundIntakeCargoPlace)
        .where(
            InboundIntakeCargoPlace.tenant_id == tenant_id,
            InboundIntakeCargoPlace.internal_barcode == normalized,
        )
        .options(
            selectinload(InboundIntakeCargoPlace.request),
            selectinload(InboundIntakeCargoPlace.lines)
            .selectinload(InboundIntakeCargoPlaceLine.product)
            .selectinload(Product.seller),
        )
    )
    cargo_place = cargo_place_result.scalar_one_or_none()
    if cargo_place is None or cargo_place.request is None:
        return None
    return _cargo_place_item(
        cargo_place,
        cargo_place.request,
        warehouse_name=_conditional_warehouse_name(cargo_place.request, warehouse_names),
    )
