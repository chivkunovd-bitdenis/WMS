from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import (
    MOVEMENT_TYPE_INBOUND_INTAKE,
    MOVEMENT_TYPE_OUTBOUND_SHIPMENT,
    MOVEMENT_TYPE_STOCK_TRANSFER_IN,
    MOVEMENT_TYPE_STOCK_TRANSFER_OUT,
    InventoryMovement,
)
from app.models.inventory_reservation import InventoryReservation
from app.models.outbound_shipment import OutboundShipmentLine, OutboundShipmentRequest
from app.models.product import Product
from app.models.storage_location import StorageLocation

OUTBOUND_RESERVE_STATUSES = ("draft", "submitted")
RESERVATION_ERROR = "insufficient_available"


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
    res = await session.execute(stmt)
    return {pid: int(s or 0) for pid, s in res.all()}


async def list_balances_total(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_product_owner_id: uuid.UUID | None = None,
) -> list[tuple[uuid.UUID, str, str, int, int]]:
    """Итоговые остатки по SKU (сумма по всем ячейкам).

    Возвращает: (product_id, sku_code, product_name, quantity_total, reserved_total)
    """
    stmt = (
        select(
            Product.id,
            Product.sku_code,
            Product.name,
            func.coalesce(func.sum(InventoryBalance.quantity), 0),
        )
        .join(InventoryBalance, InventoryBalance.product_id == Product.id)
        .where(
            Product.tenant_id == tenant_id,
            InventoryBalance.tenant_id == tenant_id,
        )
        .group_by(Product.id, Product.sku_code, Product.name)
        .order_by(Product.sku_code)
    )
    if seller_product_owner_id is not None:
        stmt = stmt.where(Product.seller_id == seller_product_owner_id)
    res = await session.execute(stmt)
    rows = [(pid, sku, name, int(q or 0)) for pid, sku, name, q in res.all()]
    if not rows:
        return []
    pids = [pid for pid, *_ in rows]
    rsv_map = await reserved_totals_by_product(session, tenant_id, pids)
    return [
        (pid, sku, name, qty, int(rsv_map.get(pid, 0)))
        for pid, sku, name, qty in rows
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
        and line.storage_location_id is not None
        and line.shipped_qty < line.quantity
    )
    if not should_hold:
        return

    sid = line.storage_location_id
    if sid is None:
        return
    desired = line.quantity - line.shipped_qty
    if desired < 1:
        return

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
        )
        session.add(bal)
    new_qty = bal.quantity + quantity_delta
    if new_qty < 0:
        msg = "insufficient stock"
        raise ValueError(msg)
    bal.quantity = new_qty
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
