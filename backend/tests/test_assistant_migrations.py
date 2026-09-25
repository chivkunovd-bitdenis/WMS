"""WMS-433: reconcile a previously deployed assistant without losing messages."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration(filename):
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = _migration("20260912_0305_assistant_messages.py")
ATTEMPTS = _migration("20260913_2200_assistant_executor_attempts.py")


def _upgrade(connection, migration):
    with (
        Operations.context(MigrationContext.configure(connection)),
        patch.object(migration.context, "is_offline_mode", return_value=False),
    ):
        migration.upgrade()


@pytest.fixture
def connection():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE tenants (id CHAR(32) PRIMARY KEY)")
        conn.exec_driver_sql("CREATE TABLE users (id CHAR(32) PRIMARY KEY)")
        yield conn
    engine.dispose()


def _insert_message(connection):
    connection.exec_driver_sql(
        "INSERT INTO assistant_messages "
        "(id, tenant_id, user_id, client_message_id, message_text) "
        "VALUES ('message', 'tenant', 'user', 'client', 'Keep this message')"
    )


def test_clean_schema_and_existing_message_upgrade(connection):
    _upgrade(connection, BASE)
    _insert_message(connection)
    _upgrade(connection, ATTEMPTS)
    row = connection.exec_driver_sql(
        "SELECT message_text, executor_attempts FROM assistant_messages"
    ).one()
    assert row == ("Keep this message", 0)
    assert sa.inspect(connection).get_columns("assistant_messages")[-1]["default"] is None


def test_existing_complete_schema_is_adopted_without_changing_data(connection):
    _upgrade(connection, BASE)
    _insert_message(connection)
    _upgrade(connection, ATTEMPTS)
    connection.exec_driver_sql("UPDATE assistant_messages SET executor_attempts = 7")
    before = connection.exec_driver_sql("SELECT * FROM assistant_messages").all()
    _upgrade(connection, BASE)
    _upgrade(connection, ATTEMPTS)
    assert connection.exec_driver_sql("SELECT * FROM assistant_messages").all() == before


@pytest.mark.parametrize("defect", ["index", "column", "type", "unique", "foreign_key"])
def test_incompatible_existing_table_fails_without_changing_message(connection, defect):
    _upgrade(connection, BASE)
    _insert_message(connection)
    if defect == "index":
        connection.exec_driver_sql("DROP INDEX ix_assistant_messages_tenant_id")
    elif defect == "column":
        connection.exec_driver_sql(
            "ALTER TABLE assistant_messages RENAME COLUMN answer_text TO wrong"
        )
    else:
        with (
            Operations.context(MigrationContext.configure(connection)),
            Operations(MigrationContext.configure(connection)).batch_alter_table(
                "assistant_messages",
                naming_convention={
                    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
                },
            ) as batch,
        ):
            if defect == "type":
                batch.alter_column("message_text", type_=sa.Integer())
            elif defect == "unique":
                batch.drop_constraint(
                    "uq_assistant_messages_user_client_message_id", type_="unique"
                )
            else:
                batch.drop_constraint("fk_assistant_messages_user_id_users", type_="foreignkey")
    before = connection.exec_driver_sql("SELECT * FROM assistant_messages").all()
    with pytest.raises(RuntimeError, match="WMS-433"):
        _upgrade(connection, BASE)
    assert connection.exec_driver_sql("SELECT * FROM assistant_messages").all() == before


@pytest.mark.parametrize("column_type", ["TEXT NOT NULL DEFAULT 'zero'", "INTEGER"])
def test_incompatible_existing_attempts_fails_without_changing_message(connection, column_type):
    _upgrade(connection, BASE)
    _insert_message(connection)
    connection.exec_driver_sql(
        f"ALTER TABLE assistant_messages ADD COLUMN executor_attempts {column_type}"
    )
    before = connection.exec_driver_sql("SELECT * FROM assistant_messages").all()
    with pytest.raises(RuntimeError, match="executor_attempts"):
        _upgrade(connection, ATTEMPTS)
    assert connection.exec_driver_sql("SELECT * FROM assistant_messages").all() == before
