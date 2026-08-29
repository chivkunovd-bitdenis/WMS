"""Shared physical-source contract for marketplace and FBS pick options."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_balance import InventoryBalance
from app.models.storage_location import StorageLocation
from app.services import inventory_service, warehouse_map_service
from app.services.inventory_container_service import ContainerKind
from app.services.sorting_location_service import SORTING_LOCATION_CODE, UNASSIGNED_LABEL
from app.services.warehouse_map_service import WarehouseContainerPathItem


class PickOptionLocationError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class PickOptionSource:
    quantity: int
    picked: int
    is_loose: bool
    source_label: str
    container_path: tuple[WarehouseContainerPathItem, ...]


@dataclass(frozen=True)
class PickOptionLocation:
    storage_location_id: uuid.UUID
    location_code: str
    quantity: int
    reserved: int
    available: int
    picked: int
    sources: tuple[PickOptionSource, ...]


def _operator_location_code(code: str) -> str:
    return UNASSIGNED_LABEL if code == SORTING_LOCATION_CODE else code


async def list_pick_option_locations(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_ids: list[uuid.UUID],
    picked_by_location: dict[tuple[uuid.UUID, uuid.UUID], int],
    picked_by_source: dict[
        tuple[
            uuid.UUID,
            uuid.UUID,
            ContainerKind | None,
            uuid.UUID | None,
        ],
        int,
    ]
    | None = None,
) -> dict[uuid.UUID, list[PickOptionLocation]]:
    """Keep legacy location totals and add distinct physical stock sources."""
    locations_by_product: dict[uuid.UUID, list[PickOptionLocation]] = {
        product_id: [] for product_id in product_ids
    }
    if not product_ids:
        return locations_by_product
    source_progress = picked_by_source or {}

    legacy_rows = await inventory_service.list_location_balances_for_products_in_warehouse(
        session,
        tenant_id,
        warehouse_id,
        product_ids,
    )
    source_result = await session.execute(
        select(
            InventoryBalance.product_id,
            InventoryBalance.storage_location_id,
            InventoryBalance.quantity,
            InventoryBalance.container_kind,
            InventoryBalance.container_id,
        )
        .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.warehouse_id == warehouse_id,
            InventoryBalance.product_id.in_(product_ids),
            InventoryBalance.quantity > 0,
        )
    )
    source_rows = list(source_result.all())
    container_refs: set[tuple[ContainerKind, uuid.UUID]] = set()
    for _product_id, _location_id, _quantity, raw_kind, container_id in source_rows:
        if raw_kind is None and container_id is None:
            continue
        if raw_kind not in {"pallet", "box", "cargo_place"} or container_id is None:
            raise PickOptionLocationError("invalid_container_reference")
        container_refs.add((cast(ContainerKind, raw_kind), container_id))
    for _product_id, _location_id, raw_kind, container_id in source_progress:
        if raw_kind is None and container_id is None:
            continue
        if raw_kind is None or container_id is None:
            raise PickOptionLocationError("invalid_container_reference")
        container_refs.add((raw_kind, container_id))

    try:
        container_paths = await warehouse_map_service.resolve_container_paths(
            session,
            tenant_id,
            warehouse_id,
            container_refs,
        )
    except warehouse_map_service.WarehouseMapError as exc:
        raise PickOptionLocationError("invalid_container_reference") from exc

    sources_by_location: dict[
        tuple[uuid.UUID, uuid.UUID], list[PickOptionSource]
    ] = defaultdict(list)
    seen_source_keys: set[
        tuple[
            uuid.UUID,
            uuid.UUID,
            ContainerKind | None,
            uuid.UUID | None,
        ]
    ] = set()
    for product_id, location_id, quantity, raw_kind, container_id in source_rows:
        source_key: tuple[
            uuid.UUID,
            uuid.UUID,
            ContainerKind | None,
            uuid.UUID | None,
        ]
        if raw_kind is None and container_id is None:
            source_key = (product_id, location_id, None, None)
            source = PickOptionSource(
                quantity=int(quantity),
                picked=source_progress.get(source_key, 0),
                is_loose=True,
                source_label="Россыпью",
                container_path=(),
            )
        else:
            assert raw_kind is not None and container_id is not None
            ref = (cast(ContainerKind, raw_kind), container_id)
            source_key = (product_id, location_id, *ref)
            path = container_paths.get(ref)
            if not path:
                raise PickOptionLocationError("invalid_container_reference")
            source = PickOptionSource(
                quantity=int(quantity),
                picked=source_progress.get(source_key, 0),
                is_loose=False,
                source_label=path[-1].label,
                container_path=path,
            )
        seen_source_keys.add(source_key)
        sources_by_location[(product_id, location_id)].append(source)

    for source_key, picked in source_progress.items():
        if picked <= 0 or source_key in seen_source_keys:
            continue
        product_id, location_id, container_kind, container_id = source_key
        if product_id not in locations_by_product:
            continue
        if container_kind is None and container_id is None:
            source = PickOptionSource(
                quantity=0,
                picked=picked,
                is_loose=True,
                source_label="Россыпью",
                container_path=(),
            )
        else:
            if container_kind is None or container_id is None:
                raise PickOptionLocationError("invalid_container_reference")
            path = container_paths.get((container_kind, container_id))
            if not path:
                raise PickOptionLocationError("invalid_container_reference")
            source = PickOptionSource(
                quantity=0,
                picked=picked,
                is_loose=False,
                source_label=path[-1].label,
                container_path=path,
            )
        sources_by_location[(product_id, location_id)].append(source)

    for sources in sources_by_location.values():
        sources.sort(
            key=lambda source: (
                source.is_loose,
                tuple(item.label for item in source.container_path),
            )
        )

    seen_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for product_id, location_id, code, on_hand, reserved in legacy_rows:
        seen_pairs.add((product_id, location_id))
        locations_by_product.setdefault(product_id, []).append(
            PickOptionLocation(
                storage_location_id=location_id,
                location_code=_operator_location_code(code),
                quantity=on_hand,
                reserved=reserved,
                available=max(0, on_hand - reserved),
                picked=picked_by_location.get((product_id, location_id), 0),
                sources=tuple(sources_by_location.get((product_id, location_id), [])),
            )
        )

    missing_picked_pairs = [
        (product_id, location_id, quantity)
        for (product_id, location_id), quantity in picked_by_location.items()
        if (product_id, location_id) not in seen_pairs
        and product_id in locations_by_product
    ]
    missing_location_ids = {location_id for _, location_id, _ in missing_picked_pairs}
    missing_locations: dict[uuid.UUID, StorageLocation] = {}
    if missing_location_ids:
        missing_location_rows = await session.scalars(
            select(StorageLocation).where(
                StorageLocation.id.in_(missing_location_ids),
                StorageLocation.tenant_id == tenant_id,
                StorageLocation.warehouse_id == warehouse_id,
            )
        )
        missing_locations = {
            location.id: location for location in missing_location_rows.all()
        }

    for product_id, location_id, picked in missing_picked_pairs:
        location = missing_locations.get(location_id)
        if location is None:
            continue
        available = await inventory_service.available_at_location(
            session, tenant_id, product_id, location_id
        )
        reserved = await inventory_service.total_reserved_at_location(
            session, tenant_id, product_id, location_id
        )
        locations_by_product[product_id].append(
            PickOptionLocation(
                storage_location_id=location_id,
                location_code=_operator_location_code(location.code),
                quantity=available + reserved,
                reserved=reserved,
                available=max(0, available),
                picked=picked,
                sources=tuple(sources_by_location.get((product_id, location_id), [])),
            )
        )

    for locations in locations_by_product.values():
        locations.sort(key=lambda location: location.location_code)
    return locations_by_product
