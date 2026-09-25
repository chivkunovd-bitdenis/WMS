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
from app.models.pallet import Pallet
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox
from app.services.product_code_resolver_service import (
    ProductCodeAliasPolicy,
    ProductCodeMatch,
    ProductCodeResolution,
    ProductCodeScope,
    ProductCodeSource,
    build_product_code_index,
    normalize_product_code,
    resolve_product_code_from_index,
)

ScanObjectType = Literal[
    "cell",
    "pallet",
    "box",
    "cargo_place",
    "product",
    "fbs_order",
    "warehouse",
]

_DIRECT_PRODUCT_CODE_SOURCES = frozenset(
    {
        ProductCodeSource.WB_PRIMARY,
        ProductCodeSource.WB_ADDITIONAL,
        ProductCodeSource.SKU,
    }
)


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


async def validated_product_ids_from_resolution(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    resolution: ProductCodeResolution,
    *,
    seller_id: uuid.UUID | None,
) -> tuple[uuid.UUID, ...]:
    """Reject marketplace aliases whose legacy link has the wrong owner.

    ProductCodeScope filters products before ambiguity, but the core index currently
    accepts an active marketplace link by product_id alone. Old inconsistent rows may
    therefore point at an in-scope product while belonging to another seller. Keep the
    core untouched and enforce the existing WMS-488 owner boundary at the consumer.
    """
    if resolution.status == "not_found":
        return ()
    matches = (
        resolution.matches
        if resolution.status == "ambiguous"
        else (
            ProductCodeMatch(
                product_id=resolution.product_id,
                matched_sources=resolution.matched_sources,
            ),
        )
    )
    direct_ids = {
        match.product_id
        for match in matches
        if _DIRECT_PRODUCT_CODE_SOURCES.intersection(match.matched_sources)
    }
    external_matches = [match for match in matches if match.product_id not in direct_ids]
    if not external_matches:
        return tuple(match.product_id for match in matches)

    external_ids = {match.product_id for match in external_matches}
    stmt = (
        select(
            ProductMarketplaceLink.product_id,
            ProductMarketplaceLink.external_barcodes,
            ProductMarketplaceLink.external_sku,
            ProductMarketplaceLink.external_offer_id,
        )
        .join(Product, Product.id == ProductMarketplaceLink.product_id)
        .where(
            ProductMarketplaceLink.tenant_id == tenant_id,
            ProductMarketplaceLink.product_id.in_(external_ids),
            ProductMarketplaceLink.marketplace == "ozon",
            ProductMarketplaceLink.is_active.is_(True),
            Product.tenant_id == tenant_id,
            Product.seller_id == ProductMarketplaceLink.seller_id,
        )
    )
    if seller_id is not None:
        stmt = stmt.where(Product.seller_id == seller_id)
    links_by_product: dict[uuid.UUID, list[tuple[object, object, object]]] = {}
    for row in (await session.execute(stmt)).all():
        links_by_product.setdefault(row.product_id, []).append(
            (row.external_barcodes, row.external_sku, row.external_offer_id)
        )

    matched_code = normalize_product_code(resolution.matched_code).casefold()

    def valid_external_match(match: ProductCodeMatch) -> bool:
        product_id = match.product_id
        sources = set(match.matched_sources)
        for external_barcodes, external_sku, external_offer_id in links_by_product.get(
            product_id, []
        ):
            if (
                ProductCodeSource.OZON_EXTERNAL_BARCODE in sources
                and isinstance(external_barcodes, (list, tuple))
                and any(
                    isinstance(value, str)
                    and normalize_product_code(value).casefold() == matched_code
                    for value in external_barcodes
                )
            ):
                return True
            if (
                ProductCodeSource.OZON_EXTERNAL_SKU in sources
                and isinstance(external_sku, str)
                and normalize_product_code(external_sku).casefold() == matched_code
            ):
                return True
            if (
                ProductCodeSource.OZON_EXTERNAL_OFFER_ID in sources
                and isinstance(external_offer_id, str)
                and normalize_product_code(external_offer_id).casefold() == matched_code
            ):
                return True
        return False

    valid_external_ids = {
        match.product_id for match in external_matches if valid_external_match(match)
    }
    return tuple(
        match.product_id
        for match in matches
        if match.product_id in direct_ids or match.product_id in valid_external_ids
    )


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
    pallet_stmt = select(Pallet).where(
        Pallet.tenant_id == tenant_id,
        Pallet.barcode == code,
        Pallet.disbanded_at.is_(None),
    )
    if warehouse_id is not None:
        pallet_stmt = pallet_stmt.where(Pallet.warehouse_id == warehouse_id)
    pallets = (await session.execute(pallet_stmt)).scalars().all()
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
    matches = [
        ScanMatch(
            type="pallet",
            id=pallet.id,
            name=f"Палета {pallet.code}",
            warehouse_id=pallet.warehouse_id,
        )
        for pallet in pallets
    ]
    matches.extend(
        ScanMatch(
            type="pallet",
            id=place.id,
            name=f"Палета / грузоместо приёмки №{place.place_number}",
            warehouse_id=place_warehouse_id,
        )
        for place, place_warehouse_id in rows
    )
    return matches


async def _find_boxes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    code: str,
    warehouse_id: uuid.UUID | None,
) -> list[ScanMatch]:
    warehouse_stmt = select(WarehouseBox).where(
        WarehouseBox.tenant_id == tenant_id,
        WarehouseBox.internal_barcode == code,
        WarehouseBox.container_kind == "box",
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
    warehouse_stmt = select(WarehouseBox).where(
        WarehouseBox.tenant_id == tenant_id,
        WarehouseBox.internal_barcode == code,
        WarehouseBox.container_kind == "cargo_place",
    )
    if warehouse_id is not None:
        warehouse_stmt = warehouse_stmt.where(WarehouseBox.warehouse_id == warehouse_id)
    warehouse_places = (await session.execute(warehouse_stmt)).scalars().all()
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
    matches = [
        ScanMatch(
            type="cargo_place",
            id=place.id,
            name=f"Складское грузоместо {place.internal_barcode}",
            warehouse_id=place.warehouse_id,
        )
        for place in warehouse_places
    ]
    matches.extend(
        ScanMatch(
            type="cargo_place",
            id=place.id,
            name=f"Грузоместо {place.wb_trbx_id}",
            warehouse_id=place_warehouse_id,
        )
        for place, place_warehouse_id in rows
    )
    return matches


async def _find_products(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    code: str,
    seller_id: uuid.UUID | None = None,
) -> list[ScanMatch]:
    index = await build_product_code_index(
        session,
        scope=ProductCodeScope(
            tenant_id=tenant_id,
            seller_ids=frozenset({seller_id}) if seller_id is not None else None,
        ),
        policy=ProductCodeAliasPolicy(include_marketplace_identity=True),
    )
    resolution = resolve_product_code_from_index(index, code)
    if resolution.status == "not_found":
        return []
    product_ids = await validated_product_ids_from_resolution(
        session,
        tenant_id,
        resolution,
        seller_id=seller_id,
    )
    if not product_ids:
        return []
    stmt = select(Product.id, Product.name).where(
        Product.tenant_id == tenant_id,
        Product.id.in_(product_ids),
    )
    if seller_id is not None:
        stmt = stmt.where(Product.seller_id == seller_id)
    names_by_id = {row.id: row.name for row in (await session.execute(stmt)).all()}
    return [
        ScanMatch(
            type="product",
            id=product_id,
            name=names_by_id[product_id],
            warehouse_id=None,
        )
        for product_id in product_ids
        if product_id in names_by_id
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
    seller_id: uuid.UUID | None = None,
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
    # Seller catalog access grants product lookup only. Filter before resolving
    # ambiguity so neither a match nor a 409 can disclose other sellers' objects.
    if seller_id is None:
        matches.extend(await _find_cells(session, tenant_id, normalized, warehouse_id))
        matches.extend(await _find_pallets(session, tenant_id, normalized, warehouse_id))
        matches.extend(await _find_boxes(session, tenant_id, normalized, warehouse_id))
        matches.extend(await _find_cargo_places(session, tenant_id, normalized, warehouse_id))
    matches.extend(await _find_products(session, tenant_id, normalized, seller_id))
    if seller_id is None:
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
    "validated_product_ids_from_resolution",
]
