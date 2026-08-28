from pathlib import Path
from types import ModuleType
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from pytest import MonkeyPatch
from sqlalchemy import CheckConstraint, Column, ForeignKeyConstraint, Integer, UniqueConstraint

from app.models.billing import BillingLedgerEntry, BillingTariffVersion
from app.services.staff_packaging_billing_service import kopecks_to_rub_str


def _script_directory() -> ScriptDirectory:
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    return ScriptDirectory.from_config(config)


def test_billing_financial_core_is_in_the_single_alembic_lineage() -> None:
    script = _script_directory()

    # Проверяем именно единственность линии, а не конкретную голову: смысл теста —
    # что ветка биллинга не отпочковалась, а пришпиленный номер ревизии приходилось
    # бы править каждой новой миграцией.
    assert len(script.get_heads()) == 1

    billing_core = script.get_revision("20260822_09a")
    billing_invoices = script.get_revision("20260822_09b")
    billing_activation = script.get_revision("20260822_09c")
    storage_merge = script.get_revision("20260823_0097")

    assert billing_core.down_revision == "20260823_0095"
    assert billing_invoices.down_revision == billing_core.revision
    assert billing_activation.down_revision == billing_invoices.revision
    assert set(storage_merge.down_revision) == {"20260822_09c", "20260823_0096"}


def test_billing_financial_core_migration_creates_only_shared_billing_tables(
    monkeypatch: MonkeyPatch,
) -> None:
    module: ModuleType = _script_directory().get_revision("20260822_09a").module
    created_tables: dict[str, tuple[Any, ...]] = {}

    monkeypatch.setattr(
        module.op,
        "create_table",
        lambda name, *items, **_kwargs: created_tables.update({name: items}),
    )
    monkeypatch.setattr(module.op, "create_index", lambda *_args, **_kwargs: None)

    module.upgrade()

    assert set(created_tables) == {
        "billing_profiles",
        "billing_tariff_versions",
        "billing_ledger_entries",
    }
    ledger_items = created_tables["billing_ledger_entries"]
    tariff_columns = {
        item.name: item
        for item in created_tables["billing_tariff_versions"]
        if isinstance(item, Column)
    }
    ledger_columns = {item.name: item for item in ledger_items if isinstance(item, Column)}
    assert isinstance(tariff_columns["amount"].type, Integer)
    assert tariff_columns["warehouse_id"].nullable is True
    assert isinstance(ledger_columns["rate"].type, Integer)
    assert isinstance(ledger_columns["amount"].type, Integer)
    assert any(
        isinstance(item, UniqueConstraint) and item.name == "uq_billing_ledger_source_event"
        for item in ledger_items
    )
    tariff_items = created_tables["billing_tariff_versions"]
    assert any(
        isinstance(item, ForeignKeyConstraint)
        and list(item.column_keys) == ["warehouse_id"]
        and item.ondelete == "RESTRICT"
        for item in tariff_items
    )
    assert any(
        isinstance(item, CheckConstraint)
        and item.name == "ck_billing_tariff_warehouse_scope"
        for item in tariff_items
    )
    assert any(
        isinstance(item, ForeignKeyConstraint)
        and item.name is None
        and list(item.column_keys) == ["reversal_of_id"]
        and item.ondelete == "RESTRICT"
        for item in ledger_items
    )


def test_billing_invoice_number_is_unique_inside_tenant_only(monkeypatch: MonkeyPatch) -> None:
    module: ModuleType = _script_directory().get_revision("20260822_09b").module
    created_tables: dict[str, tuple[Any, ...]] = {}

    monkeypatch.setattr(
        module.op,
        "create_table",
        lambda name, *items, **_kwargs: created_tables.update({name: items}),
    )
    monkeypatch.setattr(module.op, "create_index", lambda *_args, **_kwargs: None)

    module.upgrade()

    invoice_items = created_tables["billing_invoices"]
    number_column = next(
        item for item in invoice_items if isinstance(item, Column) and item.name == "number"
    )
    assert number_column.unique is not True
    assert any(
        isinstance(item, UniqueConstraint)
        and item.name == "uq_billing_invoice_tenant_number"
        and list(item._pending_colargs) == ["tenant_id", "number"]
        for item in invoice_items
    )


def test_billing_models_store_money_as_kopecks_and_format_it_as_rubles() -> None:
    assert isinstance(BillingTariffVersion.__table__.c.amount.type, Integer)
    assert isinstance(BillingLedgerEntry.__table__.c.rate.type, Integer)
    assert isinstance(BillingLedgerEntry.__table__.c.amount.type, Integer)
    assert kopecks_to_rub_str(4550) == "45.50"
