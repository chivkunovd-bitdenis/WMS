"""FBS shipment — delivery preflight, safe deliver, supply barcode."""

from __future__ import annotations

import hashlib
import logging
import uuid
from base64 import b64decode
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.settings import settings
from app.models.fbs_order import (
    FBS_ORDER_STATUS_ASSEMBLING,
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_IN_SUPPLY,
    FBS_ORDER_STATUS_PACKED,
    MARKING_KIND_SGTIN,
    FbsOrder,
    current_order_marking,
)
from app.models.fbs_order_pick import FbsOrderPick
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_PVZ,
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_DONE,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.fbs_wb_operation import (
    WB_OPERATION_STATE_CONFIRMED,
    WB_OPERATION_STATE_PENDING,
    WB_OPERATION_STATE_PENDING_CONFIRMATION,
)
from app.models.packaging_task import PackagingTaskLine
from app.services import fbs_marking_service as marking_svc
from app.services import fbs_packing_box_service as packing_box_svc
from app.services import fbs_shipment_pvz_service as pvz_svc
from app.services import inventory_service as inventory_svc
from app.services.fbs_print_asset_service import upsert_supply_qr_asset_from_bytes
from app.services.fbs_print_asset_storage import FbsPrintAssetStorageError
from app.services.fbs_supply_reconcile_service import (
    create_pending_deliver_operation,
    get_deliver_operation_by_idempotency,
    mark_deliver_operation_confirmed,
    mark_operation_failed,
    mark_operation_pending_confirmation,
    reconcile_supply_delivered,
    request_hash_for_deliver,
)
from app.services.marketplace_account_service import (
    MarketplaceAccountError,
    MarketplaceAccountService,
)
from app.services.marketplace_provider import (
    FakeMarketplaceTransport,
    MarketplaceProviderError,
    OzonMarketplaceProvider,
    provider_error_message,
)
from app.services.ozon_fbs_process_service import OzonFbsProcessError, handoff_supply
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.wb_marketplace_orders_service import (
    _apply_wb_status_to_order,
    _release_reservation,
    _supplier_status_from_row,
    _wb_status_from_row,
)
from app.services.wildberries_client import (
    deliver_marketplace_supply,
    fetch_marketplace_orders_status,
    fetch_marketplace_supply_barcode,
)
from app.services.wildberries_credentials_service import (
    _seller_in_tenant,
    get_decrypted_marketplace_token,
)
from app.services.wildberries_errors import (
    WildberriesBusinessError,
    WildberriesClientError,
    log_wb_client_error,
    wb_error_context,
    wb_error_ref,
    wb_operator_message,
)
from app.services.wildberries_fbs_client import split_marketplace_order_id_batches

_DELIVER_READY_ORDER_STATUSES = frozenset({FBS_ORDER_STATUS_PACKED})
_PACKAGING_PENDING_ORDER_STATUSES = frozenset(
    {FBS_ORDER_STATUS_IN_SUPPLY, FBS_ORDER_STATUS_ASSEMBLING}
)
_DELIVER_ALLOWED_DELIVERY_TYPES = frozenset({FBS_DELIVERY_TYPE_WAREHOUSE_SC, FBS_DELIVERY_TYPE_PVZ})
_DELIVER_BLOCKED_SUPPLY_STATUSES = frozenset(
    {
        FBS_SUPPLY_STATUS_IN_DELIVERY,
        FBS_SUPPLY_STATUS_DONE,
    }
)

logger = logging.getLogger(__name__)

_WB_DISPATCH_PENDING_MESSAGE = "fix them to dispatch items"
_FAKE_OZON_SUPPLY_QR = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    "hQGAhKmMIQAAAABJRU5ErkJggg=="
)


class FbsShipmentError(Exception):
    def __init__(
        self,
        code: str,
        *,
        message: str | None = None,
        context: dict[str, Any] | None = None,
        retryable: bool = False,
        http_status: int | None = None,
    ) -> None:
        self.code = code
        self.message = message or code
        self.context = context or {}
        self.retryable = retryable
        self.http_status = http_status
        super().__init__(code)


def _meta_validation_message(exc: WildberriesBusinessError) -> tuple[str, bool]:
    if (exc.message or "").strip().lower() == _WB_DISPATCH_PENDING_MESSAGE:
        return (
            "Wildberries ещё обрабатывает поставку. Повторите передачу через минуту.",
            True,
        )
    return (exc.message or "WB отклонил метаданные заказов.", False)


@dataclass(frozen=True)
class DeliveryCheck:
    code: str
    message: str
    ok: bool
    order_id: uuid.UUID | None = None


@dataclass(frozen=True)
class DeliveryPreflightResult:
    can_deliver: bool
    version: str
    checked_at: datetime
    checks: tuple[DeliveryCheck, ...]


def _wb_error_code(exc: WildberriesClientError) -> str:
    suffix = f"_{exc.status_code}" if exc.status_code else ""
    return f"wb_{exc.code}{suffix}"


def _shipment_error_from_wb(
    exc: WildberriesClientError,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    local_entity_id: uuid.UUID | str | None,
    wb_supply_id: str | None,
    event: str,
    retryable: bool | None = None,
    http_status: int | None = None,
    extra_context: dict[str, Any] | None = None,
) -> FbsShipmentError:
    ref = wb_error_ref()
    log_wb_client_error(
        logger,
        event,
        exc,
        tenant_id=tenant_id,
        seller_id=seller_id,
        local_entity_id=local_entity_id,
        wb_object_id=wb_supply_id,
        ref=ref,
    )
    extra: dict[str, Any] = {}
    if wb_supply_id is not None:
        extra["wb_supply_id"] = wb_supply_id
    if local_entity_id is not None:
        extra["local_entity_id"] = str(local_entity_id)
    if extra_context:
        extra.update(extra_context)
    return FbsShipmentError(
        _wb_error_code(exc),
        message=wb_operator_message(exc),
        context=wb_error_context(exc, ref=ref, extra=extra),
        retryable=exc.code == "transport_error" if retryable is None else retryable,
        http_status=http_status or (504 if exc.code == "transport_error" else 502),
    )


async def _require_marketplace_token(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> str:
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsShipmentError("seller_not_found")
    token = await get_decrypted_marketplace_token(session, tenant_id, seller_id)
    if not token:
        raise FbsShipmentError("missing_marketplace_token")
    return token


def _barcode_relative_path(supply_id: uuid.UUID) -> str:
    return f"fbs-supply-barcodes/{supply_id}.png"


def _barcode_storage_root() -> Path:
    return (Path(settings.wms_data_dir) / "fbs-supply-barcodes").resolve()


def _resolve_barcode_path(rel: str) -> Path:
    root = _barcode_storage_root()
    target = (Path(settings.wms_data_dir) / rel).resolve()
    if root not in target.parents and target != root:
        raise FbsShipmentError("invalid_barcode_path")
    return target


def _save_barcode_png(supply_id: uuid.UUID, png_bytes: bytes) -> str:
    rel = _barcode_relative_path(supply_id)
    target = _resolve_barcode_path(rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png_bytes)
    return rel


async def _get_supply_for_update(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    with_trbxes: bool = False,
) -> FbsSupply | None:
    stmt = (
        select(FbsSupply)
        .where(
            FbsSupply.id == supply_id,
            FbsSupply.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    if with_trbxes:
        stmt = stmt.options(selectinload(FbsSupply.trbxes))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _supply_orders_stmt(
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> Select[tuple[FbsOrder]]:
    return (
        select(FbsOrder)
        .where(
            FbsOrder.supply_id == supply_id,
            FbsOrder.tenant_id == tenant_id,
        )
        .options(
            selectinload(FbsOrder.product),
            selectinload(FbsOrder.product_positions),
            selectinload(FbsOrder.markings),
        )
    )


async def _load_locked_supply_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> list[FbsOrder]:
    result = await session.execute(_supply_orders_stmt(tenant_id, supply_id).with_for_update())
    return list(result.scalars().all())


async def _load_supply_orders_read(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> list[FbsOrder]:
    result = await session.execute(_supply_orders_stmt(tenant_id, supply_id))
    return list(result.scalars().all())


async def _get_supply_read(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    with_trbxes: bool = False,
) -> FbsSupply | None:
    stmt = select(FbsSupply).where(
        FbsSupply.id == supply_id,
        FbsSupply.tenant_id == tenant_id,
    )
    if with_trbxes:
        stmt = stmt.options(selectinload(FbsSupply.trbxes))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _order_has_sgtin_marking(order: FbsOrder) -> bool:
    return current_order_marking(list(order.markings), MARKING_KIND_SGTIN) is not None


async def _sync_supply_orders_from_wb(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
    http_client: httpx.AsyncClient,
    token: str,
    *,
    actor_user_id: uuid.UUID | None,
) -> list[FbsOrder]:
    orders = await _load_supply_orders_read(session, tenant_id, supply.id)
    if not orders:
        supply.last_wb_sync_at = datetime.now(UTC)
        await session.flush()
        return orders

    wb_ids = [int(order.wb_order_id) for order in orders]
    for batch in split_marketplace_order_id_batches(wb_ids):
        try:
            status_rows = await fetch_marketplace_orders_status(
                http_client,
                api_token=token,
                order_ids=batch,
            )
        except WildberriesClientError as exc:
            raise _shipment_error_from_wb(
                exc,
                tenant_id=tenant_id,
                seller_id=supply.seller_id,
                local_entity_id=supply.id,
                wb_supply_id=supply.wb_supply_id,
                event="fbs shipment WB supply status sync failed",
                extra_context={"wb_order_ids": batch},
            ) from exc
        by_id = {int(row["id"]): row for row in status_rows if row.get("id") is not None}
        for order in orders:
            row = by_id.get(int(order.wb_order_id))
            if row is None:
                continue
            wb_status = _wb_status_from_row(row)
            supplier_status = _supplier_status_from_row(row)
            if wb_status is not None or supplier_status is not None:
                await _apply_wb_status_to_order(
                    session,
                    order,
                    wb_status,
                    supplier_status=supplier_status,
                    actor_user_id=actor_user_id,
                )

    for order in orders:
        with suppress(marking_svc.FbsMarkingError):
            await marking_svc.sync_order_marking_statuses(
                session,
                tenant_id,
                order.id,
                http_client,
                actor_user_id=actor_user_id,
            )

    supply.last_wb_sync_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(supply)
    return await _load_supply_orders_read(session, tenant_id, supply.id)


def _compute_preflight_version(
    supply: FbsSupply,
    orders: list[FbsOrder],
    *,
    cargo_qr_ready: bool,
    has_physical_boxes: bool,
    without_distribution: bool,
    unassigned_packed_order_ids: frozenset[uuid.UUID],
) -> str:
    parts = [
        str(supply.id),
        supply.status,
        supply.delivery_type,
        str(cargo_qr_ready),
        str(has_physical_boxes),
        str(without_distribution),
        *(str(order_id) for order_id in sorted(unassigned_packed_order_ids)),
    ]
    for order in sorted(orders, key=lambda item: item.id):
        parts.extend(
            [
                str(order.id),
                order.status,
                order.wb_status or "",
                str(order.metadata_delivery_allowed),
            ]
        )
    raw = "|".join(parts).encode()
    return hashlib.sha256(raw).hexdigest()


def _build_delivery_checks(
    supply: FbsSupply,
    orders: list[FbsOrder],
    *,
    cargo_qr_ready: bool,
    boxes_required: bool = True,
    has_physical_boxes: bool = True,
    without_distribution: bool = False,
    unassigned_packed_order_ids: frozenset[uuid.UUID] = frozenset(),
) -> list[DeliveryCheck]:
    # «Сдать без Честного знака» снимает НАШЕ требование маркировки по поставке.
    # Требование самого Wildberries, записанное в required_meta_json заказа, этим
    # флагом не отменяется: такой заказ по-прежнему не уедет, и это правильно.
    honest_sign_skipped = supply.honest_sign_skipped_at is not None
    checks: list[DeliveryCheck] = []

    if supply.status in _DELIVER_BLOCKED_SUPPLY_STATUSES:
        checks.append(
            DeliveryCheck(
                code="supply_bad_status",
                message="Поставка уже передана или закрыта.",
                ok=False,
            )
        )
    elif supply.status != FBS_SUPPLY_STATUS_PACKED:
        checks.append(
            DeliveryCheck(
                code="packaging_required",
                message="Упаковка поставки не завершена.",
                ok=False,
            )
        )
    else:
        checks.append(
            DeliveryCheck(
                code="supply_packed",
                message="Поставка упакована.",
                ok=True,
            )
        )

    if not orders:
        checks.append(
            DeliveryCheck(
                code="supply_empty",
                message="Поставка пуста — нет заказов.",
                ok=False,
            )
        )

    for order in orders:
        if order.status == FBS_ORDER_STATUS_CANCELLED:
            checks.append(
                DeliveryCheck(
                    code="order_cancelled",
                    message="Заказ отменён на WB.",
                    ok=False,
                    order_id=order.id,
                )
            )
        elif order.status in _PACKAGING_PENDING_ORDER_STATUSES:
            checks.append(
                DeliveryCheck(
                    code="packaging_required",
                    message="Заказ ещё не упакован.",
                    ok=False,
                    order_id=order.id,
                )
            )
        elif order.status not in _DELIVER_READY_ORDER_STATUSES:
            checks.append(
                DeliveryCheck(
                    code="orders_not_ready",
                    message="Заказ не готов к передаче.",
                    ok=False,
                    order_id=order.id,
                )
            )
        else:
            checks.append(
                DeliveryCheck(
                    code="order_packed",
                    message="Заказ упакован.",
                    ok=True,
                    order_id=order.id,
                )
            )

        product = order.product
        if (
            product is not None
            and product.requires_honest_sign
            and not _order_has_sgtin_marking(order)
            and not honest_sign_skipped
        ):
            checks.append(
                DeliveryCheck(
                    code="marking_required",
                    message="Требуется маркировка Честный знак.",
                    ok=False,
                    order_id=order.id,
                )
            )
        elif not marking_svc.compute_delivery_allowed(order, list(order.markings)):
            checks.append(
                DeliveryCheck(
                    code="marking_not_allowed",
                    message=marking_svc.delivery_marking_message(order, list(order.markings)),
                    ok=False,
                    order_id=order.id,
                )
            )
        elif order.required_meta_json:
            checks.append(
                DeliveryCheck(
                    code="marking_allowed",
                    message=marking_svc.delivery_marking_message(order, list(order.markings)),
                    ok=True,
                    order_id=order.id,
                )
            )

    if supply.delivery_type == FBS_DELIVERY_TYPE_PVZ and has_physical_boxes:
        if not supply.trbxes:
            checks.append(
                DeliveryCheck(
                    code="box_qr_not_ready",
                    message="QR коробов ПВЗ ещё не готовы.",
                    ok=False,
                )
            )
        elif not cargo_qr_ready:
            checks.append(
                DeliveryCheck(
                    code="cargo_place_qr_not_ready",
                    message="QR грузомест не готовы к печати.",
                    ok=False,
                )
            )
        else:
            checks.append(
                DeliveryCheck(
                    code="cargo_places_ready",
                    message="Грузоместа и QR готовы.",
                    ok=True,
                )
            )

    if boxes_required and not has_physical_boxes:
        checks.append(
            DeliveryCheck(
                code="physical_boxes_required",
                message="Создайте физические короба для передачи поставки.",
                ok=False,
            )
        )
    if boxes_required and without_distribution and has_physical_boxes:
        checks.append(
            DeliveryCheck(
                code="boxes_without_distribution",
                message="Короба созданы без распределения товаров.",
                ok=True,
            )
        )
    else:
        for order_id in sorted(unassigned_packed_order_ids):
            checks.append(
                DeliveryCheck(
                    code="packed_order_unassigned",
                    message="Упакованный заказ не назначен в физический короб.",
                    ok=False,
                    order_id=order_id,
                )
            )

    return checks


def _checks_to_payload(checks: list[DeliveryCheck]) -> list[dict[str, Any]]:
    return [
        {
            "code": check.code,
            "message": check.message,
            "ok": check.ok,
            "order_id": str(check.order_id) if check.order_id is not None else None,
        }
        for check in checks
    ]


def _validate_checks_pass(checks: list[DeliveryCheck]) -> None:
    for check in checks:
        if not check.ok:
            raise FbsShipmentError(check.code)


async def _sync_and_validate_deliver(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
    http_client: httpx.AsyncClient,
    token: str,
    *,
    confirmed_preflight_version: str | None = None,
    actor_user_id: uuid.UUID | None,
) -> tuple[list[FbsOrder], bool]:
    orders = await _sync_supply_orders_from_wb(
        session,
        tenant_id,
        supply,
        http_client,
        token,
        actor_user_id=actor_user_id,
    )
    cargo_qr_ready = True
    if supply.delivery_type == FBS_DELIVERY_TYPE_PVZ:
        cargo_qr_ready = await pvz_svc.supply_has_ready_cargo_place_qrs(session, tenant_id, supply)
    box_readiness = await packing_box_svc.get_delivery_box_readiness(
        session, tenant_id, supply.id, orders
    )
    if confirmed_preflight_version is not None:
        current_version = _compute_preflight_version(
            supply,
            orders,
            cargo_qr_ready=cargo_qr_ready,
            has_physical_boxes=box_readiness.has_physical_boxes,
            without_distribution=box_readiness.without_distribution,
            unassigned_packed_order_ids=box_readiness.unassigned_packed_order_ids,
        )
        if current_version != confirmed_preflight_version:
            raise FbsShipmentError(
                "stale_preflight",
                message="Чек-лист устарел — обновите preflight.",
                context={
                    "current_version": current_version,
                    "confirmed_preflight_version": confirmed_preflight_version,
                },
                http_status=409,
            )
    checks = _build_delivery_checks(
        supply,
        orders,
        cargo_qr_ready=cargo_qr_ready,
        has_physical_boxes=box_readiness.has_physical_boxes,
        without_distribution=box_readiness.without_distribution,
        unassigned_packed_order_ids=box_readiness.unassigned_packed_order_ids,
    )
    _validate_checks_pass(checks)
    return orders, cargo_qr_ready


def _meta_validation_context(exc: WildberriesBusinessError) -> list[dict[str, Any]]:
    return [
        {
            "order_id": item.order_id,
            "key": item.key,
            "value": item.value,
            "decision": item.decision,
            "reason": item.reason,
        }
        for item in exc.meta_validation
    ]


async def preflight_delivery(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    *,
    actor_user_id: uuid.UUID | None,
) -> DeliveryPreflightResult:
    supply = await _get_supply_read(session, tenant_id, supply_id, with_trbxes=True)
    if supply is None:
        raise FbsShipmentError("supply_not_found")
    if supply.delivery_type not in _DELIVER_ALLOWED_DELIVERY_TYPES:
        raise FbsShipmentError("wrong_delivery_type")

    if supply.marketplace == "ozon":
        await _ozon_credentials(session, tenant_id, supply.seller_id)
        orders = await _load_supply_orders_read(session, tenant_id, supply.id)
        checks = _build_delivery_checks(
            supply,
            orders,
            cargo_qr_ready=True,
            boxes_required=False,
        )
        checked_at = datetime.now(UTC)
        version = _compute_preflight_version(
            supply,
            orders,
            cargo_qr_ready=True,
            has_physical_boxes=False,
            without_distribution=False,
            unassigned_packed_order_ids=frozenset(),
        )
        return DeliveryPreflightResult(
            can_deliver=all(check.ok for check in checks),
            version=version,
            checked_at=checked_at,
            checks=tuple(checks),
        )

    token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    orders = await _sync_supply_orders_from_wb(
        session,
        tenant_id,
        supply,
        http_client,
        token,
        actor_user_id=actor_user_id,
    )
    cargo_qr_ready = True
    if supply.delivery_type == FBS_DELIVERY_TYPE_PVZ:
        cargo_qr_ready = await pvz_svc.supply_has_ready_cargo_place_qrs(session, tenant_id, supply)
    box_readiness = await packing_box_svc.get_delivery_box_readiness(
        session, tenant_id, supply.id, orders
    )

    checks = _build_delivery_checks(
        supply,
        orders,
        cargo_qr_ready=cargo_qr_ready,
        has_physical_boxes=box_readiness.has_physical_boxes,
        without_distribution=box_readiness.without_distribution,
        unassigned_packed_order_ids=box_readiness.unassigned_packed_order_ids,
    )
    checked_at = datetime.now(UTC)
    version = _compute_preflight_version(
        supply,
        orders,
        cargo_qr_ready=cargo_qr_ready,
        has_physical_boxes=box_readiness.has_physical_boxes,
        without_distribution=box_readiness.without_distribution,
        unassigned_packed_order_ids=box_readiness.unassigned_packed_order_ids,
    )
    can_deliver = all(check.ok for check in checks)
    return DeliveryPreflightResult(
        can_deliver=can_deliver,
        version=version,
        checked_at=checked_at,
        checks=tuple(checks),
    )


def delivery_preflight_to_dict(result: DeliveryPreflightResult) -> dict[str, Any]:
    return {
        "can_deliver": result.can_deliver,
        "version": result.version,
        "checked_at": result.checked_at.isoformat(),
        "checks": _checks_to_payload(list(result.checks)),
    }


async def _apply_local_delivered(
    session: AsyncSession,
    supply: FbsSupply,
    orders: list[FbsOrder],
    actor_user_id: uuid.UUID | None,
) -> None:
    await _write_off_delivered_orders_once(session, supply, orders, actor_user_id)
    now = datetime.now(UTC)
    supply.status = FBS_SUPPLY_STATUS_IN_DELIVERY
    supply.delivered_at = now
    for order in orders:
        if order.status == FBS_ORDER_STATUS_PACKED:
            order.status = FBS_ORDER_STATUS_IN_DELIVERY
    await session.flush()


async def _shipment_locations_by_order(
    session: AsyncSession,
    order_ids: list[uuid.UUID],
) -> dict[uuid.UUID, tuple[uuid.UUID, uuid.UUID]]:
    """Return order -> (product, physical shipment location), preferring packing."""
    if not order_ids:
        return {}
    fulfillment_rows = (
        await session.execute(
            select(
                FbsPackagingFulfillment.fbs_order_id,
                PackagingTaskLine.product_id,
                PackagingTaskLine.storage_location_id,
            )
            .join(
                PackagingTaskLine,
                PackagingTaskLine.id == FbsPackagingFulfillment.packaging_task_line_id,
            )
            .where(
                FbsPackagingFulfillment.fbs_order_id.in_(order_ids),
                FbsPackagingFulfillment.undone_at.is_(None),
            )
        )
    ).all()
    result = {
        order_id: (product_id, storage_location_id)
        for order_id, product_id, storage_location_id in fulfillment_rows
    }
    missing_ids = [order_id for order_id in order_ids if order_id not in result]
    if not missing_ids:
        return result
    pick_rows = (
        await session.execute(
            select(
                FbsOrderPick.fbs_order_id,
                FbsOrderPick.product_id,
                FbsOrderPick.sorting_storage_location_id,
            ).where(
                FbsOrderPick.fbs_order_id.in_(missing_ids),
                FbsOrderPick.undone_at.is_(None),
            )
        )
    ).all()
    result.update(
        {
            order_id: (product_id, storage_location_id)
            for order_id, product_id, storage_location_id in pick_rows
        }
    )
    return result


async def _write_off_delivered_orders_once(
    session: AsyncSession,
    supply: FbsSupply,
    orders: list[FbsOrder],
    actor_user_id: uuid.UUID | None,
) -> None:
    """Create exactly one physical write-off per confirmed FBS order."""
    active_orders = [
        order
        for order in orders
        if order.status != FBS_ORDER_STATUS_CANCELLED and order.product_id is not None
    ]
    order_ids = [order.id for order in active_orders]
    existing_ledgers = {
        ledger.fbs_order_id: ledger
        for ledger in (
            (
                await session.execute(
                    select(FbsShipmentReversalLedger)
                    .where(
                        FbsShipmentReversalLedger.tenant_id == supply.tenant_id,
                        FbsShipmentReversalLedger.fbs_order_id.in_(order_ids),
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
    }
    locations = await _shipment_locations_by_order(session, order_ids)
    fallback_location_id: uuid.UUID | None = None

    for order in active_orders:
        ledger = existing_ledgers.get(order.id)
        if ledger is None:
            shipment_location = locations.get(order.id)
            if shipment_location is not None:
                fulfilled_product_id, storage_location_id = shipment_location
                if fulfilled_product_id != order.product_id:
                    raise FbsShipmentError("fbs_shipment_product_mismatch", http_status=409)
            else:
                if fallback_location_id is None:
                    fallback_location = await get_or_create_sorting_location(
                        session,
                        supply.tenant_id,
                        supply.warehouse_id,
                    )
                    fallback_location_id = fallback_location.id
                storage_location_id = fallback_location_id
            ledger = FbsShipmentReversalLedger(
                tenant_id=supply.tenant_id,
                fbs_order_id=order.id,
                product_id=order.product_id,
                storage_location_id=storage_location_id,
                quantity=1,
            )
            session.add(ledger)
            await session.flush()
            existing_ledgers[order.id] = ledger

        if ledger.reversed_at is not None:
            raise FbsShipmentError("fbs_shipment_already_reversed", http_status=409)
        if ledger.shipment_movement_id is None:
            movement = await inventory_svc.apply_fbs_supply_write_off(
                session,
                tenant_id=supply.tenant_id,
                product_id=ledger.product_id,
                storage_location_id=ledger.storage_location_id,
                quantity=int(ledger.quantity),
                actor_user_id=actor_user_id,
            )
            await session.flush()
            ledger.shipment_movement_id = movement.id
        await _release_reservation(session, order)
    await session.flush()


async def _fetch_supply_qr_after_deliver(
    session: AsyncSession,
    supply: FbsSupply,
    http_client: httpx.AsyncClient,
    token: str,
) -> None:
    # WB issues a supply QR (GET /api/v3/supplies/{id}/barcode) regardless of
    # delivery_type — verified against the WB API for both warehouse_sc and pvz
    # supplies on 2026-08-17. Do not re-add a delivery_type gate here.
    if supply.barcode_file and supply.barcode_asset_id:
        return
    try:
        png_bytes = await fetch_marketplace_supply_barcode(
            http_client,
            api_token=token,
            supply_id=supply.wb_supply_id,
        )
    except WildberriesClientError as exc:
        raise _shipment_error_from_wb(
            exc,
            tenant_id=supply.tenant_id,
            seller_id=supply.seller_id,
            local_entity_id=supply.id,
            wb_supply_id=supply.wb_supply_id,
            event="fbs shipment WB supply QR fetch failed",
        ) from exc
    supply.barcode_file = _save_barcode_png(supply.id, png_bytes)
    try:
        await upsert_supply_qr_asset_from_bytes(
            session,
            tenant_id=supply.tenant_id,
            supply=supply,
            png_bytes=png_bytes,
        )
    except FbsPrintAssetStorageError as exc:
        raise FbsShipmentError(exc.code) from exc
    await session.flush()


async def _persist_confirmed_delivery(
    session: AsyncSession,
    supply: FbsSupply,
    orders: list[FbsOrder],
    operation: Any,
    actor_user_id: uuid.UUID | None,
) -> None:
    """Durably checkpoint marketplace delivery before fetching its optional QR asset."""
    await _apply_local_delivered(session, supply, orders, actor_user_id)
    await mark_deliver_operation_confirmed(
        session,
        operation,
        wb_supply_id=supply.wb_supply_id,
        local_supply_id=supply.id,
    )
    # The route only commits selected errors.  A barcode download failure must
    # therefore not roll back the already confirmed WB delivery.
    await session.commit()


async def _ozon_credentials(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> tuple[str, str]:
    try:
        return await MarketplaceAccountService(session).stored_credentials(
            tenant_id,
            seller_id,
        )
    except MarketplaceAccountError as exc:
        raise FbsShipmentError(
            exc.code,
            message="Кабинет Ozon не подключён.",
            http_status=409,
        ) from exc


async def _store_ozon_supply_qr(
    session: AsyncSession,
    supply: FbsSupply,
    provider: OzonMarketplaceProvider,
    *,
    client_id: str,
    api_key: str,
) -> bytes:
    external_supply_id = supply.external_supply_id or supply.wb_supply_id
    try:
        png_bytes = await provider.fetch_supply_qr(
            client_id=client_id,
            api_key=api_key,
            supply_id=external_supply_id,
        )
    except MarketplaceProviderError as exc:
        raise FbsShipmentError(
            exc.code,
            message=provider_error_message(exc),
            retryable=exc.status_code in {429, 500, 502, 503, 504},
            http_status=exc.status_code or 502,
        ) from exc
    if not png_bytes:
        raise FbsShipmentError(
            "ozon_supply_qr_missing",
            message="Ozon не вернул QR поставки.",
            http_status=502,
        )
    try:
        await upsert_supply_qr_asset_from_bytes(
            session,
            tenant_id=supply.tenant_id,
            supply=supply,
            png_bytes=png_bytes,
        )
    except FbsPrintAssetStorageError as exc:
        raise FbsShipmentError(exc.code) from exc
    await session.flush()
    return png_bytes


async def _deliver_ozon_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    idempotency_key: str,
    request_hash: str,
    existing: Any,
    provider: OzonMarketplaceProvider | None,
    actor_user_id: uuid.UUID | None,
) -> FbsSupply:
    supply = await _get_supply_for_update(
        session,
        tenant_id,
        supply_id,
        with_trbxes=True,
    )
    if supply is None:
        raise FbsShipmentError("supply_not_found")
    if supply.delivery_type not in _DELIVER_ALLOWED_DELIVERY_TYPES:
        raise FbsShipmentError("wrong_delivery_type")

    client_id, api_key = await _ozon_credentials(
        session,
        tenant_id,
        supply.seller_id,
    )
    if existing is not None:
        if existing.request_hash and existing.request_hash != request_hash:
            raise FbsShipmentError("idempotency_key_reused", http_status=409)
        if existing.state == WB_OPERATION_STATE_CONFIRMED:
            return supply
        if existing.state == WB_OPERATION_STATE_PENDING:
            raise FbsShipmentError(
                "operation_in_progress",
                message="Передача в Ozon уже выполняется.",
                retryable=True,
                http_status=503,
            )
        raise FbsShipmentError(
            existing.error_code or "operation_failed",
            message="Предыдущая передача Ozon завершилась ошибкой; слепой повтор запрещён.",
            http_status=409,
        )

    if supply.status in _DELIVER_BLOCKED_SUPPLY_STATUSES:
        raise FbsShipmentError("supply_bad_status", http_status=409)
    orders = await _load_locked_supply_orders(session, tenant_id, supply.id)
    _validate_checks_pass(
        _build_delivery_checks(
            supply,
            orders,
            cargo_qr_ready=True,
            boxes_required=False,
        )
    )
    operation = existing or await create_pending_deliver_operation(
        session,
        tenant_id=tenant_id,
        seller_id=supply.seller_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        local_supply_id=supply.id,
        confirmed_preflight_version=None,
    )
    if provider is None:
        await mark_operation_failed(
            session,
            operation,
            error_code="ozon_live_handoff_blocked",
            local_supply_id=supply.id,
        )
        raise FbsShipmentError(
            "ozon_live_handoff_blocked",
            message=(
                "Реальная передача в Ozon заблокирована: кабинет недоступен. "
                "Локальная складская операция сохранена."
            ),
            http_status=503,
        )
    try:
        result = await handoff_supply(
            session,
            supply=supply,
            orders=orders,
            provider=provider,
            client_id=client_id,
            api_key=api_key,
        )
    except OzonFbsProcessError as exc:
        await session.flush()
        await mark_operation_failed(
            session,
            operation,
            error_code=exc.code,
            local_supply_id=supply.id,
        )
        raise FbsShipmentError(
            exc.code,
            message=exc.message,
            retryable=False,
            http_status=exc.status_code or 502,
        ) from exc
    except MarketplaceProviderError as exc:
        await mark_operation_failed(
            session,
            operation,
            error_code=exc.code,
            local_supply_id=supply.id,
        )
        raise FbsShipmentError(
            exc.code,
            message=provider_error_message(exc),
            retryable=exc.status_code in {429, 500, 502, 503, 504},
            http_status=exc.status_code or 502,
        ) from exc

    supply.external_supply_id = str(result.carriage_id) if result.carriage_id is not None else None
    supply.document_number = str(result.carriage_id) if result.carriage_id is not None else None
    supply.display_number = result.barcode_text
    if result.barcode_bytes:
        try:
            await upsert_supply_qr_asset_from_bytes(
                session,
                tenant_id=supply.tenant_id,
                supply=supply,
                png_bytes=result.barcode_bytes,
            )
        except FbsPrintAssetStorageError as exc:
            raise FbsShipmentError(exc.code) from exc
    await _persist_confirmed_delivery(session, supply, orders, operation, actor_user_id)
    return supply


async def deliver_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    *,
    idempotency_key: str,
    actor_user_id: uuid.UUID | None,
    confirmed_preflight_version: str | None = None,
    ozon_provider: OzonMarketplaceProvider | None = None,
) -> FbsSupply:
    if not idempotency_key.strip():
        raise FbsShipmentError("missing_idempotency_key")

    supply_read = await _get_supply_read(session, tenant_id, supply_id, with_trbxes=True)
    if supply_read is None:
        raise FbsShipmentError("supply_not_found")

    request_hash = request_hash_for_deliver(
        supply_id=supply_id,
        confirmed_preflight_version=confirmed_preflight_version,
    )
    existing = await get_deliver_operation_by_idempotency(
        session, supply_read.seller_id, idempotency_key
    )
    if supply_read.marketplace == "ozon":
        return await _deliver_ozon_supply(
            session,
            tenant_id,
            supply_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            existing=existing,
            provider=ozon_provider,
            actor_user_id=actor_user_id,
        )
    if existing is not None:
        if (
            existing.request_hash
            and existing.request_hash != request_hash
            and existing.state != WB_OPERATION_STATE_PENDING_CONFIRMATION
        ):
            raise FbsShipmentError("idempotency_key_reused", http_status=409)
        if existing.state == WB_OPERATION_STATE_CONFIRMED:
            confirmed_supply = await _get_supply_for_update(
                session, tenant_id, supply_id, with_trbxes=True
            )
            if confirmed_supply is not None:
                token = await _require_marketplace_token(
                    session, tenant_id, confirmed_supply.seller_id
                )
                # A prior QR failure is recoverable through the same idempotent
                # request and must never trigger another WB deliver mutation.
                await _fetch_supply_qr_after_deliver(session, confirmed_supply, http_client, token)
                return confirmed_supply
        if existing.state == WB_OPERATION_STATE_PENDING:
            raise FbsShipmentError(
                "operation_in_progress",
                message="Передача в доставку уже выполняется.",
                retryable=True,
                http_status=503,
            )
        if existing.state == WB_OPERATION_STATE_PENDING_CONFIRMATION:
            token = await _require_marketplace_token(session, tenant_id, supply_read.seller_id)
            reconcile_state = await reconcile_supply_delivered(
                http_client,
                api_token=token,
                wb_supply_id=supply_read.wb_supply_id,
            )
            supply = await _get_supply_for_update(session, tenant_id, supply_id, with_trbxes=True)
            if supply is None:
                raise FbsShipmentError("supply_not_found")
            await _sync_and_validate_deliver(
                session,
                tenant_id,
                supply,
                http_client,
                token,
                confirmed_preflight_version=confirmed_preflight_version,
                actor_user_id=actor_user_id,
            )
            if reconcile_state == WB_OPERATION_STATE_CONFIRMED:
                orders = await _load_locked_supply_orders(session, tenant_id, supply.id)
                await _persist_confirmed_delivery(session, supply, orders, existing, actor_user_id)
                await _fetch_supply_qr_after_deliver(session, supply, http_client, token)
                return supply

            try:
                await deliver_marketplace_supply(
                    http_client,
                    api_token=token,
                    supply_id=supply.wb_supply_id,
                )
            except WildberriesBusinessError as exc:
                meta_context = _meta_validation_context(exc)
                message, retryable = _meta_validation_message(exc)
                await mark_operation_failed(
                    session,
                    existing,
                    error_code="meta_validation_fail",
                    error_context={"meta_validation": meta_context},
                    wb_supply_id=supply.wb_supply_id,
                    local_supply_id=supply.id,
                )
                raise FbsShipmentError(
                    "meta_validation_fail",
                    message=message,
                    context={"meta_validation": meta_context},
                    retryable=retryable,
                    http_status=409,
                ) from exc
            except WildberriesClientError as exc:
                if exc.code == "transport_error":
                    ref = wb_error_ref()
                    log_wb_client_error(
                        logger,
                        "fbs shipment WB deliver timeout",
                        exc,
                        tenant_id=tenant_id,
                        seller_id=supply.seller_id,
                        local_entity_id=supply.id,
                        wb_object_id=supply.wb_supply_id,
                        ref=ref,
                    )
                    await mark_operation_pending_confirmation(
                        session,
                        existing,
                        wb_supply_id=supply.wb_supply_id,
                        local_supply_id=supply.id,
                        error_code="wb_timeout",
                    )
                    raise FbsShipmentError(
                        "wb_timeout",
                        message="WB не подтвердил передачу — повторите операцию.",
                        context={"operation_state": "pending_confirmation"},
                        retryable=True,
                        http_status=504,
                    ) from exc
                error = _shipment_error_from_wb(
                    exc,
                    tenant_id=tenant_id,
                    seller_id=supply.seller_id,
                    local_entity_id=supply.id,
                    wb_supply_id=supply.wb_supply_id,
                    event="fbs shipment WB deliver failed",
                    retryable=False,
                    http_status=502,
                )
                await mark_operation_failed(
                    session,
                    existing,
                    error_code=error.code,
                    error_context=error.context,
                    wb_supply_id=supply.wb_supply_id,
                    local_supply_id=supply.id,
                )
                raise error from exc

            orders = await _load_locked_supply_orders(session, tenant_id, supply.id)
            await _persist_confirmed_delivery(session, supply, orders, existing, actor_user_id)
            await _fetch_supply_qr_after_deliver(session, supply, http_client, token)
            return supply

    supply = await _get_supply_for_update(
        session,
        tenant_id,
        supply_id,
        with_trbxes=True,
    )
    if supply is None:
        raise FbsShipmentError("supply_not_found")
    if supply.delivery_type not in _DELIVER_ALLOWED_DELIVERY_TYPES:
        raise FbsShipmentError("wrong_delivery_type")
    if supply.status in _DELIVER_BLOCKED_SUPPLY_STATUSES:
        raise FbsShipmentError("supply_bad_status", http_status=409)

    token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    await _sync_and_validate_deliver(
        session,
        tenant_id,
        supply,
        http_client,
        token,
        confirmed_preflight_version=confirmed_preflight_version,
        actor_user_id=actor_user_id,
    )

    operation = existing
    if operation is None:
        operation = await create_pending_deliver_operation(
            session,
            tenant_id=tenant_id,
            seller_id=supply.seller_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            local_supply_id=supply.id,
            confirmed_preflight_version=confirmed_preflight_version,
            created_by_user_id=actor_user_id,
        )

    try:
        await deliver_marketplace_supply(
            http_client,
            api_token=token,
            supply_id=supply.wb_supply_id,
        )
    except WildberriesBusinessError as exc:
        meta_context = _meta_validation_context(exc)
        message, retryable = _meta_validation_message(exc)
        await mark_operation_failed(
            session,
            operation,
            error_code="meta_validation_fail",
            error_context={"meta_validation": meta_context},
            wb_supply_id=supply.wb_supply_id,
            local_supply_id=supply.id,
        )
        raise FbsShipmentError(
            "meta_validation_fail",
            message=message,
            context={"meta_validation": meta_context},
            retryable=retryable,
            http_status=409,
        ) from exc
    except WildberriesClientError as exc:
        if exc.code == "transport_error":
            ref = wb_error_ref()
            log_wb_client_error(
                logger,
                "fbs shipment WB deliver timeout",
                exc,
                tenant_id=tenant_id,
                seller_id=supply.seller_id,
                local_entity_id=supply.id,
                wb_object_id=supply.wb_supply_id,
                ref=ref,
            )
            await mark_operation_pending_confirmation(
                session,
                operation,
                wb_supply_id=supply.wb_supply_id,
                local_supply_id=supply.id,
                error_code="wb_timeout",
            )
            raise FbsShipmentError(
                "wb_timeout",
                message="WB не подтвердил передачу — повторите операцию.",
                context={"operation_state": "pending_confirmation"},
                retryable=True,
                http_status=504,
            ) from exc
        error = _shipment_error_from_wb(
            exc,
            tenant_id=tenant_id,
            seller_id=supply.seller_id,
            local_entity_id=supply.id,
            wb_supply_id=supply.wb_supply_id,
            event="fbs shipment WB deliver failed",
            retryable=False,
            http_status=502,
        )
        await mark_operation_failed(
            session,
            operation,
            error_code=error.code,
            error_context=error.context,
            wb_supply_id=supply.wb_supply_id,
            local_supply_id=supply.id,
        )
        raise error from exc

    orders = await _load_locked_supply_orders(session, tenant_id, supply.id)
    cargo_qr_ready = True
    if supply.delivery_type == FBS_DELIVERY_TYPE_PVZ:
        cargo_qr_ready = await pvz_svc.supply_has_ready_cargo_place_qrs(session, tenant_id, supply)
    _validate_checks_pass(
        _build_delivery_checks(
            supply,
            orders,
            cargo_qr_ready=cargo_qr_ready,
        )
    )
    await _persist_confirmed_delivery(session, supply, orders, operation, actor_user_id)
    await _fetch_supply_qr_after_deliver(session, supply, http_client, token)
    return supply


async def get_supply_barcode(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    *,
    type: str = "png",
) -> bytes:
    supply = await _get_supply_read(session, tenant_id, supply_id)
    if supply is None:
        raise FbsShipmentError("supply_not_found")
    if supply.status not in {FBS_SUPPLY_STATUS_IN_DELIVERY, FBS_SUPPLY_STATUS_DONE}:
        raise FbsShipmentError("supply_bad_status", http_status=409)

    if supply.barcode_file:
        cached = _resolve_barcode_path(supply.barcode_file)
        if cached.is_file():
            return cached.read_bytes()

    if supply.marketplace == "ozon":
        client_id, api_key = await _ozon_credentials(
            session,
            tenant_id,
            supply.seller_id,
        )
        provider = OzonMarketplaceProvider(
            transport=FakeMarketplaceTransport(supply_qr=_FAKE_OZON_SUPPLY_QR)
        )
        png_bytes = await _store_ozon_supply_qr(
            session,
            supply,
            provider,
            client_id=client_id,
            api_key=api_key,
        )
        supply.barcode_file = _save_barcode_png(supply.id, png_bytes)
        await session.flush()
        return png_bytes

    token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    try:
        png_bytes = await fetch_marketplace_supply_barcode(
            http_client,
            api_token=token,
            supply_id=supply.wb_supply_id,
            type=type,
        )
    except WildberriesClientError as exc:
        raise _shipment_error_from_wb(
            exc,
            tenant_id=tenant_id,
            seller_id=supply.seller_id,
            local_entity_id=supply.id,
            wb_supply_id=supply.wb_supply_id,
            event="fbs shipment WB supply barcode fetch failed",
        ) from exc

    supply.barcode_file = _save_barcode_png(supply.id, png_bytes)
    await session.flush()
    return png_bytes


async def retry_supply_qr(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> FbsSupply:
    """Safely fetch a missing supply QR after WB delivery was confirmed (any delivery_type)."""
    supply = await _get_supply_for_update(session, tenant_id, supply_id, with_trbxes=True)
    if supply is None:
        raise FbsShipmentError("supply_not_found")
    if supply.status not in {FBS_SUPPLY_STATUS_IN_DELIVERY, FBS_SUPPLY_STATUS_DONE}:
        raise FbsShipmentError("supply_bad_status", http_status=409)

    if supply.marketplace == "ozon":
        client_id, api_key = await _ozon_credentials(
            session,
            tenant_id,
            supply.seller_id,
        )
        await _store_ozon_supply_qr(
            session,
            supply,
            OzonMarketplaceProvider(
                transport=FakeMarketplaceTransport(supply_qr=_FAKE_OZON_SUPPLY_QR)
            ),
            client_id=client_id,
            api_key=api_key,
        )
        return supply

    token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    await _fetch_supply_qr_after_deliver(session, supply, http_client, token)
    return supply
