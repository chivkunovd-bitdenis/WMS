"""WMS-433: счётчик попыток захвата исполнителем

Revision ID: 20260913_2200
Revises: 20260912_0305
Create Date: 2026-09-13

Ревью Astra круг 7 (дефект №40): возраст сообщения (created_at) — плохая
замена счётчику попыток, сообщение, 40 минут ждавшее выключенного
исполнителя, выглядело «старым» уже на первой реальной попытке. Настоящий
счётчик растёт на каждый захват той же условной записью, что и claimed_at
(см. claim_next_for_executor в app/services/assistant_service.py) — это не
второй источник состояния «ожидает ли сообщение ответа» (им остаётся только
answer_text IS NULL, решение аналитика 4.1), а техническая защита от
бесконечного повтора одного и того же провала (R10/R22). Подробности — в
докстринге поля в app/models/assistant_message.py.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260913_2200"
down_revision: str | Sequence[str] | None = "20260912_0305"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "assistant_messages"
COLUMN = "executor_attempts"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(COLUMN, sa.Integer(), nullable=False, server_default="0"),
    )
    # Серверный default нужен только существующим строкам при миграции; ORM
    # пишет явный 0 при вставке новой строки — держим схему честной о том,
    # кто на самом деле задаёт значение (тот же приём, что и в 20260910_0100).
    op.alter_column(TABLE, COLUMN, server_default=None)


def downgrade() -> None:
    op.drop_column(TABLE, COLUMN)
