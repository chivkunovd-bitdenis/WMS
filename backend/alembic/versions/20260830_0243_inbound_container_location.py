"""Хранить ячейку пустой приёмочной тары.

Revision ID: 20260830_0243
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260830_0243"
down_revision: str | Sequence[str] | None = "20260830_0242"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("inbound_intake_boxes", "inbound_intake_cargo_places"):
        op.add_column(
            table,
            sa.Column(
                "storage_location_id",
                sa.Uuid(as_uuid=True),
                sa.ForeignKey("storage_locations.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.create_index(
            f"ix_{table}_storage_location_id",
            table,
            ["storage_location_id"],
        )


def downgrade() -> None:
    # Задание запрещает разрушительные миграции: добавленные связи сохраняем.
    pass
