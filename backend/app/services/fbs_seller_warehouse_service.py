"""Справочники складов продавца: у Wildberries — Marketplace API, у Ozon — Seller API.

Оба списка приезжают по запросу и никуда не сохраняются. Своя копия чужого
справочника разошлась бы с кабинетом в тот же день, когда продавец переименует
или отключит склад, а складов у продавца единицы — ходить за ними дешевле, чем
их сторожить.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.services.fbs_warehouse_binding_service import MARKETPLACE_OZON
from app.services.marketplace_account_service import (
    MarketplaceAccountError,
    MarketplaceAccountService,
)
from app.services.marketplace_provider import MarketplaceProviderError
from app.services.ozon_provider_factory import build_ozon_provider, ozon_live_api_enabled
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
                http_client,
                api_token=token,
                marketplace_api_base=settings.wildberries_marketplace_warehouse_api_base,
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
            # Экран складов продавца — вайлдберрисовский, и с появлением привязок
            # Ozon числовой ключ перестал быть уникальным сам по себе.
            FbsWarehouseBinding.marketplace == "wb",
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


def _ozon_error_code(error: MarketplaceProviderError) -> str:
    """Тот же разбор отказа, что и у публикации остатков Ozon."""
    if error.is_account_blocked:
        return "ozon_account_blocked"
    if error.status_code in {401, 403}:
        return "ozon_auth_failed"
    if error.status_code == 429:
        return "ozon_rate_limited"
    return "ozon_unavailable"


def _ozon_bool(row: dict[str, Any], key: str) -> bool:
    value = row.get(key)
    return value is True


async def list_ozon_seller_warehouses(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Склады продавца из кабинета Ozon — чтобы номер не вводили руками.

    Возвращает те же поля, по которым склад выбирают у Wildberries (номер,
    название, уже сопоставленный склад WMS), плюс `has_entrusted_acceptance`:
    включена ли на складе доверительная приёмка. Это ровно тот признак, ради
    которого в WMS-356 собирались заходить в кабинет глазами, и он приезжает
    вместе со списком, не требуя ни отдельного запроса, ни своего поля в базе.

    Рубильник боевого транспорта проверяется здесь явно и до всего остального.
    Без этой проверки выключенный Ozon вернул бы локальный фейк с пустым
    списком, и оператор прочитал бы «складов у продавца нет» про кабинет,
    которого никто не спрашивал.
    """
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsSellerWarehouseError("seller_not_found")
    if not ozon_live_api_enabled():
        raise FbsSellerWarehouseError("ozon_live_warehouses_blocked")
    try:
        client_id, api_key = await MarketplaceAccountService(session).stored_credentials(
            tenant_id,
            seller_id,
        )
    except MarketplaceAccountError as exc:
        raise FbsSellerWarehouseError(exc.code) from exc
    try:
        rows = await build_ozon_provider().fetch_warehouses(
            client_id=client_id,
            api_key=api_key,
        )
    except MarketplaceProviderError as exc:
        logger.warning(
            "ozon seller warehouses fetch failed code=%s status=%s tenant=%s seller=%s",
            exc.code,
            exc.status_code,
            tenant_id,
            seller_id,
        )
        raise FbsSellerWarehouseError(_ozon_error_code(exc)) from exc

    warehouse_ids: list[int] = []
    for row in rows:
        raw_id = row.get("warehouse_id")
        if isinstance(raw_id, bool) or not isinstance(raw_id, int) or raw_id <= 0:
            continue
        warehouse_ids.append(raw_id)

    bindings: dict[str, FbsWarehouseBinding] = {}
    if warehouse_ids:
        stmt = select(FbsWarehouseBinding).where(
            FbsWarehouseBinding.tenant_id == tenant_id,
            FbsWarehouseBinding.seller_id == seller_id,
            FbsWarehouseBinding.marketplace == MARKETPLACE_OZON,
            # Привязка Ozon опознаётся по строковому внешнему номеру: именно по
            # нему её ищет разбор отправления (`ozon_fbs_sync_service`).
            FbsWarehouseBinding.external_warehouse_id.in_(
                [str(one) for one in warehouse_ids]
            ),
        )
        bindings = {
            str(binding.external_warehouse_id): binding
            for binding in (await session.execute(stmt)).scalars().all()
        }

    result: list[dict[str, Any]] = []
    for row in rows:
        raw_id = row.get("warehouse_id")
        if isinstance(raw_id, bool) or not isinstance(raw_id, int) or raw_id <= 0:
            continue
        binding = bindings.get(str(raw_id))
        name = row.get("name")
        result.append(
            {
                "warehouse_id": raw_id,
                "name": str(name).strip() if isinstance(name, str) and name.strip()
                else f"Склад Ozon {raw_id}",
                "has_entrusted_acceptance": _ozon_bool(row, "has_entrusted_acceptance"),
                # Метод отдаёт склады FBS и rFBS вперемешку — это сказано в его
                # собственном описании. Признак пробрасывается как есть, чтобы
                # оператор не сопоставил склад чужой схемы; фильтровать молча
                # мы не имеем права.
                "is_rfbs": _ozon_bool(row, "is_rfbs"),
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
            rows = await fetch_marketplace_seller_offices(
                http_client,
                api_token=token,
                marketplace_api_base=settings.wildberries_marketplace_warehouse_api_base,
            )
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
