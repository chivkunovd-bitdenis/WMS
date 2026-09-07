"""WMS-011: overlapping invoices, cancellation and concurrent issuing."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal, engine
from app.models.billing import BillingInvoiceV2, BillingInvoiceV2Source, BillingLedgerEntry
from app.models.user import User
from app.services.billing_invoice_v2_service import BillingInvoiceV2Error, create_invoice_v2


async def _setup(client: AsyncClient) -> tuple[dict[str, str], uuid.UUID, dict[str, Any]]:
    suffix = f"invoice-duplicate-{time.time_ns()}"
    registered = await client.post(
        "/auth/register",
        json={
            "organization_name": "Invoice duplicate",
            "slug": suffix,
            "admin_email": f"{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    tenant_id = uuid.UUID((await client.get("/auth/me", headers=headers)).json()["tenant_id"])
    seller = await client.post("/sellers", headers=headers, json={"name": "Селлер"})
    root_ids = [uuid.uuid4(), uuid.uuid4()]
    async with SessionLocal() as session:
        for root_id in root_ids:
            session.add(
                BillingLedgerEntry(
                    id=root_id,
                    tenant_id=tenant_id,
                    seller_id=uuid.UUID(seller.json()["id"]),
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
                )
            )
        await session.commit()
    return (
        headers,
        tenant_id,
        {
            "creation_mode": "selected_operations",
            "seller_id": seller.json()["id"],
            "date_from": "2026-08-01",
            "date_to": "2026-08-31",
            "selected_root_ids": [str(value) for value in root_ids],
        },
    )


@pytest.mark.asyncio
async def test_overlap_rejected_atomically_cancel_releases_and_history_stays(
    async_client: AsyncClient,
) -> None:
    headers, tenant_id, both = await _setup(async_client)
    first = {**both, "selected_root_ids": both["selected_root_ids"][:1]}
    saved = await async_client.post(
        "/billing/invoices-v2", json=first, headers={**headers, "Idempotency-Key": "first"}
    )
    assert saved.status_code == 201, saved.text
    invoice_id = saved.json()["id"]
    for url in ["/billing/invoices-v2/preview", "/billing/invoices-v2"]:
        rejected = await async_client.post(
            url, json=both, headers={**headers, "Idempotency-Key": "overlap"}
        )
        assert rejected.status_code == 422, rejected.text
        assert rejected.json()["detail"] == "selected_source_already_invoiced"
    retry = await async_client.post(
        "/billing/invoices-v2", json=first, headers={**headers, "Idempotency-Key": "first"}
    )
    assert retry.status_code == 201 and retry.json()["id"] == invoice_id
    # An overlapping request must not issue even its unclaimed subset.
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(BillingInvoiceV2)) == 1
        assert await session.scalar(select(func.count()).select_from(BillingInvoiceV2Source)) == 1
    # Tenant and seller boundaries must be checked before any existing-invoice lookup.
    other_seller = await async_client.post("/sellers", headers=headers, json={"name": "Другой"})
    cross_seller = await async_client.post(
        "/billing/invoices-v2/preview",
        headers=headers,
        json={**first, "seller_id": other_seller.json()["id"]},
    )
    assert cross_seller.status_code == 422
    assert cross_seller.json()["detail"] == "selected_source_not_found"
    other_headers, _, other_body = await _setup(async_client)
    foreign = await async_client.post(
        "/billing/invoices-v2/preview",
        headers=other_headers,
        json={**other_body, "selected_root_ids": first["selected_root_ids"]},
    )
    assert foreign.status_code == 422 and foreign.json()["detail"] == "selected_source_not_found"
    assert (
        await async_client.post(f"/billing/invoices-v2/{invoice_id}/cancel", headers=other_headers)
    ).status_code == 404
    for _ in range(2):
        cancelled = await async_client.post(
            f"/billing/invoices-v2/{invoice_id}/cancel", headers=headers
        )
        assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    # An old retry returns the cancelled snapshot, never reissues it.
    retry = await async_client.post(
        "/billing/invoices-v2", json=first, headers={**headers, "Idempotency-Key": "first"}
    )
    assert retry.json()["id"] == invoice_id and retry.json()["status"] == "cancelled"
    preview = await async_client.post("/billing/invoices-v2/preview", json=both, headers=headers)
    assert preview.status_code == 200 and preview.json()["total_amount_kopecks"] == 2000
    reissued = await async_client.post(
        "/billing/invoices-v2", json=both, headers={**headers, "Idempotency-Key": "reissued"}
    )
    assert reissued.status_code == 201 and reissued.json()["id"] != invoice_id
    old = await async_client.get(f"/billing/invoices-v2/{invoice_id}", headers=headers)
    assert old.json()["total_amount_kopecks"] == saved.json()["total_amount_kopecks"]
    assert old.json()["lines"] == saved.json()["lines"]
    async with SessionLocal() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BillingInvoiceV2Source)
                .where(BillingInvoiceV2Source.tenant_id == tenant_id)
            )
            == 3
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("same_key", [False, True])
async def test_postgres_concurrent_issue_waits_then_rechecks(
    async_client: AsyncClient,
    same_key: bool,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("Row-lock concurrency requires PostgreSQL")
    _, tenant_id, body = await _setup(async_client)
    async with SessionLocal() as lookup:
        user_id = await lookup.scalar(select(User.id).where(User.tenant_id == tenant_id))
    assert user_id is not None
    async with SessionLocal() as first_session:
        first = await create_invoice_v2(
            first_session,
            tenant_id=tenant_id,
            user_id=user_id,
            request=body,
            idempotency_key="first",
        )
        started = asyncio.Event()

        async def second_request() -> uuid.UUID | str:
            async with SessionLocal() as second_session:
                started.set()
                try:
                    invoice = await create_invoice_v2(
                        second_session,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        request=body,
                        idempotency_key="first" if same_key else "second",
                    )
                    await second_session.commit()
                    return invoice.id
                except BillingInvoiceV2Error as exc:
                    await second_session.rollback()
                    return str(exc)

        second_task = asyncio.create_task(second_request())
        try:
            await started.wait()
            # The first transaction is deliberately still open: the second
            # must wait instead of validating against an empty source history.
            done, _ = await asyncio.wait({second_task}, timeout=0.2)
            assert not done
            await first_session.commit()
            result = await asyncio.wait_for(second_task, timeout=5)
        finally:
            if not second_task.done():
                second_task.cancel()
                await asyncio.gather(second_task, return_exceptions=True)
        assert result == (first.id if same_key else "selected_source_already_invoiced")
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(BillingInvoiceV2)) == 1
        assert await session.scalar(select(func.count()).select_from(BillingInvoiceV2Source)) == 2
