"""Store immutable product dimension observations and active source snapshot."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20260822_0095"
down_revision: str | Sequence[str] | None = "20260821_0093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("dimensions_source", sa.String(length=32), nullable=True))
    op.add_column(
        "products", sa.Column("dimensions_updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "products",
        sa.Column("dimensions_updated_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_products_dimensions_updated_by_user_id",
        "products",
        "users",
        ["dimensions_updated_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "product_dimension_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "author_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "observed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("external_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("length_mm", sa.Integer(), nullable=True),
        sa.Column("width_mm", sa.Integer(), nullable=True),
        sa.Column("height_mm", sa.Integer(), nullable=True),
        sa.Column("weight_g", sa.Integer(), nullable=True),
        sa.Column("volume_liters", sa.Numeric(18, 6), nullable=True),
        sa.Column("container_basis", sa.Text(), nullable=True),
        sa.Column("applied", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("fingerprint", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_product_dimension_events_product_observed",
        "product_dimension_events",
        ["product_id", "observed_at"],
    )
    op.create_index(
        "uq_product_dimension_events_product_fingerprint",
        "product_dimension_events",
        ["product_id", "fingerprint"],
        unique=True,
    )
    op.create_index(
        "uq_product_dimension_events_one_applied",
        "product_dimension_events",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("applied = true"),
        sqlite_where=sa.text("applied = 1"),
    )
    op.create_index(
        "ix_product_dimension_events_tenant_id", "product_dimension_events", ["tenant_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_product_dimension_events_tenant_id", table_name="product_dimension_events")
    op.drop_index("uq_product_dimension_events_one_applied", table_name="product_dimension_events")
    op.drop_index(
        "uq_product_dimension_events_product_fingerprint", table_name="product_dimension_events"
    )
    op.drop_index(
        "ix_product_dimension_events_product_observed", table_name="product_dimension_events"
    )
    op.drop_table("product_dimension_events")
    op.drop_constraint("fk_products_dimensions_updated_by_user_id", "products", type_="foreignkey")
    op.drop_column("products", "dimensions_updated_by_user_id")
    op.drop_column("products", "dimensions_updated_at")
    op.drop_column("products", "dimensions_source")
