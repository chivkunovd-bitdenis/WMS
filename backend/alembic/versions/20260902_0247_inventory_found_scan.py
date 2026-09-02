"""Idempotency for inventory "found" scans.

Кладовщик сканирует по вайфаю, который на складе рвётся. Ответ не доехал —
экран показал ошибку, а сервер уже записал штуку. Человек сканирует ещё раз, и
на сервере становится две. Излишек на ровном месте, и найти его потом нечем.

Клиент присылает идентификатор скана, сервер его запоминает и на повтор
отвечает тем же результатом, ничего не прибавляя.

Revision ID: 20260902_0247
Revises: 20260901_0246
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260902_0247"
down_revision: str | Sequence[str] | None = "20260901_0246"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventory_count_found_scans",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "count_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("inventory_counts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "line_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("inventory_count_lines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scan_id", sa.String(length=64), nullable=False),
        sa.Column("expected_quantity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("count_id", "scan_id", name="uq_inventory_found_scan"),
    )


def downgrade() -> None:
    op.drop_table("inventory_count_found_scans")
