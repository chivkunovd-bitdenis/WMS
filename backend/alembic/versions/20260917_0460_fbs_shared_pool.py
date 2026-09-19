"""WMS-455: «общая корзинка» — товар на двух площадках отдаёт весь свободный
остаток сразу в оба кабинета, без долей и без потолка 100%.

Одна булева колонка ``products.fbs_shared_pool`` (NOT NULL, default false).
Существующие товары после выкладки остаются на прежних долях: колонка не
меняет ``validate_rule``/``split_amounts``/``published_now`` для тех, у кого
она false.

Revision ID: 20260917_0460
Revises: 20260913_0306
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260917_0460"
down_revision: str | Sequence[str] | None = "20260913_0306"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "fbs_shared_pool",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("products", "fbs_shared_pool")
