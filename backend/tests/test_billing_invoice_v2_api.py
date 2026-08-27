from __future__ import annotations

import time
import uuid
from datetime import UTC, date, datetime
from datetime import time as datetime_time
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.billing import (
    BillingInvoice,
    BillingInvoiceV2Source,
    BillingLedgerEntry,
    BillingTariffVersion,
)
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.warehouse import Warehouse
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.storage_measurement_service import MOSCOW


@pytest.mark.asyncio
async def test_manual_invoice_v2_preview_save_retry_and_cancel(async_client: AsyncClient) -> None:
    suffix = f"invoice-v2-{time.time_ns()}"
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Invoice v2",
            "slug": suffix,
            "admin_email": f"{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Ручной селлер"})
    seller_id = seller.json()["id"]
    body = {
        "creation_mode": "manual",
        "seller_id": seller_id,
        "lines": [{"description": "Ручная услуга", "amount": "630.00", "unit_price": "12.50"}],
    }

    preview = await async_client.post("/billing/invoices-v2/preview", headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["total_amount_kopecks"] == 63000
    assert preview.json()["lines"][0]["unit_price_kopecks"] == 1250

    saved = await async_client.post(
        "/billing/invoices-v2", headers={**headers, "Idempotency-Key": "manual-1"}, json=body
    )
    assert saved.status_code == 201, saved.text
    invoice_id = saved.json()["id"]
    retry = await async_client.post(
        "/billing/invoices-v2", headers={**headers, "Idempotency-Key": "manual-1"}, json=body
    )
    assert retry.status_code == 201
    assert retry.json()["id"] == invoice_id
    changed = await async_client.post(
        "/billing/invoices-v2",
        headers={**headers, "Idempotency-Key": "manual-1"},
        json={**body, "lines": [{"description": "Другая", "amount": "1.00"}]},
    )
    assert changed.status_code == 409
    cancelled = await async_client.post(
        f"/billing/invoices-v2/{invoice_id}/cancel", headers=headers
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_manual_invoice_v2_rejects_decimal_float_and_missing_key(
    async_client: AsyncClient,
) -> None:
    suffix = f"invoice-v2-negative-{time.time_ns()}"
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Invoice v2",
            "slug": suffix,
            "admin_email": f"{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Селлер"})
    body = {
        "creation_mode": "manual",
        "seller_id": seller.json()["id"],
        "lines": [{"description": "Услуга", "amount": "1.234"}],
    }
    assert (
        await async_client.post("/billing/invoices-v2/preview", headers=headers, json=body)
    ).status_code == 422
    body["lines"][0]["amount"] = "1.00"
    assert (
        await async_client.post("/billing/invoices-v2", headers=headers, json=body)
    ).status_code == 422


@pytest.mark.asyncio
async def test_selected_operations_invoice_uses_whole_charge_reversal_chain(
    async_client: AsyncClient,
) -> None:
    suffix = f"invoice-v2-chain-{time.time_ns()}"
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Invoice v2",
            "slug": suffix,
            "admin_email": f"{suffix}@example.com",
            "password": "password123",
        },
    )
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    tenant_id = uuid.UUID((await async_client.get("/auth/me", headers=headers)).json()["tenant_id"])
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Селлер"})
    seller_id = uuid.UUID(seller.json()["id"])
    root_id, reversal_id = uuid.uuid4(), uuid.uuid4()
    async with SessionLocal() as session:
        session.add_all(
            [
                BillingLedgerEntry(
                    id=root_id,
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    service_code="inbound",
                    source="test",
                    source_type="test",
                    source_id=uuid.uuid4(),
                    event_kind="charge",
                    unit="item",
                    quantity=Decimal("1"),
                    rate=1000,
                    amount=1000,
                    occurred_at=datetime(2026, 8, 20, tzinfo=UTC),
                ),
                BillingLedgerEntry(
                    id=reversal_id,
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    reversal_of_id=root_id,
                    entry_type="reversal",
                    service_code="inbound",
                    source="test",
                    source_type="test",
                    source_id=uuid.uuid4(),
                    event_kind="reversal",
                    unit="item",
                    quantity=Decimal("-1"),
                    rate=1000,
                    amount=-200,
                    occurred_at=datetime(2026, 8, 21, tzinfo=UTC),
                ),
            ]
        )
        await session.commit()
    body = {
        "creation_mode": "selected_operations",
        "seller_id": str(seller_id),
        "date_from": "2026-08-01",
        "date_to": "2026-08-31",
        "selected_root_ids": [str(root_id)],
    }
    preview = await async_client.post("/billing/invoices-v2/preview", headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["total_amount_kopecks"] == 800
    saved = await async_client.post(
        "/billing/invoices-v2", headers={**headers, "Idempotency-Key": "chain-1"}, json=body
    )
    assert saved.status_code == 201, saved.text
    async with SessionLocal() as session:
        sources = list(
            (
                await session.scalars(
                    select(BillingInvoiceV2Source).where(
                        BillingInvoiceV2Source.tenant_id == tenant_id
                    )
                )
            ).all()
        )
    assert {source.billing_ledger_entry_id for source in sources} == {root_id, reversal_id}
    reversed_only = {**body, "selected_root_ids": [str(reversal_id)]}
    response = await async_client.post(
        "/billing/invoices-v2/preview", headers=headers, json=reversed_only
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "standalone_reversal"


async def _storage_ready_tenant(async_client: AsyncClient, suffix: str):
    """Реальные склад, товар с габаритами, движение и тариф хранения."""
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Invoice v2 storage",
            "slug": suffix,
            "admin_email": f"{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    warehouse = await async_client.post(
        "/warehouses", headers=headers, json={"name": f"Склад {suffix}", "code": f"W{suffix[-6:]}"}
    )
    assert warehouse.status_code in (200, 201), warehouse.text
    warehouse_id = uuid.UUID(warehouse.json()["id"])
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Селлер хранения"})
    seller_id = uuid.UUID(seller.json()["id"])

    async with SessionLocal() as session:
        stored = await session.get(Warehouse, warehouse_id)
        assert stored is not None
        tenant_id = stored.tenant_id
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Товар хранения",
            sku_code=f"sku-{suffix}",
            volume_liters=Decimal("2"),
            dimensions_source="manual",
        )
        session.add(product)
        await session.flush()
        location = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
        session.add(
            InventoryMovement(
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                storage_location_id=location.id,
                product_id=product.id,
                quantity_delta=3,
                movement_type="invoice_v2_storage_test",
                created_at=datetime.combine(date(2026, 8, 20), datetime_time.min, MOSCOW),
            )
        )
        session.add(
            BillingTariffVersion(
                tenant_id=tenant_id,
                seller_id=None,
                warehouse_id=warehouse_id,
                service_code="storage_liter_day",
                unit="liter_day",
                amount=100,
                valid_from=date(2026, 8, 1),
            )
        )
        await session.commit()
    return headers, tenant_id, seller_id, product


async def _storage_row(async_client: AsyncClient, headers, seller_id, date_from, date_to):
    params = f"date_from={date_from}&date_to={date_to}&include_finance=true"
    details = await async_client.get(
        f"/billing/seller-report/sellers/{seller_id}/details?{params}", headers=headers
    )
    assert details.status_code == 200, details.text
    return details.json()["storage_row"]


@pytest.mark.asyncio
async def test_storage_row_reaches_the_invoice_as_one_verified_line(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-201: токен хранения пересчитывается сервером и попадает в счёт одной строкой."""
    suffix = f"invoice-v2-storage-{time.time_ns()}"
    headers, tenant_id, seller_id, _product = await _storage_ready_tenant(async_client, suffix)
    row = await _storage_row(async_client, headers, seller_id, "2026-08-20", "2026-08-22")
    assert row["status"] == "calculated", row
    assert row["amount_kopecks"] > 0, row

    body = {
        "creation_mode": "selected_operations",
        "seller_id": str(seller_id),
        "date_from": "2026-08-20",
        "date_to": "2026-08-22",
        "selected_root_ids": [],
        "storage_calculation_token": row["calculation_token"],
    }
    preview = await async_client.post("/billing/invoices-v2/preview", headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    lines = preview.json()["lines"]
    assert len(lines) == 1, lines
    # Одна агрегированная строка без разбивки по товарам, дням и тарифам.
    assert lines[0]["description"] == "Хранение товара за выбранный период"
    assert lines[0]["total_amount_kopecks"] == row["amount_kopecks"]
    assert preview.json()["total_amount_kopecks"] == row["amount_kopecks"]

    saved = await async_client.post(
        "/billing/invoices-v2", headers={**headers, "Idempotency-Key": "storage-1"}, json=body
    )
    assert saved.status_code == 201, saved.text
    async with SessionLocal() as session:
        sources = list(
            (
                await session.scalars(
                    select(BillingInvoiceV2Source).where(
                        BillingInvoiceV2Source.tenant_id == tenant_id
                    )
                )
            ).all()
        )
    assert len(sources) == 1
    # Токен сохранён снимком: именно его отсутствие делало строку хранения немой.
    assert sources[0].storage_calculation_token == row["calculation_token"]
    assert sources[0].billing_ledger_entry_id is None
    assert sources[0].operation_fact_id is None
    assert sources[0].signed_amount_kopecks_snapshot == row["amount_kopecks"]


@pytest.mark.asyncio
async def test_storage_token_is_never_trusted_as_a_price(async_client: AsyncClient) -> None:
    """TC-NEW-202: подделанный, чужой и не тот период токены хранения счёт не создают."""
    suffix = f"invoice-v2-storage-neg-{time.time_ns()}"
    headers, _tenant_id, seller_id, _product = await _storage_ready_tenant(async_client, suffix)
    row = await _storage_row(async_client, headers, seller_id, "2026-08-20", "2026-08-22")
    body = {
        "creation_mode": "selected_operations",
        "seller_id": str(seller_id),
        "date_from": "2026-08-20",
        "date_to": "2026-08-22",
        "selected_root_ids": [],
        "storage_calculation_token": row["calculation_token"],
    }

    tampered = await async_client.post(
        "/billing/invoices-v2/preview",
        headers=headers,
        json={**body, "storage_calculation_token": f"{row['calculation_token']}x"},
    )
    assert tampered.status_code == 422
    assert tampered.json()["detail"] == "storage_calculation_stale"

    # Тот же подписанный токен, но заявленный на другой период: границы входят
    # в подпись, поэтому перенести расчёт на соседние даты нельзя.
    moved = await async_client.post(
        "/billing/invoices-v2/preview",
        headers=headers,
        json={**body, "date_from": "2026-08-21", "date_to": "2026-08-22"},
    )
    assert moved.status_code == 422
    assert moved.json()["detail"] == "storage_calculation_stale"

    # Ни одной операции и никакого хранения — счёт не собирается вообще.
    empty = await async_client.post(
        "/billing/invoices-v2/preview",
        headers=headers,
        json={**body, "storage_calculation_token": None},
    )
    assert empty.status_code == 422
    assert empty.json()["detail"] == "selected_operations_required"


@pytest.mark.asyncio
async def test_storage_without_dimensions_blocks_the_invoice(async_client: AsyncClient) -> None:
    """TC-NEW-203: товар без габаритов не даёт выставить счёт и называет причину."""
    suffix = f"invoice-v2-storage-dim-{time.time_ns()}"
    headers, tenant_id, seller_id, product = await _storage_ready_tenant(async_client, suffix)
    row = await _storage_row(async_client, headers, seller_id, "2026-08-20", "2026-08-22")
    assert row["status"] == "calculated"

    # Габариты пропали уже после того, как оператор увидел рассчитанную строку.
    async with SessionLocal() as session:
        stored = await session.get(Product, product.id)
        assert stored is not None
        stored.volume_liters = None
        await session.commit()

    blocked = await async_client.post(
        "/billing/invoices-v2/preview",
        headers=headers,
        json={
            "creation_mode": "selected_operations",
            "seller_id": str(seller_id),
            "date_from": "2026-08-20",
            "date_to": "2026-08-22",
            "selected_root_ids": [],
            "storage_calculation_token": row["calculation_token"],
        },
    )
    assert blocked.status_code == 422
    assert blocked.json()["detail"] == "storage_missing_dimensions"
    assert tenant_id is not None


@pytest.mark.asyncio
async def test_invoice_history_merges_legacy_and_v2_without_losing_documents(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-204: вкладка «Выставленные счета» показывает обе эпохи одним списком."""
    suffix = f"invoice-v2-history-{time.time_ns()}"
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Invoice history",
            "slug": suffix,
            "admin_email": f"{suffix}@example.com",
            "password": "password123",
        },
    )
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    tenant_id = uuid.UUID((await async_client.get("/auth/me", headers=headers)).json()["tenant_id"])
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Селлер истории"})
    seller_id = uuid.UUID(seller.json()["id"])

    async with SessionLocal() as session:
        session.add(
            BillingInvoice(
                tenant_id=tenant_id,
                seller_id=seller_id,
                number="СЧ-СТАРЫЙ-1",
                period=date(2026, 7, 1),
                status="issued",
                issued_at=datetime(2026, 8, 1, 10, tzinfo=UTC),
                total_amount=Decimal("18400.00"),
                ff_profile_snapshot={},
                seller_profile_snapshot={},
                lines=[],
            )
        )
        await session.commit()

    saved = await async_client.post(
        "/billing/invoices-v2",
        headers={**headers, "Idempotency-Key": "history-1"},
        json={
            "creation_mode": "manual",
            "seller_id": str(seller_id),
            "lines": [{"description": "Новая услуга", "amount": "25.50"}],
        },
    )
    assert saved.status_code == 201, saved.text

    history = await async_client.get("/billing/invoices-v2", headers=headers)
    assert history.status_code == 200, history.text
    rows = history.json()["invoices"]
    assert len(rows) == 2, rows
    by_origin = {row["origin"]: row for row in rows}

    legacy = by_origin["legacy"]
    assert legacy["number"] == "СЧ-СТАРЫЙ-1"
    assert legacy["creation_mode"] == "monthly"
    # Legacy хранит копейки в Numeric(14, 2). Приведение «как рубли» завысило
    # бы каждую строку истории в сто раз, поэтому проверяем один к одному.
    assert legacy["total_amount_kopecks"] == 18400
    # Месяц раскрывается в границы периода: колонка «Период» одна на обе эпохи.
    assert legacy["period_start"] == "2026-07-01"
    assert legacy["period_end"] == "2026-07-31"

    fresh = by_origin["v2"]
    assert fresh["creation_mode"] == "manual"
    assert fresh["total_amount_kopecks"] == 2550
    assert fresh["period_start"] is None
    assert fresh["seller_name"] == "Селлер истории"

    # Новый счёт выставлен только что, поэтому стоит выше июльского.
    assert rows[0]["origin"] == "v2"

    # Курсор режет объединённый список, а не каждую таблицу отдельно.
    first_page = await async_client.get("/billing/invoices-v2?limit=1", headers=headers)
    assert first_page.status_code == 200
    assert len(first_page.json()["invoices"]) == 1
    cursor = first_page.json()["next_cursor"]
    assert cursor
    second_page = await async_client.get(
        f"/billing/invoices-v2?limit=1&cursor={cursor}", headers=headers
    )
    assert second_page.status_code == 200
    assert [row["origin"] for row in second_page.json()["invoices"]] == ["legacy"]
    assert second_page.json()["next_cursor"] is None

    # Фильтры работают на обе эпохи одинаково.
    cancelled_only = await async_client.get(
        "/billing/invoices-v2?status=cancelled", headers=headers
    )
    assert cancelled_only.json()["invoices"] == []
    by_number = await async_client.get("/billing/invoices-v2?number=СТАРЫЙ", headers=headers)
    assert [row["origin"] for row in by_number.json()["invoices"]] == ["legacy"]

    # Чужой арендатор не видит ничего из этой истории.
    other = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Other",
            "slug": f"{suffix}-other",
            "admin_email": f"other-{suffix}@example.com",
            "password": "password123",
        },
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    assert (await async_client.get("/billing/invoices-v2", headers=other_headers)).json()[
        "invoices"
    ] == []

    assert (
        await async_client.get("/billing/invoices-v2?cursor=не-курсор", headers=headers)
    ).status_code == 422
