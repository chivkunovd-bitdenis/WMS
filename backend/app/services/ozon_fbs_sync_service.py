"""Ozon FBS synchronization behind the shared marketplace provider boundary.

The current task runs this code only with ``FakeMarketplaceTransport``.  The
service still performs the real local side of the contract: provider rows are
upserted into the shared FBS tables, statuses are mapped to existing local
states, and stock payloads are built from the same physical allocation pool.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_order import (
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_DONE,
    FBS_ORDER_STATUS_EXTERNAL_PROCESSING,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_NEW,
    MAPPING_STATUS_MAPPED,
    MAPPING_STATUS_MISSING,
    RESERVE_STATUS_NO_STOCK,
    RESERVE_STATUS_SKIPPED_NO_PRODUCT,
    RESERVE_STATUS_WAREHOUSE_UNMAPPED,
    FbsOrder,
    FbsOrderProduct,
)
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.schemas.ozon_fbs_api import OzonPostingV4PostingFbsUnfulfilledListResponsePostingsProducts
from app.services.marketplace_account_service import MarketplaceAccountService
from app.services.marketplace_provider import OzonMarketplaceProvider
from app.services.wb_marketplace_orders_service import _release_reservation, _try_reserve_order

OZON_FBS_DEADLINE_HOURS = 120
_OZON_NEW_STATUSES = frozenset({"new", "awaiting_packaging", "awaiting_deliver"})
_OZON_DELIVERY_STATUSES = frozenset({"delivering", "driver_pickup", "sent_by_seller"})
_OZON_DONE_STATUSES = frozenset({"delivered", "done"})
_OZON_CANCELLED_STATUSES = frozenset(
    {"cancelled", "canceled", "cancelled_from_split_pending", "client_arbitration"}
)


def _text(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int):
            return str(value)
    return None


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(tz=UTC)


def _legacy_numeric_order_id(external_order_id: str) -> int:
    """Fill the legacy non-null WB id without sharing WB's positive id space."""
    digest = hashlib.blake2b(external_order_id.encode("utf-8"), digest_size=8).digest()
    return -(int.from_bytes(digest, "big", signed=False) & ((1 << 63) - 1)) or -1


def _local_status(raw_status: str | None) -> str:
    normalized = (raw_status or "").strip().lower()
    if normalized in _OZON_NEW_STATUSES:
        return FBS_ORDER_STATUS_NEW
    if normalized in _OZON_DELIVERY_STATUSES:
        return FBS_ORDER_STATUS_IN_DELIVERY
    if normalized in _OZON_DONE_STATUSES:
        return FBS_ORDER_STATUS_DONE
    if normalized in _OZON_CANCELLED_STATUSES:
        return FBS_ORDER_STATUS_CANCELLED
    return FBS_ORDER_STATUS_EXTERNAL_PROCESSING


async def _credentials(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> tuple[str, str]:
    return await MarketplaceAccountService(session).stored_credentials(tenant_id, seller_id)


async def _product_id_for_row(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    row: dict[str, Any],
) -> uuid.UUID | None:
    sku = _text(row, "sku", "product_sku")
    offer_id = _text(row, "offer_id", "offerId")
    if sku is None and offer_id is None:
        return None
    identity_filters = []
    if sku is not None:
        identity_filters.append(ProductMarketplaceLink.external_sku == sku)
    if offer_id is not None:
        identity_filters.append(ProductMarketplaceLink.external_offer_id == offer_id)
    stmt = select(ProductMarketplaceLink.product_id).where(
        ProductMarketplaceLink.tenant_id == tenant_id,
        ProductMarketplaceLink.seller_id == seller_id,
        ProductMarketplaceLink.marketplace == "ozon",
        ProductMarketplaceLink.is_active.is_(True),
        or_(*identity_filters),
    )
    rows = list((await session.execute(stmt.limit(2))).scalars().all())
    return rows[0] if len(rows) == 1 else None


async def _binding_for_row(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    row: dict[str, Any],
) -> FbsWarehouseBinding | None:
    external_warehouse_id = _text(row, "warehouse_id", "warehouseId")
    if external_warehouse_id is None:
        return None
    stmt = select(FbsWarehouseBinding).where(
        FbsWarehouseBinding.tenant_id == tenant_id,
        FbsWarehouseBinding.seller_id == seller_id,
        FbsWarehouseBinding.marketplace == "ozon",
        FbsWarehouseBinding.external_warehouse_id == external_warehouse_id,
        FbsWarehouseBinding.is_active.is_(True),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _posting_products_for_row(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    row: dict[str, Any],
) -> list[FbsOrderProduct]:
    raw_products = row.get("products")
    if not isinstance(raw_products, list):
        return []

    positions: list[FbsOrderProduct] = []
    for position_index, raw_product in enumerate(raw_products):
        product_row = OzonPostingV4PostingFbsUnfulfilledListResponsePostingsProducts.model_validate(
            raw_product
        )
        provider_data = product_row.model_dump(mode="json", exclude_none=True)
        positions.append(
            FbsOrderProduct(
                product_id=await _product_id_for_row(session, tenant_id, seller_id, provider_data),
                ozon_sku=product_row.sku,
                offer_id=product_row.offer_id,
                name=product_row.name,
                quantity=int(product_row.quantity or 0),
                position_index=position_index,
                provider_data_json=provider_data,
            )
        )
    return positions


def _primary_product_id(
    positions: list[FbsOrderProduct], fallback_product_id: uuid.UUID | None
) -> uuid.UUID | None:
    return next(
        (position.product_id for position in positions if position.product_id is not None),
        fallback_product_id,
    )


def _positions_are_mapped(
    positions: list[FbsOrderProduct], fallback_product_id: uuid.UUID | None
) -> bool:
    return (
        all(position.product_id is not None for position in positions)
        if positions
        else fallback_product_id is not None
    )


def _position_signature(position: FbsOrderProduct) -> tuple[int | None, int, dict[str, Any] | None]:
    return position.ozon_sku, position.quantity, position.provider_data_json


async def _apply_status(session: AsyncSession, order: FbsOrder, raw_status: str | None) -> bool:
    normalized = (raw_status or "").strip().lower() or None
    local = _local_status(normalized)
    changed = order.status != local or order.wb_status != normalized
    order.wb_status = normalized
    order.supplier_status = "new" if local == FBS_ORDER_STATUS_NEW else normalized
    order.status = local
    if local in {FBS_ORDER_STATUS_CANCELLED, FBS_ORDER_STATUS_DONE}:
        await _release_reservation(session, order)
    return changed


async def sync_ozon_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    provider: OzonMarketplaceProvider,
    _http_client: httpx.AsyncClient,
) -> dict[str, int]:
    client_id, api_key = await _credentials(session, tenant_id, seller_id)
    rows = await provider.fetch_orders(client_id=client_id, api_key=api_key)
    upserted = 0
    created = 0
    statuses_updated = 0
    for row in rows:
        external_order_id = _text(row, "posting_number", "order_id", "id")
        if external_order_id is None:
            continue
        existing = (
            await session.execute(
                select(FbsOrder)
                .options(selectinload(FbsOrder.product_positions))
                .where(
                    FbsOrder.tenant_id == tenant_id,
                    FbsOrder.seller_id == seller_id,
                    FbsOrder.marketplace == "ozon",
                    FbsOrder.external_order_id == external_order_id,
                )
            )
        ).scalar_one_or_none()
        raw_status = _text(row, "status", "substatus")
        fallback_product_id = await _product_id_for_row(session, tenant_id, seller_id, row)
        positions = await _posting_products_for_row(session, tenant_id, seller_id, row)
        has_positions_payload = isinstance(row.get("products"), list)
        product_id = _primary_product_id(positions, fallback_product_id)
        positions_mapped = _positions_are_mapped(positions, fallback_product_id)
        if existing is not None:
            composition_changed = has_positions_payload and [
                _position_signature(position) for position in existing.product_positions
            ] != [_position_signature(position) for position in positions]
            if composition_changed:
                await _release_reservation(session, existing)
                existing.product_positions.clear()
                await session.flush()
                existing.product_id = product_id
                if positions:
                    existing.product_positions.extend(positions)
                    existing.wb_nm_id = positions[0].ozon_sku
                    existing.wb_article = positions[0].offer_id
                existing.mapping_status = (
                    MAPPING_STATUS_MAPPED if positions_mapped else MAPPING_STATUS_MISSING
                )
                details = dict(existing.meta_details_json or {})
                details["ozon_products"] = [
                    position.provider_data_json
                    for position in positions
                    if position.provider_data_json
                ]
                existing.meta_details_json = details
            statuses_updated += int(await _apply_status(session, existing, raw_status))
            if composition_changed and positions:
                await session.flush()
                await _try_reserve_order(session, existing)
            upserted += 1
            continue

        binding = await _binding_for_row(session, tenant_id, seller_id, row)
        created_at = _parse_datetime(row.get("created_at") or row.get("createdAt"))
        deadline_at = _parse_datetime(row.get("shipment_date") or row.get("shipmentDate"))
        if deadline_at <= created_at:
            deadline_at = created_at + timedelta(hours=OZON_FBS_DEADLINE_HOURS)
        if not positions_mapped:
            reserve_status = RESERVE_STATUS_SKIPPED_NO_PRODUCT
        elif binding is None:
            reserve_status = RESERVE_STATUS_WAREHOUSE_UNMAPPED
        else:
            reserve_status = RESERVE_STATUS_NO_STOCK
        order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=binding.wms_warehouse_id if binding is not None else None,
            product_id=product_id,
            marketplace="ozon",
            external_order_id=external_order_id,
            wb_order_id=_legacy_numeric_order_id(external_order_id),
            wb_warehouse_id=binding.wb_warehouse_id if binding is not None else None,
            wb_article=(positions[0].offer_id if positions else _text(row, "offer_id", "offerId")),
            wb_nm_id=positions[0].ozon_sku if positions else None,
            wb_barcode=_text(row, "barcode"),
            price=int(row["price"]) if isinstance(row.get("price"), int) else None,
            created_at_wb=created_at,
            deadline_at=deadline_at,
            mapping_status=MAPPING_STATUS_MAPPED if positions_mapped else MAPPING_STATUS_MISSING,
            reserve_status=reserve_status,
        )
        if positions:
            order.product_positions.extend(positions)
            order.meta_details_json = {
                "ozon_products": [
                    position.provider_data_json
                    for position in positions
                    if position.provider_data_json
                ]
            }
        await _apply_status(session, order, raw_status)
        session.add(order)
        await session.flush()
        await _try_reserve_order(session, order)
        created += 1
        upserted += 1
    await session.commit()
    return {
        "orders_upserted": upserted,
        "orders_created": created,
        "statuses_updated": statuses_updated,
        "stocks_bindings_processed": 0,
        "stock_errors": 0,
    }


async def sync_ozon_order_statuses(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    provider: OzonMarketplaceProvider,
    _http_client: httpx.AsyncClient,
) -> int:
    orders = list(
        (
            await session.execute(
                select(FbsOrder).where(
                    FbsOrder.tenant_id == tenant_id,
                    FbsOrder.seller_id == seller_id,
                    FbsOrder.marketplace == "ozon",
                    FbsOrder.external_order_id.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not orders:
        return 0
    client_id, api_key = await _credentials(session, tenant_id, seller_id)
    external_ids = [
        order.external_order_id for order in orders if order.external_order_id is not None
    ]
    rows = await provider.fetch_statuses(
        client_id=client_id,
        api_key=api_key,
        order_ids=external_ids,
    )
    by_external = {
        external_id: row
        for row in rows
        if (external_id := _text(row, "posting_number", "order_id", "id")) is not None
    }
    updated = 0
    for order in orders:
        row = by_external.get(order.external_order_id or "")
        if row is not None:
            updated += int(await _apply_status(session, order, _text(row, "status", "substatus")))
    await session.commit()
    return updated


async def sync_ozon_stocks(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    provider: OzonMarketplaceProvider,
    _http_client: httpx.AsyncClient,
) -> int:
    client_id, api_key = await _credentials(session, tenant_id, seller_id)
    bindings = list(
        (
            await session.execute(
                select(FbsWarehouseBinding).where(
                    FbsWarehouseBinding.tenant_id == tenant_id,
                    FbsWarehouseBinding.seller_id == seller_id,
                    FbsWarehouseBinding.marketplace == "ozon",
                    FbsWarehouseBinding.is_active.is_(True),
                    FbsWarehouseBinding.stock_sync_enabled.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    processed = 0
    for binding in bindings:
        rows = (
            await session.execute(
                select(
                    ProductMarketplaceLink.external_sku,
                    ProductMarketplaceLink.external_offer_id,
                    FbsBindingStockPool.quantity,
                )
                .join(
                    ProductMarketplaceLink,
                    ProductMarketplaceLink.product_id == FbsBindingStockPool.product_id,
                )
                .where(
                    FbsBindingStockPool.tenant_id == tenant_id,
                    FbsBindingStockPool.binding_id == binding.id,
                    ProductMarketplaceLink.tenant_id == tenant_id,
                    ProductMarketplaceLink.seller_id == seller_id,
                    ProductMarketplaceLink.marketplace == "ozon",
                    ProductMarketplaceLink.is_active.is_(True),
                )
            )
        ).all()
        stocks = [
            {
                "warehouse_id": binding.external_warehouse_id,
                "sku": external_sku,
                "offer_id": external_offer_id,
                "amount": quantity,
            }
            for external_sku, external_offer_id, quantity in rows
        ]
        await provider.publish_stocks(client_id=client_id, api_key=api_key, stocks=stocks)
        binding.last_sync_status = "confirmed"
        binding.last_sync_at = datetime.now(tz=UTC)
        binding.last_error_code = None
        processed += 1
    await session.commit()
    return processed
