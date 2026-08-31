"""FBS seller warehouses and offices via WB Marketplace API."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.services.wildberries_client import (
    WildberriesClientError,
    fetch_marketplace_seller_offices,
    fetch_marketplace_seller_warehouses,
)
from app.services.wildberries_credentials_service import (
    _seller_in_tenant,
    get_decrypted_marketplace_token,
    get_decrypted_tokens_for_seller,
)
from app.services.wildberries_errors import log_wb_client_error

logger = logging.getLogger(__name__)


class FbsSellerWarehouseError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


_WAREHOUSE_KEYS = (
    "id",
    "name",
    "address",
    "officeId",
    "cargoType",
    "deliveryType",
    "isDeleting",
    "isProcessing",
)
_OFFICE_KEYS = (
    "id",
    "officeId",
    "name",
    "city",
    "address",
    "longitude",
    "latitude",
    "selected",
)


def _pick_fields(row: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: row[key] for key in keys if key in row}


def _wb_error_code(exc: WildberriesClientError) -> str:
    suffix = f"_{exc.status_code}" if exc.status_code else ""
    return f"wb_{exc.code}{suffix}"


async def _marketplace_tokens_to_try(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> list[str]:
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsSellerWarehouseError("seller_not_found")
    marketplace_token = await get_decrypted_marketplace_token(
        session, tenant_id, seller_id
    )
    pair = await get_decrypted_tokens_for_seller(session, tenant_id, seller_id)
    if pair is None:
        raise FbsSellerWarehouseError("seller_not_found")
    content_token, supplies_token = pair

    # Старые селлеры могли сохранить единый ключ WB только в content-поле.
    # Более того, отдельное marketplace-поле могло остаться со старым ключом,
    # хотя актуальный единый ключ уже лежит в content. Пробуем все сохранённые
    # варианты, не повторяя одинаковые значения; сами ключи не логируем.
    tokens: list[str] = []
    seen: set[str] = set()
    for raw in (marketplace_token, supplies_token, content_token):
        token = raw.strip() if raw else ""
        if not token or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    if not tokens:
        raise FbsSellerWarehouseError("missing_marketplace_token")
    return tokens


async def list_seller_warehouses(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> list[dict[str, Any]]:
    tokens = await _marketplace_tokens_to_try(session, tenant_id, seller_id)
    last_exc: WildberriesClientError | None = None
    rows: list[dict[str, Any]] = []
    for attempt, token in enumerate(tokens, start=1):
        try:
            rows = await fetch_marketplace_seller_warehouses(
                http_client, api_token=token
            )
            break
        except WildberriesClientError as exc:
            last_exc = exc
            log_wb_client_error(
                logger,
                f"fbs seller warehouses fetch failed attempt={attempt}/{len(tokens)}",
                exc,
                tenant_id=tenant_id,
                seller_id=seller_id,
                endpoint=exc.endpoint or "GET /api/v3/warehouses",
            )
    else:
        assert last_exc is not None
        raise FbsSellerWarehouseError(_wb_error_code(last_exc)) from last_exc
    wb_rows = [_pick_fields(row, _WAREHOUSE_KEYS) for row in rows if isinstance(row, dict)]
    wb_ids = {
        int(row["id"])
        for row in wb_rows
        if row.get("id") is not None and int(row["id"]) > 0
    }
    bindings: dict[int, FbsWarehouseBinding] = {}
    if wb_ids:
        stmt = select(FbsWarehouseBinding).where(
            FbsWarehouseBinding.tenant_id == tenant_id,
            FbsWarehouseBinding.seller_id == seller_id,
            FbsWarehouseBinding.wb_warehouse_id.in_(wb_ids),
        )
        bindings = {
            int(binding.wb_warehouse_id): binding
            for binding in (await session.execute(stmt)).scalars().all()
        }

    result: list[dict[str, Any]] = []
    for row in wb_rows:
        raw_id = row.get("id")
        if raw_id is None or int(raw_id) <= 0:
            continue
        wb_warehouse_id = int(raw_id)
        binding = bindings.get(wb_warehouse_id)
        result.append(
            {
                **row,
                "wb_warehouse_id": wb_warehouse_id,
                "name": str(row.get("name") or f"Склад WB {wb_warehouse_id}"),
                "served": bool(binding and binding.is_active and binding.served),
                "wms_warehouse_id": (
                    str(binding.wms_warehouse_id) if binding is not None else None
                ),
            }
        )
    return result


async def list_seller_offices(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> list[dict[str, Any]]:
    tokens = await _marketplace_tokens_to_try(session, tenant_id, seller_id)
    last_exc: WildberriesClientError | None = None
    rows: list[dict[str, Any]] = []
    for attempt, token in enumerate(tokens, start=1):
        try:
            rows = await fetch_marketplace_seller_offices(http_client, api_token=token)
            break
        except WildberriesClientError as exc:
            last_exc = exc
            log_wb_client_error(
                logger,
                f"fbs seller offices fetch failed attempt={attempt}/{len(tokens)}",
                exc,
                tenant_id=tenant_id,
                seller_id=seller_id,
                endpoint=exc.endpoint or "GET /api/v3/offices",
            )
    else:
        assert last_exc is not None
        raise FbsSellerWarehouseError(_wb_error_code(last_exc)) from last_exc
    return [_pick_fields(row, _OFFICE_KEYS) for row in rows if isinstance(row, dict)]
