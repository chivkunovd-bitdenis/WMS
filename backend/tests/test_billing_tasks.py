from __future__ import annotations

import time
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.billing import BillingInvoice, BillingLedgerEntry, BillingProfile
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.services import billing_invoice_service
from app.tasks import billing_tasks


def test_billing_invoice_daily_schedule_is_0230_moscow() -> None:
    schedule = celery_app.conf.beat_schedule["billing-invoices-daily"]["schedule"]

    assert celery_app.conf.timezone is None
    assert celery_app.conf.enable_utc is True
    assert schedule._orig_hour == 23
    assert schedule._orig_minute == 30


def test_billing_schedule_keeps_existing_wb_crontab_semantics() -> None:
    wb_schedule = celery_app.conf.beat_schedule["wb-mp-warehouses-daily"]["schedule"]

    assert wb_schedule._orig_hour == 3
    assert wb_schedule._orig_minute == 0


class _August2026DateTime(datetime):
    @classmethod
    def now(cls, tz: ZoneInfo | None = None) -> datetime:
        frozen = datetime(2026, 8, 23, 12, tzinfo=UTC)
        return frozen.astimezone(tz) if tz is not None else frozen.replace(tzinfo=None)


def _complete_ff_profile(tenant_id: uuid.UUID) -> BillingProfile:
    return BillingProfile(
        tenant_id=tenant_id,
        seller_id=None,
        legal_name="ООО ФФ",
        inn="7707083893",
        bank_name="Банк",
        bik="044525225",
        settlement_account="40702810000000000001",
        correspondent_account="30101810400000000225",
    )


def _complete_seller_profile(tenant_id: uuid.UUID, seller_id: uuid.UUID) -> BillingProfile:
    return BillingProfile(
        tenant_id=tenant_id,
        seller_id=seller_id,
        legal_name="ООО Селлер",
        inn="7707083893",
    )


def _ledger_entry(
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    occurred_at: datetime,
) -> BillingLedgerEntry:
    return BillingLedgerEntry(
        tenant_id=tenant_id,
        seller_id=seller_id,
        service_code="inbound",
        source="inbound",
        source_type="daily-task-test",
        source_id=uuid.uuid4(),
        unit="document",
        quantity=Decimal("1"),
        rate=4500,
        amount=4500,
        occurred_at=occurred_at,
    )


@pytest.mark.asyncio
async def test_billing_invoice_daily_forms_all_closed_months_and_is_idempotent(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S-31-TC-006: daily job commits every seller/month and never duplicates invoices."""
    del async_client  # Initializes the isolated database used by the background task.
    suffix = str(time.time_ns())
    tenant_id = uuid.uuid4()
    seller_a_id = uuid.uuid4()
    seller_b_id = uuid.uuid4()
    commit_calls: list[AsyncSession] = []
    original_commit = AsyncSession.commit

    async def count_commit(session: AsyncSession) -> None:
        commit_calls.append(session)
        await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", count_commit)
    monkeypatch.setattr(billing_tasks, "datetime", _August2026DateTime)
    monkeypatch.setattr(billing_invoice_service, "datetime", _August2026DateTime)

    async with SessionLocal() as session:
        session.add_all(
            [
                Tenant(id=tenant_id, name="Daily invoices", slug=f"daily-invoices-{suffix}"),
                Seller(id=seller_a_id, tenant_id=tenant_id, name="Селлер А"),
                Seller(id=seller_b_id, tenant_id=tenant_id, name="Селлер Б"),
                _complete_ff_profile(tenant_id),
                _complete_seller_profile(tenant_id, seller_a_id),
                _complete_seller_profile(tenant_id, seller_b_id),
                _ledger_entry(
                    tenant_id,
                    seller_a_id,
                    datetime(2026, 6, 15, 12, tzinfo=UTC),
                ),
                _ledger_entry(
                    tenant_id,
                    seller_a_id,
                    datetime(2026, 7, 15, 12, tzinfo=UTC),
                ),
                _ledger_entry(
                    tenant_id,
                    seller_b_id,
                    datetime(2026, 7, 20, 12, tzinfo=UTC),
                ),
            ]
        )
        await session.commit()
    commit_calls.clear()

    await billing_tasks._run_billing_invoices_daily()

    async with SessionLocal() as session:
        invoices = list(
            (
                await session.scalars(
                    select(BillingInvoice).where(BillingInvoice.tenant_id == tenant_id)
                )
            ).all()
        )
    assert {(invoice.seller_id, invoice.period) for invoice in invoices} == {
        (seller_a_id, date(2026, 6, 1)),
        (seller_a_id, date(2026, 7, 1)),
        (seller_b_id, date(2026, 7, 1)),
    }
    # Two sellers times two closed months: the empty June for seller B is committed too.
    assert len(commit_calls) == 4

    commit_calls.clear()
    await billing_tasks._run_billing_invoices_daily()

    async with SessionLocal() as session:
        invoice_count = await session.scalar(
            select(func.count(BillingInvoice.id)).where(
                BillingInvoice.tenant_id == tenant_id
            )
        )
    assert invoice_count == 3
    assert len(commit_calls) == 4
