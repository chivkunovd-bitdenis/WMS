"""Тара, заведённая прямо в документе пересчёта.

Revision ID: 20260903_0250
Revises: 20260903_0249
Create Date: 2026-09-03

Кнопка «Создать короб» на экране пересчёта создавала тару на складе, но
документ её тут же терял: прунинг (`_prune_empty_containers` в
`app/api/inventory_counts.py`) выбрасывает из дерева всю тару, в которой по
документу ничего не лежит, а свежесозданный короб пуст по определению.
Отключать прунинг целиком нельзя — он заведён из-за реального случая: у
одного арендатора было 420 коробов на складе, а товар по документу лежал
только в 113, и без прунинга документ вырастал на сорок тысяч пикселей.

Эта таблица — точечное исключение для пустой тары, созданной именно в этом
документе: список пар (документ, тара), которые прунинг обязан пропустить,
даже если строк в них ещё нет.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260903_0250"
down_revision: str | Sequence[str] | None = "20260903_0249"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventory_count_created_containers",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "count_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("inventory_counts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("container_kind", sa.String(length=32), nullable=False),
        sa.Column("container_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "count_id",
            "container_kind",
            "container_id",
            name="uq_inventory_count_created_container",
        ),
    )


def downgrade() -> None:
    op.drop_table("inventory_count_created_containers")
