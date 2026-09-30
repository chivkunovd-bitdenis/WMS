"""Resolve polymorphic balance containers inside tenant and warehouse bounds."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeCargoPlace,
    InboundIntakeRequest,
)
from app.models.pallet import Pallet
from app.models.storage_location import StorageLocation
from app.models.warehouse_box import WarehouseBox
from app.services.box_barcode_service import inbound_box_display_code

ContainerKind = Literal["pallet", "box", "cargo_place"]


@dataclass(frozen=True)
class InventoryContainerScanMatch:
    kind: ContainerKind
    id: uuid.UUID
    code: str


class InventoryContainerScanError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


async def resolve_container_scan(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    barcode: str,
    *,
    casefold_candidates: frozenset[str] | None = None,
) -> InventoryContainerScanMatch:
    raw = barcode.strip()
    if not raw and not casefold_candidates:
        raise InventoryContainerScanError("container_scan_not_found")

    # Only the FBS pick scanner opts into normalized alternatives. Other
    # container flows retain their exact lookup behavior.
    def code_matches(column: Any) -> Any:
        if casefold_candidates is None:
            return column == raw
        return func.upper(column).in_(casefold_candidates)

    matches: list[InventoryContainerScanMatch] = []
    pallets = await session.scalars(
        select(Pallet).where(
            Pallet.tenant_id == tenant_id,
            Pallet.warehouse_id == warehouse_id,
            Pallet.disbanded_at.is_(None),
            or_(code_matches(Pallet.barcode), code_matches(Pallet.code)),
        )
    )
    matches.extend(
        InventoryContainerScanMatch("pallet", pallet.id, pallet.code)
        for pallet in pallets.all()
    )
    warehouse_boxes = await session.scalars(
        select(WarehouseBox).where(
            WarehouseBox.tenant_id == tenant_id,
            WarehouseBox.warehouse_id == warehouse_id,
            code_matches(WarehouseBox.internal_barcode),
        )
    )
    matches.extend(
        InventoryContainerScanMatch(
            box.container_kind,
            box.id,
            box.internal_barcode,
        )
        for box in warehouse_boxes.all()
    )
    inbound_boxes = await session.scalars(
        select(InboundIntakeBox)
        .join(InboundIntakeRequest)
        .outerjoin(
            StorageLocation,
            StorageLocation.id == InboundIntakeBox.storage_location_id,
        )
        .where(
            InboundIntakeBox.tenant_id == tenant_id,
            InboundIntakeRequest.tenant_id == tenant_id,
            or_(
                StorageLocation.warehouse_id == warehouse_id,
                and_(
                    InboundIntakeBox.storage_location_id.is_(None),
                    InboundIntakeRequest.warehouse_id == warehouse_id,
                ),
            ),
            code_matches(InboundIntakeBox.internal_barcode),
        )
    )
    matches.extend(
        InventoryContainerScanMatch(
            "box",
            box.id,
            inbound_box_display_code(tenant_id, box.box_number, box.internal_barcode),
        )
        for box in inbound_boxes.all()
    )
    inbound_cargo = await session.scalars(
        select(InboundIntakeCargoPlace)
        .join(InboundIntakeRequest)
        .outerjoin(
            StorageLocation,
            StorageLocation.id == InboundIntakeCargoPlace.storage_location_id,
        )
        .where(
            InboundIntakeCargoPlace.tenant_id == tenant_id,
            InboundIntakeRequest.tenant_id == tenant_id,
            or_(
                StorageLocation.warehouse_id == warehouse_id,
                and_(
                    InboundIntakeCargoPlace.storage_location_id.is_(None),
                    InboundIntakeRequest.warehouse_id == warehouse_id,
                ),
            ),
            code_matches(InboundIntakeCargoPlace.internal_barcode),
        )
    )
    matches.extend(
        InventoryContainerScanMatch(
            "cargo_place",
            place.id,
            f"ГМ-{place.place_number:06d}",
        )
        for place in inbound_cargo.all()
    )
    unique = {(match.kind, match.id): match for match in matches}
    if not unique:
        raise InventoryContainerScanError("container_scan_not_found")
    if len(unique) > 1:
        raise InventoryContainerScanError("container_scan_ambiguous")
    return next(iter(unique.values()))


async def validate_container(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    container_kind: ContainerKind,
    container_id: uuid.UUID,
) -> None:
    if container_kind == "pallet":
        found_id = await session.scalar(
            select(Pallet.id).with_for_update(read=True, of=Pallet).where(
                Pallet.id == container_id,
                Pallet.tenant_id == tenant_id,
                Pallet.warehouse_id == warehouse_id,
                Pallet.disbanded_at.is_(None),
            )
        )
    elif container_kind == "cargo_place":
        found_id = await session.scalar(
            select(WarehouseBox.id).with_for_update(read=True, of=WarehouseBox).where(
                WarehouseBox.id == container_id,
                WarehouseBox.tenant_id == tenant_id,
                WarehouseBox.warehouse_id == warehouse_id,
                WarehouseBox.container_kind == "cargo_place",
            )
        )
        if found_id is None:
            found_id = await session.scalar(
                select(InboundIntakeCargoPlace.id)
                .join(
                    InboundIntakeRequest,
                    InboundIntakeRequest.id == InboundIntakeCargoPlace.request_id,
                )
                .outerjoin(
                    StorageLocation,
                    StorageLocation.id
                    == InboundIntakeCargoPlace.storage_location_id,
                )
                .where(
                    InboundIntakeCargoPlace.id == container_id,
                    InboundIntakeCargoPlace.tenant_id == tenant_id,
                    InboundIntakeRequest.tenant_id == tenant_id,
                    or_(
                        StorageLocation.warehouse_id == warehouse_id,
                        and_(
                            InboundIntakeCargoPlace.storage_location_id.is_(None),
                            InboundIntakeRequest.warehouse_id == warehouse_id,
                        ),
                    ),
                )
            )
    else:
        found_id = await session.scalar(
            select(WarehouseBox.id).with_for_update(read=True, of=WarehouseBox).where(
                WarehouseBox.id == container_id,
                WarehouseBox.tenant_id == tenant_id,
                WarehouseBox.warehouse_id == warehouse_id,
                WarehouseBox.container_kind == "box",
            )
        )
        if found_id is None:
            found_id = await session.scalar(
                select(InboundIntakeBox.id)
                .join(
                    InboundIntakeRequest,
                    InboundIntakeRequest.id == InboundIntakeBox.request_id,
                )
                .outerjoin(
                    StorageLocation,
                    StorageLocation.id == InboundIntakeBox.storage_location_id,
                )
                .where(
                    InboundIntakeBox.id == container_id,
                    InboundIntakeBox.tenant_id == tenant_id,
                    InboundIntakeRequest.tenant_id == tenant_id,
                    or_(
                        StorageLocation.warehouse_id == warehouse_id,
                        and_(
                            InboundIntakeBox.storage_location_id.is_(None),
                            InboundIntakeRequest.warehouse_id == warehouse_id,
                        ),
                    ),
                )
            )
    if found_id is None:
        msg = "container not found"
        raise ValueError(msg)
