"""Server-side FBS pick scans: location → product → sorting transfer."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_order import (
    FBS_ORDER_STATUS_CANCELLED,
    PACK_STATUS_PACKED,
    PICK_STATUS_PENDING,
    PICK_STATUS_PICKED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
    FbsOrderProduct,
    FbsOrderProductPick,
    FbsOrderReservation,
)
from app.models.fbs_order_pick import (
    PICK_EVENT_PICKED,
    PICK_EVENT_UNDONE,
    FbsOrderPick,
    FbsOrderPickEvent,
)
from app.models.fbs_supply import FbsSupply
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.models.user import User
from app.services import inventory_service
from app.services import pick_option_location_service as pick_location_svc
from app.services.fbs_cancelled_after_pack_service import (
    cancelled_operation_message,
    order_belonged_to_supply,
)
from app.services.fbs_workspace_service import FbsWorkspaceError, get_supply_workspace
from app.services.operation_fact_service import record_fbs_pick
from app.services.pick_option_location_service import PickOptionLocation
from app.services.sorting_location_service import (
    get_or_create_sorting_location,
)


@dataclass
class FbsPickingError(Exception):
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False
    http_status: int = 409

    def __post_init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True)
class PickOptionProduct:
    product_id: uuid.UUID
    sku_code: str
    product_name: str
    planned_qty: int
    picked_qty: int
    locations: list[PickOptionLocation]


def _planned_qty_by_product(supply: FbsSupply) -> dict[uuid.UUID, int]:
    planned: dict[uuid.UUID, int] = {}
    for order in supply.orders:
        if order.product_positions:
            for position in order.product_positions:
                if position.product_id is not None:
                    planned[position.product_id] = (
                        planned.get(position.product_id, 0) + int(position.quantity)
                    )
            continue
        if order.product_id is not None:
            planned[order.product_id] = planned.get(order.product_id, 0) + 1
    return planned


async def _picked_qty_by_product_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> dict[tuple[uuid.UUID, uuid.UUID], int]:
    picked: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
    wb_rows = await session.execute(
        select(
            FbsOrderPick.product_id,
            FbsOrderPick.source_storage_location_id,
            func.count(FbsOrderPick.id),
        )
        .where(
            FbsOrderPick.tenant_id == tenant_id,
            FbsOrderPick.fbs_supply_id == supply_id,
            FbsOrderPick.undone_at.is_(None),
        )
        .group_by(
            FbsOrderPick.product_id,
            FbsOrderPick.source_storage_location_id,
        )
    )
    for product_id, location_id, quantity in wb_rows.all():
        picked[(product_id, location_id)] = int(quantity)

    position_rows = await session.execute(
        select(
            FbsOrderProductPick.product_id,
            FbsOrderProductPick.source_storage_location_id,
            func.count(FbsOrderProductPick.id),
        )
        .where(
            FbsOrderProductPick.tenant_id == tenant_id,
            FbsOrderProductPick.fbs_supply_id == supply_id,
            FbsOrderProductPick.undone_at.is_(None),
        )
        .group_by(
            FbsOrderProductPick.product_id,
            FbsOrderProductPick.source_storage_location_id,
        )
    )
    for product_id, location_id, quantity in position_rows.all():
        key = (product_id, location_id)
        picked[key] = picked.get(key, 0) + int(quantity)
    return picked


async def get_pick_options(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> list[PickOptionProduct]:
    """Return product-first FBS picking options with source-cell progress."""
    supply = await _load_supply(session, tenant_id, supply_id)
    planned = _planned_qty_by_product(supply)
    if not planned:
        return []

    product_ids = list(planned)
    products = await _load_products(session, tenant_id, product_ids)
    picked_by_location = await _picked_qty_by_product_location(
        session, tenant_id, supply.id
    )
    picked_by_product: dict[uuid.UUID, int] = {}
    for (product_id, _location_id), quantity in picked_by_location.items():
        picked_by_product[product_id] = picked_by_product.get(product_id, 0) + quantity

    try:
        locations_by_product = await pick_location_svc.list_pick_option_locations(
            session,
            tenant_id,
            supply.warehouse_id,
            product_ids,
            picked_by_location,
        )
    except pick_location_svc.PickOptionLocationError as exc:
        raise FbsPickingError(
            exc.code,
            "Неконсистентная ссылка на складскую тару.",
            http_status=409,
        ) from exc

    return [
        PickOptionProduct(
            product_id=product_id,
            sku_code=product.sku_code,
            product_name=product.name,
            planned_qty=planned[product_id],
            picked_qty=picked_by_product.get(product_id, 0),
            locations=locations_by_product[product_id],
        )
        for product_id, product in sorted(
            products.items(), key=lambda item: (item[1].sku_code, str(item[0]))
        )
    ]


async def scan_pick_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    location_barcode: str,
) -> dict[str, Any]:
    supply = await _load_supply(session, tenant_id, supply_id)
    location = await _resolve_storage_location(
        session,
        tenant_id,
        warehouse_id=supply.warehouse_id,
        location_barcode=location_barcode,
    )
    if location is None:
        raise FbsPickingError(
            "wrong_location",
            "Ячейка не найдена на складе поставки.",
            http_status=404,
        )
    # Зона сортировки — такое же место хранения для подбора ФБС.
    # Она входит в доступное: `fbs_available_qty_by_product` суммирует storage и sorting.
    # Запрещать подбор оттуда нельзя, иначе публикуем в WB остаток,
    # который оператор физически не может собрать.
    return await _pick_location_payload(session, tenant_id, supply, location)


async def select_pick_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    location_id: uuid.UUID,
) -> dict[str, Any]:
    """Return manual-pick choices for a concrete storage-location UUID."""
    supply = await _load_supply(session, tenant_id, supply_id)
    location = await session.scalar(
        select(StorageLocation)
        .options(selectinload(StorageLocation.warehouse))
        .where(
            StorageLocation.id == location_id,
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.warehouse_id == supply.warehouse_id,
        )
    )
    if location is None:
        raise FbsPickingError(
            "wrong_location",
            "Ячейка не принадлежит складу поставки.",
            http_status=404,
        )
    return await _pick_location_payload(session, tenant_id, supply, location)


async def _pick_location_payload(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
    location: StorageLocation,
) -> dict[str, Any]:

    pending_by_product = _pending_positions_by_product(supply.orders)
    product_ids = list(pending_by_product.keys())
    products = await _load_products(session, tenant_id, product_ids)

    expected: list[dict[str, Any]] = []
    for product_id, positions in pending_by_product.items():
        product = products.get(product_id)
        if product is None:
            continue
        available = await inventory_service.available_quantity_at_location(
            session,
            tenant_id,
            product_id,
            location.id,
        )
        if available <= 0:
            continue
        remaining_units = sum(
            position.quantity - position.picked_quantity for _, position in positions
        )
        expected.append(
            {
                "product_id": str(product_id),
                "name": product.name,
                "barcode": product.wb_barcode or positions[0][0].wb_barcode,
                "remaining_qty": min(remaining_units, available),
                "nearest_deadline_at": min(order.deadline_at for order, _ in positions).isoformat(),
            }
        )
    expected.sort(key=lambda row: row["nearest_deadline_at"])

    warehouse = location.warehouse
    return {
        "id": str(location.id),
        "code": location.code,
        "warehouse_id": str(location.warehouse_id),
        "warehouse_name": warehouse.name if warehouse else "Склад",
        "expected_products": expected,
    }


async def scan_pick_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    location_id: uuid.UUID,
    product_barcode: str,
    idempotency_key: str,
    actor: User,
    order_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    existing = await _find_pick_by_scan_idempotency(session, tenant_id, supply_id, idempotency_key)
    if existing is not None:
        return await get_supply_workspace(session, tenant_id, supply_id)

    supply = await _load_supply(session, tenant_id, supply_id)
    if order_id is not None:
        requested_order = await session.get(FbsOrder, order_id)
        if (
            requested_order is not None
            and requested_order.tenant_id == tenant_id
            and requested_order.status == FBS_ORDER_STATUS_CANCELLED
            and await order_belonged_to_supply(session, requested_order, supply)
        ):
            raise FbsPickingError(
                "order_cancelled",
                cancelled_operation_message(requested_order, "подбирать нельзя"),
                context={"order_id": str(requested_order.id)},
            )
    if supply.marketplace == "ozon":
        existing_position_pick = await session.scalar(
            select(FbsOrderProductPick.id).where(
                FbsOrderProductPick.tenant_id == tenant_id,
                FbsOrderProductPick.fbs_supply_id == supply_id,
                FbsOrderProductPick.scan_idempotency_key == idempotency_key,
                FbsOrderProductPick.undone_at.is_(None),
            )
        )
        if existing_position_pick is not None:
            return await get_supply_workspace(session, tenant_id, supply_id)
    location = await session.get(StorageLocation, location_id)
    if (
        location is None
        or location.tenant_id != tenant_id
        or location.warehouse_id != supply.warehouse_id
    ):
        raise FbsPickingError(
            "wrong_location",
            "Ячейка не принадлежит складу поставки.",
        )
    product = (
        await session.get(Product, product_id)
        if product_id is not None
        else await _resolve_product_for_supply(
            session,
            tenant_id,
            supply,
            product_barcode=product_barcode,
        )
    )
    if product is None or product.tenant_id != tenant_id:
        raise FbsPickingError(
            "wrong_product",
            "Товар не найден по штрихкоду в этой поставке.",
        )
    if product.seller_id != supply.seller_id:
        raise FbsPickingError(
            "seller_stock_mismatch",
            "Товар принадлежит другому селлеру.",
            context={"product_id": str(product.id), "seller_id": str(product.seller_id)},
        )

    eligible_positions = _eligible_positions_for_product(supply.orders, product.id)
    eligible_orders = _eligible_orders_for_product(supply.orders, product.id)
    if supply.marketplace == "ozon" and not eligible_positions:
        raise FbsPickingError(
            "product_not_in_supply",
            "Товар не входит в состав поставки или уже подобран.",
            context={"product_id": str(product.id)},
        )
    if supply.marketplace != "ozon" and not eligible_orders:
        cancelled_order = next(
            (
                order
                for order in supply.orders
                if order.product_id == product.id and order.status == FBS_ORDER_STATUS_CANCELLED
            ),
            None,
        )
        if cancelled_order is not None:
            raise FbsPickingError(
                "order_cancelled",
                cancelled_operation_message(cancelled_order, "подбирать нельзя"),
                context={"order_id": str(cancelled_order.id)},
            )
        raise FbsPickingError(
            "product_not_in_supply",
            "Товар не входит в состав поставки или уже подобран.",
            context={"product_id": str(product.id)},
        )

    target_order: FbsOrder | None = None
    target_position: FbsOrderProduct | None = None
    if supply.marketplace == "ozon":
        if order_id is not None:
            matched = next(
                (
                    (order, position)
                    for order, position in eligible_positions
                    if order.id == order_id
                ),
                None,
            )
            if matched is None:
                raise FbsPickingError(
                    "product_not_in_supply",
                    "Заказ не относится к этому товару в поставке.",
                    context={"order_id": str(order_id), "product_id": str(product.id)},
                )
            target_order, target_position = matched
        else:
            target_order, target_position = min(
                eligible_positions, key=lambda row: row[0].deadline_at
            )
    elif order_id is not None:
        target_order = next((o for o in eligible_orders if o.id == order_id), None)
        if target_order is None:
            picked = any(
                o.id == order_id and o.pick_status == PICK_STATUS_PICKED for o in supply.orders
            )
            if picked:
                raise FbsPickingError(
                    "order_already_picked",
                    "Заказ уже подобран.",
                    context={"order_id": str(order_id)},
                )
            raise FbsPickingError(
                "product_not_in_supply",
                "Заказ не относится к этому товару в поставке.",
                context={"order_id": str(order_id), "product_id": str(product.id)},
            )
    else:
        target_order = min(eligible_orders, key=lambda o: o.deadline_at)

    assert target_order is not None
    if target_order.pack_status == PACK_STATUS_PACKED:
        raise FbsPickingError(
            "order_already_packed",
            "Подбор недоступен после упаковки заказа.",
            context={"order_id": str(target_order.id)},
        )

    available = await inventory_service.available_quantity_at_location(
        session,
        tenant_id,
        product.id,
        location.id,
    )
    sorting_location = await get_or_create_sorting_location(session, tenant_id, supply.warehouse_id)
    movement_id: uuid.UUID | None = None
    if available >= 1 and location.id != sorting_location.id:
        try:
            transfer_group_id = await inventory_service.transfer_on_hand_between_locations(
                session,
                tenant_id,
                from_storage_location_id=location.id,
                to_storage_location_id=sorting_location.id,
                product_id=product.id,
                quantity=1,
                actor_user_id=actor.id,
            )
        except ValueError as exc:
            if str(exc) == "insufficient stock":
                raise FbsPickingError(
                    "insufficient_unpacked",
                    "Недостаточно неупакованного остатка в ячейке.",
                    context={
                        "order_id": str(target_order.id),
                        "product_id": str(product.id),
                        "location_id": str(location.id),
                        "location_code": location.code,
                        "requested": 1,
                        "available": 0,
                        "recommended_action": (
                            "Проверьте остаток в другой ячейке или пополните склад."
                        ),
                    },
                ) from exc
            raise
        movement_id = await inventory_service.transfer_out_movement_id(
            session, tenant_id, transfer_group_id
        )
    elif available < 1:
        movement = await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product.id,
            storage_location_id=sorting_location.id,
            quantity_delta=1,
            movement_type="fbs_order_pick",
            actor_user_id=actor.id,
        )
        if supply.marketplace != "ozon":
            await _ensure_order_reservation(session, target_order, supply)
        await session.flush()
        movement_id = movement.id
    picked_at = datetime.now(tz=UTC)
    if supply.marketplace == "ozon":
        assert target_position is not None
        position_pick = FbsOrderProductPick(
            tenant_id=tenant_id,
            order_product_id=target_position.id,
            fbs_supply_id=supply.id,
            source_storage_location_id=location.id,
            sorting_storage_location_id=sorting_location.id,
            product_id=product.id,
            inventory_movement_id=movement_id,
            scan_idempotency_key=idempotency_key,
            picked_at=picked_at,
            picked_by_user_id=actor.id,
        )
        session.add(position_pick)
        target_position.picked_quantity += 1
        if all(
            position.picked_quantity >= position.quantity
            for position in target_order.product_positions
        ):
            target_order.pick_status = PICK_STATUS_PICKED
            target_order.picked_at = picked_at
        await session.flush()
        await record_fbs_pick(
            session,
            supply=supply,
            pick=position_pick,
            source_event_id=position_pick.id,
            source_kind="fbs_order_product_pick",
            actor_user_id=actor.id,
            occurred_at=picked_at,
            product=product,
        )
        return await get_supply_workspace(session, tenant_id, supply_id)

    pick = FbsOrderPick(
        tenant_id=tenant_id,
        fbs_order_id=target_order.id,
        fbs_supply_id=supply.id,
        source_storage_location_id=location.id,
        sorting_storage_location_id=sorting_location.id,
        product_id=product.id,
        scanned_product_barcode=product_barcode,
        picked_by_user_id=actor.id,
        picked_at=picked_at,
        inventory_movement_id=movement_id,
        scan_idempotency_key=idempotency_key,
    )
    session.add(pick)
    await session.flush()
    event = FbsOrderPickEvent(
        pick_id=pick.id,
        event_type=PICK_EVENT_PICKED,
        actor_user_id=actor.id,
        idempotency_key=idempotency_key,
        source_storage_location_id=location.id,
        sorting_storage_location_id=sorting_location.id,
        inventory_movement_id=movement_id,
    )
    session.add(event)
    target_order.pick_status = PICK_STATUS_PICKED
    target_order.picked_at = picked_at
    await session.flush()
    await record_fbs_pick(
        session,
        supply=supply,
        pick=pick,
        source_event_id=event.id,
        source_kind="fbs_order_pick_event",
        actor_user_id=actor.id,
        occurred_at=picked_at,
        product=product,
    )
    return await get_supply_workspace(session, tenant_id, supply_id)


async def manual_pick_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    location_id: uuid.UUID,
    product_id: uuid.UUID,
    order_id: uuid.UUID,
    idempotency_key: str,
    actor: User,
) -> dict[str, Any]:
    """Pick the product already assigned to one explicit order without scanning."""
    existing = await _find_pick_by_scan_idempotency(session, tenant_id, supply_id, idempotency_key)
    if existing is not None:
        if (
            existing.fbs_order_id != order_id
            or existing.product_id != product_id
            or existing.source_storage_location_id != location_id
        ):
            raise FbsPickingError(
                "idempotency_key_reused",
                "Ключ идемпотентности уже использован для другого подбора.",
                context={"idempotency_key": idempotency_key},
            )
        return await get_supply_workspace(session, tenant_id, supply_id)
    return await scan_pick_product(
        session,
        tenant_id,
        supply_id,
        location_id=location_id,
        product_barcode="",
        product_id=product_id,
        order_id=order_id,
        idempotency_key=idempotency_key,
        actor=actor,
    )


async def undo_pick(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    order_id: uuid.UUID,
    *,
    idempotency_key: str,
    actor: User,
) -> dict[str, Any]:
    supply = await _load_supply(session, tenant_id, supply_id)
    order = next((o for o in supply.orders if o.id == order_id), None)
    if order is None:
        raise FbsPickingError(
            "product_not_in_supply",
            "Заказ не найден в поставке.",
            http_status=404,
            context={"order_id": str(order_id)},
        )
    if order.pack_status == PACK_STATUS_PACKED:
        raise FbsPickingError(
            "pick_undo_not_allowed",
            "Отмена подбора недоступна после упаковки.",
            context={"order_id": str(order_id)},
        )

    if supply.marketplace == "ozon":
        replayed_undo = (
            await session.execute(
                select(FbsOrderProductPick, FbsOrderProduct.order_id)
                .join(
                    FbsOrderProduct,
                    FbsOrderProduct.id == FbsOrderProductPick.order_product_id,
                )
                .where(
                    FbsOrderProductPick.tenant_id == tenant_id,
                    FbsOrderProductPick.fbs_supply_id == supply_id,
                    FbsOrderProductPick.undo_idempotency_key == idempotency_key,
                )
            )
        ).one_or_none()
        if replayed_undo is not None:
            _, replayed_order_id = replayed_undo
            if replayed_order_id != order_id:
                raise FbsPickingError(
                    "idempotency_key_reused",
                    "Ключ идемпотентности уже использован для другого подбора.",
                    context={"idempotency_key": idempotency_key},
                )
            return await get_supply_workspace(session, tenant_id, supply_id)
        position_pick = await session.scalar(
            select(FbsOrderProductPick)
            .join(
                FbsOrderProduct,
                FbsOrderProduct.id == FbsOrderProductPick.order_product_id,
            )
            .where(
                FbsOrderProductPick.tenant_id == tenant_id,
                FbsOrderProductPick.fbs_supply_id == supply_id,
                FbsOrderProduct.order_id == order.id,
                FbsOrderProductPick.undone_at.is_(None),
            )
            .order_by(FbsOrderProductPick.picked_at.desc())
        )
        if position_pick is None:
            raise FbsPickingError(
                "order_not_picked",
                "Заказ ещё не подобран.",
                context={"order_id": str(order_id)},
            )
        original_movement_type = None
        if position_pick.inventory_movement_id is not None:
            original_movement_type = await session.scalar(
                select(InventoryMovement.movement_type).where(
                    InventoryMovement.id == position_pick.inventory_movement_id,
                    InventoryMovement.tenant_id == tenant_id,
                )
            )
        if original_movement_type == "fbs_order_pick":
            await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=tenant_id,
                product_id=position_pick.product_id,
                storage_location_id=position_pick.sorting_storage_location_id,
                quantity_delta=-1,
                movement_type="fbs_order_pick_undo",
                actor_user_id=actor.id,
            )
        elif position_pick.inventory_movement_id is not None:
            await inventory_service.transfer_on_hand_between_locations(
                session,
                tenant_id,
                from_storage_location_id=position_pick.sorting_storage_location_id,
                to_storage_location_id=position_pick.source_storage_location_id,
                product_id=position_pick.product_id,
                quantity=1,
                actor_user_id=actor.id,
            )
        position_pick.undo_idempotency_key = idempotency_key
        position_pick.undone_at = datetime.now(tz=UTC)
        if position_pick.undone_by_user_id is None:
            position_pick.undone_by_user_id = actor.id
        position = await session.get(FbsOrderProduct, position_pick.order_product_id)
        assert position is not None
        position.picked_quantity = max(0, position.picked_quantity - 1)
        order.pick_status = PICK_STATUS_PENDING
        order.picked_at = None
        await session.flush()
        await record_fbs_pick(
            session,
            supply=supply,
            pick=position_pick,
            source_event_id=position_pick.id,
            source_kind="fbs_order_product_pick",
            actor_user_id=position_pick.undone_by_user_id,
            occurred_at=position_pick.undone_at,
            reversal=True,
            product=await session.get(Product, position_pick.product_id),
        )
        return await get_supply_workspace(session, tenant_id, supply_id)

    replayed_undo = await session.scalar(
        select(FbsOrderPickEvent)
        .join(FbsOrderPick, FbsOrderPick.id == FbsOrderPickEvent.pick_id)
        .where(
            FbsOrderPickEvent.event_type == PICK_EVENT_UNDONE,
            FbsOrderPickEvent.idempotency_key == idempotency_key,
            FbsOrderPick.tenant_id == tenant_id,
            FbsOrderPick.fbs_supply_id == supply_id,
        )
    )
    if replayed_undo is not None:
        replayed_pick = await session.get(FbsOrderPick, replayed_undo.pick_id)
        assert replayed_pick is not None
        if replayed_pick.fbs_order_id != order_id:
            raise FbsPickingError(
                "idempotency_key_reused",
                "Ключ идемпотентности уже использован для другого подбора.",
                context={"idempotency_key": idempotency_key},
            )
        return await get_supply_workspace(session, tenant_id, supply_id)

    pick = await _load_active_pick_for_order(session, tenant_id, order_id)
    if pick is None:
        raise FbsPickingError(
            "order_not_picked",
            "Заказ ещё не подобран.",
            context={"order_id": str(order_id)},
        )

    existing_undo = await session.scalar(
        select(FbsOrderPickEvent.id).where(
            FbsOrderPickEvent.pick_id == pick.id,
            FbsOrderPickEvent.event_type == PICK_EVENT_UNDONE,
            FbsOrderPickEvent.idempotency_key == idempotency_key,
        )
    )
    if existing_undo is not None:
        return await get_supply_workspace(session, tenant_id, supply_id)

    movement_id: uuid.UUID | None = None
    original_movement_type = None
    if pick.inventory_movement_id is not None:
        original_movement_type = await session.scalar(
            select(InventoryMovement.movement_type).where(
                InventoryMovement.id == pick.inventory_movement_id,
                InventoryMovement.tenant_id == tenant_id,
            )
        )
    try:
        if original_movement_type == "fbs_order_pick":
            movement = await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=tenant_id,
                product_id=pick.product_id,
                storage_location_id=pick.sorting_storage_location_id,
                quantity_delta=-1,
                movement_type="fbs_order_pick_undo",
                actor_user_id=actor.id,
            )
            await session.flush()
            movement_id = movement.id
        elif pick.inventory_movement_id is not None:
            transfer_group_id = await inventory_service.transfer_on_hand_between_locations(
                session,
                tenant_id,
                from_storage_location_id=pick.sorting_storage_location_id,
                to_storage_location_id=pick.source_storage_location_id,
                product_id=pick.product_id,
                quantity=1,
                actor_user_id=actor.id,
            )
            movement_id = await inventory_service.transfer_out_movement_id(
                session, tenant_id, transfer_group_id
            )
    except ValueError as exc:
        raise FbsPickingError(
            "insufficient_unpacked",
            "Недостаточно остатка в зоне сортировки для отмены подбора.",
            context={"order_id": str(order_id)},
        ) from exc
    undone_at = datetime.now(tz=UTC)
    pick.undone_at = undone_at
    undo_event = FbsOrderPickEvent(
        pick_id=pick.id,
        event_type=PICK_EVENT_UNDONE,
        actor_user_id=actor.id,
        idempotency_key=idempotency_key,
        source_storage_location_id=pick.source_storage_location_id,
        sorting_storage_location_id=pick.sorting_storage_location_id,
        inventory_movement_id=movement_id,
    )
    session.add(undo_event)
    order.pick_status = PICK_STATUS_PENDING
    order.picked_at = None
    await session.flush()
    original_event_id = await session.scalar(
        select(FbsOrderPickEvent.id)
        .where(
            FbsOrderPickEvent.pick_id == pick.id,
            FbsOrderPickEvent.event_type == PICK_EVENT_PICKED,
        )
        .order_by(FbsOrderPickEvent.created_at)
        .limit(1)
    )
    await record_fbs_pick(
        session,
        supply=supply,
        pick=pick,
        source_event_id=undo_event.id,
        source_kind="fbs_order_pick_event",
        actor_user_id=actor.id,
        occurred_at=undone_at,
        reversal=True,
        original_source_event_id=original_event_id,
        product=await session.get(Product, pick.product_id),
    )
    return await get_supply_workspace(session, tenant_id, supply_id)


async def _ensure_order_reservation(
    session: AsyncSession,
    order: FbsOrder,
    supply: FbsSupply,
) -> None:
    if order.product_id is None:
        return
    existing_id = await session.scalar(
        select(FbsOrderReservation.id).where(FbsOrderReservation.fbs_order_id == order.id)
    )
    if existing_id is not None:
        order.reserve_status = RESERVE_STATUS_RESERVED
        return
    session.add(
        FbsOrderReservation(
            tenant_id=order.tenant_id,
            fbs_order_id=order.id,
            product_id=order.product_id,
            warehouse_id=supply.warehouse_id,
            quantity=1,
        )
    )
    order.reserve_status = RESERVE_STATUS_RESERVED


async def _load_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> FbsSupply:
    stmt = (
        select(FbsSupply)
        .options(
            selectinload(FbsSupply.orders).selectinload(FbsOrder.product_positions),
            selectinload(FbsSupply.seller),
            selectinload(FbsSupply.warehouse),
        )
        .where(FbsSupply.id == supply_id, FbsSupply.tenant_id == tenant_id)
    )
    supply = (await session.execute(stmt)).scalar_one_or_none()
    if supply is None:
        raise FbsPickingError(
            "supply_not_found",
            "Поставка не найдена.",
            http_status=404,
        )
    return supply


async def _resolve_storage_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID,
    location_barcode: str,
) -> StorageLocation | None:
    stmt = (
        select(StorageLocation)
        .options(selectinload(StorageLocation.warehouse))
        .where(
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.warehouse_id == warehouse_id,
            or_(
                StorageLocation.barcode == location_barcode,
                StorageLocation.code == location_barcode,
            ),
        )
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _pending_positions_by_product(
    orders: list[FbsOrder],
) -> dict[uuid.UUID, list[tuple[FbsOrder, FbsOrderProduct]]]:
    out: dict[uuid.UUID, list[tuple[FbsOrder, FbsOrderProduct]]] = {}
    for order in orders:
        if order.status == FBS_ORDER_STATUS_CANCELLED:
            continue
        if order.product_positions:
            for position in order.product_positions:
                if position.product_id is not None and position.picked_quantity < position.quantity:
                    out.setdefault(position.product_id, []).append((order, position))
            continue
        if order.pick_status != PICK_STATUS_PICKED and order.product_id is not None:
            out.setdefault(order.product_id, []).append(
                (
                    order,
                    FbsOrderProduct(
                        product_id=order.product_id,
                        quantity=1,
                        reserved_quantity=0,
                        picked_quantity=0,
                    ),
                )
            )
    for positions in out.values():
        positions.sort(key=lambda row: row[0].deadline_at)
    return out


async def _load_products(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> dict[uuid.UUID, Product]:
    if not product_ids:
        return {}
    stmt = select(Product).where(
        Product.tenant_id == tenant_id,
        Product.id.in_(product_ids),
    )
    res = await session.execute(stmt)
    return {p.id: p for p in res.scalars().all()}


async def _resolve_product_for_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
    *,
    product_barcode: str,
) -> Product | None:
    supply_product_ids = {
        position.product_id
        for order in supply.orders
        for position in order.product_positions
        if position.product_id is not None
    } or {o.product_id for o in supply.orders if o.product_id is not None}
    if not supply_product_ids:
        return None

    stmt = select(Product).where(
        Product.tenant_id == tenant_id,
        Product.id.in_(supply_product_ids),
        or_(
            Product.wb_barcode == product_barcode,
            Product.sku_code == product_barcode,
        ),
    )
    product = (await session.execute(stmt)).scalar_one_or_none()
    if product is not None:
        return product

    order_match = next(
        (o for o in supply.orders if o.wb_barcode == product_barcode and o.product_id is not None),
        None,
    )
    if order_match is None:
        return None
    return await session.get(Product, order_match.product_id)


def _eligible_orders_for_product(
    orders: list[FbsOrder],
    product_id: uuid.UUID,
) -> list[FbsOrder]:
    return [
        o
        for o in orders
        if o.product_id == product_id
        and o.pick_status == PICK_STATUS_PENDING
        and o.status != FBS_ORDER_STATUS_CANCELLED
    ]


def _eligible_positions_for_product(
    orders: list[FbsOrder], product_id: uuid.UUID
) -> list[tuple[FbsOrder, FbsOrderProduct]]:
    return [
        (order, position)
        for order in orders
        if order.status != FBS_ORDER_STATUS_CANCELLED
        if order.pick_status == PICK_STATUS_PENDING
        for position in order.product_positions
        if position.product_id == product_id and position.picked_quantity < position.quantity
    ]


async def _find_pick_by_scan_idempotency(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    idempotency_key: str,
) -> FbsOrderPick | None:
    stmt = select(FbsOrderPick).where(
        FbsOrderPick.tenant_id == tenant_id,
        FbsOrderPick.fbs_supply_id == supply_id,
        FbsOrderPick.scan_idempotency_key == idempotency_key,
        FbsOrderPick.undone_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _load_active_pick_for_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
) -> FbsOrderPick | None:
    stmt = select(FbsOrderPick).where(
        FbsOrderPick.tenant_id == tenant_id,
        FbsOrderPick.fbs_order_id == order_id,
        FbsOrderPick.undone_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


__all__ = [
    "FbsPickingError",
    "FbsWorkspaceError",
    "get_pick_options",
    "manual_pick_product",
    "scan_pick_location",
    "scan_pick_product",
    "select_pick_location",
    "undo_pick",
]
