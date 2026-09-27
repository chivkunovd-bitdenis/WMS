"""WMS-517: immutable WB final-price versions; no legacy-price backfill.

Revision ID: 20260923_0517
Revises: 20260921_0490
"""

import sqlalchemy as sa

from alembic import op

revision = "20260923_0517"
down_revision = "20260921_0490"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wb_order_price_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("final_price", sa.Text(), nullable=True),
        sa.Column("currency_code", sa.Text(), nullable=True),
        sa.Column("converted_final_price", sa.Text(), nullable=True),
        sa.Column("converted_currency_code", sa.Text(), nullable=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["fbs_orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "revision", name="uq_wb_order_price_revision"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
            CREATE FUNCTION reject_wb_price_snapshot_mutation() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'wb_price_snapshot_is_immutable';
            END;
            $$ LANGUAGE plpgsql
        """)
        op.execute("""
            CREATE TRIGGER wb_price_snapshot_immutable
            BEFORE UPDATE OR DELETE ON wb_order_price_snapshots
            FOR EACH ROW EXECUTE FUNCTION reject_wb_price_snapshot_mutation()
        """)
    elif op.get_bind().dialect.name == "sqlite":
        for operation in ("UPDATE", "DELETE"):
            op.execute(f"""
                CREATE TRIGGER wb_price_snapshot_no_{operation.lower()}
                BEFORE {operation} ON wb_order_price_snapshots
                BEGIN
                    SELECT RAISE(ABORT, 'wb_price_snapshot_is_immutable');
                END
            """)
    # Price backfill happens through the existing /orders dateFrom sweep (<=30 days).
    # A migration cannot derive final customer payment from fbs_orders.price.


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER wb_price_snapshot_immutable ON wb_order_price_snapshots")
        op.execute("DROP FUNCTION reject_wb_price_snapshot_mutation()")
    elif op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TRIGGER wb_price_snapshot_no_update")
        op.execute("DROP TRIGGER wb_price_snapshot_no_delete")
    op.drop_table("wb_order_price_snapshots")
