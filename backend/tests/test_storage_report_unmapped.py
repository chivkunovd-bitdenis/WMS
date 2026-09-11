"""WMS-430: historical storage charges survive missing product cards."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.models.billing import BillingLedgerEntry
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services.storage_statement_service import build_storage_report


@pytest.mark.asyncio
async def test_missing_card_keeps_money_but_is_not_assigned_to_a_category(db_session):
    tenant = Tenant(name="Storage fixture", slug=uuid.uuid4().hex)
    db_session.add(tenant)
    await db_session.flush()
    seller = Seller(tenant_id=tenant.id, name="Historical seller")
    warehouse = Warehouse(tenant_id=tenant.id, name="Storage", code="STORAGE")
    db_session.add_all([seller, warehouse])
    await db_session.flush()
    db_session.add(BillingLedgerEntry(
        tenant_id=tenant.id, seller_id=seller.id, warehouse_id=warehouse.id,
        entry_type="charge", service_code="storage", source="automatic",
        source_type="storage_day", source_id=uuid.uuid4(),
        event_kind="storage_day:2026-09-09", unit="liter_day",
        quantity=Decimal("2.125"), rate=100, amount=213,
        occurred_at=datetime(2026, 9, 9, 12, tzinfo=UTC),
    ))
    await db_session.flush()
    period = dict(date_from=date(2026, 9, 9), date_to=date(2026, 9, 9))
    report = await build_storage_report(db_session, tenant.id, **period)
    assert report.liter_days == Decimal("2.125")
    assert report.amount_kopecks == 213
    row = report.sellers[0].products[0]
    assert row.product_id is None and row.volume_liters is None
    assert row.liter_days == report.liter_days and row.amount_kopecks == 213
    filtered = await build_storage_report(db_session, tenant.id, category="Shoes", **period)
    assert filtered.sellers == [] and filtered.liter_days == 0
