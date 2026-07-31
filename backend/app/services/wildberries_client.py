"""Wildberries read-only API client (import/sync). Tokens are never logged."""

from __future__ import annotations

import base64
import binascii
from typing import Any, cast

import httpx

from app.core.settings import settings

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

# WB Marketplace meta PUT bodies use plural array keys per kind (see dev.wildberries.ru).
_META_PUT_BODY_KEYS: dict[str, str] = {
    "sgtin": "sgtins",
    "uin": "uins",
    "imei": "imeis",
    "gtin": "gtins",
}

# In-memory store for e2e_mock_wb_marketplace_marking (tests may clear via reset helper).
_mock_order_meta: dict[int, dict[str, list[dict[str, str]]]] = {}


def reset_mock_marketplace_order_meta() -> None:
    """Clear mock marking meta store (tests only)."""
    _mock_order_meta.clear()


def _meta_plural_key(kind: str) -> str:
    key = _META_PUT_BODY_KEYS.get(kind)
    if key is None:
        raise WildberriesClientError("invalid_meta_kind")
    return key


def build_marketplace_order_meta_put_body(kind: str, value: str) -> dict[str, list[str]]:
    """Build JSON body for PUT /api/v3/orders/{id}/meta/{kind}."""
    return {_meta_plural_key(kind): [value]}


class WildberriesClientError(Exception):
    def __init__(self, code: str, *, status_code: int | None = None) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


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
                    "photos": [{"big": "https://example.com/e2e-mock-wb-product.jpg"}],
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
    return cast(dict[str, Any], response.json())


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
        raise WildberriesClientError("transport_error") from exc
    if response.status_code >= 400:
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
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
    params: dict[str, Any] = {"limit": min(max(limit, 1), 1000)}
    if next_token is not None:
        params["next"] = next_token
    try:
        response = await client.get(url, headers=headers, params=params, timeout=60.0)
    except httpx.HTTPError as exc:
        raise WildberriesClientError("transport_error") from exc
    if response.status_code >= 400:
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
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
        raise WildberriesClientError("transport_error") from exc
    if response.status_code >= 400:
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
        )


async def fetch_marketplace_orders_status(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    order_ids: list[int],
    marketplace_api_base: str | None = None,
) -> list[dict[str, Any]]:
    """POST /api/v3/orders/status — batch status lookup."""
    if settings.e2e_mock_wb_marketplace_orders:
        return [{"id": oid, "supplierStatus": "new", "wbStatus": "waiting"} for oid in order_ids]
    if not order_ids:
        return []
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    url = f"{base}{MARKETPLACE_ORDERS_STATUS_PATH}"
    headers = {
        "Authorization": api_token,
        "Content-Type": "application/json",
    }
    payload = {"orders": order_ids}
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
    if isinstance(data, list):
        return cast(list[dict[str, Any]], data)
    orders = data.get("orders") if isinstance(data, dict) else None
    if isinstance(orders, list):
        return cast(list[dict[str, Any]], orders)
    return []


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
        raise WildberriesClientError("transport_error") from exc
    if response.status_code >= 400:
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
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
        raise WildberriesClientError("transport_error") from exc
    if response.status_code >= 400:
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
        )
    data = response.json()
    if isinstance(data, list):
        return cast(list[dict[str, Any]], data)
    return []


def _marketplace_supplies_mock_enabled() -> bool:
    return settings.e2e_mock_wb_marketplace_supplies or settings.e2e_mock_wb_marketplace_orders


def _marketplace_supply_create_mock(name: str) -> dict[str, Any]:
    return {"id": "WB-GI-MOCK-1", "name": name}


_TINY_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
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
        raise WildberriesClientError("transport_error") from exc
    if response.status_code >= 400:
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
        )
    data = response.json()
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
    """PATCH /api/v3/supplies/{supply_id}/orders/{order_id}."""
    if _marketplace_supplies_mock_enabled():
        return
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    url = f"{base}{MARKETPLACE_SUPPLIES_PATH}/{supply_id}/orders/{order_id}"
    headers = {"Authorization": api_token}
    try:
        response = await client.patch(url, headers=headers, timeout=60.0)
    except httpx.HTTPError as exc:
        raise WildberriesClientError("transport_error") from exc
    if response.status_code >= 400:
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
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
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    url = f"{base}{MARKETPLACE_ORDER_STICKERS_PATH}"
    headers = {
        "Authorization": api_token,
        "Content-Type": "application/json",
    }
    params: dict[str, str | int] = {"type": "png", "width": width, "height": height}
    payload = {"orders": order_ids}
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


async def deliver_marketplace_supply(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    supply_id: str,
    marketplace_api_base: str | None = None,
) -> None:
    """PATCH /api/v3/supplies/{supply_id}/deliver — hand supply to WB delivery."""
    if _marketplace_supplies_mock_enabled():
        return
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    url = f"{base}{MARKETPLACE_SUPPLIES_PATH}/{supply_id}/deliver"
    headers = {"Authorization": api_token}
    try:
        response = await client.patch(url, headers=headers, timeout=60.0)
    except httpx.HTTPError as exc:
        raise WildberriesClientError("transport_error") from exc
    if response.status_code >= 400:
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
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
    plural = _meta_plural_key(kind)
    bucket = _mock_order_meta.setdefault(order_id, {})
    entries = bucket.setdefault(plural, [])
    for entry in entries:
        if entry.get("value") == value:
            entry["checkStatus"] = "new"
            return
    entries.append({"value": value, "checkStatus": "new"})


def _mock_order_meta_response(order_id: int) -> dict[str, Any]:
    return dict(_mock_order_meta.get(order_id, {}))


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
        raise WildberriesClientError(
            "upstream_error",
            status_code=response.status_code,
        )


async def fetch_marketplace_order_meta(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    order_id: int,
    marketplace_api_base: str | None = None,
) -> dict[str, Any]:
    """GET /api/v3/orders/{order_id}/meta — marking identifiers and check statuses."""
    if settings.e2e_mock_wb_marketplace_marking:
        return _mock_order_meta_response(order_id)
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    url = f"{base}{MARKETPLACE_ORDER_META_PATH.format(order_id=order_id)}"
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
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    return {}


_mock_trbx_counter = 0


def _next_mock_trbx_id() -> str:
    global _mock_trbx_counter
    _mock_trbx_counter += 1
    return f"MOCK-TRBX-{_mock_trbx_counter}"


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
                if parsed:
                    return parsed
    raise WildberriesClientError("invalid_response")


def _marketplace_trbx_create_mock(amount: int) -> list[str]:
    return [_next_mock_trbx_id() for _ in range(amount)]


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
        return _marketplace_trbx_create_mock(amount)
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
