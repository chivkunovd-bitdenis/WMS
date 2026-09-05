"""Deterministic source planning for confirmed Wildberries FBS write-offs."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order_pick import FbsOrderPick
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.inventory_balance import InventoryBalance
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse
from app.services.inventory_container_service import ContainerKind
from app.services.sorting_location_service import (
    SORTING_LOCATION_CODE,
    get_or_create_sorting_location,
)

FbsShipmentSourceMode = Literal[
    "manual_pick",
    "legacy_ledger",
    "legacy_sorting",
    "sorting_loose",
    "sorting_container",
    "storage_loose",
    "storage_container",
    "forced_negative",
]


@dataclass(frozen=True)
class FbsShipmentSourceRequest:
    """One order/product quantity that must be attributed to one stock source."""

    fbs_order_id: uuid.UUID
    product_id: uuid.UUID
    quantity: int


@dataclass(frozen=True)
class FbsShipmentSourceResolution:
    """Chosen source and the part that would have to be written below zero."""

    fbs_order_id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    source_warehouse_id: uuid.UUID
    storage_location_id: uuid.UUID
    container_kind: ContainerKind | None
    container_id: uuid.UUID | None
    source_mode: FbsShipmentSourceMode
    positive_quantity: int
    shortage_quantity: int
    negative_quantity: int

    @property
    def allow_negative(self) -> bool:
        return self.negative_quantity > 0


@dataclass(frozen=True)
class FbsShipmentSourcePlan:
    tenant_id: uuid.UUID
    supply_warehouse_id: uuid.UUID
    resolutions: tuple[FbsShipmentSourceResolution, ...]

    @property
    def has_shortage(self) -> bool:
        return any(item.shortage_quantity > 0 for item in self.resolutions)


@dataclass(frozen=True)
class FbsShipmentReversalSource:
    """Exact stock key required to restore a written-off ledger row."""

    product_id: uuid.UUID
    source_warehouse_id: uuid.UUID | None
    storage_location_id: uuid.UUID
    container_kind: ContainerKind | None
    container_id: uuid.UUID | None
    quantity: int


@dataclass(frozen=True)
class _SourceCandidate:
    warehouse_id: uuid.UUID
    warehouse_code: str
    storage_location_id: uuid.UUID
    location_code: str
    container_kind: ContainerKind | None
    container_id: uuid.UUID | None
    quantity: int


@dataclass(frozen=True)
class _ManualSource:
    warehouse_id: uuid.UUID
    storage_location_id: uuid.UUID
    container_kind: ContainerKind | None
    container_id: uuid.UUID | None
    source_mode: Literal["manual_pick", "legacy_sorting"]


_ConsumptionKey = tuple[
    uuid.UUID,
    uuid.UUID,
    ContainerKind | None,
    uuid.UUID | None,
]


def _candidate_sort_key(
    candidate: _SourceCandidate,
    supply_warehouse_id: uuid.UUID,
) -> tuple[int, str, str, int, int, str, str, str, str]:
    return (
        0 if candidate.warehouse_id == supply_warehouse_id else 1,
        (
            ""
            if candidate.warehouse_id == supply_warehouse_id
            else candidate.warehouse_code
        ),
        str(candidate.warehouse_id),
        0 if candidate.location_code == SORTING_LOCATION_CODE else 1,
        0 if candidate.container_id is None else 1,
        candidate.location_code,
        str(candidate.storage_location_id),
        candidate.container_kind or "",
        "" if candidate.container_id is None else str(candidate.container_id),
    )


def _source_mode(candidate: _SourceCandidate) -> FbsShipmentSourceMode:
    if candidate.location_code == SORTING_LOCATION_CODE:
        return "sorting_loose" if candidate.container_id is None else "sorting_container"
    return "storage_loose" if candidate.container_id is None else "storage_container"


async def _load_manual_sources(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    requests: Sequence[FbsShipmentSourceRequest],
) -> dict[tuple[uuid.UUID, uuid.UUID], _ManualSource]:
    order_ids = {item.fbs_order_id for item in requests}
    if not order_ids:
        return {}
    picks = list(
        (
            await session.scalars(
                select(FbsOrderPick).where(
                    FbsOrderPick.tenant_id == tenant_id,
                    FbsOrderPick.fbs_order_id.in_(order_ids),
                    FbsOrderPick.undone_at.is_(None),
                )
            )
        ).all()
    )
    result: dict[tuple[uuid.UUID, uuid.UUID], _ManualSource] = {}
    for pick in picks:
        legacy = pick.inventory_movement_id is not None
        location_id = (
            pick.sorting_storage_location_id
            if legacy
            else pick.source_storage_location_id
        )
        location = await session.get(StorageLocation, location_id)
        if location is None or location.tenant_id != tenant_id:
            continue
        result[(pick.fbs_order_id, pick.product_id)] = _ManualSource(
            warehouse_id=location.warehouse_id,
            storage_location_id=location_id,
            container_kind=(
                None
                if legacy
                else cast(ContainerKind | None, pick.source_container_kind)
            ),
            container_id=None if legacy else pick.source_container_id,
            source_mode="legacy_sorting" if legacy else "manual_pick",
        )
    return result


async def _load_positive_candidates(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_ids: set[uuid.UUID],
    supply_warehouse_id: uuid.UUID,
) -> dict[uuid.UUID, list[_SourceCandidate]]:
    if not product_ids:
        return {}
    rows = await session.execute(
        select(
            InventoryBalance.product_id,
            InventoryBalance.quantity,
            InventoryBalance.container_kind,
            InventoryBalance.container_id,
            StorageLocation.id,
            StorageLocation.code,
            StorageLocation.warehouse_id,
            Warehouse.code,
        )
        .join(
            StorageLocation,
            StorageLocation.id == InventoryBalance.storage_location_id,
        )
        .join(Warehouse, Warehouse.id == StorageLocation.warehouse_id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            StorageLocation.tenant_id == tenant_id,
            Warehouse.tenant_id == tenant_id,
            InventoryBalance.product_id.in_(product_ids),
            InventoryBalance.quantity > 0,
            StorageLocation.deleted_at.is_(None),
        )
    )
    result: dict[uuid.UUID, list[_SourceCandidate]] = {}
    for (
        product_id,
        quantity,
        container_kind,
        container_id,
        location_id,
        location_code,
        warehouse_id,
        warehouse_code,
    ) in rows:
        result.setdefault(product_id, []).append(
            _SourceCandidate(
                warehouse_id=warehouse_id,
                warehouse_code=str(warehouse_code),
                storage_location_id=location_id,
                location_code=str(location_code),
                container_kind=cast(ContainerKind | None, container_kind),
                container_id=container_id,
                quantity=int(quantity),
            )
        )
    for candidates in result.values():
        candidates.sort(key=lambda row: _candidate_sort_key(row, supply_warehouse_id))
    return result


def _available_quantity(
    *,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    container_kind: ContainerKind | None,
    container_id: uuid.UUID | None,
    on_hand: int,
    consumption: dict[_ConsumptionKey, int],
) -> int:
    key = (product_id, storage_location_id, container_kind, container_id)
    return max(0, on_hand - consumption.get(key, 0))


def _consume(
    resolution: FbsShipmentSourceResolution,
    consumption: dict[_ConsumptionKey, int],
) -> None:
    if resolution.positive_quantity < 1:
        return
    key = (
        resolution.product_id,
        resolution.storage_location_id,
        resolution.container_kind,
        resolution.container_id,
    )
    consumption[key] = consumption.get(key, 0) + resolution.positive_quantity


async def resolve_fbs_shipment_sources(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    supply_warehouse_id: uuid.UUID,
    requests: Sequence[FbsShipmentSourceRequest],
    initial_consumption: dict[_ConsumptionKey, int] | None = None,
) -> FbsShipmentSourcePlan:
    """Resolve sources without changing inventory balances or reserving locations."""

    normalized = tuple(requests)
    for item in normalized:
        if item.quantity < 1:
            msg = "quantity must be positive"
            raise ValueError(msg)

    manual_sources = await _load_manual_sources(session, tenant_id, normalized)
    candidates = await _load_positive_candidates(
        session,
        tenant_id,
        {item.product_id for item in normalized},
        supply_warehouse_id,
    )
    sorting_location: StorageLocation | None = None
    consumption: dict[_ConsumptionKey, int] = dict(initial_consumption or {})
    resolutions: list[FbsShipmentSourceResolution] = []

    for item in normalized:
        manual = manual_sources.get((item.fbs_order_id, item.product_id))
        if manual is not None:
            manual_on_hand = next(
                (
                    row.quantity
                    for row in candidates.get(item.product_id, ())
                    if row.storage_location_id == manual.storage_location_id
                    and row.container_kind == manual.container_kind
                    and row.container_id == manual.container_id
                ),
                0,
            )
            available = _available_quantity(
                product_id=item.product_id,
                storage_location_id=manual.storage_location_id,
                container_kind=manual.container_kind,
                container_id=manual.container_id,
                on_hand=manual_on_hand,
                consumption=consumption,
            )
            positive = min(item.quantity, available)
            shortage = item.quantity - positive
            resolution = FbsShipmentSourceResolution(
                fbs_order_id=item.fbs_order_id,
                product_id=item.product_id,
                quantity=item.quantity,
                source_warehouse_id=manual.warehouse_id,
                storage_location_id=manual.storage_location_id,
                container_kind=manual.container_kind,
                container_id=manual.container_id,
                source_mode=manual.source_mode,
                positive_quantity=positive,
                shortage_quantity=shortage,
                negative_quantity=shortage,
            )
            _consume(resolution, consumption)
            resolutions.append(resolution)
            continue

        selected: tuple[_SourceCandidate, int] | None = None
        for candidate in candidates.get(item.product_id, ()):
            available = _available_quantity(
                product_id=item.product_id,
                storage_location_id=candidate.storage_location_id,
                container_kind=candidate.container_kind,
                container_id=candidate.container_id,
                on_hand=candidate.quantity,
                consumption=consumption,
            )
            if available > 0:
                selected = (candidate, available)
                break

        if selected is None:
            if sorting_location is None:
                sorting_location = await get_or_create_sorting_location(
                    session,
                    tenant_id,
                    supply_warehouse_id,
                )
            resolution = FbsShipmentSourceResolution(
                fbs_order_id=item.fbs_order_id,
                product_id=item.product_id,
                quantity=item.quantity,
                source_warehouse_id=supply_warehouse_id,
                storage_location_id=sorting_location.id,
                container_kind=None,
                container_id=None,
                source_mode="forced_negative",
                positive_quantity=0,
                shortage_quantity=item.quantity,
                negative_quantity=item.quantity,
            )
            resolutions.append(resolution)
            continue

        candidate, available = selected
        positive = min(item.quantity, available)
        shortage = item.quantity - positive
        resolution = FbsShipmentSourceResolution(
            fbs_order_id=item.fbs_order_id,
            product_id=item.product_id,
            quantity=item.quantity,
            source_warehouse_id=candidate.warehouse_id,
            storage_location_id=candidate.storage_location_id,
            container_kind=candidate.container_kind,
            container_id=candidate.container_id,
            source_mode=_source_mode(candidate),
            positive_quantity=positive,
            shortage_quantity=shortage,
            negative_quantity=shortage,
        )
        _consume(resolution, consumption)
        resolutions.append(resolution)

    return FbsShipmentSourcePlan(
        tenant_id=tenant_id,
        supply_warehouse_id=supply_warehouse_id,
        resolutions=tuple(resolutions),
    )


async def plan_fbs_shipment_sources(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    supply_warehouse_id: uuid.UUID,
    requests: Sequence[FbsShipmentSourceRequest],
    initial_consumption: dict[_ConsumptionKey, int] | None = None,
) -> FbsShipmentSourcePlan:
    """Public planning alias kept separate from the later write-off integration."""

    return await resolve_fbs_shipment_sources(
        session,
        tenant_id=tenant_id,
        supply_warehouse_id=supply_warehouse_id,
        requests=requests,
        initial_consumption=initial_consumption,
    )


def reversal_source_from_ledger(
    ledger: FbsShipmentReversalLedger,
) -> FbsShipmentReversalSource:
    """Return the exact location/container key for a reversal movement."""

    return FbsShipmentReversalSource(
        product_id=ledger.product_id,
        source_warehouse_id=ledger.source_warehouse_id,
        storage_location_id=ledger.storage_location_id,
        container_kind=cast(ContainerKind | None, ledger.container_kind),
        container_id=ledger.container_id,
        quantity=int(ledger.quantity),
    )
