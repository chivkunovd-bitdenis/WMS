from __future__ import annotations

import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.billing import BillingLedgerEntry
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.services.billing_invoice_service import form_invoice


@celery_app.task(name="wms.billing_invoices_daily")
def run_billing_invoices_daily_task() -> None:
    asyncio.run(_run_billing_invoices_daily())


async def _run_billing_invoices_daily() -> None:
    today = datetime.now(ZoneInfo("Europe/Moscow")).date()
    current = date(today.year, today.month, 1)
    periods: list[date] = []
    period = date(
        current.year - (current.month == 1),
        12 if current.month == 1 else current.month - 1,
        1,
    )
    # Catch up all closed months represented by ledger facts. The invoice
    # service remains idempotent, so repeated daily runs are safe.
    async with SessionLocal() as session:
        earliest = await session.scalar(select(func.min(BillingLedgerEntry.occurred_at)))
    if earliest is not None:
        first = earliest.astimezone(ZoneInfo("Europe/Moscow")).date().replace(day=1)
        while period >= first:
            periods.append(period)
            period = date(
                period.year - (period.month == 1),
                12 if period.month == 1 else period.month - 1,
                1,
            )
    async with SessionLocal() as session:
        tenants = (await session.scalars(select(Tenant))).all()
        for tenant in tenants:
            sellers = (
                await session.scalars(select(Seller).where(Seller.tenant_id == tenant.id))
            ).all()
            for seller in sellers:
                for closed_period in periods:
                    try:
                        await form_invoice(
                            session,
                            tenant_id=tenant.id,
                            seller_id=seller.id,
                            period=closed_period,
                        )
                        await session.commit()
                    except ValueError:
                        await session.rollback()
