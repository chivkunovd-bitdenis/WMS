"""WMS-406: both invoice writers share source ownership and seller locking."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date

import pytest
from sqlalchemy import func, select

from app.db.session import SessionLocal, engine
from app.models.billing import (
    BillingInvoice,
    BillingInvoiceV2,
    BillingInvoiceV2Source,
    BillingLedgerEntry,
)
from app.models.user import User
from app.services.billing_invoice_service import form_invoice
from app.services.billing_invoice_v2_service import BillingInvoiceV2Error, create_invoice_v2
from tests.test_billing_invoice_api import _add_priced_ledger_entry, _billing_context
from tests.test_billing_invoice_v2_duplicates import _setup


@pytest.mark.asyncio
@pytest.mark.parametrize("first_format", ["legacy", "v2"])
async def test_cross_format_overlap_is_atomic_and_cancel_releases(async_client, first_format):
    headers, tenant, seller, _ = await _billing_context(async_client)
    await _add_priced_ledger_entry(tenant_id=tenant, seller_id=seller)
    async with SessionLocal() as session:
        root = await session.scalar(select(BillingLedgerEntry.id))
    body = {
        "creation_mode": "selected_operations",
        "seller_id": str(seller),
        "date_from": "2026-07-01",
        "date_to": "2026-07-31",
        "selected_root_ids": [str(root)],
    }
    legacy_url = f"/billing/invoices/{seller}/2026-07/form"
    if first_format == "legacy":
        first = await async_client.post(legacy_url, headers=headers)
    else:
        first = await async_client.post(
            "/billing/invoices-v2", headers={**headers, "Idempotency-Key": "first"}, json=body
        )
    assert first.status_code in (200, 201), first.text
    assert first.json()["status"] == "issued"
    # A second, unoccupied charge must not be silently issued as a partial invoice.
    await _add_priced_ledger_entry(tenant_id=tenant, seller_id=seller)
    async with SessionLocal() as session:
        body["selected_root_ids"] = [
            str(x) for x in await session.scalars(select(BillingLedgerEntry.id))
        ]
    if first_format == "legacy":
        for url in ["/billing/invoices-v2/preview", "/billing/invoices-v2"]:
            denied = await async_client.post(
                url, headers={**headers, "Idempotency-Key": "second"}, json=body
            )
            assert (
                denied.status_code == 422
                and denied.json()["detail"] == "selected_source_already_invoiced"
            ), denied.text
    else:
        denied = await async_client.post(legacy_url, headers=headers)
        assert (
            denied.status_code == 400
            and denied.json()["detail"] == "selected_source_already_invoiced"
        ), denied.text
    async with SessionLocal() as session:
        assert (await session.scalar(select(func.count()).select_from(BillingInvoice))) + (
            await session.scalar(select(func.count()).select_from(BillingInvoiceV2))
        ) == 1
    cancel_base = "invoices" if first_format == "legacy" else "invoices-v2"
    cancelled = await async_client.post(
        f"/billing/{cancel_base}/{first.json()['id']}/cancel", headers=headers
    )
    assert cancelled.status_code == 200
    if first_format == "legacy":
        second = await async_client.post(
            "/billing/invoices-v2", headers={**headers, "Idempotency-Key": "second"}, json=body
        )
        assert second.status_code == 201, second.text
        assert second.json()["total_amount_kopecks"] == 200
    else:
        second = await async_client.post(legacy_url, headers=headers)
        assert second.status_code == 200 and second.json()["status"] == "issued", second.text
        assert int(float(second.json()["total_amount"])) == 200


@pytest.mark.asyncio
async def test_storage_cancel_releases_same_days(async_client):
    headers, _, body = await _setup(async_client)
    async with SessionLocal() as session:
        root = await session.get(BillingLedgerEntry, uuid.UUID(body["selected_root_ids"][0]))
        root.service_code = "storage"
        root.source_type = "storage_day"
        await session.commit()
    body.update(selected_root_ids=[], include_storage=True)
    first = await async_client.post(
        "/billing/invoices-v2", headers={**headers, "Idempotency-Key": "storage1"}, json=body
    )
    assert first.status_code == 201, first.text
    denied = await async_client.post(
        "/billing/invoices-v2", headers={**headers, "Idempotency-Key": "storage2"}, json=body
    )
    assert denied.status_code == 422
    assert (
        await async_client.post(
            f"/billing/invoices-v2/{first.json()['id']}/cancel", headers=headers
        )
    ).status_code == 200
    second = await async_client.post(
        "/billing/invoices-v2", headers={**headers, "Idempotency-Key": "storage2"}, json=body
    )
    assert second.status_code == 201 and second.json()["total_amount_kopecks"] == 1000, second.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "first_format,second_format", [("storage", "storage"), ("legacy", "v2"), ("v2", "legacy")]
)
async def test_postgres_concurrent_writers_recheck_after_shared_lock(
    async_client, first_format, second_format
):
    if engine.dialect.name != "postgresql":
        pytest.skip("Requires real PostgreSQL row locks")
    _, tenant, seller, _ = await _billing_context(async_client)
    await _add_priced_ledger_entry(tenant_id=tenant, seller_id=seller)
    async with SessionLocal() as session:
        root = await session.scalar(select(BillingLedgerEntry))
        user = await session.scalar(select(User.id).where(User.tenant_id == tenant))
        root_id = root.id
        if first_format == "storage":
            root.service_code = "storage"
            root.source_type = "storage_day"
        await session.commit()
    body = {
        "creation_mode": "selected_operations",
        "seller_id": str(seller),
        "date_from": "2026-07-01",
        "date_to": "2026-07-31",
        "selected_root_ids": [] if first_format == "storage" else [str(root_id)],
        "include_storage": first_format == "storage",
    }

    async def issue(session, format_, key):
        if format_ == "legacy":
            return await form_invoice(
                session, tenant_id=tenant, seller_id=seller, period=date(2026, 7, 1)
            )
        return await create_invoice_v2(
            session, tenant_id=tenant, user_id=user, request=body, idempotency_key=key
        )

    async with SessionLocal() as first_session:
        first = await issue(first_session, first_format, "first")
        assert isinstance(first, (BillingInvoice, BillingInvoiceV2))
        started = asyncio.Event()

        async def second_request():
            async with SessionLocal() as session:
                started.set()
                try:
                    result = await issue(session, second_format, "second")
                    await session.commit()
                    return result
                except (BillingInvoiceV2Error, ValueError) as exc:
                    await session.rollback()
                    return str(exc)

        pending = asyncio.create_task(second_request())
        try:
            await started.wait()
            done, _ = await asyncio.wait({pending}, timeout=0.2)
            assert not done
            await first_session.commit()
            result = await asyncio.wait_for(pending, timeout=5)
            assert result == (
                "selected_operations_required"
                if first_format == "storage"
                else "selected_source_already_invoiced"
            )
        finally:
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
    async with SessionLocal() as session:
        assert (await session.scalar(select(func.count()).select_from(BillingInvoice))) + (
            await session.scalar(select(func.count()).select_from(BillingInvoiceV2))
        ) == 1
        if first_format == "storage":
            assert (
                await session.scalar(select(func.count()).select_from(BillingInvoiceV2Source)) == 1
            )
