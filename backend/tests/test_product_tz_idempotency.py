"""Product TZ import idempotency constraint and scope coverage."""

# ruff: noqa: RUF001

from __future__ import annotations

import asyncio
import io
import time

import pytest
from httpx import AsyncClient, Response
from openpyxl import Workbook  # type: ignore[import-untyped]
from sqlalchemy.exc import IntegrityError

from app.services.product_tz_import_service import _is_idempotency_conflict

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx_bytes(*, barcode: str | None, quantity: int = 3) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "ТЗ"
    sheet.append(
        [
            "Артикул продавца",
            "Размер",
            "Штрихкод",
            "Пожелания/Инструкция по обработке, упаковке и фасовке",
            "Кол/во, заявленное клиентом",
        ]
    )
    sheet.append(["IDEMPOTENT", 46, barcode, "TZ", quantity])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


async def _scope(
    async_client: AsyncClient,
    marker: str,
) -> tuple[dict[str, str], str, str]:
    suffix = f"{marker}-{time.time_ns()}"
    register = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Idempotency {marker}",
            "slug": suffix,
            "admin_email": f"{suffix}@example.com",
            "password": "password123",
        },
    )
    assert register.status_code == 200, register.text
    headers = {"Authorization": f"Bearer {register.json()['access_token']}"}
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Warehouse", "code": f"idem-{time.time_ns()}"},
    )
    seller = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": f"Seller {marker}"},
    )
    assert warehouse.status_code == 200, warehouse.text
    assert seller.status_code in {200, 201}, seller.text
    return headers, str(seller.json()["id"]), str(warehouse.json()["id"])


async def _apply(
    async_client: AsyncClient,
    *,
    headers: dict[str, str],
    seller_id: str,
    content: bytes,
    ignore_errors: bool = False,
) -> Response:
    return await async_client.post(
        "/products/import-tz/apply",
        headers=headers,
        data={
            "seller_id": seller_id,
            "ignore_errors": str(ignore_errors).lower(),
        },
        files={"file": ("same.xlsx", content, XLSX_MIME)},
    )


def test_only_named_import_unique_error_is_idempotency_conflict() -> None:
    duplicate = IntegrityError(
        "INSERT",
        {},
        Exception(
            "UNIQUE constraint failed: "
            "product_tz_imports.tenant_id, "
            "product_tz_imports.seller_id, "
            "product_tz_imports.warehouse_scope, "
            "product_tz_imports.import_type, "
            "product_tz_imports.file_sha256"
        ),
    )
    unrelated = IntegrityError(
        "INSERT",
        {},
        Exception("FOREIGN KEY constraint failed"),
    )

    assert _is_idempotency_conflict(duplicate) is True
    assert _is_idempotency_conflict(unrelated) is False


@pytest.mark.asyncio
async def test_concurrent_same_file_adds_stock_once(
    async_client: AsyncClient,
) -> None:
    headers, seller_id, warehouse_id = await _scope(async_client, "concurrent")
    content = _xlsx_bytes(barcode="2038555555555")

    first, second = await asyncio.gather(
        _apply(
            async_client,
            headers=headers,
            seller_id=seller_id,
            content=content,
        ),
        _apply(
            async_client,
            headers=headers,
            seller_id=seller_id,
            content=content,
        ),
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    bodies = [first.json(), second.json()]
    assert sorted(body["already_applied"] for body in bodies) == [False, True]
    assert sum(body["added_quantity"] for body in bodies) == 3
    balances = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=headers,
        params={"warehouse_id": warehouse_id},
    )
    assert sum(row["quantity_in_sorting"] for row in balances.json()) == 3


@pytest.mark.asyncio
async def test_same_file_hash_is_scoped_by_tenant_and_seller(
    async_client: AsyncClient,
) -> None:
    content = _xlsx_bytes(barcode="2038666666666")
    headers_a, seller_a, _warehouse_a = await _scope(async_client, "tenant-a")
    headers_b, seller_b, _warehouse_b = await _scope(async_client, "tenant-b")

    tenant_a = await _apply(
        async_client,
        headers=headers_a,
        seller_id=seller_a,
        content=content,
    )
    tenant_b = await _apply(
        async_client,
        headers=headers_b,
        seller_id=seller_b,
        content=content,
    )
    assert tenant_a.status_code == 200, tenant_a.text
    assert tenant_b.status_code == 200, tenant_b.text
    assert tenant_a.json()["already_applied"] is False
    assert tenant_b.json()["already_applied"] is False

    second_seller = await async_client.post(
        "/sellers",
        headers=headers_a,
        json={"name": "Second seller"},
    )
    malformed = _xlsx_bytes(barcode=None, quantity=0)
    seller_a_error_file = await _apply(
        async_client,
        headers=headers_a,
        seller_id=seller_a,
        content=malformed,
        ignore_errors=True,
    )
    seller_b_error_file = await _apply(
        async_client,
        headers=headers_a,
        seller_id=str(second_seller.json()["id"]),
        content=malformed,
        ignore_errors=True,
    )
    seller_a_repeat = await _apply(
        async_client,
        headers=headers_a,
        seller_id=seller_a,
        content=malformed,
        ignore_errors=True,
    )
    assert seller_a_error_file.json()["already_applied"] is False
    assert seller_b_error_file.json()["already_applied"] is False
    assert seller_a_repeat.json()["already_applied"] is True
