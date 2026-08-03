"""WB Marketplace FBS orders: sync, map products, reserve stock, status updates."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import (
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_DEFECT,
    FBS_ORDER_STATUS_DONE,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_NEW,
    FBS_ORDER_STATUS_SORTED,
    MAPPING_STATUS_MAPPED,
    MAPPING_STATUS_MISSING,
    RESERVE_STATUS_NO_STOCK,
    RESERVE_STATUS_RELEASED,
    RESERVE_STATUS_RESERVED,
    RESERVE_STATUS_SKIPPED_NO_PRODUCT,
    RESERVE_STATUS_WAREHOUSE_UNMAPPED,
    FbsOrder,
    FbsOrderReservation,
)
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product import Product
from app.services.fbs_stock_availability_service import fbs_available_qty_for_product
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

FBS_DEADLINE_HOURS = 120
MAX_ORDERS_PAGES = 10

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

STATUSES_EXCLUDED_FROM_WB_SYNC = TERMINAL_FBS_STATUSES | frozenset(
    {FBS_ORDER_STATUS_SORTED}
)

SYNC_STATUS_BATCH_SIZE = 500
MAX_SYNC_STATUS_BATCHES = 20


class WbMarketplaceOrdersError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
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


def _wb_status_from_row(row: dict[str, Any]) -> str | None:
    for key in ("wbStatus", "supplierStatus", "status"):
        val = row.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip().lower()
    return None


def _is_cancel_like_wb_status(wb_status: str) -> bool:
    return wb_status.strip().lower() in CANCEL_LIKE_WB_STATUSES


def _is_cancelled_wb_row(row: dict[str, Any]) -> bool:
    wb_status = _wb_status_from_row(row)
    return wb_status is not None and _is_cancel_like_wb_status(wb_status)


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
    """max(0, storage + sorting - outbound - FBS); FBO/MP unload not subtracted."""
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
    stmt = select(FbsWarehouseBinding.wms_warehouse_id).where(
        FbsWarehouseBinding.tenant_id == tenant_id,
        FbsWarehouseBinding.seller_id == seller_id,
        FbsWarehouseBinding.wb_warehouse_id == wb_warehouse_id,
        FbsWarehouseBinding.is_active.is_(True),
    ).with_for_update()
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


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
    """Map WB warehouse to local WMS warehouse via active seller binding."""
    resolved = await _resolve_wms_warehouse_from_binding(
        session, tenant_id, seller_id, wb_warehouse_id
    )
    if resolved is None:
        if order.warehouse_id is None:
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
    order.warehouse_id = resolved


async def _map_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    wb_barcode: str | None,
    wb_nm_id: int | None,
) -> Product | None:
    if wb_barcode:
        stmt = select(Product).where(
            Product.tenant_id == tenant_id,
            Product.seller_id == seller_id,
            Product.wb_barcode == wb_barcode,
        )
        res = await session.execute(stmt)
        product = res.scalar_one_or_none()
        if product is not None:
            return product
    if wb_nm_id is not None:
        stmt = select(Product).where(
            Product.tenant_id == tenant_id,
            Product.seller_id == seller_id,
            Product.wb_nm_id == wb_nm_id,
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()
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


async def _order_has_reservation(
    session: AsyncSession, order_id: uuid.UUID
) -> bool:
    stmt = select(FbsOrderReservation.id).where(
        FbsOrderReservation.fbs_order_id == order_id
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none() is not None


async def _lock_product_for_fbs_reserve(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
) -> None:
    stmt = (
        select(Product.id)
        .where(Product.id == product_id, Product.tenant_id == tenant_id)
        .with_for_update()
    )
    await session.execute(stmt)


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
    if order.wb_status is not None and order.wb_status.lower() in NO_RESERVE_WB_STATUSES:
        return
    if order.product_id is None:
        order.reserve_status = RESERVE_STATUS_SKIPPED_NO_PRODUCT
        return
    if order.warehouse_id is None:
        order.reserve_status = RESERVE_STATUS_WAREHOUSE_UNMAPPED
        return
    if await _order_has_reservation(session, order.id):
        return
    await _lock_product_for_fbs_reserve(session, order.tenant_id, order.product_id)
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


async def _release_reservation(session: AsyncSession, order: FbsOrder) -> None:
    stmt = select(FbsOrderReservation).where(
        FbsOrderReservation.fbs_order_id == order.id
    )
    res = await session.execute(stmt)
    reservation = res.scalar_one_or_none()
    if reservation is None:
        return
    await session.delete(reservation)
    order.reserve_status = RESERVE_STATUS_RELEASED


async def _apply_wb_row_to_existing(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    existing: FbsOrder,
    row: dict[str, Any],
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
) -> tuple[FbsOrder, bool]:
    """Returns (order, created)."""
    wb_order_id_raw = row.get("id")
    if wb_order_id_raw is None:
        raise WbMarketplaceOrdersError("missing_wb_order_id")
    wb_order_id = int(wb_order_id_raw)
    created_at_wb = _parse_wb_datetime(row.get("createdAt"))
    deadline_at = created_at_wb + timedelta(hours=FBS_DEADLINE_HOURS)
    wb_barcode = _first_barcode(row)
    wb_nm_id = row.get("nmId")
    wb_nm_id_int = int(wb_nm_id) if wb_nm_id is not None else None

    existing = await _get_order_by_wb_id(session, seller_id, wb_order_id)
    if existing is not None:
        await _apply_wb_row_to_existing(session, tenant_id, seller_id, existing, row)
        return existing, False

    product = await _map_product(
        session,
        tenant_id,
        seller_id,
        wb_barcode=wb_barcode,
        wb_nm_id=wb_nm_id_int,
    )
    mapping_status = MAPPING_STATUS_MAPPED if product is not None else MAPPING_STATUS_MISSING
    wb_warehouse_id = _wb_warehouse_id_from_row(row)
    wms_warehouse_id = await _resolve_wms_warehouse_from_binding(
        session, tenant_id, seller_id, wb_warehouse_id
    )
    if product is None:
        reserve_status = RESERVE_STATUS_SKIPPED_NO_PRODUCT
    elif wms_warehouse_id is None:
        reserve_status = RESERVE_STATUS_WAREHOUSE_UNMAPPED
    else:
        reserve_status = RESERVE_STATUS_NO_STOCK

    order = FbsOrder(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=wms_warehouse_id,
        product_id=product.id if product is not None else None,
        wb_order_id=wb_order_id,
        wb_rid=row.get("rid") if isinstance(row.get("rid"), str) else None,
        wb_nm_id=wb_nm_id_int,
        wb_chrt_id=int(row["chrtId"]) if row.get("chrtId") is not None else None,
        wb_article=str(row["article"]) if row.get("article") is not None else None,
        wb_barcode=wb_barcode,
        price=int(row["price"]) if row.get("price") is not None else None,
        is_legal=_is_legal_order(row),
        cargo_type=_cargo_type_label(row),
        wb_office_id=_wb_office_id_from_row(row),
        wb_warehouse_id=wb_warehouse_id,
        can_pvz=bool(row.get("canPvz") or row.get("isPvz")),
        status=FBS_ORDER_STATUS_NEW,
        created_at_wb=created_at_wb,
        deadline_at=deadline_at,
        mapping_status=mapping_status,
        reserve_status=reserve_status,
    )
    try:
        async with session.begin_nested():
            session.add(order)
            await session.flush()
            await _try_reserve_order(session, order)
    except IntegrityError:
        raced = await _get_order_by_wb_id(session, seller_id, wb_order_id)
        if raced is None:
            raise WbMarketplaceOrdersError("duplicate_order_race") from None
        await _apply_wb_row_to_existing(session, tenant_id, seller_id, raced, row)
        return raced, False
    return order, True


async def _apply_wb_status_to_order(
    session: AsyncSession,
    order: FbsOrder,
    wb_status: str,
) -> None:
    normalized = wb_status.strip().lower()
    order.wb_status = normalized
    if _is_cancel_like_wb_status(normalized):
        from app.services.fbs_cancellation_service import reverse_fbs_shipment_if_needed
        from app.services.fbs_packaging_integration_service import (
            detach_cancelled_order_from_supply,
        )

        order.status = FBS_ORDER_STATUS_CANCELLED
        await reverse_fbs_shipment_if_needed(session, order)
        await detach_cancelled_order_from_supply(session, order.tenant_id, order)
        await _release_reservation(session, order)
        return
    if normalized == "sold":
        order.status = FBS_ORDER_STATUS_DONE
        # Выкуплен: резерв больше не нужен (иначе available навсегда занижен).
        await _release_reservation(session, order)
        return
    if normalized == "sorted":
        order.status = FBS_ORDER_STATUS_SORTED
        return
    if normalized == DEFECT_WB_STATUS:
        order.status = FBS_ORDER_STATUS_DEFECT
        await _release_reservation(session, order)
        return
    if normalized == "waiting":
        if order.status != FBS_ORDER_STATUS_IN_DELIVERY:
            return
        return


async def sync_order_statuses(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    api_token: str,
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

        wb_ids = [o.wb_order_id for o in orders]
        try:
            status_rows = await fetch_marketplace_orders_status(
                http_client, api_token=api_token, order_ids=wb_ids
            )
        except WildberriesClientError as exc:
            suffix = f"_{exc.status_code}" if exc.status_code else ""
            raise WbMarketplaceOrdersError(f"wb_{exc.code}{suffix}") from exc

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
            if wb_status is None:
                continue
            await _apply_wb_status_to_order(session, order, wb_status)
            updated += 1

        last_row = orders[-1]
        last_created_at = last_row.created_at_wb
        last_id = last_row.id
        if len(orders) < SYNC_STATUS_BATCH_SIZE:
            break
    return updated


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
) -> dict[str, Any]:
    _ = warehouse_id  # ignored: WMS warehouse resolved per order via WB binding
    api_token = await _resolve_marketplace_api_token(session, tenant_id, seller_id)

    try:
        new_rows = await fetch_marketplace_orders_new(
            http_client, api_token=api_token
        )
    except WildberriesClientError as exc:
        suffix = f"_{exc.status_code}" if exc.status_code else ""
        raise WbMarketplaceOrdersError(f"wb_{exc.code}{suffix}") from exc

    created = 0
    upserted = 0
    orders_received = 0

    for row in new_rows:
        _order, was_created = await upsert_order_from_wb_row(
            session, tenant_id, seller_id, row
        )
        upserted += 1
        orders_received += 1
        if was_created:
            created += 1

    next_token: int | None = None
    for _page in range(MAX_ORDERS_PAGES):
        try:
            page_rows, next_token = await fetch_marketplace_orders_page(
                http_client,
                api_token=api_token,
                next_token=next_token,
            )
        except WildberriesClientError as exc:
            suffix = f"_{exc.status_code}" if exc.status_code else ""
            raise WbMarketplaceOrdersError(f"wb_{exc.code}{suffix}") from exc

        if not page_rows:
            break
        for row in page_rows:
            _order, was_created = await upsert_order_from_wb_row(
                session, tenant_id, seller_id, row
            )
            upserted += 1
            orders_received += 1
            if was_created:
                created += 1
        if next_token is None:
            break

    statuses_updated = await sync_order_statuses(
        session, tenant_id, seller_id, http_client, api_token
    )
    await session.commit()

    return {
        "seller_id": str(seller_id),
        "orders_received": orders_received,
        "orders_upserted": upserted,
        "orders_created": created,
        "statuses_updated": statuses_updated,
    }


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
