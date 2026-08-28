"""Tenant-safe resolver for every warehouse scan target."""

from __future__ import annotations

import unicodedata
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.fbs_trbx import FbsTrbx
from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeCargoPlace,
    InboundIntakeRequest,
)
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox

ScanObjectType = Literal[
    "cell",
    "pallet",
    "box",
    "cargo_place",
    "product",
    "fbs_order",
    "warehouse",
]


@dataclass(frozen=True)
class ScanMatch:
    type: ScanObjectType
    id: uuid.UUID
    name: str
    warehouse_id: uuid.UUID | None


class ScanResolverError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        matches: tuple[ScanMatch, ...] = (),
    ) -> None:
        self.code = code
        self.message = message
        self.matches = matches
        super().__init__(code)


def normalize_scan_code(code: str) -> str:
    """Remove scanner framing controls and surrounding whitespace in one place."""
    without_controls = "".join(
        character
        for character in code
        if unicodedata.category(character) not in {"Cc", "Cf"}
    )
    return without_controls.strip()


async def _find_cells(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    code: str,
    warehouse_id: uuid.UUID | None,
) -> list[ScanMatch]:
    stmt = select(StorageLocation).where(
        StorageLocation.tenant_id == tenant_id,
        StorageLocation.deleted_at.is_(None),
        or_(
            StorageLocation.barcode == code,
            func.lower(StorageLocation.code) == code.lower(),
        ),
    )
    if warehouse_id is not None:
        stmt = stmt.where(StorageLocation.warehouse_id == warehouse_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        ScanMatch(
            type="cell",
            id=row.id,
            name=f"Ячейка {row.code}",
            warehouse_id=row.warehouse_id,
        )
        for row in rows
    ]


async def _find_pallets(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    code: str,
    warehouse_id: uuid.UUID | None,
) -> list[ScanMatch]:
    stmt = (
        select(InboundIntakeCargoPlace, InboundIntakeRequest.warehouse_id)
        .join(InboundIntakeCargoPlace.request)
        .where(
            InboundIntakeCargoPlace.tenant_id == tenant_id,
            InboundIntakeRequest.tenant_id == tenant_id,
            InboundIntakeCargoPlace.internal_barcode == code,
        )
    )
    if warehouse_id is not None:
        stmt = stmt.where(InboundIntakeRequest.warehouse_id == warehouse_id)
    rows = (await session.execute(stmt)).all()
    return [
        ScanMatch(
            type="pallet",
            id=place.id,
            name=f"Палета / грузоместо приёмки №{place.place_number}",
            warehouse_id=place_warehouse_id,
        )
        for place, place_warehouse_id in rows
    ]


async def _find_boxes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    code: str,
    warehouse_id: uuid.UUID | None,
) -> list[ScanMatch]:
    warehouse_stmt = select(WarehouseBox).where(
        WarehouseBox.tenant_id == tenant_id,
        WarehouseBox.internal_barcode == code,
    )
    if warehouse_id is not None:
        warehouse_stmt = warehouse_stmt.where(WarehouseBox.warehouse_id == warehouse_id)
    warehouse_boxes = (await session.execute(warehouse_stmt)).scalars().all()

    inbound_stmt = (
        select(InboundIntakeBox, InboundIntakeRequest.warehouse_id)
        .join(InboundIntakeBox.request)
        .where(
            InboundIntakeBox.tenant_id == tenant_id,
            InboundIntakeRequest.tenant_id == tenant_id,
            InboundIntakeBox.internal_barcode == code,
        )
    )
    if warehouse_id is not None:
        inbound_stmt = inbound_stmt.where(InboundIntakeRequest.warehouse_id == warehouse_id)
    inbound_boxes = (await session.execute(inbound_stmt)).all()

    matches = [
        ScanMatch(
            type="box",
            id=box.id,
            name=f"Складской короб {box.internal_barcode}",
            warehouse_id=box.warehouse_id,
        )
        for box in warehouse_boxes
    ]
    matches.extend(
        ScanMatch(
            type="box",
            id=box.id,
            name=f"Короб приёмки №{box.box_number}",
            warehouse_id=box_warehouse_id,
        )
        for box, box_warehouse_id in inbound_boxes
    )
    return matches


async def _find_cargo_places(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    code: str,
    warehouse_id: uuid.UUID | None,
) -> list[ScanMatch]:
    stmt = (
        select(FbsTrbx, FbsSupply.warehouse_id)
        .join(FbsTrbx.supply)
        .where(
            FbsSupply.tenant_id == tenant_id,
            FbsTrbx.wb_trbx_id == code,
        )
    )
    if warehouse_id is not None:
        stmt = stmt.where(FbsSupply.warehouse_id == warehouse_id)
    rows = (await session.execute(stmt)).all()
    return [
        ScanMatch(
            type="cargo_place",
            id=place.id,
            name=f"Грузоместо {place.wb_trbx_id}",
            warehouse_id=place_warehouse_id,
        )
        for place, place_warehouse_id in rows
    ]


async def _find_products(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    code: str,
) -> list[ScanMatch]:
    # The same two identifiers are accepted by the existing inbound and FBS pick scans.
    stmt = select(Product).where(
        Product.tenant_id == tenant_id,
        or_(Product.wb_barcode == code, Product.sku_code == code),
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        ScanMatch(type="product", id=row.id, name=row.name, warehouse_id=None)
        for row in rows
    ]


async def _find_fbs_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    code: str,
    warehouse_id: uuid.UUID | None,
) -> list[ScanMatch]:
    resolved_warehouse_id = func.coalesce(FbsOrder.warehouse_id, FbsSupply.warehouse_id)
    stmt = (
        select(FbsOrder, resolved_warehouse_id)
        .outerjoin(FbsSupply, FbsSupply.id == FbsOrder.supply_id)
        .where(
            FbsOrder.tenant_id == tenant_id,
            # sticker_barcode is the technical value encoded in the printed WB label.
            FbsOrder.sticker_barcode == code,
        )
    )
    if warehouse_id is not None:
        stmt = stmt.where(resolved_warehouse_id == warehouse_id)
    rows = (await session.execute(stmt)).all()
    return [
        ScanMatch(
            type="fbs_order",
            id=order.id,
            name=f"Заказ {order.sticker_code or order.external_order_id or order.wb_order_id}",
            warehouse_id=order_warehouse_id,
        )
        for order, order_warehouse_id in rows
    ]


async def _find_warehouses(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    code: str,
    warehouse_id: uuid.UUID | None,
) -> list[ScanMatch]:
    stmt = select(Warehouse).where(
        Warehouse.tenant_id == tenant_id,
        Warehouse.is_operational.is_(True),
        or_(
            Warehouse.barcode == code,
            func.lower(Warehouse.code) == code.lower(),
        ),
    )
    if warehouse_id is not None:
        stmt = stmt.where(Warehouse.id == warehouse_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        ScanMatch(
            type="warehouse",
            id=row.id,
            name=row.name,
            warehouse_id=row.id,
        )
        for row in rows
    ]


async def _tenant_has_warehouse(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
) -> bool:
    return (
        await session.scalar(
            select(Warehouse.id).where(
                Warehouse.id == warehouse_id,
                Warehouse.tenant_id == tenant_id,
            )
        )
        is not None
    )


async def resolve_any_scan(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    code: str,
    *,
    warehouse_id: uuid.UUID | None = None,
) -> ScanMatch:
    normalized = normalize_scan_code(code)
    if not normalized:
        raise ScanResolverError("scan_code_empty", "Отсканированный код пуст.")
    if warehouse_id is not None and not await _tenant_has_warehouse(
        session, tenant_id, warehouse_id
    ):
        raise ScanResolverError(
            "scan_not_found",
            "На выбранном складе объект с таким кодом не найден.",
        )

    # Deliberate search order: a physical destination comes first, followed by
    # movable handling units, then goods/documents, and finally the warehouse.
    # Codes can overlap, so this order only makes ambiguity output deterministic:
    # every group is always searched and a first match is never silently selected.
    matches: list[ScanMatch] = []
    matches.extend(await _find_cells(session, tenant_id, normalized, warehouse_id))
    matches.extend(await _find_pallets(session, tenant_id, normalized, warehouse_id))
    matches.extend(await _find_boxes(session, tenant_id, normalized, warehouse_id))
    matches.extend(await _find_cargo_places(session, tenant_id, normalized, warehouse_id))
    matches.extend(await _find_products(session, tenant_id, normalized))
    matches.extend(await _find_fbs_orders(session, tenant_id, normalized, warehouse_id))
    matches.extend(await _find_warehouses(session, tenant_id, normalized, warehouse_id))

    unique_matches = tuple(dict.fromkeys((match.type, match.id) for match in matches))
    if not unique_matches:
        message = (
            "На выбранном складе объект с таким кодом не найден."
            if warehouse_id is not None
            else "Объект с таким кодом не найден."
        )
        raise ScanResolverError("scan_not_found", message)
    if len(unique_matches) > 1:
        by_identity = {(match.type, match.id): match for match in matches}
        ambiguous_matches = tuple(by_identity[identity] for identity in unique_matches)
        raise ScanResolverError(
            "scan_ambiguous",
            "Код относится к нескольким объектам. Уточните склад или выберите объект вручную.",
            matches=ambiguous_matches,
        )
    identity = unique_matches[0]
    return next(match for match in matches if (match.type, match.id) == identity)


__all__ = [
    "ScanMatch",
    "ScanObjectType",
    "ScanResolverError",
    "normalize_scan_code",
    "resolve_any_scan",
]
