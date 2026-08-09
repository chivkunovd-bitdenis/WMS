"""Server-side FBS pick scans: location → product → sorting transfer."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_order import (
    PACK_STATUS_PACKED,
    PICK_STATUS_PENDING,
    PICK_STATUS_PICKED,
    FbsOrder,
)
from app.models.fbs_order_pick import (
    PICK_EVENT_PICKED,
    PICK_EVENT_UNDONE,
    FbsOrderPick,
    FbsOrderPickEvent,
)
from app.models.fbs_supply import FbsSupply
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.models.user import User
from app.services import inventory_service
from app.services.fbs_workspace_service import FbsWorkspaceError, get_supply_workspace
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

    pending_by_product = _pending_orders_by_product(supply.orders)
    product_ids = list(pending_by_product.keys())
    products = await _load_products(session, tenant_id, product_ids)

    expected: list[dict[str, Any]] = []
    for product_id, orders in pending_by_product.items():
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
        remaining_orders = len(orders)
        expected.append(
            {
                "product_id": str(product_id),
                "name": product.name,
                "barcode": product.wb_barcode or orders[0].wb_barcode,
                "remaining_qty": min(remaining_orders, available),
                "nearest_deadline_at": min(o.deadline_at for o in orders).isoformat(),
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
    existing = await _find_pick_by_scan_idempotency(
        session, tenant_id, supply_id, idempotency_key
    )
    if existing is not None:
        return await get_supply_workspace(session, tenant_id, supply_id)

    supply = await _load_supply(session, tenant_id, supply_id)
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

    eligible_orders = _eligible_orders_for_product(supply.orders, product.id)
    if not eligible_orders:
        raise FbsPickingError(
            "product_not_in_supply",
            "Товар не входит в состав поставки или уже подобран.",
            context={"product_id": str(product.id)},
        )

    target_order: FbsOrder | None = None
    if order_id is not None:
        target_order = next((o for o in eligible_orders if o.id == order_id), None)
        if target_order is None:
            picked = any(
                o.id == order_id and o.pick_status == PICK_STATUS_PICKED
                for o in supply.orders
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
    if available < 1:
        raise FbsPickingError(
            "insufficient_unpacked",
            "Недостаточно неупакованного остатка в ячейке.",
            context={
                "order_id": str(target_order.id),
                "product_id": str(product.id),
                "location_id": str(location.id),
                "location_code": location.code,
                "requested": 1,
                "available": available,
                "recommended_action": (
                    "Проверьте остаток в другой ячейке или пополните склад."
                ),
            },
        )

    sorting_location = await get_or_create_sorting_location(
        session, tenant_id, supply.warehouse_id
    )
    try:
        transfer_group_id = await inventory_service.transfer_on_hand_between_locations(
            session,
            tenant_id,
            from_storage_location_id=location.id,
            to_storage_location_id=sorting_location.id,
            product_id=product.id,
            quantity=1,
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
    picked_at = datetime.now(tz=UTC)
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
    session.add(
        FbsOrderPickEvent(
            pick_id=pick.id,
            event_type=PICK_EVENT_PICKED,
            actor_user_id=actor.id,
            idempotency_key=idempotency_key,
            source_storage_location_id=location.id,
            sorting_storage_location_id=sorting_location.id,
            inventory_movement_id=movement_id,
        )
    )
    target_order.pick_status = PICK_STATUS_PICKED
    target_order.picked_at = picked_at
    await session.flush()
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
    existing = await _find_pick_by_scan_idempotency(
        session, tenant_id, supply_id, idempotency_key
    )
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

    try:
        transfer_group_id = await inventory_service.transfer_on_hand_between_locations(
            session,
            tenant_id,
            from_storage_location_id=pick.sorting_storage_location_id,
            to_storage_location_id=pick.source_storage_location_id,
            product_id=pick.product_id,
            quantity=1,
        )
    except ValueError as exc:
        raise FbsPickingError(
            "insufficient_unpacked",
            "Недостаточно остатка в зоне сортировки для отмены подбора.",
            context={"order_id": str(order_id)},
        ) from exc

    movement_id = await inventory_service.transfer_out_movement_id(
        session, tenant_id, transfer_group_id
    )
    undone_at = datetime.now(tz=UTC)
    pick.undone_at = undone_at
    session.add(
        FbsOrderPickEvent(
            pick_id=pick.id,
            event_type=PICK_EVENT_UNDONE,
            actor_user_id=actor.id,
            idempotency_key=idempotency_key,
            source_storage_location_id=pick.source_storage_location_id,
            sorting_storage_location_id=pick.sorting_storage_location_id,
            inventory_movement_id=movement_id,
        )
    )
    order.pick_status = PICK_STATUS_PENDING
    order.picked_at = None
    await session.flush()
    return await get_supply_workspace(session, tenant_id, supply_id)


async def _load_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> FbsSupply:
    stmt = (
        select(FbsSupply)
        .options(
            selectinload(FbsSupply.orders),
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


def _pending_orders_by_product(
    orders: list[FbsOrder],
) -> dict[uuid.UUID, list[FbsOrder]]:
    out: dict[uuid.UUID, list[FbsOrder]] = {}
    for order in orders:
        if order.pick_status == PICK_STATUS_PICKED or order.product_id is None:
            continue
        out.setdefault(order.product_id, []).append(order)
    for product_orders in out.values():
        product_orders.sort(key=lambda o: o.deadline_at)
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
        o.product_id for o in supply.orders if o.product_id is not None
    }
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
        (
            o
            for o in supply.orders
            if o.wb_barcode == product_barcode and o.product_id is not None
        ),
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
        if o.product_id == product_id and o.pick_status == PICK_STATUS_PENDING
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
    "manual_pick_product",
    "scan_pick_location",
    "scan_pick_product",
    "select_pick_location",
    "undo_pick",
]
