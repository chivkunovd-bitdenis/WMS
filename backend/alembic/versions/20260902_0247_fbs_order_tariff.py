"""FBS order assembly as a billable service

Revision ID: 20260902_0247
Revises: 20260901_0246
Create Date: 2026-09-02

Сборка заказов FBS до сих пор не тарифицировалась ничем: склад собирает заказы
Wildberries каждый день, а в расчётах этой работы не было вовсе. Услуга
считается **за штуку товара**, а не за заказ: у Wildberries в заказе всегда одна
штука, поэтому разницы не видно, но у Ozon в заказе может быть несколько
позиций, и ставка «за заказ» там соврала бы.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260902_0247"
down_revision: str | Sequence[str] | None = "20260901_0246"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "billing_tariff_versions_v2"
STATE_TABLE = "billing_tariff_service_states"

UNIT_WITH_FBS = (
    "(service_code = 'storage' AND unit = 'liter_day')"
    " OR (service_code = 'fbs_order' AND unit = 'item')"
    " OR (service_code NOT IN ('storage', 'fbs_order') AND unit IN ('document', 'item'))"
)
UNIT_WITHOUT_FBS = (
    "(service_code = 'storage' AND unit = 'liter_day')"
    " OR (service_code <> 'storage' AND unit IN ('document', 'item'))"
)

SCOPE_TEMPLATE = (
    "("
    "employee_user_id IS NOT NULL "
    "AND seller_id IS NULL "
    "AND product_id IS NULL "
    "AND unit = 'item' "
    "AND service_code IN ('inbound', 'picking', 'marketplace_outbound', 'return')"
    ") OR ("
    "employee_user_id IS NULL "
    "AND service_code IN ({services}) "
    "AND (product_id IS NULL OR (seller_id IS NOT NULL AND unit = 'item'))"
    ")"
)
SCOPE_WITH_FBS = SCOPE_TEMPLATE.format(
    services="'inbound', 'marketplace_outbound', 'packing', 'return', 'storage', 'fbs_order'"
)
SCOPE_WITHOUT_FBS = SCOPE_TEMPLATE.format(
    services="'inbound', 'marketplace_outbound', 'packing', 'return', 'storage'"
)

STATE_WITH_FBS = (
    "service_code IN "
    "('inbound', 'marketplace_outbound', 'packing', 'return', 'storage', 'fbs_order')"
)
STATE_WITHOUT_FBS = (
    "service_code IN ('inbound', 'marketplace_outbound', 'packing', 'return', 'storage')"
)


def _rewrite_state(condition: str) -> None:
    # Включение услуги живёт в отдельной таблице со своим списком допустимых
    # кодов: без неё FBS нельзя даже включить в матрице тарифов.
    with op.batch_alter_table(STATE_TABLE) as batch_op:
        batch_op.drop_constraint("ck_billing_tariff_service_state_code", type_="check")
        batch_op.create_check_constraint("ck_billing_tariff_service_state_code", sa.text(condition))


def _rewrite(unit_condition: str, scope_condition: str) -> None:
    # SQLite не умеет менять CHECK на месте, поэтому таблица пересоздаётся
    # батчем — тем же способом, что и в миграции про хранение.
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.drop_constraint("ck_billing_tariff_v2_unit", type_="check")
        batch_op.drop_constraint("ck_billing_tariff_v2_scope", type_="check")
        batch_op.create_check_constraint("ck_billing_tariff_v2_unit", sa.text(unit_condition))
        batch_op.create_check_constraint("ck_billing_tariff_v2_scope", sa.text(scope_condition))


def upgrade() -> None:
    _rewrite(UNIT_WITH_FBS, SCOPE_WITH_FBS)
    _rewrite_state(STATE_WITH_FBS)


def downgrade() -> None:
    # Ставки и включения по FBS убираем перед сужением CHECK: иначе откат
    # упадёт на строках, которые новому условию уже не подходят.
    op.execute(sa.text(f"DELETE FROM {TABLE} WHERE service_code = 'fbs_order'"))
    op.execute(sa.text(f"DELETE FROM {STATE_TABLE} WHERE service_code = 'fbs_order'"))
    _rewrite_state(STATE_WITHOUT_FBS)
    _rewrite(UNIT_WITHOUT_FBS, SCOPE_WITHOUT_FBS)
