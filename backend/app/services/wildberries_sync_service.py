"""Wildberries import sync (read-only); uses stored seller tokens."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.wildberries_client import WildberriesClientError, fetch_cards_list
from app.services.wildberries_credentials_service import get_decrypted_tokens_for_seller


class WildberriesSyncError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


async def sync_cards_list_first_page(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> dict[str, Any]:
    """Fetch first page of WB cards for seller (content API token required)."""
    pair = await get_decrypted_tokens_for_seller(session, tenant_id, seller_id)
    if pair is None:
        raise WildberriesSyncError("seller_not_found")
    content_token, _supplies = pair
    if not content_token:
        raise WildberriesSyncError("missing_content_token")
    try:
        data = await fetch_cards_list(http_client, api_token=content_token)
    except WildberriesClientError as exc:
        suffix = f"_{exc.status_code}" if exc.status_code else ""
        raise WildberriesSyncError(f"wb_{exc.code}{suffix}") from exc
    cards = data.get("cards")
    n_cards = len(cards) if isinstance(cards, list) else 0
    return {
        "seller_id": str(seller_id),
        "cards_received": n_cards,
        "cursor_present": data.get("cursor") is not None,
    }
