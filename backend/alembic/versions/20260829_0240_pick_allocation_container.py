"""Подбор помнит, из какой тары сняли товар.

Раньше факт подбора хранился парой «товар + ячейка», и система знала только
«сняли 7 из СТЕЛЛАЖ 1.1». Из какого именно короба — не знала, хотя остаток по
таре в inventory_balances лежит с самого начала.

Миграция добавляет тару в строку подбора и переносит уникальность на связку
вместе с тарой: одно место может дать несколько строк — россыпь и по строке на
каждый короб или палету. NULL приводится к нулевому UUID, потому что в SQL два
NULL не равны и без приведения ограничение перестало бы держать россыпь.

Revision ID: 20260829_0240
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_0240"
down_revision: str | Sequence[str] | None = "20260829_0230"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "marketplace_unload_pick_allocations"
OLD_UNIQUE = "uq_mp_unload_pick_req_product_loc"
NEW_UNIQUE = "uq_mp_unload_pick_req_product_loc_container"
ZERO_UUID = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("container_kind", sa.String(length=16), nullable=True))
    op.add_column(TABLE, sa.Column("container_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_index(f"ix_{TABLE}_container_id", TABLE, ["container_id"])
    op.create_check_constraint(
        "ck_mp_unload_pick_container_pair",
        TABLE,
        "(container_kind IS NULL AND container_id IS NULL) OR "
        "(container_kind IS NOT NULL AND container_id IS NOT NULL)",
    )

    # Старое ограничение держало одну строку на ячейку и не дало бы завести
    # вторую строку под короб. Снимаем его и ставим то же самое, но с тарой.
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint(OLD_UNIQUE, type_="unique")

    op.create_index(
        NEW_UNIQUE,
        TABLE,
        [
            "request_id",
            "product_id",
            "storage_location_id",
            sa.text(f"coalesce(container_id, '{ZERO_UUID}')"),
        ],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(NEW_UNIQUE, table_name=TABLE)
    with op.batch_alter_table(TABLE) as batch:
        batch.create_unique_constraint(
            OLD_UNIQUE,
            ["request_id", "product_id", "storage_location_id"],
        )
    op.drop_constraint("ck_mp_unload_pick_container_pair", TABLE, type_="check")
    op.drop_index(f"ix_{TABLE}_container_id", table_name=TABLE)
    op.drop_column(TABLE, "container_id")
    op.drop_column(TABLE, "container_kind")
