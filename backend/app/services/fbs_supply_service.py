"""FBS supply assembly — create WB supply, add orders, picking list, stickers."""

from __future__ import annotations

import base64
import binascii
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.settings import settings
from app.models.fbs_order import FBS_ORDER_STATUS_IN_SUPPLY, FBS_ORDER_STATUS_NEW, FbsOrder
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_PVZ,
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_DRAFT,
    FbsSupply,
)
from app.services.catalog_service import get_warehouse
from app.services.wildberries_client import (
    WildberriesClientError,
    add_order_to_marketplace_supply,
    create_marketplace_supply,
    fetch_marketplace_order_stickers,
)
from app.services.wildberries_credentials_service import (
    _seller_in_tenant,
    get_decrypted_marketplace_token,
)

_VALID_DELIVERY_TYPES = {FBS_DELIVERY_TYPE_WAREHOUSE_SC, FBS_DELIVERY_TYPE_PVZ}


class FbsSupplyError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class PickingListItem:
    article: str
    sku_code: str | None
    size: str | None
    product_name: str
    quantity: int


@dataclass(frozen=True)
class StickerMeta:
    order_id: uuid.UUID
    wb_order_id: int
    sticker_code: str | None
    sticker_file: str | None


def _wb_error_code(exc: WildberriesClientError) -> str:
    suffix = f"_{exc.status_code}" if exc.status_code else ""
    return f"wb_{exc.code}{suffix}"


async def _require_marketplace_token(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> str:
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsSupplyError("seller_not_found")
    token = await get_decrypted_marketplace_token(session, tenant_id, seller_id)
    if not token:
        raise FbsSupplyError("missing_marketplace_token")
    return token


async def _get_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    with_orders: bool = False,
) -> FbsSupply | None:
    stmt = select(FbsSupply).where(
        FbsSupply.id == supply_id,
        FbsSupply.tenant_id == tenant_id,
    )
    if with_orders:
        stmt = stmt.options(
            selectinload(FbsSupply.orders).selectinload(FbsOrder.product)
        )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _sticker_relative_path(order_id: uuid.UUID) -> str:
    return f"fbs-stickers/{order_id}.png"


def _save_sticker_png(order_id: uuid.UUID, png_bytes: bytes) -> str:
    rel = _sticker_relative_path(order_id)
    root = Path(settings.wms_data_dir)
    target = (root / rel).resolve()
    root_resolved = root.resolve()
    if root_resolved not in target.parents and target != root_resolved:
        raise FbsSupplyError("invalid_sticker_path")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png_bytes)
    return rel


def _decode_sticker_file(raw: Any) -> bytes | None:
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


async def create_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    name: str,
    delivery_type: str,
    cargo_type: str | None = None,
    wb_office_id: int | None = None,
    http_client: httpx.AsyncClient,
) -> FbsSupply:
    if delivery_type not in _VALID_DELIVERY_TYPES:
        raise FbsSupplyError("invalid_delivery_type")
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsSupplyError("seller_not_found")
    wh = await get_warehouse(session, tenant_id, warehouse_id)
    if wh is None:
        raise FbsSupplyError("warehouse_not_found")

    token = await _require_marketplace_token(session, tenant_id, seller_id)
    try:
        wb_row = await create_marketplace_supply(http_client, api_token=token, name=name)
    except WildberriesClientError as exc:
        raise FbsSupplyError(_wb_error_code(exc)) from exc

    wb_supply_id_raw = wb_row.get("id")
    if wb_supply_id_raw is None:
        raise FbsSupplyError("wb_invalid_response")
    wb_supply_id = str(wb_supply_id_raw)

    supply = FbsSupply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_supply_id=wb_supply_id,
        name=name,
        status=FBS_SUPPLY_STATUS_DRAFT,
        delivery_type=delivery_type,
        cargo_type=cargo_type,
        wb_office_id=wb_office_id,
    )
    session.add(supply)
    await session.flush()
    return supply


async def get_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    with_orders: bool = True,
) -> FbsSupply:
    supply = await _get_supply(session, tenant_id, supply_id, with_orders=with_orders)
    if supply is None:
        raise FbsSupplyError("supply_not_found")
    return supply


async def add_order_to_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    order_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> FbsSupply:
    supply = await _get_supply(session, tenant_id, supply_id, with_orders=True)
    if supply is None:
        raise FbsSupplyError("supply_not_found")
    if supply.status != FBS_SUPPLY_STATUS_DRAFT:
        raise FbsSupplyError("supply_not_editable")

    order_stmt = (
        select(FbsOrder)
        .where(
            FbsOrder.id == order_id,
            FbsOrder.tenant_id == tenant_id,
            FbsOrder.seller_id == supply.seller_id,
        )
        .with_for_update()
    )
    order_result = await session.execute(order_stmt)
    order = order_result.scalar_one_or_none()
    if order is None:
        raise FbsSupplyError("order_not_found")
    if order.warehouse_id is None:
        raise FbsSupplyError("order_warehouse_unmapped")
    if order.warehouse_id != supply.warehouse_id:
        raise FbsSupplyError("order_warehouse_mismatch")
    if order.supply_id is not None and order.supply_id != supply_id:
        raise FbsSupplyError("order_already_in_supply")
    if order.status != FBS_ORDER_STATUS_NEW:
        raise FbsSupplyError("order_bad_status")

    token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    try:
        await add_order_to_marketplace_supply(
            http_client,
            api_token=token,
            supply_id=supply.wb_supply_id,
            order_id=int(order.wb_order_id),
        )
    except WildberriesClientError as exc:
        raise FbsSupplyError(_wb_error_code(exc)) from exc

    order.supply_id = supply.id
    order.status = FBS_ORDER_STATUS_IN_SUPPLY
    await session.flush()
    await session.refresh(supply, attribute_names=["orders"])
    return supply


async def get_picking_list(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> list[PickingListItem]:
    supply = await _get_supply(session, tenant_id, supply_id, with_orders=True)
    if supply is None:
        raise FbsSupplyError("supply_not_found")

    groups: dict[tuple[str, str | None, str | None, str], int] = defaultdict(int)
    for order in supply.orders:
        product = order.product
        article = order.wb_article or (product.sku_code if product is not None else "") or ""
        sku_code = product.sku_code if product is not None else None
        size = product.wb_size if product is not None and product.wb_size else None
        product_name = product.name if product is not None else (order.wb_article or "Unknown")
        key = (article, sku_code, size, product_name)
        groups[key] += 1

    items = [
        PickingListItem(
            article=article,
            sku_code=sku_code,
            size=size,
            product_name=product_name,
            quantity=qty,
        )
        for (article, sku_code, size, product_name), qty in sorted(groups.items())
    ]
    return items


async def fetch_and_cache_stickers(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    *,
    force: bool = False,
) -> list[StickerMeta]:
    supply = await _get_supply(session, tenant_id, supply_id, with_orders=True)
    if supply is None:
        raise FbsSupplyError("supply_not_found")
    if not supply.orders:
        return []

    orders_to_fetch = [
        order
        for order in supply.orders
        if force or not order.sticker_file
    ]
    if orders_to_fetch:
        token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
        order_ids = [int(order.wb_order_id) for order in orders_to_fetch]
        try:
            sticker_rows = await fetch_marketplace_order_stickers(
                http_client,
                api_token=token,
                order_ids=order_ids,
            )
        except WildberriesClientError as exc:
            raise FbsSupplyError(_wb_error_code(exc)) from exc

        by_wb_id: dict[int, dict[str, Any]] = {}
        for row in sticker_rows:
            oid_raw = row.get("orderId") or row.get("order_id")
            if oid_raw is not None:
                by_wb_id[int(oid_raw)] = row

        for order in orders_to_fetch:
            sticker_row = by_wb_id.get(int(order.wb_order_id))
            if sticker_row is None:
                raise FbsSupplyError("wb_stickers_incomplete")
            barcode = sticker_row.get("barcode")
            if isinstance(barcode, str):
                order.sticker_code = barcode
            file_raw = sticker_row.get("file")
            png_bytes = _decode_sticker_file(file_raw)
            if png_bytes is not None:
                order.sticker_file = _save_sticker_png(order.id, png_bytes)

        still_missing = [
            order
            for order in orders_to_fetch
            if not order.sticker_file and not order.sticker_code
        ]
        if still_missing:
            raise FbsSupplyError("wb_stickers_incomplete")

    await session.flush()
    return [
        StickerMeta(
            order_id=order.id,
            wb_order_id=int(order.wb_order_id),
            sticker_code=order.sticker_code,
            sticker_file=order.sticker_file,
        )
        for order in supply.orders
    ]
