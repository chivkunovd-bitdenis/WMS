# ruff: noqa: RUF002
"""fbs_orders: технический код стикера WB (тот, что читает сканер)

Revision ID: 20260820_0092
Revises: 20260816_0091
Create Date: 2026-08-20

WB отдаёт в стикере два разных значения: человеческий номер partA/partB
(«5694425 3074»), напечатанный цифрами сбоку, и технический ``barcode``
(«*DUIkWJJF»), которым заполнены все QR и штрихкоды этикетки. Хранили только
первый, а сканер выдаёт второй — поэтому скан стикера не находил заказ.
Колонка добавляющая, существующие данные не трогаются.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260820_0092"
down_revision = "20260816_0091"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fbs_orders",
        sa.Column("sticker_barcode", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fbs_orders", "sticker_barcode")
