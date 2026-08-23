from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import String, cast, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.inbound_intake import InboundIntakeRequest
from app.models.inventory_balance import InventoryBalance
from app.models.outbound_shipment import OutboundShipmentRequest
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse
from app.models.warehouse_storage_rack import WarehouseStorageRack
from app.services import inventory_service as inv_svc
from app.services import sorting_location_service as sorting_loc_svc
from app.services.fbs_stock_publish_service import schedule_seller_stock_publish


class CatalogError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _SkipSentinel:
    pass


SKIP = _SkipSentinel()


async def list_warehouses(session: AsyncSession, tenant_id: uuid.UUID) -> list[Warehouse]:
    stmt = (
        select(Warehouse)
        .where(Warehouse.tenant_id == tenant_id, Warehouse.is_operational.is_(True))
        .order_by(Warehouse.name)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def create_warehouse(
    session: AsyncSession, tenant_id: uuid.UUID, *, name: str, code: str
) -> Warehouse:
    wh = Warehouse(
        tenant_id=tenant_id,
        name=name.strip(),
        code=code.strip().lower(),
        barcode=f"WH-{uuid.uuid4().hex[:12].upper()}",
    )
    session.add(wh)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise CatalogError("warehouse_code_taken") from exc
    await session.refresh(wh)
    await sorting_loc_svc.get_or_create_sorting_location(session, tenant_id, wh.id)
    await session.commit()
    await session.refresh(wh)
    return wh


async def resolve_warehouse_scan(
    session: AsyncSession, tenant_id: uuid.UUID, raw_scan: str
) -> tuple[str, Warehouse | StorageLocation]:
    value = raw_scan.strip()
    if not value:
        raise CatalogError("barcode_empty")
    warehouses = list(
        (
            await session.execute(
                select(Warehouse).where(
                    Warehouse.tenant_id == tenant_id,
                    Warehouse.is_operational.is_(True),
                    (func.lower(Warehouse.code) == value.lower()) | (Warehouse.barcode == value),
                )
            )
        )
        .scalars()
        .all()
    )
    locations = list(
        (
            await session.execute(
                select(StorageLocation).where(
                    StorageLocation.tenant_id == tenant_id,
                    StorageLocation.deleted_at.is_(None),
                    (func.lower(StorageLocation.code) == value.lower())
                    | (StorageLocation.barcode == value),
                )
            )
        )
        .scalars()
        .all()
    )
    if len(warehouses) + len(locations) != 1:
        raise CatalogError("barcode_ambiguous" if warehouses or locations else "barcode_unknown")
    return ("warehouse", warehouses[0]) if warehouses else ("location", locations[0])


async def get_warehouse(
    session: AsyncSession, tenant_id: uuid.UUID, warehouse_id: uuid.UUID
) -> Warehouse | None:
    wh = await session.get(Warehouse, warehouse_id)
    if wh is None or wh.tenant_id != tenant_id:
        return None
    return wh


async def get_storage_location_in_warehouse(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    location_id: uuid.UUID,
) -> StorageLocation | None:
    loc = await session.get(StorageLocation, location_id)
    if (
        loc is None
        or loc.tenant_id != tenant_id
        or loc.warehouse_id != warehouse_id
        or loc.deleted_at is not None
    ):
        return None
    return loc


async def list_locations(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    exclude_sorting_zone: bool = False,
) -> list[StorageLocation]:
    wh = await get_warehouse(session, tenant_id, warehouse_id)
    if wh is None:
        return []
    stmt = (
        select(StorageLocation)
        .where(
            StorageLocation.warehouse_id == warehouse_id,
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.deleted_at.is_(None),
        )
        .order_by(StorageLocation.code)
    )
    res = await session.execute(stmt)
    rows = list(res.scalars().all())
    if exclude_sorting_zone:
        return [loc for loc in rows if not sorting_loc_svc.is_sorting_location(loc)]
    return rows


def _normalize_rack_name(name: str) -> str:
    return name.strip().upper()


def _format_location_code(rack_name: str, side: int, position: int) -> str:
    return f"{rack_name} {side}.{position}"


async def list_racks(
    session: AsyncSession, tenant_id: uuid.UUID, warehouse_id: uuid.UUID
) -> list[WarehouseStorageRack]:
    stmt = (
        select(WarehouseStorageRack)
        .where(
            WarehouseStorageRack.tenant_id == tenant_id,
            WarehouseStorageRack.warehouse_id == warehouse_id,
        )
        .order_by(WarehouseStorageRack.name)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def _get_rack_by_name(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    rack_name: str,
) -> WarehouseStorageRack | None:
    name = _normalize_rack_name(rack_name)
    stmt = select(WarehouseStorageRack).where(
        WarehouseStorageRack.tenant_id == tenant_id,
        WarehouseStorageRack.warehouse_id == warehouse_id,
        WarehouseStorageRack.name == name,
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def _get_or_create_rack(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    rack_name: str,
) -> WarehouseStorageRack:
    name = _normalize_rack_name(rack_name)
    existing = await _get_rack_by_name(session, tenant_id, warehouse_id, rack_name=name)
    if existing is not None:
        return existing

    rack = WarehouseStorageRack(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        name=name,
    )
    session.add(rack)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        # Another request won the race; read it again.
        existing2 = await _get_rack_by_name(session, tenant_id, warehouse_id, rack_name=name)
        if existing2 is not None:
            return existing2
        raise CatalogError("rack_create_failed") from exc
    await session.refresh(rack)
    return rack


async def suggest_next_location_for_rack(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    rack_name: str,
    side: int,
) -> tuple[int, str]:
    if side not in (1, 2):
        raise CatalogError("invalid_side")
    name = _normalize_rack_name(rack_name)
    max_pos = 0
    rack = await _get_rack_by_name(session, tenant_id, warehouse_id, rack_name=rack_name)
    if rack is not None:
        stmt = select(func.max(StorageLocation.position)).where(
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.warehouse_id == warehouse_id,
            StorageLocation.rack_id == rack.id,
            StorageLocation.side == side,
            StorageLocation.position.is_not(None),
        )
        res = await session.execute(stmt)
        max_pos = int(res.scalar_one() or 0)
    next_pos = max_pos + 1
    return next_pos, _format_location_code(name, side, next_pos)


async def create_location_from_rack(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    rack_name: str,
    side: int,
    position: int | None = None,
) -> StorageLocation:
    wh = await get_warehouse(session, tenant_id, warehouse_id)
    if wh is None:
        raise CatalogError("warehouse_not_found")
    if side not in (1, 2):
        raise CatalogError("invalid_side")
    if position is not None and position <= 0:
        raise CatalogError("invalid_position")

    rack = await _get_or_create_rack(session, tenant_id, warehouse_id, rack_name=rack_name)

    if position is None:
        position, code = await suggest_next_location_for_rack(
            session, tenant_id, warehouse_id, rack_name=rack.name, side=side
        )
    else:
        code = _format_location_code(rack.name, side, position)

    # CODE128 supports alphanumeric; keep it short and unique.
    # Persisted in DB and used for printing the barcode label.
    for _ in range(5):
        loc = StorageLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            code=code,
            rack_id=rack.id,
            side=side,
            position=position,
            barcode=f"LOC-{uuid.uuid4().hex[:12].upper()}",
        )
        session.add(loc)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            msg = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
            if "uq_storage_locations_wh_code" in msg or "storage_locations_wh_code" in msg:
                raise CatalogError("location_code_taken") from exc
            if "uq_storage_locations_tenant_barcode" in msg or "tenant_barcode" in msg:
                # Retry barcode collision (extremely unlikely).
                continue
            raise
        await session.refresh(loc)
        return loc
    raise CatalogError("barcode_collision")


async def rename_warehouse(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    name: str,
) -> Warehouse:
    wh = await get_warehouse(session, tenant_id, warehouse_id)
    if wh is None:
        raise CatalogError("warehouse_not_found")
    trimmed = name.strip()
    if not trimmed:
        raise CatalogError("invalid_warehouse_name")
    wh.name = trimmed
    await session.commit()
    await session.refresh(wh)
    return wh


async def delete_warehouse(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
) -> None:
    wh = await get_warehouse(session, tenant_id, warehouse_id)
    if wh is None:
        raise CatalogError("warehouse_not_found")

    docs_count = int(
        await session.scalar(
            select(func.count(InboundIntakeRequest.id)).where(
                InboundIntakeRequest.tenant_id == tenant_id,
                InboundIntakeRequest.warehouse_id == warehouse_id,
            )
        )
        or 0
    )
    docs_count += int(
        await session.scalar(
            select(func.count(OutboundShipmentRequest.id)).where(
                OutboundShipmentRequest.tenant_id == tenant_id,
                OutboundShipmentRequest.warehouse_id == warehouse_id,
            )
        )
        or 0
    )
    if docs_count > 0:
        raise CatalogError("warehouse_has_documents")

    stock_count = int(
        await session.scalar(
            select(func.coalesce(func.sum(InventoryBalance.quantity), 0))
            .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
            .where(
                InventoryBalance.tenant_id == tenant_id,
                StorageLocation.tenant_id == tenant_id,
                StorageLocation.warehouse_id == warehouse_id,
                InventoryBalance.quantity > 0,
            )
        )
        or 0
    )
    if stock_count > 0:
        raise CatalogError("warehouse_has_stock")

    active_regular_locations = int(
        await session.scalar(
            select(func.count(StorageLocation.id)).where(
                StorageLocation.tenant_id == tenant_id,
                StorageLocation.warehouse_id == warehouse_id,
                StorageLocation.deleted_at.is_(None),
                StorageLocation.code != sorting_loc_svc.SORTING_LOCATION_CODE,
            )
        )
        or 0
    )
    if active_regular_locations > 0:
        raise CatalogError("warehouse_has_locations")

    await session.delete(wh)
    await session.commit()


async def rename_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    location_id: uuid.UUID,
    *,
    code: str,
) -> StorageLocation:
    loc = await get_storage_location_in_warehouse(session, tenant_id, warehouse_id, location_id)
    if loc is None:
        raise CatalogError("location_not_found")
    if sorting_loc_svc.is_sorting_location(loc):
        raise CatalogError("system_location_locked")
    trimmed = code.strip()
    if not trimmed:
        raise CatalogError("invalid_location_code")
    loc.code = trimmed
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        msg = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "uq_storage_locations_wh_code" in msg or "storage_locations_wh_code" in msg:
            raise CatalogError("location_code_taken") from exc
        raise
    await session.refresh(loc)
    return loc


async def delete_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    location_id: uuid.UUID,
    *,
    move_stock_to: str | None = None,
) -> None:
    loc = await get_storage_location_in_warehouse(session, tenant_id, warehouse_id, location_id)
    if loc is None:
        raise CatalogError("location_not_found")
    if sorting_loc_svc.is_sorting_location(loc):
        raise CatalogError("system_location_locked")

    balances = list(
        (
            await session.execute(
                select(InventoryBalance).where(
                    InventoryBalance.tenant_id == tenant_id,
                    InventoryBalance.storage_location_id == location_id,
                    InventoryBalance.quantity > 0,
                )
            )
        )
        .scalars()
        .all()
    )
    if balances:
        if move_stock_to not in ("sorting", "unallocated"):
            raise CatalogError("location_has_stock")
        sorting_loc = await sorting_loc_svc.get_or_create_sorting_location(
            session, tenant_id, warehouse_id
        )
        for bal in balances:
            qty = int(bal.quantity)
            if qty < 1:
                continue
            await inv_svc.transfer_on_hand_between_locations(
                session,
                tenant_id,
                from_storage_location_id=location_id,
                to_storage_location_id=sorting_loc.id,
                product_id=bal.product_id,
                quantity=qty,
            )

    loc.deleted_at = datetime.now(UTC)
    await session.commit()


async def create_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    code: str,
) -> StorageLocation:
    wh = await get_warehouse(session, tenant_id, warehouse_id)
    if wh is None:
        raise CatalogError("warehouse_not_found")
    # CODE128 supports alphanumeric; keep it short and unique.
    # Persisted in DB and used for printing the barcode label.
    for _ in range(5):
        loc = StorageLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            code=code.strip(),
            barcode=f"LOC-{uuid.uuid4().hex[:12].upper()}",
        )
        session.add(loc)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            msg = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
            if "uq_storage_locations_wh_code" in msg or "storage_locations_wh_code" in msg:
                raise CatalogError("location_code_taken") from exc
            if "uq_storage_locations_tenant_barcode" in msg or "tenant_barcode" in msg:
                # Retry barcode collision (extremely unlikely).
                continue
            raise
        await session.refresh(loc)
        return loc
    raise CatalogError("barcode_collision")


def volume_liters_from_mm(l_mm: int | None, w_mm: int | None, h_mm: int | None) -> float | None:
    """Объём в литрах: габариты в мм → мм³ / 10⁶ = литры. None если габариты не заданы."""
    if l_mm is None or w_mm is None or h_mm is None:
        return None
    if min(l_mm, w_mm, h_mm) <= 0:
        return None
    return float(l_mm * w_mm * h_mm) / 1_000_000.0


async def list_products(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None = None,
    product_ids: set[uuid.UUID] | None = None,
    search: str | None = None,
    limit: int | None = None,
) -> list[Product]:
    """Товары тенанта. ``search`` и ``limit`` фильтруют в БД, а не в памяти.

    У крупного селлера каталог доходит до десяти тысяч позиций: отдавать его целиком
    и искать на клиенте — шесть мегабайт и десяток секунд на каждый запрос, окно
    выбора товаров при этом выглядит зависшим.
    """
    stmt = (
        select(Product)
        .where(Product.tenant_id == tenant_id)
        .options(selectinload(Product.seller))
        .order_by(Product.sku_code)
    )
    if seller_id is not None:
        stmt = stmt.where(Product.seller_id == seller_id)
    if product_ids is not None:
        if not product_ids:
            return []
        stmt = stmt.where(Product.id.in_(product_ids))
    needle = (search or "").strip()
    if needle:
        like = f"%{needle}%"
        stmt = stmt.where(
            or_(
                Product.sku_code.ilike(like),
                Product.name.ilike(like),
                Product.wb_barcode.ilike(like),
                Product.wb_vendor_code.ilike(like),
                cast(Product.wb_nm_id, String).ilike(like),
            )
        )
    if limit is not None:
        stmt = stmt.limit(limit)
    res = await session.execute(stmt)
    return list(res.scalars().unique().all())


async def list_sellers(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None = None,
) -> list[Seller]:
    stmt = select(Seller).where(Seller.tenant_id == tenant_id).order_by(Seller.name)
    if seller_id is not None:
        stmt = stmt.where(Seller.id == seller_id)
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def create_seller(session: AsyncSession, tenant_id: uuid.UUID, *, name: str) -> Seller:
    s = Seller(tenant_id=tenant_id, name=name.strip())
    session.add(s)
    await session.commit()
    await session.refresh(s)
    return s


# Legacy placeholder a since-removed WB sync default used to write into
# length_mm/width_mm/height_mm when the real dimensions were unknown. Nothing
# writes this value anymore — the sync path leaves dimensions empty instead of
# guessing. Products that still carry this exact 10x10x10 triple have no real
# WB dimensions on file, so the WB import path (wildberries_product_import_service)
# treats that triple as "no data" and is allowed to overwrite it, same as None.
DEFAULT_PRODUCT_DIM_MM = 10


def _normalize_dimensions(
    length_mm: int | None,
    width_mm: int | None,
    height_mm: int | None,
) -> tuple[int | None, int | None, int | None]:
    """All three set, or all None. Partial input is invalid."""
    vals = (length_mm, width_mm, height_mm)
    if all(v is None for v in vals):
        return None, None, None
    if any(v is None for v in vals):
        raise CatalogError("invalid_dimensions")
    assert length_mm is not None and width_mm is not None and height_mm is not None
    if min(length_mm, width_mm, height_mm) <= 0:
        raise CatalogError("invalid_dimensions")
    return length_mm, width_mm, height_mm


def _normalize_weight_g(weight_g: int | None) -> int | None:
    if weight_g is None:
        return None
    if weight_g <= 0:
        raise CatalogError("invalid_weight")
    return weight_g


async def create_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    name: str,
    sku_code: str,
    length_mm: int | None = None,
    width_mm: int | None = None,
    height_mm: int | None = None,
    weight_g: int | None = None,
    seller_id: uuid.UUID | None = None,
    wb_barcode: str | None = None,
    wb_size: str | None = None,
    wb_vendor_code: str | None = None,
    packaging_instructions: str | None = None,
    requires_honest_sign: bool = False,
    commit: bool = True,
) -> Product:
    dim_l, dim_w, dim_h = _normalize_dimensions(length_mm, width_mm, height_mm)
    normalized_weight_g = _normalize_weight_g(weight_g)
    if seller_id is not None:
        sel = await session.get(Seller, seller_id)
        if sel is None or sel.tenant_id != tenant_id:
            raise CatalogError("seller_not_found")
    barcode = (wb_barcode or "").strip() or None
    size = (wb_size or "").strip() or None
    vendor = (wb_vendor_code or "").strip() or None
    tz = (packaging_instructions or "").strip() or None
    p = Product(
        tenant_id=tenant_id,
        seller_id=seller_id,
        name=name.strip(),
        sku_code=sku_code.strip(),
        length_mm=dim_l,
        width_mm=dim_w,
        height_mm=dim_h,
        weight_g=normalized_weight_g,
        volume_liters=volume_liters_from_mm(dim_l, dim_w, dim_h),
        wb_barcode=barcode,
        wb_size=size,
        wb_vendor_code=vendor,
        packaging_instructions=tz,
        requires_honest_sign=requires_honest_sign,
    )
    session.add(p)
    try:
        if commit:
            await session.commit()
        else:
            await session.flush()
    except IntegrityError as exc:
        if commit:
            await session.rollback()
            err = str(getattr(exc, "orig", exc)).lower()
            if "wb_barcode" in err or "uq_products_tenant_wb_barcode" in err:
                raise CatalogError("barcode_taken") from exc
            raise CatalogError("sku_taken") from exc
        # Nested transaction (savepoint) must see IntegrityError to roll back.
        raise
    if commit:
        await session.refresh(p)
    return p


async def get_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
) -> Product | None:
    p = await session.get(Product, product_id)
    if p is None or p.tenant_id != tenant_id:
        return None
    return p


async def update_packaging_instructions(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    packaging_instructions: str | None,
    requires_honest_sign: bool | None = None,
    commit: bool = True,
) -> Product:
    p = await get_product(session, tenant_id, product_id)
    if p is None:
        raise CatalogError("product_not_found")
    text = (packaging_instructions or "").strip()
    p.packaging_instructions = text if text else None
    if requires_honest_sign is not None:
        p.requires_honest_sign = requires_honest_sign
    if commit:
        await session.commit()
        await session.refresh(p, attribute_names=["seller"])
    else:
        await session.flush()
    return p


async def update_product_dimensions(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    length_mm: int | None,
    width_mm: int | None,
    height_mm: int | None,
    weight_g: int | None = None,
    weight_g_set: bool = False,
    commit: bool = True,
) -> Product:
    dim_l, dim_w, dim_h = _normalize_dimensions(length_mm, width_mm, height_mm)
    normalized_weight_g = _normalize_weight_g(weight_g) if weight_g_set else None
    p = await get_product(session, tenant_id, product_id)
    if p is None:
        raise CatalogError("product_not_found")
    p.length_mm = dim_l
    p.width_mm = dim_w
    p.height_mm = dim_h
    if weight_g_set:
        p.weight_g = normalized_weight_g
    p.volume_liters = volume_liters_from_mm(dim_l, dim_w, dim_h)
    if commit:
        await session.commit()
        await session.refresh(p, attribute_names=["seller"])
    else:
        await session.flush()
    return p


async def bulk_update_products_requires_honest_sign(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    product_ids: list[uuid.UUID],
    requires_honest_sign: bool,
    seller_id: uuid.UUID | None = None,
) -> int:
    if not product_ids:
        return 0
    stmt = (
        update(Product)
        .where(
            Product.tenant_id == tenant_id,
            Product.id.in_(product_ids),
        )
        .values(requires_honest_sign=requires_honest_sign)
    )
    if seller_id is not None:
        stmt = stmt.where(Product.seller_id == seller_id)
    result = await session.execute(stmt)
    updated_count = int(getattr(result, "rowcount", 0) or 0)
    await session.commit()
    return updated_count


async def update_product_fbs_stock_sync(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    fbs_stock_sync_enabled: bool | _SkipSentinel = SKIP,
    fbs_stock_limit: int | _SkipSentinel | None = SKIP,
    commit: bool = True,
) -> Product:
    enabled_given = not isinstance(fbs_stock_sync_enabled, _SkipSentinel)
    limit_given = not isinstance(fbs_stock_limit, _SkipSentinel)
    if not enabled_given and not limit_given:
        raise CatalogError("empty_patch")
    limit_value = fbs_stock_limit if limit_given else None
    if isinstance(limit_value, int) and limit_value < 0:
        raise CatalogError("invalid_fbs_stock_limit")
    p = await get_product(session, tenant_id, product_id)
    if p is None:
        raise CatalogError("product_not_found")
    if enabled_given:
        # Явно переданный флаг продолжаем уважать — его шлют старые вызовы и тесты.
        p.fbs_stock_sync_enabled = bool(fbs_stock_sync_enabled)
    elif limit_given:
        # Отдельного тумблера больше нет: участие в FBS выводится из наличия
        # остатка. Задали число — включились; очистили — флаг всё равно
        # остаётся True (см. ниже), чтобы товар не выпал из выгрузки и WB
        # получил честный ноль, а не застрял на последнем опубликованном остатке.
        p.fbs_stock_sync_enabled = True
    if limit_given:
        p.fbs_stock_limit = limit_value if isinstance(limit_value, int) else None
        if limit_value is None and not enabled_given:
            # Лимит очистили руками (не через explicit-флаг) — обнуляем
            # распределение по складам, а не удаляем строки: их наличие с
            # quantity=0 — это осознанный ноль, он проходит через zero-guard.
            zero_pool_stmt = (
                update(FbsBindingStockPool)
                .where(
                    FbsBindingStockPool.tenant_id == tenant_id,
                    FbsBindingStockPool.product_id == p.id,
                )
                .values(quantity=0)
            )
            await session.execute(zero_pool_stmt)
    # Именно в момент переключения новая цифра должна уехать в кабинет WB:
    # включили — кабинет видит остаток фулфилмента, выключили — получает ноль.
    # Ждать ближайшего движения товара или фоновой сверки здесь нельзя.
    schedule_seller_stock_publish(session, tenant_id, p.seller_id)
    if commit:
        await session.commit()
        await session.refresh(p, attribute_names=["seller"])
    else:
        await session.flush()
    return p


async def bulk_update_products_fbs_stock_sync(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    product_ids: list[uuid.UUID] | None,
    fbs_stock_sync_enabled: bool,
    fbs_stock_limit: int | _SkipSentinel | None = SKIP,
) -> int:
    limit_given = not isinstance(fbs_stock_limit, _SkipSentinel)
    limit_value = fbs_stock_limit if limit_given else None
    if isinstance(limit_value, int) and limit_value < 0:
        raise CatalogError("invalid_fbs_stock_limit")
    values: dict[str, object] = {"fbs_stock_sync_enabled": fbs_stock_sync_enabled}
    # Лимит трогаем только когда он явно передан. Иначе «включить всем» стёрло бы
    # лимиты, которые селлер расставил поштучно.
    if limit_given:
        values["fbs_stock_limit"] = limit_value if isinstance(limit_value, int) else None
    stmt = (
        update(Product)
        .where(
            Product.tenant_id == tenant_id,
            Product.seller_id == seller_id,
        )
        .values(**values)
    )
    if product_ids is not None:
        if not product_ids:
            return 0
        stmt = stmt.where(Product.id.in_(product_ids))
    result = await session.execute(stmt)
    updated_count = int(getattr(result, "rowcount", 0) or 0)
    schedule_seller_stock_publish(session, tenant_id, seller_id)
    await session.commit()
    return updated_count


async def products_missing_packaging_instructions(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> list[Product]:
    if not product_ids:
        return []
    stmt = select(Product).where(
        Product.tenant_id == tenant_id,
        Product.id.in_(product_ids),
    )
    res = await session.execute(stmt)
    products = list(res.scalars().all())
    return [p for p in products if not (p.packaging_instructions or "").strip()]
