"""Подбор ФБС помнит, из какой тары сняли штуку.

Отмена подбора возвращает товар обратно на место — и должна класть его в тот же
короб, а не россыпью на полку. Для этого строка подбора хранит тару источника.

Revision ID: 20260829_0241
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_0241"
down_revision: str | Sequence[str] | None = "20260829_0240"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "fbs_order_picks"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("source_container_kind", sa.String(length=16), nullable=True))
    op.add_column(TABLE, sa.Column("source_container_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_index(f"ix_{TABLE}_source_container_id", TABLE, ["source_container_id"])


def downgrade() -> None:
    op.drop_index(f"ix_{TABLE}_source_container_id", table_name=TABLE)
    op.drop_column(TABLE, "source_container_id")
    op.drop_column(TABLE, "source_container_kind")
