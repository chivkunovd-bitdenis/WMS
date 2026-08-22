"""Wildberries read-only API client (import/sync). Tokens are never logged."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Any, cast

import httpx

from app.core.settings import settings
from app.services.wildberries_errors import WildberriesClientError as WildberriesClientError
from app.services.wildberries_fbs_client import (
    MarketplaceSupplyDetails,
    add_orders_to_marketplace_supply_batch,
    deliver_marketplace_supply_typed,
    fetch_marketplace_order_stickers_typed,
    fetch_marketplace_orders_status_typed,
)
from app.services.wildberries_fbs_client import (
    fetch_marketplace_supply_details as fetch_marketplace_supply_details_typed,
)

CARDS_LIST_PATH = "/content/v2/get/cards/list"
SUPPLIES_LIST_PATH = "/api/v1/supplies"
MP_WAREHOUSES_PATH = "/api/v1/warehouses"
MARKETPLACE_ORDERS_NEW_PATH = "/api/v3/orders/new"
MARKETPLACE_ORDERS_PATH = "/api/v3/orders"
MARKETPLACE_ORDERS_STATUS_PATH = "/api/v3/orders/status"
MARKETPLACE_ORDERS_CANCEL_PATH = "/api/v3/orders/{order_id}/cancel"
MARKETPLACE_SELLER_WAREHOUSES_PATH = "/api/v3/warehouses"
MARKETPLACE_SELLER_OFFICES_PATH = "/api/v3/offices"
MARKETPLACE_SUPPLIES_PATH = "/api/v3/supplies"
MARKETPLACE_ORDER_STICKERS_PATH = "/api/v3/orders/stickers"
MARKETPLACE_ORDER_META_PATH = "/api/v3/orders/{order_id}/meta"
MARKETPLACE_STOCKS_PATH = "/api/v3/stocks/{warehouse_id}"
MAX_MARKETPLACE_STOCKS_BATCH = 1000


def _wb_response_text(response: httpx.Response) -> str | None:
    try:
        return response.text
    except UnicodeDecodeError:
        return None


def _wb_error_from_response(
    code: str,
    response: httpx.Response,
    *,
    endpoint: str,
) -> WildberriesClientError:
    return WildberriesClientError(
        code,
        status_code=response.status_code,
        endpoint=endpoint,
        response_body=_wb_response_text(response),
    )


# In-memory store for e2e_mock_wb_marketplace_marking (tests may clear via reset helper).
_mock_order_meta: dict[int, dict[str, list[dict[str, str]]]] = {}
_mock_marketplace_supply_add_error_once: str | None = None


def reset_mock_marketplace_order_meta() -> None:
    """Clear mock marking meta store (tests only)."""
    _mock_order_meta.clear()


def fail_next_mock_marketplace_supply_add(error_code: str) -> None:
    """Make the next mock supply add-orders call fail (tests only)."""
    global _mock_marketplace_supply_add_error_once
    _mock_marketplace_supply_add_error_once = error_code


def consume_next_mock_marketplace_supply_add_error() -> str | None:
    """Return and clear the next mock add-orders failure code (tests only)."""
    global _mock_marketplace_supply_add_error_once
    error_code = _mock_marketplace_supply_add_error_once
    _mock_marketplace_supply_add_error_once = None
    return error_code


def build_marketplace_order_meta_put_body(kind: str, value: str) -> dict[str, Any]:
    """Build JSON body for PUT /api/v3/orders/{id}/meta/{kind}."""
    if kind == "sgtin":
        return {"sgtins": [value]}
    if kind in {"uin", "imei", "gtin"}:
        return {kind: value}
    raise WildberriesClientError("invalid_meta_kind")


@dataclass(frozen=True, slots=True)
class MarketplaceStockAmount:
    chrt_id: int
    amount: int


def _validate_marketplace_stocks_batch(
    items: list[MarketplaceStockAmount],
    *,
    max_batch: int = MAX_MARKETPLACE_STOCKS_BATCH,
) -> None:
    if not items or len(items) > max_batch:
        raise WildberriesClientError("invalid_request")
    seen: set[int] = set()
    for item in items:
        if item.chrt_id <= 0:
            raise WildberriesClientError("invalid_request")
        if item.amount < 0:
            raise WildberriesClientError("invalid_request")
        if item.chrt_id in seen:
            raise WildberriesClientError("invalid_request")
        seen.add(item.chrt_id)


def _validate_marketplace_chrt_ids_batch(
    chrt_ids: list[int],
    *,
    max_batch: int = MAX_MARKETPLACE_STOCKS_BATCH,
) -> None:
    if not chrt_ids or len(chrt_ids) > max_batch:
        raise WildberriesClientError("invalid_request")
    seen: set[int] = set()
    for chrt_id in chrt_ids:
        if chrt_id <= 0:
            raise WildberriesClientError("invalid_request")
        if chrt_id in seen:
            raise WildberriesClientError("invalid_request")
        seen.add(chrt_id)


def split_marketplace_stocks_batches(
    items: list[MarketplaceStockAmount],
    *,
    max_batch: int = MAX_MARKETPLACE_STOCKS_BATCH,
) -> list[list[MarketplaceStockAmount]]:
    """Split stocks into WB API batches (≤ max_batch items each, no overlap)."""
    if not items:
        return []
    batches: list[list[MarketplaceStockAmount]] = []
    for start in range(0, len(items), max_batch):
        batch = items[start : start + max_batch]
        _validate_marketplace_stocks_batch(batch, max_batch=max_batch)
        batches.append(batch)
    return batches


def _parse_marketplace_stocks_response(data: Any) -> list[MarketplaceStockAmount]:
    if not isinstance(data, dict):
        raise WildberriesClientError("invalid_response")
    stocks_raw = data.get("stocks")
    if not isinstance(stocks_raw, list):
        raise WildberriesClientError("invalid_response")
    parsed: list[MarketplaceStockAmount] = []
    seen: set[int] = set()
    for entry in stocks_raw:
        if not isinstance(entry, dict):
            raise WildberriesClientError("invalid_response")
        chrt_raw = entry.get("chrtId")
        amount_raw = entry.get("amount")
        if not isinstance(chrt_raw, int) or isinstance(chrt_raw, bool):
            raise WildberriesClientError("invalid_response")
        if not isinstance(amount_raw, int) or isinstance(amount_raw, bool):
            raise WildberriesClientError("invalid_response")
        if chrt_raw <= 0 or amount_raw < 0:
            raise WildberriesClientError("invalid_response")
        if chrt_raw in seen:
            raise WildberriesClientError("invalid_response")
        seen.add(chrt_raw)
        parsed.append(MarketplaceStockAmount(chrt_id=chrt_raw, amount=amount_raw))
    return parsed


def _marketplace_stocks_url(
    *,
    warehouse_id: int,
    marketplace_api_base: str | None,
) -> str:
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    return f"{base}{MARKETPLACE_STOCKS_PATH.format(warehouse_id=warehouse_id)}"


async def put_marketplace_stocks(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    warehouse_id: int,
    stocks: list[MarketplaceStockAmount],
    marketplace_api_base: str | None = None,
) -> None:
    """PUT /api/v3/stocks/{warehouseId} — absolute stock amounts by chrtId."""
    _validate_marketplace_stocks_batch(stocks)
    url = _marketplace_stocks_url(
        warehouse_id=warehouse_id,
        marketplace_api_base=marketplace_api_base,
    )
    headers = {
        "Authorization": api_token,
        "Content-Type": "application/json",
    }
    payload = {
        "stocks": [
            {"chrtId": item.chrt_id, "amount": item.amount}
            for item in stocks
        ],
    }
    try:
        response = await client.put(url, headers=headers, json=payload, timeout=60.0)
    except httpx.HTTPError as exc:
        raise WildberriesClientError("transport_error") from exc
    if response.status_code >= 400:
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
        )


async def fetch_marketplace_stocks(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    warehouse_id: int,
    chrt_ids: list[int],
    marketplace_api_base: str | None = None,
) -> list[MarketplaceStockAmount]:
    """POST /api/v3/stocks/{warehouseId} — read stock amounts by chrtId."""
    _validate_marketplace_chrt_ids_batch(chrt_ids)
    url = _marketplace_stocks_url(
        warehouse_id=warehouse_id,
        marketplace_api_base=marketplace_api_base,
    )
    headers = {
        "Authorization": api_token,
        "Content-Type": "application/json",
    }
    payload = {"chrtIds": chrt_ids}
    try:
        response = await client.post(url, headers=headers, json=payload, timeout=60.0)
    except httpx.HTTPError as exc:
        raise WildberriesClientError("transport_error") from exc
    if response.status_code >= 400:
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise WildberriesClientError("invalid_response") from exc
    return _parse_marketplace_stocks_response(data)


async def fetch_cards_list(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    content_api_base: str | None = None,
    limit: int = 100,
    cursor_updated_at: str | None = None,
    cursor_nm_id: int | None = None,
) -> dict[str, Any]:
    """POST /content/v2/get/cards/list — first page (import-only, MVP)."""
    if settings.e2e_mock_wb_cards:
        return {
            "cards": [
                {
                    "nmID": 424242,
                    "vendorCode": "E2E-MOCK",
                    "brand": "E2E-MOCK-BRAND",
                    # Self-contained 1x1 PNG (data: URI) — must actually decode as an image in
                    # the browser: ProductPhotoThumb now probes the URL with a real Image() load
                    # and hides the zoom-on-hover preview for anything that fails to load (see
                    # frontend/src/components/ProductPhotoThumb.tsx). A dead external link like
                    # the previous "https://example.com/..." placeholder 404s, which used to be
                    # harmless (old code never checked load success) but now makes every e2e test
                    # that hovers a product photo fail to see the enlarged preview.
                    "photos": [
                        {
                            "big": (
                                "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
                                "AAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
                            )
                        }
                    ],
                    "sizes": [{"techSize": "L", "skus": ["E2E-MOCK-BARCODE"]}],
                    "characteristics": [
                        {"name": "Цвет", "value": ["коричневый"]},
                        {"name": "Состав", "value": ["хлопок 95%, эластан 5%"]},
                    ],
                }
            ],
            "cursor": {"total": 1},
        }
    base = (content_api_base or settings.wildberries_content_api_base).rstrip("/")
    url = f"{base}{CARDS_LIST_PATH}"
    headers = {
        "Authorization": api_token,
        "Content-Type": "application/json",
    }
    cursor: dict[str, Any] = {"limit": min(limit, 100)}
    if cursor_updated_at:
        cursor["updatedAt"] = cursor_updated_at
    if cursor_nm_id is not None:
        cursor["nmID"] = int(cursor_nm_id)
    # WB docs: settings.filter.textSearch can match barcode/vendorCode/nmID.
    # For full sync we rely on cursor-based paging with withPhoto=-1 (all cards).
    payload: dict[str, Any] = {
        "settings": {
            "sort": {"ascending": False},
            "filter": {"withPhoto": -1},
            "cursor": cursor,
        }
    }
    try:
        response = await client.post(url, headers=headers, json=payload, timeout=60.0)
    except httpx.HTTPError as exc:
        raise WildberriesClientError("transport_error") from exc
    if response.status_code >= 400:
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
        )
    try:
        return cast(dict[str, Any], response.json())
    except ValueError as exc:
        raise WildberriesClientError("invalid_json") from exc


async def fetch_supplies_list(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    supplies_api_base: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """POST /api/v1/supplies — list FBW supplies (import-only)."""
    if settings.e2e_mock_wb_supplies:
        return [
            {
                "supplyID": 888001,
                "preorderID": 2001,
                "statusID": 5,
                "createDate": "2026-01-01T00:00:00+03:00",
            },
        ]
    base = (supplies_api_base or settings.wildberries_supplies_api_base).rstrip("/")
    url = f"{base}{SUPPLIES_LIST_PATH}"
    headers = {
        "Authorization": api_token,
        "Content-Type": "application/json",
    }
    params = {"limit": min(max(limit, 1), 1000), "offset": max(offset, 0)}
    body: dict[str, Any] = {
        "dates": [{"from": "2020-01-01", "till": "2030-12-31", "type": "createDate"}],
        "statusIDs": [1, 2, 3, 4, 5, 6],
    }
    try:
        response = await client.post(
            url, headers=headers, json=body, params=params, timeout=60.0
        )
    except httpx.HTTPError as exc:
        raise WildberriesClientError("transport_error") from exc
    if response.status_code >= 400:
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
        )
    data = response.json()
    if isinstance(data, list):
        return cast(list[dict[str, Any]], data)
    sup = data.get("supplies") if isinstance(data, dict) else None
    if isinstance(sup, list):
        return cast(list[dict[str, Any]], sup)
    return []


async def fetch_mp_warehouses_list(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    supplies_api_base: str | None = None,
) -> list[dict[str, Any]]:
    """GET /api/v1/warehouses — FBW warehouse list (supplies API key)."""
    if settings.e2e_mock_wb_warehouses:
        return [
            {
                "ID": 900001,
                "name": "E2E WB склад",
                "address": "E2E",
                "workTime": "24/7",
                "isActive": True,
                "isTransitActive": False,
            },
        ]
    base = (supplies_api_base or settings.wildberries_supplies_api_base).rstrip("/")
    url = f"{base}{MP_WAREHOUSES_PATH}"
    headers = {"Authorization": api_token}
    try:
        response = await client.get(url, headers=headers, timeout=60.0)
    except httpx.HTTPError as exc:
        raise WildberriesClientError(
            "transport_error",
            endpoint=MARKETPLACE_ORDERS_NEW_PATH,
        ) from exc
    if response.status_code >= 400:
        raise _wb_error_from_response(
            "upstream_error",
            response,
            endpoint=MARKETPLACE_ORDERS_NEW_PATH,
        )
    data = response.json()
    if isinstance(data, list):
        return cast(list[dict[str, Any]], data)
    return []


def _marketplace_orders_mock() -> list[dict[str, Any]]:
    return [
        {
            "id": 990001,
            "rid": "mock-rid-990001",
            "createdAt": "2026-07-01T10:00:00+03:00",
            "nmId": 424242,
            "chrtId": 111,
            "article": "E2E-MOCK",
            "skus": ["E2E-MOCK-BARCODE"],
            "price": 150000,
            "cargoType": 1,
            "officeId": 12345,
            "isLegal": False,
            "options": {"isB2B": False},
        },
    ]


async def fetch_marketplace_orders_new(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    marketplace_api_base: str | None = None,
) -> list[dict[str, Any]]:
    """GET /api/v3/orders/new — new assembly tasks."""
    if settings.e2e_mock_wb_marketplace_orders:
        return _marketplace_orders_mock()
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    url = f"{base}{MARKETPLACE_ORDERS_NEW_PATH}"
    headers = {"Authorization": api_token}
    try:
        response = await client.get(url, headers=headers, timeout=60.0)
    except httpx.HTTPError as exc:
        raise WildberriesClientError("transport_error") from exc
    if response.status_code >= 400:
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
        )
    data = response.json()
    if isinstance(data, list):
        return cast(list[dict[str, Any]], data)
    orders = data.get("orders") if isinstance(data, dict) else None
    if isinstance(orders, list):
        return cast(list[dict[str, Any]], orders)
    return []


async def fetch_marketplace_orders_page(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    marketplace_api_base: str | None = None,
    limit: int = 100,
    next_token: int | None = None,
) -> tuple[list[dict[str, Any]], int | None]:
    """GET /api/v3/orders — paginated order list (limit/next)."""
    if settings.e2e_mock_wb_marketplace_orders:
        return [], None
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    url = f"{base}{MARKETPLACE_ORDERS_PATH}"
    headers = {"Authorization": api_token}
    params: dict[str, Any] = {
        "limit": min(max(limit, 1), 1000),
        "next": 0 if next_token is None else next_token,
    }
    try:
        response = await client.get(url, headers=headers, params=params, timeout=60.0)
    except httpx.HTTPError as exc:
        raise WildberriesClientError("transport_error", endpoint=MARKETPLACE_ORDERS_PATH) from exc
    if response.status_code >= 400:
        raise _wb_error_from_response(
            "upstream_error",
            response,
            endpoint=MARKETPLACE_ORDERS_PATH,
        )
    data = response.json()
    if not isinstance(data, dict):
        return [], None
    orders_raw = data.get("orders")
    orders = orders_raw if isinstance(orders_raw, list) else []
    next_val = data.get("next")
    next_out: int | None = int(next_val) if next_val is not None else None
    return cast(list[dict[str, Any]], orders), next_out


async def cancel_marketplace_order(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    order_id: int,
    marketplace_api_base: str | None = None,
) -> None:
    """PATCH /api/v3/orders/{order_id}/cancel — seller-initiated cancel."""
    if settings.e2e_mock_wb_marketplace_orders:
        return
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    url = f"{base}{MARKETPLACE_ORDERS_CANCEL_PATH.format(order_id=order_id)}"
    headers = {"Authorization": api_token}
    try:
        response = await client.patch(url, headers=headers, timeout=60.0)
    except httpx.HTTPError as exc:
        raise WildberriesClientError(
            "transport_error",
            endpoint=MARKETPLACE_ORDERS_CANCEL_PATH.format(order_id=order_id),
        ) from exc
    if response.status_code >= 400:
        raise _wb_error_from_response(
            "upstream_error",
            response,
            endpoint=MARKETPLACE_ORDERS_CANCEL_PATH.format(order_id=order_id),
        )


async def fetch_marketplace_orders_status(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    order_ids: list[int],
    marketplace_api_base: str | None = None,
) -> list[dict[str, Any]]:
    """POST /api/v3/orders/status — batch status lookup."""
    if settings.e2e_mock_wb_marketplace_orders or _marketplace_supplies_mock_enabled():
        return [{"id": oid, "supplierStatus": "new", "wbStatus": "waiting"} for oid in order_ids]
    return await fetch_marketplace_orders_status_typed(
        client,
        api_token=api_token,
        order_ids=order_ids,
        marketplace_api_base=marketplace_api_base,
    )


def _marketplace_seller_warehouses_mock() -> list[dict[str, Any]]:
    return [
        {
            "id": 501001,
            "name": "E2E Seller Warehouse",
            "officeId": 601001,
            "address": "E2E Seller WH Address",
            "cargoType": 1,
            "deliveryType": 1,
        },
    ]


def _marketplace_seller_offices_mock() -> list[dict[str, Any]]:
    return [
        {
            "id": 601001,
            "officeId": 601001,
            "name": "E2E Seller Office",
            "city": "Moscow",
            "address": "E2E Office Address",
            "longitude": 37.62,
            "latitude": 55.75,
        },
    ]


async def fetch_marketplace_seller_warehouses(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    marketplace_api_base: str | None = None,
) -> list[dict[str, Any]]:
    """GET /api/v3/warehouses — seller virtual warehouses (Marketplace API key)."""
    if settings.e2e_mock_wb_marketplace_warehouses:
        return _marketplace_seller_warehouses_mock()
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    url = f"{base}{MARKETPLACE_SELLER_WAREHOUSES_PATH}"
    headers = {"Authorization": api_token}
    try:
        response = await client.get(url, headers=headers, timeout=60.0)
    except httpx.HTTPError as exc:
        raise WildberriesClientError(
            "transport_error",
            endpoint=MARKETPLACE_SELLER_WAREHOUSES_PATH,
        ) from exc
    if response.status_code >= 400:
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
            endpoint=MARKETPLACE_SELLER_WAREHOUSES_PATH,
            response_body=_wb_response_text(response),
        )
    data = response.json()
    if isinstance(data, list):
        return cast(list[dict[str, Any]], data)
    return []


async def fetch_marketplace_seller_offices(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    marketplace_api_base: str | None = None,
) -> list[dict[str, Any]]:
    """GET /api/v3/offices — seller pickup points / delivery zones (Marketplace API key)."""
    if settings.e2e_mock_wb_marketplace_warehouses:
        return _marketplace_seller_offices_mock()
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    url = f"{base}{MARKETPLACE_SELLER_OFFICES_PATH}"
    headers = {"Authorization": api_token}
    try:
        response = await client.get(url, headers=headers, timeout=60.0)
    except httpx.HTTPError as exc:
        raise WildberriesClientError(
            "transport_error",
            endpoint=MARKETPLACE_SELLER_OFFICES_PATH,
        ) from exc
    if response.status_code >= 400:
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
            endpoint=MARKETPLACE_SELLER_OFFICES_PATH,
            response_body=_wb_response_text(response),
        )
    data = response.json()
    if isinstance(data, list):
        return cast(list[dict[str, Any]], data)
    return []


def _marketplace_supplies_mock_enabled() -> bool:
    return settings.e2e_mock_wb_marketplace_supplies or settings.e2e_mock_wb_marketplace_orders


def _marketplace_supply_create_mock(name: str) -> dict[str, Any]:
    global _mock_supply_counter
    _mock_supply_counter += 1
    return {"id": f"WB-GI-MOCK-{_mock_supply_counter}", "name": name}


_TINY_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    "hQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _tiny_png_bytes() -> bytes:
    return base64.b64decode(_TINY_PNG_BASE64)


def _marketplace_order_stickers_mock(order_ids: list[int]) -> list[dict[str, Any]]:
    tiny_png = _TINY_PNG_BASE64
    return [
        {
            "orderId": oid,
            "partA": oid,
            "partB": oid + 1,
            "barcode": f"MOCK-{oid}",
            "file": tiny_png,
        }
        for oid in order_ids
    ]


async def create_marketplace_supply(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    name: str,
    marketplace_api_base: str | None = None,
) -> dict[str, Any]:
    """POST /api/v3/supplies — create FBS supply."""
    if _marketplace_supplies_mock_enabled():
        return _marketplace_supply_create_mock(name)
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    url = f"{base}{MARKETPLACE_SUPPLIES_PATH}"
    headers = {
        "Authorization": api_token,
        "Content-Type": "application/json",
    }
    payload = {"name": name}
    try:
        response = await client.post(url, headers=headers, json=payload, timeout=60.0)
    except httpx.HTTPError as exc:
        raise WildberriesClientError("transport_error", endpoint=MARKETPLACE_SUPPLIES_PATH) from exc
    if response.status_code >= 400:
        raise _wb_error_from_response(
            "upstream_error",
            response,
            endpoint=MARKETPLACE_SUPPLIES_PATH,
        )
    if response.status_code == 204 or not response.content:
        raise WildberriesClientError("invalid_response")
    try:
        data = response.json()
    except ValueError as exc:
        raise WildberriesClientError("invalid_response") from exc
    if not isinstance(data, dict):
        raise WildberriesClientError("invalid_response")
    return cast(dict[str, Any], data)


async def add_order_to_marketplace_supply(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    supply_id: str,
    order_id: int,
    marketplace_api_base: str | None = None,
) -> None:
    """PATCH /api/v3/supplies/{supply_id}/orders/{order_id} (legacy single-order path)."""
    if _marketplace_supplies_mock_enabled():
        return
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    url = f"{base}{MARKETPLACE_SUPPLIES_PATH}/{supply_id}/orders/{order_id}"
    headers = {"Authorization": api_token}
    try:
        response = await client.patch(url, headers=headers, timeout=60.0)
    except httpx.HTTPError as exc:
        raise WildberriesClientError(
            "transport_error",
            endpoint=f"{MARKETPLACE_SUPPLIES_PATH}/{supply_id}/orders/{order_id}",
        ) from exc
    if response.status_code >= 400:
        raise _wb_error_from_response(
            "upstream_error",
            response,
            endpoint=f"{MARKETPLACE_SUPPLIES_PATH}/{supply_id}/orders/{order_id}",
        )


async def add_orders_to_marketplace_supply(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    supply_id: str,
    order_ids: list[int],
    marketplace_api_base: str | None = None,
) -> None:
    """PATCH /api/marketplace/v3/supplies/{supply_id}/orders — batch ≤100."""
    if _marketplace_supplies_mock_enabled():
        if (error_code := consume_next_mock_marketplace_supply_add_error()) is not None:
            raise WildberriesClientError(error_code)
        return
    await add_orders_to_marketplace_supply_batch(
        client,
        api_token=api_token,
        supply_id=supply_id,
        order_ids=order_ids,
        marketplace_api_base=marketplace_api_base,
    )


async def fetch_marketplace_order_stickers(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    order_ids: list[int],
    marketplace_api_base: str | None = None,
    width: int = 58,
    height: int = 40,
) -> list[dict[str, Any]]:
    """POST /api/v3/orders/stickers — batch order stickers (PNG)."""
    if not order_ids:
        return []
    if _marketplace_supplies_mock_enabled():
        return _marketplace_order_stickers_mock(order_ids)
    return await fetch_marketplace_order_stickers_typed(
        client,
        api_token=api_token,
        order_ids=order_ids,
        marketplace_api_base=marketplace_api_base,
        width=width,
        height=height,
    )


async def deliver_marketplace_supply(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    supply_id: str,
    marketplace_api_base: str | None = None,
) -> None:
    """PATCH /api/v3/supplies/{supply_id}/deliver — hand supply to WB delivery."""
    if _marketplace_supplies_mock_enabled():
        _mock_delivered_supplies.add(supply_id)
        return
    await deliver_marketplace_supply_typed(
        client,
        api_token=api_token,
        supply_id=supply_id,
        marketplace_api_base=marketplace_api_base,
    )


async def fetch_marketplace_supply_details(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    supply_id: str,
    marketplace_api_base: str | None = None,
) -> MarketplaceSupplyDetails:
    """GET /api/v3/supplies/{supply_id} — supply details for deliver reconcile."""
    if _marketplace_supplies_mock_enabled():
        return MarketplaceSupplyDetails(
            supply_id=supply_id,
            name=None,
            done=supply_id in _mock_delivered_supplies,
        )
    return await fetch_marketplace_supply_details_typed(
        client,
        api_token=api_token,
        supply_id=supply_id,
        marketplace_api_base=marketplace_api_base,
    )


def _decode_barcode_payload(raw: Any) -> bytes | None:
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


async def fetch_marketplace_supply_barcode(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    supply_id: str,
    type: str = "png",
    marketplace_api_base: str | None = None,
) -> bytes:
    """GET /api/v3/supplies/{supply_id}/barcode — supply QR/barcode image."""
    if _marketplace_supplies_mock_enabled():
        return _tiny_png_bytes()
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    url = f"{base}{MARKETPLACE_SUPPLIES_PATH}/{supply_id}/barcode"
    headers = {"Authorization": api_token}
    params = {"type": type}
    try:
        response = await client.get(url, headers=headers, params=params, timeout=60.0)
    except httpx.HTTPError as exc:
        raise WildberriesClientError("transport_error") from exc
    if response.status_code >= 400:
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
        )
    content_type = response.headers.get("content-type", "")
    if "image" in content_type:
        return response.content
    data = response.json()
    if isinstance(data, dict):
        for key in ("file", "barcode", "image"):
            decoded = _decode_barcode_payload(data.get(key))
            if decoded is not None:
                return decoded
    raise WildberriesClientError("invalid_response")


def _mock_upsert_order_meta(order_id: int, kind: str, value: str) -> None:
    if kind == "sgtin":
        key = "sgtins"
    elif kind in {"uin", "imei", "gtin"}:
        key = kind
    else:
        raise WildberriesClientError("invalid_meta_kind")
    bucket = _mock_order_meta.setdefault(order_id, {})
    entries = bucket.setdefault(key, [])
    for entry in entries:
        if entry.get("value") == value:
            entry["checkStatus"] = "new"
            return
    entries.append({"value": value, "checkStatus": "new"})


def _mock_order_meta_response(order_id: int) -> dict[str, Any]:
    return dict(_mock_order_meta.get(order_id, {}))


def mock_order_meta_snapshot(order_id: int) -> dict[str, Any]:
    """Снимок mock-меты заказа для batch-клиента (e2e_mock_wb_marketplace_marking).

    Batch-роут POST /api/marketplace/v3/orders/meta живёт в wildberries_fbs_client,
    но обязан читать тот же mock-стор, что и одиночные PUT/GET здесь, иначе под
    моком метаданные расходятся.
    """
    return _mock_order_meta_response(order_id)


async def put_marketplace_order_meta(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    order_id: int,
    kind: str,
    value: str,
    marketplace_api_base: str | None = None,
) -> None:
    """PUT /api/v3/orders/{order_id}/meta/{kind} — attach marking identifier."""
    if settings.e2e_mock_wb_marketplace_marking:
        _mock_upsert_order_meta(order_id, kind, value)
        return
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    url = f"{base}{MARKETPLACE_ORDER_META_PATH.format(order_id=order_id)}/{kind}"
    headers = {
        "Authorization": api_token,
        "Content-Type": "application/json",
    }
    payload = build_marketplace_order_meta_put_body(kind, value)
    try:
        response = await client.put(url, headers=headers, json=payload, timeout=60.0)
    except httpx.HTTPError as exc:
        raise WildberriesClientError("transport_error") from exc
    if response.status_code >= 400:
        if response.status_code == 409:
            from app.services.wildberries_fbs_client import parse_business_error

            raise parse_business_error(response)
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
        )


_mock_trbx_counter = 0
_mock_trbx_by_supply: dict[str, list[str]] = {}
_mock_supply_counter = 0
_mock_delivered_supplies: set[str] = set()


def _next_mock_trbx_id() -> str:
    global _mock_trbx_counter
    _mock_trbx_counter += 1
    return f"MOCK-TRBX-{_mock_trbx_counter}"


def _mock_trbx_list_for_supply(supply_id: str) -> list[str]:
    return list(_mock_trbx_by_supply.get(supply_id, []))


def _parse_trbx_ids_from_response(data: Any) -> list[str]:
    if isinstance(data, list):
        ids: list[str] = []
        for item in data:
            if isinstance(item, str):
                ids.append(item)
            elif isinstance(item, dict):
                for key in ("id", "trbxId", "trbx_id"):
                    if key in item:
                        ids.append(str(item[key]))
                        break
        return ids
    if isinstance(data, dict):
        for key in ("trbxIds", "trbx_ids", "data", "trbxes"):
            val = data.get(key)
            if val is not None:
                parsed = _parse_trbx_ids_from_response(val)
                return parsed
    raise WildberriesClientError("invalid_response")


def _marketplace_trbx_create_mock(amount: int, *, supply_id: str) -> list[str]:
    ids = [_next_mock_trbx_id() for _ in range(amount)]
    _mock_trbx_by_supply.setdefault(supply_id, []).extend(ids)
    return ids


def _marketplace_trbx_delete_mock(trbx_ids: list[str], *, supply_id: str) -> None:
    current = _mock_trbx_by_supply.get(supply_id, [])
    remove = set(trbx_ids)
    _mock_trbx_by_supply[supply_id] = [row for row in current if row not in remove]


def _marketplace_trbx_stickers_mock(trbx_ids: list[str]) -> list[dict[str, Any]]:
    tiny_png = _TINY_PNG_BASE64
    return [
        {"trbxId": trbx_id, "file": tiny_png, "barcode": f"MOCK-QR-{trbx_id}"}
        for trbx_id in trbx_ids
    ]


async def create_marketplace_supply_trbx(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    supply_id: str,
    amount: int,
    marketplace_api_base: str | None = None,
) -> list[str]:
    """POST /api/v3/supplies/{supply_id}/trbx — create cargo places."""
    if _marketplace_supplies_mock_enabled():
        return _marketplace_trbx_create_mock(amount, supply_id=supply_id)
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    url = f"{base}{MARKETPLACE_SUPPLIES_PATH}/{supply_id}/trbx"
    headers = {
        "Authorization": api_token,
        "Content-Type": "application/json",
    }
    payload = {"amount": amount}
    try:
        response = await client.post(url, headers=headers, json=payload, timeout=60.0)
    except httpx.HTTPError as exc:
        raise WildberriesClientError("transport_error") from exc
    if response.status_code >= 400:
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
        )
    data = response.json()
    ids = _parse_trbx_ids_from_response(data)
    if len(ids) != amount:
        raise WildberriesClientError("invalid_response")
    return ids


async def add_orders_to_marketplace_trbx(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    supply_id: str,
    trbx_id: str,
    order_ids: list[int],
    marketplace_api_base: str | None = None,
) -> None:
    """PATCH /api/v3/supplies/{supply_id}/trbx/{trbx_id} — bind orders to cargo place."""
    if _marketplace_supplies_mock_enabled():
        return
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    url = f"{base}{MARKETPLACE_SUPPLIES_PATH}/{supply_id}/trbx/{trbx_id}"
    headers = {
        "Authorization": api_token,
        "Content-Type": "application/json",
    }
    payload = {"orderIds": order_ids}
    try:
        response = await client.patch(url, headers=headers, json=payload, timeout=60.0)
    except httpx.HTTPError as exc:
        raise WildberriesClientError("transport_error") from exc
    if response.status_code >= 400:
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
        )


async def fetch_marketplace_trbx_stickers(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    supply_id: str,
    trbx_ids: list[str],
    type: str = "png",
    marketplace_api_base: str | None = None,
) -> list[dict[str, Any]]:
    """POST /api/v3/supplies/{supply_id}/trbx/stickers — batch trbx QR stickers."""
    if not trbx_ids:
        return []
    if _marketplace_supplies_mock_enabled():
        return _marketplace_trbx_stickers_mock(trbx_ids)
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    url = f"{base}{MARKETPLACE_SUPPLIES_PATH}/{supply_id}/trbx/stickers"
    headers = {
        "Authorization": api_token,
        "Content-Type": "application/json",
    }
    params: dict[str, str] = {"type": type}
    payload = {"trbxIds": trbx_ids}
    try:
        response = await client.post(
            url, headers=headers, params=params, json=payload, timeout=60.0
        )
    except httpx.HTTPError as exc:
        raise WildberriesClientError("transport_error") from exc
    if response.status_code >= 400:
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
        )
    data = response.json()
    if isinstance(data, list):
        return cast(list[dict[str, Any]], data)
    stickers = data.get("stickers") if isinstance(data, dict) else None
    if isinstance(stickers, list):
        return cast(list[dict[str, Any]], stickers)
    return []


async def fetch_marketplace_supply_trbx_list(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    supply_id: str,
    marketplace_api_base: str | None = None,
) -> list[str]:
    """GET /api/v3/supplies/{supply_id}/trbx — current cargo place IDs."""
    if _marketplace_supplies_mock_enabled():
        return _mock_trbx_list_for_supply(supply_id)
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    url = f"{base}{MARKETPLACE_SUPPLIES_PATH}/{supply_id}/trbx"
    headers = {"Authorization": api_token}
    try:
        response = await client.get(url, headers=headers, timeout=60.0)
    except httpx.HTTPError as exc:
        raise WildberriesClientError("transport_error") from exc
    if response.status_code >= 400:
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
        )
    data = response.json()
    return _parse_trbx_ids_from_response(data)


async def delete_marketplace_supply_trbx(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    supply_id: str,
    trbx_ids: list[str],
    marketplace_api_base: str | None = None,
) -> None:
    """DELETE /api/v3/supplies/{supply_id}/trbx — remove cargo places."""
    if not trbx_ids:
        return
    if _marketplace_supplies_mock_enabled():
        _marketplace_trbx_delete_mock(trbx_ids, supply_id=supply_id)
        return
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    url = f"{base}{MARKETPLACE_SUPPLIES_PATH}/{supply_id}/trbx"
    headers = {
        "Authorization": api_token,
        "Content-Type": "application/json",
    }
    payload = {"trbxIds": trbx_ids}
    try:
        response = await client.request(
            "DELETE",
            url,
            headers=headers,
            json=payload,
            timeout=60.0,
        )
    except httpx.HTTPError as exc:
        raise WildberriesClientError("transport_error") from exc
    if response.status_code >= 400:
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
        )
