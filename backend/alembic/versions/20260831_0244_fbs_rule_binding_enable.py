"""Enable stock sync on active served bindings with configured FBS rules.

Revision ID: 20260831_0244
Revises: 20260830_0243

The catalogue percentage rule is now the only product-level switch. Existing
configured products must not remain silently blocked by the retired stock-sync
flag. Inactive or unserved bindings remain untouched because ``served`` is the
warehouse ownership boundary. Sellers without any configured ``fbs_percent``
are deliberately untouched.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260831_0244"
down_revision: str | Sequence[str] | None = "20260830_0243"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE fbs_warehouse_bindings AS binding
            SET stock_sync_enabled = true
            WHERE binding.is_active = true
              AND binding.served = true
              AND EXISTS (
                SELECT 1
                FROM products AS product
                WHERE product.tenant_id = binding.tenant_id
                  AND product.seller_id = binding.seller_id
                  AND product.fbs_percent IS NOT NULL
            )
            """
        )
    )


def downgrade() -> None:
    # Previous per-binding false values cannot be reconstructed safely.
    pass
