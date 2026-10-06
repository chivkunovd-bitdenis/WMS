"""One-time upgrade contract against pre-WMS-654 storage_locations rows."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app.db.session import engine
from tests.test_wms654_cells import cells, create, listed  # noqa: F401

TASK_MIGRATION_FILENAME = "20261007_2302_wms654_location_tier.py"


def task_owned_tier_migrations(scripts: ScriptDirectory) -> list:
    """Return only the migration that belongs to the WMS-654 C8 contract."""
    return [
        revision
        for revision in reversed(list(scripts.walk_revisions()))
        if Path(revision.path).name == TASK_MIGRATION_FILENAME
    ]


@pytest.mark.asyncio
async def test_c8_migration_preserves_legacy_rows_and_new_list_coordinates(cells):  # noqa: F811
    old = await create(cells, {"rack_name": "А", "side": 2, "position": 4})
    assert old.status_code == 200, old.text
    original = old.json()
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "backend/alembic.ini"))
    config.set_main_option("script_location", str(root / "backend/alembic"))
    scripts = ScriptDirectory.from_config(config)
    new_revisions = task_owned_tier_migrations(scripts)

    def upgrade(connection):
        columns = {
            column["name"] for column in inspect(connection).get_columns("storage_locations")
        }
        # Fixture creates current metadata. Restore old table shape before testing upgrade.
        if "tier" in columns:
            connection.execute(text("ALTER TABLE storage_locations DROP COLUMN tier"))
        before = connection.execute(
            text(
                "SELECT id, tenant_id, warehouse_id, code, barcode, rack_id, side, position "
                "FROM storage_locations ORDER BY code"
            )
        ).all()
        with Operations.context(MigrationContext.configure(connection)):
            for revision in new_revisions:
                revision.module.upgrade()
        after = connection.execute(
            text(
                "SELECT id, tenant_id, warehouse_id, code, barcode, rack_id, side, position "
                "FROM storage_locations ORDER BY code"
            )
        ).all()
        assert after == before, "Upgrade must not rewrite existing cell identities or coordinates"
        columns = {
            column["name"]: column
            for column in inspect(connection).get_columns("storage_locations")
        }
        assert "tier" in columns, "Upgrade left old storage schema without persisted tier"
        assert columns["tier"]["nullable"], "Old rows must have an absent tier, not a forced tier"
        assert connection.execute(text("SELECT tier FROM storage_locations")).scalars().all() == [
            None
        ] * len(before)

    async with engine.begin() as connection:
        await connection.run_sync(upgrade)
    old_list = next(x for x in await listed(cells) if x["id"] == original["id"])
    for key in ("id", "warehouse_id", "code", "barcode"):
        assert old_list[key] == original[key]
    assert old_list["tier"] is None
    new = await create(
        cells,
        {
            "rack_name": "Б",
            "side": None,
            "tier": 3,
            "position": 4,
            "use_sides": False,
            "use_tiers": True,
        },
    )
    assert new.status_code == 200, new.text
    row = next(x for x in await listed(cells) if x["id"] == new.json()["id"])
    assert (row["code"], row["side"], row["tier"], row["position"]) == ("Б 3.4", None, 3, 4)
    client, headers, _ = cells
    resolved = await client.get(
        "/warehouses/resolve", headers=headers, params={"barcode": original["barcode"]}
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["id"] == original["id"]
    assert resolved.json()["code"] == original["code"]
