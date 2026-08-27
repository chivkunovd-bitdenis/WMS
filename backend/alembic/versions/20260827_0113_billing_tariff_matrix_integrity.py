"""backfill tariff matrix history and enforce tenant-safe ledger lines.

Revision ID: 20260827_0113
Revises: 20260826_0112
"""

from alembic import op

revision = "20260827_0113"
down_revision = "20260826_0112"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0112 intentionally introduced the V2 tables without changing its published
    # contents.  These are the only safe legacy rows: non-storage service rows
    # without a warehouse.  Legacy dates are Moscow calendar days; V2 ranges are
    # UTC instants and use an exclusive end boundary.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM billing_tariff_versions AS legacy
                JOIN billing_tariff_versions_v2 AS existing
                  ON existing.tenant_id = legacy.tenant_id
                 AND existing.seller_id IS NOT DISTINCT FROM legacy.seller_id
                 AND existing.product_id IS NULL
                 AND existing.employee_user_id IS NULL
                 AND existing.service_code = legacy.service_code
                 AND existing.valid_from_at =
                     (legacy.valid_from::timestamp AT TIME ZONE 'Europe/Moscow')
                WHERE legacy.warehouse_id IS NULL
                  AND legacy.service_code IN (
                      'inbound', 'marketplace_outbound', 'packing', 'return'
                  )
                  AND (
                      existing.unit IS DISTINCT FROM legacy.unit
                      OR existing.rate IS DISTINCT FROM legacy.amount
                      OR existing.enabled IS DISTINCT FROM true
                      OR existing.valid_to_at IS DISTINCT FROM
                         CASE WHEN legacy.valid_to IS NULL THEN NULL
                         ELSE ((legacy.valid_to + 1)::timestamp AT TIME ZONE 'Europe/Moscow')
                         END
                  )
            ) THEN
                RAISE EXCEPTION
                    'billing tariff V2 backfill conflicts with an existing scope/start row';
            END IF;
        END $$;
        """
    )
    op.create_check_constraint(
        "ck_billing_tariff_v2_scope",
        "billing_tariff_versions_v2",
        """
        (
            employee_user_id IS NOT NULL
            AND seller_id IS NULL
            AND product_id IS NULL
            AND unit = 'item'
            AND service_code IN ('inbound', 'picking', 'marketplace_outbound', 'return')
        ) OR (
            employee_user_id IS NULL
            AND service_code IN ('inbound', 'marketplace_outbound', 'packing', 'return')
            AND (product_id IS NULL OR (seller_id IS NOT NULL AND unit = 'item'))
        )
        """,
    )
    op.execute(
        """
        INSERT INTO billing_tariff_versions_v2 (
            id, tenant_id, seller_id, product_id, employee_user_id, service_code,
            unit, enabled, rate, valid_from_at, valid_to_at
        )
        SELECT
            gen_random_uuid(), legacy.tenant_id, legacy.seller_id, NULL, NULL,
            legacy.service_code, legacy.unit, true, legacy.amount,
            legacy.valid_from::timestamp AT TIME ZONE 'Europe/Moscow',
            CASE WHEN legacy.valid_to IS NULL THEN NULL
                 ELSE ((legacy.valid_to + 1)::timestamp AT TIME ZONE 'Europe/Moscow')
            END
        FROM billing_tariff_versions AS legacy
        WHERE legacy.warehouse_id IS NULL
          AND legacy.service_code IN ('inbound', 'marketplace_outbound', 'packing', 'return')
          AND NOT EXISTS (
              SELECT 1
              FROM billing_tariff_versions_v2 AS existing
              WHERE existing.tenant_id = legacy.tenant_id
                AND existing.seller_id IS NOT DISTINCT FROM legacy.seller_id
                AND existing.product_id IS NULL
                AND existing.employee_user_id IS NULL
                AND existing.service_code = legacy.service_code
                AND existing.valid_from_at =
                    (legacy.valid_from::timestamp AT TIME ZONE 'Europe/Moscow')
          );
        """
    )

    # NULL-bearing scope columns need partial indexes; a conventional composite
    # UNIQUE index would allow duplicate common rows on PostgreSQL.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_billing_tariff_v2_common_start
        ON billing_tariff_versions_v2 (tenant_id, service_code, valid_from_at)
        WHERE seller_id IS NULL AND product_id IS NULL AND employee_user_id IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_billing_tariff_v2_seller_start
        ON billing_tariff_versions_v2 (tenant_id, seller_id, service_code, valid_from_at)
        WHERE seller_id IS NOT NULL AND product_id IS NULL AND employee_user_id IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_billing_tariff_v2_product_start
        ON billing_tariff_versions_v2
            (tenant_id, seller_id, product_id, service_code, valid_from_at)
        WHERE seller_id IS NOT NULL AND product_id IS NOT NULL AND employee_user_id IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_billing_tariff_v2_employee_start
        ON billing_tariff_versions_v2 (tenant_id, employee_user_id, service_code, valid_from_at)
        WHERE seller_id IS NULL AND product_id IS NULL AND employee_user_id IS NOT NULL
        """
    )
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    for name, columns, predicate in (
        (
            "ex_billing_tariff_v2_common_interval",
            "tenant_id WITH =, service_code WITH =",
            "seller_id IS NULL AND product_id IS NULL AND employee_user_id IS NULL",
        ),
        (
            "ex_billing_tariff_v2_seller_interval",
            "tenant_id WITH =, seller_id WITH =, service_code WITH =",
            "seller_id IS NOT NULL AND product_id IS NULL AND employee_user_id IS NULL",
        ),
        (
            "ex_billing_tariff_v2_product_interval",
            "tenant_id WITH =, seller_id WITH =, product_id WITH =, service_code WITH =",
            "seller_id IS NOT NULL AND product_id IS NOT NULL AND employee_user_id IS NULL",
        ),
        (
            "ex_billing_tariff_v2_employee_interval",
            "tenant_id WITH =, employee_user_id WITH =, service_code WITH =",
            "seller_id IS NULL AND product_id IS NULL AND employee_user_id IS NOT NULL",
        ),
    ):
        op.execute(
            f"""
            ALTER TABLE billing_tariff_versions_v2
            ADD CONSTRAINT {name}
            EXCLUDE USING gist ({columns}, tstzrange(valid_from_at, valid_to_at, '[)') WITH &&)
            WHERE ({predicate})
            """
        )

    op.create_unique_constraint(
        "uq_billing_tariff_v2_tenant_id_id",
        "billing_tariff_versions_v2",
        ["tenant_id", "id"],
    )
    op.create_unique_constraint(
        "uq_billing_ledger_entries_tenant_id_id",
        "billing_ledger_entries",
        ["tenant_id", "id"],
    )
    op.create_unique_constraint(
        "uq_operation_fact_lines_tenant_id_id",
        "operation_fact_lines",
        ["tenant_id", "id"],
    )
    op.execute(
        """
        ALTER TABLE billing_ledger_lines
        ADD CONSTRAINT fk_billing_ledger_lines_tenant_entry
        FOREIGN KEY (tenant_id, ledger_entry_id)
        REFERENCES billing_ledger_entries (tenant_id, id) ON DELETE CASCADE
        """
    )
    # Keep tenant_id when a nullable reference is deleted; PostgreSQL's
    # column-list SET NULL avoids invalidating the line's own tenant boundary.
    op.execute(
        """
        ALTER TABLE billing_ledger_lines
        ADD CONSTRAINT fk_billing_ledger_lines_tenant_fact_line
        FOREIGN KEY (tenant_id, operation_fact_line_id)
        REFERENCES operation_fact_lines (tenant_id, id)
        ON DELETE SET NULL (operation_fact_line_id)
        """
    )
    op.execute(
        """
        ALTER TABLE billing_ledger_lines
        ADD CONSTRAINT fk_billing_ledger_lines_tenant_product
        FOREIGN KEY (tenant_id, product_id)
        REFERENCES products (tenant_id, id)
        ON DELETE SET NULL (product_id)
        """
    )
    op.execute(
        """
        ALTER TABLE billing_ledger_lines
        ADD CONSTRAINT fk_billing_ledger_lines_tenant_tariff_v2
        FOREIGN KEY (tenant_id, tariff_version_v2_id)
        REFERENCES billing_tariff_versions_v2 (tenant_id, id)
        ON DELETE SET NULL (tariff_version_v2_id)
        """
    )


def downgrade() -> None:
    # Historical V2 rows are append-only.  Dropping only constraints and indexes
    # is reversible without guessing whether a matching V2 row was created by an
    # operator after the backfill.
    for name in (
        "fk_billing_ledger_lines_tenant_tariff_v2",
        "fk_billing_ledger_lines_tenant_product",
        "fk_billing_ledger_lines_tenant_fact_line",
        "fk_billing_ledger_lines_tenant_entry",
    ):
        op.execute(f"ALTER TABLE billing_ledger_lines DROP CONSTRAINT {name}")
    op.drop_constraint("ck_billing_tariff_v2_scope", "billing_tariff_versions_v2", type_="check")
    op.drop_constraint(
        "uq_billing_ledger_entries_tenant_id_id", "billing_ledger_entries", type_="unique"
    )
    op.drop_constraint(
        "uq_operation_fact_lines_tenant_id_id", "operation_fact_lines", type_="unique"
    )
    op.drop_constraint(
        "uq_billing_tariff_v2_tenant_id_id", "billing_tariff_versions_v2", type_="unique"
    )
    for name in (
        "ex_billing_tariff_v2_employee_interval",
        "ex_billing_tariff_v2_product_interval",
        "ex_billing_tariff_v2_seller_interval",
        "ex_billing_tariff_v2_common_interval",
    ):
        op.execute(f"ALTER TABLE billing_tariff_versions_v2 DROP CONSTRAINT {name}")
    for name in (
        "uq_billing_tariff_v2_employee_start",
        "uq_billing_tariff_v2_product_start",
        "uq_billing_tariff_v2_seller_start",
        "uq_billing_tariff_v2_common_start",
    ):
        op.execute(f"DROP INDEX {name}")
