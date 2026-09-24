"""WMS-517: durable tenant-scoped withdrawal attempts and read recovery."""

import sqlalchemy as sa

from alembic import op

revision = "20260923_0518"
down_revision = "20260923_0517"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "withdrawal_operations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("seller_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("client_request_id", sa.Uuid(), nullable=False),
        sa.Column("selection_hash", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("certificate_thumbprint", sa.String(length=128), nullable=True),
        sa.Column("certificate_metadata", sa.JSON(), nullable=True),
        sa.Column("auth_uuid", sa.String(length=36), nullable=True),
        sa.Column("auth_challenge", sa.Text(), nullable=True),
        sa.Column("token_enc", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("participant_inn", sa.String(length=12), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "environment IN ('sandbox', 'production')", name="ck_withdrawal_environment"
        ),
        sa.CheckConstraint(
            "state IN ('created','auth_pending','documents_pending_signature','submitting',"
            "'submitted','reconciling','succeeded','partial_failed','failed','cancelled')",
            name="ck_withdrawal_operation_state",
        ),
        sa.CheckConstraint("attempt >= 1", name="ck_withdrawal_attempt"),
        sa.ForeignKeyConstraint(
            ["seller_id"],
            ["sellers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "tenant_id", "seller_id", name="uq_withdrawal_operation_scope"),
        sa.UniqueConstraint(
            "tenant_id", "seller_id", "client_request_id", name="uq_withdrawal_client_request"
        ),
    )
    op.create_table(
        "withdrawal_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("seller_id", sa.Uuid(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("pg", sa.String(length=64), nullable=False),
        sa.Column("participant_inn", sa.String(length=12), nullable=False),
        sa.Column("exact_payload", sa.LargeBinary(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("signature", sa.Text(), nullable=True),
        sa.Column("certificate_thumbprint", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("request_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gis_document_id", sa.String(length=36), nullable=True),
        sa.Column("gis_status", sa.String(length=64), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.LargeBinary(), nullable=True),
        sa.Column("errors", sa.JSON(), nullable=True),
        sa.Column("common_errors", sa.JSON(), nullable=True),
        sa.Column("incident", sa.String(length=64), nullable=True),
        sa.Column("reconciliation_ids", sa.JSON(), nullable=True),
        sa.Column("poll_count", sa.Integer(), nullable=False),
        sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_id", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('pending_signature','submitting','submitted','reconciling',"
            "'succeeded','failed')",
            name="ck_withdrawal_document_state",
        ),
        sa.CheckConstraint("attempt >= 1", name="ck_withdrawal_document_attempt"),
        sa.CheckConstraint(
            "state NOT IN ('submitting','submitted','reconciling') OR "
            "(next_poll_at IS NOT NULL AND request_started_at IS NOT NULL)",
            name="ck_withdrawal_recoverable",
        ),
        sa.ForeignKeyConstraint(
            ["operation_id", "tenant_id", "seller_id"],
            [
                "withdrawal_operations.id",
                "withdrawal_operations.tenant_id",
                "withdrawal_operations.seller_id",
            ],
            name="fk_withdrawal_document_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("environment", "gis_document_id", name="uq_withdrawal_gis_document"),
        sa.UniqueConstraint(
            "id",
            "operation_id",
            "tenant_id",
            "seller_id",
            "attempt",
            name="uq_withdrawal_document_scope",
        ),
    )
    op.create_index(
        "ix_withdrawal_due", "withdrawal_documents", ["next_poll_at", "lease_until"], unique=False
    )
    op.create_table(
        "withdrawal_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("seller_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("marking_id", sa.Uuid(), nullable=False),
        sa.Column("marking_code_id", sa.Uuid(), nullable=True),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("supply_id", sa.Uuid(), nullable=False),
        sa.Column("cis", sa.String(length=512), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("product_cost", sa.BigInteger(), nullable=True),
        sa.Column("pg", sa.String(length=64), nullable=True),
        sa.Column("owner_inn", sa.String(length=12), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("holds_claim", sa.Boolean(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('pending','succeeded','failed')", name="ck_withdrawal_item_state"
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "operation_id", "tenant_id", "seller_id", "attempt"],
            [
                "withdrawal_documents.id",
                "withdrawal_documents.operation_id",
                "withdrawal_documents.tenant_id",
                "withdrawal_documents.seller_id",
                "withdrawal_documents.attempt",
            ],
            name="fk_withdrawal_item_document_scope",
        ),
        sa.ForeignKeyConstraint(
            ["marking_code_id"],
            ["marking_codes.id"],
        ),
        sa.ForeignKeyConstraint(
            ["marking_id"],
            ["fbs_order_markings.id"],
        ),
        sa.ForeignKeyConstraint(
            ["operation_id", "tenant_id", "seller_id"],
            [
                "withdrawal_operations.id",
                "withdrawal_operations.tenant_id",
                "withdrawal_operations.seller_id",
            ],
            name="fk_withdrawal_item_scope",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["fbs_orders.id"],
        ),
        sa.ForeignKeyConstraint(
            ["price_snapshot_id"],
            ["wb_order_price_snapshots.id"],
        ),
        sa.ForeignKeyConstraint(
            ["supply_id"],
            ["fbs_supplies.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "operation_id", "marking_id", "attempt", name="uq_withdrawal_item_attempt"
        ),
    )
    op.create_index(
        "uq_withdrawal_marking_claim",
        "withdrawal_items",
        ["marking_id"],
        unique=True,
        postgresql_where=sa.text("holds_claim"),
        sqlite_where=sa.text("holds_claim = 1"),
    )
    op.create_index(
        "uq_withdrawal_cis_claim",
        "withdrawal_items",
        ["tenant_id", "cis"],
        unique=True,
        postgresql_where=sa.text("holds_claim"),
        sqlite_where=sa.text("holds_claim = 1"),
    )
    op.create_table(
        "withdrawal_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.LargeBinary(), nullable=True),
        sa.Column("errors", sa.JSON(), nullable=True),
        sa.Column("common_errors", sa.JSON(), nullable=True),
        sa.Column("incident", sa.String(length=64), nullable=True),
        sa.Column("reconciliation_ids", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["withdrawal_documents.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
            CREATE FUNCTION protect_withdrawal_document() RETURNS trigger AS $$
            BEGIN
                IF ROW(NEW.operation_id, NEW.tenant_id, NEW.seller_id, NEW.attempt,
                       NEW.environment, NEW.pg, NEW.participant_inn, NEW.exact_payload,
                       NEW.payload_sha256, NEW.certificate_thumbprint)
                   IS DISTINCT FROM
                   ROW(OLD.operation_id, OLD.tenant_id, OLD.seller_id, OLD.attempt,
                       OLD.environment, OLD.pg, OLD.participant_inn, OLD.exact_payload,
                       OLD.payload_sha256, OLD.certificate_thumbprint)
                   OR (OLD.signature IS NOT NULL AND NEW.signature IS DISTINCT FROM OLD.signature)
                THEN
                    RAISE EXCEPTION 'withdrawal_document_is_immutable';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """)
        op.execute("""
            CREATE TRIGGER withdrawal_document_immutable
            BEFORE UPDATE ON withdrawal_documents
            FOR EACH ROW EXECUTE FUNCTION protect_withdrawal_document()
        """)
        op.execute("""
            CREATE FUNCTION protect_withdrawal_observation() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'withdrawal_observation_is_immutable';
            END;
            $$ LANGUAGE plpgsql
        """)
        op.execute("""
            CREATE TRIGGER withdrawal_observation_immutable
            BEFORE UPDATE OR DELETE ON withdrawal_observations
            FOR EACH ROW EXECUTE FUNCTION protect_withdrawal_observation()
        """)
    elif op.get_bind().dialect.name == "sqlite":
        op.execute("""
            CREATE TRIGGER withdrawal_observation_no_update
            BEFORE UPDATE ON withdrawal_observations
            BEGIN
                SELECT RAISE(ABORT, 'withdrawal_observation_is_immutable');
            END
        """)
        op.execute("""
            CREATE TRIGGER withdrawal_observation_no_delete
            BEFORE DELETE ON withdrawal_observations
            BEGIN
                SELECT RAISE(ABORT, 'withdrawal_observation_is_immutable');
            END
        """)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER withdrawal_observation_immutable ON withdrawal_observations")
    elif op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TRIGGER withdrawal_observation_no_update")
        op.execute("DROP TRIGGER withdrawal_observation_no_delete")
    op.drop_table("withdrawal_observations")
    op.drop_table("withdrawal_items")
    op.drop_table("withdrawal_documents")
    op.drop_table("withdrawal_operations")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION protect_withdrawal_document()")
        op.execute("DROP FUNCTION protect_withdrawal_observation()")
