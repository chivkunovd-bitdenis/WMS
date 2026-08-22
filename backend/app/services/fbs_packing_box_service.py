"""Physical FBS boxes.  A box is local; when a WB HTTP client is supplied, it
also gets a linked WB cargo place (trbx) — for any delivery_type, not only
PVZ. See app/services/fbs_shipment_pvz_service.py module docstring for why
the old PVZ-only restriction was dropped on 2026-08-17."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_order import PACK_STATUS_PACKED, FbsOrder
from app.models.fbs_packing_box import FbsPackingBox, FbsPackingBoxItem
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_DONE,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FbsSupply,
)
from app.models.fbs_trbx import FbsTrbx
from app.models.warehouse_box import WarehouseBox
from app.services import fbs_shipment_pvz_service as pvz_svc


class FbsPackingBoxError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class DeliveryBoxReadiness:
    has_physical_boxes: bool
    without_distribution: bool
    unassigned_packed_order_ids: frozenset[uuid.UUID]


WITHOUT_DISTRIBUTION_KEY_PREFIX = "no-distribution:"
RETIRED_WITHOUT_DISTRIBUTION_KEY_PREFIX = "retired-no-dist:"
CREATION_IDEMPOTENCY_KEY_MAX_LENGTH = 128


async def get_delivery_box_readiness(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    orders: list[FbsOrder],
) -> DeliveryBoxReadiness:
    """Return the durable box membership gate used by preflight and delivery."""
    boxes = list(
        (
            await session.scalars(
                select(FbsPackingBox).where(
                    FbsPackingBox.tenant_id == tenant_id,
                    FbsPackingBox.supply_id == supply_id,
                )
            )
        ).all()
    )
    supply = await _get_supply(session, tenant_id, supply_id)
    without_distribution = await _supply_without_distribution(session, supply)
    packed_order_ids = {order.id for order in orders if order.pack_status == PACK_STATUS_PACKED}
    if not packed_order_ids or without_distribution:
        return DeliveryBoxReadiness(bool(boxes), without_distribution, frozenset())
    assigned_order_ids = set(
        (
            await session.scalars(
                select(FbsPackingBoxItem.fbs_order_id)
                .join(FbsPackingBox, FbsPackingBox.id == FbsPackingBoxItem.box_id)
                .where(
                    FbsPackingBoxItem.tenant_id == tenant_id,
                    FbsPackingBox.supply_id == supply_id,
                    FbsPackingBoxItem.fbs_order_id.in_(packed_order_ids),
                )
            )
        ).all()
    )
    return DeliveryBoxReadiness(
        has_physical_boxes=bool(boxes),
        without_distribution=without_distribution,
        unassigned_packed_order_ids=frozenset(packed_order_ids - assigned_order_ids),
    )


async def create_boxes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    count: int,
    idempotency_key: str,
    http_client: httpx.AsyncClient | None = None,
    *,
    actor_user_id: uuid.UUID | None = None,
    without_distribution: bool = False,
) -> list[FbsPackingBox]:
    if not idempotency_key.strip():
        raise FbsPackingBoxError("missing_idempotency_key")
    supply = await _get_supply(session, tenant_id, supply_id, for_update=True)
    _assert_supply_mutable(supply)
    stored_key = _stored_creation_key(idempotency_key, without_distribution=without_distribution)
    boxes = await _boxes_by_creation_key(session, tenant_id, supply_id, stored_key)
    if boxes:
        if len(boxes) != count:
            raise FbsPackingBoxError("idempotency_key_reused")
        if not _creation_key_matches_without_distribution_request(
            boxes, stored_key, without_distribution
        ):
            raise FbsPackingBoxError("idempotency_key_reused")
    else:
        assigned_count = await session.scalar(
            select(func.count(FbsPackingBoxItem.id))
            .join(FbsPackingBox, FbsPackingBox.id == FbsPackingBoxItem.box_id)
            .where(
                FbsPackingBoxItem.tenant_id == tenant_id,
                FbsPackingBox.supply_id == supply_id,
            )
        )
        if without_distribution and assigned_count:
            raise FbsPackingBoxError("boxes_already_distributed")
        if without_distribution and supply.boxes_without_distribution_at is None:
            supply.boxes_without_distribution_at = datetime.now(UTC)
            supply.boxes_without_distribution_by_user_id = actor_user_id
        max_number = await session.scalar(
            select(func.max(FbsPackingBox.box_number)).where(
                FbsPackingBox.tenant_id == tenant_id,
                FbsPackingBox.supply_id == supply_id,
            )
        )
        first_number = int(max_number or 0) + 1
        for number in range(first_number, first_number + count):
            warehouse_box = WarehouseBox(
                tenant_id=tenant_id,
                warehouse_id=supply.warehouse_id,
                internal_barcode=_internal_barcode(supply_id, number),
            )
            box = FbsPackingBox(
                tenant_id=tenant_id,
                supply_id=supply_id,
                warehouse_box=warehouse_box,
                box_number=number,
                creation_idempotency_key=stored_key,
            )
            session.add(box)
            boxes.append(box)
        await session.flush()

    # A cargo place is registered with WB for every box, regardless of
    # delivery_type (see module docstring).
    if http_client is None:
        raise FbsPackingBoxError("pvz_http_client_required")
    await _link_or_create_cargo_places(
        session,
        tenant_id,
        supply,
        boxes,
        idempotency_key,
        http_client,
        actor_user_id=actor_user_id,
    )
    return await _load_boxes(session, tenant_id, supply_id)


async def set_boxes_without_distribution(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    enabled: bool,
    *,
    actor_user_id: uuid.UUID | None,
) -> bool:
    """Change the supply mode while no order is assigned to its boxes."""
    supply = await _get_supply(session, tenant_id, supply_id, for_update=True)
    _assert_supply_mutable(supply)

    assigned_count = await session.scalar(
        select(func.count(FbsPackingBoxItem.id))
        .join(FbsPackingBox, FbsPackingBox.id == FbsPackingBoxItem.box_id)
        .where(
            FbsPackingBoxItem.tenant_id == tenant_id,
            FbsPackingBox.supply_id == supply_id,
        )
    )
    if assigned_count:
        raise FbsPackingBoxError("boxes_already_distributed")

    if enabled and supply.boxes_without_distribution_at is None:
        # A legacy box prefix is only an input for compatibility.  Once the
        # mode is changed through this operation, the supply fields become
        # the durable source of truth and the audit timestamp is immutable
        # for an idempotent retry.
        supply.boxes_without_distribution_at = datetime.now(UTC)
        supply.boxes_without_distribution_by_user_id = actor_user_id
    elif not enabled:
        supply.boxes_without_distribution_at = None
        supply.boxes_without_distribution_by_user_id = None
        await _retire_legacy_without_distribution_markers(session, tenant_id, supply_id)
    await session.flush()
    return enabled


async def assign_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    box_id: uuid.UUID,
    order_ids: list[uuid.UUID],
    *,
    actor_user_id: uuid.UUID | None,
) -> None:
    supply = await _get_supply(session, tenant_id, supply_id, for_update=True)
    box = await _get_box(session, tenant_id, supply_id, box_id)
    if await _supply_without_distribution(session, supply):
        raise FbsPackingBoxError("box_without_distribution")
    if not order_ids:
        raise FbsPackingBoxError("empty_order_set")
    unique_ids = list(dict.fromkeys(order_ids))
    result = await session.execute(
        select(FbsOrder).where(
            FbsOrder.tenant_id == tenant_id,
            FbsOrder.supply_id == supply_id,
            FbsOrder.id.in_(unique_ids),
        )
    )
    orders = {order.id: order for order in result.scalars().all()}
    if len(orders) != len(unique_ids):
        raise FbsPackingBoxError("order_not_in_supply")
    if any(order.pack_status != PACK_STATUS_PACKED for order in orders.values()):
        raise FbsPackingBoxError("order_not_packed")
    assigned = await session.execute(
        select(FbsPackingBoxItem).where(
            FbsPackingBoxItem.tenant_id == tenant_id,
            FbsPackingBoxItem.fbs_order_id.in_(unique_ids),
        )
    )
    assigned_by_order = {item.fbs_order_id: item for item in assigned.scalars().all()}
    if any(item.box_id != box.id for item in assigned_by_order.values()):
        raise FbsPackingBoxError("order_already_in_box")
    for order_id in unique_ids:
        if order_id not in assigned_by_order:
            session.add(
                FbsPackingBoxItem(
                    tenant_id=tenant_id,
                    box_id=box.id,
                    fbs_order_id=order_id,
                    assigned_by_user_id=actor_user_id,
                )
            )


async def remove_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    box_id: uuid.UUID,
    order_id: uuid.UUID,
) -> None:
    await _get_box(session, tenant_id, supply_id, box_id)
    result = await session.execute(
        select(FbsPackingBoxItem).where(
            FbsPackingBoxItem.tenant_id == tenant_id,
            FbsPackingBoxItem.box_id == box_id,
            FbsPackingBoxItem.fbs_order_id == order_id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise FbsPackingBoxError("box_assignment_not_found")
    await session.delete(item)


async def clear_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    box_id: uuid.UUID,
) -> None:
    """Unassign every order currently in the box, returning them to unassigned.

    Idempotent on an already-empty box.  Forbidden once the supply has been
    handed to WB — box membership must not change after that point.
    """
    supply = await _get_supply(session, tenant_id, supply_id)
    if supply.status in {FBS_SUPPLY_STATUS_IN_DELIVERY, FBS_SUPPLY_STATUS_DONE}:
        raise FbsPackingBoxError("supply_already_delivered")
    box = await _get_box(session, tenant_id, supply_id, box_id)
    await session.execute(
        delete(FbsPackingBoxItem).where(
            FbsPackingBoxItem.tenant_id == tenant_id,
            FbsPackingBoxItem.box_id == box.id,
        )
    )
    await session.flush()
    session.expire(box, ["items"])


async def delete_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    box_id: uuid.UUID,
    idempotency_key: str,
    http_client: httpx.AsyncClient | None = None,
) -> None:
    box = await _get_box(session, tenant_id, supply_id, box_id)
    if box.items:
        raise FbsPackingBoxError("box_not_empty")
    supply = await _get_supply(session, tenant_id, supply_id)
    _assert_supply_mutable(supply)
    if box.trbx is not None:
        if http_client is None:
            raise FbsPackingBoxError("pvz_http_client_required")
        try:
            await pvz_svc.delete_cargo_places(
                session,
                tenant_id,
                supply_id,
                [box.trbx.wb_trbx_id],
                idempotency_key,
                http_client,
            )
        except pvz_svc.FbsShipmentPvzError as exc:
            raise FbsPackingBoxError(exc.code) from exc
    warehouse_box = box.warehouse_box
    await session.delete(box)
    await session.flush()
    await session.delete(warehouse_box)


async def retry_box_qr(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    box_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> None:
    box = await _get_box(session, tenant_id, supply_id, box_id)
    await _get_supply(session, tenant_id, supply_id)
    if box.trbx is None:
        raise FbsPackingBoxError("box_cargo_place_unresolved")
    try:
        # This service only fetches/caches QR assets for existing WB cargo places.
        await pvz_svc.fetch_trbx_stickers(session, tenant_id, supply_id, http_client)
    except pvz_svc.FbsShipmentPvzError as exc:
        raise FbsPackingBoxError(exc.code) from exc


async def get_boxes_for_workspace(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> list[dict[str, object]]:
    supply = await _get_supply(session, tenant_id, supply_id)
    supply_without_distribution = await _supply_without_distribution(session, supply)
    boxes = await _load_boxes(session, tenant_id, supply_id)
    return [
        {
            "id": str(box.id),
            "box_number": box.box_number,
            "barcode": box.warehouse_box.internal_barcode,
            "assigned_order_ids": [str(item.fbs_order_id) for item in box.items],
            "trbx_id": str(box.trbx_id) if box.trbx_id else None,
            "wb_trbx_id": box.trbx.wb_trbx_id if box.trbx else None,
            "qr_asset": None,
            # The supply flag is the sole current source of truth.  The
            # creation-key prefix remains readable only for migration/cleanup
            # compatibility and must not affect operator-visible state.
            "without_distribution": supply_without_distribution,
        }
        for box in boxes
    ]


def _stored_creation_key(idempotency_key: str, *, without_distribution: bool) -> str:
    key = idempotency_key.strip()
    if not without_distribution:
        return key
    max_raw_len = CREATION_IDEMPOTENCY_KEY_MAX_LENGTH - len(
        WITHOUT_DISTRIBUTION_KEY_PREFIX
    )
    return f"{WITHOUT_DISTRIBUTION_KEY_PREFIX}{key[:max_raw_len]}"


def _box_without_distribution(box: FbsPackingBox) -> bool:
    return bool(
        box.creation_idempotency_key
        and box.creation_idempotency_key.startswith(WITHOUT_DISTRIBUTION_KEY_PREFIX)
    )


def _boxes_without_distribution(boxes: list[FbsPackingBox]) -> bool:
    return bool(boxes) and any(_box_without_distribution(box) for box in boxes)


def _creation_key_matches_without_distribution_request(
    boxes: list[FbsPackingBox], stored_key: str, without_distribution: bool
) -> bool:
    if _boxes_without_distribution(boxes) == without_distribution:
        return True
    return without_distribution and all(
        box.creation_idempotency_key == _retired_legacy_creation_key(stored_key)
        for box in boxes
    )


async def _has_legacy_without_distribution_marker(
    session: AsyncSession, tenant_id: uuid.UUID, supply_id: uuid.UUID
) -> bool:
    return bool(
        await session.scalar(
            select(FbsPackingBox.id)
            .where(
                FbsPackingBox.tenant_id == tenant_id,
                FbsPackingBox.supply_id == supply_id,
                FbsPackingBox.creation_idempotency_key.startswith(
                    WITHOUT_DISTRIBUTION_KEY_PREFIX
                ),
            )
            .limit(1)
        )
    )


async def _supply_without_distribution(
    session: AsyncSession, supply: FbsSupply
) -> bool:
    if supply.boxes_without_distribution_at is not None:
        return True
    return await _has_legacy_without_distribution_marker(
        session, supply.tenant_id, supply.id
    )


async def _link_or_create_cargo_places(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
    boxes: list[FbsPackingBox],
    idempotency_key: str,
    http_client: httpx.AsyncClient,
    *,
    actor_user_id: uuid.UUID | None,
) -> None:
    await _link_existing_trbxes(session, supply.id, boxes)
    unresolved = [box for box in boxes if box.trbx_id is None]
    if not unresolved:
        return
    if len(unresolved) != len(boxes):
        raise FbsPackingBoxError("box_cargo_place_unresolved")
    drafts = [
        pvz_svc.CargoPlaceDraft(
            client_id=str(box.id),
            length_mm=None,
            width_mm=None,
            height_mm=None,
            weight_g=None,
            measurements_confirmed=True,
            packaging_box_id=box.warehouse_box_id,
        )
        for box in boxes
    ]
    try:
        await pvz_svc.create_cargo_places(
            session,
            tenant_id,
            supply.id,
            len(boxes),
            drafts,
            idempotency_key,
            http_client,
            actor_user_id=actor_user_id,
            confirmation_source="fbs_physical_box",
        )
    except pvz_svc.FbsShipmentPvzError as exc:
        await _link_existing_trbxes(session, supply.id, boxes)
        raise FbsPackingBoxError(exc.code) from exc
    await _link_existing_trbxes(session, supply.id, boxes)
    if any(box.trbx_id is None for box in boxes):
        raise FbsPackingBoxError("box_cargo_place_unresolved")


async def _link_existing_trbxes(
    session: AsyncSession, supply_id: uuid.UUID, boxes: list[FbsPackingBox]
) -> None:
    warehouse_box_ids = [box.warehouse_box_id for box in boxes]
    result = await session.execute(
        select(FbsTrbx).where(
            FbsTrbx.supply_id == supply_id,
            FbsTrbx.packaging_box_id.in_(warehouse_box_ids),
        )
    )
    trbx_by_warehouse_box = {trbx.packaging_box_id: trbx for trbx in result.scalars().all()}
    for box in boxes:
        trbx = trbx_by_warehouse_box.get(box.warehouse_box_id)
        if trbx is not None:
            box.trbx_id = trbx.id
    await session.flush()


async def _get_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> FbsSupply:
    statement = select(FbsSupply).where(
        FbsSupply.id == supply_id, FbsSupply.tenant_id == tenant_id
    )
    if for_update:
        statement = statement.with_for_update()
    result = await session.execute(statement)
    supply = result.scalar_one_or_none()
    if supply is None:
        raise FbsPackingBoxError("supply_not_found")
    return supply


async def _get_box(
    session: AsyncSession, tenant_id: uuid.UUID, supply_id: uuid.UUID, box_id: uuid.UUID
) -> FbsPackingBox:
    result = await session.execute(
        select(FbsPackingBox)
        .options(
            selectinload(FbsPackingBox.items),
            selectinload(FbsPackingBox.warehouse_box),
            selectinload(FbsPackingBox.trbx),
        )
        .where(
            FbsPackingBox.id == box_id,
            FbsPackingBox.tenant_id == tenant_id,
            FbsPackingBox.supply_id == supply_id,
        )
    )
    box = result.scalar_one_or_none()
    if box is None:
        raise FbsPackingBoxError("packing_box_not_found")
    return box


async def _boxes_by_creation_key(
    session: AsyncSession, tenant_id: uuid.UUID, supply_id: uuid.UUID, key: str
) -> list[FbsPackingBox]:
    keys = [key]
    retired_legacy_key = _retired_legacy_creation_key(key)
    if retired_legacy_key != key:
        keys.append(retired_legacy_key)
    result = await session.execute(
        select(FbsPackingBox)
        .options(selectinload(FbsPackingBox.warehouse_box), selectinload(FbsPackingBox.trbx))
        .where(
            FbsPackingBox.tenant_id == tenant_id,
            FbsPackingBox.supply_id == supply_id,
            FbsPackingBox.creation_idempotency_key.in_(keys),
        )
        .order_by(FbsPackingBox.box_number)
    )
    return list(result.scalars().all())


def _retired_legacy_creation_key(key: str) -> str:
    if not key.startswith(WITHOUT_DISTRIBUTION_KEY_PREFIX):
        return key
    raw_key = key.removeprefix(WITHOUT_DISTRIBUTION_KEY_PREFIX)
    max_raw_len = CREATION_IDEMPOTENCY_KEY_MAX_LENGTH - len(
        RETIRED_WITHOUT_DISTRIBUTION_KEY_PREFIX
    )
    return f"{RETIRED_WITHOUT_DISTRIBUTION_KEY_PREFIX}{raw_key[:max_raw_len]}"


async def _retire_legacy_without_distribution_markers(
    session: AsyncSession, tenant_id: uuid.UUID, supply_id: uuid.UUID
) -> None:
    """Keep legacy create retries addressable without retaining their old mode."""
    boxes = list(
        (
            await session.scalars(
                select(FbsPackingBox).where(
                    FbsPackingBox.tenant_id == tenant_id,
                    FbsPackingBox.supply_id == supply_id,
                    FbsPackingBox.creation_idempotency_key.like(
                        f"{WITHOUT_DISTRIBUTION_KEY_PREFIX}%"
                    ),
                )
            )
        ).all()
    )
    for box in boxes:
        assert box.creation_idempotency_key is not None
        box.creation_idempotency_key = _retired_legacy_creation_key(
            box.creation_idempotency_key
        )


async def _load_boxes(
    session: AsyncSession, tenant_id: uuid.UUID, supply_id: uuid.UUID
) -> list[FbsPackingBox]:
    result = await session.execute(
        select(FbsPackingBox)
        .options(
            selectinload(FbsPackingBox.items),
            selectinload(FbsPackingBox.warehouse_box),
            selectinload(FbsPackingBox.trbx),
        )
        .where(FbsPackingBox.tenant_id == tenant_id, FbsPackingBox.supply_id == supply_id)
        .order_by(FbsPackingBox.box_number)
    )
    return list(result.scalars().all())


def _assert_supply_mutable(supply: FbsSupply) -> None:
    if supply.status in {FBS_SUPPLY_STATUS_IN_DELIVERY, FBS_SUPPLY_STATUS_DONE}:
        raise FbsPackingBoxError("supply_not_editable")


def _internal_barcode(supply_id: uuid.UUID, box_number: int) -> str:
    return f"FBS-{str(supply_id).split('-')[0].upper()}-{box_number:03d}"
