from __future__ import annotations

from pathlib import Path

from app.models.inventory_movement import InventoryMovement


def test_inventory_movement_has_immutable_reporting_dimensions() -> None:
    columns = InventoryMovement.__table__.c

    assert columns.seller_id.nullable is True
    assert columns.warehouse_id.nullable is False
    assert columns.reporting_dimensions_legacy.nullable is False
    assert columns.reporting_dimensions_legacy.server_default is not None


def test_reporting_dimensions_migration_backfills_and_indexes() -> None:
    migration = (
        Path(__file__).parents[1]
        / "alembic/versions/20260822_0094_inventory_movement_reporting_dimensions.py"
    )
    source = migration.read_text()

    assert "product.seller_id" in source
    assert "location.warehouse_id" in source
    assert "reporting_dimensions_legacy = product.seller_id IS NULL" in source
    assert "ix_inventory_movements_tenant_created_at" in source
    assert "ix_inventory_movements_tenant_seller_created_at" in source
    assert "ix_inventory_movements_tenant_warehouse_created_at" in source
    assert 'op.alter_column("inventory_movements", "warehouse_id", nullable=False)' in source
