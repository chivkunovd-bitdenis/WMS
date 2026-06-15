from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import and_, case, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import (
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
from app.services.sorting_location_service import SORTING_LOCATION_CODE

OUTBOUND_RESERVE_STATUSES = ("draft", "submitted")
MP_UNLOAD_RESERVE_STATUSES = ("submitted", "confirmed")
RESERVATION_ERROR = "insufficient_available"
DeductPrefer = Literal["packed", "unpacked"]


def _sync_balance_quantity(bal: InventoryBalance) -> None:
    bal.quantity = int(bal.quantity_unpacked) + int(bal.quantity_packed)


def _deduct_from_buckets(bal: InventoryBalance, qty: int, *, prefer: DeductPrefer) -> None:
    if prefer == "unpacked":
        from_unpacked = min(int(bal.quantity_unpacked), qty)
        from_packed = qty - from_unpacked
    else:
        from_packed = min(int(bal.quantity_packed), qty)
        from_unpacked = qty - from_packed
    if from_unpacked > int(bal.quantity_unpacked) or from_packed > int(bal.quantity_packed):
        msg = "insufficient stock"
        raise ValueError(msg)
    bal.quantity_unpacked = int(bal.quantity_unpacked) - from_unpacked
    bal.quantity_packed = int(bal.quantity_packed) - from_packed
    _sync_balance_quantity(bal)


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
    rsv = await total_reserved_at_location(
        session, tenant_id, product_id, storage_location_id
    )
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
        stmt = (
            stmt.outerjoin(
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
            MarketplaceUnloadLine.id
            == MarketplaceUnloadReservation.marketplace_unload_line_id,
        )
        .join(
            MarketplaceUnloadRequest,
            MarketplaceUnloadRequest.id == MarketplaceUnloadLine.request_id,
        )
        .where(
            MarketplaceUnloadReservation.tenant_id == tenant_id,
            MarketplaceUnloadReservation.product_id.in_(product_ids),
            MarketplaceUnloadRequest.status.in_(MP_UNLOAD_RESERVE_STATUSES),
        )
        .group_by(MarketplaceUnloadReservation.product_id)
    )
    if warehouse_id is not None:
        mp_stmt = mp_stmt.where(MarketplaceUnloadReservation.warehouse_id == warehouse_id)
    mp_res = await session.execute(mp_stmt)
    mp_map = {pid: int(s or 0) for pid, s in mp_res.all()}

    return {
        pid: int(outbound_map.get(pid, 0)) + int(mp_map.get(pid, 0)) for pid in product_ids
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
    rsv_map = await reserved_totals_by_product(
        session, tenant_id, pids, warehouse_id=warehouse_id
    )
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
    on_hand = await _physical_on_hand(
        session, tenant_id, product_id, storage_location_id
    )
    reserved = await total_reserved_at_location(
        session, tenant_id, product_id, storage_location_id
    )
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

    should_hold = (
        request.status in OUTBOUND_RESERVE_STATUSES
        and line.shipped_qty < line.quantity
    )
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
    on_hand_wh = await storage_on_hand_in_warehouse(
        session, tenant_id, wh_id, line.product_id
    )
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
) -> None:
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
        storage_location_id=storage_location_id,
        quantity_delta=quantity_delta,
        movement_type=movement_type,
        inbound_intake_line_id=inbound_intake_line_id,
        outbound_shipment_line_id=outbound_shipment_line_id,
        transfer_group_id=transfer_group_id,
        marketplace_unload_request_id=marketplace_unload_request_id,
    )
    session.add(movement)

    stmt = select(InventoryBalance).where(
        InventoryBalance.tenant_id == tenant_id,
        InventoryBalance.product_id == product_id,
        InventoryBalance.storage_location_id == storage_location_id,
    )
    res = await session.execute(stmt)
    bal = res.scalar_one_or_none()
    if bal is None:
        if quantity_delta < 0:
            msg = "insufficient stock"
            raise ValueError(msg)
        bal = InventoryBalance(
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=storage_location_id,
            quantity=0,
            quantity_unpacked=0,
            quantity_packed=0,
        )
        session.add(bal)
    if quantity_delta > 0:
        bal.quantity_unpacked = int(bal.quantity_unpacked) + quantity_delta
        _sync_balance_quantity(bal)
    else:
        _deduct_from_buckets(bal, -quantity_delta, prefer=deduct_prefer)
    if bal.quantity < 0:
        msg = "insufficient stock"
        raise ValueError(msg)
    bal.updated_at = datetime.now(UTC)


async def apply_packaging_convert(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    quantity: int,
) -> None:
    """Перевод qty из не упаковано в упаковано в том же месте."""
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
    stmt = select(InventoryBalance).where(
        InventoryBalance.tenant_id == tenant_id,
        InventoryBalance.product_id == product_id,
        InventoryBalance.storage_location_id == storage_location_id,
    )
    bal = (await session.execute(stmt)).scalar_one_or_none()
    if bal is None or int(bal.quantity_unpacked) < quantity:
        msg = "insufficient_unpacked"
        raise ValueError(msg)
    bal.quantity_unpacked = int(bal.quantity_unpacked) - quantity
    bal.quantity_packed = int(bal.quantity_packed) + quantity
    _sync_balance_quantity(bal)
    bal.updated_at = datetime.now(UTC)


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
