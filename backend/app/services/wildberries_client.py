"""Wildberries read-only API client (import/sync). Tokens are never logged."""

from __future__ import annotations

from typing import Any, cast

import httpx

from app.core.settings import settings

CARDS_LIST_PATH = "/content/v2/get/cards/list"
SUPPLIES_LIST_PATH = "/api/v1/supplies"


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
            "cards": [{"nmID": 424242, "vendorCode": "E2E-MOCK"}],
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
