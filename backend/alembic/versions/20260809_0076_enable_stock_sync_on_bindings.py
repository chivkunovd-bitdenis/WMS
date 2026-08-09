"""Включить выгрузку остатков на существующих привязках складов ФБС.

Рубильник `stock_sync_enabled` на привязке создавался выключенным, чтобы не выгрузить
в WB нули по всему складу. Эта причина ушла: теперь фильтрует признак на товаре
(`products.fbs_stock_sync_enabled`, по умолчанию выключен), и без него в WB не уходит
ничего. Выключенный рубильник остался второй скрытой заслонкой — селлер включает
галочку у товара, а выгрузка молча не идёт.

Включаем его на активных привязках. Это безопасно: пока у товаров признак выключен,
публиковаться всё равно нечему.

Revision ID: 20260809_0076
"""

from __future__ import annotations

from alembic import op

revision = "20260809_0076"
down_revision = "20260809_0075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE fbs_warehouse_bindings SET stock_sync_enabled = true WHERE is_active = true"
    )


def downgrade() -> None:
    # Обратно не выключаем: неизвестно, какие привязки были выключены осознанно.
    pass
