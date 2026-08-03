"""FBS warehouse/SC shipment — deliver supply to WB and cache supply barcode."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

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
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_PVZ,
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_DONE,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.fbs_trbx import FbsTrbx
from app.services.wildberries_client import (
    WildberriesClientError,
    deliver_marketplace_supply,
    fetch_marketplace_supply_barcode,
)
from app.services.wildberries_credentials_service import (
    _seller_in_tenant,
    get_decrypted_marketplace_token,
)

_DELIVER_READY_ORDER_STATUSES = frozenset({FBS_ORDER_STATUS_PACKED})
_PACKAGING_PENDING_ORDER_STATUSES = frozenset(
    {FBS_ORDER_STATUS_IN_SUPPLY, FBS_ORDER_STATUS_ASSEMBLING}
)
_DELIVER_ALLOWED_DELIVERY_TYPES = frozenset(
    {FBS_DELIVERY_TYPE_WAREHOUSE_SC, FBS_DELIVERY_TYPE_PVZ}
)
_DELIVER_BLOCKED_SUPPLY_STATUSES = frozenset(
    {
        FBS_SUPPLY_STATUS_IN_DELIVERY,
        FBS_SUPPLY_STATUS_DONE,
    }
)


class FbsShipmentError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


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
) -> FbsSupply | None:
    stmt = (
        select(FbsSupply)
        .where(
            FbsSupply.id == supply_id,
            FbsSupply.tenant_id == tenant_id,
        )
        .with_for_update()
    )
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


def _validate_orders_deliverable(orders: list[FbsOrder]) -> None:
    if not orders:
        raise FbsShipmentError("supply_empty")
    if any(order.status == FBS_ORDER_STATUS_CANCELLED for order in orders):
        raise FbsShipmentError("supply_has_cancelled_orders")
    for order in orders:
        if order.status in _PACKAGING_PENDING_ORDER_STATUSES:
            raise FbsShipmentError("packaging_required")
        if order.status not in _DELIVER_READY_ORDER_STATUSES:
            raise FbsShipmentError("orders_not_ready")
        product = order.product
        if product is not None and product.requires_honest_sign and not _order_has_sgtin_marking(
            order
        ):
            raise FbsShipmentError("marking_required")


async def _get_supply_read(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> FbsSupply | None:
    stmt = select(FbsSupply).where(
        FbsSupply.id == supply_id,
        FbsSupply.tenant_id == tenant_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _order_has_sgtin_marking(order: FbsOrder) -> bool:
    return any(marking.kind == MARKING_KIND_SGTIN for marking in order.markings)


async def deliver_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> FbsSupply:
    supply = await _get_supply_for_update(session, tenant_id, supply_id)
    if supply is None:
        raise FbsShipmentError("supply_not_found")
    if supply.delivery_type not in _DELIVER_ALLOWED_DELIVERY_TYPES:
        raise FbsShipmentError("wrong_delivery_type")
    if supply.status in _DELIVER_BLOCKED_SUPPLY_STATUSES:
        raise FbsShipmentError("supply_bad_status")
    if supply.status != FBS_SUPPLY_STATUS_PACKED:
        raise FbsShipmentError("packaging_required")

    orders = await _load_locked_supply_orders(session, tenant_id, supply.id)
    _validate_orders_deliverable(orders)
    if supply.delivery_type == FBS_DELIVERY_TYPE_PVZ and any(
        order.trbx_id is None for order in orders
    ):
        raise FbsShipmentError("trbx_required")
    if supply.delivery_type == FBS_DELIVERY_TYPE_PVZ:
        trbxes = list(
            (
                await session.execute(
                    select(FbsTrbx)
                    .where(FbsTrbx.supply_id == supply.id)
                    .with_for_update()
                )
            ).scalars()
        )
        if any(trbx.packaging_box_id is None for trbx in trbxes):
            raise FbsShipmentError("packaging_box_required")

    token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    try:
        await deliver_marketplace_supply(
            http_client,
            api_token=token,
            supply_id=supply.wb_supply_id,
        )
    except WildberriesClientError as exc:
        raise FbsShipmentError(_wb_error_code(exc)) from exc

    if any(order.status == FBS_ORDER_STATUS_CANCELLED for order in orders):
        raise FbsShipmentError("supply_has_cancelled_orders")
    for order in orders:
        if order.status not in _DELIVER_READY_ORDER_STATUSES:
            raise FbsShipmentError("orders_not_ready")

    now = datetime.now(UTC)
    supply.status = FBS_SUPPLY_STATUS_IN_DELIVERY
    supply.delivered_at = now
    for order in orders:
        order.status = FBS_ORDER_STATUS_IN_DELIVERY

    await session.flush()
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
