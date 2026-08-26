"""WB-штрихкод товара уникален внутри продавца, а не на весь тенант.

Один и тот же товар может находиться в кабинетах двух продавцов с одинаковым
WB-штрихкодом. Старое ограничение не давало синхронизации создать карточку
второго продавца, даже после разделения уникальности артикула по продавцам.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision = "20260826_0102"
down_revision: str | Sequence[str] | None = "20260825_0101"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_products_tenant_wb_barcode", "products", type_="unique")
    op.create_unique_constraint(
        "uq_products_tenant_wb_barcode",
        "products",
        ["tenant_id", "seller_id", "wb_barcode"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_products_tenant_wb_barcode", "products", type_="unique")
    op.create_unique_constraint(
        "uq_products_tenant_wb_barcode",
        "products",
        ["tenant_id", "wb_barcode"],
    )
