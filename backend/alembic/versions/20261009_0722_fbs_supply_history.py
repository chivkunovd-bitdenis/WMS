"""WMS-722: retain order/movement history when an empty supply card is removed."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261009_0722"
down_revision: str | Sequence[str] | None = "20261007_2303"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REFERENCES = (
    ("fbs_order_picks", "fbs_supply_id", "CASCADE"),
    ("fbs_order_product_picks", "fbs_supply_id", "CASCADE"),
    ("withdrawal_items", "supply_id", None),
)
NAMING = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}


def _change_reference(table: str, column: str, *, nullable: bool, ondelete: str | None) -> None:
    keys = sa.inspect(op.get_bind()).get_foreign_keys(table)
    key = next(key for key in keys if key["constrained_columns"] == [column]
               and key["referred_table"] == "fbs_supplies")
    name = key["name"] or f"fk_{table}_{column}_fbs_supplies"
    with op.batch_alter_table(table, naming_convention=NAMING) as batch:
        batch.drop_constraint(name, type_="foreignkey")
        batch.alter_column(column, existing_type=sa.Uuid(), nullable=nullable)
        batch.create_foreign_key(name, "fbs_supplies", [column], ["id"], ondelete=ondelete)


def upgrade() -> None:
    for table, column, _ in REFERENCES:
        _change_reference(table, column, nullable=True, ondelete="SET NULL")


def downgrade() -> None:
    # Never discard history or invent a replacement supply during a rollback.
    for table, column, _ in REFERENCES:
        detached = op.get_bind().scalar(sa.text(
            f"SELECT count(*) FROM {table} WHERE {column} IS NULL"
        ))
        if detached:
            raise RuntimeError("Cannot restore required supply references with detached history")
    for table, column, ondelete in reversed(REFERENCES):
        _change_reference(table, column, nullable=False, ondelete=ondelete)
