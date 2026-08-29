"""Привязать созданную в раскладке тару к документу приёмки.

Revision ID: 20260830_0242
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260830_0242"
down_revision: str | Sequence[str] | None = "20260829_0241"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("pallets", "warehouse_boxes"):
        op.add_column(
            table,
            sa.Column(
                "inbound_request_id",
                sa.Uuid(as_uuid=True),
                sa.ForeignKey("inbound_intake_requests.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.create_index(
            f"ix_{table}_inbound_request_id",
            table,
            ["inbound_request_id"],
        )


def downgrade() -> None:
    # Задание запрещает разрушительные миграции: добавленные связи сохраняем.
    pass
