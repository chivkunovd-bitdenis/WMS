import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.billing import BillingInvoice, BillingLedgerEntry, BillingProfile
from app.services.billing_invoice_service import form_invoice


@pytest.mark.asyncio
async def test_form_invoice_blocks_unpriced() -> None:
    session = AsyncMock()
    session.add = Mock()
    seller_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    entry = BillingLedgerEntry(
        tenant_id=tenant_id,
        seller_id=seller_id,
        source_type="inbound",
        source_id=uuid.uuid4(),
        service_code="inbound",
        unit="document",
        quantity=Decimal("1"),
        amount=None,
        occurred_at=datetime(2026, 7, 5, tzinfo=UTC),
    )
    session.scalar = AsyncMock(
        side_effect=[
            None,
            BillingProfile(tenant_id=tenant_id, seller_id=None, legal_name="FF", inn="123"),
                BillingProfile(
                    tenant_id=tenant_id, seller_id=seller_id, legal_name="Seller", inn="456"
                ),
            None,
        ]
    )
    session.scalars = AsyncMock(return_value=Mock(all=Mock(return_value=[entry])))
    result = await form_invoice(
        session, tenant_id=tenant_id, seller_id=seller_id, period=date(2026, 7, 1)
    )
    assert result.reason == "unpriced"


@pytest.mark.asyncio
async def test_existing_invoice_is_returned_without_duplicate() -> None:
    session = AsyncMock()
    session.add = Mock()
    invoice = BillingInvoice(
        tenant_id=uuid.uuid4(),
        seller_id=uuid.uuid4(),
        period=date(2026, 7, 1),
        number="INV",
        total_amount=Decimal("1"),
        ff_profile_snapshot={},
        seller_profile_snapshot={},
        lines=[],
    )
    session.scalar = AsyncMock(return_value=invoice)
    result = await form_invoice(
        session, tenant_id=invoice.tenant_id, seller_id=invoice.seller_id, period=invoice.period
    )
    assert result is invoice
    session.add.assert_not_called()
