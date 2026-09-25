"""FBS stock availability: batch math for WB publish and order reserve."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import case, func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FbsOrderProductReservation, FbsOrderReservation
from app.models.inventory_balance import InventoryBalance
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse
from app.services import stock_direction_service
from app.services.defect_warehouse_service import DEFECT_WAREHOUSE_CODE
from app.services.sorting_location_service import SORTING_LOCATION_CODE


def clamp_nonneg(value: int) -> int:
    return max(0, value)


async def fbs_reserved_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID | None,
    product_ids: list[uuid.UUID],
    *,
    exclude_fbs_order_ids: frozenset[uuid.UUID] | None = None,
) -> dict[uuid.UUID, int]:
    if not product_ids:
        return {}
    legacy_stmt = select(
        FbsOrderReservation.product_id.label("product_id"),
        FbsOrderReservation.quantity.label("quantity"),
    ).where(
        FbsOrderReservation.tenant_id == tenant_id,
        FbsOrderReservation.product_id.in_(product_ids),
    )
    if warehouse_id is not None:
        legacy_stmt = legacy_stmt.where(FbsOrderReservation.warehouse_id == warehouse_id)
    if exclude_fbs_order_ids:
        legacy_stmt = legacy_stmt.where(
            FbsOrderReservation.fbs_order_id.notin_(exclude_fbs_order_ids)
        )
    positions_stmt = select(
        FbsOrderProductReservation.product_id.label("product_id"),
        FbsOrderProductReservation.quantity.label("quantity"),
    ).where(
        FbsOrderProductReservation.tenant_id == tenant_id,
        FbsOrderProductReservation.product_id.in_(product_ids),
    )
    if warehouse_id is not None:
        positions_stmt = positions_stmt.where(
            FbsOrderProductReservation.warehouse_id == warehouse_id
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
        product_id: int(quantity) for product_id, quantity in (await session.execute(stmt)).all()
    }


async def fbs_allocated_available_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID | None,
    product_ids: list[uuid.UUID],
) -> dict[uuid.UUID, int]:
    """Compatibility for callers of the former physical FBS allocation.

    Operator caps only limit publication; they do not reserve physical stock.
    Existing order reservations are counted by fbs_reserved_by_product instead.
    Keep this entry point for catalog distribution consumers until their old
    allocation field is removed; no cap may be subtracted from availability.
    """
    return {}


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
    mp_map = await _mp_reserved_by_product(session, tenant_id, warehouse_id, product_ids)
    fbs_map = await fbs_reserved_by_product(
        session,
        tenant_id,
        warehouse_id,
        product_ids,
        exclude_fbs_order_ids=exclude_fbs_order_ids,
    )
    direction_map = (
        await stock_direction_service.direction_totals_by_product(session, tenant_id, product_ids)
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


# --- WMS-530: один расчёт «Остаток / Резерв / Доступно» на организацию -----
#
# Всё выше в этом файле считает по ОДНОМУ складу ФФ (нужно только для
# ремонта псевдоскладов WMS-516, см. physical_warehouse_repair_service).
# Каталог, панели распределения, окно «Остаток для FBS», публикация WB/Ozon,
# бронь заказов FBS, отгрузка на МП и старая «Отгрузка», инвентаризация и
# рабочий список FBS берут числа только отсюда (R1-R4): склад, зона, тара и
# признак рабочего склада на три числа не влияют.


@dataclass(frozen=True)
class OrganizationStockTotals:
    """Остаток, Резерв и Доступно одного товара для всей организации.

    on_hand (Остаток, R1) — сумма всех строк остатка товара у арендатора, на
    любых складах, зонах и таре, включая склад брака и старые псевдосклады
    «FBS WB …» (пока их не перенёс ремонт WMS-516). reserved (Резерв, R2) —
    все брони (отгрузки на МП, старая «Отгрузка», заказы FBS WB и Ozon),
    ручные направления и количество на складе брака (D2: брак физически лежит
    у ФФ и входит в Остаток, но не продаётся, поэтому входит и в Резерв).
    available (Доступно, R3) = on_hand - reserved и может быть отрицательным:
    экран показывает число как есть, а проверки и публикация берут
    ``available_for_checks`` (max(0, available), D3).
    """

    on_hand: int
    reserved: int
    available: int

    @property
    def available_for_checks(self) -> int:
        return max(0, self.available)


async def _organization_on_hand_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> dict[uuid.UUID, int]:
    """R1: сумма всех строк остатка товара, без единого фильтра по месту."""
    if not product_ids:
        return {}
    stmt = (
        select(
            InventoryBalance.product_id,
            func.coalesce(func.sum(InventoryBalance.quantity), 0),
        )
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id.in_(product_ids),
        )
        .group_by(InventoryBalance.product_id)
    )
    res = await session.execute(stmt)
    return {pid: int(qty or 0) for pid, qty in res.all()}


async def _defect_on_hand_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> dict[uuid.UUID, int]:
    """D2: брак уже в Остатке (склад брака физический), кладём его и в Резерв."""
    if not product_ids:
        return {}
    stmt = (
        select(
            InventoryBalance.product_id,
            func.coalesce(func.sum(InventoryBalance.quantity), 0),
        )
        .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
        .join(Warehouse, Warehouse.id == StorageLocation.warehouse_id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id.in_(product_ids),
            StorageLocation.tenant_id == tenant_id,
            Warehouse.tenant_id == tenant_id,
            func.lower(Warehouse.code) == DEFECT_WAREHOUSE_CODE.lower(),
        )
        .group_by(InventoryBalance.product_id)
    )
    res = await session.execute(stmt)
    return {pid: int(qty or 0) for pid, qty in res.all()}


async def organization_stock_totals_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_ids: list[uuid.UUID],
    *,
    exclude_fbs_order_ids: frozenset[uuid.UUID] | None = None,
    exclude_mp_unload_request_id: uuid.UUID | None = None,
    exclude_outbound_request_id: uuid.UUID | None = None,
) -> dict[uuid.UUID, OrganizationStockTotals]:
    """Единственный расчёт Остатка/Резерва/Доступно организации (WMS-530 R1-R3).

    Документ или заказ, который сам держит бронь, не должен вычитать её из
    своего же доступного (R4) — для этого передайте его в соответствующий
    ``exclude_*``: FBS-бронь этого заказа, бронь этой же заявки на отгрузку на
    МП или этой же строки старой «Отгрузки» (вся заявка сразу, чтобы другая её
    строка того же товара тоже не считалась чужой бронью).
    """
    if not product_ids:
        return {}
    from app.services.marketplace_unload_service import (
        _mp_reserved_by_product,
        _outbound_reserved_by_product,
    )

    on_hand_map = await _organization_on_hand_by_product(session, tenant_id, product_ids)
    outbound_map = await _outbound_reserved_by_product(
        session,
        tenant_id,
        None,
        product_ids,
        exclude_request_id=exclude_outbound_request_id,
    )
    mp_map = await _mp_reserved_by_product(
        session,
        tenant_id,
        None,
        product_ids,
        exclude_request_id=exclude_mp_unload_request_id,
    )
    fbs_map = await fbs_reserved_by_product(
        session,
        tenant_id,
        None,
        product_ids,
        exclude_fbs_order_ids=exclude_fbs_order_ids,
    )
    direction_map = await stock_direction_service.direction_totals_by_product(
        session, tenant_id, product_ids
    )
    defect_map = await _defect_on_hand_by_product(session, tenant_id, product_ids)

    result: dict[uuid.UUID, OrganizationStockTotals] = {}
    for pid in product_ids:
        on_hand = int(on_hand_map.get(pid, 0))
        directions = direction_map.get(pid)
        reserved = (
            int(outbound_map.get(pid, 0))
            + int(mp_map.get(pid, 0))
            + int(fbs_map.get(pid, 0))
            + (int(directions.total) if directions is not None else 0)
            + int(defect_map.get(pid, 0))
        )
        result[pid] = OrganizationStockTotals(
            on_hand=on_hand,
            reserved=reserved,
            available=on_hand - reserved,
        )
    return result
