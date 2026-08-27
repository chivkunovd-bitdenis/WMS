"""allow the storage service inside the tariff matrix

Revision ID: 20260827_0115
Revises: 20260827_0114

Хранение переезжает в общую матрицу тарифов: держать его на отдельном экране
означало единственную услугу с другим местом настройки, и владелец на живом
разборе прямо попросил задавать все тарифы в одном месте.

Миграция только расширяет ограничения. Старые тарифы хранения живут в таблице
`billing_tariff_versions` с привязкой к складу и НЕ переносятся: перенос
меняет предмет расчёта и остаётся отдельным решением владельца.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260827_0115"
down_revision = "20260827_0114"
branch_labels = None
depends_on = None

TABLE = "billing_tariff_versions_v2"

# Хранение считается за литро-день. Это факт предметной области, а не
# оформление: подогнать его под «за штуку» значило бы соврать в расчёте.
UNIT_WITH_STORAGE = (
    "(service_code = 'storage' AND unit = 'liter_day')"
    " OR (service_code <> 'storage' AND unit IN ('document', 'item'))"
)
UNIT_WITHOUT_STORAGE = "unit IN ('document', 'item')"

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
SCOPE_WITH_STORAGE = SCOPE_TEMPLATE.format(
    services="'inbound', 'marketplace_outbound', 'packing', 'return', 'storage'"
)
SCOPE_WITHOUT_STORAGE = SCOPE_TEMPLATE.format(
    services="'inbound', 'marketplace_outbound', 'packing', 'return'"
)


STATE_TABLE = "billing_tariff_service_states"
STATE_WITH_STORAGE = (
    "service_code IN ('inbound', 'marketplace_outbound', 'packing', 'return', 'storage')"
)
STATE_WITHOUT_STORAGE = "service_code IN ('inbound', 'marketplace_outbound', 'packing', 'return')"


def _rewrite_state(condition: str) -> None:
    # Включение и выключение услуги живёт в отдельной таблице со своим списком
    # допустимых кодов: без неё хранение нельзя даже включить в матрице.
    with op.batch_alter_table(STATE_TABLE) as batch_op:
        batch_op.drop_constraint("ck_billing_tariff_service_state_code", type_="check")
        batch_op.create_check_constraint("ck_billing_tariff_service_state_code", sa.text(condition))


def _rewrite(unit_condition: str, scope_condition: str) -> None:
    # SQLite не умеет менять CHECK на месте, поэтому таблица пересоздаётся
    # батчем — тем же способом, что и в остальных миграциях проекта.
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.drop_constraint("ck_billing_tariff_v2_unit", type_="check")
        batch_op.drop_constraint("ck_billing_tariff_v2_scope", type_="check")
        batch_op.create_check_constraint("ck_billing_tariff_v2_unit", sa.text(unit_condition))
        batch_op.create_check_constraint("ck_billing_tariff_v2_scope", sa.text(scope_condition))


def upgrade() -> None:
    _rewrite_state(STATE_WITH_STORAGE)
    _rewrite(UNIT_WITH_STORAGE, SCOPE_WITH_STORAGE)


def downgrade() -> None:
    # Возврат сужает ограничения, поэтому сначала снимаем строки хранения:
    # иначе таблица не пройдёт собственный CHECK. Ставки других услуг остаются.
    op.execute(sa.text(f"DELETE FROM {TABLE} WHERE service_code = 'storage'"))
    op.execute(sa.text(f"DELETE FROM {STATE_TABLE} WHERE service_code = 'storage'"))
    _rewrite(UNIT_WITHOUT_STORAGE, SCOPE_WITHOUT_STORAGE)
    _rewrite_state(STATE_WITHOUT_STORAGE)
