"""WMS-497 кусок 1: данные печатного листа инвентаризации (R4-R8, R13).

Проверки из docs/requirements/WMS-497.md, часть, доступная без фронта:
- шапка (номер, автор, дата) совпадает с тем, что уже отдаёт экран документа;
- строки «Склад/Селлер/Категория/Товары» печатаются только для заданного при
  создании отбора, у документа «по объекту» — только «По объекту» (R4);
- выбор товаров сохраняется в документе и переживает повторное открытие (R5);
- одна строка на товар документа, даже если он лежит в нескольких местах (R6);
- ШК/артикул — с учётом площадки, Ozon-only товар (R7);
- «Всего»/«В резерве» — тот же расчёт, что отдаёт сводка каталога (R8);
- границы арендатора и права доступа (R13);
- запрос листа ничего не пишет в базу.

R2, R9-R12 (что печатать, зебра, вёрстка, сбой окна печати) — кусок 2, фронт.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderReservation
from app.models.inventory_count import InventoryCount
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.stock_direction import StockDirection
from tests.auth_helpers import set_password_via_link
from tests.test_inventory_counts import TenantSetup, _balance, _product, _seller, _tenant


async def _product_full(
    async_client: AsyncClient,
    setup: TenantSetup,
    *,
    name: str,
    seller_id: uuid.UUID | None = None,
    wb_barcode: str | None = None,
    wb_vendor_code: str | None = None,
) -> uuid.UUID:
    response = await async_client.post(
        "/products",
        headers=setup.headers,
        json={
            "name": name,
            "sku_code": f"WMS497-{uuid.uuid4().hex[:12]}",
            "seller_id": str(seller_id) if seller_id is not None else None,
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "wb_barcode": wb_barcode,
            "wb_vendor_code": wb_vendor_code,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["id"])


async def _set_category(product_id: uuid.UUID, category: str) -> None:
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        product.category = category
        await session.commit()


async def _ozon_link(
    setup: TenantSetup,
    product_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    offer_id: str,
    barcodes: list[str],
) -> None:
    async with SessionLocal() as session:
        session.add(
            ProductMarketplaceLink(
                tenant_id=setup.tenant_id,
                seller_id=seller_id,
                product_id=product_id,
                marketplace="ozon",
                external_offer_id=offer_id,
                external_barcodes=barcodes,
                is_active=True,
            )
        )
        await session.commit()


async def _reserve_fbs(
    setup: TenantSetup, seller_id: uuid.UUID, product_id: uuid.UUID, quantity: int
) -> None:
    async with SessionLocal() as session:
        now = datetime.now(UTC)
        order = FbsOrder(
            tenant_id=setup.tenant_id,
            seller_id=seller_id,
            product_id=product_id,
            warehouse_id=setup.warehouse_id,
            wb_order_id=int(time.time_ns() % 1_000_000_000),
            created_at_wb=now,
            deadline_at=now,
            mapping_status="mapped",
            reserve_status="not_published",
            status="new",
        )
        session.add(order)
        await session.flush()
        session.add(
            FbsOrderReservation(
                tenant_id=setup.tenant_id,
                fbs_order_id=order.id,
                product_id=product_id,
                warehouse_id=setup.warehouse_id,
                quantity=quantity,
            )
        )
        await session.commit()


async def _direction(setup: TenantSetup, product_id: uuid.UUID, quantity: int) -> None:
    async with SessionLocal() as session:
        session.add(
            StockDirection(
                tenant_id=setup.tenant_id,
                product_id=product_id,
                name="WMS497 направление",
                quantity=quantity,
            )
        )
        await session.commit()


async def _create(
    async_client: AsyncClient,
    setup: TenantSetup,
    body: dict[str, object],
) -> dict[str, object]:
    response = await async_client.post(
        "/operations/inventory-counts", headers=setup.headers, json=body
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _print_sheet(
    async_client: AsyncClient, setup: TenantSetup, count_id: str
) -> dict[str, object]:
    response = await async_client.get(
        f"/operations/inventory-counts/{count_id}/print-sheet",
        headers=setup.headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _staff_without_inventory(
    async_client: AsyncClient, setup: TenantSetup
) -> dict[str, str]:
    suffix = uuid.uuid4().hex[:10]
    email = f"wms497-staff-{suffix}@example.com"
    created = await async_client.post(
        "/auth/staff-accounts",
        headers=setup.headers,
        json={"full_name": "Без прав", "email": email},
    )
    assert created.status_code == 201, created.text
    permissions = await async_client.patch(
        f"/auth/staff-accounts/{created.json()['id']}/permissions",
        headers=setup.headers,
        json={
            "settings": False,
            "mp_shipments": False,
            "reception": False,
            "cells": False,
            "inventory": False,
            "packaging": False,
        },
    )
    assert permissions.status_code == 200, permissions.text
    await set_password_via_link(async_client, email, "password123")
    login = await async_client.post(
        "/auth/login", json={"email": email, "password": "password123"}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_print_sheet_header_matches_document_screen(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "PrintHeader")
    product = await _product(async_client, setup, name="Товар")
    await _balance(setup, product, 5)
    count = await _create(
        async_client,
        setup,
        {"source": "planned", "filters": {"warehouse_id": str(setup.warehouse_id)}},
    )

    detail = await async_client.get(
        f"/operations/inventory-counts/{count['id']}", headers=setup.headers
    )
    assert detail.status_code == 200, detail.text

    sheet = await _print_sheet(async_client, setup, count["id"])
    assert sheet["number"] == detail.json()["number"]
    assert sheet["created_by"] == detail.json()["created_by"]
    assert sheet["created_at"] == detail.json()["created_at"]
    assert sheet["number"].startswith("ИНВ-")


@pytest.mark.asyncio
async def test_print_sheet_prints_only_the_filters_set_at_creation(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "PrintFilters")
    seller = await _seller(async_client, setup, "Селлер WMS497")
    p1 = await _product_full(
        async_client, setup, name="Платье", seller_id=seller,
        wb_barcode="2000000000011", wb_vendor_code="W497-DRESS",
    )
    p2 = await _product_full(
        async_client, setup, name="Платье", seller_id=seller,
        wb_barcode="2000000000028", wb_vendor_code="W497-DRESS",
    )
    await _set_category(p1, "WMS497 Платья")
    await _set_category(p2, "WMS497 Платья")
    await _balance(setup, p1, 5)
    await _balance(setup, p2, 3)

    full = await _create(
        async_client,
        setup,
        {
            "source": "planned",
            "filters": {
                "warehouse_id": str(setup.warehouse_id),
                "seller_id": str(seller),
                "category": "WMS497 Платья",
                "product_ids": [str(p1), str(p2)],
            },
        },
    )
    full_sheet = await _print_sheet(async_client, setup, full["id"])
    assert full_sheet["filters"]["object"] is False
    assert full_sheet["filters"]["warehouse_name"] == "Склад PrintFilters"
    assert full_sheet["filters"]["seller_name"] == "Селлер WMS497"
    assert full_sheet["filters"]["category"] == "WMS497 Платья"
    # Один и тот же артикул у обоих размеров карточки — печатается один раз.
    assert full_sheet["filters"]["product_articles"] == ["W497-DRESS"]

    warehouse_only = await _create(
        async_client,
        setup,
        {"source": "planned", "filters": {"warehouse_id": str(setup.warehouse_id)}},
    )
    bare_sheet = await _print_sheet(async_client, setup, warehouse_only["id"])
    assert bare_sheet["filters"]["object"] is False
    assert bare_sheet["filters"]["warehouse_name"] == "Склад PrintFilters"
    assert bare_sheet["filters"]["seller_name"] is None
    assert bare_sheet["filters"]["category"] is None
    assert bare_sheet["filters"]["product_articles"] == []


@pytest.mark.asyncio
async def test_print_sheet_object_source_prints_only_by_object(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "PrintObject")
    product = await _product(async_client, setup, name="Товар по объекту")
    await _balance(setup, product, 4)

    count = await _create(
        async_client,
        setup,
        {
            "source": "object",
            "object": {"type": "storage_location", "id": str(setup.location_id)},
        },
    )
    sheet = await _print_sheet(async_client, setup, count["id"])
    assert sheet["filters"] == {
        "object": True,
        "warehouse_name": None,
        "seller_name": None,
        "category": None,
        "product_articles": [],
    }


@pytest.mark.asyncio
async def test_print_sheet_selected_products_persist_after_reopen(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "PrintSelection")
    p1 = await _product_full(
        async_client, setup, name="Платье", wb_barcode="3000000000011",
        wb_vendor_code="W497-DRESS",
    )
    p2 = await _product_full(
        async_client, setup, name="Платье", wb_barcode="3000000000028",
        wb_vendor_code="W497-DRESS",
    )
    ozon_seller = await _seller(async_client, setup, "OzonSeller")
    p3 = await _product_full(async_client, setup, name="Товар Ozon", seller_id=ozon_seller)
    await _ozon_link(setup, p3, ozon_seller, offer_id="W497-OZ", barcodes=["4000000000015"])
    await _balance(setup, p1, 10)
    await _balance(setup, p2, 5)
    await _balance(setup, p3, 4)

    count = await _create(
        async_client,
        setup,
        {
            "source": "planned",
            "filters": {
                "warehouse_id": str(setup.warehouse_id),
                "product_ids": [str(p1), str(p2), str(p3)],
            },
        },
    )

    for _ in range(2):
        reopened = await async_client.get(
            f"/operations/inventory-counts/{count['id']}", headers=setup.headers
        )
        assert reopened.status_code == 200
        sheet = await _print_sheet(async_client, setup, count["id"])
        assert sheet["filters"]["product_articles"] == ["W497-DRESS", "W497-OZ"]
        assert sheet["filters"]["seller_name"] is None
        assert sheet["filters"]["category"] is None


@pytest.mark.asyncio
async def test_print_sheet_without_selection_has_no_products_line(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "PrintNoSelection")
    product = await _product(async_client, setup, name="Товар")
    await _balance(setup, product, 2)

    for filters in (
        {"warehouse_id": str(setup.warehouse_id)},
        {"warehouse_id": str(setup.warehouse_id), "product_ids": []},
        {"warehouse_id": str(setup.warehouse_id), "all": True},
    ):
        count = await _create(
            async_client, setup, {"source": "planned", "filters": filters}
        )
        sheet = await _print_sheet(async_client, setup, count["id"])
        assert sheet["filters"]["product_articles"] == []


@pytest.mark.asyncio
async def test_print_sheet_one_row_per_product_across_locations(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "PrintOneRow")
    product = await _product(async_client, setup, name="Товар в трёх местах")
    await _balance(setup, product, 10)
    location2 = await async_client.post(
        f"/warehouses/{setup.warehouse_id}/locations",
        headers=setup.headers,
        json={"code": "B-second"},
    )
    assert location2.status_code == 200
    await _balance(setup, product, 5, location_id=uuid.UUID(location2.json()["id"]))

    count = await _create(
        async_client,
        setup,
        {"source": "planned", "filters": {"warehouse_id": str(setup.warehouse_id)}},
    )
    sheet = await _print_sheet(async_client, setup, count["id"])
    rows = [row for row in sheet["rows"] if row["product_id"] == str(product)]
    assert len(rows) == 1
    assert rows[0]["total"] == 15
    assert rows[0]["reserved"] == 0


@pytest.mark.asyncio
async def test_print_sheet_totals_match_balances_summary_with_reservations(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "PrintTotals")
    seller = await _seller(async_client, setup, "Селлер с бронью")
    product = await _product(async_client, setup, name="Товар с бронью", seller_id=seller)
    await _balance(setup, product, 20)
    await _reserve_fbs(setup, seller, product, 2)
    await _direction(setup, product, 1)

    count = await _create(
        async_client,
        setup,
        {"source": "planned", "filters": {"warehouse_id": str(setup.warehouse_id)}},
    )
    sheet = await _print_sheet(async_client, setup, count["id"])
    row = next(row for row in sheet["rows"] if row["product_id"] == str(product))

    summary = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=setup.headers,
        params={"product_id": str(product)},
    )
    assert summary.status_code == 200, summary.text
    summary_row = next(r for r in summary.json() if r["product_id"] == str(product))

    assert row["total"] == summary_row["quantity"] == 20
    assert row["reserved"] == summary_row["reserved"] == 3


@pytest.mark.asyncio
async def test_print_sheet_movement_after_creation_shows_current_numbers(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "PrintCurrent")
    seller = await _seller(async_client, setup, "Селлер")
    product = await _product(async_client, setup, name="Товар", seller_id=seller)
    await _balance(setup, product, 10)
    count = await _create(
        async_client,
        setup,
        {"source": "planned", "filters": {"warehouse_id": str(setup.warehouse_id)}},
    )
    before = await _print_sheet(async_client, setup, count["id"])
    row_before = next(r for r in before["rows"] if r["product_id"] == str(product))
    assert row_before["total"] == 10

    await _reserve_fbs(setup, seller, product, 4)
    after = await _print_sheet(async_client, setup, count["id"])
    row_after = next(r for r in after["rows"] if r["product_id"] == str(product))
    assert row_after["total"] == 10
    assert row_after["reserved"] == 4

    # Числится в документе не пересчиталось — печать листа не трогает документ.
    detail = await async_client.get(
        f"/operations/inventory-counts/{count['id']}", headers=setup.headers
    )
    line = detail.json()["lines"][0]
    assert line["expected_quantity"] == 10


@pytest.mark.asyncio
async def test_print_sheet_ozon_only_product_uses_link_barcode_and_offer_id(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "PrintOzon")
    seller = await _seller(async_client, setup, "OzonOnly")
    product = await _product_full(async_client, setup, name="Товар Ozon", seller_id=seller)
    await _ozon_link(
        setup, product, seller, offer_id="W497-OZ", barcodes=["9000000000012"]
    )
    await _balance(setup, product, 4)

    count = await _create(
        async_client,
        setup,
        {"source": "planned", "filters": {"warehouse_id": str(setup.warehouse_id)}},
    )
    sheet = await _print_sheet(async_client, setup, count["id"])
    row = next(r for r in sheet["rows"] if r["product_id"] == str(product))
    assert row["barcode"] == "9000000000012"
    assert row["article"] == "W497-OZ"


@pytest.mark.asyncio
async def test_print_sheet_product_without_any_article_falls_back_to_sku(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "PrintNoArticle")
    product = await _product(async_client, setup, name="Товар без артикулов")
    await _balance(setup, product, 1)
    async with SessionLocal() as session:
        loaded = await session.get(Product, product)
        assert loaded is not None
        sku_code = loaded.sku_code

    count = await _create(
        async_client,
        setup,
        {"source": "planned", "filters": {"warehouse_id": str(setup.warehouse_id)}},
    )
    sheet = await _print_sheet(async_client, setup, count["id"])
    row = next(r for r in sheet["rows"] if r["product_id"] == str(product))
    assert row["article"] == sku_code
    assert row["barcode"] is None


@pytest.mark.asyncio
async def test_print_sheet_negative_balance_prints_as_is(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "PrintNegative")
    product = await _product(async_client, setup, name="Товар с недостачей")
    await _balance(setup, product, -2)

    count = await _create(
        async_client,
        setup,
        {"source": "planned", "filters": {"warehouse_id": str(setup.warehouse_id)}},
    )
    sheet = await _print_sheet(async_client, setup, count["id"])
    row = next(r for r in sheet["rows"] if r["product_id"] == str(product))
    assert row["total"] == -2


@pytest.mark.asyncio
async def test_print_sheet_works_for_posted_document(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "PrintPosted")
    product = await _product(async_client, setup, name="Товар")
    await _balance(setup, product, 6)
    count = await _create(
        async_client,
        setup,
        {"source": "planned", "filters": {"warehouse_id": str(setup.warehouse_id)}},
    )
    line_id = count["lines"][0]["id"]
    saved = await async_client.put(
        f"/operations/inventory-counts/{count['id']}/lines",
        headers=setup.headers,
        json={"lines": [{"line_id": line_id, "actual_quantity": 6}]},
    )
    assert saved.status_code == 200, saved.text
    posted = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/post", headers=setup.headers
    )
    assert posted.status_code == 200, posted.text

    sheet = await _print_sheet(async_client, setup, count["id"])
    row = next(r for r in sheet["rows"] if r["product_id"] == str(product))
    assert row["total"] == 6


@pytest.mark.asyncio
async def test_print_sheet_works_for_cancelled_document(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "PrintCancelled")
    product = await _product(async_client, setup, name="Товар")
    await _balance(setup, product, 6)
    count = await _create(
        async_client,
        setup,
        {"source": "planned", "filters": {"warehouse_id": str(setup.warehouse_id)}},
    )
    cancelled = await async_client.delete(
        f"/operations/inventory-counts/{count['id']}", headers=setup.headers
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    sheet = await _print_sheet(async_client, setup, count["id"])
    row = next(r for r in sheet["rows"] if r["product_id"] == str(product))
    assert row["total"] == 6


@pytest.mark.asyncio
async def test_print_sheet_is_read_only(async_client: AsyncClient) -> None:
    setup = await _tenant(async_client, "PrintReadOnly")
    product = await _product(async_client, setup, name="Товар")
    await _balance(setup, product, 3)
    count = await _create(
        async_client,
        setup,
        {
            "source": "planned",
            "filters": {"warehouse_id": str(setup.warehouse_id)},
            "comment": "не трогать",
        },
    )

    async def _snapshot() -> tuple[str, str | None, list[tuple[str, int, int | None]]]:
        async with SessionLocal() as session:
            row = (
                await session.execute(
                    select(InventoryCount)
                    .where(InventoryCount.id == uuid.UUID(count["id"]))
                    .options(selectinload(InventoryCount.lines))
                )
            ).scalar_one()
            return (
                row.status,
                row.comment,
                sorted(
                    (str(line.id), line.expected_quantity, line.actual_quantity)
                    for line in row.lines
                ),
            )

    before = await _snapshot()
    for _ in range(2):
        await _print_sheet(async_client, setup, count["id"])
    after = await _snapshot()
    assert before == after


@pytest.mark.asyncio
async def test_print_sheet_requires_inventory_permission(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "PrintNoPermission")
    product = await _product(async_client, setup, name="Товар")
    await _balance(setup, product, 1)
    count = await _create(
        async_client,
        setup,
        {"source": "planned", "filters": {"warehouse_id": str(setup.warehouse_id)}},
    )
    staff_headers = await _staff_without_inventory(async_client, setup)

    response = await async_client.get(
        f"/operations/inventory-counts/{count['id']}/print-sheet",
        headers=staff_headers,
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_print_sheet_is_tenant_scoped(async_client: AsyncClient) -> None:
    tenant_a = await _tenant(async_client, "PrintTenantA")
    product = await _product(async_client, tenant_a, name="Товар")
    await _balance(tenant_a, product, 1)
    count = await _create(
        async_client,
        tenant_a,
        {"source": "planned", "filters": {"warehouse_id": str(tenant_a.warehouse_id)}},
    )
    tenant_b = await _tenant(async_client, "PrintTenantB")

    response = await async_client.get(
        f"/operations/inventory-counts/{count['id']}/print-sheet",
        headers=tenant_b.headers,
    )
    assert response.status_code == 404, response.text

    missing = await async_client.get(
        f"/operations/inventory-counts/{uuid.uuid4()}/print-sheet",
        headers=tenant_a.headers,
    )
    assert missing.status_code == 404, missing.text
