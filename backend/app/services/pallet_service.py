"""Tenant-safe pallet grouping without a second inventory truth."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeCargoPlace,
    InboundIntakeRequest,
)
from app.models.inventory_balance import InventoryBalance
from app.models.pallet import Pallet
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox
from app.services.document_number_service import DOC_TYPE_PALLET, next_display_counter
from app.services.sorting_location_service import get_or_create_sorting_location


class PalletServiceError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


async def _load_pallet(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    pallet_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Pallet:
    stmt = select(Pallet).where(
        Pallet.id == pallet_id,
        Pallet.tenant_id == tenant_id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    pallet = (await session.execute(stmt)).scalar_one_or_none()
    if pallet is None:
        raise PalletServiceError("pallet_not_found")
    return pallet


async def _next_code_number(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    last_code = await session.scalar(
        select(func.max(Pallet.code)).where(Pallet.tenant_id == tenant_id)
    )
    legacy_next = 1
    try:
        if last_code:
            legacy_next = int(str(last_code).removeprefix("П-")) + 1
    except ValueError:
        pass
    return await next_display_counter(
        session,
        tenant_id,
        DOC_TYPE_PALLET,
        minimum_counter=legacy_next,
    )


async def create_pallet(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID,
    storage_location_id: uuid.UUID | None = None,
    free_text: str | None = None,
) -> Pallet:
    warehouse = await session.get(Warehouse, warehouse_id)
    if warehouse is None or warehouse.tenant_id != tenant_id:
        raise PalletServiceError("warehouse_not_found")
    if storage_location_id is not None:
        location = await session.get(StorageLocation, storage_location_id)
        if (
            location is None
            or location.tenant_id != tenant_id
            or location.warehouse_id != warehouse_id
        ):
            raise PalletServiceError("location_not_found")
    number = await _next_code_number(session, tenant_id)
    pallet = Pallet(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        code=f"П-{number:06d}",
        barcode=f"PLT-{uuid.uuid4().hex[:12].upper()}",
        storage_location_id=storage_location_id,
        free_text=free_text.strip() if free_text and free_text.strip() else None,
    )
    session.add(pallet)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise PalletServiceError("pallet_identifier_conflict") from exc
    await session.refresh(pallet)
    return pallet


async def list_pallets(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID | None = None,
    include_disbanded: bool = False,
) -> list[Pallet]:
    stmt = select(Pallet).where(Pallet.tenant_id == tenant_id)
    if warehouse_id is not None:
        stmt = stmt.where(Pallet.warehouse_id == warehouse_id)
    if not include_disbanded:
        stmt = stmt.where(Pallet.disbanded_at.is_(None))
    rows = await session.execute(stmt.order_by(Pallet.code.asc()))
    return list(rows.scalars().all())


async def _load_inbound_boxes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    ids: set[uuid.UUID],
) -> list[InboundIntakeBox]:
    if not ids:
        return []
    rows = await session.execute(
        select(InboundIntakeBox)
        .join(InboundIntakeRequest, InboundIntakeRequest.id == InboundIntakeBox.request_id)
        .where(
            InboundIntakeBox.id.in_(ids),
            InboundIntakeBox.tenant_id == tenant_id,
            InboundIntakeRequest.tenant_id == tenant_id,
            InboundIntakeRequest.warehouse_id == warehouse_id,
        )
        .with_for_update()
    )
    boxes = list(rows.scalars().all())
    if {box.id for box in boxes} != ids:
        raise PalletServiceError("box_not_found")
    return boxes


async def _load_cargo_places(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    ids: set[uuid.UUID],
) -> list[InboundIntakeCargoPlace]:
    if not ids:
        return []
    rows = await session.execute(
        select(InboundIntakeCargoPlace)
        .join(
            InboundIntakeRequest,
            InboundIntakeRequest.id == InboundIntakeCargoPlace.request_id,
        )
        .where(
            InboundIntakeCargoPlace.id.in_(ids),
            InboundIntakeCargoPlace.tenant_id == tenant_id,
            InboundIntakeRequest.tenant_id == tenant_id,
            InboundIntakeRequest.warehouse_id == warehouse_id,
        )
        .with_for_update()
    )
    places = list(rows.scalars().all())
    if {place.id for place in places} != ids:
        raise PalletServiceError("cargo_place_not_found")
    return places


async def _load_warehouse_boxes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    ids: set[uuid.UUID],
) -> list[WarehouseBox]:
    if not ids:
        return []
    rows = await session.execute(
        select(WarehouseBox)
        .where(
            WarehouseBox.id.in_(ids),
            WarehouseBox.tenant_id == tenant_id,
            WarehouseBox.warehouse_id == warehouse_id,
        )
        .with_for_update()
    )
    boxes = list(rows.scalars().all())
    if {box.id for box in boxes} != ids:
        raise PalletServiceError("box_not_found")
    return boxes


async def _move_container_balances(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    refs: Iterable[tuple[str, uuid.UUID]],
    destination_location_id: uuid.UUID,
) -> None:
    container_refs = list(refs)
    if not container_refs:
        return
    predicates = [
        and_(
            InventoryBalance.container_kind == kind,
            InventoryBalance.container_id == container_id,
        )
        for kind, container_id in container_refs
    ]
    result = await session.execute(
        select(InventoryBalance, StorageLocation)
        .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            or_(*predicates),
        )
        .with_for_update()
    )
    rows = list(result.all())
    if any(
        location.tenant_id != tenant_id or location.warehouse_id != warehouse_id
        for _balance, location in rows
    ):
        raise PalletServiceError("container_wrong_warehouse")

    grouped: dict[tuple[uuid.UUID, str, uuid.UUID], list[InventoryBalance]] = {}
    for balance, _location in rows:
        if balance.container_kind is None or balance.container_id is None:
            continue
        key = (balance.product_id, balance.container_kind, balance.container_id)
        grouped.setdefault(key, []).append(balance)

    for balances in grouped.values():
        target = next(
            (
                row
                for row in balances
                if row.storage_location_id == destination_location_id
            ),
            balances[0],
        )
        quantity = sum(int(row.quantity) for row in balances)
        unpacked = sum(int(row.quantity_unpacked) for row in balances)
        packed = sum(int(row.quantity_packed) for row in balances)
        for row in balances:
            if row is not target:
                await session.delete(row)
        await session.flush()
        target.storage_location_id = destination_location_id
        target.quantity = quantity
        target.quantity_unpacked = unpacked
        target.quantity_packed = packed
        target.updated_at = datetime.now(UTC)
        await session.flush()


async def _detach_direct_pallet_balances(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    pallet_id: uuid.UUID,
    sorting_location_id: uuid.UUID,
) -> None:
    rows = list(
        (
            await session.execute(
                select(InventoryBalance)
                .where(
                    InventoryBalance.tenant_id == tenant_id,
                    InventoryBalance.container_kind == "pallet",
                    InventoryBalance.container_id == pallet_id,
                )
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    for source in rows:
        target = (
            await session.execute(
                select(InventoryBalance)
                .where(
                    InventoryBalance.tenant_id == tenant_id,
                    InventoryBalance.product_id == source.product_id,
                    InventoryBalance.storage_location_id == sorting_location_id,
                    InventoryBalance.container_kind.is_(None),
                    InventoryBalance.container_id.is_(None),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if target is None:
            source.storage_location_id = sorting_location_id
            source.container_kind = None
            source.container_id = None
            source.updated_at = datetime.now(UTC)
            await session.flush()
            continue
        target.quantity += source.quantity
        target.quantity_unpacked += source.quantity_unpacked
        target.quantity_packed += source.quantity_packed
        target.updated_at = datetime.now(UTC)
        await session.delete(source)
        await session.flush()


async def combine_into_pallet(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    pallet_id: uuid.UUID,
    *,
    inbound_box_ids: Iterable[uuid.UUID] = (),
    cargo_place_ids: Iterable[uuid.UUID] = (),
    warehouse_box_ids: Iterable[uuid.UUID] = (),
) -> Pallet:
    pallet = await _load_pallet(session, tenant_id, pallet_id, for_update=True)
    if pallet.disbanded_at is not None:
        raise PalletServiceError("pallet_disbanded")
    inbound_ids = set(inbound_box_ids)
    cargo_ids = set(cargo_place_ids)
    warehouse_ids = set(warehouse_box_ids)
    if not inbound_ids and not cargo_ids and not warehouse_ids:
        raise PalletServiceError("containers_required")

    inbound_boxes = await _load_inbound_boxes(
        session, tenant_id, pallet.warehouse_id, inbound_ids
    )
    cargo_places = await _load_cargo_places(
        session, tenant_id, pallet.warehouse_id, cargo_ids
    )
    warehouse_boxes = await _load_warehouse_boxes(
        session, tenant_id, pallet.warehouse_id, warehouse_ids
    )
    destination = pallet.storage_location_id
    if destination is None:
        sorting = await get_or_create_sorting_location(
            session, tenant_id, pallet.warehouse_id
        )
        destination = sorting.id

    for box in inbound_boxes:
        box.pallet_id = pallet.id
    for place in cargo_places:
        place.pallet_id = pallet.id
    for warehouse_box in warehouse_boxes:
        warehouse_box.pallet_id = pallet.id
        warehouse_box.storage_location_id = pallet.storage_location_id
    await _move_container_balances(
        session,
        tenant_id,
        pallet.warehouse_id,
        refs=[
            *(("box", box.id) for box in inbound_boxes),
            *((box.container_kind, box.id) for box in warehouse_boxes),
            *(("cargo_place", place.id) for place in cargo_places),
        ],
        destination_location_id=destination,
    )
    await session.commit()
    await session.refresh(pallet)
    return pallet


async def disband_pallet(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    pallet_id: uuid.UUID,
) -> Pallet:
    pallet = await _load_pallet(session, tenant_id, pallet_id, for_update=True)
    if pallet.disbanded_at is not None:
        raise PalletServiceError("pallet_disbanded")
    sorting = await get_or_create_sorting_location(
        session, tenant_id, pallet.warehouse_id
    )
    inbound_boxes = list(
        (
            await session.execute(
                select(InboundIntakeBox).where(
                    InboundIntakeBox.tenant_id == tenant_id,
                    InboundIntakeBox.pallet_id == pallet.id,
                )
            )
        )
        .scalars()
        .all()
    )
    cargo_places = list(
        (
            await session.execute(
                select(InboundIntakeCargoPlace).where(
                    InboundIntakeCargoPlace.tenant_id == tenant_id,
                    InboundIntakeCargoPlace.pallet_id == pallet.id,
                )
            )
        )
        .scalars()
        .all()
    )
    warehouse_boxes = list(
        (
            await session.execute(
                select(WarehouseBox).where(
                    WarehouseBox.tenant_id == tenant_id,
                    WarehouseBox.pallet_id == pallet.id,
                )
            )
        )
        .scalars()
        .all()
    )
    await _move_container_balances(
        session,
        tenant_id,
        pallet.warehouse_id,
        refs=[
            *(("box", box.id) for box in inbound_boxes),
            *((box.container_kind, box.id) for box in warehouse_boxes),
            *(("cargo_place", place.id) for place in cargo_places),
        ],
        destination_location_id=sorting.id,
    )
    await _detach_direct_pallet_balances(
        session, tenant_id, pallet.id, sorting.id
    )
    for box in inbound_boxes:
        box.pallet_id = None
    for place in cargo_places:
        place.pallet_id = None
    for warehouse_box in warehouse_boxes:
        warehouse_box.pallet_id = None
        warehouse_box.storage_location_id = None
    pallet.storage_location_id = None
    pallet.disbanded_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(pallet)
    return pallet
