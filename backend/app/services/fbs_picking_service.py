"""Server-side FBS pick scans and source allocation."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, cast

import sqlalchemy as sa
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document_event import (
    DOCUMENT_TYPE_FBS_SUPPLY,
    EVENT_DATA_CHANGED,
    SOURCE_USER,
    DocumentEvent,
)
from app.models.fbs_order import (
    FBS_ORDER_STATUS_CANCELLED,
    PICK_STATUS_PENDING,
    PICK_STATUS_PICKED,
    FbsOrder,
    FbsOrderProduct,
    FbsOrderProductPick,
)
from app.models.fbs_order_pick import (
    PICK_EVENT_PICKED,
    PICK_EVENT_UNDONE,
    FbsOrderPick,
    FbsOrderPickEvent,
)
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_DONE,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FbsSupply,
)
from app.models.fbs_wb_operation import (
    WB_OPERATION_STATE_CONFIRMED,
    WB_OPERATION_STATE_PENDING,
    WB_OPERATION_STATE_PENDING_CONFIRMATION,
)
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.storage_location import StorageLocation
from app.models.user import User
from app.services import inventory_service, warehouse_map_service
from app.services import pick_option_location_service as pick_location_svc
from app.services import tenant_settings_service as tenant_settings_svc
from app.services.document_event_service import record_document_event
from app.services.fbs_cancelled_after_pack_service import (
    cancelled_operation_message,
    order_belonged_to_supply,
)
from app.services.fbs_supply_reconcile_service import list_deliver_operations_for_supply
from app.services.fbs_workspace_service import FbsWorkspaceError, get_supply_workspace
from app.services.inventory_container_service import (
    ContainerKind,
    InventoryContainerScanError,
    resolve_container_scan,
    validate_container,
)
from app.services.operation_fact_service import record_fbs_pick
from app.services.ozon_fbs_process_service import OzonHandoffProgress
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
    sku_code: str | None
    product_name: str
    seller_article: str | None
    barcode: str | None
    planned_qty: int
    picked_qty: int
    locations: list[PickOptionLocation]


@dataclass(frozen=True)
class PickAllocationResult:
    id: uuid.UUID
    product: Product
    storage_location_id: uuid.UUID
    location_code: str
    quantity: int
    picked_qty: int


@dataclass(frozen=True)
class PickScanResult:
    kind: Literal["location", "container", "product"]
    storage_location_id: uuid.UUID | None = None
    location_code: str | None = None
    product_id: uuid.UUID | None = None
    sku_code: str | None = None
    product_name: str | None = None
    picked_qty: int | None = None
    allocation_quantity: int | None = None
    source_picked_qty: int | None = None
    container_kind: ContainerKind | None = None
    container_id: uuid.UUID | None = None
    container_code: str | None = None


@dataclass(frozen=True)
class _ActiveAssignment:
    order_id: uuid.UUID
    picked_at: datetime
    pick_id: uuid.UUID


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


async def _picked_qty_by_product_source(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> dict[
    tuple[
        uuid.UUID,
        uuid.UUID,
        ContainerKind | None,
        uuid.UUID | None,
    ],
    int,
]:
    picked: dict[
        tuple[
            uuid.UUID,
            uuid.UUID,
            ContainerKind | None,
            uuid.UUID | None,
        ],
        int,
    ] = {}
    wb_rows = await session.execute(
        select(
            FbsOrderPick.product_id,
            FbsOrderPick.source_storage_location_id,
            FbsOrderPick.source_container_kind,
            FbsOrderPick.source_container_id,
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
            FbsOrderPick.source_container_kind,
            FbsOrderPick.source_container_id,
        )
    )
    for product_id, location_id, kind, container_id, quantity in wb_rows.all():
        key = (
            product_id,
            location_id,
            cast(ContainerKind | None, kind),
            container_id,
        )
        picked[key] = picked.get(key, 0) + int(quantity)

    source_kind = func.coalesce(
        FbsOrderProductPick.source_container_kind, InventoryMovement.container_kind
    )
    source_id = func.coalesce(
        FbsOrderProductPick.source_container_id, InventoryMovement.container_id
    )
    position_rows = await session.execute(
        select(
            FbsOrderProductPick.product_id,
            FbsOrderProductPick.source_storage_location_id,
            source_kind,
            source_id,
            func.count(FbsOrderProductPick.id),
        )
        .outerjoin(
            InventoryMovement, InventoryMovement.id == FbsOrderProductPick.inventory_movement_id
        )
        .where(
            FbsOrderProductPick.tenant_id == tenant_id,
            FbsOrderProductPick.fbs_supply_id == supply_id,
            FbsOrderProductPick.undone_at.is_(None),
        )
        .group_by(
            FbsOrderProductPick.product_id,
            FbsOrderProductPick.source_storage_location_id,
            source_kind,
            source_id,
        )
    )
    for product_id, location_id, kind, container_id, quantity in position_rows.all():
        key = (product_id, location_id, cast(ContainerKind | None, kind), container_id)
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
    ozon_bindings: dict[uuid.UUID, ProductMarketplaceLink] = {}
    ozon_names: dict[uuid.UUID, str] = {}
    if supply.marketplace == "ozon":
        rows = list(
            (
                await session.scalars(
                    select(ProductMarketplaceLink).where(
                        ProductMarketplaceLink.tenant_id == tenant_id,
                        ProductMarketplaceLink.seller_id == supply.seller_id,
                        ProductMarketplaceLink.product_id.in_(product_ids),
                        ProductMarketplaceLink.marketplace == "ozon",
                        ProductMarketplaceLink.is_active.is_(True),
                    )
                )
            ).all()
        )
        ozon_bindings = {row.product_id: row for row in rows}
        for order in supply.orders:
            for position in order.product_positions:
                if position.product_id is not None and position.name:
                    ozon_names.setdefault(position.product_id, position.name)
    picked_by_location = await _picked_qty_by_product_location(
        session, tenant_id, supply.id
    )
    picked_by_source = await _picked_qty_by_product_source(
        session, tenant_id, supply.id
    )
    picked_by_product: dict[uuid.UUID, int] = {}
    for (product_id, _location_id), quantity in picked_by_location.items():
        picked_by_product[product_id] = picked_by_product.get(product_id, 0) + quantity

    unlocated_rows = await session.execute(
        select(
            FbsOrderProductPick.product_id,
            FbsOrderProductPick.source_storage_location_id,
        ).where(
            FbsOrderProductPick.tenant_id == tenant_id,
            FbsOrderProductPick.fbs_supply_id == supply.id,
            FbsOrderProductPick.undone_at.is_(None),
            FbsOrderProductPick.inventory_movement_id.is_(None),
            FbsOrderProductPick.source_container_kind.is_(None),
            FbsOrderProductPick.source_container_id.is_(None),
        )
    )
    unlocated_picked_places = {(pid, loc) for pid, loc in unlocated_rows.all()}
    try:
        locations_by_product = await pick_location_svc.list_pick_option_locations(
            session,
            tenant_id,
            supply.warehouse_id,
            product_ids,
            picked_by_location,
            picked_by_source,
            unlocated_picked_places=unlocated_picked_places,
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
            sku_code=(
                ozon_bindings[product_id].external_sku
                if supply.marketplace == "ozon" and product_id in ozon_bindings
                else None
                if supply.marketplace == "ozon"
                else product.sku_code
            ),
            product_name=(
                ozon_names.get(product_id, product.name)
                if supply.marketplace == "ozon"
                else product.name
            ),
            seller_article=(
                ozon_bindings[product_id].external_offer_id
                if supply.marketplace == "ozon" and product_id in ozon_bindings
                else None
            ),
            barcode=(
                next(
                    (
                        value.strip()
                        for value in ozon_bindings[product_id].external_barcodes
                        if isinstance(value, str) and value.strip()
                    ),
                    None,
                )
                if supply.marketplace == "ozon" and product_id in ozon_bindings
                else None
            ),
            planned_qty=planned[product_id],
            picked_qty=picked_by_product.get(product_id, 0),
            locations=locations_by_product[product_id],
        )
        for product_id, product in sorted(
            products.items(), key=lambda item: (item[1].sku_code, str(item[0]))
        )
    ]


def _allocation_id(
    supply_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
) -> uuid.UUID:
    """Stable adapter id for the shipment-compatible allocation response."""
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"wms:fbs-pick:{supply_id}:{product_id}:{storage_location_id}",
    )


def _derived_idempotency_key(
    operation_key: str,
    *,
    action: str,
    order_id: uuid.UUID,
    ordinal: int,
) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"wms:fbs-pick:{operation_key}:{action}:{order_id}:{ordinal}",
        )
    )


_PICK_SET_RECEIPT_KIND = "fbs_pick_set_receipt_v1"
_PICK_SCAN_RECEIPT_KIND = "fbs_pick_scan_receipt_v1"


def _pick_scan_receipt_key(idempotency_key: str) -> str:
    digest = hashlib.sha256(idempotency_key.encode()).hexdigest()
    return f"fbs-pick-scan:{digest}"


def _pick_scan_request_payload(
    *,
    supply_id: uuid.UUID,
    barcode: str,
    product_id_hint: uuid.UUID | None,
    order_id: uuid.UUID | None,
    storage_location_id: uuid.UUID | None,
    container_kind: ContainerKind | None,
    container_id: uuid.UUID | None,
) -> dict[str, object]:
    return {
        "supply_id": str(supply_id),
        "barcode": barcode,
        "product_id": str(product_id_hint) if product_id_hint is not None else None,
        "order_id": str(order_id) if order_id is not None else None,
        "storage_location_id": (
            str(storage_location_id) if storage_location_id is not None else None
        ),
        "container_kind": container_kind,
        "container_id": str(container_id) if container_id is not None else None,
    }


def _optional_uuid(value: object) -> uuid.UUID | None:
    return uuid.UUID(str(value)) if value is not None else None


def _validate_pick_scan_receipt(
    event: DocumentEvent,
    *,
    supply_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    request_payload: dict[str, object],
    idempotency_key: str,
) -> PickScanResult:
    payload = event.payload_json or {}
    if (
        event.document_type != DOCUMENT_TYPE_FBS_SUPPLY
        or event.document_id != supply_id
        or event.actor_user_id != actor_user_id
        or payload.get("kind") != _PICK_SCAN_RECEIPT_KIND
        or payload.get("request") != request_payload
    ):
        raise FbsPickingError(
            "idempotency_key_reused",
            "Ключ идемпотентности уже использован для другого сканирования.",
            context={"idempotency_key": idempotency_key},
        )
    result = payload.get("result")
    if not isinstance(result, dict):
        raise FbsPickingError(
            "idempotency_result_missing",
            "Не удалось восстановить результат сканирования.",
        )
    result_kind = result.get("kind")
    if result_kind not in {"location", "container", "product"}:
        raise FbsPickingError(
            "idempotency_result_missing",
            "Сохранённый результат сканирования повреждён.",
        )
    saved_container_kind = result.get("container_kind")
    if saved_container_kind not in {None, "pallet", "box", "cargo_place"}:
        raise FbsPickingError(
            "idempotency_result_missing",
            "Сохранённый источник сканирования повреждён.",
        )
    return PickScanResult(
        kind=cast(Literal["location", "container", "product"], result_kind),
        storage_location_id=_optional_uuid(result.get("storage_location_id")),
        location_code=cast(str | None, result.get("location_code")),
        product_id=_optional_uuid(result.get("product_id")),
        sku_code=cast(str | None, result.get("sku_code")),
        product_name=cast(str | None, result.get("product_name")),
        picked_qty=(
            int(str(result["picked_qty"])) if result.get("picked_qty") is not None else None
        ),
        allocation_quantity=(
            int(str(result["allocation_quantity"]))
            if result.get("allocation_quantity") is not None
            else None
        ),
        source_picked_qty=(
            int(str(result["source_picked_qty"]))
            if result.get("source_picked_qty") is not None
            else None
        ),
        container_kind=cast(ContainerKind | None, saved_container_kind),
        container_id=_optional_uuid(result.get("container_id")),
        container_code=cast(str | None, result.get("container_code")),
    )


async def _pick_scan_replay(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    supply_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    idempotency_key: str,
    request_payload: dict[str, object],
) -> PickScanResult | None:
    event = await session.scalar(
        select(DocumentEvent).where(
            DocumentEvent.tenant_id == tenant_id,
            DocumentEvent.idempotency_key == _pick_scan_receipt_key(idempotency_key),
        )
    )
    if event is None:
        return None
    return _validate_pick_scan_receipt(
        event,
        supply_id=supply_id,
        actor_user_id=actor_user_id,
        request_payload=request_payload,
        idempotency_key=idempotency_key,
    )


def _pick_set_receipt_key(idempotency_key: str) -> str:
    digest = hashlib.sha256(idempotency_key.encode()).hexdigest()
    return f"fbs-pick-set:{digest}"


def _pick_set_request_payload(
    *,
    supply_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    quantity: int,
    expected_quantity: int | None,
    container_kind: ContainerKind | None,
    container_id: uuid.UUID | None,
) -> dict[str, object]:
    return {
        "supply_id": str(supply_id),
        "product_id": str(product_id),
        "storage_location_id": str(storage_location_id),
        "quantity": quantity,
        "expected_quantity": expected_quantity,
        "container_kind": container_kind,
        "container_id": str(container_id) if container_id is not None else None,
    }


def _validate_pick_set_receipt(
    event: DocumentEvent,
    *,
    supply_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    request_payload: dict[str, object],
    idempotency_key: str,
) -> dict[str, object]:
    payload = event.payload_json or {}
    if (
        event.document_type != DOCUMENT_TYPE_FBS_SUPPLY
        or event.document_id != supply_id
        or event.actor_user_id != actor_user_id
        or payload.get("kind") != _PICK_SET_RECEIPT_KIND
        or payload.get("request") != request_payload
    ):
        raise FbsPickingError(
            "idempotency_key_reused",
            "Ключ идемпотентности уже использован для другого изменения подбора.",
            context={"idempotency_key": idempotency_key},
        )
    result = payload.get("result")
    if not isinstance(result, dict):
        raise FbsPickingError(
            "idempotency_result_missing",
            "Не удалось восстановить результат изменения подбора.",
        )
    return result


async def _pick_set_replay(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    supply_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    idempotency_key: str,
    request_payload: dict[str, object],
) -> PickAllocationResult | None:
    event = await session.scalar(
        select(DocumentEvent).where(
            DocumentEvent.tenant_id == tenant_id,
            DocumentEvent.idempotency_key == _pick_set_receipt_key(idempotency_key),
        )
    )
    if event is None:
        return None
    saved = _validate_pick_set_receipt(
        event,
        supply_id=supply_id,
        actor_user_id=actor_user_id,
        request_payload=request_payload,
        idempotency_key=idempotency_key,
    )
    product = await session.get(Product, uuid.UUID(str(request_payload["product_id"])))
    if product is None or product.tenant_id != tenant_id:
        raise FbsPickingError(
            "idempotency_result_missing",
            "Товар из сохранённого результата больше не найден.",
        )
    return PickAllocationResult(
        id=uuid.UUID(str(saved["id"])),
        product=product,
        storage_location_id=uuid.UUID(str(saved["storage_location_id"])),
        location_code=str(saved["location_code"]),
        quantity=int(str(saved["quantity"])),
        picked_qty=int(str(saved["picked_qty"])),
    )


async def _active_assignments_for_product_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    container_kind: ContainerKind | None,
    container_id: uuid.UUID | None,
) -> list[_ActiveAssignment]:
    assignments: list[_ActiveAssignment] = []
    wb_rows = await session.execute(
        select(FbsOrderPick.fbs_order_id, FbsOrderPick.picked_at, FbsOrderPick.id).where(
            FbsOrderPick.tenant_id == tenant_id,
            FbsOrderPick.fbs_supply_id == supply_id,
            FbsOrderPick.product_id == product_id,
            FbsOrderPick.source_storage_location_id == storage_location_id,
            FbsOrderPick.undone_at.is_(None),
            FbsOrderPick.source_container_kind == container_kind,
            FbsOrderPick.source_container_id == container_id,
        )
    )
    assignments.extend(
        _ActiveAssignment(order_id=order_id, picked_at=picked_at, pick_id=pick_id)
        for order_id, picked_at, pick_id in wb_rows.all()
    )

    position_rows = await session.execute(
        select(FbsOrderProduct.order_id, FbsOrderProductPick.picked_at, FbsOrderProductPick.id)
        .join(
            FbsOrderProduct,
            FbsOrderProduct.id == FbsOrderProductPick.order_product_id,
        )
        .outerjoin(
            InventoryMovement, InventoryMovement.id == FbsOrderProductPick.inventory_movement_id
        )
        .where(
            func.coalesce(
                FbsOrderProductPick.source_container_kind, InventoryMovement.container_kind
            ) == container_kind,
            func.coalesce(
                FbsOrderProductPick.source_container_id, InventoryMovement.container_id
            ) == container_id,
            FbsOrderProductPick.tenant_id == tenant_id,
            FbsOrderProductPick.fbs_supply_id == supply_id,
            FbsOrderProductPick.product_id == product_id,
            FbsOrderProductPick.source_storage_location_id == storage_location_id,
            FbsOrderProductPick.undone_at.is_(None),
        )
    )
    assignments.extend(
        _ActiveAssignment(order_id=order_id, picked_at=picked_at, pick_id=pick_id)
        for order_id, picked_at, pick_id in position_rows.all()
    )
    assignments.sort(key=lambda assignment: assignment.picked_at, reverse=True)
    return assignments


def _pending_order_ids_for_product(
    supply: FbsSupply,
    product_id: uuid.UUID,
) -> list[uuid.UUID]:
    if supply.marketplace != "ozon":
        return [
            order.id
            for order in sorted(
                _eligible_orders_for_product(supply.orders, product_id),
                key=lambda order: order.deadline_at,
            )
        ]

    pending: list[tuple[datetime, uuid.UUID]] = []
    for order, position in _eligible_positions_for_product(supply.orders, product_id):
        remaining = max(0, int(position.quantity) - int(position.picked_quantity))
        pending.extend((order.deadline_at, order.id) for _ in range(remaining))
    pending.sort(key=lambda row: row[0])
    return [order_id for _deadline, order_id in pending]


async def set_pick_quantity(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    quantity: int,
    idempotency_key: str,
    actor: User,
    expected_quantity: int | None = None,
    container_kind: ContainerKind | None = None,
    container_id: uuid.UUID | None = None,
) -> PickAllocationResult:
    """Set the final picked quantity using the existing per-order pick/undo path."""
    if quantity < 0:
        raise FbsPickingError(
            "invalid_qty",
            "Количество подбора не может быть отрицательным.",
            http_status=422,
        )
    if expected_quantity is not None and expected_quantity < 0:
        raise FbsPickingError(
            "invalid_qty",
            "Ожидаемое количество подбора не может быть отрицательным.",
            http_status=422,
        )

    request_payload = _pick_set_request_payload(
        supply_id=supply_id,
        product_id=product_id,
        storage_location_id=storage_location_id,
        quantity=quantity,
        expected_quantity=expected_quantity,
        container_kind=container_kind,
        container_id=container_id,
    )
    replay = await _pick_set_replay(
        session,
        tenant_id,
        supply_id=supply_id,
        actor_user_id=actor.id,
        idempotency_key=idempotency_key,
        request_payload=request_payload,
    )
    if replay is not None:
        return replay

    supply = await _load_supply(session, tenant_id, supply_id, for_update=True)
    # The initial lookup is intentionally before the compare-and-set check.  A
    # concurrent first attempt may have been waiting on the same supply lock,
    # so repeat the receipt lookup after acquiring it and still before CAS.
    replay = await _pick_set_replay(
        session,
        tenant_id,
        supply_id=supply_id,
        actor_user_id=actor.id,
        idempotency_key=idempotency_key,
        request_payload=request_payload,
    )
    if replay is not None:
        return replay
    await _ensure_ozon_pick_editable(session, supply)

    product = await session.get(Product, product_id)
    if product is None or product.tenant_id != tenant_id:
        raise FbsPickingError(
            "wrong_product",
            "Товар не найден в этой поставке.",
            http_status=404,
        )
    if product.seller_id != supply.seller_id:
        raise FbsPickingError(
            "seller_stock_mismatch",
            "Товар принадлежит другому селлеру.",
            context={"product_id": str(product_id)},
        )

    location = await session.get(StorageLocation, storage_location_id)
    if (
        location is None
        or location.tenant_id != tenant_id
        or location.warehouse_id != supply.warehouse_id
    ):
        raise FbsPickingError(
            "wrong_location",
            "Ячейка не принадлежит складу поставки.",
            http_status=404,
        )

    active = await _active_assignments_for_product_location(
        session,
        tenant_id,
        supply_id,
        product_id,
        storage_location_id,
        container_kind,
        container_id,
    )
    pending_order_ids = _pending_order_ids_for_product(supply, product_id)
    max_quantity = len(active) + len(pending_order_ids)
    if quantity > max_quantity:
        raise FbsPickingError(
            "pick_quantity_exceeds_demand",
            "Количество больше, чем ждут неподобранные заказы поставки.",
            context={
                "product_id": str(product_id),
                "requested": quantity,
                "maximum": max_quantity,
            },
        )

    current_quantity = len(active)
    if expected_quantity is not None and expected_quantity != current_quantity:
        raise FbsPickingError(
            "pick_quantity_changed",
            "Количество подбора изменилось. Обновите данные и повторите действие.",
            context={
                "product_id": str(product_id),
                "storage_location_id": str(storage_location_id),
                "expected_quantity": expected_quantity,
                "current_quantity": current_quantity,
            },
        )

    if session.bind is not None and session.bind.dialect.name == "sqlite":
        await session.execute(
            sa.update(DocumentEvent).where(sa.false()).values(idempotency_key=None)
        )
    inserted = await record_document_event(
        session,
        tenant_id=tenant_id,
        document_type=DOCUMENT_TYPE_FBS_SUPPLY,
        document_id=supply_id,
        event_type=EVENT_DATA_CHANGED,
        source=SOURCE_USER,
        actor_user_id=actor.id,
        product_id=product_id,
        payload_json={
            "kind": _PICK_SET_RECEIPT_KIND,
            "request": request_payload,
            "result": None,
        },
        idempotency_key=_pick_set_receipt_key(idempotency_key),
    )
    if not inserted:
        replay = await _pick_set_replay(
            session,
            tenant_id,
            supply_id=supply_id,
            actor_user_id=actor.id,
            idempotency_key=idempotency_key,
            request_payload=request_payload,
        )
        assert replay is not None
        return replay

    if quantity > current_quantity:
        for ordinal, order_id in enumerate(
            pending_order_ids[: quantity - current_quantity],
            start=1,
        ):
            await manual_pick_product(
                session,
                tenant_id,
                supply_id,
                location_id=storage_location_id,
                product_id=product_id,
                order_id=order_id,
                idempotency_key=_derived_idempotency_key(
                    idempotency_key,
                    action="pick",
                    order_id=order_id,
                    ordinal=ordinal,
                ),
                actor=actor,
                container_kind=container_kind,
                container_id=container_id,
            )
    elif quantity < current_quantity:
        for ordinal, assignment in enumerate(
            active[: current_quantity - quantity],
            start=1,
        ):
            await undo_pick(
                session,
                tenant_id,
                supply_id,
                assignment.order_id,
                idempotency_key=_derived_idempotency_key(
                    idempotency_key,
                    action="undo",
                    order_id=assignment.order_id,
                    ordinal=ordinal,
                ),
                actor=actor,
                original_pick_id=assignment.pick_id,
            )

    picked_by_location = await _picked_qty_by_product_location(session, tenant_id, supply_id)
    picked_by_product = sum(
        picked
        for (picked_product_id, _location_id), picked in picked_by_location.items()
        if picked_product_id == product_id
    )
    picked_by_source = await _picked_qty_by_product_source(session, tenant_id, supply_id)
    result = PickAllocationResult(
        id=_allocation_id(supply_id, product_id, storage_location_id),
        product=product,
        storage_location_id=storage_location_id,
        location_code=location.code,
        quantity=picked_by_source.get(
            (product_id, storage_location_id, container_kind, container_id), 0,
        ),
        picked_qty=picked_by_product,
    )
    receipt = await session.scalar(
        select(DocumentEvent).where(
            DocumentEvent.tenant_id == tenant_id,
            DocumentEvent.idempotency_key == _pick_set_receipt_key(idempotency_key),
        )
    )
    assert receipt is not None
    receipt.payload_json = {
        "kind": _PICK_SET_RECEIPT_KIND,
        "request": request_payload,
        "result": {
            "id": str(result.id),
            "storage_location_id": str(result.storage_location_id),
            "location_code": result.location_code,
            "quantity": result.quantity,
            "picked_qty": result.picked_qty,
        },
    }
    await session.flush()
    return result


async def _implicit_pick_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
    product_id: uuid.UUID,
    *,
    address_storage_enabled: bool,
) -> StorageLocation:
    if address_storage_enabled:
        cell_rows = await inventory_service.list_locations_for_product_in_warehouse(
            session,
            tenant_id,
            supply.warehouse_id,
            product_id,
        )
        if cell_rows:
            raise FbsPickingError(
                "location_required",
                "Сначала отсканируйте место, из которого снимаете товар.",
            )
        return await get_or_create_sorting_location(
            session, tenant_id, supply.warehouse_id
        )

    rows = await pick_location_svc.list_pick_option_locations(
        session, tenant_id, supply.warehouse_id, [product_id], {},
    )
    candidates = [(row.available, row.storage_location_id)
                  for row in rows[product_id] if row.available > 0]
    if candidates:
        _available, location_id = max(candidates, key=lambda row: row[0])
        location = await session.get(StorageLocation, location_id)
        assert location is not None
        return location
    return await get_or_create_sorting_location(session, tenant_id, supply.warehouse_id)


async def pick_scan(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    barcode: str,
    product_id_hint: uuid.UUID | None,
    storage_location_id: uuid.UUID | None,
    idempotency_key: str,
    actor: User,
    order_id: uuid.UUID | None = None,
    container_kind: ContainerKind | None = None,
    container_id: uuid.UUID | None = None,
) -> PickScanResult:
    raw = barcode.strip()
    request_payload = _pick_scan_request_payload(
        supply_id=supply_id,
        barcode=raw,
        product_id_hint=product_id_hint,
        order_id=order_id,
        storage_location_id=storage_location_id,
        container_kind=container_kind,
        container_id=container_id,
    )
    replay = await _pick_scan_replay(
        session,
        tenant_id,
        supply_id=supply_id,
        actor_user_id=actor.id,
        idempotency_key=idempotency_key,
        request_payload=request_payload,
    )
    if replay is not None:
        return replay
    if not raw:
        raise FbsPickingError("barcode_empty", "Штрихкод не может быть пустым.", http_status=422)

    supply = await _load_supply(session, tenant_id, supply_id)
    address_storage_enabled = await tenant_settings_svc.is_address_storage_enabled(
        session, tenant_id
    )
    if address_storage_enabled:
        location = await _resolve_storage_location(
            session,
            tenant_id,
            warehouse_id=supply.warehouse_id,
            location_barcode=raw,
        )
        if location is not None:
            return PickScanResult(
                kind="location",
                storage_location_id=location.id,
                location_code=location.code,
            )

    if (container_kind is None) != (container_id is None):
        raise FbsPickingError(
            "invalid_container_reference",
            "Тип тары и её идентификатор должны передаваться вместе.",
        )

    # A new container barcode replaces the source retained by the scanner.
    try:
        container = await resolve_container_scan(
            session,
            tenant_id,
            supply.warehouse_id,
            raw,
        )
    except InventoryContainerScanError as exc:
        if exc.code != "container_scan_not_found":
            raise FbsPickingError(
                "invalid_container_reference",
                "Штрихкод относится к нескольким складским тарам.",
            ) from exc
    else:
        location_id = await warehouse_map_service.resolve_container_location(
            session,
            tenant_id,
            supply.warehouse_id,
            container.kind,
            container.id,
        )
        location = await session.get(StorageLocation, location_id)
        return PickScanResult(
            kind="container",
            storage_location_id=location_id,
            location_code=location.code if location is not None else None,
            container_kind=container.kind,
            container_id=container.id,
            container_code=container.code,
        )

    # Product scans mutate picks and stock. Serialize every marketplace on the
    # same supply row, then repeat receipt lookup before resolving mutable
    # eligibility or the physical source. A concurrent first request may have
    # committed while this request was waiting for the row lock.
    supply = await _load_supply(session, tenant_id, supply_id, for_update=True)
    replay = await _pick_scan_replay(
        session,
        tenant_id,
        supply_id=supply_id,
        actor_user_id=actor.id,
        idempotency_key=idempotency_key,
        request_payload=request_payload,
    )
    if replay is not None:
        return replay

    if container_kind is not None and container_id is not None:
        try:
            await validate_container(
                session,
                tenant_id,
                supply.warehouse_id,
                container_kind,
                container_id,
            )
        except ValueError as exc:
            raise FbsPickingError(
                "invalid_container_reference",
                "Тара не найдена на складе поставки.",
            ) from exc
        container_location_id = await warehouse_map_service.resolve_container_location(
            session,
            tenant_id,
            supply.warehouse_id,
            container_kind,
            container_id,
        )
        if (
            storage_location_id is not None
            and storage_location_id != container_location_id
        ):
            raise FbsPickingError(
                "invalid_container_reference",
                "Тара находится в другой ячейке.",
            )
        storage_location_id = container_location_id

    product = (
        await session.get(Product, product_id_hint)
        if product_id_hint is not None
        else await _resolve_product_for_supply(
            session,
            tenant_id,
            supply,
            product_barcode=raw,
        )
    )
    if product is None or product.tenant_id != tenant_id:
        raise FbsPickingError(
            "wrong_product",
            "Товар не найден по штрихкоду в этой поставке.",
        )

    if storage_location_id is not None:
        location = await session.get(StorageLocation, storage_location_id)
        if (
            location is None
            or location.tenant_id != tenant_id
            or location.warehouse_id != supply.warehouse_id
        ):
            raise FbsPickingError(
                "wrong_location",
                "Ячейка не принадлежит складу поставки.",
                http_status=404,
            )
    else:
        location = await _implicit_pick_location(
            session,
            tenant_id,
            supply,
            product.id,
            address_storage_enabled=address_storage_enabled,
        )
        # Product-first picking without address storage still has to preserve
        # the physical container source. If there is exactly one positive
        # container balance at the implicit location, use it instead of
        # incorrectly checking only the loose (container=NULL) balance.
        if container_kind is None and container_id is None:
            container_rows = (
                await session.execute(
                    select(
                        InventoryBalance.container_kind,
                        InventoryBalance.container_id,
                    ).where(
                        InventoryBalance.tenant_id == tenant_id,
                        InventoryBalance.product_id == product.id,
                        InventoryBalance.storage_location_id == location.id,
                        InventoryBalance.container_kind.is_not(None),
                        InventoryBalance.container_id.is_not(None),
                        InventoryBalance.quantity > 0,
                    )
                )
            ).all()
            if len(container_rows) == 1:
                container_kind = cast(ContainerKind, container_rows[0][0])
                container_id = container_rows[0][1]

    if session.bind is not None and session.bind.dialect.name == "sqlite":
        await session.execute(
            sa.update(DocumentEvent).where(sa.false()).values(idempotency_key=None)
        )
    inserted = await record_document_event(
        session,
        tenant_id=tenant_id,
        document_type=DOCUMENT_TYPE_FBS_SUPPLY,
        document_id=supply_id,
        event_type=EVENT_DATA_CHANGED,
        source=SOURCE_USER,
        actor_user_id=actor.id,
        product_id=product.id,
        payload_json={
            "kind": _PICK_SCAN_RECEIPT_KIND,
            "request": request_payload,
            "result": None,
        },
        idempotency_key=_pick_scan_receipt_key(idempotency_key),
    )
    if not inserted:
        replay = await _pick_scan_replay(
            session,
            tenant_id,
            supply_id=supply_id,
            actor_user_id=actor.id,
            idempotency_key=idempotency_key,
            request_payload=request_payload,
        )
        assert replay is not None
        return replay

    await scan_pick_product(
        session,
        tenant_id,
        supply_id,
        location_id=location.id,
        product_barcode=raw,
        product_id=product.id,
        idempotency_key=idempotency_key,
        actor=actor,
        order_id=order_id,
        container_kind=container_kind,
        container_id=container_id,
    )
    picked_by_location = await _picked_qty_by_product_location(
        session, tenant_id, supply_id
    )
    picked_by_product = sum(
        picked
        for (picked_product_id, _location_id), picked in picked_by_location.items()
        if picked_product_id == product.id
    )
    picked_by_source = await _picked_qty_by_product_source(session, tenant_id, supply_id)
    source_picked_qty = picked_by_source.get(
        (product.id, location.id, container_kind, container_id), 0,
    )
    result = PickScanResult(
        kind="product",
        storage_location_id=location.id,
        location_code=location.code,
        product_id=product.id,
        sku_code=product.sku_code,
        product_name=product.name,
        picked_qty=picked_by_product,
        allocation_quantity=source_picked_qty,
        source_picked_qty=source_picked_qty,
        container_kind=container_kind,
        container_id=container_id,
    )
    receipt = await session.scalar(
        select(DocumentEvent).where(
            DocumentEvent.tenant_id == tenant_id,
            DocumentEvent.idempotency_key == _pick_scan_receipt_key(idempotency_key),
        )
    )
    assert receipt is not None
    receipt.payload_json = {
        "kind": _PICK_SCAN_RECEIPT_KIND,
        "request": request_payload,
        "result": {
            "kind": result.kind,
            "storage_location_id": str(result.storage_location_id),
            "location_code": result.location_code,
            "product_id": str(result.product_id),
            "sku_code": result.sku_code,
            "product_name": result.product_name,
            "picked_qty": result.picked_qty,
            "allocation_quantity": result.allocation_quantity,
            "source_picked_qty": result.source_picked_qty,
            "container_kind": result.container_kind,
            "container_id": str(result.container_id) if result.container_id else None,
            "container_code": result.container_code,
        },
    }
    await session.flush()
    return result


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
                "barcode": (
                    product.primary_print_barcode
                    or product.wb_barcode
                    or positions[0][0].wb_barcode
                ),
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


def _scan_order_key(order: FbsOrder) -> tuple[datetime, datetime, uuid.UUID]:
    # Source is chosen by the operator; automatic order selection is oldest-first.
    def utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    return utc(order.created_at_wb), utc(order.deadline_at), order.id


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
    container_kind: ContainerKind | None = None,
    container_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    existing = await _find_pick_by_scan_idempotency(session, tenant_id, supply_id, idempotency_key)
    if existing is not None:
        return await get_supply_workspace(session, tenant_id, supply_id)

    supply = await _load_supply(session, tenant_id, supply_id, for_update=True)
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
    await _ensure_ozon_pick_editable(session, supply)
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
                eligible_positions, key=lambda row: _scan_order_key(row[0])
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
        target_order = min(eligible_orders, key=_scan_order_key)

    assert target_order is not None
    sorting_location = await get_or_create_sorting_location(session, tenant_id, supply.warehouse_id)
    # Serialize source assignment against other picks and order reservations.
    await inventory_service.lock_stock_product(session, tenant_id, product.id)
    available = await pick_location_svc.available_pick_source_quantity(
        session,
        tenant_id,
        product.id,
        location.id,
        container_kind,
        container_id,
    )
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
                # Снимаем из указанной тары; на сортировку штука уезжает
                # россыпью — тары там нет, короб остаётся стоять в ячейке.
                from_container_kind=container_kind,
                from_container_id=container_id,
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
        raise FbsPickingError(
            "insufficient_unpacked",
            "Недостаточно товара в выбранном месте подбора.",
            context={
                "order_id": str(target_order.id),
                "product_id": str(product.id),
                "location_id": str(location.id),
                "location_code": location.code,
                "requested": 1,
                "available": int(available),
                "recommended_action": "Выберите другую ячейку или тару с доступным остатком.",
            },
        )
    picked_at = datetime.now(tz=UTC)
    if supply.marketplace == "ozon":
        assert target_position is not None
        position_pick = FbsOrderProductPick(
            tenant_id=tenant_id,
            order_product_id=target_position.id,
            fbs_supply_id=supply.id,
            source_storage_location_id=location.id,
            source_container_kind=container_kind,
            source_container_id=container_id,
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
        source_container_kind=container_kind,
        source_container_id=container_id,
        sorting_storage_location_id=sorting_location.id,
        product_id=product.id,
        scanned_product_barcode=product_barcode,
        picked_by_user_id=actor.id,
        picked_at=picked_at,
        inventory_movement_id=movement_id,
        scan_idempotency_key=idempotency_key,
    )
    try:
        async with session.begin_nested():
            session.add(pick)
            await session.flush()
    except IntegrityError as exc:
        # A concurrent request may have selected the same pending order before
        # the balance-row lock became visible (notably on SQLite, which ignores
        # FOR UPDATE). Keep this a normal business conflict, never a 500.
        raise FbsPickingError(
            "order_already_picked",
            "Заказ уже подобран другим запросом.",
            context={"order_id": str(target_order.id)},
        ) from exc
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
    container_kind: ContainerKind | None = None,
    container_id: uuid.UUID | None = None,
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
        container_kind=container_kind,
        container_id=container_id,
    )


async def undo_pick(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    order_id: uuid.UUID,
    *,
    idempotency_key: str,
    actor: User,
    original_pick_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    supply = await _load_supply(session, tenant_id, supply_id)
    if supply.marketplace == "ozon":
        supply = await _load_supply(session, tenant_id, supply_id, for_update=True)
    order = next((o for o in supply.orders if o.id == order_id), None)
    if order is None:
        raise FbsPickingError(
            "product_not_in_supply",
            "Заказ не найден в поставке.",
            http_status=404,
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
        await _ensure_ozon_pick_editable(session, supply)
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
                *([FbsOrderProductPick.id == original_pick_id] if original_pick_id else []),
            )
            .order_by(FbsOrderProductPick.picked_at.desc())
        )
        if position_pick is None:
            raise FbsPickingError(
                "order_not_picked",
                "Заказ ещё не подобран.",
                context={"order_id": str(order_id)},
            )
        original_movement = None
        if position_pick.inventory_movement_id is not None:
            original_movement = await session.scalar(
                select(InventoryMovement).where(
                    InventoryMovement.id == position_pick.inventory_movement_id,
                    InventoryMovement.tenant_id == tenant_id,
                )
            )
        original_movement_type = original_movement.movement_type if original_movement else None
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
                to_container_kind=cast(ContainerKind | None, original_movement.container_kind)
                if original_movement
                else None,
                to_container_id=original_movement.container_id if original_movement else None,
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
                # Возврат кладём ровно туда, откуда сняли: в тот же короб.
                to_container_kind=cast("ContainerKind | None", pick.source_container_kind),
                to_container_id=pick.source_container_id,
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


async def _load_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    for_update: bool = False,
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
    if for_update:
        # Delivery and cancellation also lock the supply first. Refresh both
        # the parent and select-in-loaded orders after waiting for that lock.
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    supply = (await session.execute(stmt)).scalar_one_or_none()
    if supply is None:
        raise FbsPickingError(
            "supply_not_found",
            "Поставка не найдена.",
            http_status=404,
        )
    return supply


async def _ensure_ozon_pick_editable(session: AsyncSession, supply: FbsSupply) -> None:
    """Guard stock mutations under the supply lock, never workspace navigation."""
    if supply.marketplace != "ozon":
        return
    if supply.delivered_at is not None or supply.status in {
        FBS_SUPPLY_STATUS_IN_DELIVERY, FBS_SUPPLY_STATUS_DONE,
    }:
        raise FbsPickingError(
            "supply_already_submitted", "Поставка уже передана: менять подбор нельзя.",
        )
    # Ozon checkpoints commit before HTTP calls. The existing operation bridges
    # those unlocked intervals, including an ambiguous or failed local finish.
    for operation in await list_deliver_operations_for_supply(
        session, tenant_id=supply.tenant_id, seller_id=supply.seller_id,
        local_supply_id=supply.id,
    ):
        if operation.state == WB_OPERATION_STATE_CONFIRMED:
            raise FbsPickingError(
                "supply_already_submitted", "Поставка уже передана: менять подбор нельзя.",
            )
        progress = OzonHandoffProgress.from_json(
            (operation.request_summary_json or {}).get("ozon_handoff_progress"),
        )
        if operation.state in {
            WB_OPERATION_STATE_PENDING, WB_OPERATION_STATE_PENDING_CONFIRMATION,
        } or (progress.carriage_create_started or progress.carriage_id is not None
              or progress.carriage_approved or progress.used_fallback):
            raise FbsPickingError(
                "operation_in_progress",
                "Передача в Ozon начата. Завершите проверку её результата "
                "перед изменением подбора.",
                retryable=True,
            )


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

    alias_product_id = await session.scalar(
        select(ProductBarcode.product_id).where(
            ProductBarcode.tenant_id == tenant_id,
            ProductBarcode.seller_id == supply.seller_id,
            ProductBarcode.product_id.in_(supply_product_ids),
            ProductBarcode.barcode == product_barcode,
        )
    )
    if alias_product_id is not None:
        return await session.get(Product, alias_product_id)

    if supply.marketplace != "wb":
        # Запасной поиск по штрихкодам маркетплейса: у товара Ozon собственный
        # код вида OZN<sku>, которого нет ни в `wb_barcode`, ни в `sku_code`.
        # Вайлдберрисовскую поставку эта ветка не задевает вовсе.
        from app.services.ozon_product_import_service import (
            find_product_ids_by_marketplace_barcode,
        )

        linked_ids = await find_product_ids_by_marketplace_barcode(
            session,
            tenant_id,
            [product_barcode],
        )
        matched = supply_product_ids.intersection(linked_ids)
        if len(matched) == 1:
            return await session.get(Product, next(iter(matched)))

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
    "pick_scan",
    "scan_pick_location",
    "scan_pick_product",
    "select_pick_location",
    "set_pick_quantity",
    "undo_pick",
]
