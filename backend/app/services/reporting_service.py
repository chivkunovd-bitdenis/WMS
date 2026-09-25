from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from openpyxl import Workbook  # type: ignore[import-untyped]
from openpyxl.utils import get_column_letter  # type: ignore[import-untyped]
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from app.models.background_job import BackgroundJob
from app.models.fbs_order import FbsOrder
from app.models.fbs_order_pick import FbsOrderPick, FbsOrderPickEvent
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_count import InventoryCountLine
from app.models.inventory_movement import (
    MOVEMENT_TYPE_DISCREPANCY_ACT,
    MOVEMENT_TYPE_FBS_SHIPMENT,
    MOVEMENT_TYPE_INBOUND_INTAKE,
    InventoryMovement,
)
from app.models.marketplace_unload import MarketplaceUnloadRequest
from app.models.outbound_shipment import OutboundShipmentLine
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.services.inventory_movement_report_service import (
    REPORT_MOVEMENT_TYPE_GROUPS,
    load_report_photo_urls,
    movement_group_label,
)
from app.services.ownership_transfer_service import (
    MOVEMENT_TYPE_OWNERSHIP_IN,
    MOVEMENT_TYPE_OWNERSHIP_OUT,
    MOVEMENT_TYPE_OWNERSHIP_RECEIPT,
)

# WMS-530/531. Остаток и расположение — разные понятия (AGENTS.md, §3). Эти движения
# только перекладывают товар между складами, ячейками и тарой: остаток они не
# меняют и приходом или расходом в отчёте не считаются ни при каком фильтре, и
# строками в раскрытии не показываются вовсе (WMS-531 R1).
LOCATION_ONLY_MOVEMENT_TYPES = (
    "stock_transfer_in",
    "stock_transfer_out",
    "warehouse_map_move",
    "container_reattach",
    "transfer",
)
# Пары движений расположения, где обе стороны пишутся одним и тем же
# movement_type (перевешивание тары, перенос по карте склада, историческое
# «transfer»). Только stock_transfer различает вход/выход по типу.
_SAME_TYPE_PAIR_TYPES = frozenset({"warehouse_map_move", "container_reattach", "transfer"})
_STOCK_TRANSFER_PAIR_TYPES = frozenset({"stock_transfer_in", "stock_transfer_out"})


def stock_movement_filter() -> ColumnElement[bool]:
    """Только движения, которые меняют остаток, а не расположение."""
    return InventoryMovement.movement_type.not_in(LOCATION_ONLY_MOVEMENT_TYPES)


PAGE_SIZE = 50
MOVEMENT_PAGE_LIMIT = 200
GROUP_BY_VALUES = {"product", "operation", "seller"}
PRODUCT_SORTS = {"name", "sku", "in_qty", "out_qty", "net"}
OPERATION_SORTS = {"operation", "in_qty", "out_qty", "net"}
# Селлер — верхний уровень отчёта: менеджер сначала смотрит, кто сколько принёс
# и увёз, и только потом раскрывает товары внутри одного селлера.
SELLER_SORTS = {"name", "in_qty", "out_qty", "net", "products"}
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
WB_IMPORT_JOB_TYPES = frozenset(
    {"wildberries_cards_sync", "wildberries_supplies_sync", "wildberries_marketplace_orders_sync"}
)


def validate_period(date_from: datetime, date_to: datetime) -> None:
    if date_to <= date_from:
        raise ValueError("date_to must be after date_from")
    if date_to - date_from > timedelta(days=366):
        raise ValueError("period cannot be longer than 366 days")


def normalize_period(date_from: datetime, date_to: datetime) -> tuple[datetime, datetime]:
    """Interpret offset-less calendar boundaries as Moscow time, then compare in UTC."""
    if date_from.tzinfo is None:
        date_from = date_from.replace(tzinfo=MOSCOW_TZ)
    if date_to.tzinfo is None:
        date_to = date_to.replace(tzinfo=MOSCOW_TZ)
    date_from = date_from.astimezone(UTC)
    date_to = date_to.astimezone(UTC)
    validate_period(date_from, date_to)
    return date_from, date_to


def validated_sort(
    group_by: str, sort_by: str | None, sort_order: str
) -> tuple[str, str]:
    if group_by not in GROUP_BY_VALUES:
        raise ValueError("group_by must be product, operation or seller")
    allowed_sorts = {
        "product": PRODUCT_SORTS, "operation": OPERATION_SORTS, "seller": SELLER_SORTS,
    }[group_by]
    resolved_sort = sort_by or ("operation" if group_by == "operation" else "name")
    if resolved_sort not in allowed_sorts:
        raise ValueError("unsupported sort_by")
    if sort_order not in {"asc", "desc"}:
        raise ValueError("sort_order must be asc or desc")
    return resolved_sort, sort_order


def product_search_filter(tenant_id: uuid.UUID, search: str) -> ColumnElement[bool]:
    """One product scope for report rows, exports, balances and overview totals."""
    pattern = f"%{search.strip()}%"
    marketplace_match = select(ProductMarketplaceLink.product_id).where(
        ProductMarketplaceLink.tenant_id == tenant_id,
        ProductMarketplaceLink.is_active.is_(True),
        or_(
            ProductMarketplaceLink.external_sku.ilike(pattern),
            ProductMarketplaceLink.external_offer_id.ilike(pattern),
        ),
    )
    return or_(
        Product.name.ilike(pattern), Product.sku_code.ilike(pattern),
        Product.wb_vendor_code.ilike(pattern), Product.wb_barcode.ilike(pattern),
        Product.id.in_(marketplace_match),
    )


def _product_scope_filters(
    tenant_id: uuid.UUID, seller_id: uuid.UUID | None, search: str | None
) -> list[ColumnElement[bool]]:
    """Товарный контур строки отчёта — Продукт, а не снимок движения (WMS-531 R10).

    Селлера и поиск фильтруем через ТЕКУЩЕГО владельца товара (`Product.seller_id`),
    а не через `InventoryMovement.seller_id`: последнее поле — снимок на момент
    движения и при передаче между селлерами не совпадает с тем, у кого товар
    числится сейчас. Отчёт обязан сходиться по текущему селлеру (R7, R10).
    """
    filters: list[ColumnElement[bool]] = [Product.tenant_id == tenant_id]
    if seller_id is not None:
        filters.append(Product.seller_id == seller_id)
    if search:
        filters.append(product_search_filter(tenant_id, search))
    return filters


# ---------------------------------------------------------------------------
# WMS-531 R6-R9. Остаток на начало/конец периода и приход/расход по товару.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProductPeriodFigures:
    opening_balance: int
    in_qty: int
    out_qty: int
    closing_balance: int

    @property
    def net(self) -> int:
        return self.in_qty - self.out_qty


@dataclass
class _SellerAgg:
    """Накопитель строки селлера — типизированная замена dict[str, object],
    чтобы mypy не спотыкался об `int(object)` на каждом сложении (WMS-531)."""

    seller_id: str
    seller_name: str
    product_count: int = 0
    opening_balance: int = 0
    total_in: int = 0
    total_out: int = 0
    closing_balance: int = 0

    @property
    def net(self) -> int:
        return self.total_in - self.total_out

    def as_dict(self) -> dict[str, object]:
        return {
            "seller_id": self.seller_id, "seller_name": self.seller_name,
            "product_count": self.product_count, "opening_balance": self.opening_balance,
            "total_in": self.total_in, "total_out": self.total_out, "net": self.net,
            "closing_balance": self.closing_balance, "current_balance": self.closing_balance,
        }


async def _sum_balance_by_product(
    session: AsyncSession, tenant_id: uuid.UUID, *, seller_id: uuid.UUID | None, search: str | None
) -> dict[uuid.UUID, int]:
    """Остаток сейчас — сумма ВСЕХ строк остатка товара (WMS-530 R1): без склада,
    зоны, тары и признака рабочего склада. Ровно та же цифра, что в каталоге."""
    scope_filters = _product_scope_filters(tenant_id, seller_id, search)
    stmt = (
        select(InventoryBalance.product_id, func.coalesce(func.sum(InventoryBalance.quantity), 0))
        .join(Product, Product.id == InventoryBalance.product_id)
        .where(InventoryBalance.tenant_id == tenant_id, *scope_filters)
        .group_by(InventoryBalance.product_id)
    )
    return {pid: int(qty) for pid, qty in (await session.execute(stmt)).all()}


async def _sum_movement_delta_since(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    since: datetime,
    seller_id: uuid.UUID | None,
    search: str | None,
) -> dict[uuid.UUID, int]:
    """Сумма ВСЕХ движений (включая расположение) начиная с `since` — для отката
    текущего остатка к границе периода. Расположение здесь обязано остаться:
    у полной пары его сумма ноль, а откат должен воспроизводить факт, а не
    подгонку под приход/расход (WMS-531 D2)."""
    stmt = (
        select(
            InventoryMovement.product_id,
            func.coalesce(func.sum(InventoryMovement.quantity_delta), 0),
        )
        .join(Product, Product.id == InventoryMovement.product_id)
        .where(
            InventoryMovement.tenant_id == tenant_id,
            InventoryMovement.created_at >= since,
            *_product_scope_filters(tenant_id, seller_id, search),
        )
        .group_by(InventoryMovement.product_id)
    )
    return {pid: int(delta) for pid, delta in (await session.execute(stmt)).all()}


async def _sum_period_in_out(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    date_from: datetime,
    date_to: datetime,
    seller_id: uuid.UUID | None,
    search: str | None,
) -> dict[uuid.UUID, tuple[int, int]]:
    """Приход/расход периода — только движения остатка (WMS-531 R1)."""
    in_expr = func.coalesce(
        func.sum(
            case((InventoryMovement.quantity_delta > 0, InventoryMovement.quantity_delta), else_=0)
        ),
        0,
    )
    out_expr = func.coalesce(
        func.sum(
            case((InventoryMovement.quantity_delta < 0, -InventoryMovement.quantity_delta), else_=0)
        ),
        0,
    )
    stmt = (
        select(InventoryMovement.product_id, in_expr, out_expr)
        .join(Product, Product.id == InventoryMovement.product_id)
        .where(
            InventoryMovement.tenant_id == tenant_id,
            InventoryMovement.created_at >= date_from,
            InventoryMovement.created_at < date_to,
            stock_movement_filter(),
            *_product_scope_filters(tenant_id, seller_id, search),
        )
        .group_by(InventoryMovement.product_id)
    )
    rows = (await session.execute(stmt)).all()
    return {pid: (int(in_q), int(out_q)) for pid, in_q, out_q in rows}


async def load_product_period_figures(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    date_from: datetime,
    date_to: datetime,
    seller_id: uuid.UUID | None = None,
    search: str | None = None,
) -> dict[uuid.UUID, ProductPeriodFigures]:
    """Было на начало / приход / расход / остаток на конец — по каждому товару.

    WMS-531 R6-R9: «было» и «стало» — факт (откат от текущего остатка), не
    подгонка. Строится ОДИН раз и используется и для плиток (build_overview),
    и для строк товара/селлера (build_inventory_report), и для Excel — иначе
    экран, плитки и файл разойдутся (R7, R8, R13). Четыре агрегата вместо
    построчного чтения журнала: работает за фиксированное число запросов
    независимо от объёма истории (R15).
    """
    current = await _sum_balance_by_product(session, tenant_id, seller_id=seller_id, search=search)
    since_from = await _sum_movement_delta_since(
        session, tenant_id, since=date_from, seller_id=seller_id, search=search
    )
    since_to = await _sum_movement_delta_since(
        session, tenant_id, since=date_to, seller_id=seller_id, search=search
    )
    period = await _sum_period_in_out(
        session, tenant_id, date_from=date_from, date_to=date_to, seller_id=seller_id, search=search
    )

    figures: dict[uuid.UUID, ProductPeriodFigures] = {}
    for product_id in set(current) | set(since_from):
        current_balance = current.get(product_id, 0)
        opening = current_balance - since_from.get(product_id, 0)
        closing = current_balance - since_to.get(product_id, 0)
        in_qty, out_qty = period.get(product_id, (0, 0))
        # WMS-531 R9: товар с нулями на начало и конец и без движений периода
        # не показывается — иначе список раздувается «спящими» товарами.
        if in_qty == 0 and out_qty == 0 and opening == 0 and closing == 0:
            continue
        figures[product_id] = ProductPeriodFigures(
            opening_balance=opening, in_qty=in_qty, out_qty=out_qty, closing_balance=closing,
        )
    return figures


async def incomplete_transfer_product_ids(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    date_from: datetime,
    date_to: datetime,
    seller_id: uuid.UUID | None = None,
    search: str | None = None,
) -> set[uuid.UUID]:
    """WMS-531 R7. Товары, у которых движение расположения в периоде осталось без пары.

    Расположение не входит в приход/расход (R1) и само по себе не двигает
    сумму остатка организации — но только когда обе стороны перемещения на
    месте. Если одна сторона потеряна (баг данных, а не норма), сумма по
    организации на самом деле сдвинута, и «было + приход - расход = стало»
    не сойдётся законно. Это не скрывается: строка товара помечается, и
    фронт показывает существующее предупреждение.
    """
    group_id_stmt = (
        select(InventoryMovement.transfer_group_id)
        .join(Product, Product.id == InventoryMovement.product_id)
        .where(
            InventoryMovement.tenant_id == tenant_id,
            InventoryMovement.created_at >= date_from,
            InventoryMovement.created_at < date_to,
            InventoryMovement.movement_type.in_(LOCATION_ONLY_MOVEMENT_TYPES),
            InventoryMovement.transfer_group_id.is_not(None),
            *_product_scope_filters(tenant_id, seller_id, search),
        )
        .distinct()
    )
    rows = (
        await session.execute(
            select(
                InventoryMovement.transfer_group_id,
                InventoryMovement.product_id,
                InventoryMovement.quantity_delta,
                InventoryMovement.movement_type,
            ).where(
                InventoryMovement.tenant_id == tenant_id,
                InventoryMovement.transfer_group_id.in_(group_id_stmt),
                # Групповой id также используют разделённое списание FBS и
                # передача между селлерами — сюда попадают только строки
                # расположения того же transfer_group_id, а не вся группа.
                InventoryMovement.movement_type.in_(LOCATION_ONLY_MOVEMENT_TYPES),
            )
        )
    ).all()

    groups: dict[uuid.UUID, list[tuple[uuid.UUID, int, str]]] = {}
    for group_id, product_id, quantity, movement_type in rows:
        groups.setdefault(group_id, []).append((product_id, int(quantity), movement_type))

    incomplete: set[uuid.UUID] = set()
    for members in groups.values():
        types = {m[2] for m in members}
        pair_ok = types == _STOCK_TRANSFER_PAIR_TYPES or (
            len(types) == 1 and next(iter(types)) in _SAME_TYPE_PAIR_TYPES
        )
        is_complete = (
            len(members) == 2
            and members[0][0] == members[1][0]
            and pair_ok
            and members[0][1] != 0
            and members[1][1] != 0
            and members[0][1] * members[1][1] < 0
            and abs(members[0][1]) == abs(members[1][1])
        )
        if not is_complete:
            incomplete.update(m[0] for m in members)

    # WMS-531 ревью Astra, F6: движение расположения совсем без номера группы
    # никогда не может оказаться полной парой — раньше такие строки не
    # попадали даже в кандидаты (`transfer_group_id IS NOT NULL` их
    # отбрасывал), и товар с потерянной второй стороной оставался без
    # предупреждения, хотя откат «было»/«стало» её всё равно учитывает.
    ungrouped_rows = await session.execute(
        select(InventoryMovement.product_id)
        .join(Product, Product.id == InventoryMovement.product_id)
        .where(
            InventoryMovement.tenant_id == tenant_id,
            InventoryMovement.created_at >= date_from,
            InventoryMovement.created_at < date_to,
            InventoryMovement.movement_type.in_(LOCATION_ONLY_MOVEMENT_TYPES),
            InventoryMovement.transfer_group_id.is_(None),
            *_product_scope_filters(tenant_id, seller_id, search),
        )
        .distinct()
    )
    incomplete.update(product_id for (product_id,) in ungrouped_rows)
    return incomplete


# ---------------------------------------------------------------------------
# Сведения о товаре для строк отчёта (имя, артикулы, ТЕКУЩИЙ селлер, фото).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ProductInfo:
    name: str
    sku_code: str
    wb_vendor_code: str | None
    wb_barcode: str | None
    seller_id: uuid.UUID | None
    seller_name: str | None
    wb_nm_id: int | None


async def _load_product_infos(
    session: AsyncSession, tenant_id: uuid.UUID, product_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, _ProductInfo]:
    if not product_ids:
        return {}
    rows = await session.execute(
        select(
            Product.id, Product.name, Product.sku_code, Product.wb_vendor_code,
            Product.wb_barcode, Product.seller_id, Seller.name, Product.wb_nm_id,
        )
        .outerjoin(Seller, Seller.id == Product.seller_id)
        .where(Product.tenant_id == tenant_id, Product.id.in_(list(product_ids)))
    )
    return {
        pid: _ProductInfo(
            name=name, sku_code=sku, wb_vendor_code=vendor, wb_barcode=barcode,
            seller_id=seller_id, seller_name=seller_name, wb_nm_id=nm_id,
        )
        for pid, name, sku, vendor, barcode, seller_id, seller_name, nm_id in rows.all()
    }


# ---------------------------------------------------------------------------
# «По операциям»: виды движения, приход/расход. Остаток здесь не считается —
# он относится к товару, а не к виду движения.
# ---------------------------------------------------------------------------


def operation_group_expr() -> ColumnElement[str]:
    """Возврат — отдельная группа: он приезжает движением «приёмка», но для
    склада и денег это другая операция (не путать с обычной приёмкой той же
    заявки). Проверяем именно СВОЙ ли это движение inbound_intake — иначе
    акт расхождений или служебная приёмка передачи, у которых тоже заполнен
    inbound_intake_line_id, случайно попадут в «Возврат» вместо своей группы."""
    return case(
        (
            and_(
                InventoryMovement.movement_type == MOVEMENT_TYPE_INBOUND_INTAKE,
                InboundIntakeRequest.operation_type == "return",
            ),
            "Возврат",
        ),
        *(
            (InventoryMovement.movement_type == movement_type, movement_group_label(movement_type))
            for movement_type in REPORT_MOVEMENT_TYPE_GROUPS
        ),
        else_="Прочее",
    )


async def _build_operation_rows(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    date_from: datetime,
    date_to: datetime,
    seller_id: uuid.UUID | None,
    search: str | None,
    page: int,
    sort_by: str,
    sort_order: str,
) -> dict[str, object]:
    filters = [
        InventoryMovement.tenant_id == tenant_id,
        InventoryMovement.created_at >= date_from,
        InventoryMovement.created_at < date_to,
        stock_movement_filter(),
    ]
    if search:
        filters.append(product_search_filter(tenant_id, search))
    in_qty = func.coalesce(func.sum(case((InventoryMovement.quantity_delta > 0,
        InventoryMovement.quantity_delta), else_=0)), 0)
    out_qty = func.coalesce(func.sum(case((InventoryMovement.quantity_delta < 0,
        -InventoryMovement.quantity_delta), else_=0)), 0)
    operation = operation_group_expr()
    grouped = select(
        operation.label("operation"), in_qty, out_qty,
    ).select_from(InventoryMovement).join(
        Product, Product.id == InventoryMovement.product_id).outerjoin(
        InboundIntakeLine,
        InboundIntakeLine.id == InventoryMovement.inbound_intake_line_id).outerjoin(
        InboundIntakeRequest,
        InboundIntakeRequest.id == InboundIntakeLine.request_id).where(*filters)
    if seller_id is not None:
        grouped = grouped.where(Product.seller_id == seller_id)
    grouped = grouped.group_by(operation)
    sort_columns = {
        "operation": operation, "in_qty": in_qty,
        "out_qty": out_qty, "net": in_qty - out_qty,
    }
    grouped = grouped.order_by(
        sort_columns[sort_by].desc() if sort_order == "desc" else sort_columns[sort_by].asc(),
        operation,
    )
    count_stmt = select(func.count()).select_from(grouped.order_by(None).subquery())
    total = int((await session.scalar(count_stmt)) or 0)
    start = (page - 1) * PAGE_SIZE
    rows = (await session.execute(grouped.limit(PAGE_SIZE).offset(start))).all()
    result = [
        {
            "operation": op, "in_qty": int(incoming), "out_qty": int(outgoing),
            "net": int(incoming) - int(outgoing),
        }
        for op, incoming, outgoing in rows
    ]
    return {
        "group_by": "operation", "page": page, "page_size": PAGE_SIZE,
        "total": total, "rows": result,
    }


# ---------------------------------------------------------------------------
# «По товарам» / «По селлерам»: остаток на начало/конец + приход/расход.
# ---------------------------------------------------------------------------


async def build_inventory_report(
    session: AsyncSession, tenant_id: uuid.UUID, *, date_from: datetime,
    date_to: datetime, group_by: str, page: int, seller_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None, search: str | None = None,
    sort_by: str | None = None, sort_order: str = "asc",
) -> dict[str, object]:
    """WMS-531. `warehouse_id` принимается и полностью игнорируется (R5): склад
    в отчёте больше не фильтрует ничего, старый клиент получает те же числа,
    что и без параметра."""
    del warehouse_id
    date_from, date_to = normalize_period(date_from, date_to)
    sort_by, sort_order = validated_sort(group_by, sort_by, sort_order)

    if group_by == "operation":
        return await _build_operation_rows(
            session, tenant_id, date_from=date_from, date_to=date_to,
            seller_id=seller_id, search=search, page=page,
            sort_by=sort_by, sort_order=sort_order,
        )

    figures = await load_product_period_figures(
        session, tenant_id, date_from=date_from, date_to=date_to,
        seller_id=seller_id, search=search,
    )
    infos = await _load_product_infos(session, tenant_id, list(figures.keys()))
    incomplete_ids = await incomplete_transfer_product_ids(
        session, tenant_id, date_from=date_from, date_to=date_to,
        seller_id=seller_id, search=search,
    )
    seller_nm = {
        pid: (info.seller_id, info.wb_nm_id) for pid, info in infos.items()
    }
    photos = await load_report_photo_urls(session, tenant_id, seller_nm)

    if group_by == "product":
        items: list[dict[str, object]] = []
        for pid, fig in figures.items():
            info = infos.get(pid)
            if info is None:
                continue
            items.append({
                "product_id": str(pid), "product_name": info.name, "sku_code": info.sku_code,
                "wb_vendor_code": info.wb_vendor_code, "wb_barcode": info.wb_barcode,
                "seller_id": str(info.seller_id) if info.seller_id else "",
                "seller_name": info.seller_name or "Без селлера",
                "photo_url": photos.get(pid),
                "opening_balance": fig.opening_balance,
                "total_in": fig.in_qty, "total_out": fig.out_qty, "net": fig.net,
                "closing_balance": fig.closing_balance,
                # Совместимость со старым полем: значение то же, что «остаток
                # на конец периода» — раньше означало «остаток сейчас».
                "current_balance": fig.closing_balance,
                "integrity_error": pid in incomplete_ids,
            })
        sort_key = {
            "name": lambda item: (item["product_name"] or "", item["sku_code"] or ""),
            "sku": lambda item: item["sku_code"] or "",
            "in_qty": lambda item: item["total_in"],
            "out_qty": lambda item: item["total_out"],
            "net": lambda item: item["net"],
        }[sort_by]
        items.sort(key=sort_key, reverse=(sort_order == "desc"))
        total = len(items)
        start = (page - 1) * PAGE_SIZE
        page_items = items[start:start + PAGE_SIZE]
        return {"group_by": "product", "page": page, "page_size": PAGE_SIZE,
            "total": total, "rows": page_items}

    # group_by == "seller"
    by_seller: dict[str, _SellerAgg] = {}
    for pid, fig in figures.items():
        info = infos.get(pid)
        if info is None:
            continue
        key = str(info.seller_id) if info.seller_id else ""
        agg = by_seller.setdefault(
            key, _SellerAgg(seller_id=key, seller_name=info.seller_name or "Без селлера")
        )
        agg.product_count += 1
        agg.opening_balance += fig.opening_balance
        agg.total_in += fig.in_qty
        agg.total_out += fig.out_qty
        agg.closing_balance += fig.closing_balance
    seller_aggs = list(by_seller.values())
    seller_sort_key = {
        "name": lambda item: item.seller_name,
        "in_qty": lambda item: item.total_in,
        "out_qty": lambda item: item.total_out,
        "net": lambda item: item.net,
        "products": lambda item: item.product_count,
    }[sort_by]
    seller_aggs.sort(key=seller_sort_key, reverse=(sort_order == "desc"))
    total = len(seller_aggs)
    start = (page - 1) * PAGE_SIZE
    page_items = [agg.as_dict() for agg in seller_aggs[start:start + PAGE_SIZE]]
    return {"group_by": "seller", "page": page, "page_size": PAGE_SIZE,
        "total": total, "rows": page_items}


# ---------------------------------------------------------------------------
# Плитки отчёта: было / приход / расход / остаток на конец по организации.
# ---------------------------------------------------------------------------


async def build_overview(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    date_from: datetime,
    date_to: datetime,
    seller_id: uuid.UUID | None,
    warehouse_id: uuid.UUID | None = None,
    search: str | None = None,
    include_technical_warnings: bool = True,
) -> dict[str, object]:
    """`warehouse_id` принимается и полностью игнорируется — см. build_inventory_report."""
    del warehouse_id
    date_from, date_to = normalize_period(date_from, date_to)

    figures = await load_product_period_figures(
        session, tenant_id, date_from=date_from, date_to=date_to,
        seller_id=seller_id, search=search,
    )
    opening_balance = sum(f.opening_balance for f in figures.values())
    closing_balance = sum(f.closing_balance for f in figures.values())
    in_qty = sum(f.in_qty for f in figures.values())
    out_qty = sum(f.out_qty for f in figures.values())

    now = datetime.now(UTC)
    closing_is_current = date_to > now
    closing_as_of = now if closing_is_current else date_to

    incomplete_ids = await incomplete_transfer_product_ids(
        session, tenant_id, date_from=date_from, date_to=date_to,
        seller_id=seller_id, search=search,
    )

    # WMS-531 ревью Astra, F5: селлер здесь и ниже — ТЕКУЩИЙ владелец товара
    # (Product.seller_id), а не снимок на момент движения
    # (InventoryMovement.seller_id). Иначе кабинет селлера мог показать
    # количества по чужому текущему владельцу товара или потерять свои —
    # ровно то расхождение, которое R10 запрещает.
    movement_filter = [
        InventoryMovement.tenant_id == tenant_id,
        InventoryMovement.created_at >= date_from,
        InventoryMovement.created_at < date_to,
        stock_movement_filter(),
        Product.id == InventoryMovement.product_id,
    ]
    if seller_id is not None:
        movement_filter.append(Product.seller_id == seller_id)
    if search:
        movement_filter.append(product_search_filter(tenant_id, search))

    length = date_to - date_from
    previous_from, previous_to = date_from - length, date_from
    previous_filter = [
        InventoryMovement.tenant_id == tenant_id,
        InventoryMovement.created_at >= previous_from,
        InventoryMovement.created_at < previous_to,
        stock_movement_filter(),
        Product.id == InventoryMovement.product_id,
    ]
    if seller_id is not None:
        previous_filter.append(Product.seller_id == seller_id)
    if search:
        previous_filter.append(product_search_filter(tenant_id, search))
    out_expr = func.coalesce(
        func.sum(
            case(
                (InventoryMovement.quantity_delta < 0, -InventoryMovement.quantity_delta),
                else_=0,
            )
        ),
        0,
    )
    previous_out = int(
        (
            await session.scalar(
                select(out_expr)
                .select_from(InventoryMovement)
                .join(Product, Product.id == InventoryMovement.product_id)
                .where(*previous_filter)
            )
        )
        or 0
    )
    current_out = out_qty

    # Keep calendar grouping in Python.  This is deliberately portable between
    # SQLite (tests) and PostgreSQL and, unlike ``date(created_at)``, always
    # uses the Moscow calendar that defines the requested report period.
    daily_stmt = (
        select(
            InventoryMovement.created_at,
            InventoryMovement.quantity_delta,
        )
        .select_from(InventoryMovement)
        .join(Product, Product.id == InventoryMovement.product_id)
        .where(*movement_filter)
    )
    daily: dict[str, dict[str, int]] = {}
    for created_at, quantity_delta in (await session.execute(daily_stmt)).all():
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        key = created_at.astimezone(MOSCOW_TZ).date().isoformat()
        item = daily.setdefault(key, {"in_qty": 0, "out_qty": 0, "previous_out_qty": 0})
        if quantity_delta > 0:
            item["in_qty"] += int(quantity_delta)
        else:
            item["out_qty"] += -int(quantity_delta)

    previous_daily_stmt = (
        select(InventoryMovement.created_at, InventoryMovement.quantity_delta)
        .select_from(InventoryMovement)
        .join(Product, Product.id == InventoryMovement.product_id)
        .where(*previous_filter)
    )
    for created_at, quantity_delta in (await session.execute(previous_daily_stmt)).all():
        if quantity_delta >= 0:
            continue
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        previous_day = created_at.astimezone(MOSCOW_TZ).date()
        current_day = previous_day + length
        key = current_day.isoformat()
        item = daily.setdefault(key, {"in_qty": 0, "out_qty": 0, "previous_out_qty": 0})
        item["previous_out_qty"] += -int(quantity_delta)

    # An entirely empty series is an explicit chart-empty signal.  Once either
    # interval has a movement, preserve every calendar bucket so isolated facts
    # do not look like a continuous daily flow.
    if daily:
        current_day = date_from.astimezone(MOSCOW_TZ).date()
        day_count = length.days + (1 if length % timedelta(days=1) else 0)
        for day_offset in range(day_count):
            key = (current_day + timedelta(days=day_offset)).isoformat()
            daily.setdefault(key, {"in_qty": 0, "out_qty": 0, "previous_out_qty": 0})
    days = [
        {"date": day, **values}
        for day, values in sorted(daily.items())
    ]

    legacy_stmt = select(func.count()).select_from(InventoryMovement).where(
        *movement_filter, InventoryMovement.reporting_dimensions_legacy.is_(True)
    )
    legacy_count = int((await session.scalar(legacy_stmt)) or 0)

    freshness_filters = [
        FbsWarehouseBinding.tenant_id == tenant_id,
        FbsWarehouseBinding.is_active.is_(True),
        FbsWarehouseBinding.stock_sync_enabled.is_(True),
    ]
    if seller_id is not None:
        freshness_filters.append(FbsWarehouseBinding.seller_id == seller_id)
    # Свежесть считается по задачам импорта Wildberries, поэтому и привязки
    # берём вайлдберрисовские. Без этого фильтра арендатор с одними озоновскими
    # привязками всегда получал предупреждение «данные Wildberries устарели» —
    # про площадку, которой у него нет.
    freshness_filters.append(FbsWarehouseBinding.marketplace == "wb")
    binding_count = int(
        (await session.scalar(select(func.count()).where(*freshness_filters))) or 0
    )
    import_jobs = (
        await session.execute(
            select(
                BackgroundJob.job_type,
                BackgroundJob.status,
                BackgroundJob.payload_json,
                BackgroundJob.finished_at,
            ).where(
                BackgroundJob.tenant_id == tenant_id,
                BackgroundJob.job_type.in_(WB_IMPORT_JOB_TYPES),
            )
        )
    ).all()
    attempted_streams: set[tuple[str | None, str]] = set()
    successful_streams: dict[tuple[str | None, str], datetime] = {}
    for job_type, job_status, payload, finished_at in import_jobs:
        raw_seller_id = (payload or {}).get("seller_id")
        if seller_id is not None and raw_seller_id != str(seller_id):
            continue
        stream = (raw_seller_id if isinstance(raw_seller_id, str) else None, job_type)
        attempted_streams.add(stream)
        if job_status != "done" or finished_at is None:
            continue
        if finished_at.tzinfo is None:
            finished_at = finished_at.replace(tzinfo=UTC)
        previous_success = successful_streams.get(stream)
        if previous_success is None or finished_at > previous_success:
            successful_streams[stream] = finished_at
    source_freshness: dict[str, object] | None = None
    warnings: list[dict[str, object]] = []
    if binding_count or attempted_streams:
        sync_at = (
            min(successful_streams.values())
            if attempted_streams and len(successful_streams) == len(attempted_streams)
            else None
        )
        # A missing timestamp is stale as well: it means that this enabled WB
        # feed has not yet supplied a confirmed freshness point.
        is_stale = sync_at is None or datetime.now(UTC) - sync_at > timedelta(hours=1)
        source_freshness = {
            "source": "wildberries",
            "last_updated_at": sync_at.isoformat() if sync_at else None,
            "is_stale": is_stale,
        }
        if is_stale:
            warnings.append({"code": "wildberries_stale", "source": "wildberries",
                "last_updated_at": sync_at.isoformat() if sync_at else None})
    if include_technical_warnings and legacy_count:
        warnings.append({"code": "reporting_dimensions_legacy", "count": legacy_count})

    return {
        "date_from": date_from.isoformat(), "date_to": date_to.isoformat(),
        "current_balance": closing_balance,
        "opening_balance": opening_balance,
        "closing_balance": closing_balance,
        "closing_balance_as_of": closing_as_of.isoformat(),
        "closing_balance_is_current": closing_is_current,
        "in_qty": in_qty, "out_qty": out_qty,
        "comparison": {
            "previous_out_qty": previous_out,
            "change_percent": None if previous_out == 0 else round(
                (current_out - previous_out) * 100 / previous_out, 2
            ),
            "change": current_out - previous_out,
        },
        "daily": days,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_freshness": source_freshness, "warnings": warnings,
        "has_incomplete_transfer": bool(incomplete_ids),
    }


# ---------------------------------------------------------------------------
# Строки движений (третий уровень раскрытия) — общая сборка для экрана и Excel.
# ---------------------------------------------------------------------------


def row_operation_label(
    movement_type: str,
    *,
    intake_operation_type: str | None,
    quantity_delta: int,
    has_resolved_document: bool = False,
) -> str:
    """WMS-531 R2. Подпись «Движение» одной строки — не всегда совпадает с её
    группой в «По операциям» (см. Корректировка/Передача между селлерами:
    группа общая, подписи разные).

    WMS-531 ревью Astra, F8: «FBS, сторно» — это про ПОДТВЕРЖДЁННОЕ историческое
    сторно (R2: «сторно до 05.09.2026», связанное `reversal_movement_id`), а не
    про любую положительную строку по знаку. Известные сентябрьские правки —
    разовые правки данных без автора, не сторно заказа (факт ведущего, прод,
    только чтение) — подписывать их «сторно» без подтверждённой связи с
    заказом означало бы приписать документу непроверенный смысл. Пока
    требования не определяют отдельную подпись для положительной строки без
    связи, используем нейтральную «FBS» — она и так верна (это FBS-движение),
    просто не утверждает, что это возврат.
    """
    if movement_type == MOVEMENT_TYPE_INBOUND_INTAKE:
        return "Возврат" if intake_operation_type == "return" else "Приёмка"
    if movement_type == MOVEMENT_TYPE_DISCREPANCY_ACT:
        return "Корректировка по акту расхождений"
    if movement_type == MOVEMENT_TYPE_OWNERSHIP_RECEIPT:
        return "Приёмка при передаче между селлерами"
    if movement_type == MOVEMENT_TYPE_FBS_SHIPMENT:
        return "FBS, сторно" if quantity_delta > 0 and has_resolved_document else "FBS"
    if movement_type not in REPORT_MOVEMENT_TYPE_GROUPS:
        # WMS-531 R2, последняя строка таблицы: неизвестный вид всё равно
        # обязан быть виден и опознаваем, а не молча слит с прочими «Прочее».
        return f"Прочее: {movement_type}"
    return movement_group_label(movement_type)


def _fbs_order_number(marketplace: str, wb_order_id: int, external_order_id: str | None) -> str:
    """WMS-531 R4: площадка обязана быть видна в подписи заказа."""
    if marketplace == "ozon":
        return f"Заказ Ozon №{external_order_id or wb_order_id}"
    return f"Заказ WB №{wb_order_id}"


async def _resolve_intake_documents(
    session: AsyncSession, intake_line_ids: set[uuid.UUID]
) -> dict[uuid.UUID, tuple[uuid.UUID, str | None, str]]:
    """intake_line_id -> (request_id, номер, operation_type).

    Используется приёмкой/возвратом, актом расхождений (ссылается на строку
    приёмки, к которой относится) и служебной приёмкой передачи между
    селлерами — у всех троих один и тот же FK.
    """
    if not intake_line_ids:
        return {}
    rows = await session.execute(
        select(
            InboundIntakeLine.id,
            InboundIntakeRequest.id,
            InboundIntakeRequest.display_number,
            InboundIntakeRequest.document_number,
            InboundIntakeRequest.operation_type,
        )
        .join(InboundIntakeRequest, InboundIntakeRequest.id == InboundIntakeLine.request_id)
        .where(InboundIntakeLine.id.in_(intake_line_ids))
    )
    return {
        line_id: (request_id, display_number or document_number, str(operation_type))
        for line_id, request_id, display_number, document_number, operation_type in rows
    }


async def _resolve_unload_documents(
    session: AsyncSession, unload_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str | None]:
    if not unload_ids:
        return {}
    rows = await session.execute(
        select(
            MarketplaceUnloadRequest.id,
            MarketplaceUnloadRequest.display_number,
            MarketplaceUnloadRequest.document_number,
        ).where(MarketplaceUnloadRequest.id.in_(unload_ids))
    )
    return {
        unload_id: display_number or document_number
        for unload_id, display_number, document_number in rows
    }


async def _resolve_outbound_documents(
    session: AsyncSession, outbound_line_ids: set[uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID]:
    """outbound_shipment_line_id -> request_id. Заявка на старую отгрузку не
    получает собственный номер нигде в системе (в своём списке видна только
    строка статуса) — документ показывается с подписью «без номера»."""
    if not outbound_line_ids:
        return {}
    rows = await session.execute(
        select(OutboundShipmentLine.id, OutboundShipmentLine.request_id).where(
            OutboundShipmentLine.id.in_(outbound_line_ids)
        )
    )
    return {line_id: request_id for line_id, request_id in rows}


async def _resolve_inventory_count_documents(
    session: AsyncSession, count_line_ids: set[uuid.UUID]
) -> dict[uuid.UUID, tuple[uuid.UUID, str]]:
    """inventory_count_line_id -> (count_id, «ИНВ-…»).

    Формула номера обязана совпадать с `app.api.inventory_counts._number` —
    это тот же номер, что виден в списке инвентаризаций (WMS-531 C14). Сервис
    не импортирует API-модуль (нарушало бы направление слоёв, AGENTS.md §4),
    поэтому формула продублирована однострочно; при изменении там менять и тут.
    """
    if not count_line_ids:
        return {}
    rows = await session.execute(
        select(InventoryCountLine.id, InventoryCountLine.count_id).where(
            InventoryCountLine.id.in_(count_line_ids)
        )
    )
    return {
        line_id: (count_id, f"ИНВ-{str(count_id).split('-')[0].upper()}")
        for line_id, count_id in rows.all()
    }


async def _resolve_fbs_documents(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rows: Sequence[InventoryMovement],
    *,
    date_from: datetime,
    date_to: datetime,
) -> dict[uuid.UUID, tuple[str, uuid.UUID | None]]:
    """movement_id -> (подпись заказа с площадкой, supply_id).

    Списание FBS связано с заказом через журнал `FbsShipmentReversalLedger`:
    прямой id (исходное списание или его историческое сторно
    `reversal_movement_id`) либо позиция Ozon-заказа с несколькими товарами
    (`ozon_positions_json`, где у каждой позиции свой movement_id). Старое
    `fbs_order_pick`/его отмена документа в журнале не имеют — ищем через
    запись подбора (см. ниже).

    WMS-531 ревью Astra, F2: список позиций Ozon ограничен по времени НЕ
    `created_at` самого журнала (он пишется заранее, при подготовке к
    передаче — `fbs_ozon_packaging_service.prepare_shipment_sources`, часто
    задолго до фактического списания), а по `created_at` движения-якоря
    (`shipment_movement_id`): все позиции одного списания создаются в одном
    вызове `write_off_order` практически одномоментно, поэтому якорь — верная
    граница периода, а дата журнала — нет. Старое ограничение по дате
    журнала теряло вторую и следующие позиции, если журнал готовили раньше.
    """
    fbs_movement_ids = {
        row.id for row in rows if row.movement_type in {"fbs_shipment", "fbs_order_pick"}
    }
    pick_undo_ids = {row.id for row in rows if row.movement_type == "fbs_order_pick_undo"}
    result: dict[uuid.UUID, tuple[str, uuid.UUID | None]] = {}

    # WMS-531 ревью Astra, F3: разделённое списание (в т.ч. вторая и следующие
    # позиции Ozon, расколотые по местам/таре) может быть найдено не по своему
    # id, а по id ЛЮБОГО соседа с тем же transfer_group_id — включая соседа,
    # найденного только через ozon_positions_json, а не через
    # shipment_movement_id напрямую. Поэтому расширяем набор кандидатов ДО
    # прямых поисков всеми участниками группы, а не подбираем документ по
    # группе отдельным финальным шагом, ограниченным только shipment_movement_id.
    group_by_movement: dict[uuid.UUID, uuid.UUID] = {
        row.id: row.transfer_group_id
        for row in rows
        if row.movement_type == "fbs_shipment" and row.transfer_group_id is not None
    }
    members_by_group: dict[uuid.UUID, set[uuid.UUID]] = {}
    if group_by_movement:
        group_ids = set(group_by_movement.values())
        sibling_rows = await session.execute(
            select(InventoryMovement.id, InventoryMovement.transfer_group_id).where(
                InventoryMovement.tenant_id == tenant_id,
                InventoryMovement.transfer_group_id.in_(group_ids),
                InventoryMovement.movement_type == "fbs_shipment",
            )
        )
        for member_id, group_id in sibling_rows:
            members_by_group.setdefault(group_id, set()).add(member_id)

    expanded_fbs_ids = set(fbs_movement_ids)
    for members in members_by_group.values():
        expanded_fbs_ids |= members

    async def _apply_ledger_rows(
        # Каждый элемент — Row из session.execute с колонками (movement_id,
        # ozon_positions_json, marketplace, wb_order_id, external_order_id,
        # supply_id). Типизируем как Iterable[Any]: mypy не считает Row
        # SQLAlchemy подтипом tuple, а распаковка в цикле ниже работает и так.
        ledger_rows: Iterable[Any],
        candidate_ids: set[uuid.UUID],
    ) -> None:
        for movement_id, positions, marketplace, wb_order_id, external_order_id, supply_id in (
            ledger_rows
        ):
            linked_ids: set[uuid.UUID] = {movement_id} if movement_id is not None else set()
            for position in positions or []:
                try:
                    linked_ids.add(uuid.UUID(str(position.get("movement_id"))))
                except (ValueError, AttributeError, TypeError):
                    continue
            for linked_id in linked_ids & candidate_ids:
                if linked_id in result:
                    continue
                number = _fbs_order_number(marketplace, wb_order_id, external_order_id)
                result[linked_id] = (number, supply_id)

    if expanded_fbs_ids:
        by_shipment_id = await session.execute(
            select(
                FbsShipmentReversalLedger.shipment_movement_id,
                FbsShipmentReversalLedger.ozon_positions_json,
                FbsOrder.marketplace, FbsOrder.wb_order_id, FbsOrder.external_order_id,
                FbsOrder.supply_id,
            )
            .join(FbsOrder, FbsOrder.id == FbsShipmentReversalLedger.fbs_order_id)
            .where(
                FbsShipmentReversalLedger.tenant_id == tenant_id,
                FbsOrder.tenant_id == tenant_id,
                FbsShipmentReversalLedger.shipment_movement_id.in_(expanded_fbs_ids),
            )
        )
        await _apply_ledger_rows(by_shipment_id, expanded_fbs_ids)

    # Историческое сторно FBS (до 05.09.2026, movement_type всё ещё
    # "fbs_shipment", но со знаком «+») связано через reversal_movement_id,
    # а не shipment_movement_id.
    reversal_candidates = expanded_fbs_ids - set(result)
    if reversal_candidates:
        by_reversal_id = await session.execute(
            select(
                FbsShipmentReversalLedger.reversal_movement_id,
                FbsShipmentReversalLedger.ozon_positions_json,
                FbsOrder.marketplace, FbsOrder.wb_order_id, FbsOrder.external_order_id,
                FbsOrder.supply_id,
            )
            .join(FbsOrder, FbsOrder.id == FbsShipmentReversalLedger.fbs_order_id)
            .where(
                FbsShipmentReversalLedger.tenant_id == tenant_id,
                FbsOrder.tenant_id == tenant_id,
                FbsShipmentReversalLedger.reversal_movement_id.in_(reversal_candidates),
            )
        )
        await _apply_ledger_rows(by_reversal_id, reversal_candidates)

    ozon_position_candidates = expanded_fbs_ids - set(result)
    if ozon_position_candidates:
        anchor_movement = aliased(InventoryMovement)
        by_position = await session.execute(
            select(
                FbsShipmentReversalLedger.shipment_movement_id,
                FbsShipmentReversalLedger.ozon_positions_json,
                FbsOrder.marketplace, FbsOrder.wb_order_id, FbsOrder.external_order_id,
                FbsOrder.supply_id,
            )
            .join(FbsOrder, FbsOrder.id == FbsShipmentReversalLedger.fbs_order_id)
            .join(
                anchor_movement,
                anchor_movement.id == FbsShipmentReversalLedger.shipment_movement_id,
            )
            .where(
                FbsShipmentReversalLedger.tenant_id == tenant_id,
                FbsOrder.tenant_id == tenant_id,
                FbsShipmentReversalLedger.ozon_positions_json.is_not(None),
                anchor_movement.created_at >= date_from,
                anchor_movement.created_at < date_to,
            )
        )
        await _apply_ledger_rows(by_position, ozon_position_candidates)

    # Распространяем найденный документ на всех участников группы: если хоть
    # один сосед разрешился (любым из способов выше), остальные наследуют тот
    # же заказ, не будучи связаны напрямую (R3).
    for members in members_by_group.values():
        found = next((result[member_id] for member_id in members if member_id in result), None)
        if found is None:
            continue
        for member_id in members:
            result.setdefault(member_id, found)

    # Старое fbs_order_pick / его отмена: документ в журнале сторно
    # отсутствует. Ищем заказ через запись подбора — сначала по её событию
    # (несёт movement_id и исходного подбора, и отмены), а для совсем старых
    # записей без событий — по прямому FK на исходный pick.
    pick_candidates = {mid for mid in (fbs_movement_ids | pick_undo_ids) if mid not in result}
    if pick_candidates:
        _OrderInfo = dict[uuid.UUID, tuple[str, uuid.UUID | None]]

        async def _orders_by_id(order_ids: set[uuid.UUID]) -> _OrderInfo:
            if not order_ids:
                return {}
            order_rows = await session.execute(
                select(FbsOrder.id, FbsOrder.marketplace, FbsOrder.wb_order_id,
                    FbsOrder.external_order_id, FbsOrder.supply_id)
                .where(FbsOrder.id.in_(order_ids), FbsOrder.tenant_id == tenant_id)
            )
            info: _OrderInfo = {}
            for order_id, marketplace, wb_order_id, external_order_id, supply_id in order_rows:
                number = _fbs_order_number(marketplace, wb_order_id, external_order_id)
                info[order_id] = (number, supply_id)
            return info

        event_rows = list(
            await session.execute(
                select(FbsOrderPickEvent.inventory_movement_id, FbsOrderPick.fbs_order_id)
                .join(FbsOrderPick, FbsOrderPick.id == FbsOrderPickEvent.pick_id)
                .where(
                    FbsOrderPick.tenant_id == tenant_id,
                    FbsOrderPickEvent.inventory_movement_id.in_(pick_candidates),
                )
            )
        )
        order_by_id = await _orders_by_id(
            {order_id for _, order_id in event_rows if order_id is not None}
        )
        for movement_id, order_id in event_rows:
            if movement_id is not None and order_id in order_by_id:
                result[movement_id] = order_by_id[order_id]

        remaining = pick_candidates - set(result)
        if remaining:
            direct_rows = list(
                await session.execute(
                    select(FbsOrderPick.inventory_movement_id, FbsOrderPick.fbs_order_id).where(
                        FbsOrderPick.tenant_id == tenant_id,
                        FbsOrderPick.inventory_movement_id.in_(remaining),
                    )
                )
            )
            direct_order_by_id = await _orders_by_id(
                {order_id for _, order_id in direct_rows if order_id is not None}
            )
            for movement_id, order_id in direct_rows:
                if movement_id is not None and order_id in direct_order_by_id:
                    result[movement_id] = direct_order_by_id[order_id]

    return result


async def _resolve_ownership_transfer_partners(
    session: AsyncSession, tenant_id: uuid.UUID, rows: Sequence[InventoryMovement]
) -> dict[uuid.UUID, str]:
    """movement_id -> подпись «Передано селлеру «…»» / «Получено от селлера «…»».

    Обе стороны передачи между селлерами пишутся одним transfer_group_id
    (WMS-531 R3: «вторая строка той же передачи — для имени селлера»).
    """
    group_ids = {
        row.transfer_group_id
        for row in rows
        if row.movement_type in {MOVEMENT_TYPE_OWNERSHIP_OUT, MOVEMENT_TYPE_OWNERSHIP_IN}
        and row.transfer_group_id is not None
    }
    if not group_ids:
        return {}
    sibling_rows = await session.execute(
        select(
            InventoryMovement.transfer_group_id, InventoryMovement.movement_type,
            InventoryMovement.seller_id, Seller.name,
        )
        .outerjoin(Seller, Seller.id == InventoryMovement.seller_id)
        .where(
            InventoryMovement.tenant_id == tenant_id,
            InventoryMovement.transfer_group_id.in_(group_ids),
            InventoryMovement.movement_type.in_(
                (MOVEMENT_TYPE_OWNERSHIP_OUT, MOVEMENT_TYPE_OWNERSHIP_IN)
            ),
        )
    )
    name_by_group_and_type: dict[tuple[uuid.UUID, str], str] = {}
    for group_id, movement_type, _seller_id, seller_name in sibling_rows:
        name_by_group_and_type[(group_id, movement_type)] = seller_name or "без селлера"

    result: dict[uuid.UUID, str] = {}
    for row in rows:
        if row.movement_type == MOVEMENT_TYPE_OWNERSHIP_OUT and row.transfer_group_id is not None:
            recipient_key = (row.transfer_group_id, MOVEMENT_TYPE_OWNERSHIP_IN)
            recipient = name_by_group_and_type.get(recipient_key)
            if recipient is not None:
                result[row.id] = f"Передано селлеру «{recipient}»"
        elif row.movement_type == MOVEMENT_TYPE_OWNERSHIP_IN and row.transfer_group_id is not None:
            sender_key = (row.transfer_group_id, MOVEMENT_TYPE_OWNERSHIP_OUT)
            sender = name_by_group_and_type.get(sender_key)
            if sender is not None:
                result[row.id] = f"Получено от селлера «{sender}»"
    return result


async def _enrich_movement_rows(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rows: Sequence[InventoryMovement],
    *,
    date_from: datetime,
    date_to: datetime,
) -> list[dict[str, object]]:
    """Общая сборка обогащённых строк движения — использует и постраничный
    экранный эндпоинт, и Excel (WMS-531 R13: одна функция гарантирует, что
    файл и экран не разойдутся). Имя и артикул товара заполняются всегда:
    в раскрытии по виду движения без них не понять, что именно уехало —
    там в одной пачке лежат разные товары."""
    intake_line_ids = {row.inbound_intake_line_id for row in rows if row.inbound_intake_line_id}
    unload_ids = {
        row.marketplace_unload_request_id for row in rows if row.marketplace_unload_request_id
    }
    outbound_line_ids = {
        row.outbound_shipment_line_id for row in rows if row.outbound_shipment_line_id
    }
    count_line_ids = {row.inventory_count_line_id for row in rows if row.inventory_count_line_id}

    intake_by_line = await _resolve_intake_documents(session, intake_line_ids)
    unload_numbers = await _resolve_unload_documents(session, unload_ids)
    outbound_requests = await _resolve_outbound_documents(session, outbound_line_ids)
    count_documents = await _resolve_inventory_count_documents(session, count_line_ids)
    fbs_documents = await _resolve_fbs_documents(
        session, tenant_id, rows, date_from=date_from, date_to=date_to
    )
    ownership_labels = await _resolve_ownership_transfer_partners(session, tenant_id, rows)

    product_names: dict[uuid.UUID, tuple[str | None, str | None]] = {}
    product_ids = {row.product_id for row in rows if row.product_id}
    if product_ids:
        for pid, name, sku in await session.execute(
            select(Product.id, Product.name, Product.sku_code).where(
                Product.tenant_id == tenant_id, Product.id.in_(product_ids)
            )
        ):
            product_names[pid] = (name, sku)

    result: list[dict[str, object]] = []
    for row in rows:
        document: dict[str, object] | None = None
        intake_operation_type: str | None = None
        if row.inbound_intake_line_id and row.inbound_intake_line_id in intake_by_line:
            request_id, number, operation_type = intake_by_line[row.inbound_intake_line_id]
            intake_operation_type = operation_type
            document = {"kind": "inbound", "id": str(request_id), "number": number or "без номера"}
        elif row.id in fbs_documents:
            number, supply_id = fbs_documents[row.id]
            document = {
                "kind": "fbs_supply" if supply_id else "fbs_order",
                "id": str(supply_id) if supply_id else str(row.id),
                "number": number,
            }
        elif row.marketplace_unload_request_id:
            document = {
                "kind": "marketplace_unload",
                "id": str(row.marketplace_unload_request_id),
                "number": unload_numbers.get(row.marketplace_unload_request_id) or "без номера",
            }
        elif row.outbound_shipment_line_id and row.outbound_shipment_line_id in outbound_requests:
            document = {
                "kind": "outbound_shipment",
                "id": str(outbound_requests[row.outbound_shipment_line_id]),
                "number": "без номера",
            }
        elif row.inventory_count_line_id and row.inventory_count_line_id in count_documents:
            count_id, number = count_documents[row.inventory_count_line_id]
            document = {"kind": "inventory_count", "id": str(count_id), "number": number}

        if row.id in ownership_labels:
            row_operation = ownership_labels[row.id]
        else:
            row_operation = row_operation_label(
                row.movement_type,
                intake_operation_type=intake_operation_type,
                quantity_delta=int(row.quantity_delta),
                has_resolved_document=document is not None,
            )

        name, sku = product_names.get(row.product_id, (None, None))
        result.append({
            "id": str(row.id), "at": row.created_at.isoformat(), "operation": row_operation,
            "quantity": int(row.quantity_delta), "document": document,
            "product_id": str(row.product_id) if row.product_id else None,
            "product_name": name, "sku_code": sku,
        })
    return result


async def list_product_movements(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    product_id: uuid.UUID | None = None,
    operation: str | None = None,
    date_from: datetime,
    date_to: datetime,
    seller_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    search: str | None = None,
    page: int = 1,
    limit: int = MOVEMENT_PAGE_LIMIT,
) -> tuple[list[dict[str, object]], bool, int]:
    """Движения за период — то, что видно при раскрытии строки отчёта.

    `warehouse_id` принимается и игнорируется (WMS-531 R5). Возвращает
    `(rows, truncated, total)`: `truncated` — есть ли ещё строки после этой
    страницы, `total` — сколько их всего (для «Загрузить ещё», R11).

    WMS-531 ревью Astra, F4: `search` раньше не принимался вовсе — сводка по
    виду операции учитывала поиск, а раскрытие того же вида его теряло, и
    сумма раскрытых движений расходилась со строкой (R11, R13).
    """
    del warehouse_id
    if product_id is None and operation is None:
        raise ValueError("movements require a product or an operation group")
    date_from, date_to = normalize_period(date_from, date_to)
    filters = [
        InventoryMovement.tenant_id == tenant_id,
        InventoryMovement.created_at >= date_from,
        InventoryMovement.created_at < date_to,
        stock_movement_filter(),
    ]
    if product_id is not None:
        filters.append(InventoryMovement.product_id == product_id)
    if seller_id is not None or search:
        product_scope_filters = [Product.tenant_id == tenant_id]
        if seller_id is not None:
            product_scope_filters.append(Product.seller_id == seller_id)
        if search:
            product_scope_filters.append(product_search_filter(tenant_id, search))
        scoped_product_ids = select(Product.id).where(*product_scope_filters)
        filters.append(InventoryMovement.product_id.in_(scoped_product_ids))

    query = select(InventoryMovement)
    if operation is not None:
        query = query.join(Product, Product.id == InventoryMovement.product_id).outerjoin(
            InboundIntakeLine,
            InboundIntakeLine.id == InventoryMovement.inbound_intake_line_id,
        ).outerjoin(
            InboundIntakeRequest,
            InboundIntakeRequest.id == InboundIntakeLine.request_id,
        )
        filters.append(operation_group_expr() == operation)

    id_only = query.with_only_columns(InventoryMovement.id).where(*filters)
    count_stmt = select(func.count()).select_from(id_only.subquery())
    total = int((await session.scalar(count_stmt)) or 0)

    offset = (page - 1) * limit
    rows = list(
        (
            await session.execute(
                query.where(*filters)
                .order_by(InventoryMovement.created_at.desc(), InventoryMovement.id)
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
    )
    truncated = offset + len(rows) < total

    result = await _enrich_movement_rows(
        session, tenant_id, rows, date_from=date_from, date_to=date_to,
    )
    return result, truncated, total


# ---------------------------------------------------------------------------
# Выгрузка в Excel (WMS-531 R12-R14). CSV убран из интерфейса и из бэка: два
# формата выгрузки с разным содержимым — путь к расхождениям (D6).
# ---------------------------------------------------------------------------


_XLSX_DATE_FORMAT = "DD.MM.YYYY HH:MM:SS"


def _moscow_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(MOSCOW_TZ).replace(tzinfo=None)


def _set_numeric(cell: object, value: int) -> None:
    cell.value = value  # type: ignore[attr-defined]
    cell.number_format = "0"  # type: ignore[attr-defined]


def _movement_quantity(movement: dict[str, object]) -> int:
    """`movement["quantity"]` типизирован как `object` (общий словарь строки
    движения) — isinstance сужает тип без предупреждений mypy про int(object)."""
    value = movement["quantity"]
    assert isinstance(value, int)
    return value


async def build_inventory_workbook(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    date_from: datetime,
    date_to: datetime,
    group_by: str,
    seller_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    search: str | None = None,
    include_seller: bool = True,
    sort_by: str | None = None,
    sort_order: str = "asc",
) -> bytes:
    """Полная выгрузка: та же группировка, что на экране, без ограничений
    50/200 (R12.8). Использует ровно те же агрегаты и ту же сборку строк
    движения, что и JSON-эндпоинты — числа гарантированно совпадают (R13).

    WMS-531 ревью Astra, F1: журнал движений периода читается и обогащается
    ПОРЦИЯМИ — по одному селлеру за раз, а не всем тенантом разом, — чтобы
    пиковая память ограничивалась объёмом одного селлера, а не годовым
    журналом самого крупного арендатора целиком (R15).
    """
    del warehouse_id
    date_from, date_to = normalize_period(date_from, date_to)
    sort_by, sort_order = validated_sort(group_by, sort_by, sort_order)

    figures = await load_product_period_figures(
        session, tenant_id, date_from=date_from, date_to=date_to,
        seller_id=seller_id, search=search,
    )
    if not figures:
        raise ValueError("nothing to export for the selected period")
    infos = await _load_product_infos(session, tenant_id, list(figures.keys()))

    sellers: dict[str, dict[str, object]] = {}
    for pid, fig in figures.items():
        info = infos.get(pid)
        if info is None:
            continue
        key = str(info.seller_id) if info.seller_id else ""
        bucket = sellers.setdefault(
            key, {"seller_name": info.seller_name or "Без селлера", "products": []}
        )
        bucket["products"].append((pid, info, fig))  # type: ignore[attr-defined]
    # Освобождаем словари, которые уже разложены по селлерам, — дальше журнал
    # движений тоже читается порциями, и не нужно держать все товары/фигуры
    # тенанта плоским списком одновременно с ними.
    del figures, infos

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Остатки и движения"
    headers = ["Товар", "Артикул продавца", "ШК", "Дата", "Движение", "Документ",
        "Было на начало", "Приход", "Расход", "Остаток на конец"]
    if include_seller:
        headers.insert(0, "Селлер")
    sheet.append(headers)
    sheet.freeze_panes = "A2"
    sheet.sheet_properties.outlinePr.summaryBelow = False

    # Индексы колонок считаются один раз по итоговому списку headers (уже с
    # учётом вставленной «Селлер», если она есть) — не подбираются вручную на
    # каждой строке. WMS-531: ручной подбор индексов уже давал рассинхрон
    # («Было на начало» уезжало в «Документ»), нашлось только тестами.
    col_name = headers.index("Товар")
    col_vendor = headers.index("Артикул продавца")
    col_barcode = headers.index("ШК")
    col_date = headers.index("Дата")
    col_operation = headers.index("Движение")
    col_document = headers.index("Документ")
    col_opening = headers.index("Было на начало")
    col_in = headers.index("Приход")
    col_out = headers.index("Расход")
    col_closing = headers.index("Остаток на конец")
    numeric_columns = frozenset({col_opening, col_in, col_out, col_closing})

    # WMS-531 ревью Astra, F1 (P1): `sheet.max_row` в установленной версии
    # openpyxl — это `max(self._cells)`, то есть обход всех уже накопленных
    # ячеек. Вызов после каждой строки давал квадратичный рост (замер ревью:
    # 1.381 с / 4.003 с / 20.225 с на 1000/2000/4000 строк). Собственный
    # счётчик и точечная запись через `sheet.cell(row=, column=)` вместо
    # `sheet.append(list) + sheet.max_row` держат каждую операцию O(1):
    # тот же объём — 4000 строк — укладывается в доли секунды (проверено
    # отдельным локальным замером при написании этого исправления).
    next_row = 1  # заголовок уже в строке 1

    def _append(values: list[object], *, outline_level: int) -> None:
        nonlocal next_row
        next_row += 1
        for column_index, value in enumerate(values):
            if value is None:
                continue
            cell = sheet.cell(row=next_row, column=column_index + 1, value=value)
            if isinstance(value, str):
                # WMS-531 ревью Astra, F10: openpyxl трактует строку,
                # начинающуюся с «=», как формулу — название товара вида
                # «=1+1» не должно поменять смысл при открытии в Excel.
                # Числа и даты явный тип не получают — им ниже нужен
                # number_format числовой/датной ячейки, а не текстовой.
                cell.data_type = "s"
            elif column_index in numeric_columns:
                cell.number_format = "0"
            elif column_index == col_date:
                cell.number_format = _XLSX_DATE_FORMAT
        if outline_level > 0:
            sheet.row_dimensions[next_row].outlineLevel = outline_level
            sheet.row_dimensions[next_row].hidden = True

    total_opening = total_in = total_out = total_closing = 0
    for _seller_key, bucket in sorted(sellers.items(), key=lambda kv: str(kv[1]["seller_name"])):
        products: list[tuple[uuid.UUID, _ProductInfo, ProductPeriodFigures]] = bucket["products"]  # type: ignore[assignment]
        seller_product_ids = [pid for pid, _info, _fig in products]
        movement_rows = list(
            (
                await session.execute(
                    select(InventoryMovement)
                    .where(
                        InventoryMovement.tenant_id == tenant_id,
                        InventoryMovement.created_at >= date_from,
                        InventoryMovement.created_at < date_to,
                        stock_movement_filter(),
                        InventoryMovement.product_id.in_(seller_product_ids),
                    )
                    .order_by(InventoryMovement.created_at.asc(), InventoryMovement.id)
                )
            ).scalars().all()
        )
        enriched = await _enrich_movement_rows(
            session, tenant_id, movement_rows, date_from=date_from, date_to=date_to,
        )
        del movement_rows
        movements_by_product: dict[str, list[dict[str, object]]] = {}
        for row in enriched:
            row_product_id = row["product_id"]
            if row_product_id is None:
                continue
            movements_by_product.setdefault(str(row_product_id), []).append(row)
        del enriched

        seller_opening = sum(fig.opening_balance for _p, _i, fig in products)
        seller_in = sum(fig.in_qty for _p, _i, fig in products)
        seller_out = sum(fig.out_qty for _p, _i, fig in products)
        seller_closing = sum(fig.closing_balance for _p, _i, fig in products)
        total_opening += seller_opening
        total_in += seller_in
        total_out += seller_out
        total_closing += seller_closing

        # WMS-531 ревью Astra, F7: в кабинете селлера уровня «Селлер» нет
        # вовсе (R12.9) — не только колонки и названия, но и самой строки:
        # верхним уровнем становятся товары/виды, а не безымянный дубль
        # итогов над ними. `top_level`/`leaf_level` сдвигают вложенность на
        # один уровень вверх, когда селлерского уровня нет.
        top_level = 1 if include_seller else 0
        leaf_level = 2 if include_seller else 1
        if include_seller:
            seller_row: list[object] = [None] * len(headers)
            seller_row[0] = bucket["seller_name"]
            seller_row[col_opening] = seller_opening
            seller_row[col_in] = seller_in
            seller_row[col_out] = seller_out
            seller_row[col_closing] = seller_closing
            _append(seller_row, outline_level=0)

        if group_by == "product":
            for pid, info, fig in sorted(products, key=_product_row_sort_key):
                product_row: list[object] = [None] * len(headers)
                if include_seller:
                    product_row[0] = bucket["seller_name"]
                product_row[col_name] = info.name
                product_row[col_vendor] = info.wb_vendor_code
                product_row[col_barcode] = info.wb_barcode
                product_row[col_opening] = fig.opening_balance
                product_row[col_in] = fig.in_qty
                product_row[col_out] = fig.out_qty
                product_row[col_closing] = fig.closing_balance
                _append(product_row, outline_level=top_level)
                for movement in movements_by_product.get(str(pid), []):
                    movement_row: list[object] = [None] * len(headers)
                    if include_seller:
                        movement_row[0] = bucket["seller_name"]
                    movement_row[col_date] = _moscow_naive(
                        datetime.fromisoformat(str(movement["at"]))
                    )
                    row_operation = str(movement["operation"])
                    movement_row[col_operation] = row_operation
                    document = movement["document"]
                    movement_row[col_document] = _excel_document_text(
                        row_operation, document  # type: ignore[arg-type]
                    )
                    quantity = _movement_quantity(movement)
                    if quantity > 0:
                        movement_row[col_in] = quantity
                    else:
                        movement_row[col_out] = -quantity
                    _append(movement_row, outline_level=leaf_level)
        else:  # group_by == "operation"
            by_group: dict[str, list[tuple[_ProductInfo, dict[str, object]]]] = {}
            for pid, info, _fig in products:
                for movement in movements_by_product.get(str(pid), []):
                    group_label = _excel_operation_group(str(movement["operation"]))
                    by_group.setdefault(group_label, []).append((info, movement))
            for group_label, members in sorted(by_group.items()):
                member_quantities = [_movement_quantity(m) for _i, m in members]
                group_in = sum(q for q in member_quantities if q > 0)
                group_out = sum(-q for q in member_quantities if q < 0)
                group_row: list[object] = [None] * len(headers)
                if include_seller:
                    group_row[0] = bucket["seller_name"]
                group_row[col_operation] = group_label
                group_row[col_in] = group_in
                group_row[col_out] = group_out
                _append(group_row, outline_level=top_level)
                for info, movement in members:
                    movement_row = [None] * len(headers)
                    if include_seller:
                        movement_row[0] = bucket["seller_name"]
                    movement_row[col_name] = info.name
                    movement_row[col_date] = _moscow_naive(
                        datetime.fromisoformat(str(movement["at"]))
                    )
                    row_operation = str(movement["operation"])
                    movement_row[col_operation] = row_operation
                    document = movement["document"]
                    movement_row[col_document] = _excel_document_text(
                        row_operation, document  # type: ignore[arg-type]
                    )
                    quantity = _movement_quantity(movement)
                    if quantity > 0:
                        movement_row[col_in] = quantity
                    else:
                        movement_row[col_out] = -quantity
                    _append(movement_row, outline_level=leaf_level)

    total_row: list[object] = [None] * len(headers)
    total_row[0] = "Итого"
    total_row[col_opening] = total_opening
    total_row[col_in] = total_in
    total_row[col_out] = total_out
    total_row[col_closing] = total_closing
    _append(total_row, outline_level=0)

    widths = [22, 16, 16, 20, 26, 26, 14, 10, 10, 14]
    if include_seller:
        widths = [22, *widths]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width

    import io

    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def _product_row_sort_key(
    item: tuple[uuid.UUID, _ProductInfo, ProductPeriodFigures]
) -> tuple[str, str]:
    return (item[1].name, item[1].sku_code)


_EXCEL_DOCUMENT_PREFIX_BY_OPERATION: dict[str, str] = {
    # WMS-531 ревью Astra, F9: JSON отдаёт структурированные kind/id/number —
    # фронт волен оформить их как ссылку сам. В Excel это уже конечный,
    # плоский текст (R12), и он обязан нести те же слова, что задаёт таблица
    # R2: «Приёмка №…», «Возврат №…», «Отгрузка №…» и т. д., а не голый номер.
    "Приёмка": "Приёмка {number}",
    "Возврат": "Возврат {number}",
    # Акт расхождений ссылается на строку той же приёмки (R2, R3).
    "Корректировка по акту расхождений": "Приёмка {number}",
    "Отгрузка на МП": "Отгрузка {number}",
    "Отгрузка": "Отгрузка {number}",
    "Приёмка при передаче между селлерами": "Служебная приёмка {number}",
}


def _excel_document_text(operation: str, document: dict[str, object] | None) -> str:
    """Полный текст документа для ячейки Excel — с подписью вида, а не только
    номером. FBS («Заказ WB №…»/«Заказ Ozon №…») и обе стороны передачи между
    селлерами уже несут полный текст в `operation`/`number`; «ИНВ-…» уже
    самодостаточна — их не дублируем префиксом."""
    if document is None:
        return "без документа"
    number = str(document["number"])
    template = _EXCEL_DOCUMENT_PREFIX_BY_OPERATION.get(operation)
    if template is None:
        return number
    return template.format(number=number)


def _excel_operation_group(row_label: str) -> str:
    """Группа «По операциям» для Excel по уже готовой подписи строки движения.

    Группа не всегда совпадает с подписью (акт расхождений, сторно FBS,
    обе стороны передачи между селлерами) — см. таблицу WMS-531 R2. Остальные
    подписи уже равны своей группе (Приёмка, Возврат, Отгрузка на МП,
    Отгрузка, Инвентаризация, Загрузка ТЗ, Корректировка).
    """
    if row_label == "Корректировка по акту расхождений":
        return "Корректировка"
    if row_label == "FBS, сторно":
        return "FBS"
    if row_label == "Приёмка при передаче между селлерами":
        return "Передача между селлерами"
    if row_label.startswith("Передано селлеру") or row_label.startswith("Получено от селлера"):
        return "Передача между селлерами"
    if row_label.startswith("Прочее"):
        return "Прочее"
    return row_label


def inventory_workbook_filename(date_from: datetime, date_to: datetime) -> str:
    """WMS-531 R12.2. Период — последний включённый день, а не exclusive-границу.

    Тире между датами — то же en dash, что в примере имени файла в требованиях;
    подавляем предупреждение линтера про «неоднозначный» символ намеренно.
    """
    start = date_from.astimezone(MOSCOW_TZ).date()
    end = (date_to - timedelta(microseconds=1)).astimezone(MOSCOW_TZ).date()
    return f"Остатки и движения {start:%d.%m.%Y}–{end:%d.%m.%Y}.xlsx"  # noqa: RUF001
