"""WMS-406/407: shipment selection and explicit invoice adjustment."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.billing import BillingLedgerEntry, BillingTariffVersionV2
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from tests.test_billing_invoice_v2_duplicates import _setup


async def shipment(client, priced=True):
    headers, tenant_id, body = await _setup(client)
    seller_id = uuid.UUID(body["seller_id"])
    async with SessionLocal() as session:
        tenant = await session.get(Tenant, tenant_id)
        tenant.billing_enabled_from = None
        warehouse = Warehouse(tenant_id=tenant_id, name="WMS406 synthetic", code="WMS406")
        session.add(warehouse)
        await session.flush()
        supply = FbsSupply(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse.id,
            name="WMS406 synthetic",
            delivery_type="pvz",
            delivered_at=datetime(2026, 8, 20, tzinfo=UTC),
        )
        session.add(supply)
        await session.flush()
        order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse.id,
            supply_id=supply.id,
            wb_order_id=406001,
            status="in_delivery",
            created_at_wb=datetime(2026, 8, 1, tzinfo=UTC),
            deadline_at=datetime(2026, 8, 21, tzinfo=UTC),
            mapping_status="missing",
            reserve_status="released",
        )
        session.add(order)
        if priced:
            session.add(
                BillingTariffVersionV2(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    service_code="fbs_order",
                    unit="item",
                    rate=1250,
                    enabled=True,
                    valid_from_at=datetime(2026, 8, 1, tzinfo=UTC),
                )
            )
        await session.commit()
        order_id = order.id
    body["selected_root_ids"] = []
    body["selected_sources"] = [
        {"source_type": "fbs_order", "source_id": str(order_id), "service_code": "fbs_order"}
    ]
    return headers, body, order_id


@pytest.mark.asyncio
async def test_confirmed_no_gate_deduplicates_preserves_calculation(async_client):
    headers, body, order_id = await shipment(async_client)
    preview = await async_client.post("/billing/invoices-v2/preview", headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["total_amount_kopecks"] == 1250
    async with SessionLocal() as session:
        assert (
            await session.scalar(
                select(BillingLedgerEntry).where(BillingLedgerEntry.source_id == order_id)
            )
            is None
        )
    body["selected_sources"] *= 2
    body["final_amount"] = "10.00"
    saved = await async_client.post(
        "/billing/invoices-v2", headers={**headers, "Idempotency-Key": "ship"}, json=body
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["total_amount_kopecks"] == 1000
    assert [line["total_amount_kopecks"] for line in saved.json()["lines"]] == [1250, -250]
    async with SessionLocal() as session:
        ledger = await session.scalar(
            select(BillingLedgerEntry).where(BillingLedgerEntry.source_id == order_id)
        )
        assert ledger.amount == 1250
        body["selected_root_ids"] = [str(ledger.id)]
    overlap = await async_client.post(
        "/billing/invoices-v2", headers={**headers, "Idempotency-Key": "overlap"}, json=body
    )
    assert (
        overlap.status_code == 422
        and overlap.json()["detail"] == "selected_source_already_invoiced"
    )


@pytest.mark.asyncio
async def test_missing_price_requires_explicit_total(async_client):
    headers, body, order_id = await shipment(async_client, priced=False)
    preview = await async_client.post("/billing/invoices-v2/preview", headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["total_amount_kopecks"] is None
    assert preview.json()["lines"][0]["total_amount_kopecks"] is None
    assert "Нет ставки" in preview.json()["lines"][0]["description"]
    rejected = await async_client.post(
        "/billing/invoices-v2", headers={**headers, "Idempotency-Key": "missing"}, json=body
    )
    assert rejected.status_code == 422
    saved = await async_client.post(
        "/billing/invoices-v2",
        headers={**headers, "Idempotency-Key": "explicit"},
        json={**body, "final_amount": "99.00"},
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["total_amount_kopecks"] == 9900
    assert saved.json()["lines"][0]["total_amount_kopecks"] is None
    repeat = await async_client.post(
        "/billing/invoices-v2",
        headers={**headers, "Idempotency-Key": "another"},
        json={**body, "final_amount": "99.00"},
    )
    assert (
        repeat.status_code == 422 and repeat.json()["detail"] == "selected_source_already_invoiced"
    )
    original = await async_client.get("/billing/invoices-v2/" + saved.json()["id"], headers=headers)
    assert original.json()["lines"][0]["total_amount_kopecks"] is None
    assert "исходный расчёт неполный" in saved.json()["lines"][-1]["description"]
    async with SessionLocal() as session:
        ledger = await session.scalar(
            select(BillingLedgerEntry).where(BillingLedgerEntry.source_id == order_id)
        )
        assert ledger.amount is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["unconfirmed", "period", "seller", "negative", "overflow"])
async def test_source_and_amount_guards(async_client, failure):
    headers, body, order_id = await shipment(async_client)
    if failure == "unconfirmed":
        async with SessionLocal() as session:
            order = await session.get(FbsOrder, order_id)
            supply = await session.get(FbsSupply, order.supply_id)
            supply.delivered_at = None
            order.status = "done"
            await session.commit()
    elif failure == "period":
        body["date_to"] = "2026-08-19"
    elif failure == "seller":
        seller = await async_client.post("/sellers", headers=headers, json={"name": "Other"})
        body["seller_id"] = seller.json()["id"]
    else:
        body["final_amount"] = "-1.00" if failure == "negative" else "999999999.00"
    response = await async_client.post(
        "/billing/invoices-v2", headers={**headers, "Idempotency-Key": failure}, json=body
    )
    assert response.status_code == 422, response.text
