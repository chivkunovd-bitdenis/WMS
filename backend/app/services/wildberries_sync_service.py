"""Wildberries import sync (read-only); uses stored seller tokens."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.wildberries_client import (
    WildberriesClientError,
    fetch_cards_list,
    fetch_supplies_list,
)
from app.services.wildberries_credentials_service import get_decrypted_tokens_for_seller
from app.services.wildberries_import_cards_service import upsert_imported_cards
from app.services.wildberries_import_supplies_service import upsert_imported_supplies


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
    card_list = cards if isinstance(cards, list) else []
    n_cards = len(card_list)
    saved = await upsert_imported_cards(session, tenant_id, seller_id, card_list)
    return {
        "seller_id": str(seller_id),
        "cards_received": n_cards,
        "cards_saved": saved,
        "cursor_present": data.get("cursor") is not None,
    }


async def sync_supplies_list_first_page(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> dict[str, Any]:
    """Fetch first page of WB FBW supplies (supplies API token required)."""
    pair = await get_decrypted_tokens_for_seller(session, tenant_id, seller_id)
    if pair is None:
        raise WildberriesSyncError("seller_not_found")
    _content, supplies_token = pair
    if not supplies_token:
        raise WildberriesSyncError("missing_supplies_token")
    try:
        rows = await fetch_supplies_list(
            http_client, api_token=supplies_token, limit=100, offset=0
        )
    except WildberriesClientError as exc:
        suffix = f"_{exc.status_code}" if exc.status_code else ""
        raise WildberriesSyncError(f"wb_{exc.code}{suffix}") from exc
    n = len(rows)
    saved = await upsert_imported_supplies(session, tenant_id, seller_id, rows)
    return {
        "seller_id": str(seller_id),
        "supplies_received": n,
        "supplies_saved": saved,
    }
