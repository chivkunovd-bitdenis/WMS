"""Backfill every WB size barcode onto existing WMS products.

The command is read-only by default. Pass ``--apply`` to commit one WB page at
a time. It never creates Product rows and never prints the stored WB token.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.product import Product
from app.models.seller import Seller
from app.services.product_barcode_service import add_barcodes_to_product
from app.services.wb_card_enrichment import iter_size_variants_from_card
from app.services.wildberries_client import WildberriesClientError, fetch_cards_list
from app.services.wildberries_credentials_service import get_decrypted_tokens_for_seller

PAGE_LIMIT = 100
REQUEST_PAUSE_SECONDS = 0.65
MAX_FETCH_ATTEMPTS = 5


@dataclass
class BackfillReport:
    mode: str
    tenant_id: str
    seller_id: str
    wb_cards_read: int = 0
    existing_products_found: int = 0
    barcodes_existing: int = 0
    barcodes_added: int = 0
    chrt_ids_not_found_count: int = 0
    chrt_ids_not_found: list[int] = field(default_factory=list)
    barcode_conflicts_count: int = 0
    barcode_conflicts: list[dict[str, str]] = field(default_factory=list)
    errors_count: int = 0
    errors: list[str] = field(default_factory=list)
    last_successful_cursor: dict[str, object] | None = None


async def _fetch_page_with_retry(
    client: httpx.AsyncClient,
    *,
    api_token: str,
    cursor_updated_at: str | None,
    cursor_nm_id: int | None,
) -> dict[str, Any]:
    for attempt in range(MAX_FETCH_ATTEMPTS):
        try:
            return await fetch_cards_list(
                client,
                api_token=api_token,
                limit=PAGE_LIMIT,
                cursor_updated_at=cursor_updated_at,
                cursor_nm_id=cursor_nm_id,
            )
        except WildberriesClientError as exc:
            retryable = exc.code == "transport_error" or exc.status_code == 429 or (
                exc.status_code is not None and 500 <= exc.status_code < 600
            )
            if not retryable or attempt + 1 >= MAX_FETCH_ATTEMPTS:
                raise
            await asyncio.sleep(min(2**attempt, 8))
    raise RuntimeError("unreachable")


async def process_cards_page(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    cards: list[object],
    apply: bool,
    report: BackfillReport,
) -> None:
    variants = [
        variant
        for card in cards
        if isinstance(card, dict)
        for variant in iter_size_variants_from_card(card)
    ]
    chrt_ids = {variant.chrt_id for variant in variants if variant.chrt_id is not None}
    products = list(
        (
            await session.execute(
                select(Product).where(
                    Product.tenant_id == tenant_id,
                    Product.seller_id == seller_id,
                    Product.wb_chrt_id.in_(chrt_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    by_chrt: dict[int, list[Product]] = {}
    for product in products:
        if product.wb_chrt_id is not None:
            by_chrt.setdefault(int(product.wb_chrt_id), []).append(product)

    found_ids: set[uuid.UUID] = set()
    for variant in variants:
        if variant.chrt_id is None:
            continue
        matches = by_chrt.get(variant.chrt_id, [])
        if len(matches) != 1:
            if not matches:
                report.chrt_ids_not_found.append(variant.chrt_id)
            else:
                report.errors.append(
                    f"duplicate_product_chrt_id:{variant.chrt_id}:{len(matches)}"
                )
            continue
        product = matches[0]
        found_ids.add(product.id)
        result = await add_barcodes_to_product(session, product, variant.barcodes)
        if result.conflicts:
            report.barcode_conflicts.extend(
                {
                    "barcode": barcode,
                    "incoming_product_id": str(product.id),
                    "existing_product_id": str(existing_product_id),
                    "chrt_id": str(variant.chrt_id),
                }
                for barcode, existing_product_id in result.conflicts
            )
            continue
        report.barcodes_existing += result.existing
        report.barcodes_added += result.added

    report.existing_products_found += len(found_ids)
    try:
        await session.flush()
        if apply:
            await session.commit()
        else:
            await session.rollback()
    except IntegrityError:
        await session.rollback()
        raise


def _next_cursor(data: dict[str, Any], cards_count: int) -> tuple[str, int] | None:
    if cards_count < PAGE_LIMIT:
        return None
    cursor = data.get("cursor")
    if not isinstance(cursor, dict):
        raise ValueError("invalid_cursor")
    updated_at = cursor.get("updatedAt")
    nm_id = cursor.get("nmID")
    if (
        not isinstance(updated_at, str)
        or not updated_at.strip()
        or not isinstance(nm_id, int)
        or isinstance(nm_id, bool)
    ):
        raise ValueError("invalid_cursor")
    return updated_at, nm_id


async def run_backfill(
    *, tenant_id: uuid.UUID, seller_id: uuid.UUID, apply: bool
) -> BackfillReport:
    report = BackfillReport(
        mode="apply" if apply else "dry-run",
        tenant_id=str(tenant_id),
        seller_id=str(seller_id),
    )
    async with SessionLocal() as session:
        seller = await session.get(Seller, seller_id)
        if seller is None or seller.tenant_id != tenant_id:
            raise ValueError("seller_not_found_in_tenant")
        tokens = await get_decrypted_tokens_for_seller(session, tenant_id, seller_id)
        if tokens is None or not tokens[0]:
            raise ValueError("seller_content_token_missing")
        content_token = tokens[0]

    cursor_updated_at: str | None = None
    cursor_nm_id: int | None = None
    seen_cursors: set[tuple[str, int]] = set()
    async with httpx.AsyncClient() as client:
        while True:
            try:
                data = await _fetch_page_with_retry(
                    client,
                    api_token=content_token,
                    cursor_updated_at=cursor_updated_at,
                    cursor_nm_id=cursor_nm_id,
                )
                cards = data.get("cards")
                if not isinstance(cards, list):
                    raise ValueError("invalid_cards")
                async with SessionLocal() as session:
                    await process_cards_page(
                        session,
                        tenant_id=tenant_id,
                        seller_id=seller_id,
                        cards=cards,
                        apply=apply,
                        report=report,
                    )
                report.wb_cards_read += len(cards)
                next_cursor = _next_cursor(data, len(cards))
            except (IntegrityError, ValueError, WildberriesClientError) as exc:
                status = getattr(exc, "status_code", None)
                code = getattr(exc, "code", type(exc).__name__)
                report.errors.append(f"{code}:{status}" if status else str(code))
                break

            cursor_payload = data.get("cursor")
            report.last_successful_cursor = (
                dict(cursor_payload) if isinstance(cursor_payload, dict) else None
            )
            if next_cursor is None:
                break
            if next_cursor in seen_cursors:
                report.errors.append("pagination_stalled")
                break
            seen_cursors.add(next_cursor)
            cursor_updated_at, cursor_nm_id = next_cursor
            await asyncio.sleep(REQUEST_PAUSE_SECONDS)

    report.chrt_ids_not_found = sorted(set(report.chrt_ids_not_found))
    report.chrt_ids_not_found_count = len(report.chrt_ids_not_found)
    report.barcode_conflicts_count = len(report.barcode_conflicts)
    report.errors_count = len(report.errors)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", type=uuid.UUID, required=True)
    parser.add_argument("--seller-id", type=uuid.UUID, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(
        run_backfill(
            tenant_id=args.tenant_id,
            seller_id=args.seller_id,
            apply=args.apply,
        )
    )
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
