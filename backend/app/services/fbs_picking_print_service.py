"""Read-only receipt history and current physical places for the printed FBS sheet."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.fbs_picking_service import _load_supply, _planned_qty_by_product
from app.services.sorting_location_service import SORTING_LOCATION_CODE, UNASSIGNED_LABEL

# WMS-710: retain document links for picked-to-zero places only in Imperiya's picking context.
IMPERIYA_PICK_LIST_TENANT_IDS = frozenset(
    {uuid.UUID("7b98a8aa-c03c-4649-9677-a645be45c622")}
)


async def get_picking_context(
    session: AsyncSession, tenant_id: uuid.UUID, supply_id: uuid.UUID
) -> list[dict[str, Any]]:
    supply = await _load_supply(session, tenant_id, supply_id)
    product_ids = list(_planned_qty_by_product(supply))
    if not product_ids:
        return []
    result: dict[uuid.UUID, dict[str, Any]] = {
        pid: {"product_id": str(pid), "inbound_supplies": [], "locations": [], "source_groups": []}
        for pid in product_ids
    }
    groups: dict[uuid.UUID, dict[str, dict[str, Any]]] = {pid: {} for pid in product_ids}
    params = {"tenant": tenant_id, "seller": supply.seller_id,
              "warehouse": supply.warehouse_id, "products": product_ids}
    receipts = await session.execute(text("""
        SELECT DISTINCT l.product_id, r.id, r.display_number, r.document_number,
               r.posted_at, r.created_at, r.operation_type
        FROM inbound_intake_lines l
        JOIN inbound_intake_requests r ON r.id=l.request_id
        WHERE r.tenant_id=:tenant AND r.seller_id=:seller
          AND l.product_id IN :products
          AND (l.posted_qty > 0 OR EXISTS (
              SELECT 1 FROM inventory_movements m
              WHERE m.tenant_id=:tenant AND m.product_id=l.product_id
                AND m.inbound_intake_line_id=l.id
                AND m.movement_type='inbound_intake' AND m.quantity_delta > 0
          ))
        ORDER BY r.created_at, r.id
    """).bindparams(bindparam("products", expanding=True)), params)
    for row in receipts.mappings():
        number = row["display_number"] or row["document_number"]
        date = (row["posted_at"] or row["created_at"]).strftime("%d.%m.%Y")
        label = f"{number} · {date}" if number else f"Приёмка от {date}"
        if row["operation_type"] == "return":
            label = f"Возврат {label}"
        result[row["product_id"]]["inbound_supplies"].append(label)
        kind = "В" if row["operation_type"] == "return" else "П"
        key = f"inbound:{row['id']}"
        groups[row["product_id"]][key] = {
            "key": key, "title": f"{kind}: {number or date}", "lines": [],
            "date": date, "line_keys": [],
        }
    places_params = {
        **params,
        "include_zero_quantity_places": tenant_id in IMPERIYA_PICK_LIST_TENANT_IDS,
    }
    places = await session.execute(text("""
        SELECT b.product_id, b.quantity, s.code AS location_code,
               s.id AS storage_location_id,
               b.container_kind, b.container_id,
               coalesce(wb.internal_barcode, ib.internal_barcode,
                        cp.internal_barcode, p.barcode) AS barcode,
               ib.box_number, cp.place_number, p.code AS pallet_code,
               coalesce(ib.request_id,cp.request_id,wb.inbound_request_id) AS request_id,
               origin.count_id AS inventory_count_id,
               origin_request.display_number AS origin_number,
               origin_request.document_number AS origin_document_number,
               origin_request.operation_type AS origin_operation_type,
               coalesce(origin_request.posted_at, origin_request.created_at) AS origin_date
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
        LEFT JOIN inbound_intake_requests origin_request
          ON origin_request.id=coalesce(ib.request_id,cp.request_id,wb.inbound_request_id)
          AND origin_request.tenant_id=:tenant AND origin_request.seller_id=:seller
        LEFT JOIN LATERAL (
            SELECT created.count_id FROM inventory_count_created_containers created
            JOIN inventory_counts ic ON ic.id=created.count_id AND ic.tenant_id=:tenant
            WHERE created.tenant_id=:tenant AND created.container_id=b.container_id
              AND created.container_kind=b.container_kind
            ORDER BY created.created_at, created.id LIMIT 1
        ) origin ON true
        WHERE b.tenant_id=:tenant AND s.tenant_id=:tenant
          AND s.warehouse_id=:warehouse AND b.product_id IN :products
          AND (b.quantity > 0 OR
               (:include_zero_quantity_places AND b.quantity = 0))
        ORDER BY s.code, ib.box_number, cp.place_number, barcode, b.id
    """).bindparams(bindparam("products", expanding=True)), places_params)
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
        pid = row["product_id"]
        key = f"inbound:{row['request_id']}" if row["request_id"] else ""
        if key not in groups[pid]:
            group_date = None
            if key and (row["origin_number"] or row["origin_document_number"]):
                prefix = "В" if row["origin_operation_type"] == "return" else "П"
                title = f"{prefix}: {row['origin_number'] or row['origin_document_number']}"
                if row["origin_date"] is not None:
                    group_date = row["origin_date"].strftime("%d.%m.%Y")
            elif row["inventory_count_id"]:
                key = f"inventory:{row['inventory_count_id']}"
                title = f"И: {str(row['inventory_count_id'])[:8]}"
            else:
                key, title = "unlinked", "Без привязки к документу:"
            groups[pid].setdefault(
                key,
                {"key": key, "title": title, "lines": [], "date": group_date, "line_keys": []},
            )
        cell = "" if row["location_code"] == SORTING_LOCATION_CODE else f" · {location}"
        groups[pid][key]["lines"].append(f"{container}{cell}: {row['quantity']} шт.")
        # WMS-710: ключ места той же формы, что у вкладки «Подбор»: ячейка|тара.
        groups[pid][key]["line_keys"].append(
            f"{row['storage_location_id']}|{row['container_id'] or 'loose'}"
        )
    for pid in product_ids:
        result[pid]["source_groups"] = list(groups[pid].values())
    return list(result.values())
