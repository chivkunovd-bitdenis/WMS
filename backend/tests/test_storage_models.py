from sqlalchemy import UniqueConstraint

from app.models.storage_measurement import StorageMeasurement
from app.models.storage_statement import StorageStatement


def _constraint(table, name: str):
    return next(item for item in table.constraints if item.name == name)


def test_statement_is_unique_for_tenant_seller_warehouse_and_month() -> None:
    constraint = _constraint(
        StorageStatement.__table__,
        "uq_storage_statements_tenant_seller_warehouse_period",
    )
    assert isinstance(constraint, UniqueConstraint)
    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "seller_id",
        "warehouse_id",
        "period_start",
    ]


def test_storage_rows_reject_negative_accumulated_values() -> None:
    assert (
        _constraint(
            StorageMeasurement.__table__,
            "ck_storage_measurements_quantity_days_nonnegative",
        ).sqltext.text
        == "quantity_days >= 0"
    )
    assert (
        _constraint(
            StorageMeasurement.__table__,
            "ck_storage_measurements_liter_days_nonnegative",
        ).sqltext.text
        == "liter_days >= 0"
    )


def test_measurement_keeps_immutable_movement_boundary_references() -> None:
    foreign_keys = {
        constraint.target_fullname
        for column in (
            StorageMeasurement.__table__.c.movement_start_id,
            StorageMeasurement.__table__.c.movement_end_id,
        )
        for constraint in column.foreign_keys
    }

    assert foreign_keys == {
        "inventory_movements.id",
    }


def test_storage_models_have_no_financial_columns() -> None:
    assert not {
        "tariff_id",
        "rate",
        "amount",
        "currency",
        "ledger_entry_id",
    }.intersection(StorageStatement.__table__.columns.keys())
