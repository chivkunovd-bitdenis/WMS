"""FBS stock availability: batch math for WB publish and order reserve."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import case, func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FbsOrderProductReservation, FbsOrderReservation
from app.models.inventory_balance import InventoryBalance
from app.models.storage_location import StorageLocation
from app.services import stock_direction_service
from app.services.sorting_location_service import SORTING_LOCATION_CODE


def clamp_nonneg(value: int) -> int:
    return max(0, value)


async def fbs_reserved_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_ids: list[uuid.UUID],
    *,
    exclude_fbs_order_ids: frozenset[uuid.UUID] | None = None,
) -> dict[uuid.UUID, int]:
    if not product_ids:
        return {}
    legacy_stmt = (
        select(
            FbsOrderReservation.product_id.label("product_id"),
            FbsOrderReservation.quantity.label("quantity"),
        )
        .where(
            FbsOrderReservation.tenant_id == tenant_id,
            FbsOrderReservation.warehouse_id == warehouse_id,
            FbsOrderReservation.product_id.in_(product_ids),
        )
    )
    if exclude_fbs_order_ids:
        legacy_stmt = legacy_stmt.where(
            FbsOrderReservation.fbs_order_id.notin_(exclude_fbs_order_ids)
        )
    positions_stmt = (
        select(
            FbsOrderProductReservation.product_id.label("product_id"),
            FbsOrderProductReservation.quantity.label("quantity"),
        )
        .where(
            FbsOrderProductReservation.tenant_id == tenant_id,
            FbsOrderProductReservation.warehouse_id == warehouse_id,
            FbsOrderProductReservation.product_id.in_(product_ids),
        )
    )
    if exclude_fbs_order_ids:
        from app.models.fbs_order import FbsOrderProduct

        positions_stmt = positions_stmt.join(
            FbsOrderProduct,
            FbsOrderProduct.id == FbsOrderProductReservation.order_product_id,
        ).where(FbsOrderProduct.order_id.notin_(exclude_fbs_order_ids))
    combined = union_all(legacy_stmt, positions_stmt).subquery()
    stmt = select(
        combined.c.product_id,
        func.coalesce(func.sum(combined.c.quantity), 0),
    ).group_by(combined.c.product_id)
    return {
        product_id: int(quantity)
        for product_id, quantity in (await session.execute(stmt)).all()
    }


async def fbs_reserved_qty_for_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    exclude_order_id: uuid.UUID | None = None,
) -> int:
    exclude_ids = frozenset({exclude_order_id}) if exclude_order_id is not None else None
    reserved = await fbs_reserved_by_product(
        session,
        tenant_id,
        warehouse_id,
        [product_id],
        exclude_fbs_order_ids=exclude_ids,
    )
    return int(reserved.get(product_id, 0))


async def _storage_and_sorting_on_hand_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> dict[uuid.UUID, tuple[int, int]]:
    """product_id -> (storage_qty, sorting_qty)."""
    if not product_ids:
        return {}
    storage_qty = func.coalesce(
        func.sum(
            case(
                (
                    StorageLocation.code != SORTING_LOCATION_CODE,
                    InventoryBalance.quantity,
                ),
                else_=0,
            )
        ),
        0,
    )
    sorting_qty = func.coalesce(
        func.sum(
            case(
                (
                    StorageLocation.code == SORTING_LOCATION_CODE,
                    InventoryBalance.quantity,
                ),
                else_=0,
            )
        ),
        0,
    )
    stmt = (
        select(
            InventoryBalance.product_id,
            storage_qty,
            sorting_qty,
        )
        .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id.in_(product_ids),
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.warehouse_id == warehouse_id,
        )
        .group_by(InventoryBalance.product_id)
    )
    res = await session.execute(stmt)
    return {pid: (int(storage or 0), int(sorting or 0)) for pid, storage, sorting in res.all()}


@dataclass(frozen=True)
class FbsStockBreakdown:
    """Три числа вместо одного: сколько лежит, сколько занято, сколько свободно.

    Экран настройки доли показывает все три, потому что без «занято» непонятно,
    почему процент дал меньше, чем ожидалось от общего остатка. Числа приходят
    из одного расчёта, а не из двух похожих: иначе они однажды разойдутся.
    """

    on_hand: int
    reserved: int
    free: int


async def fbs_stock_breakdown_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_ids: list[uuid.UUID],
    *,
    exclude_fbs_order_ids: frozenset[uuid.UUID] | None = None,
    include_global_direction_reserve: bool = True,
) -> dict[uuid.UUID, FbsStockBreakdown]:
    """Фактический остаток и то, что уже занято, по каждому товару.

    Направления хранения — это резервы («двести штук под комплекты»), а не отдельный
    FBS-пул: галки «FBS» у них больше нет. Поэтому доступное под FBS считается от
    реального остатка на складе, из которого вычитается всё занятое — отгрузки на
    маркетплейс, именованные резервы и уже созданные брони под FBS-заказы.

    Раньше здесь стояло `directions.fbs - reserved`, то есть при отсутствии
    направления с галкой FBS доступным считался ноль. После снятия галки такое
    правило означало бы, что ни один заказ из WB никогда не сможет забронировать
    товар, — все они уходили бы в «нет остатка».
    """
    if not product_ids:
        return {}
    from app.services.marketplace_unload_service import (
        _mp_reserved_by_product,
        _outbound_reserved_by_product,
    )

    on_hand_map = await _storage_and_sorting_on_hand_by_product(
        session, tenant_id, warehouse_id, product_ids
    )
    outbound_map = await _outbound_reserved_by_product(
        session, tenant_id, warehouse_id, product_ids
    )
    # Отгрузка на маркетплейс (ФБО) держит товар в коробах под свою поставку.
    # Без этого слагаемого одна и та же штука одновременно уложена в короб и
    # предложена покупателю в ФБС — то есть продана дважды. Описание функции
    # обещало этот вычет с самого начала, а кода не было.
    mp_map = await _mp_reserved_by_product(
        session, tenant_id, warehouse_id, product_ids
    )
    fbs_map = await fbs_reserved_by_product(
        session,
        tenant_id,
        warehouse_id,
        product_ids,
        exclude_fbs_order_ids=exclude_fbs_order_ids,
    )
    direction_map = (
        await stock_direction_service.direction_totals_by_product(
            session, tenant_id, product_ids
        )
        if include_global_direction_reserve
        else {}
    )
    result: dict[uuid.UUID, FbsStockBreakdown] = {}
    for pid in product_ids:
        storage, sorting = on_hand_map.get(pid, (0, 0))
        directions = direction_map.get(pid)
        reserved_by_directions = int(directions.total) if directions is not None else 0
        on_hand = storage + sorting
        reserved = (
            int(outbound_map.get(pid, 0))
            + int(mp_map.get(pid, 0))
            + reserved_by_directions
            + int(fbs_map.get(pid, 0))
        )
        result[pid] = FbsStockBreakdown(
            on_hand=on_hand,
            reserved=reserved,
            free=clamp_nonneg(on_hand - reserved),
        )
    return result


async def fbs_available_qty_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_ids: list[uuid.UUID],
    *,
    exclude_fbs_order_ids: frozenset[uuid.UUID] | None = None,
) -> dict[uuid.UUID, int]:
    """Только свободное количество — тонкая обёртка над разложением на три числа."""
    breakdown = await fbs_stock_breakdown_by_product(
        session,
        tenant_id,
        warehouse_id,
        product_ids,
        exclude_fbs_order_ids=exclude_fbs_order_ids,
    )
    return {pid: row.free for pid, row in breakdown.items()}


async def fbs_available_qty_for_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    exclude_fbs_order_id: uuid.UUID | None = None,
) -> int:
    exclude_ids = frozenset({exclude_fbs_order_id}) if exclude_fbs_order_id is not None else None
    result = await fbs_available_qty_by_product(
        session,
        tenant_id,
        warehouse_id,
        [product_id],
        exclude_fbs_order_ids=exclude_ids,
    )
    return int(result.get(product_id, 0))
