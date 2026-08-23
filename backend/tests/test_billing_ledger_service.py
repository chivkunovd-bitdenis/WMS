import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.billing import BillingLedgerEntry
from app.services.billing_ledger_service import (
    record_operational_charge,
    record_operational_reversal,
)


def _savepoint_session() -> AsyncMock:
    session = AsyncMock()
    savepoint = AsyncMock()
    session.begin_nested = AsyncMock(return_value=savepoint)
    return session


@pytest.mark.asyncio
async def test_operational_charge_without_tariff_is_unpriced() -> None:
    session = _savepoint_session()
    session.add = Mock()
    session.scalar = AsyncMock(side_effect=[date(2026, 1, 1), None, None, None])
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
    session = _savepoint_session()
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
    session.scalar = AsyncMock(side_effect=[date(2026, 1, 1), existing])

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


@pytest.mark.asyncio
async def test_tariff_period_uses_moscow_calendar_date() -> None:
    session = _savepoint_session()
    session.add = Mock()
    tariff = Mock(id=uuid.uuid4(), amount=Decimal("10.00"), unit="item")
    session.scalar = AsyncMock(side_effect=[date(2026, 1, 1), None, None, tariff])

    entry = await record_operational_charge(
        session,
        tenant_id=uuid.uuid4(),
        seller_id=None,
        source_type="inbound_intake",
        source_id=uuid.uuid4(),
        source="inbound",
        service_code="inbound",
        quantity=Decimal("2"),
        occurred_at=datetime(2026, 2, 28, 21, 30, tzinfo=UTC),
        performer_id=None,
    )

    assert entry.tariff_version_id == tariff.id
    assert session.add.call_args.args[0] is entry


@pytest.mark.asyncio
async def test_operational_charge_before_billing_activation_is_not_recorded() -> None:
    session = _savepoint_session()
    session.add = Mock()
    session.scalar = AsyncMock(return_value=date(2026, 3, 1))

    entry = await record_operational_charge(
        session,
        tenant_id=uuid.uuid4(),
        seller_id=uuid.uuid4(),
        source_type="inbound_intake",
        source_id=uuid.uuid4(),
        source="inbound",
        service_code="inbound",
        quantity=Decimal("3"),
        occurred_at=datetime(2026, 2, 28, 20, 30, tzinfo=UTC),
        performer_id=uuid.uuid4(),
    )

    assert entry is None
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_operational_reversal_preserves_snapshot_and_is_idempotent() -> None:
    session = _savepoint_session()
    session.add = Mock()
    original = BillingLedgerEntry(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        seller_id=uuid.uuid4(),
        tariff_version_id=uuid.uuid4(),
        performer_id=uuid.uuid4(),
        source_type="marketplace_unload",
        source_id=uuid.uuid4(),
        source="marketplace_unload",
        service_code="marketplace_outbound",
        unit="item",
        quantity=Decimal("4"),
        rate=Decimal("12.50"),
        amount=Decimal("50.00"),
        occurred_at=datetime(2026, 8, 20, 10, tzinfo=UTC),
    )
    session.scalar = AsyncMock(side_effect=[original, None])
    cancelled_by = uuid.uuid4()

    reversal = await record_operational_reversal(
        session,
        tenant_id=original.tenant_id,
        source_type=original.source_type,
        source_id=original.source_id,
        occurred_at=datetime(2026, 9, 2, 10, tzinfo=UTC),
        performer_id=cancelled_by,
    )

    assert isinstance(reversal, BillingLedgerEntry)
    assert reversal.entry_type == "reversal"
    assert reversal.reversal_of_id == original.id
    assert reversal.tariff_version_id == original.tariff_version_id
    assert reversal.quantity == Decimal("-4")
    assert reversal.rate == Decimal("12.50")
    assert reversal.amount == Decimal("-50.00")
    assert reversal.performer_id == cancelled_by
    session.add.assert_called_once_with(reversal)

    session.scalar = AsyncMock(side_effect=[None, reversal])
    repeated = await record_operational_reversal(
        session,
        tenant_id=original.tenant_id,
        source_type=original.source_type,
        source_id=original.source_id,
        occurred_at=datetime(2026, 9, 2, 11, tzinfo=UTC),
        performer_id=uuid.uuid4(),
    )

    assert repeated is reversal
    session.add.assert_called_once_with(reversal)


@pytest.mark.asyncio
async def test_charge_is_created_again_only_after_the_same_fact_is_reversed() -> None:
    session = _savepoint_session()
    entries: list[BillingLedgerEntry] = []
    session.add = Mock(side_effect=entries.append)
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    source_id = uuid.uuid4()
    occurred_at = datetime(2026, 8, 20, 10, tzinfo=UTC)

    session.scalar = AsyncMock(side_effect=[date(2026, 1, 1), None, None, None])
    initial = await record_operational_charge(
        session,
        tenant_id=tenant_id,
        seller_id=seller_id,
        source_type="marketplace_unload",
        source_id=source_id,
        source="marketplace_unload",
        service_code="marketplace_outbound",
        quantity=Decimal("4"),
        occurred_at=occurred_at,
        performer_id=uuid.uuid4(),
    )

    assert initial is not None
    session.scalar = AsyncMock(side_effect=[initial, None])
    reversal = await record_operational_reversal(
        session,
        tenant_id=tenant_id,
        source_type="marketplace_unload",
        source_id=source_id,
        occurred_at=occurred_at,
        performer_id=uuid.uuid4(),
    )

    assert reversal is not None
    session.scalar = AsyncMock(side_effect=[date(2026, 1, 1), None, reversal, None])
    repeated_fact = await record_operational_charge(
        session,
        tenant_id=tenant_id,
        seller_id=seller_id,
        source_type="marketplace_unload",
        source_id=source_id,
        source="marketplace_unload",
        service_code="marketplace_outbound",
        quantity=Decimal("4"),
        occurred_at=occurred_at,
        performer_id=uuid.uuid4(),
    )

    assert repeated_fact is not None
    assert [entry.entry_type for entry in entries] == ["charge", "reversal", "charge"]
    assert [entry.quantity for entry in entries] == [Decimal("4"), Decimal("-4"), Decimal("4")]
    assert initial.event_kind == "completed"
    assert repeated_fact.event_kind == f"completed_after_reversal:{reversal.id}"


@pytest.mark.asyncio
async def test_identical_charge_calls_without_reversal_create_one_ledger_entry() -> None:
    session = _savepoint_session()
    entries: list[BillingLedgerEntry] = []
    session.add = Mock(side_effect=entries.append)
    tenant_id = uuid.uuid4()
    source_id = uuid.uuid4()
    kwargs = {
        "tenant_id": tenant_id,
        "seller_id": uuid.uuid4(),
        "source_type": "inbound_intake",
        "source_id": source_id,
        "source": "inbound",
        "service_code": "inbound",
        "quantity": Decimal("3"),
        "occurred_at": datetime(2026, 8, 20, 10, tzinfo=UTC),
        "performer_id": uuid.uuid4(),
    }

    session.scalar = AsyncMock(side_effect=[date(2026, 1, 1), None, None, None])
    initial = await record_operational_charge(session, **kwargs)

    assert initial is not None
    session.scalar = AsyncMock(side_effect=[date(2026, 1, 1), initial])
    repeated = await record_operational_charge(session, **kwargs)

    assert repeated is initial
    assert entries == [initial]
