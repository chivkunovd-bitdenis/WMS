"""Call 74 migration contract: additive table, reversible, WB untouched."""

from __future__ import annotations

import importlib.util
from pathlib import Path

# Номер сменился при сведении веток: 20260825_0101 занимали сразу две ревизии —
# уникальный артикул продавца (он на бою) и счета маркетплейсов из линии Ozon.
# На бою остался исходный номер, линия Ozon переехала на 20260825_0111, иначе
# накатка на боевую базу встала бы на неоднозначной ревизии.
REVISION_PATH = (
    Path(__file__).parents[1] / "alembic/versions/20260825_0111_marketplace_accounts.py"
)


def _migration() -> object:
    spec = importlib.util.spec_from_file_location("marketplace_accounts_0101", REVISION_PATH)
    assert spec is not None and spec.loader is not None, "Call 74 migration is required"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tc_s32_ozon_013_revision_is_additive_and_has_the_required_parent() -> None:
    migration = _migration()
    assert migration.revision == "20260825_0111"
    assert migration.down_revision == "20260823_0100"


def test_tc_s32_ozon_013_migration_contains_no_wb_backfill_or_provider_code() -> None:
    source = REVISION_PATH.read_text(encoding="utf-8").lower()
    assert "marketplace_accounts" in source
    # ``secret_encrypted`` is the required storage column; prohibit operational
    # crypto/network calls, not that schema name.
    for forbidden in ("seller_wildberries_credentials", "decrypt(", "encrypt(", "http", "requests"):
        assert forbidden not in source


def test_tc_s32_ozon_013_upgrade_and_downgrade_are_limited_to_new_account_table() -> None:
    migration = _migration()
    calls: list[tuple[str, str]] = []

    class OpSpy:
        def create_table(self, name: str, *_args: object, **_kwargs: object) -> None:
            calls.append(("create_table", name))

        def create_index(self, name: str, table: str, *_args: object, **_kwargs: object) -> None:
            calls.append(("create_index", f"{table}:{name}"))

        def drop_index(self, name: str, *, table_name: str) -> None:
            calls.append(("drop_index", f"{table_name}:{name}"))

        def drop_table(self, name: str) -> None:
            calls.append(("drop_table", name))

    migration.op = OpSpy()
    migration.upgrade()
    migration.downgrade()
    assert calls[0] == ("create_table", "marketplace_accounts")
    assert all("wildberries" not in value for _, value in calls)
    assert calls[-1] == ("drop_table", "marketplace_accounts")
