"""Уникальность привязки склада учитывает маркетплейс

Revision ID: 20260903_0249
Revises: 20260902_0248
Create Date: 2026-09-03

Привязка склада маркетплейса уникальна по паре «селлер + числовой id склада»
(`uq_fbs_warehouse_bindings_seller_wb_warehouse`). Ограничение писалось, когда
маркетплейс был один, и в нём нет измерения «маркетплейс» — а идентификаторы
складов у Wildberries и у Ozon живут в разных пространствах и совпадают
свободно. Ревизия 03.09.2026: даже если починить создание привязки, склад Ozon с
тем же числом, что у вайлдберрисовского склада того же продавца, база просто не
примет. Это не забытый параметр в ручке, а решение модели данных.

Расширяем ограничение до тройки «селлер + маркетплейс + id склада». Оно строго
мягче прежнего: любая пара, проходившая раньше, проходит и теперь, поэтому
существующие строки не затрагиваются и данные не теряются. Колонка `marketplace`
объявлена NOT NULL со значением по умолчанию `wb`, пустых значений в ней не
бывает — проверено на боевой базе, где все 72 привязки вайлдберрисовские.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260903_0249"
down_revision: str | Sequence[str] | None = "20260902_0248"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "fbs_warehouse_bindings"
OLD_NAME = "uq_fbs_warehouse_bindings_seller_wb_warehouse"
NEW_NAME = "uq_fbs_warehouse_bindings_seller_marketplace_wb_warehouse"


def upgrade() -> None:
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint(OLD_NAME, type_="unique")
        batch.create_unique_constraint(
            NEW_NAME, ["seller_id", "marketplace", "wb_warehouse_id"]
        )


def downgrade() -> None:
    # Обратный переход сузит ограничение. Если к этому моменту у продавца уже
    # заведены склады двух маркетплейсов с одинаковым числовым id, откат
    # упадёт на существующих данных — и это правильно: молча удалять привязку
    # склада нельзя, её надо разобрать руками.
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint(NEW_NAME, type_="unique")
        batch.create_unique_constraint(OLD_NAME, ["seller_id", "wb_warehouse_id"])
