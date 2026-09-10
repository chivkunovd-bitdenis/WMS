"""WMS-423: tenant_wb_mp_warehouses.wb_warehouse_id -> bigint

Справочник хранит склады Wildberries, и его `wb_warehouse_id` был объявлен как
int4. Но искать в нём приходится по полю заказа, а у заказа Ozon там лежит номер
озоновского склада — например 1020005029603630, который в int4 не помещается.
Postgres отвечал `integer out of range`, и падал не только справочник: 500
получали список заказов FBS и проверка новой поставки, каждый раз в новом месте.

Расширяем тип до bigint. Логика не меняется: озоновского склада в
вайлдберрисовском справочнике нет и быть не может, поэтому запрос теперь просто
ничего не находит — как и должен был с самого начала.

Revision ID: 20260910_1500
Revises: 20260908_0257
Create Date: 2026-09-10 15:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260910_1500"
down_revision: str | Sequence[str] | None = "20260908_0257"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "tenant_wb_mp_warehouses",
        "wb_warehouse_id",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "tenant_wb_mp_warehouses",
        "wb_warehouse_id",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
    )
