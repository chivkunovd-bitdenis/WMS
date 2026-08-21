"""fbs_supplies: поле режима «без распределения» вместо приписки к ключу короба

Revision ID: 20260821_0094
Revises: 20260821_0093
Create Date: 2026-08-21

Дефект I15: признак «короба без распределения» хранился припиской
«no-distribution:» к creation_idempotency_key короба — служебному полю
идемпотентности, а не полю состояния. Из-за этого признак терялся при
пересоздании коробов (ровно это произошло на проде 20.08.2026, дважды).
Плюс галку на экране можно было переключить только пока коробов вообще
не было — раздумавший оператор упирался в тупик.

Переносим признак на саму поставку: он относится ко всей поставке целиком
(так уже вело себя старое чтение — «без распределения», если хотя бы один
короб размечен так), а не к конкретному коробу. Пара полей «когда» и «кто»
по образцу honest_sign_skipped_at/by_user_id — тот же паттерн уже есть на
этой таблице.

Поле добавляющее: старые короба, где режим до сих пор виден только через
приписку к ключу, не трогаем и не переносим данными — backend/app/services
/fbs_packing_box_service.py читает оба источника (приписку как откат для
старых коробов, поле поставки как основной путь для новых и переключённых),
так что боевые поставки признак не теряют без миграции данных.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_0094"
down_revision: str | Sequence[str] | None = "20260821_0093"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Временная метка, когда включили режим «без распределения» на поставке
    op.add_column(
        "fbs_supplies",
        sa.Column("boxes_without_distribution_at", sa.DateTime(timezone=True), nullable=True),
    )
    # UUID пользователя, который включил режим
    op.add_column(
        "fbs_supplies",
        sa.Column("boxes_without_distribution_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_fbs_supplies_boxes_without_distribution_by_user_id",
        "fbs_supplies",
        "users",
        ["boxes_without_distribution_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_fbs_supplies_boxes_without_distribution_by_user_id",
        "fbs_supplies",
        type_="foreignkey",
    )
    op.drop_column("fbs_supplies", "boxes_without_distribution_by_user_id")
    op.drop_column("fbs_supplies", "boxes_without_distribution_at")
