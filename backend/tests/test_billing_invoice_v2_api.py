from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.billing import BillingInvoiceV2Source, BillingLedgerEntry


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
