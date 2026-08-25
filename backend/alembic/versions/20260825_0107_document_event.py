"""add append-only document status and data journal

Revision ID: 20260825_0107
Revises: 20260825_0106
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260825_0107"
down_revision = "20260825_0106"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.String(length=32), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("qty", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column(
            "payload_json",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_event_document_occurred",
        "document_event",
        ["tenant_id", "document_type", "document_id", "occurred_at"],
    )
    op.create_index(
        "ix_document_event_actor_occurred",
        "document_event",
        ["tenant_id", "actor_user_id", "occurred_at"],
    )
    op.create_index(
        "uq_document_event_tenant_idempotency",
        "document_event",
        ["tenant_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION write_system_fbs_supply_status_event()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF OLD.status IS DISTINCT FROM NEW.status
                   AND COALESCE(
                       current_setting('wms.document_event_writer', true), ''
                   ) <> 'application'
                THEN
                    BEGIN
                        INSERT INTO document_event (
                            id,
                            tenant_id,
                            document_type,
                            document_id,
                            event_type,
                            actor_user_id,
                            source,
                            occurred_at,
                            qty,
                            product_id,
                            payload_json,
                            idempotency_key,
                            created_at
                        )
                        VALUES (
                            gen_random_uuid(),
                            NEW.tenant_id,
                            'fbs_supply',
                            NEW.id,
                            'status_changed',
                            NULL,
                            'system',
                            CURRENT_TIMESTAMP,
                            (SELECT COUNT(*) FROM fbs_orders WHERE supply_id = NEW.id),
                            NULL,
                            jsonb_build_object('from', OLD.status, 'to', NEW.status),
                            NULL,
                            CURRENT_TIMESTAMP
                        );
                    EXCEPTION WHEN OTHERS THEN
                        RAISE WARNING
                            'document event write failed for fbs supply %: %',
                            NEW.id,
                            SQLERRM;
                    END;
                END IF;
                RETURN NEW;
            END;
            $$
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_fbs_supply_system_status_event
            AFTER UPDATE OF status ON fbs_supplies
            FOR EACH ROW
            EXECUTE FUNCTION write_system_fbs_supply_status_event()
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_fbs_supply_system_status_event ON fbs_supplies")
        op.execute("DROP FUNCTION IF EXISTS write_system_fbs_supply_status_event()")
    op.drop_index("uq_document_event_tenant_idempotency", table_name="document_event")
    op.drop_index("ix_document_event_actor_occurred", table_name="document_event")
    op.drop_index("ix_document_event_document_occurred", table_name="document_event")
    op.drop_table("document_event")
