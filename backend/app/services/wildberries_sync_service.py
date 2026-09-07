"""Wildberries import sync (read-only); uses stored seller tokens."""

from __future__ import annotations

import asyncio
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
from app.services.wildberries_import_supplies_service import (
    external_key_from_supply_row,
    upsert_imported_supplies,
)


class WildberriesSyncError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


async def sync_cards_list(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> dict[str, Any]:
    """Fetch all WB card pages; preserve the existing snapshot-only import."""
    pair = await get_decrypted_tokens_for_seller(session, tenant_id, seller_id)
    if pair is None:
        raise WildberriesSyncError("seller_not_found")
    content_token, _supplies = pair
    if not content_token:
        raise WildberriesSyncError("missing_content_token")
    card_list: list[Any] = []
    updated_at: str | None = None
    nm_id: int | None = None
    seen: set[tuple[str, int]] = set()
    cursor_present = False
    try:
        while True:
            data = await fetch_cards_list(
                http_client,
                api_token=content_token,
                limit=100,
                cursor_updated_at=updated_at,
                cursor_nm_id=nm_id,
            )
            cards = data.get("cards")
            if not isinstance(cards, list):
                raise WildberriesClientError("invalid_response")
            card_list.extend(cards)
            cursor = data.get("cursor")
            cursor_present = cursor_present or cursor is not None
            # WB's cursor.total counts THIS page, not the entire catalogue.
            if len(cards) < 100:
                break
            if not isinstance(cursor, dict):
                raise WildberriesClientError("invalid_response")
            next_updated_at, next_nm_id = cursor.get("updatedAt"), cursor.get("nmID")
            if (
                not isinstance(next_updated_at, str)
                or not next_updated_at.strip()
                or not isinstance(next_nm_id, int)
                or isinstance(next_nm_id, bool)
            ):
                raise WildberriesClientError("invalid_response")
            next_cursor = (next_updated_at, next_nm_id)
            if next_cursor in seen:
                raise WildberriesClientError("pagination_stalled")
            seen.add(next_cursor)
            updated_at, nm_id = next_cursor
            await asyncio.sleep(0.6)  # WB Content: 100 requests/minute.
    except WildberriesClientError as exc:
        suffix = f"_{exc.status_code}" if exc.status_code else ""
        raise WildberriesSyncError(f"wb_{exc.code}{suffix}") from exc
    n_cards = len(card_list)
    saved = await upsert_imported_cards(session, tenant_id, seller_id, card_list)
    return {
        "seller_id": str(seller_id),
        "cards_received": n_cards,
        "cards_saved": saved,
        "cursor_present": cursor_present,
    }


async def sync_supplies_list(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> dict[str, Any]:
    """Fetch all WB FBW supply pages (supplies API token required)."""
    pair = await get_decrypted_tokens_for_seller(session, tenant_id, seller_id)
    if pair is None:
        raise WildberriesSyncError("seller_not_found")
    _content, supplies_token = pair
    if not supplies_token:
        raise WildberriesSyncError("missing_supplies_token")
    rows: list[dict[str, Any]] = []
    seen_pages: set[tuple[str | None, ...]] = set()
    try:
        while True:
            page = await fetch_supplies_list(
                http_client, api_token=supplies_token, limit=100, offset=len(rows)
            )
            page_keys = tuple(external_key_from_supply_row(row) for row in page)
            if page and page_keys in seen_pages:
                raise WildberriesClientError("pagination_stalled")
            seen_pages.add(page_keys)
            rows.extend(page)
            if len(page) < 100:
                break
            await asyncio.sleep(2)  # WB FBW supplies: 30 requests/minute.
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
