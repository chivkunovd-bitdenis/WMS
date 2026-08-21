"""FBS stock availability: batch math for WB publish and order reserve."""

from __future__ import annotations

import uuid
from collections.abc import Collection

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FbsOrderReservation
from app.models.inventory_balance import InventoryBalance
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse
from app.services import stock_direction_service
from app.services.sorting_location_service import SORTING_LOCATION_CODE


def clamp_nonneg(value: int) -> int:
    return max(0, value)


async def tenant_warehouse_ids(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> list[uuid.UUID]:
    """Все склады тенанта.

    I10 (21.08.2026): у большинства клиентов физически одна площадка, а строк
    `warehouses` в базе несколько — «основной» плюс автосозданные под каждый
    склад WB (см. `AUTO_FBS_WAREHOUSE_CODE_PREFIX` в
    `fbs_warehouse_binding_service.py`). Раньше остаток и резерв под FBS
    считались строго по одному складу, к которому исторически привязан
    конкретный заказ, — из-за этого подбор и упаковка не видели товар, если
    приёмка положила его не в ту ячейку того же тенанта (поставка на 155
    заказов встала 20.08 именно так). Теперь считаем по всем складам тенанта
    сразу.
    """
    stmt = select(Warehouse.id).where(Warehouse.tenant_id == tenant_id)
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def fbs_reserved_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_ids: list[uuid.UUID],
    *,
    exclude_fbs_order_ids: frozenset[uuid.UUID] | None = None,
    warehouse_ids: Collection[uuid.UUID] | None = None,
) -> dict[uuid.UUID, int]:
    if not product_ids:
        return {}
    ids = list(warehouse_ids) if warehouse_ids is not None else [warehouse_id]
    stmt = (
        select(
            FbsOrderReservation.product_id,
            func.coalesce(func.sum(FbsOrderReservation.quantity), 0),
        )
        .where(
            FbsOrderReservation.tenant_id == tenant_id,
            FbsOrderReservation.warehouse_id.in_(ids),
            FbsOrderReservation.product_id.in_(product_ids),
        )
        .group_by(FbsOrderReservation.product_id)
    )
    if exclude_fbs_order_ids:
        stmt = stmt.where(FbsOrderReservation.fbs_order_id.notin_(exclude_fbs_order_ids))
    res = await session.execute(stmt)
    return {pid: int(qty) for pid, qty in res.all()}


async def fbs_reserved_qty_for_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    exclude_order_id: uuid.UUID | None = None,
) -> int:
    exclude_ids = (
        frozenset({exclude_order_id}) if exclude_order_id is not None else None
    )
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
    *,
    warehouse_ids: Collection[uuid.UUID] | None = None,
) -> dict[uuid.UUID, tuple[int, int]]:
    """product_id -> (storage_qty, sorting_qty), просуммировано по складу(ам).

    По умолчанию — один `warehouse_id`. `warehouse_ids` суммирует несколько
    складов сразу (I10).
    """
    if not product_ids:
        return {}
    ids = list(warehouse_ids) if warehouse_ids is not None else [warehouse_id]
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
            StorageLocation.warehouse_id.in_(ids),
        )
        .group_by(InventoryBalance.product_id)
    )
    res = await session.execute(stmt)
    return {
        pid: (int(storage or 0), int(sorting or 0)) for pid, storage, sorting in res.all()
    }


async def fbs_available_qty_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_ids: list[uuid.UUID],
    *,
    exclude_fbs_order_ids: frozenset[uuid.UUID] | None = None,
) -> dict[uuid.UUID, int]:
    """Фактический остаток минус то, что уже занято.

    Направления хранения — это резервы («двести штук под комплекты»), а не отдельный
    FBS-пул: галки «FBS» у них больше нет. Поэтому доступное под FBS считается от
    реального остатка на складе, из которого вычитается всё занятое — отгрузки на
    маркетплейс, именованные резервы и уже созданные брони под FBS-заказы.

    Раньше здесь стояло `directions.fbs - reserved`, то есть при отсутствии
    направления с галкой FBS доступным считался ноль. После снятия галки такое
    правило означало бы, что ни один заказ из WB никогда не сможет забронировать
    товар, — все они уходили бы в «нет остатка».

    I10 (21.08.2026): считаем не по одному `warehouse_id`, а сразу по всем
    складам тенанта — клиент физически работает как с одним складом, и товар,
    который приёмка положила не туда, всё равно должен быть виден и подбору,
    и упаковке, и предсоздании поставки. `warehouse_id` остаётся в сигнатуре
    ради обратной совместимости вызовов — просто гарантированно входит в
    просуммированный набор.
    """
    if not product_ids:
        return {}
    from app.services.marketplace_unload_service import _outbound_reserved_by_product

    ids = set(await tenant_warehouse_ids(session, tenant_id))
    ids.add(warehouse_id)

    on_hand_map = await _storage_and_sorting_on_hand_by_product(
        session, tenant_id, warehouse_id, product_ids, warehouse_ids=ids
    )
    outbound_map = await _outbound_reserved_by_product(
        session, tenant_id, warehouse_id, product_ids, warehouse_ids=ids
    )
    fbs_map = await fbs_reserved_by_product(
        session,
        tenant_id,
        warehouse_id,
        product_ids,
        exclude_fbs_order_ids=exclude_fbs_order_ids,
        warehouse_ids=ids,
    )
    direction_map = await stock_direction_service.direction_totals_by_product(
        session, tenant_id, product_ids
    )
    result: dict[uuid.UUID, int] = {}
    for pid in product_ids:
        storage, sorting = on_hand_map.get(pid, (0, 0))
        directions = direction_map.get(pid)
        reserved_by_directions = int(directions.total) if directions is not None else 0
        result[pid] = clamp_nonneg(
            storage
            + sorting
            - int(outbound_map.get(pid, 0))
            - reserved_by_directions
            - int(fbs_map.get(pid, 0))
        )
    return result


async def fbs_available_qty_for_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    exclude_fbs_order_id: uuid.UUID | None = None,
) -> int:
    exclude_ids = (
        frozenset({exclude_fbs_order_id}) if exclude_fbs_order_id is not None else None
    )
    result = await fbs_available_qty_by_product(
        session,
        tenant_id,
        warehouse_id,
        [product_id],
        exclude_fbs_order_ids=exclude_ids,
    )
    return int(result.get(product_id, 0))


async def fbs_stock_by_warehouse_for_products(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> dict[uuid.UUID, dict[uuid.UUID, int]]:
    """product_id -> {warehouse_id: остаток (хранение + сортировка)}, только > 0.

    I10: нужна не сумма, а разбивка по складам — чтобы на создании поставки
    сказать оператору словами «товара нет на складе заказа, зато N шт. лежит
    на складе Y», а не просто пропустить проверку молча.
    """
    if not product_ids:
        return {}
    stmt = (
        select(
            InventoryBalance.product_id,
            StorageLocation.warehouse_id,
            func.coalesce(func.sum(InventoryBalance.quantity), 0),
        )
        .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id.in_(product_ids),
            StorageLocation.tenant_id == tenant_id,
        )
        .group_by(InventoryBalance.product_id, StorageLocation.warehouse_id)
    )
    res = await session.execute(stmt)
    out: dict[uuid.UUID, dict[uuid.UUID, int]] = {}
    for product_id, warehouse_id, qty in res.all():
        qty_int = int(qty or 0)
        if qty_int <= 0:
            continue
        out.setdefault(product_id, {})[warehouse_id] = qty_int
    return out
