"""Wildberries read-only API client (import/sync). Tokens are never logged."""

from __future__ import annotations

from typing import Any, cast

import httpx

from app.core.settings import settings

CARDS_LIST_PATH = "/content/v2/get/cards/list"


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
    payload: dict[str, Any] = {
        "settings": {
            "cursor": {"limit": min(limit, 100)},
        },
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
