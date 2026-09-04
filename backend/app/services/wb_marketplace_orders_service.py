# ruff: noqa: RUF003
"""WB Marketplace FBS orders: sync, map products, reserve stock, status updates."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import httpx
from sqlalchemy import Select, and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import (
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_DEFECT,
    FBS_ORDER_STATUS_DONE,
    FBS_ORDER_STATUS_EXTERNAL_PROCESSING,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_NEW,
    FBS_ORDER_STATUS_SORTED,
    MAPPING_STATUS_MAPPED,
    MAPPING_STATUS_MISSING,
    RESERVE_STATUS_NO_STOCK,
    RESERVE_STATUS_NOT_PUBLISHED,
    RESERVE_STATUS_RELEASED,
    RESERVE_STATUS_RESERVED,
    RESERVE_STATUS_SKIPPED_NO_PRODUCT,
    RESERVE_STATUS_WAREHOUSE_UNMAPPED,
    FbsOrder,
    FbsOrderProduct,
    FbsOrderProductReservation,
    FbsOrderReservation,
)
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_SOURCE_WB,
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_DONE,
    FbsSupply,
)
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product import Product
from app.models.warehouse import Warehouse
from app.services.fbs_marking_service import apply_wb_meta_requirements_to_order
from app.services.fbs_order_import_scope_service import FbsOrderImportStats, import_wb_order_rows
from app.services.fbs_stock_availability_service import fbs_available_qty_for_product
from app.services.fbs_stock_publish_service import schedule_seller_stock_publish
from app.services.fbs_supply_composition_service import (
    link_order_to_wb_supply_if_compatible,
)
from app.services.fbs_warehouse_binding_service import (
    get_or_create_binding_for_sole_operational_warehouse,
    is_auto_fbs_wms_warehouse,
)
from app.services.fbs_wb_seller_lock_service import wb_seller_lock
from app.services.wildberries_client import (
    WildberriesClientError,
    fetch_marketplace_orders_new,
    fetch_marketplace_orders_page,
    fetch_marketplace_orders_status,
)
from app.services.wildberries_credentials_service import (
    get_decrypted_marketplace_token,
    get_decrypted_tokens_for_seller,
)
from app.services.wildberries_errors import (
    log_wb_client_error,
    wb_error_context,
    wb_error_ref,
    wb_operator_message,
)
from app.services.wildberries_fbs_client import (
    fetch_marketplace_supplies_page,
    fetch_marketplace_supply_details,
    split_marketplace_order_id_batches,
)

FBS_DEADLINE_HOURS = 120
MAX_ORDERS_PAGES = 20
# Окно полного обхода заданий: столько дней назад просим у WB. Совпадает с
# умолчанием WB и с его же ограничением «максимум 30 календарных дней за запрос».
ORDERS_SWEEP_WINDOW_DAYS = 30
# Размер страницы обхода. WB разрешает до 1000, но каждая страница разбирается
# и пишется в одной транзакции: тысяча строк — это долгие блокировки на каждом
# из трёх десятков селлеров. Берём середину — охват тот же за счёт числа страниц,
# транзакция вдвое короче, а двадцать запросов на селлера укладываются в лимит WB
# (300 запросов в минуту на аккаунт).
ORDERS_SWEEP_PAGE_LIMIT = 500
MAX_SUPPLIES_PAGES = 10

RESERVE_STATUS_WAREHOUSE_REMAP_CONFLICT = "warehouse_remap_conflict"

CANCEL_LIKE_WB_STATUSES = frozenset(
    {
        "cancel",
        "canceled",
        "cancelled",
        "canceled_by_client",
        "canceled_by_carrier",
        "declined_by_client",
    }
)

DEFECT_WB_STATUS = "defect"

NO_RESERVE_WB_STATUSES = CANCEL_LIKE_WB_STATUSES | {DEFECT_WB_STATUS}

TERMINAL_FBS_STATUSES = frozenset(
    {FBS_ORDER_STATUS_CANCELLED, FBS_ORDER_STATUS_DONE, FBS_ORDER_STATUS_DEFECT}
)

STATUSES_EXCLUDED_FROM_WB_SYNC = TERMINAL_FBS_STATUSES

SYNC_STATUS_BATCH_SIZE = 500
MAX_SYNC_STATUS_BATCHES = 20

logger = logging.getLogger(__name__)

# Повтор списания пула при занятой базе: рядом может писать фоновая публикация остатка.


class WbMarketplaceOrdersError(Exception):
    def __init__(
        self,
        code: str,
        *,
        message: str | None = None,
        context: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        self.code = code
        self.message = message or code
        self.context = context or {}
        self.retryable = retryable
        super().__init__(code)


def _parse_wb_datetime(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo is not None else raw.replace(tzinfo=UTC)
    if not isinstance(raw, str) or not raw.strip():
        return datetime.now(tz=UTC)
    text = raw.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(tz=UTC)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _first_barcode(row: dict[str, Any]) -> str | None:
    skus = row.get("skus")
    if isinstance(skus, list) and skus:
        first = skus[0]
        if isinstance(first, str) and first.strip():
            return first.strip()
    for key in ("barcode", "sku"):
        val = row.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _status_from_row(row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        val = row.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip().lower()
    return None


def _supplier_status_from_row(row: dict[str, Any]) -> str | None:
    return _status_from_row(row, ("supplierStatus", "status"))


def _wb_status_from_row(row: dict[str, Any]) -> str | None:
    return _status_from_row(row, ("wbStatus", "status"))


def _is_cancel_like_wb_status(wb_status: str | None) -> bool:
    return wb_status is not None and wb_status.strip().lower() in CANCEL_LIKE_WB_STATUSES


def _is_cancelled_wb_row(row: dict[str, Any]) -> bool:
    wb_status = _wb_status_from_row(row)
    supplier_status = _supplier_status_from_row(row)
    return _is_cancel_like_wb_status(wb_status) or _is_cancel_like_wb_status(supplier_status)


def _local_status_from_wb_statuses(
    *,
    wb_status: str | None,
    supplier_status: str | None,
) -> str:
    if _is_cancel_like_wb_status(wb_status) or _is_cancel_like_wb_status(supplier_status):
        return FBS_ORDER_STATUS_CANCELLED
    if wb_status == "sold":
        return FBS_ORDER_STATUS_DONE
    if wb_status == "sorted":
        return FBS_ORDER_STATUS_SORTED
    if wb_status == DEFECT_WB_STATUS:
        return FBS_ORDER_STATUS_DEFECT
    if supplier_status is not None and supplier_status != FBS_ORDER_STATUS_NEW:
        return FBS_ORDER_STATUS_EXTERNAL_PROCESSING
    return FBS_ORDER_STATUS_NEW


def _can_pvz_value_from_row(row: dict[str, Any]) -> bool | None:
    """Разрешена ли сдача заказа через ПВЗ.

    Настоящее поле WB — `isPickupPointShipmentAllowed`. Раньше читались `canPvz`
    и `isPvz`, которых в ответе WB нет вовсе, поэтому признак всегда выходил false
    и маршрут ПВЗ был заблокирован для всех заказов. Старые имена оставлены
    запасными: их отдаёт эмулятор и старые фикстуры.
    """
    for key in ("isPickupPointShipmentAllowed", "canPvz", "isPvz"):
        value = row.get(key)
        if value is not None:
            return bool(value)
    return None


def _can_pvz_from_row(row: dict[str, Any]) -> bool:
    value = _can_pvz_value_from_row(row)
    if value is not None:
        return value
    return False


def _is_legal_order(row: dict[str, Any]) -> bool:
    if row.get("isLegal") is True:
        return True
    options = row.get("options")
    return isinstance(options, dict) and options.get("isB2B") is True


def _cargo_type_label(row: dict[str, Any]) -> str | None:
    raw = row.get("cargoType")
    if raw is None:
        return None
    mapping = {1: "mgt", 2: "kgt", 3: "sgt"}
    if isinstance(raw, int):
        return mapping.get(raw, str(raw))
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


async def available_qty_for_fbs_reserve(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    exclude_order_id: uuid.UUID | None = None,
) -> int:
    """FBS direction pool minus active FBS reserves; no FBS direction means 0."""
    return await fbs_available_qty_for_product(
        session,
        tenant_id,
        warehouse_id,
        product_id,
        exclude_fbs_order_id=exclude_order_id,
    )


def _wb_office_id_from_row(row: dict[str, Any]) -> int | None:
    office = row.get("officeId")
    if office is None:
        return None
    return int(office)


def _wb_warehouse_id_from_row(row: dict[str, Any]) -> int | None:
    wh = row.get("warehouseId")
    if wh is None:
        return None
    return int(wh)


async def _resolve_wms_warehouse_from_binding(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    wb_warehouse_id: int | None,
) -> uuid.UUID | None:
    if wb_warehouse_id is None:
        return None
    stmt = (
        select(FbsWarehouseBinding, Warehouse)
        .join(Warehouse, Warehouse.id == FbsWarehouseBinding.wms_warehouse_id)
        .where(
            FbsWarehouseBinding.tenant_id == tenant_id,
            FbsWarehouseBinding.seller_id == seller_id,
            FbsWarehouseBinding.wb_warehouse_id == wb_warehouse_id,
            FbsWarehouseBinding.is_active.is_(True),
            Warehouse.tenant_id == tenant_id,
        )
    )
    res = await session.execute(stmt)
    row = res.one_or_none()
    if row is None:
        binding = await get_or_create_binding_for_sole_operational_warehouse(
            session, tenant_id, seller_id, wb_warehouse_id
        )
        if binding is None or not binding.is_active:
            return None
        warehouse = await session.get(Warehouse, binding.wms_warehouse_id)
        if warehouse is None:
            return None
    else:
        binding, warehouse = row
        if is_auto_fbs_wms_warehouse(warehouse):
            binding = await get_or_create_binding_for_sole_operational_warehouse(
                session, tenant_id, seller_id, wb_warehouse_id
            )
            if binding is None or not binding.is_active:
                return None
            warehouse = await session.get(Warehouse, binding.wms_warehouse_id)
            if warehouse is None:
                return None
    if is_auto_fbs_wms_warehouse(warehouse):
        binding.stock_sync_enabled = False
        await session.flush()
        return None
    return cast(uuid.UUID, binding.wms_warehouse_id)


async def _resolve_wms_warehouse_for_wb(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    wb_warehouse_id: int | None,
) -> uuid.UUID | None:
    return await _resolve_wms_warehouse_from_binding(session, tenant_id, seller_id, wb_warehouse_id)


async def _get_reservation_warehouse_id(
    session: AsyncSession, order_id: uuid.UUID
) -> uuid.UUID | None:
    stmt = select(FbsOrderReservation.warehouse_id).where(
        FbsOrderReservation.fbs_order_id == order_id
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def _detect_warehouse_remap_conflict(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    order: FbsOrder,
    new_wb_warehouse_id: int,
) -> bool:
    """True when WB warehouse changed but an active reserve pins another WMS warehouse."""
    if new_wb_warehouse_id == order.wb_warehouse_id:
        return False
    reservation_wh = await _get_reservation_warehouse_id(session, order.id)
    if reservation_wh is None:
        return False
    resolved = await _resolve_wms_warehouse_from_binding(
        session, tenant_id, seller_id, new_wb_warehouse_id
    )
    return resolved != reservation_wh


async def _assign_wms_warehouse_from_binding(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    order: FbsOrder,
    wb_warehouse_id: int | None,
) -> None:
    """Map WB warehouse to local WMS warehouse only through an explicit active binding."""
    resolved = await _resolve_wms_warehouse_for_wb(session, tenant_id, seller_id, wb_warehouse_id)
    if resolved is None:
        if order.warehouse_id is not None:
            current_warehouse = await session.get(Warehouse, order.warehouse_id)
            if current_warehouse is not None and is_auto_fbs_wms_warehouse(current_warehouse):
                order.reserve_status = RESERVE_STATUS_WAREHOUSE_REMAP_CONFLICT
                return
            if current_warehouse is None:
                order.warehouse_id = None
        order.reserve_status = RESERVE_STATUS_WAREHOUSE_UNMAPPED
        return

    if order.warehouse_id is None:
        order.warehouse_id = resolved
        return

    if order.warehouse_id == resolved:
        return

    reservation_wh = await _get_reservation_warehouse_id(session, order.id)
    if reservation_wh is not None and reservation_wh != resolved:
        order.reserve_status = RESERVE_STATUS_WAREHOUSE_REMAP_CONFLICT
        return
    # An already assigned order is warehouse work in progress.  A later
    # auto-binding (or a changed external WB route) may make another warehouse
    # resolvable, but must not silently transfer the document.
    return


async def _map_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    wb_barcode: str | None,
    wb_nm_id: int | None,
    wb_chrt_id: int | None,
) -> Product | None:
    async def one_or_none(stmt: Select[tuple[Product]]) -> Product | None:
        rows = list((await session.execute(stmt.limit(2))).scalars().all())
        if len(rows) == 1:
            return rows[0]
        return None

    if wb_chrt_id is not None:
        stmt = select(Product).where(
            Product.tenant_id == tenant_id,
            Product.seller_id == seller_id,
            Product.wb_chrt_id == wb_chrt_id,
        )
        product = await one_or_none(stmt)
        if product is not None:
            return product
    if wb_barcode:
        stmt = select(Product).where(
            Product.tenant_id == tenant_id,
            Product.seller_id == seller_id,
            Product.wb_barcode == wb_barcode,
        )
        product = await one_or_none(stmt)
        if product is not None:
            return product
    if wb_nm_id is not None:
        stmt = select(Product).where(
            Product.tenant_id == tenant_id,
            Product.seller_id == seller_id,
            Product.wb_nm_id == wb_nm_id,
        )
        return await one_or_none(stmt)
    return None


async def _get_order_by_wb_id(
    session: AsyncSession,
    seller_id: uuid.UUID,
    wb_order_id: int,
) -> FbsOrder | None:
    stmt = select(FbsOrder).where(
        FbsOrder.seller_id == seller_id,
        FbsOrder.wb_order_id == wb_order_id,
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def _order_has_reservation(session: AsyncSession, order_id: uuid.UUID) -> bool:
    legacy = await session.scalar(
        select(FbsOrderReservation.id).where(FbsOrderReservation.fbs_order_id == order_id)
    )
    if legacy is not None:
        return True
    return (
        await session.scalar(
            select(FbsOrderProductReservation.id)
            .join(
                FbsOrderProduct, FbsOrderProduct.id == FbsOrderProductReservation.order_product_id
            )
            .where(FbsOrderProduct.order_id == order_id)
        )
    ) is not None


async def _lock_product_for_fbs_reserve(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
) -> Product | None:
    stmt = (
        select(Product)
        .where(Product.id == product_id, Product.tenant_id == tenant_id)
        .with_for_update()
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _lock_fbs_reservations_for_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
) -> None:
    stmt = (
        select(FbsOrderReservation.id)
        .where(
            FbsOrderReservation.tenant_id == tenant_id,
            FbsOrderReservation.warehouse_id == warehouse_id,
            FbsOrderReservation.product_id == product_id,
        )
        .with_for_update()
    )
    await session.execute(stmt)


async def _try_reserve_order(
    session: AsyncSession,
    order: FbsOrder,
) -> None:
    if order.status in TERMINAL_FBS_STATUSES:
        return
    if order.status == FBS_ORDER_STATUS_EXTERNAL_PROCESSING:
        return
    if order.wb_status is not None and order.wb_status.lower() in NO_RESERVE_WB_STATUSES:
        return
    if (
        order.supplier_status is not None
        and order.supplier_status.strip().lower() != FBS_ORDER_STATUS_NEW
    ):
        return
    positions = list(
        (await session.execute(select(FbsOrderProduct).where(FbsOrderProduct.order_id == order.id)))
        .scalars()
        .all()
    )
    if order.marketplace == "ozon" and positions:
        if order.warehouse_id is None:
            order.reserve_status = RESERVE_STATUS_WAREHOUSE_UNMAPPED
            return
        if any(position.product_id is None or position.quantity < 1 for position in positions):
            order.reserve_status = RESERVE_STATUS_SKIPPED_NO_PRODUCT
            return
        if await _order_has_reservation(session, order.id):
            return
        required_by_product: dict[uuid.UUID, int] = {}
        for position in positions:
            assert position.product_id is not None
            required_by_product[position.product_id] = (
                required_by_product.get(position.product_id, 0) + position.quantity
            )
        for product_id, quantity in required_by_product.items():
            await _lock_product_for_fbs_reserve(session, order.tenant_id, product_id)
            await _lock_fbs_reservations_for_product(
                session, order.tenant_id, order.warehouse_id, product_id
            )
            available = await available_qty_for_fbs_reserve(
                session,
                order.tenant_id,
                order.warehouse_id,
                product_id,
                exclude_order_id=order.id,
            )
            if available < quantity:
                order.reserve_status = RESERVE_STATUS_NO_STOCK
                return
        async with session.begin_nested():
            for position in positions:
                assert position.product_id is not None
                session.add(
                    FbsOrderProductReservation(
                        tenant_id=order.tenant_id,
                        order_product_id=position.id,
                        product_id=position.product_id,
                        warehouse_id=order.warehouse_id,
                        quantity=position.quantity,
                    )
                )
                position.reserved_quantity = position.quantity
            order.reserve_status = RESERVE_STATUS_RESERVED
            await session.flush()
        schedule_seller_stock_publish(session, order.tenant_id, order.seller_id)
        return
    if order.product_id is None:
        order.reserve_status = RESERVE_STATUS_SKIPPED_NO_PRODUCT
        return
    if order.warehouse_id is None:
        order.reserve_status = RESERVE_STATUS_WAREHOUSE_UNMAPPED
        return
    if await _order_has_reservation(session, order.id):
        return
    product = await _lock_product_for_fbs_reserve(
        session, order.tenant_id, order.product_id
    )
    if (
        product is None
        or not product.fbs_stock_sync_enabled
        or product.fbs_percent is None
    ):
        order.reserve_status = RESERVE_STATUS_NOT_PUBLISHED
        return
    await _lock_fbs_reservations_for_product(
        session, order.tenant_id, order.warehouse_id, order.product_id
    )
    available = await available_qty_for_fbs_reserve(
        session,
        order.tenant_id,
        order.warehouse_id,
        order.product_id,
        exclude_order_id=order.id,
    )
    if available < 1:
        order.reserve_status = RESERVE_STATUS_NO_STOCK
        return
    try:
        async with session.begin_nested():
            session.add(
                FbsOrderReservation(
                    tenant_id=order.tenant_id,
                    fbs_order_id=order.id,
                    product_id=order.product_id,
                    warehouse_id=order.warehouse_id,
                    quantity=1,
                )
            )
            order.reserve_status = RESERVE_STATUS_RESERVED
            await session.flush()
    except IntegrityError:
        order.reserve_status = RESERVE_STATUS_NO_STOCK
        return
    # Резерв под ФБС-заказ уменьшает доступное — кабинет должен увидеть новую цифру.
    schedule_seller_stock_publish(session, order.tenant_id, order.seller_id)


async def _release_reservation(session: AsyncSession, order: FbsOrder) -> None:
    stmt = select(FbsOrderReservation).where(FbsOrderReservation.fbs_order_id == order.id)
    res = await session.execute(stmt)
    reservation = res.scalar_one_or_none()
    position_reservations = list(
        (
            await session.execute(
                select(FbsOrderProductReservation)
                .join(
                    FbsOrderProduct,
                    FbsOrderProduct.id == FbsOrderProductReservation.order_product_id,
                )
                .where(FbsOrderProduct.order_id == order.id)
            )
        )
        .scalars()
        .all()
    )
    if reservation is None and not position_reservations:
        return
    if reservation is not None:
        await session.delete(reservation)
    for position_reservation in position_reservations:
        position = await session.get(FbsOrderProduct, position_reservation.order_product_id)
        if position is not None:
            position.reserved_quantity = 0
        await session.delete(position_reservation)
    order.reserve_status = RESERVE_STATUS_RELEASED
    # Снятый резерв возвращает товар в доступное — публикуем увеличенную цифру.
    schedule_seller_stock_publish(session, order.tenant_id, order.seller_id)


async def _move_new_order_to_external_processing(
    session: AsyncSession,
    order: FbsOrder,
) -> None:
    if order.status != FBS_ORDER_STATUS_NEW or order.supply_id is not None:
        return
    order.status = FBS_ORDER_STATUS_EXTERNAL_PROCESSING
    await _release_reservation(session, order)


async def _apply_wb_row_to_existing(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    existing: FbsOrder,
    row: dict[str, Any],
    *,
    preserve_unmapped_warehouse: bool = False,
) -> None:
    wb_barcode = _first_barcode(row)
    wb_nm_id = row.get("nmId")
    wb_nm_id_int = int(wb_nm_id) if wb_nm_id is not None else None

    existing.wb_rid = row.get("rid") if isinstance(row.get("rid"), str) else existing.wb_rid
    existing.wb_nm_id = wb_nm_id_int
    existing.wb_chrt_id = (
        int(row["chrtId"]) if row.get("chrtId") is not None else existing.wb_chrt_id
    )
    existing.wb_article = (
        str(row["article"]) if row.get("article") is not None else existing.wb_article
    )
    existing.wb_barcode = wb_barcode or existing.wb_barcode
    existing.price = int(row["price"]) if row.get("price") is not None else existing.price
    existing.is_legal = _is_legal_order(row)
    existing.cargo_type = _cargo_type_label(row)
    office_id = _wb_office_id_from_row(row)
    if office_id is not None:
        existing.wb_office_id = office_id
    wb_wh_id = _wb_warehouse_id_from_row(row)
    if wb_wh_id is not None:
        if await _detect_warehouse_remap_conflict(
            session, tenant_id, seller_id, existing, wb_wh_id
        ):
            existing.reserve_status = RESERVE_STATUS_WAREHOUSE_REMAP_CONFLICT
        else:
            existing.wb_warehouse_id = wb_wh_id
    wb_supply_id = _wb_supply_id_from_order_row(row)
    if wb_supply_id is not None:
        existing.wb_supply_id = wb_supply_id
    can_pvz = _can_pvz_value_from_row(row)
    if can_pvz is not None:
        existing.can_pvz = can_pvz
    supplier_status = _supplier_status_from_row(row)
    wb_status = _wb_status_from_row(row)
    if supplier_status is not None or wb_status is not None:
        await _apply_wb_status_to_order(
            session,
            existing,
            wb_status,
            supplier_status=supplier_status,
            actor_user_id=None,
        )
    apply_wb_meta_requirements_to_order(existing, row)
    if preserve_unmapped_warehouse:
        if existing.warehouse_id is None:
            existing.reserve_status = RESERVE_STATUS_WAREHOUSE_UNMAPPED
    else:
        await _assign_wms_warehouse_from_binding(
            session, tenant_id, seller_id, existing, existing.wb_warehouse_id
        )
    if existing.product_id is None:
        product = await _map_product(
            session,
            tenant_id,
            seller_id,
            wb_barcode=existing.wb_barcode,
            wb_nm_id=existing.wb_nm_id,
            wb_chrt_id=existing.wb_chrt_id,
        )
        if product is not None:
            existing.product_id = product.id
            existing.mapping_status = MAPPING_STATUS_MAPPED
    try:
        async with session.begin_nested():
            await _try_reserve_order(session, existing)
    except IntegrityError:
        pass


async def upsert_order_from_wb_row(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    row: dict[str, Any],
    *,
    preserve_unmapped_warehouse: bool = False,
) -> tuple[FbsOrder, bool]:
    """Returns (order, created).

    "shortfall": int} across calls: units actually subtracted from
    fbs_binding_stock_pools for this row's order, and units that could not
    be subtracted because the pool was already lower than the order needed
    (a WB-cabinet desync, not an error to raise on). Callers that don't
    care can omit it; the 2-tuple return is unchanged so no call site breaks.
    """
    wb_order_id_raw = row.get("id")
    if wb_order_id_raw is None:
        raise WbMarketplaceOrdersError("missing_wb_order_id")
    wb_order_id = int(wb_order_id_raw)
    created_at_wb = _parse_wb_datetime(row.get("createdAt"))
    deadline_at = created_at_wb + timedelta(hours=FBS_DEADLINE_HOURS)
    wb_barcode = _first_barcode(row)
    wb_nm_id = row.get("nmId")
    wb_nm_id_int = int(wb_nm_id) if wb_nm_id is not None else None
    wb_chrt_id = row.get("chrtId")
    wb_chrt_id_int = int(wb_chrt_id) if wb_chrt_id is not None else None

    existing = await _get_order_by_wb_id(session, seller_id, wb_order_id)
    if existing is not None:
        await _apply_wb_row_to_existing(
            session,
            tenant_id,
            seller_id,
            existing,
            row,
            preserve_unmapped_warehouse=preserve_unmapped_warehouse,
        )
        return existing, False

    product = await _map_product(
        session,
        tenant_id,
        seller_id,
        wb_barcode=wb_barcode,
        wb_nm_id=wb_nm_id_int,
        wb_chrt_id=wb_chrt_id_int,
    )
    mapping_status = MAPPING_STATUS_MAPPED if product is not None else MAPPING_STATUS_MISSING
    wb_warehouse_id = _wb_warehouse_id_from_row(row)
    wms_warehouse_id = None
    if not preserve_unmapped_warehouse:
        wms_warehouse_id = await _resolve_wms_warehouse_for_wb(
            session, tenant_id, seller_id, wb_warehouse_id
        )
    if product is None:
        reserve_status = RESERVE_STATUS_SKIPPED_NO_PRODUCT
    elif wms_warehouse_id is None:
        reserve_status = RESERVE_STATUS_WAREHOUSE_UNMAPPED
    else:
        reserve_status = RESERVE_STATUS_NO_STOCK

    wb_status = _wb_status_from_row(row)
    supplier_status = _supplier_status_from_row(row)
    order = FbsOrder(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=wms_warehouse_id,
        product_id=product.id if product is not None else None,
        wb_order_id=wb_order_id,
        wb_rid=row.get("rid") if isinstance(row.get("rid"), str) else None,
        wb_nm_id=wb_nm_id_int,
        wb_chrt_id=wb_chrt_id_int,
        wb_article=str(row["article"]) if row.get("article") is not None else None,
        wb_barcode=wb_barcode,
        price=int(row["price"]) if row.get("price") is not None else None,
        is_legal=_is_legal_order(row),
        cargo_type=_cargo_type_label(row),
        wb_office_id=_wb_office_id_from_row(row),
        wb_warehouse_id=wb_warehouse_id,
        wb_supply_id=_wb_supply_id_from_order_row(row),
        can_pvz=_can_pvz_from_row(row),
        status=_local_status_from_wb_statuses(
            wb_status=wb_status,
            supplier_status=supplier_status,
        ),
        wb_status=wb_status,
        supplier_status=supplier_status,
        created_at_wb=created_at_wb,
        deadline_at=deadline_at,
        mapping_status=mapping_status,
        reserve_status=reserve_status,
    )
    apply_wb_meta_requirements_to_order(order, row)
    try:
        async with session.begin_nested():
            session.add(order)
            await session.flush()
            await _try_reserve_order(session, order)
    except IntegrityError:
        raced = await _get_order_by_wb_id(session, seller_id, wb_order_id)
        if raced is None:
            raise WbMarketplaceOrdersError("duplicate_order_race") from None
        await _apply_wb_row_to_existing(
            session,
            tenant_id,
            seller_id,
            raced,
            row,
            preserve_unmapped_warehouse=preserve_unmapped_warehouse,
        )
        return raced, False
    return order, True


async def _apply_wb_status_to_order(
    session: AsyncSession,
    order: FbsOrder,
    wb_status: str | None,
    *,
    supplier_status: str | None = None,
    actor_user_id: uuid.UUID | None,
) -> None:
    normalized_wb = (
        wb_status.strip().lower() if isinstance(wb_status, str) and wb_status.strip() else None
    )
    normalized_supplier = (
        supplier_status.strip().lower()
        if isinstance(supplier_status, str) and supplier_status.strip()
        else None
    )
    if normalized_wb is not None:
        order.wb_status = normalized_wb
    if normalized_supplier is not None:
        order.supplier_status = normalized_supplier

    effective_statuses = tuple(
        status for status in (normalized_wb, normalized_supplier) if status is not None
    )

    if any(_is_cancel_like_wb_status(status) for status in effective_statuses):
        from app.services.fbs_cancellation_service import reverse_fbs_shipment_if_needed
        from app.services.fbs_packaging_integration_service import (
            detach_cancelled_order_from_supply,
        )

        order.status = FBS_ORDER_STATUS_CANCELLED
        await reverse_fbs_shipment_if_needed(
            session,
            order,
            actor_user_id=actor_user_id,
        )
        await detach_cancelled_order_from_supply(
            session,
            order.tenant_id,
            order,
            actor_user_id=actor_user_id,
        )
        await _release_reservation(session, order)
        return
    if normalized_wb == "sold":
        order.status = FBS_ORDER_STATUS_DONE
        # Склад здесь не трогаем ничем. Остаток снимает только наша передача
        # поставки маркетплейсу — правило владельца OWN-20.
        # Выкуплен: резерв больше не нужен (иначе available навсегда занижен).
        await _release_reservation(session, order)
        await _charge_confirmed_order(session, order)
        return
    if normalized_wb == "sorted":
        order.status = FBS_ORDER_STATUS_SORTED
        await _charge_confirmed_order(session, order)
        return
    if normalized_wb == DEFECT_WB_STATUS:
        order.status = FBS_ORDER_STATUS_DEFECT
        await _release_reservation(session, order)
        return
    if normalized_supplier is not None and normalized_supplier != FBS_ORDER_STATUS_NEW:
        await _move_new_order_to_external_processing(session, order)
        return
    if normalized_wb == "waiting":
        if order.status != FBS_ORDER_STATUS_IN_DELIVERY:
            return
        return


async def _charge_confirmed_order(session: AsyncSession, order: FbsOrder) -> None:
    """Начислить за собранный заказ, когда WB подтвердил, что забрал его.

    Импорт внутри функции: модуль тарификации ходит в биллинг, а биллинг знает
    про заказы — на уровне модулей это дало бы цикл.
    """
    from app.services.fbs_order_billing_service import record_fbs_order_confirmed

    try:
        # Точка сохранения обязательна. Голого except мало: ошибка на стороне
        # базы (нарушенное ограничение, отвалившееся соединение) переводит всю
        # транзакцию PostgreSQL в аварийное состояние, и следующий commit падает
        # уже сам по себе. Тогда вместе с начислением откатились бы и статус
        # заказа, и списание товара по «sold», и снятие резерва: WB заказ забрал,
        # а на складе он остался бы висеть в старой вкладке и искажать остаток.
        # Savepoint откатывает только начисление, а внешняя транзакция остаётся
        # живой и довозит статусы по всему батчу.
        async with session.begin_nested():
            await record_fbs_order_confirmed(session, order)
    except Exception:
        # Деньги важны, но статусы важнее: если начисление почему-то не легло,
        # проход опроса обязан довезти статусы по всему батчу, а не откатиться
        # вместе с блокировками. Разбираемся по логу, а не по остановленному складу.
        logger.exception("fbs order charge skipped: order_id=%s", order.id)


def _wb_orders_error_from_client(
    exc: WildberriesClientError,
    *,
    ref: str,
    extra_context: dict[str, Any] | None = None,
) -> WbMarketplaceOrdersError:
    suffix = f"_{exc.status_code}" if exc.status_code else ""
    return WbMarketplaceOrdersError(
        f"wb_{exc.code}{suffix}",
        message=wb_operator_message(exc),
        context=wb_error_context(exc, ref=ref, extra=extra_context),
        retryable=exc.code == "transport_error",
    )


async def _fetch_status_rows_resilient(
    http_client: httpx.AsyncClient,
    *,
    api_token: str,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    orders_by_wb_id: dict[int, list[FbsOrder]],
) -> list[dict[str, Any]]:
    status_rows: list[dict[str, Any]] = []
    wb_ids = sorted(orders_by_wb_id)
    for batch in split_marketplace_order_id_batches(wb_ids):
        try:
            status_rows.extend(
                await fetch_marketplace_orders_status(
                    http_client,
                    api_token=api_token,
                    order_ids=batch,
                )
            )
            continue
        except WildberriesClientError as exc:
            ref = wb_error_ref()
            log_wb_client_error(
                logger,
                "fbs order status WB batch failed; retrying per order",
                exc,
                tenant_id=tenant_id,
                seller_id=seller_id,
                local_entity_id=None,
                wb_object_id=",".join(str(item) for item in batch[:10]),
                ref=ref,
                level=logging.WARNING,
            )
            if len(batch) == 1:
                continue

        for wb_order_id in batch:
            try:
                status_rows.extend(
                    await fetch_marketplace_orders_status(
                        http_client,
                        api_token=api_token,
                        order_ids=[wb_order_id],
                    )
                )
            except WildberriesClientError as exc:
                ref = wb_error_ref()
                local_ids = [str(order.id) for order in orders_by_wb_id.get(wb_order_id, [])]
                log_wb_client_error(
                    logger,
                    "fbs order status WB single order skipped",
                    exc,
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    local_entity_id=",".join(local_ids) or None,
                    wb_object_id=wb_order_id,
                    ref=ref,
                    level=logging.WARNING,
                )
                continue
    return status_rows


async def sync_order_statuses(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    api_token: str,
    *,
    actor_user_id: uuid.UUID | None,
) -> int:
    updated = 0
    last_created_at: datetime | None = None
    last_id: uuid.UUID | None = None
    for _batch in range(MAX_SYNC_STATUS_BATCHES):
        filters = [
            FbsOrder.tenant_id == tenant_id,
            FbsOrder.seller_id == seller_id,
            FbsOrder.status.not_in(tuple(STATUSES_EXCLUDED_FROM_WB_SYNC)),
        ]
        if last_created_at is not None and last_id is not None:
            filters.append(
                or_(
                    FbsOrder.created_at_wb > last_created_at,
                    and_(
                        FbsOrder.created_at_wb == last_created_at,
                        FbsOrder.id > last_id,
                    ),
                )
            )
        stmt = (
            select(FbsOrder)
            .where(*filters)
            .order_by(FbsOrder.created_at_wb.asc(), FbsOrder.id.asc())
            .limit(SYNC_STATUS_BATCH_SIZE)
            .with_for_update()
        )
        res = await session.execute(stmt)
        orders = list(res.scalars().all())
        if not orders:
            break

        orders_by_wb_id: dict[int, list[FbsOrder]] = {}
        for order in orders:
            if order.wb_order_id <= 0:
                logger.warning(
                    "fbs order status skipped invalid local wb_order_id tenant_id=%s "
                    "seller_id=%s order_id=%s wb_order_id=%s",
                    tenant_id,
                    seller_id,
                    order.id,
                    order.wb_order_id,
                )
                continue
            orders_by_wb_id.setdefault(int(order.wb_order_id), []).append(order)
        if not orders_by_wb_id:
            last_row = orders[-1]
            last_created_at = last_row.created_at_wb
            last_id = last_row.id
            continue
        status_rows = await _fetch_status_rows_resilient(
            http_client,
            api_token=api_token,
            tenant_id=tenant_id,
            seller_id=seller_id,
            orders_by_wb_id=orders_by_wb_id,
        )

        by_id: dict[int, dict[str, Any]] = {}
        for row in status_rows:
            oid = row.get("id")
            if oid is not None:
                by_id[int(oid)] = row

        for order in orders:
            status_row = by_id.get(order.wb_order_id)
            if status_row is None:
                continue
            wb_status = _wb_status_from_row(status_row)
            supplier_status = _supplier_status_from_row(status_row)
            if wb_status is None and supplier_status is None:
                continue
            await _apply_wb_status_to_order(
                session,
                order,
                wb_status,
                supplier_status=supplier_status,
                actor_user_id=actor_user_id,
            )
            updated += 1

        last_row = orders[-1]
        last_created_at = last_row.created_at_wb
        last_id = last_row.id
        if len(orders) < SYNC_STATUS_BATCH_SIZE:
            break
    return updated


def _wb_supply_id_from_order_row(row: dict[str, Any]) -> str | None:
    for key in ("supplyId", "supplyID", "supply_id", "wb_supply_id"):
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _wb_supply_name_from_row(row: dict[str, Any], wb_supply_id: str) -> str:
    for key in ("name", "supplyName", "supply_name"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"WB supply {wb_supply_id}"


def _wb_supply_created_at_from_row(row: dict[str, Any]) -> datetime | None:
    for key in ("supplyCreatedAt", "supplyCreateDate", "supply_created_at"):
        value = row.get(key)
        if value is not None:
            return _parse_wb_datetime(value)
    return None


async def _load_unlinked_confirmed_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> list[FbsOrder]:
    stmt = (
        select(FbsOrder)
        .where(
            FbsOrder.tenant_id == tenant_id,
            FbsOrder.seller_id == seller_id,
            FbsOrder.supply_id.is_(None),
            FbsOrder.wb_supply_id.is_not(None),
            FbsOrder.supplier_status == "confirm",
            FbsOrder.status.not_in(tuple(TERMINAL_FBS_STATUSES)),
        )
        .order_by(FbsOrder.created_at_wb.asc(), FbsOrder.id.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def _get_existing_supply_by_wb_id(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    wb_supply_id: str,
) -> FbsSupply | None:
    stmt = select(FbsSupply).where(
        FbsSupply.tenant_id == tenant_id,
        FbsSupply.seller_id == seller_id,
        FbsSupply.wb_supply_id == wb_supply_id,
    )
    res = await session.execute(stmt.limit(1))
    return res.scalar_one_or_none()


async def _resolve_supply_warehouse_for_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    orders: list[FbsOrder],
) -> uuid.UUID | None:
    for order in orders:
        if order.warehouse_id is not None:
            warehouse = await session.get(Warehouse, order.warehouse_id)
            if warehouse is not None and not is_auto_fbs_wms_warehouse(warehouse):
                return order.warehouse_id
            order.warehouse_id = None
            order.reserve_status = RESERVE_STATUS_WAREHOUSE_UNMAPPED
        if order.wb_warehouse_id is None:
            continue
        resolved = await _resolve_wms_warehouse_for_wb(
            session, tenant_id, seller_id, order.wb_warehouse_id
        )
        if resolved is not None:
            order.warehouse_id = resolved
            return resolved
    return None


async def _get_or_create_wb_origin_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    wb_supply_id: str,
    row: dict[str, Any],
    matching_orders: list[FbsOrder],
    http_client: httpx.AsyncClient | None = None,
    api_token: str | None = None,
    supplies_dict: dict[str, tuple[str | None, bool]] | None = None,
) -> FbsSupply | None:
    existing = await _get_existing_supply_by_wb_id(session, tenant_id, seller_id, wb_supply_id)
    if existing is not None:
        return existing

    warehouse_id = await _resolve_supply_warehouse_for_orders(
        session, tenant_id, seller_id, matching_orders
    )
    if warehouse_id is None:
        logger.warning(
            "wb supply link skipped: seller=%s wb_supply_id=%s reason=no_local_warehouse",
            seller_id,
            wb_supply_id,
        )
        return None

    first_order = matching_orders[0]

    # Get supply details from pre-fetched dictionary or fall back to individual request
    supply_name = _wb_supply_name_from_row(row, wb_supply_id)
    supply_status = FBS_SUPPLY_STATUS_ASSEMBLING

    if supplies_dict is not None and wb_supply_id in supplies_dict:
        # Use data from pre-fetched supplies list
        wb_name, wb_done = supplies_dict[wb_supply_id]
        if wb_name:
            supply_name = wb_name
        if wb_done:
            supply_status = FBS_SUPPLY_STATUS_DONE
    elif http_client is not None and api_token is not None:
        # Fall back to individual fetch if not in supplies_dict
        try:
            details = await fetch_marketplace_supply_details(
                http_client,
                api_token=api_token,
                supply_id=wb_supply_id,
            )
            if details.name:
                supply_name = details.name
            if details.done:
                supply_status = FBS_SUPPLY_STATUS_DONE
        except Exception as exc:
            logger.warning(
                "wb supply details fetch failed: seller=%s wb_supply_id=%s error=%s",
                seller_id,
                wb_supply_id,
                type(exc).__name__,
                exc_info=True,
            )

    supply = FbsSupply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_supply_id=wb_supply_id,
        name=supply_name,
        source=FBS_SUPPLY_SOURCE_WB,
        status=supply_status,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        cargo_type=first_order.cargo_type,
        wb_office_id=first_order.wb_office_id,
        created_at_wb=_wb_supply_created_at_from_row(row),
    )
    session.add(supply)
    await session.flush()
    return supply


# Ключи сводки синхронизации, которые доезжают до `sync_seller_orders` и дальше — до
# фонового задания `/operations/fbs-orders/sync`. Один источник умолчаний, чтобы во всех
# ранних `return` не разъезжались набор ключей: раньше «пропуск из-за непривязанного
# склада» был виден только в логе (logger.warning), оператор видел заказы с пометкой
# «склад WB не привязан» и не понимал, почему поставка из кабинета WB не появилась.
def _empty_supply_link_result(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "supply_link_candidates": 0,
        "supply_linked_orders": 0,
        "supply_links_created": 0,
        "supply_link_supplies_scanned": 0,
        "supply_link_skipped_unmapped_warehouse": 0,
        "supply_link_skipped_unmapped_warehouse_supply_ids": [],
        "supply_link_skipped_warehouse_mismatch_orders": 0,
        "supply_link_discrepancies": [],
    }
    result.update(overrides)
    return result


async def fetch_seller_supplies_map(
    http_client: httpx.AsyncClient,
    *,
    api_token: str,
    seller_id: uuid.UUID,
) -> dict[str, tuple[str | None, bool]]:
    """Все поставки селлера одним списком: `{wb_supply_id: (имя, закрыта ли)}`.

    У WB два способа узнать, закрыта ли поставка: спросить про каждую отдельно
    (`GET /supplies/{id}`) или забрать список целиком. Поштучный опрос упирается
    в лимит запросов: на бою у селлера с восемью незакрытыми поставками часть
    ответов приходила как 429, и эти поставки висели «в работе» сутками, потому
    что следующий проход повторял ту же очередь. Список стоит один запрос на
    селлера независимо от числа поставок, поэтому он и есть основной источник.

    Список может не доехать (сеть, лимит, ошибка WB) — тогда возвращается пустая
    карта, а вызывающий сам решает, спрашивать ли про поставку поштучно.
    """
    supplies_map: dict[str, tuple[str | None, bool]] = {}
    try:
        next_cursor: int | None = None
        for _page in range(MAX_SUPPLIES_PAGES):
            try:
                page = await fetch_marketplace_supplies_page(
                    http_client,
                    api_token=api_token,
                    next_cursor=next_cursor,
                )
                supplies_map.update(page.supplies)
                # WB отдаёт курсор всегда, даже когда данные кончились: по одному
                # только курсору цикл крутил все MAX_SUPPLIES_PAGES страниц на каждого
                # селлера. На бою это 10 запросов × 20 селлеров за проход и 429
                # от общего лимитера. Признак конца — пустая страница.
                if not page.supplies or page.next_cursor is None:
                    break
                next_cursor = page.next_cursor
            except WildberriesClientError as exc:
                logger.warning(
                    "wb supplies list fetch failed: seller=%s error=%s page=%d",
                    seller_id,
                    exc.code,
                    _page,
                    exc_info=True,
                )
                break
    except Exception as exc:
        logger.warning(
            "wb supplies list fetch failed with exception: seller=%s error=%s",
            seller_id,
            type(exc).__name__,
            exc_info=True,
        )
    return supplies_map


async def link_confirmed_orders_to_wb_supplies(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    api_token: str,
) -> dict[str, Any]:
    supplies_dict = await fetch_seller_supplies_map(
        http_client, api_token=api_token, seller_id=seller_id
    )

    # Periodic sync: update non-terminal supplies that are done in WB
    # using supplies_dict
    stmt_unfinished = select(FbsSupply).where(
        FbsSupply.tenant_id == tenant_id,
        FbsSupply.seller_id == seller_id,
        FbsSupply.source == FBS_SUPPLY_SOURCE_WB,
        FbsSupply.status != FBS_SUPPLY_STATUS_DONE,
    )
    res_unfinished = await session.execute(stmt_unfinished)
    unfinished_supplies = list(res_unfinished.scalars().all())

    for local_supply in unfinished_supplies:
        if local_supply.wb_supply_id in supplies_dict:
            wb_name, wb_done = supplies_dict[local_supply.wb_supply_id]
            if wb_done:
                local_supply.status = FBS_SUPPLY_STATUS_DONE
                if wb_name:
                    local_supply.name = wb_name

    await session.commit()

    candidates = await _load_unlinked_confirmed_orders(session, tenant_id, seller_id)
    if not candidates:
        return _empty_supply_link_result()

    async with wb_seller_lock(session, seller_id) as acquired:
        if not acquired:
            logger.info("wb supply link skipped: seller=%s reason=lock_busy", seller_id)
            return _empty_supply_link_result(
                supply_link_candidates=len(candidates),
                supply_link_skipped="seller_lock_busy",
            )

        candidates = await _load_unlinked_confirmed_orders(session, tenant_id, seller_id)
        if not candidates:
            return _empty_supply_link_result()

        candidates_by_supply_id: dict[str, list[FbsOrder]] = {}
        for order in candidates:
            if order.wb_supply_id is None:
                continue
            wb_supply_id = order.wb_supply_id.strip()
            if wb_supply_id:
                candidates_by_supply_id.setdefault(wb_supply_id, []).append(order)

        if not candidates_by_supply_id:
            return _empty_supply_link_result(supply_link_candidates=len(candidates))

        linked_orders = 0
        supplies_created = 0
        supplies_scanned = len(candidates_by_supply_id)
        skipped_unmapped_warehouse_supply_ids: list[str] = []
        skipped_warehouse_mismatch_orders = 0
        link_discrepancies: list[dict[str, Any]] = []

        for wb_supply_id, matching_orders in candidates_by_supply_id.items():
            existed_before = (
                await _get_existing_supply_by_wb_id(session, tenant_id, seller_id, wb_supply_id)
                is not None
            )
            supply = await _get_or_create_wb_origin_supply(
                session,
                tenant_id,
                seller_id,
                wb_supply_id,
                {"supplyId": wb_supply_id},
                matching_orders,
                http_client=http_client,
                api_token=api_token,
                supplies_dict=supplies_dict,
            )
            if supply is None:
                # _get_or_create_wb_origin_supply вернул None только по одной причине:
                # ни у одного заказа поставки не нашлось привязки WB-склад → WMS-склад
                # (см. _resolve_supply_warehouse_for_orders). Раньше это было видно только
                # в логе; теперь сводка несёт номер поставки WB дальше, в интерфейс.
                skipped_unmapped_warehouse_supply_ids.append(wb_supply_id)
                continue
            if not existed_before:
                supplies_created += 1

            current_orders = list(
                (
                    await session.execute(
                        select(FbsOrder).where(FbsOrder.supply_id == supply.id)
                    )
                )
                .scalars()
                .all()
            )
            added_orders: list[FbsOrder] = []
            for order in matching_orders:
                if order.supply_id is not None:
                    continue
                if order.warehouse_id is None and order.wb_warehouse_id is not None:
                    order.warehouse_id = await _resolve_wms_warehouse_for_wb(
                        session, tenant_id, seller_id, order.wb_warehouse_id
                    )
                link_result = await link_order_to_wb_supply_if_compatible(
                    session,
                    supply,
                    order,
                    existing_orders=current_orders,
                )
                if link_result.discrepancy is not None:
                    logger.warning(
                        "wb supply link skipped: seller=%s wb_supply_id=%s wb_order_id=%s "
                        "reason=%s",
                        seller_id,
                        wb_supply_id,
                        order.wb_order_id,
                        link_result.discrepancy.code,
                    )
                    if link_result.discrepancy.code == "different_wms_warehouse":
                        skipped_warehouse_mismatch_orders += 1
                    link_discrepancies.append(
                        {
                            "wb_supply_id": wb_supply_id,
                            "wb_order_id": int(order.wb_order_id),
                            "order_id": str(order.id),
                            "reason": link_result.discrepancy.code,
                        }
                    )
                    continue
                if link_result.linked:
                    added_orders.append(order)
                    linked_orders += 1

            if added_orders:
                from app.services.fbs_supply_service import (
                    _sync_existing_packaging_task_for_added_orders,
                )

                await _sync_existing_packaging_task_for_added_orders(
                    session,
                    tenant_id,
                    supply,
                    added_orders,
                )

        await session.commit()
        result = _empty_supply_link_result(
            supply_link_candidates=len(candidates),
            supply_linked_orders=linked_orders,
            supply_links_created=supplies_created,
            supply_link_supplies_scanned=supplies_scanned,
            supply_link_skipped_unmapped_warehouse=len(skipped_unmapped_warehouse_supply_ids),
            supply_link_skipped_unmapped_warehouse_supply_ids=skipped_unmapped_warehouse_supply_ids,
            supply_link_skipped_warehouse_mismatch_orders=skipped_warehouse_mismatch_orders,
            supply_link_discrepancies=link_discrepancies,
        )
        return result


async def _resolve_marketplace_api_token(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> str:
    """Prefer dedicated marketplace token; fall back to supplies token for intake."""
    marketplace_token = await get_decrypted_marketplace_token(session, tenant_id, seller_id)
    if marketplace_token:
        return marketplace_token
    pair = await get_decrypted_tokens_for_seller(session, tenant_id, seller_id)
    if pair is None:
        raise WbMarketplaceOrdersError("seller_not_found")
    _content, supplies_token = pair
    if not supplies_token:
        raise WbMarketplaceOrdersError("missing_marketplace_token")
    return supplies_token


async def sync_seller_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    *,
    warehouse_id: uuid.UUID | None = None,
    include_history: bool = True,
) -> dict[str, Any]:
    """Fetch seller orders, optionally limiting the cycle to WB's new feed."""
    _ = warehouse_id  # ignored: WMS warehouse resolved per order via WB binding
    api_token = await _resolve_marketplace_api_token(session, tenant_id, seller_id)

    try:
        new_rows = await fetch_marketplace_orders_new(http_client, api_token=api_token)
    except WildberriesClientError as exc:
        ref = wb_error_ref()
        log_wb_client_error(
            logger,
            "fbs orders WB new-orders failed",
            exc,
            tenant_id=tenant_id,
            seller_id=seller_id,
            ref=ref,
        )
        raise _wb_orders_error_from_client(exc, ref=ref) from exc

    import_stats = FbsOrderImportStats()
    orders_page_error: str | None = None
    status_sync_error: str | None = None
    supply_link_result: dict[str, Any] = {}

    await import_wb_order_rows(
        session, tenant_id, seller_id, new_rows, import_stats
    )
    if import_stats.received:
        await session.commit()

    if include_history:
        # WB и без dateFrom отдаёт последние 30 дней (это его умолчание), поэтому
        # дело было не в диапазоне, а в глубине: страницами по сто штук обход
        # прочитывал тысячу самых ранних заданий окна и до свежих не доходил —
        # у крупного селлера их под четыре тысячи за месяц. Просим окно явно и
        # увеличиваем охват до десяти тысяч заданий за проход.
        sweep_date_from = int(
            (datetime.now(tz=UTC) - timedelta(days=ORDERS_SWEEP_WINDOW_DAYS)).timestamp()
        )
        next_token: int | None = None
        for _page in range(MAX_ORDERS_PAGES):
            try:
                page_rows, next_token = await fetch_marketplace_orders_page(
                    http_client,
                    api_token=api_token,
                    next_token=next_token,
                    date_from=sweep_date_from,
                    limit=ORDERS_SWEEP_PAGE_LIMIT,
                )
            except WildberriesClientError as exc:
                ref = wb_error_ref()
                log_wb_client_error(
                    logger,
                    "fbs orders WB page failed",
                    exc,
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    ref=ref,
                )
                error = _wb_orders_error_from_client(exc, ref=ref)
                code = error.code
                if import_stats.received:
                    orders_page_error = code
                    await session.rollback()
                    break
                raise error from exc

            if not page_rows:
                break
            await import_wb_order_rows(
                session, tenant_id, seller_id, page_rows, import_stats
            )
            await session.commit()
            if next_token is None:
                break

    statuses_updated = 0
    if include_history and orders_page_error is None:
        try:
            statuses_updated = await sync_order_statuses(
                session,
                tenant_id,
                seller_id,
                http_client,
                api_token,
                actor_user_id=None,
            )
            await session.commit()
        except WbMarketplaceOrdersError as exc:
            await session.rollback()
            if not import_stats.received:
                raise
            status_sync_error = exc.code
        if status_sync_error is None:
            try:
                supply_link_result = await link_confirmed_orders_to_wb_supplies(
                    session, tenant_id, seller_id, http_client, api_token
                )
                await session.commit()
            except Exception as exc:
                await session.rollback()
                logger.exception(
                    "wb supply link failed: seller=%s step=local error=%s",
                    seller_id,
                    type(exc).__name__,
                )
                supply_link_result = _empty_supply_link_result(
                    supply_link_error="local_exception",
                )

    result: dict[str, Any] = {
        "seller_id": str(seller_id),
        "orders_received": import_stats.received,
        "orders_upserted": import_stats.upserted,
        "orders_created": import_stats.created,
        "orders_skipped_unserved": import_stats.skipped_unserved,
        "statuses_updated": statuses_updated,
    }
    result.update(supply_link_result)
    if orders_page_error is not None:
        result["orders_page_error"] = orders_page_error
    if status_sync_error is not None:
        result["status_sync_error"] = status_sync_error
    return result


async def list_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[FbsOrder]:
    stmt = select(FbsOrder).where(FbsOrder.tenant_id == tenant_id)
    if seller_id is not None:
        stmt = stmt.where(FbsOrder.seller_id == seller_id)
    stmt = stmt.order_by(FbsOrder.created_at_wb.desc()).limit(limit).offset(offset)
    res = await session.execute(stmt)
    return list(res.scalars().all())
