"""Read-only receipt history and current physical places for the printed FBS sheet."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.fbs_picking_service import _load_supply, _planned_qty_by_product
from app.services.sorting_location_service import SORTING_LOCATION_CODE, UNASSIGNED_LABEL


async def get_picking_context(
    session: AsyncSession, tenant_id: uuid.UUID, supply_id: uuid.UUID
) -> list[dict[str, Any]]:
    supply = await _load_supply(session, tenant_id, supply_id)
    product_ids = list(_planned_qty_by_product(supply))
    if not product_ids:
        return []
    result = {
        pid: {"product_id": str(pid), "inbound_supplies": [], "locations": []}
        for pid in product_ids
    }
    params = {"tenant": tenant_id, "seller": supply.seller_id,
              "warehouse": supply.warehouse_id, "products": product_ids}
    receipts = await session.execute(text("""
        SELECT DISTINCT l.product_id, r.id, r.display_number, r.document_number,
               r.posted_at, r.created_at
        FROM inbound_intake_lines l
        JOIN inbound_intake_requests r ON r.id=l.request_id
        WHERE r.tenant_id=:tenant AND r.seller_id=:seller
          AND l.product_id IN :products AND l.posted_qty > 0
          AND r.operation_type='inbound'
        ORDER BY r.created_at, r.id
    """).bindparams(bindparam("products", expanding=True)), params)
    for row in receipts.mappings():
        number = row["display_number"] or row["document_number"]
        date = (row["posted_at"] or row["created_at"]).strftime("%d.%m.%Y")
        result[row["product_id"]]["inbound_supplies"].append(
            f"{number} · {date}" if number else f"Приёмка от {date}"
        )
    places = await session.execute(text("""
        SELECT b.product_id, b.quantity, s.code AS location_code,
               b.container_kind, b.container_id,
               coalesce(wb.internal_barcode, ib.internal_barcode,
                        cp.internal_barcode, p.barcode) AS barcode,
               ib.box_number, cp.place_number, p.code AS pallet_code
        FROM inventory_balances b
        JOIN storage_locations s ON s.id=b.storage_location_id
        LEFT JOIN warehouse_boxes wb ON wb.id=b.container_id
          AND wb.tenant_id=:tenant AND wb.warehouse_id=:warehouse
          AND wb.container_kind=b.container_kind
        LEFT JOIN inbound_intake_boxes ib ON ib.tenant_id=:tenant
          AND b.container_kind='box'
          AND (ib.id=b.container_id OR
               (wb.inbound_request_id=ib.request_id AND wb.internal_barcode=ib.internal_barcode))
        LEFT JOIN inbound_intake_cargo_places cp ON cp.tenant_id=:tenant
          AND b.container_kind='cargo_place'
          AND (cp.id=b.container_id OR
               (wb.inbound_request_id=cp.request_id AND wb.internal_barcode=cp.internal_barcode))
        LEFT JOIN pallets p ON p.id=b.container_id AND p.tenant_id=:tenant
          AND p.warehouse_id=:warehouse AND b.container_kind='pallet'
        WHERE b.tenant_id=:tenant AND s.tenant_id=:tenant
          AND s.warehouse_id=:warehouse AND b.product_id IN :products
          AND b.quantity > 0
        ORDER BY s.code, ib.box_number, cp.place_number, barcode, b.id
    """).bindparams(bindparam("products", expanding=True)), params)
    for row in places.mappings():
        location = (UNASSIGNED_LABEL if row["location_code"] == SORTING_LOCATION_CODE
                    else row["location_code"])
        kind = row["container_kind"]
        barcode = row["barcode"]
        if kind == "box":
            container = f"Короб №{row['box_number']}" if row["box_number"] else "Короб"
        elif kind == "cargo_place":
            container = (f"Грузоместо №{row['place_number']}"
                         if row["place_number"] else "Грузоместо")
        elif kind == "pallet":
            container = f"Палета {row['pallet_code'] or ''}".strip()
        else:
            container = "Россыпью"
        if barcode:
            container += f" · {barcode}"
        elif kind:
            container += " · ШК не указан"
        result[row["product_id"]]["locations"].append(
            f"{location} · {container}: {row['quantity']} шт."
        )
    return list(result.values())
