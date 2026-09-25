"""WMS-433: таблица переписки AI-помощника

Revision ID: 20260912_0305
Revises: 20260911_0304
Create Date: 2026-09-12

Одна строка — один ход переписки (сообщение пользователя, контекст экрана,
безопасный ответ, отметка захвата очереди исполнителем). Решение аналитика
4.1: хранилище новое и минимальное, состояние запроса не хранится отдельным
полем — оно вычисляется из `answered_at` (есть ли ответ) и `claimed_at`
(захвачен ли исполнителем и не устарел ли захват). Подробности — в докстринге
`app/models/assistant_message.py`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import context, op

revision: str = "20260912_0305"
down_revision: str | Sequence[str] | None = "20260911_0304"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "assistant_messages"


def _validate_existing_table(inspector: sa.Inspector) -> None:
    """Adopt a previously deployed table only after checking its contract."""
    expected = {
        "id": (sa.Uuid, None, False),
        "tenant_id": (sa.Uuid, None, False),
        "user_id": (sa.Uuid, None, False),
        "client_message_id": (sa.String, 128, False),
        "message_text": (sa.Text, None, False),
        "screen_path": (sa.String, 512, False),
        "screen_title": (sa.String, 256, False),
        "screen_text": (sa.Text, None, False),
        "created_at": (sa.DateTime, None, False),
        "claimed_at": (sa.DateTime, None, True),
        "answer_text": (sa.Text, None, True),
        "answered_at": (sa.DateTime, None, True),
        "backlog_number": (sa.String, 16, True),
    }
    columns = {column["name"]: column for column in inspector.get_columns(TABLE)}
    if set(columns) - set(expected) - {"executor_attempts"}:
        raise RuntimeError("WMS-433: incompatible assistant_messages extra columns")
    for name, (kind, length, nullable) in expected.items():
        column = columns.get(name)
        if column is None:
            raise RuntimeError(f"WMS-433: assistant_messages missing column {name}")
        actual = column["type"]
        # SQLite reflects UUID storage as CHAR(32); PostgreSQL reflects UUID.
        uuid_storage = kind is sa.Uuid and inspector.bind.dialect.name == "sqlite"
        type_matches = (
            isinstance(actual, sa.CHAR) and actual.length == 32
            if uuid_storage
            else isinstance(actual, kind)
        )
        if (
            not type_matches
            or column["nullable"] != nullable
            or (length is not None and getattr(actual, "length", None) != length)
        ):
            raise RuntimeError(f"WMS-433: incompatible assistant_messages column {name}")
        if (
            kind is sa.DateTime
            and inspector.bind.dialect.name == "postgresql"
            and not getattr(actual, "timezone", False)
        ):
            raise RuntimeError(f"WMS-433: assistant_messages column {name} needs timezone")
    if inspector.get_pk_constraint(TABLE)["constrained_columns"] != ["id"]:
        raise RuntimeError("WMS-433: incompatible assistant_messages primary key")
    unique_columns = {
        tuple(item["column_names"]) for item in inspector.get_unique_constraints(TABLE)
    }
    indexes = inspector.get_indexes(TABLE)
    if ("user_id", "client_message_id") not in unique_columns:
        raise RuntimeError("WMS-433: assistant_messages missing message uniqueness")
    indexed_columns = {
        tuple(item["column_names"])
        for item in indexes
        if not any(key.endswith("_where") for key in item.get("dialect_options", {}))
    }
    if not {(name,) for name in ("tenant_id", "user_id", "created_at")} <= indexed_columns:
        raise RuntimeError("WMS-433: assistant_messages missing required indexes")
    foreign_keys = inspector.get_foreign_keys(TABLE)
    for column_name, target in (("tenant_id", "tenants"), ("user_id", "users")):
        if not any(
            fk["constrained_columns"] == [column_name]
            and fk["referred_table"] == target
            and fk.get("referred_schema") in (None, inspector.default_schema_name)
            and fk["referred_columns"] == ["id"]
            and (fk.get("options", {}).get("ondelete") or "").upper() == "CASCADE"
            for fk in foreign_keys
        ):
            raise RuntimeError(
                f"WMS-433: incompatible assistant_messages foreign key {column_name}"
            )


def upgrade() -> None:
    if not context.is_offline_mode():
        inspector = sa.inspect(op.get_bind())
        if inspector.has_table(TABLE):
            _validate_existing_table(inspector)
            return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("client_message_id", sa.String(length=128), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("screen_path", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("screen_title", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("screen_text", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("backlog_number", sa.String(length=16), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "client_message_id", name="uq_assistant_messages_user_client_message_id"
        ),
    )
    op.create_index("ix_assistant_messages_tenant_id", TABLE, ["tenant_id"])
    op.create_index("ix_assistant_messages_user_id", TABLE, ["user_id"])
    op.create_index("ix_assistant_messages_created_at", TABLE, ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_assistant_messages_created_at", table_name=TABLE)
    op.drop_index("ix_assistant_messages_user_id", table_name=TABLE)
    op.drop_index("ix_assistant_messages_tenant_id", table_name=TABLE)
    op.drop_table(TABLE)
