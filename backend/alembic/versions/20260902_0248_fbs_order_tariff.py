"""FBS order assembly as a billable service

Revision ID: 20260902_0248
Revises: 20260902_0247
Create Date: 2026-09-02

Сборка заказов FBS до сих пор не тарифицировалась ничем: склад собирает заказы
Wildberries каждый день, а в расчётах этой работы не было вовсе. Услуга
считается **за штуку товара**, а не за заказ: у Wildberries в заказе всегда одна
штука, поэтому разницы не видно, но у Ozon в заказе может быть несколько
позиций, и ставка «за заказ» там соврала бы.
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260902_0248"
down_revision: str | Sequence[str] | None = "20260902_0247"
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


def _seed_service_state() -> None:
    """Завести строку услуги существующим арендаторам.

    Экран тарифов присылает обратно ровно тот список услуг, который получил, а
    сервер требует полного совпадения с эталонным набором. Без этой строки у
    давнего арендатора перестанет сохраняться матрица целиком — не раздел FBS, а
    любая ставка вообще.
    """
    bind = op.get_bind()
    configs = bind.execute(
        sa.text(
            "SELECT c.id, c.tenant_id FROM billing_tariff_matrix_configs c "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM billing_tariff_service_states s "
            "  WHERE s.tenant_id = c.tenant_id AND s.service_code = 'fbs_order'"
            ")"
        )
    ).fetchall()
    for config_id, tenant_id in configs:
        bind.execute(
            sa.text(
                "INSERT INTO billing_tariff_service_states "
                "(id, config_id, tenant_id, service_code, enabled) "
                "VALUES (:id, :config_id, :tenant_id, 'fbs_order', false)"
            ),
            {"id": str(uuid.uuid4()), "config_id": config_id, "tenant_id": tenant_id},
        )


def upgrade() -> None:
    _rewrite(UNIT_WITH_FBS, SCOPE_WITH_FBS)
    _rewrite_state(STATE_WITH_FBS)
    _seed_service_state()


def downgrade() -> None:
    # Ставки и включения по FBS убираем перед сужением CHECK: иначе откат
    # упадёт на строках, которые новому условию уже не подходят.
    op.execute(sa.text(f"DELETE FROM {TABLE} WHERE service_code = 'fbs_order'"))
    op.execute(sa.text(f"DELETE FROM {STATE_TABLE} WHERE service_code = 'fbs_order'"))
    _rewrite_state(STATE_WITHOUT_FBS)
    _rewrite(UNIT_WITHOUT_FBS, SCOPE_WITHOUT_FBS)
