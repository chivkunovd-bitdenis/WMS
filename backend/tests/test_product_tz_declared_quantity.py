"""Catalog Excel imports ignore quantity columns.

The catalog import creates/updates product cards only. Stock intake belongs to
warehouse documents, not to CAT-04.
"""


from __future__ import annotations

import io
import time
from collections.abc import Sequence

import pytest
from httpx import AsyncClient
from openpyxl import Workbook  # type: ignore[import-untyped]

from app.services.product_tz_import_service import parse_product_tz_xlsx

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
HEADERS = [
    "Артикул продавца",
    "Фото",
    "Размер",
    "Штрихкод",
    "Информация для этикетки",
    "Пожелания/Инструкция по обработке, упаковке и фасовке",
    "Кол/во, заявленное клиентом",
]


def _workbook_bytes(
    rows: Sequence[Sequence[object]],
    *,
    copy_sheet: bool = False,
) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "ТЗ Шаблон"
    ws.append(HEADERS)
    for row in rows:
        ws.append(row)
    if copy_sheet:
        wb.copy_worksheet(ws).title = "ТЗ Шаблон — копия"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def _admin_and_seller(
    async_client: AsyncClient,
    *,
    marker: str,
) -> tuple[dict[str, str], str]:
    suffix = f"{marker}-{int(time.time() * 1_000_000)}"
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"TZ quantity ignored {marker}",
            "slug": suffix,
            "admin_email": f"{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    seller = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": f"Seller {marker}"},
    )
    assert seller.status_code in {200, 201}, seller.text
    return headers, str(seller.json()["id"])


def test_parse_ignores_quantity_columns_and_uses_first_matching_sheet_once() -> None:
    quantities = [250] * 41 + [160]
    rows = [
        [
            f"ART-{index}",
            None,
            46,
            f"2038{index:09d}",
            None,
            "TZ",
            quantity,
        ]
        for index, quantity in enumerate(quantities, start=1)
    ]
    content = _workbook_bytes(rows, copy_sheet=True)

    sheet, parsed = parse_product_tz_xlsx(content, filename="tz.xlsx")

    assert sheet == "ТЗ Шаблон"
    assert len(parsed) == 42
    assert {row["declared_quantity"] for row in parsed} == {None}


@pytest.mark.asyncio
async def test_quantity_columns_do_not_create_inventory_movements(
    async_client: AsyncClient,
) -> None:
    headers, seller_id = await _admin_and_seller(async_client, marker="apply")
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Only warehouse", "code": "tz-qty-ignored"},
    )
    assert warehouse.status_code == 200, warehouse.text
    existing = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Existing",
            "sku_code": "TZ-EXISTING",
            "seller_id": seller_id,
            "wb_barcode": "2038111111111",
        },
    )
    assert existing.status_code == 200, existing.text
    content = _workbook_bytes(
        [
            ["ART-OLD", None, 46, "2038111111111", None, "Updated TZ", 40],
            ["ART-NEW", None, 48, "2038111111112", None, "New TZ", 2],
        ]
    )

    preview = await async_client.post(
        "/products/import-tz/preview",
        headers=headers,
        data={"seller_id": seller_id},
        files={"file": ("tz.xlsx", content, XLSX_MIME)},
    )
    assert preview.status_code == 200, preview.text
    preview_body = preview.json()
    assert preview_body["summary"]["declared_total"] == 0
    assert [row["declared_quantity"] for row in preview_body["rows"]] == [None, None]

    first = await async_client.post(
        "/products/import-tz/apply",
        headers=headers,
        data={"seller_id": seller_id, "ignore_errors": "false"},
        files={"file": ("tz.xlsx", content, XLSX_MIME)},
    )
    assert first.status_code == 200, first.text
    assert first.json()["created_count"] == 1
    assert first.json()["updated_count"] == 1
    assert first.json()["added_quantity"] == 0
    assert first.json()["movement_count"] == 0
    assert first.json()["already_applied"] is False

    repeat = await async_client.post(
        "/products/import-tz/apply",
        headers=headers,
        data={"seller_id": seller_id, "ignore_errors": "false"},
        files={"file": ("tz.xlsx", content, XLSX_MIME)},
    )
    assert repeat.status_code == 200, repeat.text
    assert repeat.json()["added_quantity"] == 0
    assert repeat.json()["movement_count"] == 0
    assert repeat.json()["already_applied"] is True

    balances = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=headers,
        params={"warehouse_id": warehouse.json()["id"]},
    )
    assert balances.status_code == 200, balances.text
    assert balances.json() == []
    movements = await async_client.get(
        "/operations/inventory-movements",
        headers=headers,
    )
    assert movements.json() == []


@pytest.mark.asyncio
async def test_invalid_quantity_values_are_not_catalog_row_errors(
    async_client: AsyncClient,
) -> None:
    headers, seller_id = await _admin_and_seller(async_client, marker="invalid")
    content = _workbook_bytes(
        [
            ["ART-OK", None, 46, "2038222222201", None, "TZ", 5],
            ["ART-NEG", None, 48, "2038222222202", None, "TZ", -1],
            ["ART-FRAC", None, 50, "2038222222203", None, "TZ", 1.5],
            ["ART-BOOL", None, 52, "2038222222204", None, "TZ", True],
            ["ART-TEXT", None, 54, "2038222222205", None, "TZ", "2"],
            ["ART-ZERO", None, 56, "2038222222206", None, "TZ", 0],
        ]
    )

    preview = await async_client.post(
        "/products/import-tz/preview",
        headers=headers,
        data={"seller_id": seller_id},
        files={"file": ("invalid.xlsx", content, XLSX_MIME)},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["summary"]["error_count"] == 0
    assert body["summary"]["declared_total"] == 0
    assert [row["error_code"] for row in body["rows"]] == [None] * 6

    apply = await async_client.post(
        "/products/import-tz/apply",
        headers=headers,
        data={"seller_id": seller_id, "ignore_errors": "false"},
        files={"file": ("invalid.xlsx", content, XLSX_MIME)},
    )
    assert apply.status_code == 200, apply.text
    assert apply.json()["created_count"] == 6
    assert apply.json()["added_quantity"] == 0
    assert apply.json()["movement_count"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("warehouse_count", [0, 2])
async def test_quantity_columns_do_not_require_warehouse(
    async_client: AsyncClient,
    warehouse_count: int,
) -> None:
    headers, seller_id = await _admin_and_seller(
        async_client,
        marker=f"warehouses-{warehouse_count}",
    )
    for index in range(warehouse_count):
        warehouse = await async_client.post(
            "/warehouses",
            headers=headers,
            json={
                "name": f"Warehouse {index}",
                "code": f"tz-wh-{warehouse_count}-{index}",
            },
        )
        assert warehouse.status_code == 200
    content = _workbook_bytes(
        [["ART-WH", None, 46, "2038333333333", None, "TZ", 1]]
    )

    apply = await async_client.post(
        "/products/import-tz/apply",
        headers=headers,
        data={"seller_id": seller_id, "ignore_errors": "false"},
        files={"file": ("warehouse.xlsx", content, XLSX_MIME)},
    )

    assert apply.status_code == 200, apply.text
    assert apply.json()["created_count"] == 1
    assert apply.json()["added_quantity"] == 0
