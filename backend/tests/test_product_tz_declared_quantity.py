"""Declared quantities in FF product TZ imports."""

# ruff: noqa: RUF001

from __future__ import annotations

import io
import time
import uuid
from collections.abc import Sequence

import pytest
from httpx import AsyncClient
from openpyxl import Workbook  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import inventory_service
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
            "organization_name": f"TZ quantity {marker}",
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


def test_parse_declared_quantity_uses_first_matching_sheet_once() -> None:
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
    assert sum(int(row["declared_quantity"]) for row in parsed) == 10_410


@pytest.mark.asyncio
async def test_declared_quantity_apply_is_additive_and_idempotent(
    async_client: AsyncClient,
) -> None:
    headers, seller_id = await _admin_and_seller(async_client, marker="apply")
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Only warehouse", "code": "tz-qty-only"},
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
    assert preview_body["summary"]["declared_total"] == 42
    assert [row["declared_quantity"] for row in preview_body["rows"]] == [40, 2]

    first = await async_client.post(
        "/products/import-tz/apply",
        headers=headers,
        data={"seller_id": seller_id, "ignore_errors": "false"},
        files={"file": ("tz.xlsx", content, XLSX_MIME)},
    )
    assert first.status_code == 200, first.text
    assert first.json()["created_count"] == 1
    assert first.json()["updated_count"] == 1
    assert first.json()["added_quantity"] == 42
    assert first.json()["movement_count"] == 2
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
    assert sum(row["quantity_in_sorting"] for row in balances.json()) == 42
    assert sum(row["available"] for row in balances.json()) == 0
    movements = await async_client.get(
        "/operations/inventory-movements",
        headers=headers,
    )
    imported = [
        row
        for row in movements.json()
        if row["movement_type"] == "product_tz_import"
    ]
    assert sorted(row["quantity_delta"] for row in imported) == [2, 40]


@pytest.mark.asyncio
async def test_invalid_declared_quantities_roll_back_whole_apply(
    async_client: AsyncClient,
) -> None:
    headers, seller_id = await _admin_and_seller(async_client, marker="invalid")
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Only warehouse", "code": "tz-invalid-only"},
    )
    assert warehouse.status_code == 200
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
    assert body["summary"]["error_count"] == 4
    assert body["summary"]["declared_total"] == 5
    assert {row["error_code"] for row in body["rows"] if row["error_code"]} == {
        "invalid_declared_quantity"
    }

    apply = await async_client.post(
        "/products/import-tz/apply",
        headers=headers,
        data={"seller_id": seller_id, "ignore_errors": "false"},
        files={"file": ("invalid.xlsx", content, XLSX_MIME)},
    )
    assert apply.status_code == 422, apply.text
    catalog = await async_client.get(
        "/products/ff-catalog",
        headers=headers,
        params={"seller_id": seller_id},
    )
    assert catalog.status_code == 200
    assert catalog.json() == []
    movements = await async_client.get(
        "/operations/inventory-movements",
        headers=headers,
    )
    assert movements.json() == []


@pytest.mark.asyncio
async def test_apply_failure_after_first_movement_rolls_back_everything(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, seller_id = await _admin_and_seller(async_client, marker="rollback")
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Only warehouse", "code": "tz-rollback-only"},
    )
    assert warehouse.status_code == 200
    content = _workbook_bytes(
        [
            ["ART-ONE", None, 46, "2038444444401", None, "TZ", 1],
            ["ART-TWO", None, 48, "2038444444402", None, "TZ", 1],
        ]
    )
    original_record = inventory_service.record_movement_and_adjust_balance
    call_count = 0

    async def fail_on_second_movement(
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        product_id: uuid.UUID,
        storage_location_id: uuid.UUID,
        quantity_delta: int,
        movement_type: str,
    ) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("forced movement failure")
        await original_record(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=storage_location_id,
            quantity_delta=quantity_delta,
            movement_type=movement_type,
        )

    monkeypatch.setattr(
        inventory_service,
        "record_movement_and_adjust_balance",
        fail_on_second_movement,
    )
    with pytest.raises(RuntimeError, match="forced movement failure"):
        await async_client.post(
            "/products/import-tz/apply",
            headers=headers,
            data={"seller_id": seller_id, "ignore_errors": "false"},
            files={"file": ("rollback.xlsx", content, XLSX_MIME)},
        )

    catalog = await async_client.get(
        "/products/ff-catalog",
        headers=headers,
        params={"seller_id": seller_id},
    )
    assert catalog.json() == []
    movements = await async_client.get(
        "/operations/inventory-movements",
        headers=headers,
    )
    assert movements.json() == []

    monkeypatch.setattr(
        inventory_service,
        "record_movement_and_adjust_balance",
        original_record,
    )
    retry = await async_client.post(
        "/products/import-tz/apply",
        headers=headers,
        data={"seller_id": seller_id, "ignore_errors": "false"},
        files={"file": ("rollback.xlsx", content, XLSX_MIME)},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["already_applied"] is False
    assert retry.json()["added_quantity"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("warehouse_count", [0, 2])
async def test_positive_quantity_requires_exactly_one_warehouse(
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

    assert apply.status_code == 422, apply.text
    expected_code = "warehouse_required" if warehouse_count == 0 else "warehouse_ambiguous"
    assert apply.json()["detail"]["code"] == expected_code
    catalog = await async_client.get(
        "/products/ff-catalog",
        headers=headers,
        params={"seller_id": seller_id},
    )
    assert catalog.json() == []
