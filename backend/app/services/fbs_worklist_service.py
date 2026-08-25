"""FBS operator worklist: batched read model for orders (no N+1)."""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import String, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.models.fbs_order import (
    FBS_ORDER_STATUS_ASSEMBLING,
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_DEFECT,
    FBS_ORDER_STATUS_DONE,
    FBS_ORDER_STATUS_EXTERNAL_PROCESSING,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_IN_SUPPLY,
    FBS_ORDER_STATUS_NEW,
    FBS_ORDER_STATUS_PACKED,
    FBS_ORDER_STATUS_SORTED,
    MAPPING_STATUS_MISSING,
    FbsOrder,
    FbsOrderMarking,
    current_order_marking,
)
from app.models.fbs_order_pick import FbsOrderPick
from app.models.fbs_print_asset import (
    PRINT_ASSET_KIND_ORDER_STICKER,
    PRINT_ASSET_STATUS_READY,
    FbsPrintAsset,
)
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_reservation import InventoryReservation
from app.models.outbound_shipment import OutboundShipmentLine, OutboundShipmentRequest
from app.models.product import Product
from app.models.seller import Seller
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.storage_location import StorageLocation
from app.models.tenant_wb_mp_warehouse import TenantWbMpWarehouse
from app.models.warehouse import Warehouse
from app.services.fbs_stock_availability_service import fbs_available_qty_by_product
from app.services.inventory_service import OUTBOUND_RESERVE_STATUSES
from app.services.wb_card_enrichment import (
    color_from_card,
    first_photo_url_from_card,
    size_from_card_for_barcode,
    subject_name_from_card,
)

STATUS_GROUP_MAP: dict[str, frozenset[str]] = {
    "new": frozenset({FBS_ORDER_STATUS_NEW}),
    # BL-3 (16.08, FBS-03): заказы со статусом NEW, у которых истёк срок сборки
    # (deadline_at < server_now) — WB их уже не примет, но статус в БД остаётся "new",
    # WB его не меняет. Тот же набор статусов, что у "new" — реальное разделение идёт
    # по deadline_at в _fetch_orders_page/_fetch_warehouse_options, а не по статусу.
    # Тот же приём, что для "cancelled": отдельная вкладка через status_group,
    # без изменения данных в БД.
    "expired": frozenset({FBS_ORDER_STATUS_NEW}),
    "active": frozenset(
        {
            FBS_ORDER_STATUS_IN_SUPPLY,
            FBS_ORDER_STATUS_ASSEMBLING,
            FBS_ORDER_STATUS_PACKED,
            FBS_ORDER_STATUS_EXTERNAL_PROCESSING,
        }
    ),
    "delivery": frozenset({FBS_ORDER_STATUS_IN_DELIVERY, FBS_ORDER_STATUS_SORTED}),
    "done": frozenset({FBS_ORDER_STATUS_DONE}),
    # Решение пользователя 16.08 («сделай как в WB — отменённые заказы») + FBS-06
    # («убирает из "Новых" либо показывает в корректной вкладке»): отменённые и брак
    # раньше сваливались в "done" вместе с реально завершёнными — отвал был не виден.
    # Теперь у них своя группа, как отдельная вкладка «Отменённые» в кабинете WB.
    "cancelled": frozenset({FBS_ORDER_STATUS_CANCELLED, FBS_ORDER_STATUS_DEFECT}),
}

MISSING_WMS_WAREHOUSE = "Склад не привязан"
MISSING_WB_WAREHOUSE = "Склад WB неизвестен"
MISSING_PRODUCT = "Товар не сопоставлен"


def _is_supplier_status_new(supplier_status: str | None) -> bool:
    return supplier_status is None or supplier_status.strip().lower() == FBS_ORDER_STATUS_NEW


def _supplier_new_clause() -> ColumnElement[bool]:
    return or_(
        FbsOrder.supplier_status.is_(None),
        func.lower(FbsOrder.supplier_status) == FBS_ORDER_STATUS_NEW,
    )


@dataclass(frozen=True)
class WorklistPage:
    items: list[dict[str, Any]]
    next_cursor: str | None
    server_now: str
    warehouse_options: list[dict[str, Any]]


@dataclass(frozen=True)
class _LocationBalanceRow:
    product_id: uuid.UUID
    location_id: uuid.UUID
    location_code: str
    available_unpacked: int


def print_asset_content_url(asset_id: uuid.UUID) -> str:
    return f"/operations/fbs-print-assets/{asset_id}/content"


def _encode_cursor(deadline_at: datetime, order_id: uuid.UUID) -> str:
    payload = {"d": deadline_at.isoformat(), "i": str(order_id)}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        payload = json.loads(raw.decode())
        deadline = datetime.fromisoformat(str(payload["d"]))
        order_id = uuid.UUID(str(payload["i"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        msg = "invalid_cursor"
        raise ValueError(msg) from exc
    return deadline, order_id


async def fetch_worklist_page(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None = None,
    marketplace: str | None = None,
    status_group: str | None = None,
    wb_warehouse_id: int | None = None,
    search: str | None = None,
    limit: int = 100,
    cursor: str | None = None,
) -> WorklistPage:
    server_now = datetime.now(tz=UTC)
    orders = await _fetch_orders_page(
        session,
        tenant_id,
        seller_id=seller_id,
        marketplace=marketplace,
        status_group=status_group,
        wb_warehouse_id=wb_warehouse_id,
        search=search,
        limit=limit,
        cursor=cursor,
        server_now=server_now,
    )
    items = await build_worklist_items(session, tenant_id, orders, server_now=server_now)
    warehouse_options = await _fetch_warehouse_options(
        session,
        tenant_id,
        seller_id=seller_id,
        status_group=status_group,
        server_now=server_now,
    )
    next_cursor: str | None = None
    if len(orders) == limit:
        last = orders[-1]
        next_cursor = _encode_cursor(last.deadline_at, last.id)
    return WorklistPage(
        items=items,
        next_cursor=next_cursor,
        server_now=server_now.isoformat(),
        warehouse_options=warehouse_options,
    )


async def _fetch_orders_page(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None,
    marketplace: str | None,
    status_group: str | None,
    wb_warehouse_id: int | None,
    search: str | None,
    limit: int,
    cursor: str | None,
    server_now: datetime,
) -> list[FbsOrder]:
    stmt = select(FbsOrder).where(FbsOrder.tenant_id == tenant_id)
    if seller_id is not None:
        stmt = stmt.where(FbsOrder.seller_id == seller_id)
    if marketplace is not None:
        stmt = stmt.where(FbsOrder.marketplace == marketplace)
    if status_group:
        allowed = STATUS_GROUP_MAP.get(status_group)
        if allowed is None:
            msg = "invalid_status_group"
            raise ValueError(msg)
        stmt = stmt.where(FbsOrder.status.in_(allowed))
        if status_group == "new":
            stmt = stmt.where(_supplier_new_clause())
            # BL-3: "Новые" показывают только заказы, которые WB ещё реально примет.
            stmt = stmt.where(FbsOrder.deadline_at >= server_now)
        elif status_group == "expired":
            stmt = stmt.where(_supplier_new_clause())
            # BL-3: "Просрочены" — зеркало "new", но с истёкшим дедлайном.
            stmt = stmt.where(FbsOrder.deadline_at < server_now)
    if wb_warehouse_id is not None:
        stmt = stmt.where(FbsOrder.wb_warehouse_id == wb_warehouse_id)
    if search and search.strip():
        term = search.strip()
        stmt = stmt.outerjoin(Product, Product.id == FbsOrder.product_id).outerjoin(
            SellerWildberriesImportedCard,
            and_(
                SellerWildberriesImportedCard.tenant_id == FbsOrder.tenant_id,
                SellerWildberriesImportedCard.seller_id == FbsOrder.seller_id,
                SellerWildberriesImportedCard.nm_id == FbsOrder.wb_nm_id,
            ),
        )
        clauses: list[ColumnElement[bool]] = [
            FbsOrder.wb_barcode.ilike(f"%{term}%"),
            FbsOrder.wb_article.ilike(f"%{term}%"),
            Product.name.ilike(f"%{term}%"),
            Product.sku_code.ilike(f"%{term}%"),
            Product.wb_vendor_code.ilike(f"%{term}%"),
            Product.wb_barcode.ilike(f"%{term}%"),
            Product.wb_size.ilike(f"%{term}%"),
            SellerWildberriesImportedCard.title.ilike(f"%{term}%"),
            SellerWildberriesImportedCard.vendor_code.ilike(f"%{term}%"),
            SellerWildberriesImportedCard.raw_json.cast(String).ilike(f"%{term}%"),
        ]
        if term.isdigit():
            term_num = int(term)
            clauses.extend(
                [
                    FbsOrder.wb_order_id == term_num,
                    FbsOrder.wb_nm_id == term_num,
                    FbsOrder.wb_chrt_id == term_num,
                    Product.wb_nm_id == term_num,
                    Product.wb_chrt_id == term_num,
                ]
            )
        stmt = stmt.where(or_(*clauses))
    if cursor:
        cursor_deadline, cursor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                FbsOrder.deadline_at > cursor_deadline,
                and_(
                    FbsOrder.deadline_at == cursor_deadline,
                    FbsOrder.id > cursor_id,
                ),
            )
        )
    stmt = stmt.order_by(FbsOrder.deadline_at.asc(), FbsOrder.id.asc()).limit(limit)
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def _fetch_warehouse_options(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None,
    status_group: str | None,
    server_now: datetime,
) -> list[dict[str, Any]]:
    stmt = (
        select(
            FbsOrder.wb_warehouse_id,
            TenantWbMpWarehouse.name,
        )
        .distinct()
        .outerjoin(
            TenantWbMpWarehouse,
            and_(
                TenantWbMpWarehouse.tenant_id == FbsOrder.tenant_id,
                TenantWbMpWarehouse.wb_warehouse_id == FbsOrder.wb_warehouse_id,
            ),
        )
        .where(
            FbsOrder.tenant_id == tenant_id,
            FbsOrder.wb_warehouse_id.is_not(None),
        )
    )
    if seller_id is not None:
        stmt = stmt.where(FbsOrder.seller_id == seller_id)
    if status_group:
        allowed = STATUS_GROUP_MAP[status_group]
        stmt = stmt.where(FbsOrder.status.in_(allowed))
        if status_group == "new":
            stmt = stmt.where(_supplier_new_clause())
            stmt = stmt.where(FbsOrder.deadline_at >= server_now)
        elif status_group == "expired":
            stmt = stmt.where(_supplier_new_clause())
            stmt = stmt.where(FbsOrder.deadline_at < server_now)
    stmt = stmt.order_by(TenantWbMpWarehouse.name.asc(), FbsOrder.wb_warehouse_id.asc())
    res = await session.execute(stmt)
    options: dict[str, dict[str, Any]] = {}
    for wb_id, wb_name in res.all():
        if wb_id is None:
            continue
        wb_id_int = int(wb_id)
        key = str(wb_id_int)
        label = (
            wb_name.strip()
            if isinstance(wb_name, str) and wb_name.strip()
            else f"WB {wb_id_int}"
        )
        options.setdefault(
            key,
            {
                "id": key,
                "name": label,
                "wb_warehouse": {
                    "id": wb_id_int,
                    "name": label,
                },
            },
        )
    return list(options.values())


async def build_worklist_items(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    orders: list[FbsOrder],
    *,
    server_now: datetime | None = None,
) -> list[dict[str, Any]]:
    if not orders:
        return []
    now = server_now or datetime.now(tz=UTC)
    ctx = await _load_worklist_context(session, tenant_id, orders)
    return [_map_order(order, ctx, now) for order in orders]


async def _load_worklist_context(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    orders: list[FbsOrder],
) -> dict[str, Any]:
    seller_ids = {o.seller_id for o in orders}
    warehouse_ids = {o.warehouse_id for o in orders if o.warehouse_id is not None}
    product_ids = {o.product_id for o in orders if o.product_id is not None}
    order_ids = [o.id for o in orders]
    wb_wh_ids = {int(o.wb_warehouse_id) for o in orders if o.wb_warehouse_id is not None}
    seller_nm_pairs: set[tuple[uuid.UUID, int]] = set()
    for o in orders:
        if o.seller_id and o.wb_nm_id is not None:
            seller_nm_pairs.add((o.seller_id, int(o.wb_nm_id)))

    sellers = await _load_sellers(session, tenant_id, seller_ids)
    warehouses = await _load_warehouses(session, tenant_id, warehouse_ids)
    wb_names = await _load_wb_warehouse_names(session, tenant_id, wb_wh_ids)
    products = await _load_products(session, tenant_id, product_ids)
    cards = await _load_imported_cards(session, tenant_id, seller_nm_pairs)
    availability = await _load_availability_by_warehouse_product(
        session, tenant_id, orders
    )
    locations = await _load_location_balances(session, tenant_id, orders)
    markings = await _load_markings(session, order_ids)
    picks = await _load_active_picks(session, tenant_id, order_ids)
    sticker_assets = await _load_sticker_assets(session, tenant_id, order_ids)
    return {
        "sellers": sellers,
        "warehouses": warehouses,
        "wb_names": wb_names,
        "products": products,
        "cards": cards,
        "availability": availability,
        "locations": locations,
        "markings": markings,
        "picks": picks,
        "sticker_assets": sticker_assets,
    }


async def _load_sellers(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_ids: set[uuid.UUID],
) -> dict[uuid.UUID, Seller]:
    if not seller_ids:
        return {}
    stmt = select(Seller).where(
        Seller.tenant_id == tenant_id,
        Seller.id.in_(seller_ids),
    )
    res = await session.execute(stmt)
    return {s.id: s for s in res.scalars().all()}


async def _load_warehouses(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_ids: set[uuid.UUID],
) -> dict[uuid.UUID, Warehouse]:
    if not warehouse_ids:
        return {}
    stmt = select(Warehouse).where(
        Warehouse.tenant_id == tenant_id,
        Warehouse.id.in_(warehouse_ids),
    )
    res = await session.execute(stmt)
    return {w.id: w for w in res.scalars().all()}


async def _load_wb_warehouse_names(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    wb_warehouse_ids: set[int],
) -> dict[int, str | None]:
    if not wb_warehouse_ids:
        return {}
    stmt = select(TenantWbMpWarehouse).where(
        TenantWbMpWarehouse.tenant_id == tenant_id,
        TenantWbMpWarehouse.wb_warehouse_id.in_(wb_warehouse_ids),
    )
    res = await session.execute(stmt)
    return {int(r.wb_warehouse_id): r.name for r in res.scalars().all()}


async def _load_products(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_ids: set[uuid.UUID],
) -> dict[uuid.UUID, Product]:
    if not product_ids:
        return {}
    stmt = select(Product).where(
        Product.tenant_id == tenant_id,
        Product.id.in_(product_ids),
    )
    res = await session.execute(stmt)
    return {p.id: p for p in res.scalars().all()}


async def _load_imported_cards(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_nm_pairs: set[tuple[uuid.UUID, int]],
) -> dict[tuple[uuid.UUID, int], SellerWildberriesImportedCard]:
    if not seller_nm_pairs:
        return {}
    seller_ids = {s for s, _ in seller_nm_pairs}
    nm_ids = {n for _, n in seller_nm_pairs}
    stmt = select(SellerWildberriesImportedCard).where(
        SellerWildberriesImportedCard.tenant_id == tenant_id,
        SellerWildberriesImportedCard.seller_id.in_(seller_ids),
        SellerWildberriesImportedCard.nm_id.in_(nm_ids),
    )
    res = await session.execute(stmt)
    out: dict[tuple[uuid.UUID, int], SellerWildberriesImportedCard] = {}
    for card in res.scalars().all():
        key = (card.seller_id, int(card.nm_id))
        if key in seller_nm_pairs:
            out[key] = card
    return out


async def _load_availability_by_warehouse_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    orders: list[FbsOrder],
) -> dict[tuple[uuid.UUID, uuid.UUID], int]:
    by_wh: dict[uuid.UUID, set[uuid.UUID]] = {}
    exclude_by_wh: dict[uuid.UUID, set[uuid.UUID]] = {}
    for o in orders:
        if o.warehouse_id is None or o.product_id is None:
            continue
        by_wh.setdefault(o.warehouse_id, set()).add(o.product_id)
        exclude_by_wh.setdefault(o.warehouse_id, set()).add(o.id)
    result: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
    for wh_id, pids in by_wh.items():
        qty_map = await fbs_available_qty_by_product(
            session,
            tenant_id,
            wh_id,
            list(pids),
            exclude_fbs_order_ids=frozenset(exclude_by_wh.get(wh_id, set())),
        )
        for pid, qty in qty_map.items():
            result[(wh_id, pid)] = int(qty)
    return result


async def _load_location_balances(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    orders: list[FbsOrder],
) -> dict[tuple[uuid.UUID, uuid.UUID], list[_LocationBalanceRow]]:
    by_wh: dict[uuid.UUID, set[uuid.UUID]] = {}
    for o in orders:
        if o.warehouse_id is None or o.product_id is None:
            continue
        by_wh.setdefault(o.warehouse_id, set()).add(o.product_id)
    result: dict[tuple[uuid.UUID, uuid.UUID], list[_LocationBalanceRow]] = {}
    for wh_id, pids in by_wh.items():
        pid_list = list(pids)
        bal_stmt = (
            select(
                InventoryBalance.product_id,
                StorageLocation.id,
                StorageLocation.code,
                InventoryBalance.quantity_unpacked,
            )
            .join(
                StorageLocation,
                StorageLocation.id == InventoryBalance.storage_location_id,
            )
            .where(
                InventoryBalance.tenant_id == tenant_id,
                StorageLocation.tenant_id == tenant_id,
                StorageLocation.warehouse_id == wh_id,
                InventoryBalance.product_id.in_(pid_list),
                InventoryBalance.quantity_unpacked > 0,
            )
            .order_by(StorageLocation.code.asc())
        )
        bal_res = await session.execute(bal_stmt)
        balance_rows = list(bal_res.all())
        if not balance_rows:
            continue
        loc_ids = {loc_id for _, loc_id, _, _ in balance_rows}
        rsv_stmt = (
            select(
                InventoryReservation.product_id,
                InventoryReservation.storage_location_id,
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
                InventoryReservation.storage_location_id.in_(loc_ids),
                InventoryReservation.product_id.in_(pid_list),
                OutboundShipmentRequest.status.in_(OUTBOUND_RESERVE_STATUSES),
            )
            .group_by(
                InventoryReservation.product_id,
                InventoryReservation.storage_location_id,
            )
        )
        rsv_res = await session.execute(rsv_stmt)
        reserved: dict[tuple[uuid.UUID, uuid.UUID], int] = {
            (pid, loc_id): int(qty or 0) for pid, loc_id, qty in rsv_res.all()
        }
        for pid, loc_id, code, unpacked in balance_rows:
            avail = max(0, int(unpacked) - reserved.get((pid, loc_id), 0))
            if avail <= 0:
                continue
            key = (wh_id, pid)
            result.setdefault(key, []).append(
                _LocationBalanceRow(
                    product_id=pid,
                    location_id=loc_id,
                    location_code=str(code),
                    available_unpacked=avail,
                )
            )
    return result


async def _load_markings(
    session: AsyncSession,
    order_ids: list[uuid.UUID],
) -> dict[uuid.UUID, list[FbsOrderMarking]]:
    if not order_ids:
        return {}
    stmt = select(FbsOrderMarking).where(FbsOrderMarking.order_id.in_(order_ids))
    res = await session.execute(stmt)
    out: dict[uuid.UUID, list[FbsOrderMarking]] = {}
    for m in res.scalars().all():
        out.setdefault(m.order_id, []).append(m)
    return out


async def _load_active_picks(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_ids: list[uuid.UUID],
) -> dict[uuid.UUID, FbsOrderPick]:
    if not order_ids:
        return {}
    stmt = (
        select(FbsOrderPick)
        .options(selectinload(FbsOrderPick.source_storage_location))
        .where(
            FbsOrderPick.tenant_id == tenant_id,
            FbsOrderPick.fbs_order_id.in_(order_ids),
            FbsOrderPick.undone_at.is_(None),
        )
    )
    res = await session.execute(stmt)
    return {p.fbs_order_id: p for p in res.scalars().all()}


async def _load_sticker_assets(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_ids: list[uuid.UUID],
) -> dict[uuid.UUID, FbsPrintAsset]:
    if not order_ids:
        return {}
    stmt = select(FbsPrintAsset).where(
        FbsPrintAsset.tenant_id == tenant_id,
        FbsPrintAsset.fbs_order_id.in_(order_ids),
        FbsPrintAsset.kind == PRINT_ASSET_KIND_ORDER_STICKER,
        FbsPrintAsset.status == PRINT_ASSET_STATUS_READY,
    )
    res = await session.execute(stmt)
    out: dict[uuid.UUID, FbsPrintAsset] = {}
    for asset in res.scalars().all():
        if asset.fbs_order_id is not None:
            out[asset.fbs_order_id] = asset
    return out


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def compute_selection_blockers(
    order: FbsOrder,
    *,
    available_unpacked: int,
    server_now: datetime,
) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    if order.status in {FBS_ORDER_STATUS_CANCELLED, FBS_ORDER_STATUS_DEFECT}:
        blockers.append(
            {"code": "order_cancelled", "message": "Заказ отменён или брак."}
        )
    if not _is_supplier_status_new(order.supplier_status):
        blockers.append(
            {
                "code": "order_external_processing",
                "message": "Заказ уже ушёл в кабинете WB.",
            }
        )
    if order.supply_id is not None:
        blockers.append(
            {"code": "already_in_supply", "message": "Заказ уже в поставке."}
        )
    if order.mapping_status == MAPPING_STATUS_MISSING or order.product_id is None:
        blockers.append(
            {"code": "product_not_mapped", "message": "Товар не сопоставлен с карточкой."}
        )
    if order.warehouse_id is None:
        blockers.append(
            {
                "code": "warehouse_unmapped",
                "message": "Склад WB не привязан к WMS — привяжите его на вкладке «Остатки WB».",
            }
        )
    if _as_utc(order.deadline_at) < _as_utc(server_now):
        blockers.append(
            {"code": "deadline_passed", "message": "Срок сборки истёк."}
        )
    return blockers


def _map_order(order: FbsOrder, ctx: dict[str, Any], server_now: datetime) -> dict[str, Any]:
    seller = ctx["sellers"].get(order.seller_id)
    warehouse = (
        ctx["warehouses"].get(order.warehouse_id) if order.warehouse_id else None
    )
    wb_wh_id = int(order.wb_warehouse_id) if order.wb_warehouse_id is not None else 0
    wb_name = ctx["wb_names"].get(wb_wh_id) if wb_wh_id else None
    product = ctx["products"].get(order.product_id) if order.product_id else None
    card = None
    if order.seller_id and order.wb_nm_id is not None:
        card = ctx["cards"].get((order.seller_id, int(order.wb_nm_id)))
    card_raw = card.raw_json if card and isinstance(card.raw_json, dict) else None
    barcode = order.wb_barcode or (product.wb_barcode if product else None)
    image_url = first_photo_url_from_card(card_raw) if card_raw else None
    category = subject_name_from_card(card_raw) if card_raw else None
    color = color_from_card(card_raw) if card_raw else None
    size = None
    if product and product.wb_size:
        size = product.wb_size
    elif card_raw:
        size = size_from_card_for_barcode(card_raw, barcode)
    avail_key = (order.warehouse_id, order.product_id)
    available = 0
    loc_rows: list[_LocationBalanceRow] = []
    if order.warehouse_id and order.product_id:
        available = int(ctx["availability"].get(avail_key, 0))
        loc_rows = ctx["locations"].get(avail_key, [])
    markings = ctx["markings"].get(order.id, [])
    pick_row = ctx["picks"].get(order.id)
    sticker_asset = ctx["sticker_assets"].get(order.id)
    sticker_url = (
        print_asset_content_url(sticker_asset.id) if sticker_asset is not None else None
    )
    applied_at = order.sticker_applied_at or (
        sticker_asset.applied_at if sticker_asset else None
    )
    pick_location = None
    if pick_row and pick_row.source_storage_location is not None:
        pick_location = pick_row.source_storage_location.code
    picked_at = order.picked_at or (pick_row.picked_at if pick_row else None)
    return {
        "id": str(order.id),
        "marketplace": order.marketplace,
        "external_order_id": order.external_order_id,
        "wb_order_id": int(order.wb_order_id),
        "status": order.status,
        "wb_status": order.wb_status,
        "supplier_status": order.supplier_status,
        "seller": {
            "id": str(order.seller_id),
            "name": seller.name if seller else "Селлер не найден",
        },
        "wb_warehouse": {
            "id": wb_wh_id,
            "name": wb_name if wb_name else MISSING_WB_WAREHOUSE,
        },
        "wms_warehouse": {
            "id": str(order.warehouse_id) if order.warehouse_id else "",
            "name": warehouse.name if warehouse else MISSING_WMS_WAREHOUSE,
        },
        "product": {
            "id": str(order.product_id) if order.product_id else None,
            "name": product.name if product else MISSING_PRODUCT,
            "image_url": image_url,
            "seller_article": (
                product.wb_vendor_code
                if product and product.wb_vendor_code
                else order.wb_article
            ),
            "wb_article": int(order.wb_nm_id) if order.wb_nm_id is not None else None,
            "barcode": barcode,
            "sku": product.sku_code if product else None,
            "chrt_id": (
                int(order.wb_chrt_id)
                if order.wb_chrt_id is not None
                else int(product.wb_chrt_id)
                if product and product.wb_chrt_id is not None
                else None
            ),
            "category": category,
            "color": color,
            "size": size,
            "packaging_instructions": product.packaging_instructions if product else None,
            "has_packaging_instructions": bool(
                product
                and product.packaging_instructions
                and product.packaging_instructions.strip()
            ),
        },
        "inventory": {
            "available_unpacked": available,
            "locations": [
                {
                    "id": str(row.location_id),
                    "code": row.location_code,
                    "available_unpacked": row.available_unpacked,
                }
                for row in loc_rows
            ],
        },
        "buyer_type": "legal" if order.is_legal else "individual",
        "cargo_type": order.cargo_type or "unknown",
        "can_pvz": bool(order.can_pvz),
        "metadata": _build_metadata(order, markings),
        "sticker": {
            "code": order.sticker_code,
            "status": order.sticker_status,
            "asset_url": sticker_url,
            "applied_at": applied_at.isoformat() if applied_at else None,
        },
        "pick": {
            "status": order.pick_status,
            "location_code": pick_location,
            "picked_at": picked_at.isoformat() if picked_at else None,
        },
        "pack": {
            "status": order.pack_status,
            "packed_at": order.packed_at.isoformat() if order.packed_at else None,
        },
        "created_at_wb": order.created_at_wb.isoformat(),
        "deadline_at": order.deadline_at.isoformat(),
        "supply_id": str(order.supply_id) if order.supply_id else None,
        "selection_blockers": compute_selection_blockers(
            order,
            available_unpacked=available,
            server_now=server_now,
        ),
    }


def _marking_value_tail(value: str | None, length: int = 8) -> str | None:
    """Последние символы кода маркировки — опознавательный хвост для оператора."""
    if not value:
        return None
    cleaned = value.strip()
    return cleaned[-length:] if len(cleaned) > length else cleaned


def _build_metadata(
    order: FbsOrder,
    markings: list[FbsOrderMarking],
) -> dict[str, Any]:
    required = list(order.required_meta_json or [])
    optional = list(order.optional_meta_json or [])
    states: list[dict[str, Any]] = []
    for kind in required + optional:
        mark = current_order_marking(markings, kind, include_rejected=True)
        if mark is not None:
            states.append(
                {
                    "kind": kind,
                    "status": mark.meta_status,
                    "reason": mark.reason,
                    "source": mark.source,
                    # Хвост кода: оператор сверяет его глазами с этикеткой на товаре.
                    # Целиком код в строку таблицы не влезает и читать его незачем.
                    "value_tail": _marking_value_tail(mark.value),
                }
            )
        else:
            states.append(
                {
                    "kind": kind,
                    "status": "missing",
                    "reason": None,
                    "source": None,
                    "value_tail": None,
                }
            )
    delivery_allowed = (
        bool(order.metadata_delivery_allowed)
        if order.metadata_delivery_allowed is not None
        else False
    )
    return {
        "required": required,
        "optional": optional,
        "states": states,
        "delivery_allowed": delivery_allowed,
        "last_checked_at": (
            order.metadata_last_checked_at.isoformat()
            if order.metadata_last_checked_at
            else None
        ),
    }
