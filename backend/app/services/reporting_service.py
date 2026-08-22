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
        filters.append(Product.seller_id == seller_id)
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
            Seller.id == Product.seller_id).join(
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
    incomplete_transfer = False
    if warehouse_id is not None:
        transfer_rows = (await session.execute(select(InventoryMovement.transfer_group_id,
            func.count(InventoryMovement.id)).join(
            Product, Product.id == InventoryMovement.product_id).join(
            Warehouse, Warehouse.id == InventoryMovement.warehouse_id).where(*filters,
            InventoryMovement.transfer_group_id.is_not(None)).group_by(InventoryMovement.transfer_group_id))).all()
        incomplete_transfer = any(count < 2 for _group_id, count in transfer_rows)
    start = (page - 1) * PAGE_SIZE
    result: list[dict[str, object]] = []
    for row in rows[start:start + PAGE_SIZE]:
        if group_by == "product":
            pid, name, sku, vendor, barcode, seller_name, incoming, outgoing = row
            result.append({"product_id": str(pid), "name": name, "sku": sku,
                "vendor_code": vendor, "barcode": barcode, "seller_name": seller_name,
                "in_qty": int(incoming), "out_qty": int(outgoing),
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
        headers = ["Название", "Артикул продавца", "ШК"]
        if include_seller:
            headers.append("Селлер")
        headers.extend(["Приход", "Расход", "Нетто"])
        writer.writerow(headers)
        for report_page in pages:
            for row in cast(list[dict[str, Any]], report_page["rows"]):
                values = [row["name"], row["vendor_code"], row["barcode"]]
                if include_seller:
                    values.append(row["seller_name"])
                values.extend([row["in_qty"], row["out_qty"], row["net"]])
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
) -> dict[str, object]:
    validate_period(date_from, date_to)
    movement_filter = [
        InventoryMovement.tenant_id == tenant_id,
        InventoryMovement.created_at >= date_from,
        InventoryMovement.created_at < date_to,
        InventoryMovement.transfer_group_id.is_(None),
    ]
    if seller_id is not None:
        movement_filter.append(InventoryMovement.seller_id == seller_id)

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
    totals = (await session.execute(select(in_expr, out_expr).where(*movement_filter))).one()

    length = date_to - date_from
    previous_from, previous_to = date_from - length, date_from
    previous_filter = [
        InventoryMovement.tenant_id == tenant_id,
        InventoryMovement.created_at >= previous_from,
        InventoryMovement.created_at < previous_to,
        InventoryMovement.transfer_group_id.is_(None),
    ]
    if seller_id is not None:
        previous_filter.append(InventoryMovement.seller_id == seller_id)
    previous_out = int((await session.scalar(select(out_expr).where(*previous_filter))) or 0)
    current_out = int(totals[1] or 0)

    balance_stmt = (
        select(func.coalesce(func.sum(InventoryBalance.quantity), 0))
        .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
        .join(Warehouse, Warehouse.id == StorageLocation.warehouse_id)
        .join(Product, Product.id == InventoryBalance.product_id)
        .where(InventoryBalance.tenant_id == tenant_id)
    )
    if seller_id is not None:
        balance_stmt = balance_stmt.where(Product.seller_id == seller_id)
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
        .where(*movement_filter)
        .group_by(func.date(InventoryMovement.created_at))
    )
    daily = {
        str(day): {"in_qty": int(in_qty), "out_qty": int(out_qty)}
        for day, in_qty, out_qty in (await session.execute(daily_stmt)).all()
    }
    days: list[dict[str, object]] = []
    cursor = date_from.date()
    while cursor < date_to.date():
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
