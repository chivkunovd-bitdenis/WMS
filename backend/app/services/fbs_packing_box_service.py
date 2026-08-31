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
from app.models.fbs_wb_operation import WB_OPERATION_STATE_FAILED
from app.models.warehouse_box import WarehouseBox
from app.services import fbs_shipment_pvz_service as pvz_svc
from app.services.fbs_supply_reconcile_service import get_cargo_operation_by_idempotency


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
    # Packaging remains optional for WB.  An unpacked order must not become a
    # dead-end merely because boxes were already created in distribution mode:
    # the unchanged UI only offers packed orders for manual box assignment.
    # If the operator did record packaging, that packed order still has to be
    # assigned unless the durable "without distribution" mode was selected.
    assignment_required_order_ids = {
        order.id for order in orders if order.pack_status == PACK_STATUS_PACKED
    }
    if not assignment_required_order_ids or without_distribution:
        return DeliveryBoxReadiness(bool(boxes), without_distribution, frozenset())
    assigned_order_ids = set(
        (
            await session.scalars(
                select(FbsPackingBoxItem.fbs_order_id)
                .join(FbsPackingBox, FbsPackingBox.id == FbsPackingBoxItem.box_id)
                .where(
                    FbsPackingBoxItem.tenant_id == tenant_id,
                    FbsPackingBox.supply_id == supply_id,
                    FbsPackingBoxItem.fbs_order_id.in_(assignment_required_order_ids),
                )
            )
        ).all()
    )
    return DeliveryBoxReadiness(
        has_physical_boxes=bool(boxes),
        without_distribution=without_distribution,
        unassigned_packed_order_ids=frozenset(
            assignment_required_order_ids - assigned_order_ids
        ),
    )


async def create_boxes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    count: int,
    idempotency_key: str,
    http_client: httpx.AsyncClient | None = None,
    *,
    actor_user_id: uuid.UUID | None,
    without_distribution: bool = False,
) -> list[FbsPackingBox]:
    if not idempotency_key.strip():
        raise FbsPackingBoxError("missing_idempotency_key")
    supply = await _get_supply(session, tenant_id, supply_id, for_update=True)
    _assert_supply_mutable(supply)
    if supply.marketplace == "ozon":
        raise FbsPackingBoxError("ozon_boxes_managed_automatically")
    # The mode now belongs to the supply.  Keep the complete API idempotency
    # key on every newly created box; a client key is never a mode marker.
    stored_key = idempotency_key.strip()
    boxes = await _boxes_by_creation_key(
        session,
        tenant_id,
        supply_id,
        supply.seller_id,
        stored_key,
    )
    wb_operation_key = await _cargo_operation_key_for_retry(
        session, supply.seller_id, stored_key
    )
    created_box_ids: list[uuid.UUID] = []
    created_warehouse_box_ids: list[uuid.UUID] = []
    enabled_without_distribution_now = False
    if boxes:
        if len(boxes) != count or any(
            box.created_without_distribution != without_distribution for box in boxes
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
            enabled_without_distribution_now = True
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
                created_without_distribution=without_distribution,
            )
            session.add(box)
            boxes.append(box)
        await session.flush()
        created_box_ids = [box.id for box in boxes]
        created_warehouse_box_ids = [box.warehouse_box_id for box in boxes]

    # A cargo place is registered with WB for every box, regardless of
    # delivery_type (see module docstring).
    if http_client is None:
        raise FbsPackingBoxError("pvz_http_client_required")
    try:
        await _link_or_create_cargo_places(
            session,
            tenant_id,
            supply,
            boxes,
            wb_operation_key,
            http_client,
            actor_user_id=actor_user_id,
        )
    except FbsPackingBoxError as exc:
        if exc.code == "box_create_rejected_by_wb" and created_box_ids:
            # The WB operation service commits definitive failures so its audit row
            # survives the HTTP rollback. That commit also makes the just-created
            # local boxes visible; remove only this attempt in a compensating
            # transaction, leaving the failed WB journal entry intact.
            await session.execute(
                delete(FbsPackingBox)
                .where(FbsPackingBox.id.in_(created_box_ids))
                .execution_options(synchronize_session=False)
            )
            await session.execute(
                delete(WarehouseBox)
                .where(WarehouseBox.id.in_(created_warehouse_box_ids))
                .execution_options(synchronize_session=False)
            )
            if enabled_without_distribution_now:
                compensated_supply = await _get_supply(
                    session, tenant_id, supply_id, for_update=True
                )
                compensated_supply.boxes_without_distribution_at = None
                compensated_supply.boxes_without_distribution_by_user_id = None
            await session.commit()
        raise
    return await _load_boxes(session, tenant_id, supply_id)


async def _cargo_operation_key_for_retry(
    session: AsyncSession,
    seller_id: uuid.UUID,
    operator_key: str,
) -> str:
    """Continue an uncertain retry and advance only past definitive WB 409s."""
    candidate = operator_key
    seen: set[str] = set()
    while candidate not in seen:
        seen.add(candidate)
        operation = await get_cargo_operation_by_idempotency(session, seller_id, candidate)
        if operation is None:
            return candidate
        if not (
            operation.state == WB_OPERATION_STATE_FAILED
            and operation.error_code in {"wb_upstream_error_409", "wb_business_error_409"}
        ):
            # Pending/pending-confirmation must keep its exact key so the cargo
            # service reconciles instead of issuing a blind duplicate WB create.
            return candidate
        candidate = f"box-retry:{operation.id}"
    raise FbsPackingBoxError("idempotency_key_reused")


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
    if supply.marketplace == "ozon":
        if enabled and supply.boxes_without_distribution_at is not None:
            return True
        raise FbsPackingBoxError("ozon_boxes_managed_automatically")

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
    _assert_supply_mutable(supply)
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
    if supply.marketplace != "wb" and any(
        order.pack_status != PACK_STATUS_PACKED for order in orders.values()
    ):
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


async def _supply_without_distribution(session: AsyncSession, supply: FbsSupply) -> bool:
    _ = session
    return supply.boxes_without_distribution_at is not None


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
        if exc.code in {"wb_upstream_error_409", "wb_business_error_409"}:
            raise FbsPackingBoxError("box_create_rejected_by_wb") from exc
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
    statement = select(FbsSupply).where(FbsSupply.id == supply_id, FbsSupply.tenant_id == tenant_id)
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
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    seller_id: uuid.UUID,
    key: str,
) -> list[FbsPackingBox]:
    exact_boxes = await _boxes_by_stored_creation_keys(session, tenant_id, supply_id, [key])
    if exact_boxes:
        return exact_boxes

    max_legacy_raw_len = CREATION_IDEMPOTENCY_KEY_MAX_LENGTH - len(WITHOUT_DISTRIBUTION_KEY_PREFIX)
    # The legacy prefix consumed part of the 128-character column and old
    # writes therefore truncated longer raw keys.  The durable WB operation
    # journal kept the complete API key, so use it to distinguish a retry of
    # that old request from a different key with the same stored prefix.
    legacy_key = key[:max_legacy_raw_len]
    legacy_boxes = await _boxes_by_stored_creation_keys(
        session,
        tenant_id,
        supply_id,
        [
            f"{WITHOUT_DISTRIBUTION_KEY_PREFIX}{legacy_key}",
            f"{RETIRED_WITHOUT_DISTRIBUTION_KEY_PREFIX}{legacy_key}",
        ],
    )
    if not legacy_boxes:
        return []
    # A prefix alone is ambiguous: it can be an ordinary client key.  Only the
    # durable WB operation for the unprefixed client key proves this was a
    # pre-0094 marker and keeps its old retry addressable.
    operation = await get_cargo_operation_by_idempotency(session, seller_id, key)
    if operation is None or operation.local_entity_id != supply_id:
        return []
    return legacy_boxes


async def _boxes_by_stored_creation_keys(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    keys: list[str],
) -> list[FbsPackingBox]:
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
