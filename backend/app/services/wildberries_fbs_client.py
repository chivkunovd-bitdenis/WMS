"""Typed Wildberries Marketplace FBS client helpers (batch/meta/trbx).

OpenAPI reference: dev.wildberries.ru/docs/openapi/orders-fbs (verified 2026-08-03).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import httpx

from app.core.settings import settings
from app.services.wildberries_errors import (
    MetaValidationFailItem,
    WildberriesBusinessError,
    WildberriesClientError,
)

MAX_MARKETPLACE_FBS_BATCH = 100

MARKETPLACE_SUPPLIES_BATCH_ORDERS_PATH = "/api/marketplace/v3/supplies/{supply_id}/orders"
MARKETPLACE_SUPPLY_ORDER_IDS_PATH = "/api/marketplace/v3/supplies/{supply_id}/order-ids"
MARKETPLACE_ORDERS_META_BULK_PATH = "/api/marketplace/v3/orders/meta"
MARKETPLACE_SUPPLY_TRBX_PATH = "/api/v3/supplies/{supply_id}/trbx"
MARKETPLACE_SUPPLIES_PATH = "/api/v3/supplies"
MARKETPLACE_ORDERS_STATUS_PATH = "/api/v3/orders/status"
MARKETPLACE_ORDER_STICKERS_PATH = "/api/v3/orders/stickers"
MARKETPLACE_ORDER_META_PATH = "/api/v3/orders/{order_id}/meta"

WB_FBS_OPENAPI_VERIFIED_DATE = "2026-08-03"


@dataclass(frozen=True, slots=True)
class MarketplaceMetaDetail:
    key: str
    value: str | None
    decision: str


@dataclass(frozen=True, slots=True)
class MarketplaceSupplyCreateResult:
    supply_id: str
    name: str | None = None


@dataclass(frozen=True, slots=True)
class MarketplaceSupplyDetails:
    supply_id: str
    name: str | None
    done: bool
    order_ids: tuple[int, ...] = ()
    trbx_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MarketplaceOrderMetaRow:
    order_id: int
    meta_details: tuple[MarketplaceMetaDetail, ...] = ()
    meta: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class MarketplaceTrbxEntry:
    trbx_id: str


def _marketplace_api_url(
    path: str,
    *,
    marketplace_api_base: str | None,
) -> str:
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    return f"{base}{path}"


def _response_endpoint(response: httpx.Response) -> str | None:
    try:
        return response.request.url.raw_path.decode()
    except RuntimeError:
        return response.url.raw_path.decode()


def _response_text(response: httpx.Response) -> str | None:
    try:
        return response.text
    except UnicodeDecodeError:
        return None


def _marketplace_auth_headers(
    api_token: str,
    *,
    json_body: bool = False,
) -> dict[str, str]:
    headers = {"Authorization": api_token}
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def _validate_marketplace_order_ids_batch(
    order_ids: list[int],
    *,
    max_batch: int = MAX_MARKETPLACE_FBS_BATCH,
) -> None:
    if not order_ids or len(order_ids) > max_batch:
        raise WildberriesClientError("invalid_request")
    seen: set[int] = set()
    for order_id in order_ids:
        if order_id <= 0 or order_id in seen:
            raise WildberriesClientError("invalid_request")
        seen.add(order_id)


def _validate_marketplace_trbx_ids_batch(
    trbx_ids: list[str],
    *,
    max_batch: int = MAX_MARKETPLACE_FBS_BATCH,
) -> None:
    if not trbx_ids or len(trbx_ids) > max_batch:
        raise WildberriesClientError("invalid_request")
    seen: set[str] = set()
    for trbx_id in trbx_ids:
        cleaned = trbx_id.strip()
        if not cleaned or cleaned in seen:
            raise WildberriesClientError("invalid_request")
        seen.add(cleaned)


def split_marketplace_order_id_batches(
    order_ids: list[int],
    *,
    max_batch: int = MAX_MARKETPLACE_FBS_BATCH,
) -> list[list[int]]:
    if not order_ids:
        return []
    batches: list[list[int]] = []
    for start in range(0, len(order_ids), max_batch):
        batch = order_ids[start : start + max_batch]
        _validate_marketplace_order_ids_batch(batch, max_batch=max_batch)
        batches.append(batch)
    return batches


def split_marketplace_trbx_id_batches(
    trbx_ids: list[str],
    *,
    max_batch: int = MAX_MARKETPLACE_FBS_BATCH,
) -> list[list[str]]:
    if not trbx_ids:
        return []
    batches: list[list[str]] = []
    for start in range(0, len(trbx_ids), max_batch):
        batch = trbx_ids[start : start + max_batch]
        _validate_marketplace_trbx_ids_batch(batch, max_batch=max_batch)
        batches.append(batch)
    return batches


def _parse_meta_detail(entry: dict[str, Any]) -> MarketplaceMetaDetail | None:
    key = entry.get("key")
    if not isinstance(key, str):
        return None
    value_raw = entry.get("value")
    value: str | None = None if value_raw is None else str(value_raw)
    decision_raw = entry.get("decision")
    decision = str(decision_raw) if decision_raw is not None else "unknown"
    return MarketplaceMetaDetail(key=key, value=value, decision=decision)


def _extend_meta_validation_items(
    items: list[MetaValidationFailItem],
    *,
    order_id: int | None,
    details_raw: Any,
) -> None:
    if not isinstance(details_raw, list):
        return
    for entry in details_raw:
        if not isinstance(entry, dict):
            continue
        parsed = _parse_meta_detail(entry)
        if parsed is None:
            continue
        reason_raw = entry.get("reason") or entry.get("message")
        reason = str(reason_raw) if reason_raw is not None else None
        items.append(
            MetaValidationFailItem(
                order_id=order_id,
                key=parsed.key,
                value=parsed.value,
                decision=parsed.decision,
                reason=reason,
            )
        )


def parse_meta_validation_fail(data: dict[str, Any]) -> list[MetaValidationFailItem]:
    items: list[MetaValidationFailItem] = []
    _extend_meta_validation_items(
        items,
        order_id=None,
        details_raw=data.get("metaDetails"),
    )
    orders_raw = data.get("orders")
    if isinstance(orders_raw, list):
        for order in orders_raw:
            if not isinstance(order, dict):
                continue
            oid = order.get("id")
            order_id = oid if isinstance(oid, int) and not isinstance(oid, bool) else None
            _extend_meta_validation_items(
                items,
                order_id=order_id,
                details_raw=order.get("metaDetails"),
            )
    return items


def _is_read_only_token_error(response: httpx.Response) -> bool:
    """WB отвечает 401 и поясняет, что ключ создан в режиме «Только на чтение».

    Отличать это от «неверный токен» важно: ключ рабочий, заказы по нему приезжают,
    но записать остаток или создать поставку он не может. Без явного текста
    селлер будет часами перепроверять валидный ключ.
    """
    if response.status_code != 401:
        return False
    try:
        data = response.json()
    except ValueError:
        return False
    if not isinstance(data, dict):
        return False
    detail = data.get("detail")
    return isinstance(detail, str) and "read-only" in detail.lower()


def map_upstream_error(response: httpx.Response) -> WildberriesClientError:
    if response.status_code == 409:
        return parse_business_error(response)
    if _is_read_only_token_error(response):
        return WildberriesClientError(
            "token_read_only",
            status_code=response.status_code,
            endpoint=_response_endpoint(response),
            response_body=_response_text(response),
        )
    return WildberriesClientError(
        "upstream_error",
        status_code=response.status_code,
        endpoint=_response_endpoint(response),
        response_body=_response_text(response),
    )


def parse_business_error(response: httpx.Response) -> WildberriesBusinessError:
    endpoint = _response_endpoint(response)
    response_body = _response_text(response)
    try:
        data = response.json()
    except ValueError:
        return WildberriesBusinessError(
            "upstream_error",
            status_code=409,
            endpoint=endpoint,
            response_body=response_body,
        )
    if not isinstance(data, dict):
        return WildberriesBusinessError(
            "upstream_error",
            status_code=409,
            endpoint=endpoint,
            response_body=response_body,
        )
    wb_code_raw = data.get("code")
    wb_code = wb_code_raw if isinstance(wb_code_raw, str) else None
    message_raw = data.get("message")
    message = message_raw if isinstance(message_raw, str) else None
    meta_items = parse_meta_validation_fail(data)
    if wb_code == "MetaValidationFail" or meta_items:
        return WildberriesBusinessError(
            "meta_validation_fail",
            status_code=409,
            wb_code=wb_code or "MetaValidationFail",
            message=message,
            meta_validation=meta_items,
            endpoint=endpoint,
            response_body=response_body,
        )
    return WildberriesBusinessError(
        "business_error",
        status_code=409,
        wb_code=wb_code,
        message=message,
        endpoint=endpoint,
        response_body=response_body,
    )


def ensure_success(response: httpx.Response, *, allow_empty: bool = False) -> None:
    if response.status_code >= 400:
        raise map_upstream_error(response)
    if allow_empty and response.status_code == 204:
        return
    if not allow_empty and response.status_code == 204:
        return


def _parse_supply_create(data: Any) -> MarketplaceSupplyCreateResult:
    if not isinstance(data, dict):
        raise WildberriesClientError("invalid_response")
    supply_id_raw = data.get("id")
    if supply_id_raw is None:
        raise WildberriesClientError("invalid_response")
    supply_id = str(supply_id_raw)
    name_raw = data.get("name")
    name = name_raw if isinstance(name_raw, str) else None
    return MarketplaceSupplyCreateResult(supply_id=supply_id, name=name)


def _parse_supply_details(data: Any) -> MarketplaceSupplyDetails:
    if not isinstance(data, dict):
        raise WildberriesClientError("invalid_response")
    supply_id_raw = data.get("id")
    if supply_id_raw is None:
        raise WildberriesClientError("invalid_response")
    name_raw = data.get("name")
    name = name_raw if isinstance(name_raw, str) else None
    done_raw = data.get("done")
    done = bool(done_raw) if isinstance(done_raw, bool) else False
    order_ids: list[int] = []
    orders_raw = data.get("orders") or data.get("orderIds")
    if isinstance(orders_raw, list):
        for item in orders_raw:
            if isinstance(item, int) and not isinstance(item, bool):
                order_ids.append(item)
    trbx_ids: list[str] = []
    trbx_raw = data.get("trbxIds") or data.get("trbxes")
    if isinstance(trbx_raw, list):
        for item in trbx_raw:
            if isinstance(item, str):
                trbx_ids.append(item)
            elif isinstance(item, dict):
                for key in ("id", "trbxId", "trbx_id"):
                    if key in item:
                        trbx_ids.append(str(item[key]))
                        break
    return MarketplaceSupplyDetails(
        supply_id=str(supply_id_raw),
        name=name,
        done=done,
        order_ids=tuple(order_ids),
        trbx_ids=tuple(trbx_ids),
    )


def _parse_order_ids_response(data: Any) -> list[int]:
    if not isinstance(data, dict):
        raise WildberriesClientError("invalid_response")
    order_ids_raw = data.get("orderIds")
    if not isinstance(order_ids_raw, list):
        raise WildberriesClientError("invalid_response")
    parsed: list[int] = []
    for item in order_ids_raw:
        if not isinstance(item, int) or isinstance(item, bool):
            raise WildberriesClientError("invalid_response")
        parsed.append(item)
    return parsed


def _parse_orders_meta_response(data: Any) -> list[MarketplaceOrderMetaRow]:
    if not isinstance(data, dict):
        raise WildberriesClientError("invalid_response")
    orders_raw = data.get("orders")
    if not isinstance(orders_raw, list):
        raise WildberriesClientError("invalid_response")
    rows: list[MarketplaceOrderMetaRow] = []
    for order in orders_raw:
        if not isinstance(order, dict):
            raise WildberriesClientError("invalid_response")
        oid = order.get("id")
        if not isinstance(oid, int) or isinstance(oid, bool):
            raise WildberriesClientError("invalid_response")
        details_raw = order.get("metaDetails")
        details: list[MarketplaceMetaDetail] = []
        if isinstance(details_raw, list):
            for entry in details_raw:
                if not isinstance(entry, dict):
                    raise WildberriesClientError("invalid_response")
                parsed = _parse_meta_detail(entry)
                if parsed is None:
                    raise WildberriesClientError("invalid_response")
                details.append(parsed)
        meta_raw = order.get("meta")
        meta = cast(dict[str, Any], meta_raw) if isinstance(meta_raw, dict) else None
        rows.append(
            MarketplaceOrderMetaRow(
                order_id=oid,
                meta_details=tuple(details),
                meta=meta,
            )
        )
    return rows


def _parse_trbx_list(data: Any) -> list[MarketplaceTrbxEntry]:
    if isinstance(data, list):
        entries: list[MarketplaceTrbxEntry] = []
        for item in data:
            if isinstance(item, str):
                entries.append(MarketplaceTrbxEntry(trbx_id=item))
            elif isinstance(item, dict):
                for key in ("id", "trbxId", "trbx_id"):
                    if key in item:
                        entries.append(MarketplaceTrbxEntry(trbx_id=str(item[key])))
                        break
        return entries
    if isinstance(data, dict):
        for key in ("trbxes", "trbxIds", "data"):
            val = data.get(key)
            if val is not None:
                parsed = _parse_trbx_list(val)
                if parsed:
                    return parsed
    raise WildberriesClientError("invalid_response")


async def marketplace_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    api_token: str,
    json_body: dict[str, Any] | None = None,
    params: dict[str, str | int] | None = None,
) -> httpx.Response:
    headers = _marketplace_auth_headers(api_token, json_body=json_body is not None)
    try:
        response = await client.request(
            method,
            url,
            headers=headers,
            json=json_body,
            params=params,
            timeout=60.0,
        )
    except httpx.HTTPError as exc:
        raise WildberriesClientError("transport_error", endpoint=url) from exc
    return response


async def create_marketplace_supply_typed(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    name: str,
    marketplace_api_base: str | None = None,
) -> MarketplaceSupplyCreateResult:
    url = _marketplace_api_url(MARKETPLACE_SUPPLIES_PATH, marketplace_api_base=marketplace_api_base)
    response = await marketplace_request(
        client,
        "POST",
        url,
        api_token=api_token,
        json_body={"name": name},
    )
    if response.status_code >= 400:
        raise map_upstream_error(response)
    if response.status_code == 204 or not response.content:
        raise WildberriesClientError("invalid_response")
    try:
        data = response.json()
    except ValueError as exc:
        raise WildberriesClientError("invalid_response") from exc
    return _parse_supply_create(data)


async def add_orders_to_marketplace_supply_batch(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    supply_id: str,
    order_ids: list[int],
    marketplace_api_base: str | None = None,
) -> None:
    """PATCH /api/marketplace/v3/supplies/{supplyId}/orders — up to 100 order IDs."""
    _validate_marketplace_order_ids_batch(order_ids)
    url = _marketplace_api_url(
        MARKETPLACE_SUPPLIES_BATCH_ORDERS_PATH.format(supply_id=supply_id),
        marketplace_api_base=marketplace_api_base,
    )
    response = await marketplace_request(
        client,
        "PATCH",
        url,
        api_token=api_token,
        json_body={"orders": order_ids},
    )
    ensure_success(response, allow_empty=True)


async def fetch_marketplace_supply_details(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    supply_id: str,
    marketplace_api_base: str | None = None,
) -> MarketplaceSupplyDetails:
    """GET /api/v3/supplies/{supplyId} — supply details for reconcile."""
    url = _marketplace_api_url(
        f"{MARKETPLACE_SUPPLIES_PATH}/{supply_id}",
        marketplace_api_base=marketplace_api_base,
    )
    response = await marketplace_request(client, "GET", url, api_token=api_token)
    if response.status_code >= 400:
        raise map_upstream_error(response)
    try:
        data = response.json()
    except ValueError as exc:
        raise WildberriesClientError("invalid_response") from exc
    return _parse_supply_details(data)


async def fetch_marketplace_supply_order_ids(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    supply_id: str,
    marketplace_api_base: str | None = None,
) -> list[int]:
    """GET /api/marketplace/v3/supplies/{supplyId}/order-ids."""
    url = _marketplace_api_url(
        MARKETPLACE_SUPPLY_ORDER_IDS_PATH.format(supply_id=supply_id),
        marketplace_api_base=marketplace_api_base,
    )
    response = await marketplace_request(client, "GET", url, api_token=api_token)
    if response.status_code >= 400:
        raise map_upstream_error(response)
    try:
        data = response.json()
    except ValueError as exc:
        raise WildberriesClientError("invalid_response") from exc
    return _parse_order_ids_response(data)


async def fetch_marketplace_orders_meta_batch(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    order_ids: list[int],
    marketplace_api_base: str | None = None,
) -> list[MarketplaceOrderMetaRow]:
    """POST /api/marketplace/v3/orders/meta — batch metadata + metaDetails."""
    _validate_marketplace_order_ids_batch(order_ids)
    if settings.e2e_mock_wb_marketplace_marking:
        from app.services.wildberries_client import mock_order_meta_snapshot

        return [
            MarketplaceOrderMetaRow(
                order_id=order_id,
                meta_details=(),
                meta=mock_order_meta_snapshot(order_id),
            )
            for order_id in order_ids
        ]
    url = _marketplace_api_url(
        MARKETPLACE_ORDERS_META_BULK_PATH,
        marketplace_api_base=marketplace_api_base,
    )
    response = await marketplace_request(
        client,
        "POST",
        url,
        api_token=api_token,
        json_body={"orders": order_ids},
    )
    if response.status_code >= 400:
        raise map_upstream_error(response)
    try:
        data = response.json()
    except ValueError as exc:
        raise WildberriesClientError("invalid_response") from exc
    return _parse_orders_meta_response(data)


async def delete_marketplace_order_meta(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    order_id: int,
    key: str,
    marketplace_api_base: str | None = None,
) -> None:
    """DELETE /api/v3/orders/{orderId}/meta?key=…"""
    if order_id <= 0 or not key.strip():
        raise WildberriesClientError("invalid_request")
    url = _marketplace_api_url(
        MARKETPLACE_ORDER_META_PATH.format(order_id=order_id),
        marketplace_api_base=marketplace_api_base,
    )
    response = await marketplace_request(
        client,
        "DELETE",
        url,
        api_token=api_token,
        params={"key": key},
    )
    ensure_success(response, allow_empty=True)


async def fetch_marketplace_supply_trbx_list(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    supply_id: str,
    marketplace_api_base: str | None = None,
) -> list[MarketplaceTrbxEntry]:
    """GET /api/v3/supplies/{supplyId}/trbx — current cargo places."""
    url = _marketplace_api_url(
        MARKETPLACE_SUPPLY_TRBX_PATH.format(supply_id=supply_id),
        marketplace_api_base=marketplace_api_base,
    )
    response = await marketplace_request(client, "GET", url, api_token=api_token)
    if response.status_code >= 400:
        raise map_upstream_error(response)
    try:
        data = response.json()
    except ValueError as exc:
        raise WildberriesClientError("invalid_response") from exc
    return _parse_trbx_list(data)


async def delete_marketplace_supply_trbx(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    supply_id: str,
    trbx_ids: list[str],
    marketplace_api_base: str | None = None,
) -> None:
    """DELETE /api/v3/supplies/{supplyId}/trbx — remove cargo places."""
    _validate_marketplace_trbx_ids_batch(trbx_ids)
    url = _marketplace_api_url(
        MARKETPLACE_SUPPLY_TRBX_PATH.format(supply_id=supply_id),
        marketplace_api_base=marketplace_api_base,
    )
    response = await marketplace_request(
        client,
        "DELETE",
        url,
        api_token=api_token,
        json_body={"trbxIds": trbx_ids},
    )
    ensure_success(response, allow_empty=True)


async def deliver_marketplace_supply_typed(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    supply_id: str,
    marketplace_api_base: str | None = None,
) -> None:
    """PATCH /api/v3/supplies/{supplyId}/deliver — 409 MetaValidationFail preserved."""
    url = _marketplace_api_url(
        f"{MARKETPLACE_SUPPLIES_PATH}/{supply_id}/deliver",
        marketplace_api_base=marketplace_api_base,
    )
    response = await marketplace_request(client, "PATCH", url, api_token=api_token)
    ensure_success(response, allow_empty=True)


async def fetch_marketplace_order_stickers_typed(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    order_ids: list[int],
    marketplace_api_base: str | None = None,
    width: int = 58,
    height: int = 40,
) -> list[dict[str, Any]]:
    """POST /api/v3/orders/stickers — batch ≤100."""
    if not order_ids:
        return []
    _validate_marketplace_order_ids_batch(order_ids)
    url = _marketplace_api_url(
        MARKETPLACE_ORDER_STICKERS_PATH,
        marketplace_api_base=marketplace_api_base,
    )
    params: dict[str, str | int] = {"type": "png", "width": width, "height": height}
    response = await marketplace_request(
        client,
        "POST",
        url,
        api_token=api_token,
        json_body={"orders": order_ids},
        params=params,
    )
    if response.status_code >= 400:
        raise map_upstream_error(response)
    try:
        data = response.json()
    except ValueError as exc:
        raise WildberriesClientError("invalid_response") from exc
    if isinstance(data, list):
        return cast(list[dict[str, Any]], data)
    stickers = data.get("stickers") if isinstance(data, dict) else None
    if isinstance(stickers, list):
        return cast(list[dict[str, Any]], stickers)
    return []


async def fetch_marketplace_orders_status_typed(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    order_ids: list[int],
    marketplace_api_base: str | None = None,
) -> list[dict[str, Any]]:
    """POST /api/v3/orders/status — batch ≤100."""
    if not order_ids:
        return []
    _validate_marketplace_order_ids_batch(order_ids)
    url = _marketplace_api_url(
        MARKETPLACE_ORDERS_STATUS_PATH,
        marketplace_api_base=marketplace_api_base,
    )
    response = await marketplace_request(
        client,
        "POST",
        url,
        api_token=api_token,
        json_body={"orders": order_ids},
    )
    if response.status_code >= 400:
        raise map_upstream_error(response)
    try:
        data = response.json()
    except ValueError as exc:
        raise WildberriesClientError("invalid_response") from exc
    if isinstance(data, list):
        return cast(list[dict[str, Any]], data)
    orders = data.get("orders") if isinstance(data, dict) else None
    if isinstance(orders, list):
        return cast(list[dict[str, Any]], orders)
    return []
