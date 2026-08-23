import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import Boolean, Date, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.models.billing import BillingInvoice, BillingLedgerEntry, BillingProfile
from app.services import billing_invoice_service
from app.services.billing_invoice_service import _storage_source_ids, form_invoice


def _result(values: list[object]) -> Mock:
    return Mock(all=Mock(return_value=values))


def _savepoint_session() -> AsyncMock:
    session = AsyncMock()
    session.add = Mock()
    session.begin_nested = AsyncMock(return_value=AsyncMock())
    return session


@pytest.mark.asyncio
async def test_form_invoice_blocks_unpriced_with_one_current_issue() -> None:
    session = _savepoint_session()
    seller_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    entry = BillingLedgerEntry(
        tenant_id=tenant_id,
        seller_id=seller_id,
        source_type="inbound_intake",
        source_id=uuid.uuid4(),
        service_code="inbound",
        unit="document",
        quantity=Decimal("1"),
        amount=None,
        occurred_at=datetime(2026, 7, 5, tzinfo=UTC),
    )
    ff_profile = BillingProfile(tenant_id=tenant_id, seller_id=None, legal_name="FF", inn="123")
    seller_profile = BillingProfile(
        tenant_id=tenant_id,
        seller_id=seller_id,
        legal_name="Seller",
        inn="456",
    )
    session.scalar = AsyncMock(
        side_effect=[object(), None, None, ff_profile, seller_profile, None]
    )
    session.scalars = AsyncMock(return_value=_result([entry]))

    result = await form_invoice(
        session,
        tenant_id=tenant_id,
        seller_id=seller_id,
        period=date(2026, 7, 1),
    )

    assert result.reason == "unpriced"
    assert session.add.call_count == 1
    assert session.add.call_args.args[0] is result


@pytest.mark.asyncio
async def test_empty_month_is_not_persisted_as_blocking_issue() -> None:
    session = _savepoint_session()
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    session.scalar = AsyncMock(side_effect=[object(), None, None])
    session.scalars = AsyncMock(return_value=_result([]))

    result = await form_invoice(
        session,
        tenant_id=tenant_id,
        seller_id=seller_id,
        period=date(2026, 7, 1),
    )

    assert result is None
    session.execute.assert_awaited_once()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_existing_invoice_clears_stale_issues_without_duplicate() -> None:
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
    session.scalar = AsyncMock(side_effect=[object(), invoice])

    result = await form_invoice(
        session,
        tenant_id=invoice.tenant_id,
        seller_id=invoice.seller_id,
        period=invoice.period,
    )

    assert result is invoice
    session.execute.assert_awaited_once()
    session.add.assert_not_called()


class _StorageBase(DeclarativeBase):
    pass


class _Warehouse(_StorageBase):
    __tablename__ = "test_invoice_warehouses"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    is_operational: Mapped[bool] = mapped_column(Boolean)


class _Statement(_StorageBase):
    __tablename__ = "test_invoice_statements"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    seller_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String)


class _Measurement(_StorageBase):
    __tablename__ = "test_invoice_measurements"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    seller_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)


@pytest.mark.asyncio
async def test_storage_barrier_requires_fixed_published_statement_for_both_warehouses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S-31-TC-013: one fixed warehouse never unlocks a two-warehouse invoice."""
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    warehouse_a = uuid.uuid4()
    warehouse_b = uuid.uuid4()
    statement_a = SimpleNamespace(id=uuid.uuid4(), warehouse_id=warehouse_a)
    measurement_a = uuid.uuid4()
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=uuid.uuid4())
    session.scalars = AsyncMock(
        side_effect=[
            _result([warehouse_a, warehouse_b]),
            _result([statement_a]),
        ]
    )

    modules = {
        "app.models.storage_statement": SimpleNamespace(StorageStatement=_Statement),
        "app.models.storage_measurement": SimpleNamespace(StorageMeasurement=_Measurement),
        "app.models.warehouse": SimpleNamespace(Warehouse=_Warehouse),
    }
    monkeypatch.setattr(
        billing_invoice_service.importlib,
        "import_module",
        lambda name: modules[name],
    )

    ready, source_ids = await _storage_source_ids(
        session,
        tenant_id=tenant_id,
        seller_id=seller_id,
        period=date(2026, 7, 1),
    )

    assert ready is False
    assert source_ids == set()
    assert measurement_a not in source_ids


@pytest.mark.asyncio
async def test_storage_barrier_accepts_zero_and_measured_published_statements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S-31-TC-006: every operational warehouse contributes an auditable source."""
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    warehouse_a = uuid.uuid4()
    warehouse_b = uuid.uuid4()
    statement_a = SimpleNamespace(id=uuid.uuid4(), warehouse_id=warehouse_a)
    statement_b = SimpleNamespace(id=uuid.uuid4(), warehouse_id=warehouse_b)
    measurement_a = uuid.uuid4()
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=uuid.uuid4())
    session.scalars = AsyncMock(
        side_effect=[
            _result([warehouse_a, warehouse_b]),
            _result([statement_a, statement_b]),
            _result([measurement_a]),
            _result([]),
            _result([measurement_a, statement_b.id]),
        ]
    )
    modules = {
        "app.models.storage_statement": SimpleNamespace(StorageStatement=_Statement),
        "app.models.storage_measurement": SimpleNamespace(StorageMeasurement=_Measurement),
        "app.models.warehouse": SimpleNamespace(Warehouse=_Warehouse),
    }
    monkeypatch.setattr(
        billing_invoice_service.importlib,
        "import_module",
        lambda name: modules[name],
    )

    ready, source_ids = await _storage_source_ids(
        session,
        tenant_id=tenant_id,
        seller_id=seller_id,
        period=date(2026, 7, 1),
    )

    assert ready is True
    assert source_ids == {measurement_a, statement_b.id}
