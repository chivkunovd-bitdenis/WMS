"""FBS supply ↔ packaging task integration."""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_order import (
    FBS_ORDER_STATUS_ASSEMBLING,
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_IN_SUPPLY,
    FBS_ORDER_STATUS_PACKED,
    META_STATUS_ACCEPTED,
    META_STATUS_ALLOWED_WITHOUT_CHECK,
    META_STATUS_PENDING,
    META_STATUS_REJECTED,
    META_STATUS_REPLACEMENT_REQUIRED,
    PACK_STATUS_PACKED,
    PICK_STATUS_PICKED,
    FbsOrder,
    current_order_marking,
)
from app.models.fbs_order_pick import FbsOrderPick
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_DRAFT,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.fbs_trbx import FbsTrbx
from app.models.inventory_balance import InventoryBalance
from app.models.packaging_task import STATUS_DRAFT, PackagingTask, PackagingTaskLine
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.models.warehouse_box import WarehouseBox
from app.services import inventory_service as inv_svc
from app.services import sorting_location_service as sorting_loc_svc
from app.services.document_number_service import (
    DOC_TYPE_PACKAGING,
    assign_display_number_if_missing,
    assign_document_number_if_missing,
)
from app.services.packaging_task_service import get_task, is_task_complete, qty_done

logger = logging.getLogger(__name__)

_VALID_SUPPLY_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    FBS_SUPPLY_STATUS_DRAFT: frozenset({FBS_SUPPLY_STATUS_ASSEMBLING}),
    FBS_SUPPLY_STATUS_ASSEMBLING: frozenset(),
    FBS_SUPPLY_STATUS_PACKED: frozenset(),
}


class FbsPackagingIntegrationError(Exception):
    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        self.message = message
        super().__init__(code)


@dataclass(frozen=True)
class FbsPackUnitResult:
    fulfillment: FbsPackagingFulfillment
    order: FbsOrder


@dataclass(frozen=True)
class FbsPackProgressResult:
    units: list[FbsPackUnitResult]
    # Предупреждения оператору: упаковка больше не падает из-за остатка, но нельзя
    # молчать, когда списали не из той ячейки или не списали вовсе.
    warnings: list[str] = field(default_factory=list)


async def _load_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    with_orders: bool = False,
    with_trbxes: bool = False,
    for_update: bool = False,
) -> FbsSupply | None:
    stmt = select(FbsSupply).where(
        FbsSupply.id == supply_id,
        FbsSupply.tenant_id == tenant_id,
    )
    if with_orders:
        stmt = stmt.options(
            selectinload(FbsSupply.orders).selectinload(FbsOrder.product),
            selectinload(FbsSupply.orders).selectinload(FbsOrder.markings),
        )
    if with_trbxes:
        stmt = stmt.options(selectinload(FbsSupply.trbxes))
    if for_update:
        stmt = stmt.with_for_update()
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _order_marking_blocks_promotion(order: FbsOrder) -> bool:
    if order.status == FBS_ORDER_STATUS_CANCELLED:
        return False
    required = list(order.required_meta_json or [])
    if not required:
        return False
    ok_statuses = {
        META_STATUS_ACCEPTED,
        META_STATUS_ALLOWED_WITHOUT_CHECK,
        META_STATUS_PENDING,
    }
    for kind in required:
        mark = current_order_marking(list(order.markings), kind)
        if mark is None:
            return True
        if mark.meta_status in {
            META_STATUS_REJECTED,
            META_STATUS_REPLACEMENT_REQUIRED,
        }:
            return True
        if mark.meta_status not in ok_statuses:
            return True
    return False


def _supply_requires_marking(supply: FbsSupply) -> bool:
    return any(_order_marking_blocks_promotion(order) for order in supply.orders)


async def _decrement_packaging_line_for_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
    product_id: uuid.UUID,
) -> None:
    if supply.packaging_task_id is None:
        return
    task = await get_task(session, tenant_id, supply.packaging_task_id)
    if task is None:
        return
    for line in list(task.lines):
        if line.product_id != product_id:
            continue
        new_total = int(line.qty_total) - 1
        if new_total <= 0:
            if qty_done(line) <= 0:
                await session.delete(line)
            else:
                line.qty_total = qty_done(line)
        else:
            line.qty_total = new_total
        break


async def detach_cancelled_order_from_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order: FbsOrder,
) -> FbsSupply | None:
    """Remove cancelled order from FBS supply and fix packaging task totals."""
    if order.supply_id is None:
        return None

    supply = await _load_supply(
        session,
        tenant_id,
        order.supply_id,
        with_orders=True,
        for_update=True,
    )
    if supply is None:
        order.supply_id = None
        order.trbx_id = None
        return None

    if order.product_id is not None:
        await _decrement_packaging_line_for_product(
            session, tenant_id, supply, order.product_id
        )

    order.supply_id = None
    order.trbx_id = None
    await session.flush()

    active_orders = sum(
        1
        for row in supply.orders
        if row.id != order.id and row.status != FBS_ORDER_STATUS_CANCELLED
    )
    if active_orders == 0:
        supply.status = FBS_SUPPLY_STATUS_DRAFT
        await session.flush()
        return supply

    if supply.status == FBS_SUPPLY_STATUS_PACKED:
        supply.status = FBS_SUPPLY_STATUS_ASSEMBLING
        for row in supply.orders:
            if row.id != order.id and row.status == FBS_ORDER_STATUS_PACKED:
                row.status = FBS_ORDER_STATUS_ASSEMBLING
        await session.flush()
        return supply

    if supply.status == FBS_SUPPLY_STATUS_ASSEMBLING:
        return await try_promote_fbs_supply_if_ready(session, tenant_id, supply.id)
    return supply


async def create_packaging_task_for_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> PackagingTask:
    supply = await _load_supply(
        session,
        tenant_id,
        supply_id,
        with_orders=True,
        for_update=True,
    )
    if supply is None:
        raise FbsPackagingIntegrationError("supply_not_found")

    if supply.packaging_task_id is not None:
        existing = await get_task(session, tenant_id, supply.packaging_task_id)
        if existing is not None:
            return existing

    task = PackagingTask(
        tenant_id=tenant_id,
        warehouse_id=supply.warehouse_id,
        status=STATUS_DRAFT,
    )
    session.add(task)
    await session.flush()
    await assign_document_number_if_missing(
        session, tenant_id, DOC_TYPE_PACKAGING, task
    )
    await assign_display_number_if_missing(
        session, tenant_id, DOC_TYPE_PACKAGING, task
    )

    qty_by_product: dict[uuid.UUID, int] = defaultdict(int)
    for order in supply.orders:
        if order.product_id is None:
            logger.warning(
                "fbs packaging: order %s in supply %s has no mapped product",
                order.id,
                supply.id,
            )
            continue
        qty_by_product[order.product_id] += 1

    sorting_loc = await sorting_loc_svc.get_or_create_sorting_location(
        session, tenant_id, supply.warehouse_id
    )
    for product_id, qty in sorted(qty_by_product.items(), key=lambda item: str(item[0])):
        session.add(
            PackagingTaskLine(
                task_id=task.id,
                product_id=product_id,
                storage_location_id=sorting_loc.id,
                qty_total=qty,
                qty_suggested_packed=0,
            )
        )

    supply.packaging_task_id = task.id
    await session.flush()
    loaded = await get_task(session, tenant_id, task.id)
    assert loaded is not None
    return loaded


async def update_supply_status(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    new_status: str,
) -> FbsSupply:
    supply = await _load_supply(
        session,
        tenant_id,
        supply_id,
        with_orders=True,
        for_update=True,
    )
    if supply is None:
        raise FbsPackagingIntegrationError("supply_not_found")

    if new_status == supply.status:
        return supply

    allowed = _VALID_SUPPLY_STATUS_TRANSITIONS.get(supply.status, frozenset())
    if new_status not in allowed:
        raise FbsPackagingIntegrationError("invalid_status_transition")

    supply.status = new_status
    if new_status == FBS_SUPPLY_STATUS_ASSEMBLING:
        await create_packaging_task_for_supply(session, tenant_id, supply_id)
        for order in supply.orders:
            if order.status == FBS_ORDER_STATUS_IN_SUPPLY:
                order.status = FBS_ORDER_STATUS_ASSEMBLING

    await session.flush()
    return supply


async def get_supply_for_packaging_task(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    packaging_task_id: uuid.UUID,
    *,
    with_orders: bool = False,
) -> FbsSupply | None:
    return await _load_supply_by_packaging_task(
        session,
        tenant_id,
        packaging_task_id,
        with_orders=with_orders,
    )


async def _order_has_active_fulfillment(
    session: AsyncSession,
    order_id: uuid.UUID,
) -> bool:
    fulfillment_id = await session.scalar(
        select(FbsPackagingFulfillment.id)
        .where(
            FbsPackagingFulfillment.fbs_order_id == order_id,
            FbsPackagingFulfillment.undone_at.is_(None),
        )
        .limit(1)
    )
    return fulfillment_id is not None


async def _order_has_active_pick(
    session: AsyncSession,
    order_id: uuid.UUID,
) -> bool:
    pick_id = await session.scalar(
        select(FbsOrderPick.id)
        .where(
            FbsOrderPick.fbs_order_id == order_id,
            FbsOrderPick.undone_at.is_(None),
        )
        .limit(1)
    )
    return pick_id is not None


async def _eligible_orders_for_product(
    session: AsyncSession,
    supply: FbsSupply,
    product_id: uuid.UUID,
    *,
    require_pick: bool = True,
) -> list[FbsOrder]:
    supply_order_ids = {order.id for order in supply.orders}
    fulfilled_ids = set(
        (
            await session.execute(
                select(FbsPackagingFulfillment.fbs_order_id).where(
                    FbsPackagingFulfillment.fbs_order_id.in_(supply_order_ids),
                    FbsPackagingFulfillment.undone_at.is_(None),
                )
            )
        ).scalars()
    )
    eligible: list[FbsOrder] = []
    for order in supply.orders:
        if order.status == FBS_ORDER_STATUS_CANCELLED:
            continue
        if order.product_id != product_id:
            continue
        if order.id in fulfilled_ids:
            continue
        if require_pick:
            if order.pick_status != PICK_STATUS_PICKED:
                continue
            if not await _order_has_active_pick(session, order.id):
                continue
        eligible.append(order)
    eligible.sort(
        key=lambda row: (
            row.deadline_at or datetime.max.replace(tzinfo=UTC),
            row.created_at_wb,
            row.wb_order_id,
        )
    )
    return eligible


def _unpicked_orders_for_product(
    supply: FbsSupply,
    product_id: uuid.UUID,
) -> list[FbsOrder]:
    return [
        order
        for order in supply.orders
        if order.status != FBS_ORDER_STATUS_CANCELLED
        and order.product_id == product_id
        and order.pick_status != PICK_STATUS_PICKED
    ]


async def _resolve_order_for_pack_unit(
    session: AsyncSession,
    supply: FbsSupply,
    product_id: uuid.UUID,
    *,
    explicit_order_id: uuid.UUID | None,
) -> FbsOrder:
    if explicit_order_id is not None:
        order = next((row for row in supply.orders if row.id == explicit_order_id), None)
        if order is None:
            raise FbsPackagingIntegrationError("order_not_in_supply")
        if order.product_id != product_id:
            raise FbsPackagingIntegrationError("order_product_mismatch")
        if order.pick_status != PICK_STATUS_PICKED:
            raise FbsPackagingIntegrationError("order_not_picked")
        if not await _order_has_active_pick(session, order.id):
            raise FbsPackagingIntegrationError("order_not_picked")
        if await _order_has_active_fulfillment(session, order.id):
            raise FbsPackagingIntegrationError("order_already_packed")
        return order

    eligible = await _eligible_orders_for_product(session, supply, product_id)
    if not eligible:
        if _unpicked_orders_for_product(supply, product_id):
            raise FbsPackagingIntegrationError("order_not_picked")
        raise FbsPackagingIntegrationError("no_eligible_order")
    return eligible[0]


async def _insufficient_stock_message(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    line: PackagingTaskLine,
) -> str:
    """Собрать понятный текст: чего не хватает и где оператор смотрел."""
    product = await session.get(Product, line.product_id)
    loc = await session.get(StorageLocation, line.storage_location_id)
    product_label = (
        f"«{product.name}» (арт. {product.sku_code})" if product is not None else "товара"
    )
    if loc is not None and sorting_loc_svc.is_sorting_location(loc):
        location_label = f"ячейке сортировки склада (код {loc.barcode})"
    elif loc is not None:
        location_label = f"ячейке «{loc.code}»"
    else:
        location_label = "указанной ячейке"
    on_hand = await session.scalar(
        select(InventoryBalance.quantity).where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id == line.product_id,
            InventoryBalance.storage_location_id == line.storage_location_id,
        )
    )
    on_hand_int = int(on_hand or 0)
    return (
        f"Недостаточно {product_label} в {location_label}: по остатку числится "
        f"{on_hand_int} шт., а нужна как минимум 1. Проверьте фактическое наличие "
        "товара на складе — возможно, он лежит в другой ячейке или ещё не подобран."
    )


async def _try_deduct_from_alternative_sorting_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    primary_location_id: uuid.UUID,
) -> tuple[bool, str | None]:
    """
    Попытаться списать товар из другой ячейки сортировки этого же тенанта.

    Возвращает (успешно, название_ячейки_если_успешно).
    """
    # Получить склад первичной ячейки
    primary_loc = await session.get(StorageLocation, primary_location_id)
    if primary_loc is None:
        return False, None

    # Ячейки сортировки других складов этого же тенанта, где остаток товара больше нуля
    sorting_locs = await session.execute(
        select(
            StorageLocation.id,
            StorageLocation.barcode,
            InventoryBalance.quantity,
        )
        .join(
            InventoryBalance,
            InventoryBalance.storage_location_id == StorageLocation.id,
        )
        .where(
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.warehouse_id != primary_loc.warehouse_id,
            StorageLocation.code == sorting_loc_svc.SORTING_LOCATION_CODE,
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id == product_id,
            InventoryBalance.quantity > 0,
        )
        .order_by(InventoryBalance.quantity.desc())
    )

    for alt_loc_id, alt_barcode, _ in sorting_locs.all():
        # Попробовать списать из найденной ячейки
        try:
            await inv_svc.apply_packaging_convert(
                session,
                tenant_id=tenant_id,
                product_id=product_id,
                storage_location_id=alt_loc_id,
                quantity=1,
                require_unpacked=False,
            )
            return True, f"{alt_barcode}"
        except ValueError as exc:
            # Если оттуда тоже не вышло (может быть race condition), пробуем следующую
            if str(exc) != "insufficient_stock":
                raise
            continue

    return False, None


async def record_fbs_pack_progress(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    task: PackagingTask,
    line: PackagingTaskLine,
    qty: int,
    *,
    order_id: uuid.UUID | None = None,
    acting_user_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
) -> FbsPackProgressResult:
    """Link each packed unit to one picked FBS order and convert sorting stock."""
    if qty < 1:
        raise FbsPackagingIntegrationError("invalid_qty")
    if order_id is not None and qty > 1:
        raise FbsPackagingIntegrationError("invalid_qty")

    supply = await _load_supply_by_packaging_task(
        session,
        tenant_id,
        task.id,
        with_orders=True,
        for_update=True,
    )
    if supply is None:
        raise FbsPackagingIntegrationError("supply_not_found")

    units: list[FbsPackUnitResult] = []
    warnings: list[str] = []
    base_key = idempotency_key or str(uuid.uuid4())
    for index in range(qty):
        unit_key = base_key if qty == 1 else f"{base_key}:{index}"
        existing = await session.scalar(
            select(FbsPackagingFulfillment)
            .where(
                FbsPackagingFulfillment.packaging_task_id == task.id,
                FbsPackagingFulfillment.pack_idempotency_key == unit_key,
            )
            .options(selectinload(FbsPackagingFulfillment.order))
        )
        if existing is not None:
            units.append(FbsPackUnitResult(existing, existing.order))
            continue

        target_order = await _resolve_order_for_pack_unit(
            session,
            supply,
            line.product_id,
            explicit_order_id=order_id if index == 0 else None,
        )

        # Попробовать списать из основной ячейки
        try:
            await inv_svc.apply_packaging_convert(
                session,
                tenant_id=tenant_id,
                product_id=line.product_id,
                storage_location_id=line.storage_location_id,
                quantity=1,
                # Упаковке всё равно, числится товар «упакованным» или «неупакованным» —
                # важен только общий остаток в ячейке. Деление между статусами остаётся
                # учётной операцией и переносит столько, сколько реально есть в
                # «не упаковано»; оно больше не блокирует упаковку.
                require_unpacked=False,
            )
        except ValueError as exc:
            if str(exc) == "insufficient_stock":
                # Попробовать найти и списать из другой ячейки сортировки тенанта
                success, alt_location_code = await _try_deduct_from_alternative_sorting_location(
                    session,
                    tenant_id,
                    line.product_id,
                    line.storage_location_id,
                )
                if success:
                    warnings.append(
                        f"Товар списан из другой ячейки сортировки: {alt_location_code}"
                    )
                    # Остаток одного склада уменьшился, чтобы закрыть недостачу на
                    # другом, физического перемещения не было. Без записи в журнал это
                    # расхождение потом нечем объяснить: тост оператор увидит один раз.
                    logger.warning(
                        "fbs packing cross-location deduction: tenant=%s product=%s "
                        "line_location=%s alt_location=%s order=%s",
                        tenant_id,
                        line.product_id,
                        line.storage_location_id,
                        alt_location_code,
                        target_order.id,
                    )
                else:
                    # Товара нет нигде, но упаковка продолжается
                    insufficient_msg = await _insufficient_stock_message(
                        session, tenant_id, line
                    )
                    warnings.append(
                        "Упаковка продолжена, остаток не списан. " + insufficient_msg
                    )
                    # След в журнале: без него расхождение остатка потом не объяснить.
                    logger.warning(
                        "fbs packing without stock: tenant=%s product=%s location=%s order=%s",
                        tenant_id,
                        line.product_id,
                        line.storage_location_id,
                        target_order.id,
                    )
            else:
                raise

        now = datetime.now(UTC)
        fulfillment = FbsPackagingFulfillment(
            tenant_id=tenant_id,
            fbs_order_id=target_order.id,
            packaging_task_id=task.id,
            packaging_task_line_id=line.id,
            fulfilled_by_user_id=acting_user_id,
            fulfilled_at=now,
            pack_idempotency_key=unit_key,
        )
        session.add(fulfillment)
        target_order.pack_status = PACK_STATUS_PACKED
        target_order.packed_at = now
        line.qty_packed_in_task = int(line.qty_packed_in_task) + 1
        units.append(FbsPackUnitResult(fulfillment, target_order))

    await session.flush()
    return FbsPackProgressResult(units=units, warnings=warnings)


async def _all_active_orders_fulfilled(
    session: AsyncSession,
    supply: FbsSupply,
) -> bool:
    for order in supply.orders:
        if order.status == FBS_ORDER_STATUS_CANCELLED:
            continue
        if order.product_id is None:
            return False
        if not await _order_has_active_fulfillment(session, order.id):
            return False
    return True


async def try_promote_fbs_supply_if_ready(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> FbsSupply | None:
    supply = await _load_supply(
        session,
        tenant_id,
        supply_id,
        with_orders=True,
        for_update=True,
    )
    if supply is None or supply.status != FBS_SUPPLY_STATUS_ASSEMBLING:
        return supply

    task = None
    if supply.packaging_task_id is not None:
        task = await get_task(session, tenant_id, supply.packaging_task_id)
        if task is None or not is_task_complete(task):
            return supply

    if not await _all_active_orders_fulfilled(session, supply):
        return supply

    if _supply_requires_marking(supply):
        return supply

    supply.status = FBS_SUPPLY_STATUS_PACKED
    for order in supply.orders:
        if order.status == FBS_ORDER_STATUS_CANCELLED:
            continue
        if await _order_has_active_fulfillment(session, order.id):
            order.status = FBS_ORDER_STATUS_PACKED
    await session.flush()
    return supply


async def sync_fbs_supply_on_packaging_done(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    packaging_task_id: uuid.UUID,
) -> FbsSupply | None:
    supply = await _load_supply_by_packaging_task(
        session, tenant_id, packaging_task_id, with_orders=True
    )
    if supply is None:
        return None
    return await try_promote_fbs_supply_if_ready(session, tenant_id, supply.id)


async def sync_fbs_supply_after_order_marking_update(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
) -> FbsSupply | None:
    order = await session.get(FbsOrder, order_id)
    if order is None or order.tenant_id != tenant_id or order.supply_id is None:
        return None
    return await try_promote_fbs_supply_if_ready(session, tenant_id, order.supply_id)


async def _load_supply_by_packaging_task(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    packaging_task_id: uuid.UUID,
    *,
    with_orders: bool = False,
    for_update: bool = False,
) -> FbsSupply | None:
    stmt = select(FbsSupply).where(
        FbsSupply.tenant_id == tenant_id,
        FbsSupply.packaging_task_id == packaging_task_id,
    )
    if with_orders:
        stmt = stmt.options(
            selectinload(FbsSupply.orders).selectinload(FbsOrder.product),
            selectinload(FbsSupply.orders).selectinload(FbsOrder.markings),
        )
    if for_update:
        stmt = stmt.with_for_update()
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def bind_packaging_box_to_trbx(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    trbx_id: uuid.UUID,
    packaging_box_id: uuid.UUID,
) -> FbsTrbx:
    # Binding a box to a WB cargo place (trbx) is not PVZ-specific: WB accepts
    # cargo places for any delivery_type (see fbs_shipment_pvz_service module
    # docstring), so a warehouse_sc supply may have trbxes to bind too.
    supply = await _load_supply(
        session,
        tenant_id,
        supply_id,
        with_trbxes=True,
        for_update=True,
    )
    if supply is None:
        raise FbsPackagingIntegrationError("supply_not_found")

    trbx = next((row for row in supply.trbxes if row.id == trbx_id), None)
    if trbx is None:
        raise FbsPackagingIntegrationError("trbx_not_found")

    box = await session.scalar(
        select(WarehouseBox)
        .where(
            WarehouseBox.id == packaging_box_id,
            WarehouseBox.tenant_id == tenant_id,
            WarehouseBox.warehouse_id == supply.warehouse_id,
        )
        .with_for_update()
    )
    if box is None:
        raise FbsPackagingIntegrationError("packaging_box_not_found")

    already_bound = await session.scalar(
        select(FbsTrbx.id).where(
            FbsTrbx.packaging_box_id == packaging_box_id,
            FbsTrbx.id != trbx.id,
        )
    )
    if already_bound is not None:
        raise FbsPackagingIntegrationError("packaging_box_already_bound")
    try:
        async with session.begin_nested():
            trbx.packaging_box_id = packaging_box_id
            await session.flush()
    except IntegrityError as exc:
        raise FbsPackagingIntegrationError("packaging_box_already_bound") from exc
    return trbx
