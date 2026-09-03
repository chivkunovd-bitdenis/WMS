# ruff: noqa: E501
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import app
from app.models.billing import BillingInvoice, BillingLedgerEntry, BillingLedgerLine
from app.models.operation_fact import OperationFact, OperationFactCutover, OperationFactLine
from app.models.user import User


async def _admin(async_client):
    response = await async_client.post("/auth/register", json={
        "organization_name": "Report API", "slug": f"report-api-{uuid.uuid4().hex}",
        "admin_email": f"report-{uuid.uuid4().hex}@example.com", "password": "password123",
    })
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Селлер"})
    me = await async_client.get("/auth/me", headers=headers)
    return headers, uuid.UUID(seller.json()["id"]), me.json()["email"]


@pytest.mark.asyncio
async def test_seller_report_summary_and_details_are_tenant_scoped(async_client) -> None:
    """TC-NEW-002: real DB aggregation and finance-off response contract."""
    headers, seller_id, email = await _admin(async_client)
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        session.add(BillingLedgerEntry(
            tenant_id=user.tenant_id, seller_id=seller_id, service_code="inbound", source="test",
            source_type="inbound_intake", source_id=uuid.uuid4(), unit="item", quantity=3,
            rate=100, amount=300, occurred_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
        ))
        await session.commit()

    params = "date_from=2026-08-20&date_to=2026-08-20"
    summary = await async_client.get(f"/billing/seller-report/summary?{params}", headers=headers)
    assert summary.status_code == 200, summary.text
    row = summary.json()["rows"][0]
    assert row["seller_id"] == str(seller_id)
    assert "net_total_kopecks" not in row
    details = await async_client.get(f"/billing/seller-report/sellers/{seller_id}/details?{params}", headers=headers)
    assert details.status_code == 200, details.text
    assert len(details.json()["entries"]) == 1
    assert "amount_kopecks" not in details.json()["entries"][0]
    assert "invoice_history" not in details.json()["entries"][0]
    assert "unpriced" not in details.json()["entries"][0]["result"]

    foreign_headers, foreign_seller_id, _foreign_email = await _admin(async_client)
    foreign = await async_client.get(
        f"/billing/seller-report/sellers/{seller_id}/details?{params}", headers=foreign_headers
    )
    assert foreign.status_code == 404
    assert foreign_seller_id != seller_id


@pytest.mark.asyncio
async def test_seller_report_rejects_future_and_too_long_period_before_data_read(async_client) -> None:
    headers, _seller_id, _email = await _admin(async_client)
    future = await async_client.get("/billing/seller-report/summary?date_from=2099-01-01&date_to=2099-01-01", headers=headers)
    assert future.status_code == 422
    too_long = await async_client.get("/billing/seller-report/summary?date_from=2024-01-01&date_to=2025-01-01", headers=headers)
    assert too_long.status_code == 422


@pytest.mark.asyncio
async def test_details_cursor_keeps_one_storage_row_and_exact_legacy_invoice_history(async_client) -> None:
    """TC-NEW-003: real cursor has no second storage row and cancelled invoice counts."""
    headers, seller_id, email = await _admin(async_client)
    _foreign_headers, foreign_seller_id, foreign_email = await _admin(async_client)
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        foreign_user = await session.scalar(select(User).where(User.email == foreign_email))
        assert user is not None
        assert foreign_user is not None
        first_id = uuid.uuid4()
        for entry_id, hour in ((first_id, 12), (uuid.uuid4(), 11)):
            session.add(BillingLedgerEntry(
                id=entry_id, tenant_id=user.tenant_id, seller_id=seller_id, service_code="inbound", source="test",
                source_type="inbound_intake", source_id=uuid.uuid4(), unit="item", quantity=1,
                rate=100, amount=100, occurred_at=datetime(2026, 8, 20, hour, tzinfo=UTC),
            ))
        session.add(BillingInvoice(
            tenant_id=user.tenant_id, seller_id=seller_id, number="S-REPORT-1", period=datetime(2026, 8, 1).date(),
            status="cancelled", total_amount=1, ff_profile_snapshot={}, seller_profile_snapshot={},
            lines=[{"documents": [{"id": str(first_id)}]}],
        ))
        session.add(BillingInvoice(
            tenant_id=foreign_user.tenant_id, seller_id=foreign_seller_id, number="S-REPORT-FOREIGN", period=datetime(2026, 8, 1).date(),
            status="cancelled", total_amount=1, ff_profile_snapshot={}, seller_profile_snapshot={},
            lines=[{"documents": [{"id": str(first_id)}]}],
        ))
        await session.commit()

    url = f"/billing/seller-report/sellers/{seller_id}/details?date_from=2026-08-20&date_to=2026-08-20&include_finance=true&limit=1"
    first = await async_client.get(url, headers=headers)
    assert first.status_code == 200, first.text
    first_payload = first.json()
    assert first_payload["storage_row"]["kind"] == "storage"
    assert first_payload["next_cursor"]
    history = first_payload["entries"][0]["invoice_history"]
    assert history == {"state": "known", "count": 1}
    tampered = first_payload["next_cursor"][:-1] + ("A" if first_payload["next_cursor"][-1] != "A" else "B")
    tampered_response = await async_client.get(f"{url}&cursor={tampered}", headers=headers)
    assert tampered_response.status_code == 422
    wrong_filter = await async_client.get(f"{url}&include_finance=false&cursor={first_payload['next_cursor']}", headers=headers)
    assert wrong_filter.status_code == 422
    foreign_cursor = await async_client.get(
        f"/billing/seller-report/sellers/{foreign_seller_id}/details?date_from=2026-08-20&date_to=2026-08-20&cursor={first_payload['next_cursor']}",
        headers=_foreign_headers,
    )
    assert foreign_cursor.status_code == 422
    second = await async_client.get(f"{url}&cursor={first_payload['next_cursor']}", headers=headers)
    assert second.status_code == 200, second.text
    assert second.json()["storage_row"] is None
    assert second.json()["entries"][0]["id"] != first_payload["entries"][0]["id"]


@pytest.mark.asyncio
async def test_finance_off_hides_unpriced_and_openapi_exposes_distinct_shapes(async_client) -> None:
    headers, seller_id, email = await _admin(async_client)
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        session.add(BillingLedgerEntry(
            tenant_id=user.tenant_id, seller_id=seller_id, service_code="inbound", source="test",
            source_type="inbound_intake", source_id=uuid.uuid4(), unit="item", quantity=1,
            rate=None, amount=None, occurred_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
        ))
        await session.commit()
    base = "date_from=2026-08-20&date_to=2026-08-20"
    off = await async_client.get(f"/billing/seller-report/sellers/{seller_id}/details?{base}", headers=headers)
    assert off.status_code == 200, off.text
    off_entry = off.json()["entries"][0]
    assert off_entry["result"] == "completed"
    assert not ({"rate_kopecks", "amount_kopecks", "billing_ledger_entry_id", "invoice_history", "unit"} & off_entry.keys())
    on = await async_client.get(f"/billing/seller-report/sellers/{seller_id}/details?{base}&include_finance=true", headers=headers)
    assert on.status_code == 200, on.text
    assert on.json()["entries"][0]["result"] == "unpriced"
    assert on.json()["totals"]["unpriced_count"] == 1
    openapi = app.openapi()
    response = openapi["paths"]["/billing/seller-report/summary"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert {branch["$ref"] for branch in response["anyOf"]} == {
        "#/components/schemas/SellerReportFinancialSummaryOut",
        "#/components/schemas/SellerReportPhysicalSummaryOut",
    }
    assert "SellerReportFinancialDetailsOut" in openapi["components"]["schemas"]


@pytest.mark.asyncio
async def test_invoice_history_counts_the_full_charge_reversal_chain(async_client) -> None:
    headers, seller_id, email = await _admin(async_client)
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        charge_id, reversal_id = uuid.uuid4(), uuid.uuid4()
        session.add_all([
            BillingLedgerEntry(
                id=charge_id, tenant_id=user.tenant_id, seller_id=seller_id, service_code="inbound", source="test",
                source_type="inbound_intake", source_id=uuid.uuid4(), unit="item", quantity=1, rate=100, amount=100,
                occurred_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
            ),
            BillingLedgerEntry(
                id=reversal_id, tenant_id=user.tenant_id, seller_id=seller_id, service_code="inbound", source="test",
                source_type="billing_reversal", source_id=charge_id, unit="item", quantity=-1, rate=100, amount=-100,
                entry_type="reversal", reversal_of_id=charge_id, occurred_at=datetime(2026, 8, 20, 13, tzinfo=UTC),
            ),
            BillingInvoice(
                tenant_id=user.tenant_id, seller_id=seller_id, number="CHAIN-CHARGE", period=date(2026, 8, 1), status="issued",
                total_amount=100, ff_profile_snapshot={}, seller_profile_snapshot={}, lines=[{"documents": [{"id": str(charge_id)}]}],
            ),
            BillingInvoice(
                tenant_id=user.tenant_id, seller_id=seller_id, number="CHAIN-REVERSAL", period=date(2026, 7, 1), status="cancelled",
                total_amount=-100, ff_profile_snapshot={}, seller_profile_snapshot={}, lines=[{"documents": [{"id": str(reversal_id)}]}],
            ),
        ])
        await session.commit()
    response = await async_client.get(
        f"/billing/seller-report/sellers/{seller_id}/details?date_from=2026-08-20&date_to=2026-08-20&include_finance=true",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert {entry["invoice_history"]["count"] for entry in response.json()["entries"]} == {2}


@pytest.mark.asyncio
async def test_malformed_same_tenant_invoice_snapshot_makes_history_unknown(async_client) -> None:
    headers, seller_id, email = await _admin(async_client)
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        entry_id = uuid.uuid4()
        session.add(BillingLedgerEntry(
            id=entry_id, tenant_id=user.tenant_id, seller_id=seller_id, service_code="inbound", source="test",
            source_type="inbound_intake", source_id=uuid.uuid4(), unit="item", quantity=1, rate=100, amount=100,
            occurred_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
        ))
        session.add(BillingInvoice(
            tenant_id=user.tenant_id, seller_id=seller_id, number="MALFORMED", period=date(2026, 8, 1), status="issued",
            total_amount=100, ff_profile_snapshot={}, seller_profile_snapshot={}, lines=[{"documents": [{"id": "not-a-uuid"}]}],
        ))
        await session.commit()
    response = await async_client.get(
        f"/billing/seller-report/sellers/{seller_id}/details?date_from=2026-08-20&date_to=2026-08-20&include_finance=true",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["entries"][0]["invoice_history"] == {"state": "unknown"}


@pytest.mark.asyncio
async def test_finance_operation_fact_explicitly_nulls_unpriced_and_mixed_rates(async_client) -> None:
    """Finance consumers must distinguish a missing/mixed rate from an omitted field."""
    headers, seller_id, email = await _admin(async_client)
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        occurred_at = datetime(2026, 8, 20, 12, tzinfo=UTC)
        cutover = OperationFactCutover(id=1, occurred_at=datetime(2026, 8, 20, tzinfo=UTC))
        unpriced_fact_id, mixed_fact_id = uuid.uuid4(), uuid.uuid4()
        unpriced_line_id, mixed_line_id = uuid.uuid4(), uuid.uuid4()
        # Деньги находятся по документу операции, поэтому у начисления и у факта
        # он должен быть один. Смешанные ставки живой код записывает одной
        # строкой с пустой ставкой и посчитанной суммой: у строк начисления
        # ставки разные, и общей у документа просто нет.
        mixed_document_id = uuid.uuid4()
        mixed_entry_id = uuid.uuid4()
        session.add_all([
            cutover,
            OperationFact(
                id=unpriced_fact_id, tenant_id=user.tenant_id, operation_code="unpriced-operation", billable_service_code="inbound",
                source_kind="test", source_event_id=uuid.uuid4(), seller_id=seller_id, seller_name_snapshot="Селлер",
                document_type="inbound_intake", document_id=uuid.uuid4(), source="system", occurred_at=occurred_at, item_quantity=1,
            ),
            OperationFactLine(id=unpriced_line_id, tenant_id=user.tenant_id, operation_fact_id=unpriced_fact_id, product_id=None, sku_snapshot=None, product_name_snapshot=None, item_quantity=1),
            OperationFact(
                id=mixed_fact_id, tenant_id=user.tenant_id, operation_code="mixed-operation", billable_service_code="inbound",
                source_kind="test", source_event_id=uuid.uuid4(), seller_id=seller_id, seller_name_snapshot="Селлер",
                document_type="inbound_intake", document_id=mixed_document_id, source="system", occurred_at=occurred_at, item_quantity=1,
            ),
            OperationFactLine(id=mixed_line_id, tenant_id=user.tenant_id, operation_fact_id=mixed_fact_id, product_id=None, sku_snapshot=None, product_name_snapshot=None, item_quantity=1),
            BillingLedgerEntry(
                id=mixed_entry_id, tenant_id=user.tenant_id, seller_id=seller_id, service_code="inbound", source="test",
                source_type="inbound_intake", source_id=mixed_document_id, unit="item", quantity=2, rate=None, amount=300,
                occurred_at=occurred_at,
            ),
        ])
        for rate in (100, 200):
            session.add(BillingLedgerLine(
                tenant_id=user.tenant_id, ledger_entry_id=mixed_entry_id, operation_fact_line_id=None, product_id=None,
                product_snapshot={}, physical_quantity=Decimal("1"), billing_quantity=Decimal("1"), billing_unit="item",
                tariff_snapshot={}, rate=rate, amount=rate,
            ))
        await session.commit()
    response = await async_client.get(
        f"/billing/seller-report/sellers/{seller_id}/details?date_from=2026-08-20&date_to=2026-08-20&include_finance=true",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    by_id = {entry["id"]: entry for entry in response.json()["entries"]}
    assert by_id[f"operation_fact:{unpriced_fact_id}"]["result"] == "unpriced"
    assert by_id[f"operation_fact:{unpriced_fact_id}"]["rate_kopecks"] is None
    assert by_id[f"operation_fact:{mixed_fact_id}"]["result"] == "completed"
    assert by_id[f"operation_fact:{mixed_fact_id}"]["rate_kopecks"] is None
    assert by_id[f"operation_fact:{mixed_fact_id}"]["amount_kopecks"] == 300
    # Начисление найдено по документу — операцию можно положить в счёт.
    assert by_id[f"operation_fact:{mixed_fact_id}"]["billing_ledger_entry_id"] == str(mixed_entry_id)


@pytest.mark.asyncio
async def test_packing_charge_is_visible_and_can_be_invoiced(async_client) -> None:
    """Упаковка своего факта не пишет, но её деньги обязаны быть видны.

    Начисление за упаковку идёт по тому же документу, что и отгрузка. Раньше
    отчёт искал деньги через связь со строкой операции, которую не заполняет ни
    один боевой путь, — и упаковку не видел никто: ни экран, ни счёт.
    """
    headers, seller_id, email = await _admin(async_client)
    occurred_at = datetime(2026, 8, 20, 12, tzinfo=UTC)
    document_id = uuid.uuid4()
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        fact_id, outbound_id, packing_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        session.add_all([
            OperationFactCutover(id=1, occurred_at=datetime(2026, 8, 1, tzinfo=UTC)),
            OperationFact(
                id=fact_id, tenant_id=user.tenant_id, operation_code="marketplace_outbound_completed",
                billable_service_code="marketplace_outbound", source_kind="marketplace_unload_request",
                source_event_id=uuid.uuid4(), seller_id=seller_id, seller_name_snapshot="Селлер",
                document_type="marketplace_unload", document_id=document_id, source="system",
                occurred_at=occurred_at, item_quantity=4,
            ),
            OperationFactLine(
                tenant_id=user.tenant_id, operation_fact_id=fact_id, product_id=None,
                sku_snapshot=None, product_name_snapshot=None, item_quantity=4,
            ),
            BillingLedgerEntry(
                id=outbound_id, tenant_id=user.tenant_id, seller_id=seller_id,
                service_code="marketplace_outbound", source="marketplace_unload",
                source_type="marketplace_unload", source_id=document_id, unit="item",
                quantity=4, rate=100, amount=400, occurred_at=occurred_at,
            ),
            BillingLedgerEntry(
                id=packing_id, tenant_id=user.tenant_id, seller_id=seller_id,
                service_code="packing", source="marketplace_unload",
                source_type="marketplace_unload", source_id=document_id, unit="item",
                quantity=4, rate=50, amount=200, occurred_at=occurred_at,
            ),
        ])
        await session.commit()

    params = "date_from=2026-08-20&date_to=2026-08-20&include_finance=true"
    details = await async_client.get(
        f"/billing/seller-report/sellers/{seller_id}/details?{params}", headers=headers
    )
    assert details.status_code == 200, details.text
    entries = {entry["service_code"]: entry for entry in details.json()["entries"]}

    assert entries["marketplace_outbound"]["amount_kopecks"] == 400
    assert entries["marketplace_outbound"]["billing_ledger_entry_id"] == str(outbound_id)
    # Отдельная строка упаковки: сумма и своя услуга, а не молчаливая прибавка
    # к отгрузке.
    assert entries["packing"]["amount_kopecks"] == 200
    assert entries["packing"]["billing_ledger_entry_id"] == str(packing_id)
    assert entries["packing"]["source_id"] == str(document_id)


@pytest.mark.asyncio
async def test_seller_with_storage_only_stays_in_the_summary(async_client) -> None:
    """Селлер, у которого за период было только хранение, не должен исчезать.

    Сводка строилась из операций, а хранение читалось лишь при раскрытии
    строки: строки не было — и до хранения было не добраться.
    """
    headers, seller_id, email = await _admin(async_client)
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        session.add(BillingLedgerEntry(
            tenant_id=user.tenant_id, seller_id=seller_id, service_code="storage",
            source="storage_daily", source_type="storage_day", source_id=uuid.uuid4(),
            unit="liter_day", quantity=Decimal("12.5"), rate=200, amount=2500,
            occurred_at=datetime(2026, 8, 20, 20, tzinfo=UTC),
        ))
        await session.commit()

    params = "date_from=2026-08-20&date_to=2026-08-20&include_finance=true"
    summary = await async_client.get(f"/billing/seller-report/summary?{params}", headers=headers)
    assert summary.status_code == 200, summary.text
    assert [row["seller_id"] for row in summary.json()["rows"]] == [str(seller_id)]

    details = await async_client.get(
        f"/billing/seller-report/sellers/{seller_id}/details?{params}", headers=headers
    )
    assert details.status_code == 200, details.text
    storage_row = details.json()["storage_row"]
    assert storage_row["liter_days"] == 12.5
    assert storage_row["amount_kopecks"] == 2500
