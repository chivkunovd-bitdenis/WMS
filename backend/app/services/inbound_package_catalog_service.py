from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeBoxLine,
    InboundIntakeCargoPlace,
    InboundIntakeRequest,
)
from app.models.warehouse import Warehouse

PackageKind = Literal["box", "cargo_place"]


@dataclass(frozen=True)
class InboundPackageCatalogLine:
    product_id: uuid.UUID
    remaining_qty: int


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


def _box_line_remaining_qty(line: InboundIntakeBoxLine) -> int:
    return max(0, int(line.quantity) - int(line.posted_qty))


def _request_display_number(request: InboundIntakeRequest) -> str | None:
    return request.display_number or request.document_number


def _box_item(
    box: InboundIntakeBox,
    request: InboundIntakeRequest,
    *,
    warehouse_name: str | None,
) -> InboundPackageCatalogItem:
    lines = tuple(
        InboundPackageCatalogLine(product_id=line.product_id, remaining_qty=remaining)
        for line in box.lines
        if (remaining := _box_line_remaining_qty(line)) > 0
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
    )


def _cargo_place_item(
    place: InboundIntakeCargoPlace,
    request: InboundIntakeRequest,
    *,
    warehouse_name: str | None,
) -> InboundPackageCatalogItem:
    return InboundPackageCatalogItem(
        id=place.id,
        kind="cargo_place",
        number=int(place.place_number),
        internal_barcode=place.internal_barcode,
        request_id=request.id,
        request_display_number=_request_display_number(request),
        warehouse_name=warehouse_name,
        intake_status=request.status,
        composition_tracked=False,
        fully_distributed=False,
        remaining_qty=None,
        lines=(),
        request_created_at=request.created_at,
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
        .where(InboundIntakeBox.tenant_id == tenant_id)
        .options(
            selectinload(InboundIntakeBox.lines),
            selectinload(InboundIntakeBox.request),
        )
    )
    cargo_places_result = await session.execute(
        select(InboundIntakeCargoPlace)
        .where(InboundIntakeCargoPlace.tenant_id == tenant_id)
        .options(selectinload(InboundIntakeCargoPlace.request))
    )
    warehouse_names = await _warehouse_names_for_tenant(session, tenant_id)
    return (
        list(boxes_result.scalars()),
        list(cargo_places_result.scalars()),
        warehouse_names,
    )


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
    items: list[InboundPackageCatalogItem] = []
    for box in boxes:
        request = box.request
        if request is None:
            continue
        item = _box_item(
            box,
            request,
            warehouse_name=_conditional_warehouse_name(request, warehouse_names),
        )
        is_empty_box = not box.lines
        if (item.remaining_qty is not None and item.remaining_qty > 0) or (
            is_empty_box and request.status != "done"
        ):
            items.append(item)

    for place in cargo_places:
        request = place.request
        if request is None or request.status == "done":
            continue
        items.append(
            _cargo_place_item(
                place,
                request,
                warehouse_name=_conditional_warehouse_name(request, warehouse_names),
            )
        )
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
        .options(selectinload(InboundIntakeBox.lines), selectinload(InboundIntakeBox.request))
    )
    box = box_result.scalar_one_or_none()
    if box is not None and box.request is not None:
        return _box_item(
            box,
            box.request,
            warehouse_name=_conditional_warehouse_name(box.request, warehouse_names),
        )

    cargo_place_result = await session.execute(
        select(InboundIntakeCargoPlace)
        .where(
            InboundIntakeCargoPlace.tenant_id == tenant_id,
            InboundIntakeCargoPlace.internal_barcode == normalized,
        )
        .options(selectinload(InboundIntakeCargoPlace.request))
    )
    cargo_place = cargo_place_result.scalar_one_or_none()
    if cargo_place is None or cargo_place.request is None:
        return None
    return _cargo_place_item(
        cargo_place,
        cargo_place.request,
        warehouse_name=_conditional_warehouse_name(cargo_place.request, warehouse_names),
    )
