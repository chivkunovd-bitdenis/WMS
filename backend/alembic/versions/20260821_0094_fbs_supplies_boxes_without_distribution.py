"""fbs_supplies: сохраняемый режим «без распределения»"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260821_0094"
down_revision = "20260821_0093"
branch_labels = None
depends_on = None


WITHOUT_DISTRIBUTION_KEY_PREFIX = "no-distribution:"
RETIRED_WITHOUT_DISTRIBUTION_KEY_PREFIX = "retired-no-dist:"
LEGACY_RAW_IDEMPOTENCY_KEY_MAX_LENGTH = 128 - len(WITHOUT_DISTRIBUTION_KEY_PREFIX)


def _backfill_legacy_boxes_without_distribution(bind: sa.Connection) -> None:
    """Move only provable pre-0094 box markers onto their supply.

    Before this revision the mode was encoded by prepending
    ``no-distribution:`` to the stored box creation key, while the WB operation
    journal retained the original client key.  A client was also free to send a
    key beginning with that text, so the prefix by itself is not evidence of
    the old mode.  The equality below proves the old write shape instead.
    """
    bind.execute(
        sa.text(
            """
            UPDATE fbs_supplies
            SET boxes_without_distribution_at = (
                SELECT MIN(box.created_at)
                FROM fbs_packing_boxes AS box
                JOIN fbs_wb_operations AS operation
                  ON operation.seller_id = fbs_supplies.seller_id
                 AND operation.operation_kind = 'cargo_places_create'
                 AND operation.local_entity_type = 'fbs_supply'
                 AND operation.local_entity_id = fbs_supplies.id
                 AND box.creation_idempotency_key IN (
                     :prefix || substr(operation.idempotency_key, 1, :legacy_raw_key_max_length),
                     :retired_prefix
                         || substr(operation.idempotency_key, 1, :legacy_raw_key_max_length)
                 )
                WHERE box.supply_id = fbs_supplies.id
            )
            WHERE boxes_without_distribution_at IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM fbs_packing_boxes AS box
                  JOIN fbs_wb_operations AS operation
                    ON operation.seller_id = fbs_supplies.seller_id
                   AND operation.operation_kind = 'cargo_places_create'
                   AND operation.local_entity_type = 'fbs_supply'
                   AND operation.local_entity_id = fbs_supplies.id
                   AND box.creation_idempotency_key IN (
                       :prefix || substr(operation.idempotency_key, 1, :legacy_raw_key_max_length),
                       :retired_prefix
                           || substr(operation.idempotency_key, 1, :legacy_raw_key_max_length)
                   )
                  WHERE box.supply_id = fbs_supplies.id
              )
            """
        ),
        {
            "prefix": WITHOUT_DISTRIBUTION_KEY_PREFIX,
            "retired_prefix": RETIRED_WITHOUT_DISTRIBUTION_KEY_PREFIX,
            "legacy_raw_key_max_length": LEGACY_RAW_IDEMPOTENCY_KEY_MAX_LENGTH,
        },
    )
    bind.execute(
        sa.text(
            """
            UPDATE fbs_packing_boxes AS box
            SET created_without_distribution = TRUE
            WHERE EXISTS (
                SELECT 1
                FROM fbs_supplies AS supply
                JOIN fbs_wb_operations AS operation
                  ON operation.seller_id = supply.seller_id
                 AND operation.operation_kind = 'cargo_places_create'
                 AND operation.local_entity_type = 'fbs_supply'
                 AND operation.local_entity_id = supply.id
                WHERE supply.id = box.supply_id
                  AND box.creation_idempotency_key IN (
                      :prefix || substr(operation.idempotency_key, 1, :legacy_raw_key_max_length),
                      :retired_prefix
                          || substr(operation.idempotency_key, 1, :legacy_raw_key_max_length)
                  )
            )
            """
        ),
        {
            "prefix": WITHOUT_DISTRIBUTION_KEY_PREFIX,
            "retired_prefix": RETIRED_WITHOUT_DISTRIBUTION_KEY_PREFIX,
            "legacy_raw_key_max_length": LEGACY_RAW_IDEMPOTENCY_KEY_MAX_LENGTH,
        },
    )


def upgrade() -> None:
    op.add_column(
        "fbs_supplies",
        sa.Column("boxes_without_distribution_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "fbs_supplies",
        sa.Column("boxes_without_distribution_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "fbs_packing_boxes",
        sa.Column(
            "created_without_distribution",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_foreign_key(
        "fk_fbs_supplies_boxes_without_distribution_by_user_id",
        "fbs_supplies",
        "users",
        ["boxes_without_distribution_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    _backfill_legacy_boxes_without_distribution(op.get_bind())


def downgrade() -> None:
    op.drop_column("fbs_packing_boxes", "created_without_distribution")
    op.drop_constraint(
        "fk_fbs_supplies_boxes_without_distribution_by_user_id",
        "fbs_supplies",
        type_="foreignkey",
    )
    op.drop_column("fbs_supplies", "boxes_without_distribution_by_user_id")
    op.drop_column("fbs_supplies", "boxes_without_distribution_at")
