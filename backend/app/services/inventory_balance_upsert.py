"""Dialect-specific atomic UPSERT for one inventory balance identity."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.sql.dml import Insert

from app.models.inventory_balance import InventoryBalance
from app.services.inventory_container_service import ContainerKind

_CONTAINER_ID_COALESCE_SQL = (
    "coalesce(container_id, '00000000-0000-0000-0000-000000000000')"
)


def build_positive_balance_upsert(
    *,
    dialect_name: str,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    quantity_delta: int,
    container_kind: ContainerKind | None = None,
    container_id: uuid.UUID | None = None,
) -> Insert:
    values = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "product_id": product_id,
        "storage_location_id": storage_location_id,
        "container_kind": container_kind,
        "container_id": container_id,
        "quantity": quantity_delta,
        "quantity_unpacked": quantity_delta,
        "quantity_packed": 0,
        "updated_at": datetime.now(UTC),
    }
    update_values = {
        "quantity_unpacked": InventoryBalance.quantity_unpacked + quantity_delta,
        "quantity": (
            InventoryBalance.quantity_unpacked
            + InventoryBalance.quantity_packed
            + quantity_delta
        ),
        "updated_at": datetime.now(UTC),
    }
    if dialect_name == "postgresql":
        return postgresql_insert(InventoryBalance).values(**values).on_conflict_do_update(
            index_elements=[
                InventoryBalance.storage_location_id,
                InventoryBalance.product_id,
                text(_CONTAINER_ID_COALESCE_SQL),
            ],
            set_=update_values,
        )
    if dialect_name == "sqlite":
        return sqlite_insert(InventoryBalance).values(**values).on_conflict_do_update(
            index_elements=[
                InventoryBalance.storage_location_id,
                InventoryBalance.product_id,
                text(_CONTAINER_ID_COALESCE_SQL),
            ],
            set_=update_values,
        )
    msg = f"unsupported inventory balance dialect: {dialect_name}"
    raise RuntimeError(msg)
