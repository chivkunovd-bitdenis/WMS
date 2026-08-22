from __future__ import annotations

import csv
import io
import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from app.models.background_job import BackgroundJob
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse
from app.services.inventory_movement_report_service import (
    REPORT_MOVEMENT_TYPE_GROUPS,
    movement_group_label,
)

TRANSFER_TYPES = {"stock_transfer_in", "stock_transfer_out"}
PAGE_SIZE = 50
GROUP_BY_VALUES = {"product", "operation"}
PRODUCT_SORTS = {"name", "sku", "in_qty", "out_qty", "net"}
OPERATION_SORTS = {"operation", "in_qty", "out_qty", "net"}
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


def operation_label(movement_type: str) -> str:
    if movement_type == "stock_transfer_in":
        return "Перемещение: пришло"
    if movement_type == "stock_transfer_out":
        return "Перемещение: ушло"
    return movement_group_label(movement_type)


def operation_group_expr() -> ColumnElement[str]:
    return case(
        *(
            (InventoryMovement.movement_type == movement_type, operation_label(movement_type))
            for movement_type in REPORT_MOVEMENT_TYPE_GROUPS
        ),
        else_="Прочее",
    )


def validated_sort(
    group_by: str, sort_by: str | None, sort_order: str
) -> tuple[str, str]:
    if group_by not in GROUP_BY_VALUES:
        raise ValueError("group_by must be product or operation")
    allowed_sorts = PRODUCT_SORTS if group_by == "product" else OPERATION_SORTS
    resolved_sort = sort_by or ("name" if group_by == "product" else "operation")
    if resolved_sort not in allowed_sorts:
        raise ValueError("unsupported sort_by")
    if sort_order not in {"asc", "desc"}:
        raise ValueError("sort_order must be asc or desc")
    return resolved_sort, sort_order


async def build_inventory_report(
    session: AsyncSession, tenant_id: uuid.UUID, *, date_from: datetime,
    date_to: datetime, group_by: str, page: int, seller_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None, search: str | None = None,
    sort_by: str | None = None, sort_order: str = "asc",
) -> dict[str, object]:
    date_from, date_to = normalize_period(date_from, date_to)
    sort_by, sort_order = validated_sort(group_by, sort_by, sort_order)
    filters = [InventoryMovement.tenant_id == tenant_id, InventoryMovement.created_at >= date_from,
        InventoryMovement.created_at < date_to, Warehouse.is_operational.is_(True)]
    # Transfers are an internal flow.  They are useful only when an operator
    # narrows the report to one warehouse, where each side is meaningful.
    if warehouse_id is None:
        filters.append(InventoryMovement.transfer_group_id.is_(None))
    if seller_id is not None:
        # The movement owns the seller at event time.  Filtering through the
        # mutable product relation would move historical rows when a product
        # is reassigned later.
        filters.append(InventoryMovement.seller_id == seller_id)
    if warehouse_id is not None:
        filters.append(InventoryMovement.warehouse_id == warehouse_id)
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(or_(Product.name.ilike(pattern), Product.sku_code.ilike(pattern),
            Product.wb_vendor_code.ilike(pattern), Product.wb_barcode.ilike(pattern)))
    in_qty = func.coalesce(func.sum(case((InventoryMovement.quantity_delta > 0,
        InventoryMovement.quantity_delta), else_=0)), 0)
    out_qty = func.coalesce(func.sum(case((InventoryMovement.quantity_delta < 0,
        -InventoryMovement.quantity_delta), else_=0)), 0)
    if group_by == "product":
        grouped = select(
            Product.id.label("product_id"), Product.name.label("product_name"),
            Product.sku_code.label("sku_code"), Product.wb_vendor_code.label("wb_vendor_code"),
            Product.wb_barcode, Seller.name, in_qty, out_qty,
        ).select_from(InventoryMovement).join(
            Product, Product.id == InventoryMovement.product_id).outerjoin(Seller,
            Seller.id == InventoryMovement.seller_id).join(
            Warehouse, Warehouse.id == InventoryMovement.warehouse_id).where(
            *filters).group_by(Product.id, Product.name, Product.sku_code, Product.wb_vendor_code,
            Product.wb_barcode, Seller.name)
        sort_columns = {
            "name": Product.name, "sku": Product.sku_code, "in_qty": in_qty,
            "out_qty": out_qty, "net": in_qty - out_qty,
        }
        grouped = grouped.order_by(
            sort_columns[sort_by].desc() if sort_order == "desc" else sort_columns[sort_by].asc(),
            Product.id,
        )
    else:
        operation = operation_group_expr()
        grouped = select(
            operation.label("operation"), in_qty, out_qty,
        ).select_from(InventoryMovement).join(
            Product, Product.id == InventoryMovement.product_id).join(Warehouse,
            Warehouse.id == InventoryMovement.warehouse_id).where(*filters).group_by(
            operation)
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
    balances_by_product: dict[uuid.UUID, int] = {}
    if group_by == "product" and rows:
        product_ids = [row[0] for row in rows]
        balance_stmt = (
            select(
                InventoryBalance.product_id,
                func.coalesce(func.sum(InventoryBalance.quantity), 0),
            )
            .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
            .join(Warehouse, Warehouse.id == StorageLocation.warehouse_id)
            .join(Product, Product.id == InventoryBalance.product_id)
            .where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id.in_(product_ids),
                Warehouse.is_operational.is_(True),
            )
            .group_by(InventoryBalance.product_id)
        )
        if warehouse_id is not None:
            balance_stmt = balance_stmt.where(Warehouse.id == warehouse_id)
        if seller_id is not None:
            balance_stmt = balance_stmt.where(Product.seller_id == seller_id)
        balances_by_product = {
            product_id: int(quantity)
            for product_id, quantity in (await session.execute(balance_stmt)).all()
        }
    incomplete_transfer_product_ids: set[uuid.UUID] = set()
    incomplete_transfer_operations: set[str] = set()
    if warehouse_id is not None:
        visible_transfer_group_ids = select(InventoryMovement.transfer_group_id).where(
            InventoryMovement.tenant_id == tenant_id,
            InventoryMovement.created_at >= date_from,
            InventoryMovement.created_at < date_to,
            InventoryMovement.warehouse_id == warehouse_id,
            InventoryMovement.transfer_group_id.is_not(None),
        )
        integrity_filters = [InventoryMovement.tenant_id == tenant_id,
            InventoryMovement.transfer_group_id.in_(visible_transfer_group_ids)]
        if seller_id is not None:
            integrity_filters.append(InventoryMovement.seller_id == seller_id)
        # Inspect both sides of every pair, even when the report is filtered to
        # one warehouse.  Applying warehouse_id here would make every valid
        # cross-warehouse pair look incomplete because its other side is
        # intentionally outside the selected slice.
        transfer_rows = (await session.execute(select(InventoryMovement.transfer_group_id,
            InventoryMovement.product_id, InventoryMovement.seller_id,
            InventoryMovement.warehouse_id, InventoryMovement.quantity_delta,
            InventoryMovement.movement_type).where(*integrity_filters))).all()
        transfer_groups: dict[uuid.UUID, list[tuple[uuid.UUID, uuid.UUID | None,
            uuid.UUID, int, str]]] = {}
        for (
            group_id, product_id, movement_seller_id, movement_warehouse_id, quantity, movement_type
        ) in transfer_rows:
            transfer_groups.setdefault(group_id, []).append(
                (
                    product_id, movement_seller_id, movement_warehouse_id,
                    int(quantity), movement_type,
                )
            )
        for rows_for_group in transfer_groups.values():
            is_complete = (
                len(rows_for_group) == 2
                and rows_for_group[0][0] == rows_for_group[1][0]
                and rows_for_group[0][1] == rows_for_group[1][1]
                and rows_for_group[0][2] != rows_for_group[1][2]
                and {row[4] for row in rows_for_group} == TRANSFER_TYPES
                and rows_for_group[0][3] != 0
                and rows_for_group[1][3] != 0
                and rows_for_group[0][3] * rows_for_group[1][3] < 0
                and abs(rows_for_group[0][3]) == abs(rows_for_group[1][3])
            )
            if not is_complete:
                incomplete_transfer_product_ids.update(row[0] for row in rows_for_group)
                incomplete_transfer_operations.update(
                    operation_label(row[4]) for row in rows_for_group
                )
    result: list[dict[str, object]] = []
    for row in rows:
        if group_by == "product":
            pid, name, sku, vendor, barcode, seller_name, incoming, outgoing = row
            result.append({"product_id": str(pid), "product_name": name, "sku_code": sku,
                "wb_vendor_code": vendor, "wb_barcode": barcode, "seller_name": seller_name,
                "current_balance": balances_by_product.get(pid, 0),
                "total_in": int(incoming), "total_out": int(outgoing),
                "net": int(incoming) - int(outgoing),
                "integrity_error": pid in incomplete_transfer_product_ids})
        else:
            operation, incoming, outgoing = row
            result.append({"operation": operation, "in_qty": int(incoming),
                "out_qty": int(outgoing), "net": int(incoming) - int(outgoing),
                "integrity_error": operation in incomplete_transfer_operations})
    return {"group_by": group_by, "page": page, "page_size": PAGE_SIZE,
        "total": total, "rows": result}


async def build_inventory_csv(
    session: AsyncSession, tenant_id: uuid.UUID, *, date_from: datetime,
    date_to: datetime, group_by: str, seller_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None, search: str | None = None,
    include_seller: bool = True, sort_by: str | None = None,
    sort_order: str = "asc",
) -> AsyncIterator[bytes]:
    """Stream the complete, table-shaped export for the authorised slice."""
    date_from, date_to = normalize_period(date_from, date_to)
    sort_by, sort_order = validated_sort(group_by, sort_by, sort_order)

    # The export deliberately does not page through ``build_inventory_report``:
    # doing so used to rerun the complete GROUP BY for every 50 rows and built
    # the whole file in memory before returning its first byte.
    filters = [
        InventoryMovement.tenant_id == tenant_id,
        InventoryMovement.created_at >= date_from,
        InventoryMovement.created_at < date_to,
        Warehouse.is_operational.is_(True),
    ]
    if warehouse_id is None:
        filters.append(InventoryMovement.transfer_group_id.is_(None))
    if seller_id is not None:
        filters.append(InventoryMovement.seller_id == seller_id)
    if warehouse_id is not None:
        filters.append(InventoryMovement.warehouse_id == warehouse_id)
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                Product.name.ilike(pattern), Product.sku_code.ilike(pattern),
                Product.wb_vendor_code.ilike(pattern), Product.wb_barcode.ilike(pattern),
            )
        )

    in_qty = func.coalesce(func.sum(case((InventoryMovement.quantity_delta > 0,
        InventoryMovement.quantity_delta), else_=0)), 0)
    out_qty = func.coalesce(func.sum(case((InventoryMovement.quantity_delta < 0,
        -InventoryMovement.quantity_delta), else_=0)), 0)
    if group_by == "product":
        balance_location = aliased(StorageLocation)
        balance_warehouse = aliased(Warehouse)
        balance_filters = [
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id == Product.id,
            balance_warehouse.is_operational.is_(True),
        ]
        if warehouse_id is not None:
            balance_filters.append(balance_warehouse.id == warehouse_id)
        if seller_id is not None:
            balance_filters.append(Product.seller_id == seller_id)
        current_balance = (
            select(func.coalesce(func.sum(InventoryBalance.quantity), 0))
            .join(balance_location, balance_location.id == InventoryBalance.storage_location_id)
            .join(balance_warehouse, balance_warehouse.id == balance_location.warehouse_id)
            .where(*balance_filters)
            .correlate(Product)
            .scalar_subquery()
        )
        grouped = select(
            Product.id.label("product_id"), Product.name.label("product_name"),
            Product.sku_code.label("sku_code"), Product.wb_vendor_code.label("wb_vendor_code"),
            Product.wb_barcode, Seller.name.label("seller_name"), in_qty.label("in_qty"),
            out_qty.label("out_qty"), current_balance.label("current_balance"),
        ).select_from(InventoryMovement).join(
            Product, Product.id == InventoryMovement.product_id).outerjoin(
            Seller, Seller.id == InventoryMovement.seller_id).join(
            Warehouse, Warehouse.id == InventoryMovement.warehouse_id).where(*filters).group_by(
            Product.id, Product.name, Product.sku_code, Product.wb_vendor_code,
            Product.wb_barcode, Seller.name,
        )
        sort_columns = {
            "name": Product.name, "sku": Product.sku_code, "in_qty": in_qty,
            "out_qty": out_qty, "net": in_qty - out_qty,
        }
        grouped = grouped.order_by(
            sort_columns[sort_by].desc() if sort_order == "desc" else sort_columns[sort_by].asc(),
            Product.id,
        )
    else:
        operation = operation_group_expr()
        grouped = select(
            operation.label("operation"), in_qty.label("in_qty"),
            out_qty.label("out_qty"),
        ).select_from(InventoryMovement).join(
            Product, Product.id == InventoryMovement.product_id).join(
            Warehouse, Warehouse.id == InventoryMovement.warehouse_id).where(*filters).group_by(
            operation)
        sort_columns = {
            "operation": operation, "in_qty": in_qty,
            "out_qty": out_qty, "net": in_qty - out_qty,
        }
        grouped = grouped.order_by(
            sort_columns[sort_by].desc() if sort_order == "desc" else sort_columns[sort_by].asc(),
            operation,
        )

    if (await session.execute(grouped.limit(1))).first() is None:
        raise ValueError("nothing to export for the selected period")

    def csv_line(values: Sequence[object]) -> bytes:
        output = io.StringIO(newline="")
        csv.writer(output, lineterminator="\n").writerow(values)
        return output.getvalue().encode("utf-8")

    async def stream() -> AsyncIterator[bytes]:
        if group_by == "product":
            headers = ["Товар", "Название", "Артикул продавца", "ШК"]
            if include_seller:
                headers.append("Селлер")
            headers.extend(["Остаток сейчас", "Приход", "Расход", "Нетто"])
            yield b"\xef\xbb\xbf" + csv_line(headers)

            result = await session.stream(grouped)
            async for (
                _product_id, name, sku, vendor, barcode, seller_name, incoming, outgoing, balance
            ) in result:
                values: list[object] = [sku, name, vendor, barcode]
                if include_seller:
                    values.append(seller_name)
                values.extend(
                    [int(balance), int(incoming), int(outgoing), int(incoming) - int(outgoing)]
                )
                yield csv_line(values)
            return

        yield b"\xef\xbb\xbf" + csv_line(["Операция", "Приход", "Расход", "Нетто"])
        result = await session.stream(grouped)
        async for operation, incoming, outgoing in result:
            yield csv_line([operation, int(incoming), int(outgoing), int(incoming) - int(outgoing)])

    return stream()


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
    date_from, date_to = normalize_period(date_from, date_to)
    movement_filter = [
        InventoryMovement.tenant_id == tenant_id,
        InventoryMovement.created_at >= date_from,
        InventoryMovement.created_at < date_to,
        InventoryMovement.transfer_group_id.is_(None),
        Warehouse.is_operational.is_(True),
    ]
    if warehouse_id is not None:
        movement_filter.append(InventoryMovement.warehouse_id == warehouse_id)
    if seller_id is not None:
        movement_filter.append(InventoryMovement.seller_id == seller_id)
    if search:
        pattern = f"%{search.strip()}%"
        movement_filter.extend(
            [
                Product.id == InventoryMovement.product_id,
                or_(
                    Product.name.ilike(pattern),
                    Product.sku_code.ilike(pattern),
                    Product.wb_vendor_code.ilike(pattern),
                    Product.wb_barcode.ilike(pattern),
                ),
            ]
        )

    in_expr = func.coalesce(
        func.sum(
            case(
                (InventoryMovement.quantity_delta > 0, InventoryMovement.quantity_delta),
                else_=0,
            )
        ),
        0,
    )
    out_expr = func.coalesce(
        func.sum(
            case(
                (InventoryMovement.quantity_delta < 0, -InventoryMovement.quantity_delta),
                else_=0,
            )
        ),
        0,
    )
    totals = (
        await session.execute(
            select(in_expr, out_expr)
            .select_from(InventoryMovement)
            .join(Product, Product.id == InventoryMovement.product_id)
            .join(Warehouse, Warehouse.id == InventoryMovement.warehouse_id)
            .where(*movement_filter)
        )
    ).one()

    length = date_to - date_from
    previous_from, previous_to = date_from - length, date_from
    previous_filter = [
        InventoryMovement.tenant_id == tenant_id,
        InventoryMovement.created_at >= previous_from,
        InventoryMovement.created_at < previous_to,
        InventoryMovement.transfer_group_id.is_(None),
        Warehouse.is_operational.is_(True),
    ]
    if seller_id is not None:
        previous_filter.append(InventoryMovement.seller_id == seller_id)
    if warehouse_id is not None:
        previous_filter.append(InventoryMovement.warehouse_id == warehouse_id)
    if search:
        pattern = f"%{search.strip()}%"
        previous_filter.extend(
            [
                Product.id == InventoryMovement.product_id,
                or_(
                    Product.name.ilike(pattern),
                    Product.sku_code.ilike(pattern),
                    Product.wb_vendor_code.ilike(pattern),
                    Product.wb_barcode.ilike(pattern),
                ),
            ]
        )
    previous_out = int(
        (
            await session.scalar(
                select(out_expr)
                .select_from(InventoryMovement)
                .join(Product, Product.id == InventoryMovement.product_id)
                .join(Warehouse, Warehouse.id == InventoryMovement.warehouse_id)
                .where(*previous_filter)
            )
        )
        or 0
    )
    current_out = int(totals[1] or 0)

    balance_stmt = (
        select(func.coalesce(func.sum(InventoryBalance.quantity), 0))
        .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
        .join(Warehouse, Warehouse.id == StorageLocation.warehouse_id)
        .join(Product, Product.id == InventoryBalance.product_id)
        .where(InventoryBalance.tenant_id == tenant_id, Warehouse.is_operational.is_(True))
    )
    if seller_id is not None:
        balance_stmt = balance_stmt.where(Product.seller_id == seller_id)
    if warehouse_id is not None:
        balance_stmt = balance_stmt.where(Warehouse.id == warehouse_id)
    if search:
        pattern = f"%{search.strip()}%"
        balance_stmt = balance_stmt.where(
            or_(
                Product.name.ilike(pattern),
                Product.sku_code.ilike(pattern),
                Product.wb_vendor_code.ilike(pattern),
                Product.wb_barcode.ilike(pattern),
            )
        )
    current_balance = int((await session.scalar(balance_stmt)) or 0)

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
        .join(Warehouse, Warehouse.id == InventoryMovement.warehouse_id)
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
        .join(Warehouse, Warehouse.id == InventoryMovement.warehouse_id)
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

    legacy_stmt = select(func.count()).select_from(InventoryMovement).join(
        Warehouse, Warehouse.id == InventoryMovement.warehouse_id
    ).where(*movement_filter, InventoryMovement.reporting_dimensions_legacy.is_(True))
    legacy_count = int((await session.scalar(legacy_stmt)) or 0)

    freshness_filters = [
        FbsWarehouseBinding.tenant_id == tenant_id,
        FbsWarehouseBinding.is_active.is_(True),
        FbsWarehouseBinding.stock_sync_enabled.is_(True),
    ]
    if seller_id is not None:
        freshness_filters.append(FbsWarehouseBinding.seller_id == seller_id)
    if warehouse_id is not None:
        freshness_filters.append(FbsWarehouseBinding.wms_warehouse_id == warehouse_id)
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
        "current_balance": current_balance,
        "in_qty": int(totals[0] or 0), "out_qty": current_out,
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
    }
