from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.billing import BillingInvoice, BillingLedgerEntry, BillingRunIssue
from app.models.inbound_intake import InboundIntakeRequest
from app.models.warehouse import Warehouse


async def _billing_context(
    async_client: AsyncClient,
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID, uuid.UUID]:
    suffix = f"invoice-{time.time_ns()}"
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Invoice FF",
            "slug": suffix,
            "admin_email": f"{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": "ООО Альфа"},
    )
    assert seller.status_code == 201, seller.text
    seller_id = uuid.UUID(seller.json()["id"])

    ff_profile = await async_client.put(
        "/billing/profiles/ff",
        headers=headers,
        json={
            "legal_name": "ООО ФФ",
            "inn": "7707083893",
            "bank_name": "Банк",
            "bik": "044525225",
            "settlement_account": "40702810000000000001",
            "correspondent_account": "30101810400000000225",
        },
    )
    assert ff_profile.status_code == 200, ff_profile.text
    seller_profile = await async_client.put(
        f"/billing/profiles/sellers/{seller_id}",
        headers=headers,
        json={"legal_name": "ООО Альфа", "inn": "7707083893"},
    )
    assert seller_profile.status_code == 200, seller_profile.text

    async with SessionLocal() as session:
        warehouse_id = await session.scalar(
            select(Warehouse.id).where(Warehouse.tenant_id == tenant_id)
        )
        if warehouse_id is None:
            warehouse = Warehouse(
                tenant_id=tenant_id,
                name="Основной",
                code=f"invoice-{time.time_ns()}",
            )
            session.add(warehouse)
            await session.flush()
            warehouse_id = warehouse.id
        await session.commit()
    return headers, tenant_id, seller_id, warehouse_id


@pytest.mark.asyncio
async def test_billing_http_parallel_form_uses_date_alias_and_keeps_document_snapshot(
    async_client: AsyncClient,
) -> None:
    """S-31-TC-006/014/015: one immutable invoice and idempotent cancellation."""
    headers, tenant_id, seller_id, warehouse_id = await _billing_context(async_client)
    source_id = uuid.uuid4()
    ledger_id = uuid.uuid4()
    async with SessionLocal() as session:
        session.add(
            InboundIntakeRequest(
                id=source_id,
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                seller_id=seller_id,
                status="done",
                document_number="ПР-101",
            )
        )
        session.add(
            BillingLedgerEntry(
                id=ledger_id,
                tenant_id=tenant_id,
                seller_id=seller_id,
                service_code="inbound",
                source="inbound",
                source_type="inbound_intake",
                source_id=source_id,
                unit="item",
                quantity=Decimal("14"),
                rate=4500,
                amount=63000,
                occurred_at=datetime(2026, 7, 15, 9, tzinfo=UTC),
            )
        )
        await session.commit()

    ledger = await async_client.get(
        "/billing/ledger?date=2026-07-01&document_number=ПР-101",
        headers=headers,
    )
    assert ledger.status_code == 200, ledger.text
    assert len(ledger.json()["entries"]) == 1
    assert ledger.json()["entries"][0]["document_number"] == "ПР-101"

    form_url = f"/billing/invoices/{seller_id}/2026-07/form"
    first, second = await asyncio.gather(
        async_client.post(form_url, headers=headers),
        async_client.post(form_url, headers=headers),
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]

    invoice_id = uuid.UUID(first.json()["id"])
    detail = await async_client.get(f"/billing/invoices/{invoice_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert Decimal(str(detail.json()["total_amount"])) == Decimal("63000")
    assert detail.json()["lines"][0]["documents"][0]["number"] == "ПР-101"

    first_cancel = await async_client.post(
        f"/billing/invoices/{invoice_id}/cancel",
        headers=headers,
    )
    second_cancel = await async_client.post(
        f"/billing/invoices/{invoice_id}/cancel",
        headers=headers,
    )
    assert first_cancel.json()["status"] == "cancelled"
    assert second_cancel.json()["status"] == "cancelled"
    async with SessionLocal() as session:
        invoices = list(
            (
                await session.scalars(
                    select(BillingInvoice).where(
                        BillingInvoice.tenant_id == tenant_id,
                        BillingInvoice.seller_id == seller_id,
                        BillingInvoice.period == date(2026, 7, 1),
                    )
                )
            ).all()
        )
        assert len(invoices) == 1
        assert invoices[0].status == "cancelled"


@pytest.mark.asyncio
async def test_form_invoice_returns_empty_for_a_month_without_charges(
    async_client: AsyncClient,
) -> None:
    """S-31-TC-006: a month without charges is an empty state, not a blocker."""
    headers, _tenant_id, seller_id, _warehouse_id = await _billing_context(async_client)

    formed = await async_client.post(
        f"/billing/invoices/{seller_id}/2026-07/form",
        headers=headers,
    )

    assert formed.status_code == 200, formed.text
    assert formed.json() == {"status": "empty"}

    invoices = await async_client.get("/billing/invoices?period=2026-07", headers=headers)
    assert invoices.status_code == 200, invoices.text
    assert invoices.json() == {"invoices": [], "issues": []}


@pytest.mark.asyncio
async def test_form_invoice_keeps_unpriced_charge_as_blocking_reason(
    async_client: AsyncClient,
) -> None:
    """S-31-TC-012: a charge without a tariff remains an actionable blocker."""
    headers, tenant_id, seller_id, _warehouse_id = await _billing_context(async_client)
    async with SessionLocal() as session:
        session.add(
            BillingLedgerEntry(
                tenant_id=tenant_id,
                seller_id=seller_id,
                service_code="inbound",
                source="inbound",
                source_type="test_fact",
                source_id=uuid.uuid4(),
                unit="document",
                quantity=Decimal("1"),
                rate=None,
                amount=None,
                occurred_at=datetime(2026, 7, 15, 9, tzinfo=UTC),
            )
        )
        await session.commit()

    formed = await async_client.post(
        f"/billing/invoices/{seller_id}/2026-07/form",
        headers=headers,
    )

    assert formed.status_code == 200, formed.text
    assert formed.json() == {
        "status": "blocked",
        "reason": "unpriced",
        "message": "Нет тарифа",
    }


@pytest.mark.asyncio
async def test_invoice_list_hides_resolved_and_nonblocking_run_issues(
    async_client: AsyncClient,
) -> None:
    """S-31-TC-013: fixed causes no longer keep retry disabled; no_entries is not a blocker."""
    headers, tenant_id, seller_id, _warehouse_id = await _billing_context(async_client)
    async with SessionLocal() as session:
        session.add(
            BillingLedgerEntry(
                tenant_id=tenant_id,
                seller_id=seller_id,
                service_code="inbound",
                source="inbound",
                source_type="test_fact",
                source_id=uuid.uuid4(),
                unit="document",
                quantity=Decimal("1"),
                rate=100,
                amount=100,
                occurred_at=datetime(2026, 6, 15, 9, tzinfo=UTC),
            )
        )
        session.add_all(
            [
                BillingRunIssue(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    period=date(2026, 6, 1),
                    reason="unpriced",
                    message="Нет тарифа",
                ),
                BillingRunIssue(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    period=date(2026, 7, 1),
                    reason="no_entries",
                    message="Нет начислений для формирования",
                ),
            ]
        )
        await session.commit()

    june = await async_client.get("/billing/invoices?period=2026-06", headers=headers)
    july = await async_client.get("/billing/invoices?period=2026-07", headers=headers)
    assert june.status_code == 200, june.text
    assert july.status_code == 200, july.text
    assert june.json()["issues"] == []
    assert july.json()["issues"] == []
