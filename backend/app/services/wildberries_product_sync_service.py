"""Full WB cards fetch + product upsert (all pages) for one seller or all sellers."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.background_job import BackgroundJob
from app.models.product import Product
from app.models.seller import Seller
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.services.wildberries_client import WildberriesClientError
from app.services.wildberries_credentials_service import get_decrypted_tokens_for_seller
from app.services.wildberries_import_cards_service import upsert_imported_cards
from app.services.wildberries_product_import_service import upsert_products_from_wb_cards
from app.services.wildberries_sync_service import WildberriesSyncError, fetch_all_cards

logger = logging.getLogger(__name__)


def _parse_card_nm_id(card: dict[str, Any]) -> int | None:
    """Same parsing rule as ``upsert_products_from_wb_cards`` (duplicated by
    convention: this module doesn't import that module's private helper, see
    ``wildberries_import_cards_service._parse_nm_id`` for the same pattern)."""
    raw = card.get("nmID") if "nmID" in card else card.get("nmId")
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    return None


async def get_selected_wb_nm_ids(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID,
) -> set[int]:
    """nmID of the WB cards already "on fulfilment" for this seller (WMS-548 А3).

    There is no separate selection flag: a card counts as selected exactly when
    this seller already has a Product row with its nmID. One flat query, no
    ``.in_(...)`` list — it filters by tenant_id/seller_id (both indexed
    equality conditions), so it never hits the IN-list size limit that WMS-538
    ran into on large catalogues.
    """
    stmt = (
        select(Product.wb_nm_id)
        .where(
            Product.tenant_id == tenant_id,
            Product.seller_id == seller_id,
            Product.wb_nm_id.isnot(None),
        )
        .distinct()
    )
    res = await session.execute(stmt)
    return {int(nm) for (nm,) in res.all() if nm is not None}


def filter_wb_cards_to_selected(
    cards: list[Any], selected_nm_ids: set[int],
) -> list[Any]:
    """Keep only cards already selected (see ``get_selected_wb_nm_ids``).

    WMS-548 R4/R5: saving a key or syncing must not create Product rows for a
    card that hasn't been added to the fulfilment yet. Typed ``list[Any]`` (not
    ``list[dict[str, Any]]``/``list[object]``) purely so this drops into both
    callers unchanged — the API layer's ``total_cards: list[object]`` and the
    sync service's ``list[dict[str, Any]]`` — ``list`` is invariant in mypy.
    """
    return [
        card
        for card in cards
        if isinstance(card, dict) and _parse_card_nm_id(card) in selected_nm_ids
    ]


async def fetch_all_wb_cards(
    http_client: httpx.AsyncClient,
    *,
    api_token: str,
) -> list[dict[str, Any]]:
    """Use the same complete-page fetch as the fulfillment card import."""
    cards, _cursor_present = await fetch_all_cards(http_client, api_token=api_token)
    return [card for card in cards if isinstance(card, dict)]


async def sync_wb_products_for_seller(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> dict[str, Any]:
    """Import all WB cards and upsert size-variant Product rows for one seller."""
    pair = await get_decrypted_tokens_for_seller(session, tenant_id, seller_id)
    if pair is None:
        raise WildberriesSyncError("seller_not_found")
    content_token, _supplies = pair
    if not content_token:
        raise WildberriesSyncError("missing_content_token")
    try:
        cards = await fetch_all_wb_cards(http_client, api_token=content_token)
    except WildberriesClientError as exc:
        suffix = f"_{exc.status_code}" if exc.status_code else ""
        raise WildberriesSyncError(f"wb_{exc.code}{suffix}") from exc
    return await _save_wb_cards(session, tenant_id, seller_id, cards)


async def _save_wb_cards(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID,
    cards: list[dict[str, Any]],
) -> dict[str, Any]:
    # Снимок обновляется по всем карточкам всегда; товары WMS — только по тем,
    # что уже выбраны (см. get_selected_wb_nm_ids). WMS-548 R5: синхронизация не
    # заводит новые карточки и не трогает те, что селлер не выбрал.
    saved = await upsert_imported_cards(session, tenant_id, seller_id, cards)
    selected_nm_ids = await get_selected_wb_nm_ids(session, tenant_id, seller_id)
    prod_stats = await upsert_products_from_wb_cards(
        session,
        tenant_id,
        seller_id,
        filter_wb_cards_to_selected(list(cards), selected_nm_ids),
    )
    return {
        "seller_id": str(seller_id),
        "tenant_id": str(tenant_id),
        "cards_received": len(cards),
        "cards_saved": saved,
        **prod_stats,
    }


async def _sync_scheduled_seller(
    tenant_id: uuid.UUID, seller_id: uuid.UUID, http_client: httpx.AsyncClient,
) -> dict[str, Any]:
    # Own the read session: do not commit a caller's transaction to release its
    # connection. No DB session/lock remains open while fetching all WB pages.
    async with SessionLocal() as session:
        active_job = await session.scalar(select(BackgroundJob.id).where(
            BackgroundJob.tenant_id == tenant_id,
            BackgroundJob.job_type == "wildberries_cards_sync",
            BackgroundJob.status.in_(("pending", "running")),
            BackgroundJob.payload_json["seller_id"].as_string() == str(seller_id),
        ).limit(1))
        if active_job is not None:
            raise WildberriesSyncError("manual_sync_active")
        pair = await get_decrypted_tokens_for_seller(session, tenant_id, seller_id)
        if pair is None or not pair[0]:
            raise WildberriesSyncError("missing_content_token")
        content_token = pair[0]
    try:
        cards = await fetch_all_wb_cards(http_client, api_token=content_token)
    except WildberriesClientError as exc:
        suffix = f"_{exc.status_code}" if exc.status_code else ""
        raise WildberriesSyncError(f"wb_{exc.code}{suffix}") from exc
    async with SessionLocal() as session:
        # A disconnect/change during HTTP must not persist that old response.
        pair = await get_decrypted_tokens_for_seller(session, tenant_id, seller_id)
        if pair is None or pair[0] != content_token:
            raise WildberriesSyncError("content_token_changed")
        return await _save_wb_cards(session, tenant_id, seller_id, cards)


async def run_wb_products_sync_all_sellers() -> dict[str, Any]:
    """Hourly/CLI WB-only import, sequentially for connected content credentials."""
    async with SessionLocal() as session:
        stmt = (
            select(Seller.id, Seller.tenant_id, Seller.name)
            .join(
                SellerWildberriesCredentials,
                SellerWildberriesCredentials.seller_id == Seller.id,
            )
            .where(
                SellerWildberriesCredentials.content_token_encrypted.isnot(None),
                SellerWildberriesCredentials.content_token_encrypted != "",
            )
            .order_by(Seller.tenant_id, Seller.name)
        )
        res = await session.execute(stmt)
        sellers = list(res.all())

    ok: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    async with httpx.AsyncClient() as http_client:
        for seller_id, tenant_id, seller_name in sellers:
            try:
                result = await _sync_scheduled_seller(
                    tenant_id,
                    seller_id,
                    http_client,
                )
            except WildberriesSyncError as exc:
                code = exc.code
                if code in ("missing_content_token", "manual_sync_active", "content_token_changed"):
                    skipped.append(
                        {
                            "seller_id": str(seller_id),
                            "seller_name": seller_name,
                            "reason": code,
                        }
                    )
                    logger.info(
                        "wb products sync skipped seller=%s reason=%s",
                        seller_id,
                        code,
                    )
                    continue
                failed.append(
                    {
                        "seller_id": str(seller_id),
                        "seller_name": seller_name,
                        "error": code,
                    }
                )
                logger.warning(
                    "wb products sync failed seller=%s error=%s",
                    seller_id,
                    code,
                )
            except Exception as exc:
                failed.append(
                    {
                        "seller_id": str(seller_id),
                        "seller_name": seller_name,
                        "error": str(exc),
                    }
                )
                logger.exception("wb products sync failed seller=%s", seller_id)
            else:
                ok.append(result)
                logger.info(
                    "wb products sync ok seller=%s cards=%s created=%s "
                    "updated=%s legacy_old=%s",
                    seller_id,
                    result.get("cards_received"),
                    result.get("products_created"),
                    result.get("products_updated"),
                    result.get("legacy_marked_old"),
                )

    summary = {
        "sellers_total": len(sellers),
        "sellers_ok": len(ok),
        "sellers_failed": len(failed),
        "sellers_skipped": len(skipped),
        "ok": ok,
        "failed": failed,
        "skipped": skipped,
    }
    logger.info(
        "wb products sync all sellers done ok=%s failed=%s skipped=%s",
        len(ok),
        len(failed),
        len(skipped),
    )
    return summary
