import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Base, BillingLedgerEntry


def test_billing_ff_profile_index_is_partial_on_sqlite() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    indexes = inspect(engine).get_indexes("billing_profiles")
    ff_index = next(index for index in indexes if index["name"] == "uq_billing_profiles_tenant_ff")

    assert ff_index["unique"] == 1
    assert "seller_id IS NULL" in str(ff_index["dialect_options"].get("sqlite_where"))


def test_billing_unique_indexes_separate_common_and_seller_tariffs_and_reversals() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    indexes = {
        index["name"]: index for index in inspect(engine).get_indexes("billing_tariff_versions")
    }
    assert indexes["uq_billing_tariff_version_common"]["unique"] == 1
    assert "seller_id IS NULL" in str(
        indexes["uq_billing_tariff_version_common"]["dialect_options"].get("sqlite_where")
    )
    assert indexes["uq_billing_tariff_version_seller"]["unique"] == 1
    assert "seller_id IS NOT NULL" in str(
        indexes["uq_billing_tariff_version_seller"]["dialect_options"].get("sqlite_where")
    )

    ledger_indexes = {
        index["name"]: index for index in inspect(engine).get_indexes("billing_ledger_entries")
    }
    assert ledger_indexes["uq_billing_ledger_reversal_of"]["unique"] == 1
    assert "reversal_of_id IS NOT NULL" in str(
        ledger_indexes["uq_billing_ledger_reversal_of"]["dialect_options"].get("sqlite_where")
    )


def test_billing_ledger_rejects_duplicate_source_event_and_second_reversal() -> None:
    """The database, rather than only service code, preserves immutable ledger identity."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    tenant_id = uuid.uuid4()
    source_id = uuid.uuid4()

    def entry(**overrides: object) -> BillingLedgerEntry:
        values: dict[str, object] = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "seller_id": None,
            "tariff_version_id": None,
            "reversal_of_id": None,
            "performer_id": None,
            "entry_type": "charge",
            "service_code": "storage_liter_day",
            "source": "storage_measurement",
            "source_type": "storage_measurement",
            "source_id": source_id,
            "unit": "liter_day",
            "quantity": Decimal("1.0000"),
            "rate": Decimal("10.00"),
            "amount": Decimal("10.00"),
            "occurred_at": datetime(2026, 8, 1, tzinfo=UTC),
        }
        values.update(overrides)
        return BillingLedgerEntry(**values)  # type: ignore[arg-type]

    with Session(engine) as session:
        original = entry()
        session.add(original)
        session.commit()

        session.add(entry())
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        reversal = entry(
            entry_type="reversal",
            source_type="billing_reversal",
            source_id=uuid.uuid4(),
            reversal_of_id=original.id,
            quantity=Decimal("-1.0000"),
            amount=Decimal("-10.00"),
        )
        session.add(reversal)
        session.commit()
        session.refresh(original)

        assert original.entry_type == "charge"
        assert original.quantity == Decimal("1.0000")
        assert original.amount == Decimal("10.00")

        session.add(
            entry(
                entry_type="reversal",
                source_type="billing_reversal",
                source_id=uuid.uuid4(),
                reversal_of_id=original.id,
                quantity=Decimal("-1.0000"),
                amount=Decimal("-10.00"),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
