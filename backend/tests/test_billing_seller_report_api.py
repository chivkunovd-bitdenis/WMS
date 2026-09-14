# ruff: noqa: E501
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.billing import (
    BillingInvoice,
    BillingLedgerEntry,
    BillingLedgerLine,
    BillingTariffVersionV2,
)
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.operation_fact import OperationFact, OperationFactCutover, OperationFactLine
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services import fbs_packing_box_service as packing_box_svc
from app.services import fbs_shipment_service as fbs_shipment_svc


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
@pytest.mark.parametrize("include_finance", [False, True])
async def test_wms406_confirmed_handover_drives_both_reports_despite_old_fact_dates(async_client, include_finance) -> None:
    headers, seller_id, email = await _admin(async_client)
    handover = datetime(2026, 8, 20, 12, tzinfo=UTC)
    stale = datetime(2026, 8, 1, 12, tzinfo=UTC)
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        warehouse = Warehouse(tenant_id=user.tenant_id, name="Склад", code="WMS406")
        session.add(warehouse)
        await session.flush()
        supplies = [FbsSupply(
            tenant_id=user.tenant_id, seller_id=seller_id, warehouse_id=warehouse.id,
            name=f"Поставка {index}", wb_supply_id=f"WB-406-{index}", delivery_type="warehouse_sc",
            delivered_at=moment,
        ) for index, moment in enumerate((handover, stale, None))]
        session.add_all(supplies)
        await session.flush()
        orders = [FbsOrder(
            tenant_id=user.tenant_id, seller_id=seller_id, wb_order_id=406000 + index,
            marketplace="wb", status="cancelled" if index == 3 else "packed",
            supply_id=supplies[index].id if index < 3 else None,
            created_at_wb=stale, deadline_at=stale, updated_at=stale,
            mapping_status="unmapped", reserve_status="none",
        ) for index in range(4)]
        session.add_all(orders)
        await session.flush()
        detached = orders[3]
        session.add(FbsWbOperation(
            tenant_id=user.tenant_id, seller_id=seller_id, operation_kind="supply_deliver",
            idempotency_key="wms406-detached", state="confirmed", confirmed_at=handover,
            local_entity_type="fbs_supply", local_entity_id=supplies[0].id,
            request_summary_json={"checkpoint_source_plan": {"resolutions": [{"fbs_order_id": str(detached.id)}]}},
        ))
        # The real handover is inside/outside the window in the opposite order
        # to these historical facts. An imported packed order has no handover.
        for index, order in enumerate(orders[:3]):
            session.add(OperationFact(
                tenant_id=user.tenant_id, seller_id=seller_id, marketplace="wb",
                operation_code="fbs_order", billable_service_code="fbs_order", source_kind="fbs_order",
                source_event_id=order.id, document_type="fbs_order", document_id=order.id,
                occurred_at=stale if index == 0 else handover, item_quantity=1, source="system",
            ))
        packing_id = uuid.uuid4()
        session.add(BillingLedgerEntry(
            id=packing_id, tenant_id=user.tenant_id, seller_id=seller_id, service_code="packing",
            source="fbs", source_type="fbs_order", source_id=orders[0].id,
            unit="document", quantity=1, rate=250, amount=250, occurred_at=stale,
        ))
        session.add(BillingInvoice(
            tenant_id=user.tenant_id, seller_id=seller_id, number="WMS406-1", period=date(2026, 8, 1),
            status="cancelled", total_amount=250, ff_profile_snapshot={}, seller_profile_snapshot={},
            lines=[{"documents": [{"id": str(packing_id)}]}],
        ))
        await session.commit()
        expected_ids = {str(orders[0].id), str(detached.id)}
    params = f"date_from=2026-08-20&date_to=2026-08-20&include_finance={str(include_finance).lower()}"
    summary = await async_client.get(f"/billing/seller-report/summary?{params}", headers=headers)
    details = await async_client.get(f"/billing/seller-report/sellers/{seller_id}/details?{params}", headers=headers)
    assert summary.status_code == details.status_code == 200, (summary.text, details.text)
    entries = details.json()["entries"]
    assert len(entries) == 4
    assert {row["source_id"] for row in entries} == expected_ids
    assert {row["occurred_at"] for row in entries} == {"2026-08-20T15:00:00+03:00"}
    for totals in (summary.json()["totals"], summary.json()["rows"][0], details.json()["totals"]):
        assert totals["fbs_items"] == totals["packing_items"] == 2
        assert totals["operation_count"] == 4
        if include_finance:
            assert totals["net_total_kopecks"] == 250
    if include_finance:
        priced = next(row for row in entries if row.get("billing_ledger_entry_id") == str(packing_id))
        assert priced["amount_kopecks"] == 250 and priced["item_quantity"] == 1
        assert priced["invoice_history"] == {"state": "known", "count": 1}


@pytest.mark.asyncio
@pytest.mark.parametrize("with_packing_charge", [False, True])
async def test_wms406_fbo_shipped_units_define_packing_without_standalone_events(async_client, with_packing_charge) -> None:
    headers, seller_id, email = await _admin(async_client)
    moment = datetime(2026, 8, 20, 12, tzinfo=UTC)
    document_id = uuid.uuid4()
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        session.add_all([
            OperationFact(
                tenant_id=user.tenant_id, seller_id=seller_id, operation_code="marketplace_outbound_completed",
                billable_service_code="marketplace_outbound", source_kind="marketplace_unload_request",
                source_event_id=document_id, document_type="marketplace_unload", document_id=document_id,
                occurred_at=moment, item_quantity=7, source="system",
            ),
            OperationFact(
                tenant_id=user.tenant_id, seller_id=seller_id, operation_code="packing_completed",
                billable_service_code="packing", source_kind="packaging_task", source_event_id=uuid.uuid4(),
                document_type="packaging_task", document_id=uuid.uuid4(), occurred_at=moment,
                item_quantity=100, source="system",
            ),
            BillingLedgerEntry(
                tenant_id=user.tenant_id, seller_id=seller_id, service_code="packing", source="packaging",
                source_type="packaging_task", source_id=uuid.uuid4(), unit="item", quantity=100,
                rate=10, amount=1000, occurred_at=moment,
            ),
        ])
        if with_packing_charge:
            session.add(BillingLedgerEntry(
                tenant_id=user.tenant_id, seller_id=seller_id, service_code="packing", source="marketplace_unload",
                source_type="marketplace_unload", source_id=document_id, unit="document", quantity=1,
                rate=300, amount=300, occurred_at=moment,
            ))
        await session.commit()
    for finance in (False, True):
        params = f"date_from=2026-08-20&date_to=2026-08-20&include_finance={str(finance).lower()}"
        summary = await async_client.get(f"/billing/seller-report/summary?{params}", headers=headers)
        details = await async_client.get(f"/billing/seller-report/sellers/{seller_id}/details?{params}", headers=headers)
        assert summary.status_code == details.status_code == 200, (summary.text, details.text)
        assert len(details.json()["entries"]) == 2
        packing = next(row for row in details.json()["entries"] if row["service_code"] == "packing")
        assert packing["item_quantity"] == 7 and packing["source_id"] == str(document_id)
        for totals in (summary.json()["totals"], details.json()["totals"]):
            assert totals["packing_items"] == totals["outbound_items"] == 7
            if finance:
                assert totals["net_total_kopecks"] == (300 if with_packing_charge else 0)


@pytest.mark.asyncio
async def test_wms406_legacy_fbo_packing_and_ozon_contract_remain_visible(async_client) -> None:
    headers, seller_id, email = await _admin(async_client)
    moment = datetime(2026, 8, 20, 12, tzinfo=UTC)
    document_id = uuid.uuid4()
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        session.add(OperationFactCutover(id=1, occurred_at=datetime(2026, 8, 21, tzinfo=UTC)))
        order = FbsOrder(
            tenant_id=user.tenant_id, seller_id=seller_id, marketplace="ozon", wb_order_id=-40601,
            external_order_id="OZON406", status="sorted", created_at_wb=moment, deadline_at=moment,
            mapping_status="unmapped", reserve_status="none",
        )
        session.add(order)
        await session.flush()
        for source_type, source_id, service, quantity in (("marketplace_unload", document_id, "marketplace_outbound", 5), ("fbs_order", order.id, "fbs_order", 3)):
            session.add(BillingLedgerEntry(
                tenant_id=user.tenant_id, seller_id=seller_id, service_code=service, source="test",
                source_type=source_type, source_id=source_id, unit="item", quantity=quantity,
                rate=100, amount=quantity * 100, occurred_at=moment,
            ))
        await session.commit()
    response = await async_client.get(
        f"/billing/seller-report/sellers/{seller_id}/details?date_from=2026-08-20&date_to=2026-08-20&include_finance=true", headers=headers
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["entries"]) == 4
    assert payload["totals"]["packing_items"] == 8
    assert payload["totals"]["fbs_items"] == 3
    assert payload["totals"]["outbound_items"] == 5
    assert payload["totals"]["net_total_kopecks"] == 800


@pytest.mark.asyncio
@pytest.mark.parametrize("with_priced_part", [False, True])
async def test_wms406_fbo_existing_unpriced_charge_is_not_zero_or_live_repriced(async_client, with_priced_part) -> None:
    headers, seller_id, email = await _admin(async_client)
    moment = datetime(2026, 8, 20, 12, tzinfo=UTC)
    document_id = uuid.uuid4()
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        session.add(OperationFact(
            tenant_id=user.tenant_id, seller_id=seller_id, operation_code="marketplace_outbound_completed",
            billable_service_code="marketplace_outbound", source_kind="marketplace_unload_request",
            source_event_id=document_id, document_type="marketplace_unload", document_id=document_id,
            occurred_at=moment, item_quantity=3, source="system",
        ))
        for service_code in ("marketplace_outbound", "packing"):
            session.add_all([
                BillingLedgerEntry(
                    tenant_id=user.tenant_id, seller_id=seller_id, service_code=service_code,
                    source="marketplace_unload", source_type="marketplace_unload", source_id=document_id,
                    unit="item", quantity=3, rate=None, amount=None, occurred_at=moment,
                ),
                # A now-available tariff must not replace an existing unpriced ledger.
                BillingTariffVersionV2(
                    tenant_id=user.tenant_id, seller_id=seller_id, service_code=service_code,
                    unit="item", rate=100, valid_from_at=datetime(2026, 8, 1, tzinfo=UTC),
                ),
            ])
        if with_priced_part:
            session.add(BillingLedgerEntry(
                tenant_id=user.tenant_id, seller_id=seller_id, service_code="marketplace_outbound",
                source="marketplace_unload", source_type="marketplace_unload", source_id=document_id,
                event_kind="correction", unit="item", quantity=1, rate=100, amount=100, occurred_at=moment,
            ))
        await session.commit()
    params = "date_from=2026-08-20&date_to=2026-08-20&include_finance=true"
    summary = await async_client.get(f"/billing/seller-report/summary?{params}", headers=headers)
    details = await async_client.get(f"/billing/seller-report/sellers/{seller_id}/details?{params}", headers=headers)
    assert summary.status_code == details.status_code == 200, (summary.text, details.text)
    entries = details.json()["entries"]
    assert {row["service_code"] for row in entries} == {"marketplace_outbound", "packing"}
    assert all(row["amount_kopecks"] is None and row["result"] == "unpriced" for row in entries)
    assert all(row.get("priced_live") is False for row in entries)
    for totals in (summary.json()["totals"], details.json()["totals"]):
        assert totals["unpriced_count"] == 2
        assert totals["packing_items"] == totals["outbound_items"] == 3


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
    row = summary.json()["rows"][0]
    assert row["seller_id"] == str(seller_id)
    # Строка не должна показывать ноль там, где в раскрывашке лежат деньги:
    # счёт хранение включает, значит и «Стоимость услуг» обязана его считать.
    assert row["net_total_kopecks"] == 2500
    assert summary.json()["totals"]["net_total_kopecks"] == 2500

    details = await async_client.get(
        f"/billing/seller-report/sellers/{seller_id}/details?{params}", headers=headers
    )
    assert details.status_code == 200, details.text
    storage_row = details.json()["storage_row"]
    assert storage_row["liter_days"] == 12.5
    assert storage_row["amount_kopecks"] == 2500


@pytest.mark.asyncio
async def test_reversal_money_lands_on_its_own_document(async_client) -> None:
    """У отменённой операции должны быть видны обе стороны: и плюс, и минус.

    Сторно адресуется не документом, а отменяемым начислением
    (`source_type='billing_reversal'`), поэтому поиск денег по документу его не
    находил: в отчёте оставался «плюс», а «минус» не показывал никто.
    """
    headers, seller_id, email = await _admin(async_client)
    occurred_at = datetime(2026, 8, 20, 12, tzinfo=UTC)
    document_id = uuid.uuid4()
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        charge_id, reversal_id = uuid.uuid4(), uuid.uuid4()
        fact_id, reversal_fact_id = uuid.uuid4(), uuid.uuid4()
        session.add_all([
            OperationFactCutover(id=1, occurred_at=datetime(2026, 8, 1, tzinfo=UTC)),
            OperationFact(
                id=fact_id, tenant_id=user.tenant_id, operation_code="marketplace_outbound_completed",
                billable_service_code="marketplace_outbound", source_kind="marketplace_unload_request",
                source_event_id=uuid.uuid4(), seller_id=seller_id, seller_name_snapshot="Селлер",
                document_type="marketplace_unload", document_id=document_id, source="system",
                occurred_at=occurred_at, item_quantity=2,
            ),
            BillingLedgerEntry(
                id=charge_id, tenant_id=user.tenant_id, seller_id=seller_id,
                service_code="marketplace_outbound", source="marketplace_unload",
                source_type="marketplace_unload", source_id=document_id, unit="item",
                quantity=2, rate=100, amount=200, occurred_at=occurred_at,
            ),
        ])
        await session.flush()
        session.add_all([
            OperationFact(
                id=reversal_fact_id, tenant_id=user.tenant_id, operation_code="marketplace_outbound_reversal",
                billable_service_code="marketplace_outbound", source_kind="marketplace_unload_request",
                source_event_id=uuid.uuid4(), seller_id=seller_id, seller_name_snapshot="Селлер",
                document_type="marketplace_unload", document_id=document_id, source="system",
                occurred_at=occurred_at, item_quantity=2, reversal_of_id=fact_id,
            ),
            BillingLedgerEntry(
                id=reversal_id, tenant_id=user.tenant_id, seller_id=seller_id,
                entry_type="reversal", reversal_of_id=charge_id,
                service_code="marketplace_outbound", source="marketplace_unload",
                source_type="billing_reversal", source_id=charge_id, unit="item",
                quantity=-2, rate=100, amount=-200, occurred_at=occurred_at,
            ),
        ])
        await session.commit()

    params = "date_from=2026-08-20&date_to=2026-08-20&include_finance=true"
    details = await async_client.get(
        f"/billing/seller-report/sellers/{seller_id}/details?{params}", headers=headers
    )
    assert details.status_code == 200, details.text
    by_id = {entry["id"]: entry for entry in details.json()["entries"]}
    assert by_id[f"operation_fact:{fact_id}"]["amount_kopecks"] == 200
    reversal_row = by_id[f"operation_fact:{reversal_fact_id}"]
    assert reversal_row["result"] == "reversed"
    assert reversal_row["amount_kopecks"] == -200
    assert reversal_row["billing_ledger_entry_id"] == str(reversal_id)
    # Плюс и минус гасят друг друга, а не остаются половиной суммы.
    assert details.json()["totals"]["net_total_kopecks"] == 0


async def _seed_boxed_supply(
    session, *, tenant_id, seller_id, warehouse_id, name, marketplace, box_count, actor_user_id, http_client=None,
):
    """Поставка плюс короба штатным `fbs_packing_box_service.create_boxes` (C6, WMS-447).

    Для WB короб дополнительно регистрирует грузоместо WB и требует http_client
    (реальный HTTP не уходит — settings.e2e_mock_wb_marketplace_supplies включён
    фикстурой теста). Для Ozon http_client не нужен: сервис возвращается раньше.
    """
    supply = FbsSupply(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id, name=name,
        wb_supply_id=f"WB-{name}" if marketplace == "wb" else None,
        marketplace=marketplace, delivery_type="warehouse_sc",
    )
    session.add(supply)
    await session.flush()
    if box_count:
        await packing_box_svc.create_boxes(
            session, tenant_id, supply.id, box_count, f"boxes-{name}",
            http_client, actor_user_id=actor_user_id, without_distribution=False,
        )
    return supply


async def _deliver_supply(session, supply, *, delivered_at):
    """Провести поставку штатным `fbs_shipment_service._apply_local_delivered`.

    Момент передачи задаётся через `confirmed_at` подтверждённой операции — тем
    же полем, которым сама `_apply_local_delivered` пользуется раньше, чем
    `datetime.now(UTC)` (`now = supply.delivered_at or getattr(operation,
    "confirmed_at", None) or datetime.now(UTC)`), и тем же полем, которым
    WMS-406 определяет момент подтверждённой передачи для отчёта — так время
    контролируется детерминированно, без sleep и без подмены глобальных часов.
    Пустой список заказов: поставка без заказов не требует физического
    списания (`_write_off_delivered_orders_once` не выполняет ничего для
    пустого списка) — короб и момент проведения от состава заказов не зависят
    (R2 «на счёт не влияют состав заказов в коробах»), поэтому для этой
    проверки они не нужны.
    """
    operation = SimpleNamespace(confirmed_at=delivered_at)
    await fbs_shipment_svc._apply_local_delivered(session, supply, [], None, None, operation)
    await session.flush()


@pytest.mark.asyncio
@pytest.mark.parametrize("include_finance", [False, True])
async def test_wms447_fbs_box_count_lands_in_totals_by_delivered_supply(
    async_client, include_finance, monkeypatch,
) -> None:
    """C6 (R2/R3/R6/R7): короба считаются только у поставок, проведённых штатным
    `_apply_local_delivered`, и только за короба, созданные штатным
    `create_boxes` — не за напрямую вставленные строки моделей. Отчёт проверен
    ДО проведения (0, хотя короб уже есть) и ПОСЛЕ (число появилось в сутках
    проведения без отдельного пересчёта — тот же `build_seller_report`), плюс
    соседние сутки (0), полностью пустой период (0), чужой селлер и чужой
    тенант не подмешиваются, короба Ozon считаются наравне с WB, непустая
    строка селлера (есть факт операции) получает верное число, а не
    нуль-заглушку, и граница московских суток — честная (проверяется по
    реальному хранению `delivered_at` как `datetime` c `tzinfo=UTC`, как пишет
    прод через `operation.confirmed_at`/`datetime.now(UTC)`, а не по
    заранее московским значениям).
    """
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)

    headers, seller_a_id, email = await _admin(async_client)
    seller_b_response = await async_client.post("/sellers", headers=headers, json={"name": "Селлер Б (447)"})
    assert seller_b_response.status_code == 201, seller_b_response.text
    seller_b_id = uuid.UUID(seller_b_response.json()["id"])
    token = await async_client.patch(
        f"/integrations/wildberries/sellers/{seller_a_id}/tokens",
        headers=headers, json={"marketplace_api_token": "wms447-wb-token"},
    )
    assert token.status_code == 200, token.text

    other_headers, other_seller_id, other_email = await _admin(async_client)

    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        other_user = await session.scalar(select(User).where(User.email == other_email))
        assert other_user is not None
        warehouse = Warehouse(tenant_id=user.tenant_id, name="Склад 447", code=f"WMS447-{uuid.uuid4().hex[:8]}")
        other_warehouse = Warehouse(
            tenant_id=other_user.tenant_id, name="Чужой склад 447", code=f"WMS447-OTHER-{uuid.uuid4().hex[:8]}",
        )
        session.add_all([warehouse, other_warehouse])
        await session.flush()
        tenant_id, other_tenant_id = user.tenant_id, other_user.tenant_id
        warehouse_id, other_warehouse_id, actor_id = warehouse.id, other_warehouse.id, user.id

        async with httpx.AsyncClient() as http_client:
            # A1 — WB, граница московских суток: 10.09 00:30 МСК = 09.09 21:30 UTC.
            a1 = await _seed_boxed_supply(
                session, tenant_id=tenant_id, seller_id=seller_a_id, warehouse_id=warehouse_id,
                name="A1", marketplace="wb", box_count=1, actor_user_id=actor_id, http_client=http_client,
            )
            await session.commit()

            # ДО проведения: короб реально создан штатным create_boxes, но
            # delivered_at ещё нет — 0 (C6 «непроведённая поставка с коробами»).
            before = await async_client.get(
                "/billing/seller-report/summary?date_from=2026-09-10&date_to=2026-09-10"
                f"&include_finance={str(include_finance).lower()}",
                headers=headers,
            )
            assert before.status_code == 200, before.text
            assert before.json()["totals"]["fbs_boxes"] == 0

            await _deliver_supply(session, a1, delivered_at=datetime(2026, 9, 9, 21, 30, tzinfo=UTC))
            await session.commit()

            # A2 — WB, проведена накануне (09.09 12:00 МСК = 09:00 UTC) — не в 10.09.
            a2 = await _seed_boxed_supply(
                session, tenant_id=tenant_id, seller_id=seller_a_id, warehouse_id=warehouse_id,
                name="A2", marketplace="wb", box_count=1, actor_user_id=actor_id, http_client=http_client,
            )
            await session.commit()
            await _deliver_supply(session, a2, delivered_at=datetime(2026, 9, 9, 9, 0, tzinfo=UTC))
            await session.commit()

            # A4 — короб создан штатно, пока поставка ещё редактируема (status=draft),
            # затем status выставлен done напрямую, delivered_at не тронут — так
            # выглядит поставка, закрытая в кабинете WB мимо WMS (R3, D2).
            a4 = await _seed_boxed_supply(
                session, tenant_id=tenant_id, seller_id=seller_a_id, warehouse_id=warehouse_id,
                name="A4", marketplace="wb", box_count=1, actor_user_id=actor_id, http_client=http_client,
            )
            a4.status = "done"
            await session.commit()

        # A5 — Ozon, без http_client (create_boxes не требует его для Ozon).
        a5 = await _seed_boxed_supply(
            session, tenant_id=tenant_id, seller_id=seller_a_id, warehouse_id=warehouse_id,
            name="A5", marketplace="ozon", box_count=1, actor_user_id=actor_id,
        )
        await session.commit()
        await _deliver_supply(session, a5, delivered_at=datetime(2026, 9, 10, 12, 0, tzinfo=UTC))
        await session.commit()

        # A6 — проведена внутри периода, но без коробов: вклад 0, а не пропавшая строка.
        a6 = await _seed_boxed_supply(
            session, tenant_id=tenant_id, seller_id=seller_a_id, warehouse_id=warehouse_id,
            name="A6", marketplace="wb", box_count=0, actor_user_id=actor_id,
        )
        await session.commit()
        await _deliver_supply(session, a6, delivered_at=datetime(2026, 9, 10, 15, 0, tzinfo=UTC))
        await session.commit()

        # B1 — другой селлер того же тенанта, Ozon (не подмешивается в фильтр по А).
        b1 = await _seed_boxed_supply(
            session, tenant_id=tenant_id, seller_id=seller_b_id, warehouse_id=warehouse_id,
            name="B1", marketplace="ozon", box_count=1, actor_user_id=actor_id,
        )
        await session.commit()
        await _deliver_supply(session, b1, delivered_at=datetime(2026, 9, 10, 7, 0, tzinfo=UTC))
        await session.commit()

        # X1 — чужой тенант, Ozon (не должен влиять на числа этого тенанта).
        x1 = await _seed_boxed_supply(
            session, tenant_id=other_tenant_id, seller_id=other_seller_id, warehouse_id=other_warehouse_id,
            name="X1", marketplace="ozon", box_count=1, actor_user_id=None,
        )
        await session.commit()
        await _deliver_supply(session, x1, delivered_at=datetime(2026, 9, 10, 8, 0, tzinfo=UTC))
        await session.commit()

        # Непустая строка селлера (review N2/п.3): факт операции селлера А в том же
        # периоде — тогда его строка попадёт в rows, и там тоже нужно верное число
        # коробов, а не нуль-заглушка (R7).
        session.add(OperationFact(
            tenant_id=tenant_id, seller_id=seller_a_id, operation_code="marketplace_outbound_completed",
            billable_service_code="marketplace_outbound", source_kind="marketplace_unload_request",
            source_event_id=uuid.uuid4(), seller_name_snapshot="Селлер А (447)",
            document_type="marketplace_unload", document_id=uuid.uuid4(), source="system",
            occurred_at=datetime(2026, 9, 10, 10, 0, tzinfo=UTC), item_quantity=1,
        ))
        await session.commit()

    params = f"date_from=2026-09-10&date_to=2026-09-10&include_finance={str(include_finance).lower()}"

    summary_all = await async_client.get(f"/billing/seller-report/summary?{params}", headers=headers)
    assert summary_all.status_code == 200, summary_all.text
    payload = summary_all.json()
    # A1(1) + A5(1) + A6(0) + B1(1) = 3. A2 (накануне) и A4 (done без delivered_at) не считаются.
    assert payload["totals"]["fbs_boxes"] == 3
    seller_a_row = next(row for row in payload["rows"] if row["seller_id"] == str(seller_a_id))
    # Непустая строка (есть факт операции) — тоже верное число, а не нуль-заглушка.
    assert seller_a_row["fbs_boxes"] == 2  # A1 + A5; A6 = 0

    summary_a = await async_client.get(
        f"/billing/seller-report/summary?{params}&seller_id={seller_a_id}", headers=headers
    )
    assert summary_a.status_code == 200, summary_a.text
    assert summary_a.json()["totals"]["fbs_boxes"] == 2

    summary_b = await async_client.get(
        f"/billing/seller-report/summary?{params}&seller_id={seller_b_id}", headers=headers
    )
    assert summary_b.status_code == 200, summary_b.text
    assert summary_b.json()["totals"]["fbs_boxes"] == 1

    prev_day_params = f"date_from=2026-09-09&date_to=2026-09-09&include_finance={str(include_finance).lower()}"
    summary_prev_day = await async_client.get(f"/billing/seller-report/summary?{prev_day_params}", headers=headers)
    assert summary_prev_day.status_code == 200, summary_prev_day.text
    # Только A2 (09:00 UTC = 12:00 МСК 09.09). A1 (21:30 UTC = 00:30 МСК 10.09) сюда не попадает — граница суток.
    assert summary_prev_day.json()["totals"]["fbs_boxes"] == 1

    # Полностью пустой период (п.3 замечания ревью): ни поставок, ни фактов.
    empty_params = f"date_from=2026-09-01&date_to=2026-09-01&include_finance={str(include_finance).lower()}"
    summary_empty = await async_client.get(f"/billing/seller-report/summary?{empty_params}", headers=headers)
    assert summary_empty.status_code == 200, summary_empty.text
    assert summary_empty.json()["totals"]["fbs_boxes"] == 0
    assert summary_empty.json()["rows"] == []

    summary_other_tenant = await async_client.get(f"/billing/seller-report/summary?{params}", headers=other_headers)
    assert summary_other_tenant.status_code == 200, summary_other_tenant.text
    assert summary_other_tenant.json()["totals"]["fbs_boxes"] == 1

    details_a = await async_client.get(f"/billing/seller-report/sellers/{seller_a_id}/details?{params}", headers=headers)
    assert details_a.status_code == 200, details_a.text
    assert details_a.json()["totals"]["fbs_boxes"] == 2

    details_b = await async_client.get(f"/billing/seller-report/sellers/{seller_b_id}/details?{params}", headers=headers)
    assert details_b.status_code == 200, details_b.text
    assert details_b.json()["totals"]["fbs_boxes"] == 1
