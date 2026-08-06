"""FBS shipment — delivery preflight, safe deliver, supply barcode."""

from __future__ import annotations

import hashlib
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
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
)
from app.models.fbs_packing_box import FbsPackingBox, FbsPackingBoxItem
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
from app.services import fbs_marking_service as marking_svc
from app.services import fbs_shipment_pvz_service as pvz_svc
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
from app.services.wb_marketplace_orders_service import (
    _apply_wb_status_to_order,
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
from app.services.wildberries_errors import WildberriesBusinessError, WildberriesClientError
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


PACKING_BOX_STATUS_CLOSED = "closed"


@dataclass(frozen=True)
class PackingDistribution:
    box_ids: tuple[uuid.UUID, ...]
    box_statuses: tuple[tuple[uuid.UUID, str], ...]
    assignments: tuple[tuple[uuid.UUID, uuid.UUID], ...]

    def assignment_counts(self) -> dict[uuid.UUID, int]:
        counts: dict[uuid.UUID, int] = {}
        for order_id, _box_id in self.assignments:
            counts[order_id] = counts.get(order_id, 0) + 1
        return counts


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


async def _load_locked_supply_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> list[FbsOrder]:
    stmt = (
        select(FbsOrder)
        .where(
            FbsOrder.supply_id == supply_id,
            FbsOrder.tenant_id == tenant_id,
        )
        .with_for_update()
        .options(
            selectinload(FbsOrder.product),
            selectinload(FbsOrder.markings),
        )
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _load_supply_orders_read(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> list[FbsOrder]:
    stmt = (
        select(FbsOrder)
        .where(
            FbsOrder.supply_id == supply_id,
            FbsOrder.tenant_id == tenant_id,
        )
        .options(
            selectinload(FbsOrder.product),
            selectinload(FbsOrder.markings),
        )
    )
    result = await session.execute(stmt)
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
    return any(marking.kind == MARKING_KIND_SGTIN for marking in order.markings)


async def _sync_supply_orders_from_wb(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
    http_client: httpx.AsyncClient,
    token: str,
) -> list[FbsOrder]:
    orders = await _load_supply_orders_read(session, tenant_id, supply.id)
    if not orders:
        supply.last_wb_sync_at = datetime.now(UTC)
        await session.flush()
        return orders

    wb_ids = [int(order.wb_order_id) for order in orders]
    for batch in split_marketplace_order_id_batches(wb_ids):
        status_rows = await fetch_marketplace_orders_status(
            http_client,
            api_token=token,
            order_ids=batch,
        )
        by_id = {int(row["id"]): row for row in status_rows if row.get("id") is not None}
        for order in orders:
            row = by_id.get(int(order.wb_order_id))
            if row is None:
                continue
            wb_status = _wb_status_from_row(row)
            if wb_status is not None:
                await _apply_wb_status_to_order(session, order, wb_status)

    for order in orders:
        with suppress(marking_svc.FbsMarkingError):
            await marking_svc.sync_order_marking_statuses(session, tenant_id, order.id, http_client)

    supply.last_wb_sync_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(supply)
    return await _load_supply_orders_read(session, tenant_id, supply.id)


async def _load_packing_distribution(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> PackingDistribution:
    box_rows = tuple(
        (
            await session.execute(
                select(FbsPackingBox.id, FbsPackingBox.status)
                .where(
                    FbsPackingBox.tenant_id == tenant_id,
                    FbsPackingBox.supply_id == supply_id,
                )
                .order_by(FbsPackingBox.id)
            )
        ).tuples()
    )
    if not box_rows:
        return PackingDistribution(box_ids=(), box_statuses=(), assignments=())
    box_ids = tuple(row[0] for row in box_rows)
    box_statuses = tuple((row[0], str(row[1])) for row in box_rows)
    assignments = tuple(
        (
            await session.execute(
                select(FbsPackingBoxItem.fbs_order_id, FbsPackingBoxItem.box_id)
                .where(
                    FbsPackingBoxItem.tenant_id == tenant_id,
                    FbsPackingBoxItem.box_id.in_(box_ids),
                )
                .order_by(FbsPackingBoxItem.fbs_order_id, FbsPackingBoxItem.box_id)
            )
        ).tuples()
    )
    return PackingDistribution(
        box_ids=box_ids,
        box_statuses=box_statuses,
        assignments=assignments,
    )


def _compute_preflight_version(
    supply: FbsSupply,
    orders: list[FbsOrder],
    *,
    cargo_qr_ready: bool,
    distribution: PackingDistribution,
) -> str:
    parts = [
        str(supply.id),
        supply.status,
        supply.delivery_type,
        str(cargo_qr_ready),
    ]
    parts.extend(
        f"box:{box_id}:{status}" for box_id, status in distribution.box_statuses
    )
    parts.extend(f"assignment:{order_id}:{box_id}" for order_id, box_id in distribution.assignments)
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
    distribution: PackingDistribution,
) -> list[DeliveryCheck]:
    checks: list[DeliveryCheck] = []

    if supply.status in _DELIVER_BLOCKED_SUPPLY_STATUSES:
        checks.append(
            DeliveryCheck(
                code="supply_bad_status",
                message="Состав поставки уже зафиксирован в WB или поставка закрыта.",
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
                    message="Заказ не готов к фиксации состава поставки.",
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
                    message="Метаданные WB не позволяют зафиксировать состав поставки.",
                    ok=False,
                    order_id=order.id,
                )
            )
        elif order.required_meta_json:
            checks.append(
                DeliveryCheck(
                    code="marking_allowed",
                    message="Метаданные WB позволяют зафиксировать состав поставки.",
                    ok=True,
                    order_id=order.id,
                )
            )

    if not distribution.box_ids:
        checks.append(
            DeliveryCheck(
                code="packing_boxes_required",
                message="Создайте физические короба WMS.",
                ok=False,
            )
        )
    else:
        checks.append(
            DeliveryCheck(
                code="packing_boxes_ready",
                message="Физические короба WMS созданы.",
                ok=True,
            )
        )

    assignment_counts = distribution.assignment_counts()
    missing_distribution = [
        order
        for order in orders
        if order.status == FBS_ORDER_STATUS_PACKED and assignment_counts.get(order.id, 0) != 1
    ]
    if missing_distribution:
        for order in missing_distribution:
            checks.append(
                DeliveryCheck(
                    code="orders_not_distributed",
                    message="Упакованный заказ не распределён ровно в один короб.",
                    ok=False,
                    order_id=order.id,
                )
            )
    elif orders:
        checks.append(
            DeliveryCheck(
                code="orders_distributed",
                message="Упакованные заказы полностью распределены по коробам.",
                ok=True,
            )
        )

    all_boxes_closed = bool(distribution.box_ids) and all(
        status == PACKING_BOX_STATUS_CLOSED for _, status in distribution.box_statuses
    )
    orders_fully_distributed = bool(orders) and not missing_distribution
    if not distribution.box_ids:
        pass
    elif not all_boxes_closed:
        checks.append(
            DeliveryCheck(
                code="packing_boxes_not_closed",
                message="Закройте все физические короба перед сдачей в WB.",
                ok=False,
            )
        )
    elif orders_fully_distributed:
        checks.append(
            DeliveryCheck(
                code="packing_boxes_closed",
                message="Все физические короба закрыты.",  # noqa: RUF001
                ok=True,
            )
        )

    if supply.delivery_type == FBS_DELIVERY_TYPE_PVZ:
        if not supply.trbxes:
            checks.append(
                DeliveryCheck(
                    code="cargo_places_required",
                    message="Создайте грузоместа для ПВЗ.",
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
            raise FbsShipmentError(check.code, message=check.message)


async def _sync_and_validate_deliver(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
    http_client: httpx.AsyncClient,
    token: str,
    *,
    confirmed_preflight_version: str | None = None,
) -> tuple[list[FbsOrder], bool]:
    orders = await _sync_supply_orders_from_wb(session, tenant_id, supply, http_client, token)
    cargo_qr_ready = True
    if supply.delivery_type == FBS_DELIVERY_TYPE_PVZ:
        cargo_qr_ready = await pvz_svc.supply_has_ready_cargo_place_qrs(session, tenant_id, supply)
    distribution = await _load_packing_distribution(session, tenant_id, supply.id)
    if confirmed_preflight_version is not None:
        current_version = _compute_preflight_version(
            supply,
            orders,
            cargo_qr_ready=cargo_qr_ready,
            distribution=distribution,
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
        distribution=distribution,
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
) -> DeliveryPreflightResult:
    supply = await _get_supply_read(session, tenant_id, supply_id, with_trbxes=True)
    if supply is None:
        raise FbsShipmentError("supply_not_found")
    if supply.delivery_type not in _DELIVER_ALLOWED_DELIVERY_TYPES:
        raise FbsShipmentError("wrong_delivery_type")

    token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    orders = await _sync_supply_orders_from_wb(session, tenant_id, supply, http_client, token)
    cargo_qr_ready = True
    if supply.delivery_type == FBS_DELIVERY_TYPE_PVZ:
        cargo_qr_ready = await pvz_svc.supply_has_ready_cargo_place_qrs(session, tenant_id, supply)

    distribution = await _load_packing_distribution(session, tenant_id, supply.id)
    checks = _build_delivery_checks(
        supply,
        orders,
        cargo_qr_ready=cargo_qr_ready,
        distribution=distribution,
    )
    checked_at = datetime.now(UTC)
    version = _compute_preflight_version(
        supply,
        orders,
        cargo_qr_ready=cargo_qr_ready,
        distribution=distribution,
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
) -> None:
    now = datetime.now(UTC)
    supply.status = FBS_SUPPLY_STATUS_IN_DELIVERY
    supply.delivered_at = now
    for order in orders:
        if order.status == FBS_ORDER_STATUS_PACKED:
            order.status = FBS_ORDER_STATUS_IN_DELIVERY
    await session.flush()


async def _fetch_supply_qr_after_deliver(
    session: AsyncSession,
    supply: FbsSupply,
    http_client: httpx.AsyncClient,
    token: str,
) -> None:
    if supply.delivery_type != FBS_DELIVERY_TYPE_WAREHOUSE_SC:
        return
    if supply.barcode_file and supply.barcode_asset_id:
        return
    try:
        png_bytes = await fetch_marketplace_supply_barcode(
            http_client,
            api_token=token,
            supply_id=supply.wb_supply_id,
        )
    except WildberriesClientError as exc:
        raise FbsShipmentError(_wb_error_code(exc)) from exc
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
) -> None:
    """Durably checkpoint WB delivery before fetching its optional QR asset."""
    await _apply_local_delivered(session, supply, orders)
    await mark_deliver_operation_confirmed(
        session,
        operation,
        wb_supply_id=supply.wb_supply_id,
        local_supply_id=supply.id,
    )
    # The route only commits selected errors.  A barcode download failure must
    # therefore not roll back the already confirmed WB delivery.
    await session.commit()


async def deliver_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    *,
    idempotency_key: str,
    confirmed_preflight_version: str,
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
                message="Фиксация состава в WB уже выполняется.",
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
            )
            if reconcile_state == WB_OPERATION_STATE_CONFIRMED:
                orders = await _load_locked_supply_orders(session, tenant_id, supply.id)
                await _persist_confirmed_delivery(session, supply, orders, existing)
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
                    message=exc.message or "WB отклонил метаданные заказов.",
                    context={"meta_validation": meta_context},
                    http_status=409,
                ) from exc
            except WildberriesClientError as exc:
                if exc.code == "transport_error":
                    await mark_operation_pending_confirmation(
                        session,
                        existing,
                        wb_supply_id=supply.wb_supply_id,
                        local_supply_id=supply.id,
                        error_code="wb_timeout",
                    )
                    raise FbsShipmentError(
                        "wb_timeout",
                        message="WB не подтвердил фиксацию состава — повторите операцию.",
                        context={"operation_state": "pending_confirmation"},
                        retryable=True,
                        http_status=504,
                    ) from exc
                await mark_operation_failed(
                    session,
                    existing,
                    error_code=_wb_error_code(exc),
                    wb_supply_id=supply.wb_supply_id,
                    local_supply_id=supply.id,
                )
                raise FbsShipmentError(_wb_error_code(exc), http_status=502) from exc

            orders = await _load_locked_supply_orders(session, tenant_id, supply.id)
            await _persist_confirmed_delivery(session, supply, orders, existing)
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
        )

    try:
        await deliver_marketplace_supply(
            http_client,
            api_token=token,
            supply_id=supply.wb_supply_id,
        )
    except WildberriesBusinessError as exc:
        meta_context = _meta_validation_context(exc)
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
            message=exc.message or "WB отклонил метаданные заказов.",
            context={"meta_validation": meta_context},
            http_status=409,
        ) from exc
    except WildberriesClientError as exc:
        if exc.code == "transport_error":
            await mark_operation_pending_confirmation(
                session,
                operation,
                wb_supply_id=supply.wb_supply_id,
                local_supply_id=supply.id,
                error_code="wb_timeout",
            )
            raise FbsShipmentError(
                "wb_timeout",
                message="WB не подтвердил фиксацию состава — повторите операцию.",
                context={"operation_state": "pending_confirmation"},
                retryable=True,
                http_status=504,
            ) from exc
        await mark_operation_failed(
            session,
            operation,
            error_code=_wb_error_code(exc),
            wb_supply_id=supply.wb_supply_id,
            local_supply_id=supply.id,
        )
        raise FbsShipmentError(_wb_error_code(exc), http_status=502) from exc

    orders = await _load_locked_supply_orders(session, tenant_id, supply.id)
    cargo_qr_ready = True
    if supply.delivery_type == FBS_DELIVERY_TYPE_PVZ:
        cargo_qr_ready = await pvz_svc.supply_has_ready_cargo_place_qrs(session, tenant_id, supply)
    distribution = await _load_packing_distribution(session, tenant_id, supply.id)
    _validate_checks_pass(
        _build_delivery_checks(
            supply,
            orders,
            cargo_qr_ready=cargo_qr_ready,
            distribution=distribution,
        )
    )
    await _persist_confirmed_delivery(session, supply, orders, operation)
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
    if supply.delivery_type != FBS_DELIVERY_TYPE_WAREHOUSE_SC:
        raise FbsShipmentError("wrong_delivery_type", http_status=409)
    if supply.status not in {FBS_SUPPLY_STATUS_IN_DELIVERY, FBS_SUPPLY_STATUS_DONE}:
        raise FbsShipmentError("supply_bad_status", http_status=409)

    if supply.barcode_file:
        cached = _resolve_barcode_path(supply.barcode_file)
        if cached.is_file():
            return cached.read_bytes()

    token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    try:
        png_bytes = await fetch_marketplace_supply_barcode(
            http_client,
            api_token=token,
            supply_id=supply.wb_supply_id,
            type=type,
        )
    except WildberriesClientError as exc:
        raise FbsShipmentError(_wb_error_code(exc)) from exc

    supply.barcode_file = _save_barcode_png(supply.id, png_bytes)
    await session.flush()
    return png_bytes


async def retry_supply_qr(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> FbsSupply:
    """Safely fetch a missing warehouse/SC QR after WB delivery was confirmed."""
    supply = await _get_supply_for_update(session, tenant_id, supply_id, with_trbxes=True)
    if supply is None:
        raise FbsShipmentError("supply_not_found")
    if supply.delivery_type != FBS_DELIVERY_TYPE_WAREHOUSE_SC:
        raise FbsShipmentError("wrong_delivery_type", http_status=409)
    if supply.status not in {FBS_SUPPLY_STATUS_IN_DELIVERY, FBS_SUPPLY_STATUS_DONE}:
        raise FbsShipmentError("supply_bad_status", http_status=409)

    token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    await _fetch_supply_qr_after_deliver(session, supply, http_client, token)
    return supply
