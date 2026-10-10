"""WMS-748: repair container locations when all stock is in one cell."""

from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "20261010_0723"
down_revision: str | None = "20261009_0722"
branch_labels: str | None = None
depends_on: str | None = None

_SORTING_CODE = "__SORTING__"
_SERVICE_LOCATION_CODES = {_SORTING_CODE, "__DEFECT__"}
_LOGGER = logging.getLogger("alembic.runtime.migration")
_SOURCES = (
    ("inbound_intake_boxes", "box", True),
    ("inbound_intake_cargo_places", "cargo_place", True),
    ("warehouse_boxes", None, False),
)


def _source_rows(
    connection: sa.Connection,
    *,
    table_name: str,
    fixed_container_kind: str | None,
    inbound: bool,
) -> list[dict[str, Any]]:
    if inbound:
        warehouse_join = (
            "JOIN inbound_intake_requests parent "
            "ON parent.id = c.request_id AND parent.tenant_id = c.tenant_id"
        )
        warehouse_id = "parent.warehouse_id"
        container_kind = ":container_kind"
    else:
        warehouse_join = ""
        warehouse_id = "c.warehouse_id"
        container_kind = "c.container_kind"

    statement = sa.text(
        f"""
        SELECT
            c.id AS container_id,
            c.tenant_id AS tenant_id,
            {warehouse_id} AS warehouse_id,
            c.pallet_id AS pallet_id,
            c.storage_location_id AS source_location_id,
            source_location.tenant_id AS source_tenant_id,
            source_location.warehouse_id AS source_warehouse_id,
            source_location.deleted_at AS source_deleted_at,
            {container_kind} AS container_kind,
            balance.storage_location_id AS balance_location_id,
            COALESCE(SUM(balance.quantity), 0) AS balance_quantity,
            destination_location.tenant_id AS destination_tenant_id,
            destination_location.warehouse_id AS destination_warehouse_id,
            destination_location.code AS destination_code
        FROM {table_name} c
        {warehouse_join}
        JOIN storage_locations source_location
          ON source_location.id = c.storage_location_id
         AND source_location.code = :sorting_code
        LEFT JOIN inventory_balances balance
          ON balance.tenant_id = c.tenant_id
         AND balance.container_kind = {container_kind}
         AND balance.container_id = c.id
         AND balance.quantity <> 0
        LEFT JOIN storage_locations destination_location
          ON destination_location.id = balance.storage_location_id
         AND destination_location.deleted_at IS NULL
        GROUP BY
            c.id, c.tenant_id, {warehouse_id}, c.pallet_id, c.storage_location_id,
            source_location.tenant_id, source_location.warehouse_id,
            source_location.deleted_at,
            {container_kind}, balance.storage_location_id,
            destination_location.tenant_id, destination_location.warehouse_id,
            destination_location.code
        """
    )
    params: dict[str, Any] = {"sorting_code": _SORTING_CODE}
    if fixed_container_kind is not None:
        params["container_kind"] = fixed_container_kind
    return [dict(row) for row in connection.execute(statement, params).mappings()]


def _repair_source(
    connection: sa.Connection,
    *,
    table_name: str,
    fixed_container_kind: str | None,
    inbound: bool,
) -> tuple[int, int]:
    rows = _source_rows(
        connection,
        table_name=table_name,
        fixed_container_kind=fixed_container_kind,
        inbound=inbound,
    )
    records: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
    for row in rows:
        key = (row["container_id"], row["tenant_id"], row["container_kind"])
        record = records.setdefault(
            key,
            {
                "container_id": row["container_id"],
                "tenant_id": row["tenant_id"],
                "warehouse_id": row["warehouse_id"],
                "pallet_id": row["pallet_id"],
                "source_location_id": row["source_location_id"],
                "source_tenant_id": row["source_tenant_id"],
                "source_warehouse_id": row["source_warehouse_id"],
                "source_deleted_at": row["source_deleted_at"],
                "balances": [],
            },
        )
        if row["balance_location_id"] is not None:
            record["balances"].append(row)

    updated = 0
    ambiguous = 0
    for record in records.values():
        balances = record["balances"]
        if (
            record["pallet_id"] is not None
            or record["source_tenant_id"] != record["tenant_id"]
            or record["source_warehouse_id"] != record["warehouse_id"]
            or record["source_deleted_at"] is not None
            or len(balances) != 1
        ):
            ambiguous += 1
            continue

        balance = balances[0]
        destination_id = balance["balance_location_id"]
        if (
            int(balance["balance_quantity"] or 0) <= 0
            or balance["destination_tenant_id"] != record["tenant_id"]
            or balance["destination_warehouse_id"] != record["warehouse_id"]
            or balance["destination_code"] in _SERVICE_LOCATION_CODES
        ):
            ambiguous += 1
            continue

        result = connection.execute(
            sa.text(
                f"""UPDATE {table_name}
                    SET storage_location_id = :destination_id
                    WHERE id = :container_id
                      AND tenant_id = :tenant_id
                      AND storage_location_id = :source_location_id"""
            ),
            {
                "destination_id": destination_id,
                "container_id": record["container_id"],
                "tenant_id": record["tenant_id"],
                "source_location_id": record["source_location_id"],
            },
        )
        if result.rowcount == 1:
            updated += 1
        else:
            ambiguous += 1

    return updated, ambiguous


def upgrade() -> None:
    connection = op.get_bind()
    total_updated = 0
    total_ambiguous = 0
    for table_name, fixed_container_kind, inbound in _SOURCES:
        updated, ambiguous = _repair_source(
            connection,
            table_name=table_name,
            fixed_container_kind=fixed_container_kind,
            inbound=inbound,
        )
        total_updated += updated
        total_ambiguous += ambiguous
        _LOGGER.info(
            "WMS-748: %s updated=%d ambiguous=%d",
            table_name,
            updated,
            ambiguous,
        )
    _LOGGER.info(
        "WMS-748: total updated=%d ambiguous=%d",
        total_updated,
        total_ambiguous,
    )


def downgrade() -> None:
    """Correct container locations are valid data and cannot be reversed safely."""
    pass
