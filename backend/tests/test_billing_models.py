from sqlalchemy import create_engine, inspect

from app.models import Base
from app.models.billing import BillingLedgerEntry


def test_billing_ff_profile_index_is_partial_on_sqlite() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    indexes = inspect(engine).get_indexes("billing_profiles")
    ff_index = next(index for index in indexes if index["name"] == "uq_billing_profiles_tenant_ff")

    assert ff_index["unique"] == 1
    assert "seller_id IS NULL" in str(ff_index["dialect_options"].get("sqlite_where"))
    assert "billing_invoices" not in inspect(engine).get_table_names()
    assert "billing_run_issues" not in inspect(engine).get_table_names()


def test_billing_unique_indexes_separate_common_and_seller_tariffs_and_reversals() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    indexes = {
        index["name"]: index for index in inspect(engine).get_indexes("billing_tariff_versions")
    }
    assert indexes["uq_billing_tariff_version_common"]["unique"] == 1
    assert "warehouse_id" in indexes["uq_billing_tariff_version_common"]["column_names"]
    assert "seller_id IS NULL" in str(
        indexes["uq_billing_tariff_version_common"]["dialect_options"].get("sqlite_where")
    )
    assert "warehouse_id IS NOT NULL" in str(
        indexes["uq_billing_tariff_version_common"]["dialect_options"].get("sqlite_where")
    )
    assert indexes["uq_billing_tariff_version_seller"]["unique"] == 1
    assert "warehouse_id" in indexes["uq_billing_tariff_version_seller"]["column_names"]
    assert "seller_id IS NOT NULL" in str(
        indexes["uq_billing_tariff_version_seller"]["dialect_options"].get("sqlite_where")
    )
    assert indexes["uq_billing_tariff_version_global_common"]["unique"] == 1
    assert indexes["uq_billing_tariff_version_global_seller"]["unique"] == 1

    rate_type = BillingLedgerEntry.__table__.c.rate.type
    assert rate_type.scale == 12

    ledger_indexes = {
        index["name"]: index for index in inspect(engine).get_indexes("billing_ledger_entries")
    }
    assert ledger_indexes["uq_billing_ledger_reversal_of"]["unique"] == 1
    assert "reversal_of_id IS NOT NULL" in str(
        ledger_indexes["uq_billing_ledger_reversal_of"]["dialect_options"].get("sqlite_where")
    )
