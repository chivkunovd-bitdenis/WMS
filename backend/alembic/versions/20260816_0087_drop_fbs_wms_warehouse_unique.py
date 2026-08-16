"""Drop one-WMS-warehouse-per-seller unique constraint on FBS bindings.

One physical WMS warehouse now feeds every WB warehouse address for a
seller (pool 1, item 5 of docs/agent-orders/HANDOFF-POLISH.md) — the
former uniqueness on (seller_id, wms_warehouse_id) blocked live-order
binding on staging (PUT .../warehouse-bindings/1155120 -> 409
wms_warehouse_already_bound).

Revision ID: 20260816_0087
Revises: 20260815_0086
Create Date: 2026-08-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260816_0087"
down_revision: str | Sequence[str] | None = "20260815_0086"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_fbs_warehouse_bindings_seller_wms_warehouse",
        "fbs_warehouse_bindings",
        type_="unique",
    )


def downgrade() -> None:
    # Откат односторонний по своей природе: ограничение снимали ровно затем, чтобы один
    # склад WMS кормил несколько складов WB. Как только такие привязки появились,
    # create_unique_constraint упадёт невнятной ошибкой БД посреди отката. Проверяем
    # заранее и объясняем человеческим языком, что именно мешает и что с этим делать.
    duplicates = (
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT seller_id, wms_warehouse_id, count(*) AS bindings
                FROM fbs_warehouse_bindings
                GROUP BY seller_id, wms_warehouse_id
                HAVING count(*) > 1
                """
            )
        )
        .fetchall()
    )
    if duplicates:
        details = "; ".join(
            f"селлер {row.seller_id}, склад WMS {row.wms_warehouse_id} — {row.bindings} привязок"
            for row in duplicates
        )
        raise RuntimeError(
            "Откат миграции 20260816_0087 невозможен: есть склады WMS, привязанные "
            f"к нескольким складам WB ({details}). Уникальность "
            "(seller_id, wms_warehouse_id) вернуть нельзя, пока эти привязки существуют. "
            "Удалите лишние привязки вручную и повторите откат."
        )
    op.create_unique_constraint(
        "uq_fbs_warehouse_bindings_seller_wms_warehouse",
        "fbs_warehouse_bindings",
        ["seller_id", "wms_warehouse_id"],
    )
