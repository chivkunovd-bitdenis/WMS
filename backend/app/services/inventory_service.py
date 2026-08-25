from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy import and_, case, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.dml import Insert

from app.models.fbs_order import FbsOrderReservation
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import (
    MOVEMENT_TYPE_FBS_SHIPMENT,
    MOVEMENT_TYPE_INBOUND_INTAKE,
    MOVEMENT_TYPE_MARKETPLACE_UNLOAD,
    MOVEMENT_TYPE_OUTBOUND_SHIPMENT,
    MOVEMENT_TYPE_STOCK_TRANSFER_IN,
    MOVEMENT_TYPE_STOCK_TRANSFER_OUT,
    InventoryMovement,
)
from app.models.inventory_reservation import InventoryReservation
from app.models.marketplace_unload import MarketplaceUnloadLine, MarketplaceUnloadRequest
from app.models.marketplace_unload_reservation import MarketplaceUnloadReservation
from app.models.outbound_shipment import OutboundShipmentLine, OutboundShipmentRequest
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.services.fbs_stock_publish_service import schedule_seller_stock_publish
from app.services.marketplace_unload_status import RESERVE_STATUSES
from app.services.sorting_location_service import SORTING_LOCATION_CODE

OUTBOUND_RESERVE_STATUSES = ("draft", "submitted")
RESERVATION_ERROR = "insufficient_available"
DeductPrefer = Literal["packed", "unpacked"]


def _build_positive_balance_upsert(
    *,
    dialect_name: str,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    quantity_delta: int,
) -> Insert:
    values = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "product_id": product_id,
        "storage_location_id": storage_location_id,
        "quantity": quantity_delta,
        "quantity_unpacked": quantity_delta,
        "quantity_packed": 0,
        "updated_at": datetime.now(UTC),
    }
    update_values = {
        "quantity_unpacked": InventoryBalance.quantity_unpacked + quantity_delta,
        "quantity": (
            InventoryBalance.quantity_unpacked + InventoryBalance.quantity_packed + quantity_delta
        ),
        "updated_at": datetime.now(UTC),
    }
    if dialect_name == "postgresql":
        stmt = postgresql_insert(InventoryBalance).values(**values)
        return stmt.on_conflict_do_update(
            index_elements=[
                InventoryBalance.storage_location_id,
                InventoryBalance.product_id,
            ],
            set_=update_values,
        )
    elif dialect_name == "sqlite":
        sqlite_stmt = sqlite_insert(InventoryBalance).values(**values)
        return sqlite_stmt.on_conflict_do_update(
            index_elements=[
                InventoryBalance.storage_location_id,
                InventoryBalance.product_id,
            ],
            set_=update_values,
        )
    msg = f"unsupported inventory balance dialect: {dialect_name}"
    raise RuntimeError(msg)


async def _physical_on_hand(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
) -> int:
    stmt = select(InventoryBalance.quantity).where(
        InventoryBalance.tenant_id == tenant_id,
        InventoryBalance.product_id == product_id,
        InventoryBalance.storage_location_id == storage_location_id,
    )
    q = await session.scalar(stmt)
    return int(q or 0)


async def available_at_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
) -> int:
    on_hand = await _physical_on_hand(session, tenant_id, product_id, storage_location_id)
    rsv = await total_reserved_at_location(session, tenant_id, product_id, storage_location_id)
    return on_hand - rsv


async def total_reserved_at_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
) -> int:
    sums = await reserved_totals_by_product_at_location(
        session, tenant_id, storage_location_id, [product_id]
    )
    return int(sums.get(product_id, 0))


async def reserved_totals_by_product_at_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> dict[uuid.UUID, int]:
    if not product_ids:
        return {}
    stmt = (
        select(
            InventoryReservation.product_id,
            func.coalesce(func.sum(InventoryReservation.quantity), 0),
        )
        .join(
            OutboundShipmentLine,
            OutboundShipmentLine.id == InventoryReservation.outbound_shipment_line_id,
        )
        .join(
            OutboundShipmentRequest,
            OutboundShipmentRequest.id == OutboundShipmentLine.request_id,
        )
        .where(
            InventoryReservation.tenant_id == tenant_id,
            InventoryReservation.storage_location_id == storage_location_id,
            InventoryReservation.product_id.in_(product_ids),
            OutboundShipmentRequest.status.in_(OUTBOUND_RESERVE_STATUSES),
        )
        .group_by(InventoryReservation.product_id)
    )
    res = await session.execute(stmt)
    return {pid: int(s or 0) for pid, s in res.all()}


async def reserved_totals_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_ids: list[uuid.UUID],
    *,
    warehouse_id: uuid.UUID | None = None,
) -> dict[uuid.UUID, int]:
    if not product_ids:
        return {}
    stmt = (
        select(
            InventoryReservation.product_id,
            func.coalesce(func.sum(InventoryReservation.quantity), 0),
        )
        .join(
            OutboundShipmentLine,
            OutboundShipmentLine.id == InventoryReservation.outbound_shipment_line_id,
        )
        .join(
            OutboundShipmentRequest,
            OutboundShipmentRequest.id == OutboundShipmentLine.request_id,
        )
        .where(
            InventoryReservation.tenant_id == tenant_id,
            InventoryReservation.product_id.in_(product_ids),
            OutboundShipmentRequest.status.in_(OUTBOUND_RESERVE_STATUSES),
        )
        .group_by(InventoryReservation.product_id)
    )
    if warehouse_id is not None:
        stmt = stmt.outerjoin(
            StorageLocation,
            StorageLocation.id == InventoryReservation.storage_location_id,
        ).where(
            or_(
                and_(
                    InventoryReservation.storage_location_id.isnot(None),
                    StorageLocation.tenant_id == tenant_id,
                    StorageLocation.warehouse_id == warehouse_id,
                ),
                and_(
                    InventoryReservation.storage_location_id.is_(None),
                    InventoryReservation.warehouse_id == warehouse_id,
                ),
            )
        )
    res = await session.execute(stmt)
    outbound_map = {pid: int(s or 0) for pid, s in res.all()}

    mp_stmt = (
        select(
            MarketplaceUnloadReservation.product_id,
            func.coalesce(func.sum(MarketplaceUnloadReservation.quantity), 0),
        )
        .join(
            MarketplaceUnloadLine,
            MarketplaceUnloadLine.id == MarketplaceUnloadReservation.marketplace_unload_line_id,
        )
        .join(
            MarketplaceUnloadRequest,
            MarketplaceUnloadRequest.id == MarketplaceUnloadLine.request_id,
        )
        .where(
            MarketplaceUnloadReservation.tenant_id == tenant_id,
            MarketplaceUnloadReservation.product_id.in_(product_ids),
            MarketplaceUnloadRequest.status.in_(RESERVE_STATUSES),
        )
        .group_by(MarketplaceUnloadReservation.product_id)
    )
    if warehouse_id is not None:
        mp_stmt = mp_stmt.where(MarketplaceUnloadReservation.warehouse_id == warehouse_id)
    mp_res = await session.execute(mp_stmt)
    mp_map = {pid: int(s or 0) for pid, s in mp_res.all()}

    fbs_map: dict[uuid.UUID, int] = {}
    if warehouse_id is not None:
        fbs_stmt = (
            select(
                FbsOrderReservation.product_id,
                func.coalesce(func.sum(FbsOrderReservation.quantity), 0),
            )
            .where(
                FbsOrderReservation.tenant_id == tenant_id,
                FbsOrderReservation.warehouse_id == warehouse_id,
                FbsOrderReservation.product_id.in_(product_ids),
            )
            .group_by(FbsOrderReservation.product_id)
        )
        fbs_res = await session.execute(fbs_stmt)
        fbs_map = {pid: int(s or 0) for pid, s in fbs_res.all()}

    return {
        pid: int(outbound_map.get(pid, 0)) + int(mp_map.get(pid, 0)) + int(fbs_map.get(pid, 0))
        for pid in product_ids
    }


async def list_balances_total(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_product_owner_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
) -> list[tuple[uuid.UUID, str, str, int, int, int, int, int]]:
    """Итоговые остатки по SKU (сумма по всем ячейкам, в т.ч. зона сортировки).

    Возвращает:
    (product_id, sku_code, product_name, quantity_total, quantity_in_sorting,
     quantity_unpacked_total, quantity_packed_total, reserved_total)
    """
    sorting_qty = func.coalesce(
        func.sum(
            case(
                (StorageLocation.code == SORTING_LOCATION_CODE, InventoryBalance.quantity),
                else_=0,
            )
        ),
        0,
    )
    stmt = (
        select(
            Product.id,
            Product.sku_code,
            Product.name,
            func.coalesce(func.sum(InventoryBalance.quantity), 0),
            sorting_qty,
            func.coalesce(func.sum(InventoryBalance.quantity_unpacked), 0),
            func.coalesce(func.sum(InventoryBalance.quantity_packed), 0),
        )
        .join(InventoryBalance, InventoryBalance.product_id == Product.id)
        .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
        .where(
            Product.tenant_id == tenant_id,
            InventoryBalance.tenant_id == tenant_id,
            StorageLocation.tenant_id == tenant_id,
        )
        .group_by(Product.id, Product.sku_code, Product.name)
        .order_by(Product.sku_code)
    )
    if seller_product_owner_id is not None:
        stmt = stmt.where(Product.seller_id == seller_product_owner_id)
    if warehouse_id is not None:
        stmt = stmt.where(StorageLocation.warehouse_id == warehouse_id)
    res = await session.execute(stmt)
    rows = [
        (pid, sku, name, int(q or 0), int(sort_q or 0), int(unp or 0), int(pck or 0))
        for pid, sku, name, q, sort_q, unp, pck in res.all()
    ]
    if not rows:
        return []
    pids = [pid for pid, *_ in rows]
    rsv_map = await reserved_totals_by_product(session, tenant_id, pids, warehouse_id=warehouse_id)
    return [
        (pid, sku, name, qty, sort_qty, unp, pck, int(rsv_map.get(pid, 0)))
        for pid, sku, name, qty, sort_qty, unp, pck in rows
    ]


async def reserved_qty_excluding_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    exclude_line_id: uuid.UUID,
) -> int:
    stmt = (
        select(func.coalesce(func.sum(InventoryReservation.quantity), 0))
        .join(
            OutboundShipmentLine,
            OutboundShipmentLine.id == InventoryReservation.outbound_shipment_line_id,
        )
        .join(
            OutboundShipmentRequest,
            OutboundShipmentRequest.id == OutboundShipmentLine.request_id,
        )
        .where(
            InventoryReservation.tenant_id == tenant_id,
            InventoryReservation.product_id == product_id,
            InventoryReservation.storage_location_id == storage_location_id,
            OutboundShipmentRequest.status.in_(OUTBOUND_RESERVE_STATUSES),
            OutboundShipmentLine.id != exclude_line_id,
        )
    )
    res = await session.scalar(stmt)
    return int(res or 0)


async def available_quantity_at_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
) -> int:
    on_hand = await _physical_on_hand(session, tenant_id, product_id, storage_location_id)
    reserved = await total_reserved_at_location(session, tenant_id, product_id, storage_location_id)
    return on_hand - reserved


async def _physical_on_hand_in_warehouse(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
) -> int:
    stmt = (
        select(func.coalesce(func.sum(InventoryBalance.quantity), 0))
        .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id == product_id,
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.warehouse_id == warehouse_id,
        )
    )
    return int(await session.scalar(stmt) or 0)


async def storage_on_hand_in_warehouse(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
) -> int:
    """Остаток в ячейках хранения (без зоны «Сортировка»)."""
    stmt = (
        select(func.coalesce(func.sum(InventoryBalance.quantity), 0))
        .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id == product_id,
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.warehouse_id == warehouse_id,
            StorageLocation.code != SORTING_LOCATION_CODE,
        )
    )
    return int(await session.scalar(stmt) or 0)


async def sorting_on_hand_in_warehouse(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
) -> int:
    """Остаток в зоне «Сортировка» (буфер до раскладки)."""
    stmt = (
        select(func.coalesce(func.sum(InventoryBalance.quantity), 0))
        .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id == product_id,
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.warehouse_id == warehouse_id,
            StorageLocation.code == SORTING_LOCATION_CODE,
        )
    )
    return int(await session.scalar(stmt) or 0)


async def _schedule_fbs_publish_for_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
) -> None:
    """Ставит публикацию остатка ФБС по владельцу товара, если он известен."""
    product = await session.get(Product, product_id)
    if product is not None:
        schedule_seller_stock_publish(session, tenant_id, product.seller_id)


async def sync_outbound_line_reservation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request: OutboundShipmentRequest,
    line: OutboundShipmentLine,
) -> None:
    await session.execute(
        delete(InventoryReservation).where(
            InventoryReservation.outbound_shipment_line_id == line.id,
        )
    )

    # Резерв под исходящую отгрузку вычитается из доступного для ФБС
    # (`fbs_available_qty_by_product` минусует `_outbound_reserved_by_product`).
    # Значит и постановка, и снятие резерва меняют цифру, которую должен видеть WB.
    # Ставим публикацию здесь, до всех ранних `return`, чтобы не потерять ни один путь.
    await _schedule_fbs_publish_for_product(session, tenant_id, line.product_id)

    should_hold = request.status in OUTBOUND_RESERVE_STATUSES and line.shipped_qty < line.quantity
    if not should_hold:
        return

    desired = line.quantity - line.shipped_qty
    if desired < 1:
        return

    sid = line.storage_location_id
    if sid is not None:
        on_hand = await _physical_on_hand(session, tenant_id, line.product_id, sid)
        others = await reserved_qty_excluding_line(
            session, tenant_id, line.product_id, sid, line.id
        )
        if on_hand < others + desired:
            raise ValueError(RESERVATION_ERROR)
        session.add(
            InventoryReservation(
                tenant_id=tenant_id,
                outbound_shipment_line_id=line.id,
                product_id=line.product_id,
                storage_location_id=sid,
                warehouse_id=None,
                quantity=desired,
            )
        )
        return

    wh_id = request.warehouse_id
    on_hand_wh = await storage_on_hand_in_warehouse(session, tenant_id, wh_id, line.product_id)
    rsv_map = await reserved_totals_by_product(
        session,
        tenant_id,
        [line.product_id],
        warehouse_id=wh_id,
    )
    already = int(rsv_map.get(line.product_id, 0))
    if on_hand_wh < already + desired:
        raise ValueError(RESERVATION_ERROR)

    session.add(
        InventoryReservation(
            tenant_id=tenant_id,
            outbound_shipment_line_id=line.id,
            product_id=line.product_id,
            storage_location_id=None,
            warehouse_id=wh_id,
            quantity=desired,
        )
    )


async def list_balances_at_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    *,
    seller_product_owner_id: uuid.UUID | None = None,
) -> list[tuple[InventoryBalance, Product, int]] | None:
    loc = await session.get(StorageLocation, storage_location_id)
    if loc is None or loc.tenant_id != tenant_id:
        return None
    stmt = (
        select(InventoryBalance, Product)
        .join(Product, Product.id == InventoryBalance.product_id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.storage_location_id == storage_location_id,
        )
        .options(selectinload(Product.seller))
        .order_by(Product.sku_code)
    )
    if seller_product_owner_id is not None:
        stmt = stmt.where(Product.seller_id == seller_product_owner_id)
    res = await session.execute(stmt)
    pairs = [(b, p) for b, p in res.all()]
    if not pairs:
        return []
    pids = list({b.product_id for b, _ in pairs})
    rsv_map = await reserved_totals_by_product_at_location(
        session, tenant_id, storage_location_id, pids
    )
    return [(b, p, int(rsv_map.get(b.product_id, 0))) for b, p in pairs]


async def record_movement_and_adjust_balance(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    quantity_delta: int,
    movement_type: str,
    inbound_intake_line_id: uuid.UUID | None = None,
    outbound_shipment_line_id: uuid.UUID | None = None,
    transfer_group_id: uuid.UUID | None = None,
    marketplace_unload_request_id: uuid.UUID | None = None,
    deduct_prefer: DeductPrefer = "unpacked",
) -> InventoryMovement:
    """Запись в журнал и изменение остатка (delta может быть отрицательным)."""
    if quantity_delta == 0:
        msg = "quantity_delta must be non-zero"
        raise ValueError(msg)

    loc = await session.get(StorageLocation, storage_location_id)
    if loc is None or loc.tenant_id != tenant_id:
        msg = "storage location not found"
        raise ValueError(msg)

    prod = await session.get(Product, product_id)
    if prod is None or prod.tenant_id != tenant_id:
        msg = "product not found"
        raise ValueError(msg)

    movement = InventoryMovement(
        tenant_id=tenant_id,
        product_id=product_id,
        seller_id=prod.seller_id,
        storage_location_id=storage_location_id,
        warehouse_id=loc.warehouse_id,
        quantity_delta=quantity_delta,
        movement_type=movement_type,
        inbound_intake_line_id=inbound_intake_line_id,
        outbound_shipment_line_id=outbound_shipment_line_id,
        transfer_group_id=transfer_group_id,
        marketplace_unload_request_id=marketplace_unload_request_id,
    )
    session.add(movement)

    # Единственная точка, через которую меняется остаток, — значит и единственное место,
    # где надо поставить в очередь публикацию нового количества в кабинет WB.
    # Сама публикация уйдёт после коммита, снаружи этой транзакции.
    schedule_seller_stock_publish(session, tenant_id, prod.seller_id)

    if quantity_delta >= 0:
        bind = session.get_bind()
        await session.execute(
            _build_positive_balance_upsert(
                dialect_name=bind.dialect.name,
                tenant_id=tenant_id,
                product_id=product_id,
                storage_location_id=storage_location_id,
                quantity_delta=quantity_delta,
            )
        )
        return movement

    quantity_to_deduct = -quantity_delta
    unpacked = InventoryBalance.quantity_unpacked
    packed = InventoryBalance.quantity_packed
    preferred = unpacked if deduct_prefer == "unpacked" else packed
    deducted_from_preferred = case(
        (preferred >= quantity_to_deduct, quantity_to_deduct),
        else_=preferred,
    )
    if deduct_prefer == "unpacked":
        next_unpacked = unpacked - deducted_from_preferred
        next_packed = packed - (quantity_to_deduct - deducted_from_preferred)
    else:
        next_packed = packed - deducted_from_preferred
        next_unpacked = unpacked - (quantity_to_deduct - deducted_from_preferred)
    updated_balance_id = await session.scalar(
        update(InventoryBalance)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id == product_id,
            InventoryBalance.storage_location_id == storage_location_id,
            unpacked + packed >= quantity_to_deduct,
        )
        .values(
            quantity_unpacked=next_unpacked,
            quantity_packed=next_packed,
            quantity=unpacked + packed - quantity_to_deduct,
            updated_at=datetime.now(UTC),
        )
        .returning(InventoryBalance.id)
        .execution_options(synchronize_session=False)
    )
    if updated_balance_id is None:
        msg = "insufficient stock"
        raise ValueError(msg)
    return movement


async def apply_packaging_convert(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    quantity: int,
    require_unpacked: bool = True,
) -> None:
    """Перевод qty из не упаковано в упаковано в том же месте.

    По умолчанию (``require_unpacked=True``) операция требует, чтобы именно
    неупакованной части хватало на всю запрошенную quantity — так ведёт себя
    обычная (не FBS) упаковка, где деление важно для планирования остатка.

    ``require_unpacked=False`` снимает это требование: гейт — ОБЩИЙ остаток
    в ячейке (unpacked + packed), а не его неупакованная часть. Перенос
    по-прежнему идёт из «не упаковано» в «упаковано», но только на то
    количество, которое там реально есть (может быть 0) — остаток deficit
    просто уже числится упакованным на этом месте, и это не повод падать.
    Уйти в минус по общему остатку по-прежнему нельзя.
    """
    if quantity < 1:
        msg = "quantity must be positive"
        raise ValueError(msg)
    loc = await session.get(StorageLocation, storage_location_id)
    if loc is None or loc.tenant_id != tenant_id:
        msg = "storage location not found"
        raise ValueError(msg)
    prod = await session.get(Product, product_id)
    if prod is None or prod.tenant_id != tenant_id:
        msg = "product not found"
        raise ValueError(msg)
    unpacked = InventoryBalance.quantity_unpacked
    packed = InventoryBalance.quantity_packed
    if require_unpacked:
        stmt = (
            update(InventoryBalance)
            .where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == storage_location_id,
                unpacked >= quantity,
            )
            .values(
                quantity_unpacked=unpacked - quantity,
                quantity_packed=packed + quantity,
                quantity=unpacked + packed,
                updated_at=datetime.now(UTC),
            )
        )
    else:
        moved_from_unpacked = case((unpacked >= quantity, quantity), else_=unpacked)
        stmt = (
            update(InventoryBalance)
            .where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == storage_location_id,
                unpacked + packed >= quantity,
            )
            .values(
                quantity_unpacked=unpacked - moved_from_unpacked,
                quantity_packed=packed + moved_from_unpacked,
                quantity=unpacked + packed,
                updated_at=datetime.now(UTC),
            )
        )
    updated_balance_id = await session.scalar(
        stmt.returning(InventoryBalance.id).execution_options(synchronize_session=False)
    )
    if updated_balance_id is None:
        msg = "insufficient_unpacked" if require_unpacked else "insufficient_stock"
        raise ValueError(msg)


async def reverse_packaging_convert(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    quantity: int,
) -> None:
    """Вернуть qty из упаковано в не упаковано в той же ячейке."""
    if quantity < 1:
        msg = "quantity must be positive"
        raise ValueError(msg)
    loc = await session.get(StorageLocation, storage_location_id)
    if loc is None or loc.tenant_id != tenant_id:
        msg = "storage location not found"
        raise ValueError(msg)
    prod = await session.get(Product, product_id)
    if prod is None or prod.tenant_id != tenant_id:
        msg = "product not found"
        raise ValueError(msg)
    unpacked = InventoryBalance.quantity_unpacked
    packed = InventoryBalance.quantity_packed
    updated_balance_id = await session.scalar(
        update(InventoryBalance)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id == product_id,
            InventoryBalance.storage_location_id == storage_location_id,
            packed >= quantity,
        )
        .values(
            quantity_unpacked=unpacked + quantity,
            quantity_packed=packed - quantity,
            quantity=unpacked + packed,
            updated_at=datetime.now(UTC),
        )
        .returning(InventoryBalance.id)
        .execution_options(synchronize_session=False)
    )
    if updated_balance_id is None:
        msg = "insufficient_packed"
        raise ValueError(msg)


async def apply_inbound_receive(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    quantity: int,
    movement_type: str,
    inbound_intake_line_id: uuid.UUID,
) -> None:
    """Приход по строке приёмки (положительный delta)."""
    if quantity <= 0:
        msg = "quantity must be positive"
        raise ValueError(msg)
    await record_movement_and_adjust_balance(
        session,
        tenant_id=tenant_id,
        product_id=product_id,
        storage_location_id=storage_location_id,
        quantity_delta=quantity,
        movement_type=movement_type or MOVEMENT_TYPE_INBOUND_INTAKE,
        inbound_intake_line_id=inbound_intake_line_id,
    )


async def reverse_inbound_receive(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    quantity: int,
    inbound_intake_line_id: uuid.UUID,
) -> None:
    """Сторно прихода по строке приёмки (отрицательный delta в зоне сортировки)."""
    if quantity <= 0:
        msg = "quantity must be positive"
        raise ValueError(msg)
    await record_movement_and_adjust_balance(
        session,
        tenant_id=tenant_id,
        product_id=product_id,
        storage_location_id=storage_location_id,
        quantity_delta=-quantity,
        movement_type=MOVEMENT_TYPE_INBOUND_INTAKE,
        inbound_intake_line_id=inbound_intake_line_id,
    )


async def apply_putaway_from_sorting(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    from_storage_location_id: uuid.UUID,
    to_storage_location_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: int,
    inbound_intake_line_id: uuid.UUID,
) -> None:
    """Перемещение из зоны сортировки в ячейку хранения (привязка к строке приёмки)."""
    if quantity < 1:
        msg = "quantity must be positive"
        raise ValueError(msg)
    if from_storage_location_id == to_storage_location_id:
        msg = "from and to must differ"
        raise ValueError(msg)

    loc_from = await session.get(StorageLocation, from_storage_location_id)
    loc_to = await session.get(StorageLocation, to_storage_location_id)
    if (
        loc_from is None
        or loc_to is None
        or loc_from.tenant_id != tenant_id
        or loc_to.tenant_id != tenant_id
    ):
        msg = "storage location not found"
        raise ValueError(msg)
    if loc_from.warehouse_id != loc_to.warehouse_id:
        msg = "locations must be in the same warehouse"
        raise ValueError(msg)

    avail = await available_quantity_at_location(
        session, tenant_id, product_id, from_storage_location_id
    )
    if avail < quantity:
        msg = "insufficient stock"
        raise ValueError(msg)

    group_id = uuid.uuid4()
    await record_movement_and_adjust_balance(
        session,
        tenant_id=tenant_id,
        product_id=product_id,
        storage_location_id=from_storage_location_id,
        quantity_delta=-quantity,
        movement_type=MOVEMENT_TYPE_STOCK_TRANSFER_OUT,
        transfer_group_id=group_id,
        inbound_intake_line_id=inbound_intake_line_id,
    )
    await record_movement_and_adjust_balance(
        session,
        tenant_id=tenant_id,
        product_id=product_id,
        storage_location_id=to_storage_location_id,
        quantity_delta=quantity,
        movement_type=MOVEMENT_TYPE_STOCK_TRANSFER_IN,
        transfer_group_id=group_id,
        inbound_intake_line_id=inbound_intake_line_id,
    )


async def apply_return_defect_putaway(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    from_storage_location_id: uuid.UUID,
    to_storage_location_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: int,
    inbound_intake_line_id: uuid.UUID,
) -> None:
    """Move inspected defective return stock into the tenant's service warehouse."""
    if quantity < 1:
        raise ValueError("quantity must be positive")
    if from_storage_location_id == to_storage_location_id:
        raise ValueError("from and to must differ")
    loc_from = await session.get(StorageLocation, from_storage_location_id)
    loc_to = await session.get(StorageLocation, to_storage_location_id)
    if (
        loc_from is None
        or loc_to is None
        or loc_from.tenant_id != tenant_id
        or loc_to.tenant_id != tenant_id
    ):
        raise ValueError("storage location not found")
    available = await available_quantity_at_location(
        session, tenant_id, product_id, from_storage_location_id
    )
    if available < quantity:
        raise ValueError("insufficient stock")
    group_id = uuid.uuid4()
    await record_movement_and_adjust_balance(
        session,
        tenant_id=tenant_id,
        product_id=product_id,
        storage_location_id=from_storage_location_id,
        quantity_delta=-quantity,
        movement_type=MOVEMENT_TYPE_STOCK_TRANSFER_OUT,
        transfer_group_id=group_id,
        inbound_intake_line_id=inbound_intake_line_id,
    )
    await record_movement_and_adjust_balance(
        session,
        tenant_id=tenant_id,
        product_id=product_id,
        storage_location_id=to_storage_location_id,
        quantity_delta=quantity,
        movement_type=MOVEMENT_TYPE_STOCK_TRANSFER_IN,
        transfer_group_id=group_id,
        inbound_intake_line_id=inbound_intake_line_id,
    )


async def apply_stock_transfer(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    from_storage_location_id: uuid.UUID,
    to_storage_location_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: int,
) -> None:
    """Перемещение между ячейками одного склада."""
    if quantity < 1:
        msg = "quantity must be positive"
        raise ValueError(msg)
    if from_storage_location_id == to_storage_location_id:
        msg = "from and to must differ"
        raise ValueError(msg)

    loc_from = await session.get(StorageLocation, from_storage_location_id)
    loc_to = await session.get(StorageLocation, to_storage_location_id)
    if (
        loc_from is None
        or loc_to is None
        or loc_from.tenant_id != tenant_id
        or loc_to.tenant_id != tenant_id
    ):
        msg = "storage location not found"
        raise ValueError(msg)
    if loc_from.warehouse_id != loc_to.warehouse_id:
        msg = "locations must be in the same warehouse"
        raise ValueError(msg)

    avail = await available_quantity_at_location(
        session, tenant_id, product_id, from_storage_location_id
    )
    if avail < quantity:
        msg = "insufficient stock"
        raise ValueError(msg)

    group_id = uuid.uuid4()
    await record_movement_and_adjust_balance(
        session,
        tenant_id=tenant_id,
        product_id=product_id,
        storage_location_id=from_storage_location_id,
        quantity_delta=-quantity,
        movement_type=MOVEMENT_TYPE_STOCK_TRANSFER_OUT,
        transfer_group_id=group_id,
    )
    await record_movement_and_adjust_balance(
        session,
        tenant_id=tenant_id,
        product_id=product_id,
        storage_location_id=to_storage_location_id,
        quantity_delta=quantity,
        movement_type=MOVEMENT_TYPE_STOCK_TRANSFER_IN,
        transfer_group_id=group_id,
    )


async def list_location_balances_for_products_in_warehouse(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> list[tuple[uuid.UUID, uuid.UUID, str, int, int]]:
    """product_id, location_id, location_code, on_hand, reserved."""
    if not product_ids:
        return []
    stmt = (
        select(
            InventoryBalance.product_id,
            StorageLocation.id,
            StorageLocation.code,
            InventoryBalance.quantity,
        )
        .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.warehouse_id == warehouse_id,
            InventoryBalance.product_id.in_(product_ids),
            InventoryBalance.quantity > 0,
        )
        .order_by(StorageLocation.code.asc())
    )
    res = await session.execute(stmt)
    rows: list[tuple[uuid.UUID, uuid.UUID, str, int, int]] = []
    for pid, loc_id, code, qty in res.all():
        rsv = await total_reserved_at_location(session, tenant_id, pid, loc_id)
        rows.append((pid, loc_id, str(code), int(qty), int(rsv)))
    return rows


async def list_locations_for_product_in_warehouse(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
) -> list[tuple[uuid.UUID, str, int, int]]:
    """location_id, location_code, on_hand, reserved — sorted by on_hand desc."""
    rows = await list_location_balances_for_products_in_warehouse(
        session, tenant_id, warehouse_id, [product_id]
    )
    product_rows = [
        (loc_id, code, on_hand, rsv)
        for pid, loc_id, code, on_hand, rsv in rows
        if pid == product_id and code != SORTING_LOCATION_CODE
    ]
    product_rows.sort(key=lambda x: x[2], reverse=True)
    return product_rows


async def _lock_inventory_balance(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
) -> InventoryBalance | None:
    stmt = (
        select(InventoryBalance)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id == product_id,
            InventoryBalance.storage_location_id == storage_location_id,
        )
        .with_for_update()
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def apply_fbs_supply_write_off(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    quantity: int,
) -> InventoryMovement:
    """Списание упакованного FBS-товара при завершении упаковки поставки."""
    if quantity < 1:
        msg = "quantity must be positive"
        raise ValueError(msg)
    bal = await _lock_inventory_balance(session, tenant_id, product_id, storage_location_id)
    if bal is None or int(bal.quantity) < quantity:
        msg = "insufficient stock"
        raise ValueError(msg)
    from app.services import stock_direction_service

    try:
        await stock_direction_service.consume_fbs_pool(
            session,
            tenant_id,
            product_id,
            quantity,
        )
    except stock_direction_service.StockDirectionError as exc:
        if exc.code == "insufficient_fbs_pool":
            msg = "insufficient_fbs_pool"
            raise ValueError(msg) from exc
        raise
    return await record_movement_and_adjust_balance(
        session,
        tenant_id=tenant_id,
        product_id=product_id,
        storage_location_id=storage_location_id,
        quantity_delta=-quantity,
        movement_type=MOVEMENT_TYPE_FBS_SHIPMENT,
        deduct_prefer="packed",
    )


async def apply_marketplace_unload_pick(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    quantity: int,
    marketplace_unload_request_id: uuid.UUID,
) -> None:
    if quantity < 1:
        msg = "quantity must be positive"
        raise ValueError(msg)
    bal = await _lock_inventory_balance(session, tenant_id, product_id, storage_location_id)
    if bal is None or int(bal.quantity) < quantity:
        msg = "insufficient stock"
        raise ValueError(msg)
    await record_movement_and_adjust_balance(
        session,
        tenant_id=tenant_id,
        product_id=product_id,
        storage_location_id=storage_location_id,
        quantity_delta=-quantity,
        movement_type=MOVEMENT_TYPE_MARKETPLACE_UNLOAD,
        marketplace_unload_request_id=marketplace_unload_request_id,
        deduct_prefer="packed",
    )


async def reverse_marketplace_unload_pick(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    quantity: int,
    marketplace_unload_request_id: uuid.UUID,
) -> None:
    """DEC-016: restore on_hand when removing qty from shipment box."""
    if quantity < 1:
        msg = "quantity must be positive"
        raise ValueError(msg)
    await record_movement_and_adjust_balance(
        session,
        tenant_id=tenant_id,
        product_id=product_id,
        storage_location_id=storage_location_id,
        quantity_delta=quantity,
        movement_type=MOVEMENT_TYPE_MARKETPLACE_UNLOAD,
        marketplace_unload_request_id=marketplace_unload_request_id,
    )


async def apply_outbound_shipment_line(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    quantity: int,
    outbound_shipment_line_id: uuid.UUID,
) -> None:
    """Списание по строке отгрузки (отрицательный delta)."""
    if quantity < 1:
        msg = "quantity must be positive"
        raise ValueError(msg)
    await record_movement_and_adjust_balance(
        session,
        tenant_id=tenant_id,
        product_id=product_id,
        storage_location_id=storage_location_id,
        quantity_delta=-quantity,
        movement_type=MOVEMENT_TYPE_OUTBOUND_SHIPMENT,
        outbound_shipment_line_id=outbound_shipment_line_id,
    )


async def list_movements_for_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    seller_product_owner_id: uuid.UUID | None = None,
) -> list[InventoryMovement]:
    stmt = (
        select(InventoryMovement)
        .join(
            InboundIntakeLine,
            InboundIntakeLine.id == InventoryMovement.inbound_intake_line_id,
        )
        .join(
            InboundIntakeRequest,
            InboundIntakeRequest.id == InboundIntakeLine.request_id,
        )
        .where(
            InboundIntakeRequest.tenant_id == tenant_id,
            InboundIntakeRequest.id == request_id,
        )
    )
    if seller_product_owner_id is not None:
        stmt = stmt.join(Product, Product.id == InboundIntakeLine.product_id).where(
            Product.seller_id == seller_product_owner_id,
        )
    stmt = stmt.order_by(InventoryMovement.created_at.desc())
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def list_recent_movements(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    limit: int = 100,
    seller_product_owner_id: uuid.UUID | None = None,
) -> list[tuple[InventoryMovement, Product]]:
    stmt = (
        select(InventoryMovement, Product)
        .join(Product, Product.id == InventoryMovement.product_id)
        .where(InventoryMovement.tenant_id == tenant_id)
        .order_by(InventoryMovement.created_at.desc())
        .limit(limit)
    )
    if seller_product_owner_id is not None:
        stmt = stmt.where(Product.seller_id == seller_product_owner_id)
    res = await session.execute(stmt)
    return [(m, p) for m, p in res.all()]


async def transfer_on_hand_between_locations(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    from_storage_location_id: uuid.UUID,
    to_storage_location_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: int,
) -> uuid.UUID:
    """Перемещение фактического on_hand между ячейками (DEC-019 migration).

    Returns transfer_group_id for audit linkage.
    """
    if quantity < 1:
        msg = "quantity must be positive"
        raise ValueError(msg)
    if from_storage_location_id == to_storage_location_id:
        msg = "from and to must differ"
        raise ValueError(msg)

    loc_from = await session.get(StorageLocation, from_storage_location_id)
    loc_to = await session.get(StorageLocation, to_storage_location_id)
    if (
        loc_from is None
        or loc_to is None
        or loc_from.tenant_id != tenant_id
        or loc_to.tenant_id != tenant_id
    ):
        msg = "storage location not found"
        raise ValueError(msg)
    if loc_from.warehouse_id != loc_to.warehouse_id:
        msg = "locations must be in the same warehouse"
        raise ValueError(msg)

    on_hand = await _physical_on_hand(session, tenant_id, product_id, from_storage_location_id)
    if on_hand < quantity:
        msg = "insufficient stock"
        raise ValueError(msg)

    group_id = uuid.uuid4()
    await record_movement_and_adjust_balance(
        session,
        tenant_id=tenant_id,
        product_id=product_id,
        storage_location_id=from_storage_location_id,
        quantity_delta=-quantity,
        movement_type=MOVEMENT_TYPE_STOCK_TRANSFER_OUT,
        transfer_group_id=group_id,
    )
    await record_movement_and_adjust_balance(
        session,
        tenant_id=tenant_id,
        product_id=product_id,
        storage_location_id=to_storage_location_id,
        quantity_delta=quantity,
        movement_type=MOVEMENT_TYPE_STOCK_TRANSFER_IN,
        transfer_group_id=group_id,
    )
    return group_id


async def transfer_out_movement_id(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    transfer_group_id: uuid.UUID,
) -> uuid.UUID | None:
    """Inventory movement id for the outbound leg of a stock transfer."""
    stmt = (
        select(InventoryMovement.id)
        .where(
            InventoryMovement.tenant_id == tenant_id,
            InventoryMovement.transfer_group_id == transfer_group_id,
            InventoryMovement.movement_type == MOVEMENT_TYPE_STOCK_TRANSFER_OUT,
        )
        .limit(1)
    )
    return cast(uuid.UUID | None, await session.scalar(stmt))


async def migrate_all_address_balances_to_sorting(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> None:
    """DEC-019: move all address-cell on_hand balances to sorting virtual zone."""
    from app.services import sorting_location_service as sort_loc_svc

    stmt = (
        select(InventoryBalance, StorageLocation)
        .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.quantity > 0,
            StorageLocation.code != SORTING_LOCATION_CODE,
        )
    )
    rows = (await session.execute(stmt)).all()
    sorting_by_wh: dict[uuid.UUID, uuid.UUID] = {}

    for bal, loc in rows:
        qty = int(bal.quantity)
        if qty < 1:
            continue
        wh_id = loc.warehouse_id
        if wh_id not in sorting_by_wh:
            sorting_loc = await sort_loc_svc.get_or_create_sorting_location(
                session, tenant_id, wh_id
            )
            sorting_by_wh[wh_id] = sorting_loc.id
        await transfer_on_hand_between_locations(
            session,
            tenant_id,
            from_storage_location_id=bal.storage_location_id,
            to_storage_location_id=sorting_by_wh[wh_id],
            product_id=bal.product_id,
            quantity=qty,
        )
