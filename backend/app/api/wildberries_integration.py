from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_fulfillment_admin
from app.core.roles import FULFILLMENT_SELLER
from app.core.settings import settings
from app.db.session import get_db
from app.models.user import User
from app.services.wildberries_client import WildberriesClientError, fetch_cards_list
from app.services.wildberries_credentials_service import (
    SKIP,
    TokenPatchValue,
    WildberriesCredentialsError,
    get_decrypted_tokens_for_seller,
    get_public_token_status,
    patch_seller_tokens,
)
from app.services.wildberries_import_cards_service import (
    list_imported_cards_for_seller,
    upsert_imported_cards,
)
from app.services.wildberries_import_supplies_service import list_imported_supplies_for_seller
from app.services.wildberries_product_import_service import upsert_products_from_wb_cards
from app.services.wildberries_product_link_service import (
    WildberriesLinkError,
    link_product_to_wb_card,
)

router = APIRouter(prefix="/integrations/wildberries", tags=["integrations"])


class WildberriesStatusOut(BaseModel):
    content_api_base: str
    supplies_api_base: str
    import_only: bool = True


class WildberriesSellerTokensOut(BaseModel):
    seller_id: str
    has_content_token: bool
    has_supplies_token: bool
    updated_at: datetime | None


class WildberriesSelfTokensOut(BaseModel):
    has_content_token: bool
    has_supplies_token: bool
    updated_at: datetime | None


class WildberriesImportedCardOut(BaseModel):
    nm_id: int
    vendor_code: str | None
    title: str | None
    updated_at: datetime


class WildberriesImportedSupplyOut(BaseModel):
    external_key: str
    wb_supply_id: int | None
    wb_preorder_id: int | None
    status_id: int | None
    updated_at: datetime


class LinkProductWbBody(BaseModel):
    product_id: uuid.UUID
    nm_id: int = Field(ge=1)


class LinkProductWbOut(BaseModel):
    product_id: str
    sku_code: str
    wb_nm_id: int
    wb_vendor_code: str | None


class WildberriesSelfTokenSaveBody(BaseModel):
    content_api_token: str = Field(min_length=5, max_length=4096)


class WildberriesSelfTokenSaveOut(BaseModel):
    ok: bool = True
    cards_received: int
    cards_saved: int
    products_created: int = 0
    products_updated: int = 0
    products_skipped: int = 0


class WildberriesSelfSyncOut(BaseModel):
    ok: bool = True
    cards_received: int
    cards_saved: int
    products_created: int
    products_updated: int
    products_skipped: int


def _parse_token_merge_patch(raw: object) -> tuple[TokenPatchValue, TokenPatchValue]:
    if not isinstance(raw, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="expected_object",
        )
    allowed = {"content_api_token", "supplies_api_token"}
    if set(raw) - allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="unknown_fields",
        )
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="empty_patch",
        )
    content: TokenPatchValue = SKIP
    supplies: TokenPatchValue = SKIP
    if "content_api_token" in raw:
        val = raw["content_api_token"]
        if val is not None and not isinstance(val, str):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid_type:content_api_token",
            )
        content = val
    if "supplies_api_token" in raw:
        val = raw["supplies_api_token"]
        if val is not None and not isinstance(val, str):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid_type:supplies_api_token",
            )
        supplies = val
    if content is SKIP and supplies is SKIP:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="empty_patch",
        )
    return content, supplies


@router.get("/status", response_model=WildberriesStatusOut)
async def wildberries_status(
    _: Annotated[User, Depends(require_fulfillment_admin)],
) -> WildberriesStatusOut:
    """Публичная конфигурация (без токенов): базы URL для импорта WB."""
    return WildberriesStatusOut(
        content_api_base=settings.wildberries_content_api_base,
        supplies_api_base=settings.wildberries_supplies_api_base,
    )


@router.get(
    "/sellers/{seller_id}/imported-cards",
    response_model=list[WildberriesImportedCardOut],
)
async def list_seller_wildberries_imported_cards(
    seller_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[WildberriesImportedCardOut]:
    """Импортированные карточки WB (последний снимок синка)."""
    rows = await list_imported_cards_for_seller(session, user.tenant_id, seller_id)
    if rows is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="seller_not_found")
    return [
        WildberriesImportedCardOut(
            nm_id=int(r.nm_id),
            vendor_code=r.vendor_code,
            title=r.title,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.get(
    "/sellers/{seller_id}/imported-supplies",
    response_model=list[WildberriesImportedSupplyOut],
)
async def list_seller_wildberries_imported_supplies(
    seller_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[WildberriesImportedSupplyOut]:
    """Импортированные поставки FBW (последний снимок синка)."""
    rows = await list_imported_supplies_for_seller(session, user.tenant_id, seller_id)
    if rows is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="seller_not_found")
    return [
        WildberriesImportedSupplyOut(
            external_key=r.external_key,
            wb_supply_id=int(r.wb_supply_id) if r.wb_supply_id is not None else None,
            wb_preorder_id=int(r.wb_preorder_id) if r.wb_preorder_id is not None else None,
            status_id=r.status_id,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.post(
    "/sellers/{seller_id}/link-product",
    response_model=LinkProductWbOut,
)
async def link_product_to_wildberries(
    seller_id: uuid.UUID,
    body: LinkProductWbBody,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> LinkProductWbOut:
    """Привязать SKU к импортированной карточке WB (nm_id) для селлера."""
    try:
        p = await link_product_to_wb_card(
            session,
            user.tenant_id,
            seller_id,
            body.product_id,
            body.nm_id,
        )
    except WildberriesLinkError as exc:
        if exc.code == "product_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="product_not_found",
            ) from exc
        if exc.code == "wb_card_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="wb_card_not_found",
            ) from exc
        if exc.code == "wb_nm_already_linked":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="wb_nm_already_linked",
            ) from exc
        if exc.code in ("product_must_have_seller", "product_seller_mismatch"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=exc.code,
            ) from exc
        raise
    assert p.wb_nm_id is not None
    return LinkProductWbOut(
        product_id=str(p.id),
        sku_code=p.sku_code,
        wb_nm_id=int(p.wb_nm_id),
        wb_vendor_code=p.wb_vendor_code,
    )


@router.get("/sellers/{seller_id}/tokens", response_model=WildberriesSellerTokensOut)
async def get_seller_wildberries_tokens(
    seller_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WildberriesSellerTokensOut:
    """Маска наличия токенов (значения не отдаются)."""
    st = await get_public_token_status(session, user.tenant_id, seller_id)
    if st is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="seller_not_found")
    has_c, has_s, upd = st
    return WildberriesSellerTokensOut(
        seller_id=str(seller_id),
        has_content_token=has_c,
        has_supplies_token=has_s,
        updated_at=upd,
    )


@router.get("/self/tokens", response_model=WildberriesSelfTokensOut)
async def get_self_wildberries_tokens(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WildberriesSelfTokensOut:
    if user.role != FULFILLMENT_SELLER or user.seller_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    st = await get_public_token_status(session, user.tenant_id, user.seller_id)
    if st is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="seller_not_found")
    has_c, has_s, upd = st
    return WildberriesSelfTokensOut(
        has_content_token=has_c,
        has_supplies_token=has_s,
        updated_at=upd,
    )


@router.patch("/sellers/{seller_id}/tokens", response_model=WildberriesSellerTokensOut)
async def patch_seller_wildberries_tokens(
    seller_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> WildberriesSellerTokensOut:
    """Частичное обновление: только переданные ключи JSON (null = удалить токен)."""
    try:
        raw = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid_json",
        ) from exc
    content, supplies = _parse_token_merge_patch(raw)
    try:
        row = await patch_seller_tokens(
            session,
            user.tenant_id,
            seller_id,
            content_api_token=content,
            supplies_api_token=supplies,
        )
    except WildberriesCredentialsError as exc:
        if exc.code in ("empty_patch", "token_empty", "invalid_token_type"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=exc.code,
            ) from exc
        raise
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="seller_not_found")
    st = await get_public_token_status(session, user.tenant_id, seller_id)
    assert st is not None
    has_c, has_s, upd = st
    if (
        supplies is not SKIP
        and isinstance(supplies, str)
        and supplies.strip()
        and has_s
    ):
        from app.services.wb_mp_warehouse_service import run_wb_mp_warehouses_sync_task

        background_tasks.add_task(run_wb_mp_warehouses_sync_task, user.tenant_id, seller_id)
    return WildberriesSellerTokensOut(
        seller_id=str(seller_id),
        has_content_token=has_c,
        has_supplies_token=has_s,
        updated_at=upd,
    )


@router.post("/self/content-token", response_model=WildberriesSelfTokenSaveOut)
async def save_and_validate_self_content_token(
    body: WildberriesSelfTokenSaveBody,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WildberriesSelfTokenSaveOut:
    """Seller saves WB content API key; validate by calling cards list."""
    if user.role != FULFILLMENT_SELLER or user.seller_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    token = body.content_api_token.strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="token_empty",
        )
    total_cards: list[object] = []
    updated_at: str | None = None
    nm_id: int | None = None
    total_hint: int | None = None
    try:
        async with httpx.AsyncClient() as client:
            seen: set[tuple[str | None, int | None]] = set()
            for _ in range(250):
                seen_key = (updated_at, nm_id)
                if seen_key in seen:
                    break
                seen.add(seen_key)
                data = await fetch_cards_list(
                    client,
                    api_token=token,
                    limit=100,
                    cursor_updated_at=updated_at,
                    cursor_nm_id=nm_id,
                )
                cards = data.get("cards") if isinstance(data, dict) else None
                batch = cards if isinstance(cards, list) else []
                if not batch:
                    break
                total_cards.extend(batch)
                cur = data.get("cursor") if isinstance(data, dict) else None
                if isinstance(cur, dict):
                    ua = cur.get("updatedAt")
                    if isinstance(ua, str) and ua.strip():
                        updated_at = ua
                    cid = cur.get("nmID")
                    if isinstance(cid, int):
                        nm_id = cid
                    th = cur.get("total")
                    if isinstance(th, int):
                        total_hint = th
                if total_hint is not None and len(total_cards) >= total_hint:
                    break
    except WildberriesClientError as exc:
        if exc.code == "upstream_error" and exc.status_code in (401, 403):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid_wb_token",
            ) from None
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=exc.code,
        ) from None
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="transport_error",
        ) from None

    n = len(total_cards)

    try:
        await patch_seller_tokens(
            session,
            user.tenant_id,
            user.seller_id,
            content_api_token=token,
            supplies_api_token=SKIP,
        )
        saved = await upsert_imported_cards(session, user.tenant_id, user.seller_id, total_cards)
        prod_stats = await upsert_products_from_wb_cards(
            session, user.tenant_id, user.seller_id, total_cards
        )
    except WildberriesCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.code,
        ) from None
    return WildberriesSelfTokenSaveOut(
        cards_received=n,
        cards_saved=saved,
        products_created=prod_stats["products_created"],
        products_updated=prod_stats["products_updated"],
        products_skipped=prod_stats["products_skipped"],
    )


@router.post("/self/sync-products", response_model=WildberriesSelfSyncOut)
async def sync_products_now(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WildberriesSelfSyncOut:
    """Seller-click sync: fetch all WB cards, persist snapshots, and upsert Product rows."""
    if user.role != FULFILLMENT_SELLER or user.seller_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    pair = await get_decrypted_tokens_for_seller(session, user.tenant_id, user.seller_id)
    if pair is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="seller_not_found")
    content_token, _supplies = pair
    if not content_token:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="missing_content_token")

    total_cards: list[object] = []
    updated_at: str | None = None
    nm_id: int | None = None
    total_hint: int | None = None
    async with httpx.AsyncClient() as client:
        seen: set[tuple[str | None, int | None]] = set()
        for _ in range(250):
            seen_key = (updated_at, nm_id)
            if seen_key in seen:
                break
            seen.add(seen_key)
            try:
                data = await fetch_cards_list(
                    client,
                    api_token=content_token,
                    limit=100,
                    cursor_updated_at=updated_at,
                    cursor_nm_id=nm_id,
                )
            except WildberriesClientError as exc:
                if exc.code == "upstream_error" and exc.status_code in (401, 403):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="invalid_wb_token",
                    ) from None
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=exc.code,
                ) from None
            cards = data.get("cards") if isinstance(data, dict) else None
            batch = cards if isinstance(cards, list) else []
            if not batch:
                break
            total_cards.extend(batch)
            cur = data.get("cursor") if isinstance(data, dict) else None
            if isinstance(cur, dict):
                ua = cur.get("updatedAt")
                if isinstance(ua, str) and ua.strip():
                    updated_at = ua
                cid = cur.get("nmID")
                if isinstance(cid, int):
                    nm_id = cid
                th = cur.get("total")
                if isinstance(th, int):
                    total_hint = th
            if total_hint is not None and len(total_cards) >= total_hint:
                break

    n = len(total_cards)
    saved = await upsert_imported_cards(session, user.tenant_id, user.seller_id, total_cards)
    prod_stats = await upsert_products_from_wb_cards(
        session,
        user.tenant_id,
        user.seller_id,
        total_cards,
    )
    return WildberriesSelfSyncOut(
        cards_received=n,
        cards_saved=saved,
        products_created=prod_stats["products_created"],
        products_updated=prod_stats["products_updated"],
        products_skipped=prod_stats["products_skipped"],
    )
