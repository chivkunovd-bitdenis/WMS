"""Артикул товара уникален внутри продавца, а не на весь тенант.

Ограничение ``uq_products_tenant_sku`` (tenant_id, sku_code) считало пару
«артикул + размер» занятой на всю компанию. Из-за этого импорт карточек WB для
второго продавца молча пропускал товар: `J308-24/36` уже числился за Loviana,
и такой же товар для ООО «Фэшн» создать было нельзя. На проде так не завелись
50 из 72 карточек ООО «Фэшн», и перенос остатков упирался в отсутствие
товара-получателя.

Ограничение заменяется на (tenant_id, seller_id, sku_code).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision = "20260825_0101"
down_revision: str | Sequence[str] | None = "20260823_0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_products_tenant_seller_sku",
        "products",
        ["tenant_id", "seller_id", "sku_code"],
    )
    op.drop_constraint("uq_products_tenant_sku", "products", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_products_tenant_sku", "products", ["tenant_id", "sku_code"]
    )
    op.drop_constraint("uq_products_tenant_seller_sku", "products", type_="unique")
