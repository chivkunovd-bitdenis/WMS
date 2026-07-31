"""FBS PVZ shipment — cargo places (trbx), order binding, stickers."""

from __future__ import annotations

import base64
import binascii
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.settings import settings
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FBS_DELIVERY_TYPE_PVZ, FbsSupply
from app.models.fbs_trbx import FbsTrbx
from app.services.wildberries_client import (
    WildberriesClientError,
    add_orders_to_marketplace_trbx,
    create_marketplace_supply_trbx,
    fetch_marketplace_trbx_stickers,
)
from app.services.wildberries_credentials_service import (
    _seller_in_tenant,
    get_decrypted_marketplace_token,
)

MAX_TRBX_SIDE_MM = 600
MAX_TRBX_WEIGHT_G = 5000
MIN_TRBX_ORDERS = 2
MAX_SUPPLY_TRBX_VOLUME_MM3 = 1_000_000_000


class FbsShipmentPvzError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class TrbxMeta:
    id: uuid.UUID
    wb_trbx_id: str
    packaging_box_id: uuid.UUID | None
    length_mm: int | None
    width_mm: int | None
    height_mm: int | None
    weight_g: int | None
    sticker_file: str | None


def _wb_error_code(exc: WildberriesClientError) -> str:
    suffix = f"_{exc.status_code}" if exc.status_code else ""
    return f"wb_{exc.code}{suffix}"


async def _require_marketplace_token(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> str:
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsShipmentPvzError("seller_not_found")
    token = await get_decrypted_marketplace_token(session, tenant_id, seller_id)
    if not token:
        raise FbsShipmentPvzError("missing_marketplace_token")
    return token


async def _get_supply(
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


def _require_pvz_supply(supply: FbsSupply) -> None:
    if supply.delivery_type != FBS_DELIVERY_TYPE_PVZ:
        raise FbsShipmentPvzError("wrong_delivery_type")


def _trbx_volume_mm3(trbx: FbsTrbx) -> int | None:
    if trbx.length_mm is None or trbx.width_mm is None or trbx.height_mm is None:
        return None
    return trbx.length_mm * trbx.width_mm * trbx.height_mm


def _dims_volume_mm3(length_mm: int, width_mm: int, height_mm: int) -> int:
    return length_mm * width_mm * height_mm


def _validate_trbx_dims_weight(
    length_mm: int,
    width_mm: int,
    height_mm: int,
    weight_g: int,
) -> None:
    if max(length_mm, width_mm, height_mm) > MAX_TRBX_SIDE_MM:
        raise FbsShipmentPvzError("trbx_oversized")
    if weight_g > MAX_TRBX_WEIGHT_G:
        raise FbsShipmentPvzError("trbx_overweight")


def _validate_supply_volume(
    trbxes: list[FbsTrbx],
    *,
    current_trbx_id: uuid.UUID,
    new_volume_mm3: int,
) -> None:
    total = new_volume_mm3
    for trbx in trbxes:
        if trbx.id == current_trbx_id:
            continue
        volume = _trbx_volume_mm3(trbx)
        if volume is not None:
            total += volume
    if total > MAX_SUPPLY_TRBX_VOLUME_MM3:
        raise FbsShipmentPvzError("trbx_volume_exceeded")


def _sticker_relative_path(trbx_id: uuid.UUID) -> str:
    return f"fbs-trbx-stickers/{trbx_id}.png"


def _sticker_storage_root() -> Path:
    return (Path(settings.wms_data_dir) / "fbs-trbx-stickers").resolve()


def _resolve_sticker_path(rel: str) -> Path:
    root = _sticker_storage_root()
    target = (Path(settings.wms_data_dir) / rel).resolve()
    if root not in target.parents and target != root:
        raise FbsShipmentPvzError("invalid_sticker_path")
    return target


def _decode_sticker_payload(raw: object) -> bytes | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    payload = raw.strip()
    if payload.startswith("data:"):
        comma = payload.find(",")
        if comma == -1:
            return None
        payload = payload[comma + 1 :]
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        return None


def _save_sticker_png(trbx_id: uuid.UUID, png_bytes: bytes) -> str:
    rel = _sticker_relative_path(trbx_id)
    target = _resolve_sticker_path(rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png_bytes)
    return rel


def _trbx_meta(trbx: FbsTrbx) -> TrbxMeta:
    return TrbxMeta(
        id=trbx.id,
        wb_trbx_id=trbx.wb_trbx_id,
        packaging_box_id=trbx.packaging_box_id,
        length_mm=trbx.length_mm,
        width_mm=trbx.width_mm,
        height_mm=trbx.height_mm,
        weight_g=trbx.weight_g,
        sticker_file=trbx.sticker_file,
    )


async def create_trbxes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    count: int,
    http_client: httpx.AsyncClient,
    *,
    length_mm: int | None = None,
    width_mm: int | None = None,
    height_mm: int | None = None,
    weight_g: int | None = None,
) -> list[FbsTrbx]:
    if count < 1:
        raise FbsShipmentPvzError("invalid_trbx_count")

    supply = await _get_supply(session, tenant_id, supply_id, with_trbxes=True)
    if supply is None:
        raise FbsShipmentPvzError("supply_not_found")
    _require_pvz_supply(supply)

    dims_provided = (
        length_mm is not None
        and width_mm is not None
        and height_mm is not None
        and weight_g is not None
    )
    if dims_provided:
        assert length_mm is not None
        assert width_mm is not None
        assert height_mm is not None
        assert weight_g is not None
        _validate_trbx_dims_weight(length_mm, width_mm, height_mm, weight_g)
        new_volume = _dims_volume_mm3(length_mm, width_mm, height_mm) * count
        existing_volume = sum(
            vol for trbx in supply.trbxes if (vol := _trbx_volume_mm3(trbx)) is not None
        )
        if existing_volume + new_volume > MAX_SUPPLY_TRBX_VOLUME_MM3:
            raise FbsShipmentPvzError("trbx_volume_exceeded")

    token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    try:
        wb_ids = await create_marketplace_supply_trbx(
            http_client,
            api_token=token,
            supply_id=supply.wb_supply_id,
            amount=count,
        )
    except WildberriesClientError as exc:
        raise FbsShipmentPvzError(_wb_error_code(exc)) from exc

    created: list[FbsTrbx] = []
    for wb_trbx_id in wb_ids:
        trbx = FbsTrbx(
            supply_id=supply.id,
            wb_trbx_id=wb_trbx_id,
            length_mm=length_mm,
            width_mm=width_mm,
            height_mm=height_mm,
            weight_g=weight_g,
        )
        session.add(trbx)
        created.append(trbx)

    await session.flush()
    return created


async def bind_orders_to_trbx(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    trbx_id: uuid.UUID,
    order_ids: list[uuid.UUID],
    length_mm: int,
    width_mm: int,
    height_mm: int,
    weight_g: int,
    http_client: httpx.AsyncClient,
) -> FbsTrbx:
    if len(order_ids) < MIN_TRBX_ORDERS:
        raise FbsShipmentPvzError("trbx_min_orders")

    _validate_trbx_dims_weight(length_mm, width_mm, height_mm, weight_g)
    new_volume = _dims_volume_mm3(length_mm, width_mm, height_mm)

    supply = await _get_supply(session, tenant_id, supply_id, with_trbxes=True)
    if supply is None:
        raise FbsShipmentPvzError("supply_not_found")
    _require_pvz_supply(supply)

    trbx = next((row for row in supply.trbxes if row.id == trbx_id), None)
    if trbx is None:
        raise FbsShipmentPvzError("trbx_not_found")

    _validate_supply_volume(supply.trbxes, current_trbx_id=trbx_id, new_volume_mm3=new_volume)

    unique_order_ids = list(dict.fromkeys(order_ids))
    stmt = (
        select(FbsOrder)
        .where(
            FbsOrder.id.in_(unique_order_ids),
            FbsOrder.tenant_id == tenant_id,
            FbsOrder.supply_id == supply_id,
        )
        .with_for_update()
    )
    result = await session.execute(stmt)
    orders = list(result.scalars().all())
    if len(orders) != len(unique_order_ids):
        raise FbsShipmentPvzError("order_not_in_supply")

    for order in orders:
        if order.trbx_id is not None and order.trbx_id != trbx_id:
            raise FbsShipmentPvzError("order_already_in_trbx")

    wb_order_ids = [int(order.wb_order_id) for order in orders]
    token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    try:
        await add_orders_to_marketplace_trbx(
            http_client,
            api_token=token,
            supply_id=supply.wb_supply_id,
            trbx_id=trbx.wb_trbx_id,
            order_ids=wb_order_ids,
        )
    except WildberriesClientError as exc:
        raise FbsShipmentPvzError(_wb_error_code(exc)) from exc

    trbx.length_mm = length_mm
    trbx.width_mm = width_mm
    trbx.height_mm = height_mm
    trbx.weight_g = weight_g
    for order in orders:
        order.trbx_id = trbx.id

    await session.flush()
    return trbx


async def fetch_trbx_stickers(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    *,
    type: str = "png",
) -> list[TrbxMeta]:
    supply = await _get_supply(session, tenant_id, supply_id, with_trbxes=True)
    if supply is None:
        raise FbsShipmentPvzError("supply_not_found")
    _require_pvz_supply(supply)
    if not supply.trbxes:
        return []

    uncached: list[FbsTrbx] = []
    for trbx in supply.trbxes:
        if trbx.sticker_file:
            cached = _resolve_sticker_path(trbx.sticker_file)
            if cached.is_file():
                continue
        uncached.append(trbx)

    if uncached:
        token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
        try:
            stickers = await fetch_marketplace_trbx_stickers(
                http_client,
                api_token=token,
                supply_id=supply.wb_supply_id,
                trbx_ids=[trbx.wb_trbx_id for trbx in uncached],
                type=type,
            )
        except WildberriesClientError as exc:
            raise FbsShipmentPvzError(_wb_error_code(exc)) from exc

        by_wb_id: dict[str, dict[str, Any]] = {}
        for row in stickers:
            for key in ("trbxId", "trbx_id", "id"):
                wb_id = row.get(key)
                if wb_id is not None:
                    by_wb_id[str(wb_id)] = row
                    break

        for trbx in uncached:
            sticker_row = by_wb_id.get(trbx.wb_trbx_id)
            if sticker_row is None:
                raise FbsShipmentPvzError("wb_invalid_response")
            png_bytes: bytes | None = None
            for key in ("file", "barcode", "image"):
                png_bytes = _decode_sticker_payload(sticker_row.get(key))
                if png_bytes is not None:
                    break
            if png_bytes is None:
                raise FbsShipmentPvzError("wb_invalid_response")
            trbx.sticker_file = _save_sticker_png(trbx.id, png_bytes)

    await session.flush()
    return [_trbx_meta(trbx) for trbx in supply.trbxes]
