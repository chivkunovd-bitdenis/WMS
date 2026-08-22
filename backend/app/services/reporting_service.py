from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse

TRANSFER_TYPES = {"stock_transfer_in", "stock_transfer_out"}
PAGE_SIZE = 50
GROUP_BY_VALUES = {"product", "operation"}


def validate_period(date_from: datetime, date_to: datetime) -> None:
    if date_to <= date_from:
        raise ValueError("date_to must be after date_from")
    if date_to - date_from > timedelta(days=366):
        raise ValueError("period cannot be longer than 366 days")


async def build_inventory_report(
    session: AsyncSession, tenant_id: uuid.UUID, *, date_from: datetime,
    date_to: datetime, group_by: str, page: int, seller_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None, search: str | None = None) -> dict[str, object]:
    validate_period(date_from, date_to)
    if group_by not in GROUP_BY_VALUES:
        raise ValueError("group_by must be product or operation")
    filters = [InventoryMovement.tenant_id == tenant_id, InventoryMovement.created_at >= date_from,
        InventoryMovement.created_at < date_to, ~Warehouse.name.startswith("FBS WB ")]
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
        stmt = select(Product.id, Product.name, Product.sku_code, Product.wb_vendor_code,
            Product.wb_barcode, Seller.name, in_qty, out_qty).select_from(InventoryMovement).join(
            Product, Product.id == InventoryMovement.product_id).outerjoin(Seller,
            Seller.id == InventoryMovement.seller_id).join(
            Warehouse, Warehouse.id == InventoryMovement.warehouse_id).where(
            *filters).group_by(Product.id, Product.name, Product.sku_code, Product.wb_vendor_code,
            Product.wb_barcode, Seller.name).order_by(Product.name, Product.sku_code)
    else:
        stmt = select(InventoryMovement.movement_type, in_qty, out_qty).select_from(
            InventoryMovement).join(
            Product, Product.id == InventoryMovement.product_id).join(Warehouse,
            Warehouse.id == InventoryMovement.warehouse_id).where(*filters).group_by(
            InventoryMovement.movement_type).order_by(InventoryMovement.movement_type)
    rows = (await session.execute(stmt)).all()
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
                ~Warehouse.name.startswith("FBS WB "),
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
    incomplete_transfer = False
    if warehouse_id is not None:
        integrity_filters = [InventoryMovement.tenant_id == tenant_id,
            InventoryMovement.created_at >= date_from, InventoryMovement.created_at < date_to,
            ~Warehouse.name.startswith("FBS WB "), InventoryMovement.transfer_group_id.is_not(None)]
        if seller_id is not None:
            integrity_filters.append(InventoryMovement.seller_id == seller_id)
        # Inspect both sides of every pair, even when the report is filtered to
        # one warehouse.  Applying warehouse_id here would make every valid
        # cross-warehouse pair look incomplete because its other side is
        # intentionally outside the selected slice.
        transfer_rows = (await session.execute(select(InventoryMovement.transfer_group_id,
            InventoryMovement.product_id, InventoryMovement.seller_id,
            InventoryMovement.warehouse_id, InventoryMovement.quantity_delta).join(
            Product, Product.id == InventoryMovement.product_id).join(
            Warehouse, Warehouse.id == InventoryMovement.warehouse_id).where(*integrity_filters
            ))).all()
        transfer_groups: dict[uuid.UUID, list[tuple[uuid.UUID, uuid.UUID | None,
            uuid.UUID, int]]] = {}
        for (
            group_id, product_id, movement_seller_id, movement_warehouse_id, quantity
        ) in transfer_rows:
            transfer_groups.setdefault(group_id, []).append(
                (product_id, movement_seller_id, movement_warehouse_id, int(quantity))
            )
        incomplete_transfer = any(
            len(rows_for_group) != 2
            or rows_for_group[0][0] != rows_for_group[1][0]
            or rows_for_group[0][1] != rows_for_group[1][1]
            or rows_for_group[0][2] == rows_for_group[1][2]
            or rows_for_group[0][3] == 0
            or rows_for_group[1][3] == 0
            or rows_for_group[0][3] * rows_for_group[1][3] >= 0
            or abs(rows_for_group[0][3]) != abs(rows_for_group[1][3])
            for rows_for_group in transfer_groups.values()
        )
    start = (page - 1) * PAGE_SIZE
    result: list[dict[str, object]] = []
    for row in rows[start:start + PAGE_SIZE]:
        if group_by == "product":
            pid, name, sku, vendor, barcode, seller_name, incoming, outgoing = row
            result.append({"product_id": str(pid), "product_name": name, "sku_code": sku,
                "wb_vendor_code": vendor, "wb_barcode": barcode, "seller_name": seller_name,
                "current_balance": balances_by_product.get(pid, 0),
                "total_in": int(incoming), "total_out": int(outgoing),
                "net": int(incoming) - int(outgoing), "integrity_error": incomplete_transfer})
        else:
            movement_type, incoming, outgoing = row
            operation = {"stock_transfer_in": "Перемещение: пришло",
                "stock_transfer_out": "Перемещение: ушло"}.get(movement_type, movement_type)
            result.append({"operation": operation, "in_qty": int(incoming),
                "out_qty": int(outgoing), "net": int(incoming) - int(outgoing),
                "integrity_error": incomplete_transfer})
    return {"group_by": group_by, "page": page, "page_size": PAGE_SIZE,
        "total": len(rows), "rows": result}


async def build_inventory_csv(
    session: AsyncSession, tenant_id: uuid.UUID, *, date_from: datetime,
    date_to: datetime, group_by: str, seller_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None, search: str | None = None,
    include_seller: bool = True,
) -> bytes:
    """Build the complete, table-shaped export for the current authorised slice."""
    validate_period(date_from, date_to)
    if group_by not in GROUP_BY_VALUES:
        raise ValueError("group_by must be product or operation")

    first_page = await build_inventory_report(
        session, tenant_id, date_from=date_from, date_to=date_to,
        group_by=group_by, page=1, seller_id=seller_id,
        warehouse_id=warehouse_id, search=search,
    )
    total = cast(int, first_page["total"])
    if total == 0:
        raise ValueError("nothing to export for the selected period")
    pages: list[dict[str, object]] = [first_page]
    for page_number in range(2, (total + PAGE_SIZE - 1) // PAGE_SIZE + 1):
        pages.append(await build_inventory_report(
            session, tenant_id, date_from=date_from, date_to=date_to,
            group_by=group_by, page=page_number, seller_id=seller_id,
            warehouse_id=warehouse_id, search=search,
        ))

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    if group_by == "product":
        headers = ["Товар", "SKU", "Артикул продавца", "ШК"]
        if include_seller:
            headers.append("Селлер")
        headers.extend(["Остаток сейчас", "Приход", "Расход", "Нетто"])
        writer.writerow(headers)
        for report_page in pages:
            for row in cast(list[dict[str, Any]], report_page["rows"]):
                values = [
                    row["product_name"], row["sku_code"], row["wb_vendor_code"],
                    row["wb_barcode"],
                ]
                if include_seller:
                    values.append(row["seller_name"])
                values.extend([
                    row["current_balance"], row["total_in"], row["total_out"], row["net"]
                ])
                writer.writerow(values)
    else:
        writer.writerow(["Операция", "Приход", "Расход", "Нетто"])
        for report_page in pages:
            for row in cast(list[dict[str, Any]], report_page["rows"]):
                writer.writerow([row["operation"], row["in_qty"], row["out_qty"], row["net"]])
    return output.getvalue().encode("utf-8-sig")


async def build_overview(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    date_from: datetime,
    date_to: datetime,
    seller_id: uuid.UUID | None,
    warehouse_id: uuid.UUID | None = None,
    search: str | None = None,
) -> dict[str, object]:
    validate_period(date_from, date_to)
    movement_filter = [
        InventoryMovement.tenant_id == tenant_id,
        InventoryMovement.created_at >= date_from,
        InventoryMovement.created_at < date_to,
        InventoryMovement.transfer_group_id.is_(None),
        ~Warehouse.name.startswith("FBS WB "),
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
        ~Warehouse.name.startswith("FBS WB "),
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
        .where(InventoryBalance.tenant_id == tenant_id, ~Warehouse.name.startswith("FBS WB "))
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

    daily_stmt = (
        select(
            func.date(InventoryMovement.created_at),
            func.coalesce(
                func.sum(
                    case(
                        (InventoryMovement.quantity_delta > 0, InventoryMovement.quantity_delta),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (InventoryMovement.quantity_delta < 0, -InventoryMovement.quantity_delta),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .select_from(InventoryMovement)
        .join(Product, Product.id == InventoryMovement.product_id)
        .join(Warehouse, Warehouse.id == InventoryMovement.warehouse_id)
        .where(*movement_filter)
        .group_by(func.date(InventoryMovement.created_at))
    )
    daily = {
        str(day): {"in_qty": int(in_qty), "out_qty": int(out_qty)}
        for day, in_qty, out_qty in (await session.execute(daily_stmt)).all()
    }
    days: list[dict[str, object]] = []
    cursor = date_from.date()
    last_day = (
        date_to.date()
        if date_to.time() != datetime.min.time()
        else date_to.date() - timedelta(days=1)
    )
    while cursor <= last_day:
        item = daily.get(cursor.isoformat(), {"in_qty": 0, "out_qty": 0})
        days.append({"date": cursor.isoformat(), **item})
        cursor += timedelta(days=1)

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
        "source_freshness": None, "warnings": [],
    }
