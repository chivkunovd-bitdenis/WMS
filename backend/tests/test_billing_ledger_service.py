import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.billing import BillingLedgerEntry
from app.services.billing_ledger_service import record_operational_charge


@pytest.mark.asyncio
async def test_operational_charge_without_tariff_is_unpriced() -> None:
    session = AsyncMock()
    session.add = Mock()
    session.scalar = AsyncMock(side_effect=[None, None])
    tenant_id = uuid.uuid4()
    source_id = uuid.uuid4()

    entry = await record_operational_charge(
        session,
        tenant_id=tenant_id,
        seller_id=uuid.uuid4(),
        source_type="inbound_intake",
        source_id=source_id,
        source="inbound",
        service_code="inbound",
        quantity=Decimal("3"),
        occurred_at=datetime.now(UTC),
        performer_id=uuid.uuid4(),
    )

    assert isinstance(entry, BillingLedgerEntry)
    assert entry.tariff_version_id is None
    assert entry.rate is None
    assert entry.amount is None
    assert entry.quantity == Decimal("3")
    session.add.assert_called_once_with(entry)


@pytest.mark.asyncio
async def test_repeated_operational_charge_returns_existing_entry() -> None:
    session = AsyncMock()
    session.add = Mock()
    existing = BillingLedgerEntry(
        tenant_id=uuid.uuid4(),
        source_type="marketplace_unload",
        source_id=uuid.uuid4(),
        source="marketplace_unload",
        service_code="marketplace_outbound",
        unit="item",
        quantity=Decimal("4"),
        occurred_at=datetime.now(UTC),
    )
    session.scalar = AsyncMock(return_value=existing)

    result = await record_operational_charge(
        session,
        tenant_id=existing.tenant_id,
        seller_id=None,
        source_type=existing.source_type,
        source_id=existing.source_id,
        source=existing.source,
        service_code=existing.service_code,
        quantity=Decimal("99"),
        occurred_at=existing.occurred_at,
        performer_id=None,
    )

    assert result is existing
    session.add.assert_not_called()
