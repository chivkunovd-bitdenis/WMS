"""FBS seller warehouses and offices via WB Marketplace API."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

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


async def _require_marketplace_token(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> str:
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsSellerWarehouseError("seller_not_found")
    token = await get_decrypted_marketplace_token(session, tenant_id, seller_id)
    if not token:
        pair = await get_decrypted_tokens_for_seller(session, tenant_id, seller_id)
        if pair is None:
            raise FbsSellerWarehouseError("seller_not_found")
        _content_token, supplies_token = pair
        token = supplies_token
    if not token:
        raise FbsSellerWarehouseError("missing_marketplace_token")
    return token


async def list_seller_warehouses(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> list[dict[str, Any]]:
    token = await _require_marketplace_token(session, tenant_id, seller_id)
    try:
        rows = await fetch_marketplace_seller_warehouses(http_client, api_token=token)
    except WildberriesClientError as exc:
        log_wb_client_error(
            logger,
            "fbs seller warehouses fetch failed",
            exc,
            tenant_id=tenant_id,
            seller_id=seller_id,
            endpoint=exc.endpoint or "GET /api/v3/warehouses",
        )
        raise FbsSellerWarehouseError(_wb_error_code(exc)) from exc
    return [_pick_fields(row, _WAREHOUSE_KEYS) for row in rows if isinstance(row, dict)]


async def list_seller_offices(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> list[dict[str, Any]]:
    token = await _require_marketplace_token(session, tenant_id, seller_id)
    try:
        rows = await fetch_marketplace_seller_offices(http_client, api_token=token)
    except WildberriesClientError as exc:
        log_wb_client_error(
            logger,
            "fbs seller offices fetch failed",
            exc,
            tenant_id=tenant_id,
            seller_id=seller_id,
            endpoint=exc.endpoint or "GET /api/v3/offices",
        )
        raise FbsSellerWarehouseError(_wb_error_code(exc)) from exc
    return [_pick_fields(row, _OFFICE_KEYS) for row in rows if isinstance(row, dict)]
