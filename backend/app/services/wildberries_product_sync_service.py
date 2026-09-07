"""Full WB cards fetch + product upsert (all pages) for one seller or all sellers."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.seller import Seller
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.services.wildberries_client import WildberriesClientError
from app.services.wildberries_credentials_service import get_decrypted_tokens_for_seller
from app.services.wildberries_import_cards_service import upsert_imported_cards
from app.services.wildberries_product_import_service import upsert_products_from_wb_cards
from app.services.wildberries_sync_service import WildberriesSyncError, fetch_all_cards

logger = logging.getLogger(__name__)


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
    saved = await upsert_imported_cards(session, tenant_id, seller_id, cards)
    prod_stats = await upsert_products_from_wb_cards(
        session,
        tenant_id,
        seller_id,
        list(cards),
    )
    return {
        "seller_id": str(seller_id),
        "tenant_id": str(tenant_id),
        "cards_received": len(cards),
        "cards_saved": saved,
        **prod_stats,
    }


async def run_wb_products_sync_all_sellers() -> dict[str, Any]:
    """Post-deploy: sync WB products for every seller with a content API token."""
    async with SessionLocal() as session:
        stmt = (
            select(Seller.id, Seller.tenant_id, Seller.name)
            .join(
                SellerWildberriesCredentials,
                SellerWildberriesCredentials.seller_id == Seller.id,
            )
            .where(SellerWildberriesCredentials.content_token_encrypted.isnot(None))
            .order_by(Seller.tenant_id, Seller.name)
        )
        res = await session.execute(stmt)
        sellers = list(res.all())

    ok: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    async with httpx.AsyncClient() as http_client:
        for seller_id, tenant_id, seller_name in sellers:
            async with SessionLocal() as session:
                try:
                    result = await sync_wb_products_for_seller(
                        session,
                        tenant_id,
                        seller_id,
                        http_client,
                    )
                except WildberriesSyncError as exc:
                    code = exc.code
                    if code == "missing_content_token":
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
