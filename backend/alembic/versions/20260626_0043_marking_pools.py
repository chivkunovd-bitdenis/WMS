"""marking pools, pool products, extended marking_codes + backfill

Revision ID: 20260626_0043
Revises: 20260626_0042
Create Date: 2026-06-26

"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "20260626_0043"
down_revision = "20260626_0042"
branch_labels = None
depends_on = None


def _uuid_sql(value: uuid.UUID | object) -> str:
    if isinstance(value, uuid.UUID):
        return value.hex
    return str(value).replace("-", "")


def _backfill_marking_pools(connection: sa.Connection) -> None:
    from app.services.marking_code_service import extract_gtin_from_cis

    codes = connection.execute(
        sa.text(
            """
            SELECT id, tenant_id, seller_id, gtin, product_id, cis_code
            FROM marking_codes
            WHERE pool_id IS NULL
            """
        )
    ).fetchall()

    pool_by_key: dict[tuple[object, object, str], uuid.UUID] = {}
    pool_products: set[tuple[uuid.UUID, object]] = set()

    for row in codes:
        gtin_raw = (row.gtin or "").strip()
        if not gtin_raw:
            gtin_raw = extract_gtin_from_cis(row.cis_code) or ""
        pool_key = (row.tenant_id, row.seller_id, gtin_raw)
        pool_id = pool_by_key.get(pool_key)
        if pool_id is None:
            pool_id = uuid.uuid4()
            title = gtin_raw if gtin_raw else "Без GTIN"
            connection.execute(
                sa.text(
                    """
                    INSERT INTO marking_pools (
                        id, tenant_id, seller_id, gtin, title,
                        low_stock_threshold, created_at
                    )
                    VALUES (
                        :id, :tenant_id, :seller_id, :gtin, :title,
                        NULL, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "id": _uuid_sql(pool_id),
                    "tenant_id": _uuid_sql(row.tenant_id),
                    "seller_id": _uuid_sql(row.seller_id),
                    "gtin": gtin_raw,
                    "title": title,
                },
            )
            pool_by_key[pool_key] = pool_id

        connection.execute(
            sa.text("UPDATE marking_codes SET pool_id = :pool_id WHERE id = :code_id"),
            {"pool_id": _uuid_sql(pool_id), "code_id": _uuid_sql(row.id)},
        )

        if row.product_id is not None:
            pool_products.add((pool_id, row.product_id))

    for pool_id, product_id in pool_products:
        exists = connection.execute(
            sa.text(
                """
                SELECT 1 FROM marking_pool_products
                WHERE pool_id = :pool_id AND product_id = :product_id
                """
            ),
            {"pool_id": _uuid_sql(pool_id), "product_id": _uuid_sql(product_id)},
        ).first()
        if exists is not None:
            continue
        tenant_row = connection.execute(
            sa.text("SELECT tenant_id FROM marking_pools WHERE id = :pool_id"),
            {"pool_id": _uuid_sql(pool_id)},
        ).one()
        connection.execute(
            sa.text(
                """
                INSERT INTO marking_pool_products (
                    id, tenant_id, pool_id, product_id, created_at
                )
                VALUES (:id, :tenant_id, :pool_id, :product_id, CURRENT_TIMESTAMP)
                """
            ),
            {
                "id": _uuid_sql(uuid.uuid4()),
                "tenant_id": _uuid_sql(tenant_row.tenant_id),
                "pool_id": _uuid_sql(pool_id),
                "product_id": _uuid_sql(product_id),
            },
        )


def upgrade() -> None:
    op.create_table(
        "marking_pools",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("seller_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("gtin", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("low_stock_threshold", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_marking_pools_tenant_seller_gtin",
        "marking_pools",
        ["tenant_id", "seller_id", "gtin"],
        unique=False,
    )
    op.create_index("ix_marking_pools_tenant_id", "marking_pools", ["tenant_id"])
    op.create_index("ix_marking_pools_seller_id", "marking_pools", ["seller_id"])

    op.create_table(
        "marking_pool_products",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("pool_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["pool_id"], ["marking_pools.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pool_id", "product_id", name="uq_marking_pool_products_pool_product"),
    )
    op.create_index(
        "ix_marking_pool_products_tenant_id",
        "marking_pool_products",
        ["tenant_id"],
    )
    op.create_index(
        "ix_marking_pool_products_pool_id",
        "marking_pool_products",
        ["pool_id"],
    )
    op.create_index(
        "ix_marking_pool_products_product_id",
        "marking_pool_products",
        ["product_id"],
    )

    op.add_column(
        "marking_codes",
        sa.Column("pool_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column("marking_codes", sa.Column("serial", sa.String(length=128), nullable=True))
    op.add_column("marking_codes", sa.Column("crypto_tail", sa.String(length=256), nullable=True))
    op.add_column(
        "marking_codes",
        sa.Column("reserved_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "marking_codes",
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "marking_codes",
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "marking_codes",
        sa.Column("introduced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "marking_codes",
        sa.Column("transferred_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "marking_codes",
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "marking_codes",
        sa.Column("defective_reason", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "marking_codes",
        sa.Column("replaced_by_code_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_marking_codes_pool_id",
        "marking_codes",
        "marking_pools",
        ["pool_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_marking_codes_reserved_by_user_id",
        "marking_codes",
        "users",
        ["reserved_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_marking_codes_replaced_by_code_id",
        "marking_codes",
        "marking_codes",
        ["replaced_by_code_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_marking_codes_pool_id", "marking_codes", ["pool_id"])

    _backfill_marking_pools(op.get_bind())


def downgrade() -> None:
    op.drop_index("ix_marking_codes_pool_id", table_name="marking_codes")
    op.drop_constraint("fk_marking_codes_replaced_by_code_id", "marking_codes", type_="foreignkey")
    op.drop_constraint("fk_marking_codes_reserved_by_user_id", "marking_codes", type_="foreignkey")
    op.drop_constraint("fk_marking_codes_pool_id", "marking_codes", type_="foreignkey")
    op.drop_column("marking_codes", "replaced_by_code_id")
    op.drop_column("marking_codes", "defective_reason")
    op.drop_column("marking_codes", "consumed_at")
    op.drop_column("marking_codes", "transferred_at")
    op.drop_column("marking_codes", "introduced_at")
    op.drop_column("marking_codes", "applied_at")
    op.drop_column("marking_codes", "reserved_at")
    op.drop_column("marking_codes", "reserved_by_user_id")
    op.drop_column("marking_codes", "crypto_tail")
    op.drop_column("marking_codes", "serial")
    op.drop_column("marking_codes", "pool_id")

    op.drop_index("ix_marking_pool_products_product_id", table_name="marking_pool_products")
    op.drop_index("ix_marking_pool_products_pool_id", table_name="marking_pool_products")
    op.drop_index("ix_marking_pool_products_tenant_id", table_name="marking_pool_products")
    op.drop_table("marking_pool_products")

    op.drop_index("ix_marking_pools_seller_id", table_name="marking_pools")
    op.drop_index("ix_marking_pools_tenant_id", table_name="marking_pools")
    op.drop_index("ix_marking_pools_tenant_seller_gtin", table_name="marking_pools")
    op.drop_table("marking_pools")
