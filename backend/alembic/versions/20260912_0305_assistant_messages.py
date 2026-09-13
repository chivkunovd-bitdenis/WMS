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

from alembic import op

revision: str = "20260912_0305"
down_revision: str | Sequence[str] | None = "20260911_0304"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "assistant_messages"


def upgrade() -> None:
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
