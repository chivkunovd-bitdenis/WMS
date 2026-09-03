"""Persist Wildberries API tokens per seller (encrypted at rest)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.seller import Seller
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.services.integration_fernet import decrypt_secret, encrypt_secret


class WildberriesCredentialsError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _SkipSentinel:
    __slots__ = ()


SKIP: _SkipSentinel = _SkipSentinel()

TokenPatchValue = str | None | _SkipSentinel


async def _seller_in_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> Seller | None:
    s = await session.get(Seller, seller_id)
    if s is None or s.tenant_id != tenant_id:
        return None
    return s


async def get_public_token_status(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> tuple[bool, bool, bool, datetime | None, bool | None] | None:
    """(has_content, has_supplies, has_marketplace, updated_at, marketplace_scope_ok)
    or None if seller not in tenant.

    marketplace_scope_ok is the result of the last live check of the Marketplace API
    scope for the stored key: True/False once checked at least once via the seller
    self-service flow, or None if never checked (e.g. an admin set the tokens
    directly without going through validation).
    """
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        return None
    row = await session.get(SellerWildberriesCredentials, seller_id)
    if row is None:
        return False, False, False, None, None
    return (
        bool(row.content_token_encrypted),
        bool(row.supplies_token_encrypted),
        bool(row.marketplace_token_encrypted),
        row.updated_at,
        row.marketplace_scope_ok,
    )


async def patch_seller_tokens(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    content_api_token: TokenPatchValue,
    supplies_api_token: TokenPatchValue,
    marketplace_api_token: TokenPatchValue = SKIP,
    marketplace_scope_ok: bool | _SkipSentinel = SKIP,
) -> SellerWildberriesCredentials | None:
    """
    content_api_token / supplies_api_token / marketplace_api_token:
    - ``SKIP``: do not change field
    - ``None``: clear stored token
    - non-empty ``str``: replace with encrypted value

    marketplace_scope_ok:
    - ``SKIP``: do not change the last known Marketplace-scope check result
    - ``True`` / ``False``: record the outcome of a live scope check just performed
      for the current key (also stamps ``marketplace_scope_checked_at``)

    One WB key is meant to cover everything for a seller: content, products, FBS
    orders, supplies and stock. The seller is only ever asked for a single key. When
    ``marketplace_api_token`` is left as ``SKIP`` and a content token is being set
    while the marketplace field is still empty (first-ever save), that same content
    key is copied into the marketplace field too, so it starts working everywhere
    right away. An already-populated marketplace field is never silently overwritten
    this way — a prior bug destroyed a working marketplace key exactly by doing that
    unconditionally. Callers that perform a live scope check should instead record
    the real outcome via ``marketplace_scope_ok`` so the UI can honestly tell the
    seller when their key currently lacks Marketplace rights.
    """
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        return None

    if (
        content_api_token is SKIP
        and supplies_api_token is SKIP
        and marketplace_api_token is SKIP
        and marketplace_scope_ok is SKIP
    ):
        raise WildberriesCredentialsError("empty_patch")

    row = await session.get(SellerWildberriesCredentials, seller_id)
    if row is None:
        row = SellerWildberriesCredentials(seller_id=seller_id)
        session.add(row)

    now = datetime.now(tz=UTC)

    if content_api_token is not SKIP:
        if content_api_token is None:
            row.content_token_encrypted = None
        else:
            assert isinstance(content_api_token, str)
            stripped = content_api_token.strip()
            if not stripped:
                raise WildberriesCredentialsError("token_empty")
            row.content_token_encrypted = encrypt_secret(stripped)

    if supplies_api_token is not SKIP:
        if supplies_api_token is None:
            row.supplies_token_encrypted = None
        else:
            assert isinstance(supplies_api_token, str)
            stripped = supplies_api_token.strip()
            if not stripped:
                raise WildberriesCredentialsError("token_empty")
            row.supplies_token_encrypted = encrypt_secret(stripped)

    if marketplace_api_token is not SKIP:
        if marketplace_api_token is None:
            row.marketplace_token_encrypted = None
            if marketplace_scope_ok is SKIP:
                # Ключ стёрт вручную — прошлый результат проверки права
                # "Маркетплейс" больше не имеет смысла, сбрасываем в неизвестное.
                row.marketplace_scope_ok = None
                row.marketplace_scope_checked_at = None
        else:
            assert isinstance(marketplace_api_token, str)
            stripped = marketplace_api_token.strip()
            if not stripped:
                raise WildberriesCredentialsError("token_empty")
            row.marketplace_token_encrypted = encrypt_secret(stripped)
    elif (
        content_api_token is not SKIP
        and row.marketplace_token_encrypted is None
        and marketplace_scope_ok is not False
    ):
        # Один ключ на всё: при первом сохранении (поле маркетплейс-токена ещё
        # пустое) новый контентный ключ подставляется и туда, чтобы заказы FBS
        # заработали без отдельного маркетплейс-ключа. Если поле уже заполнено —
        # не трогаем: не заменяем рабочий ключ ключом, чья проверка права
        # "Маркетплейс" могла провалиться (см. marketplace_scope_ok).
        #
        # Исключение: если вызывающий код в этом же вызове передал
        # marketplace_scope_ok=False, значит он только что живой проверкой
        # убедился, что у этого конкретного ключа права "Маркетплейс" нет —
        # копировать его в поле маркетплейс-токена нельзя, это выдало бы
        # заведомо нерабочий ключ за годный.
        row.marketplace_token_encrypted = row.content_token_encrypted

    if marketplace_scope_ok is not SKIP:
        row.marketplace_scope_ok = cast(bool, marketplace_scope_ok)
        row.marketplace_scope_checked_at = now

    row.updated_at = now
    await session.commit()
    await session.refresh(row)
    return row


async def get_decrypted_tokens_for_seller(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> tuple[str | None, str | None] | None:
    """
    For sync jobs: returns (content_token, supplies_token) or None if seller missing.

    The seller cabinet key is canonical; supplies falls back to that same key when
    an old dedicated supplies token is not present.
    """
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        return None
    row = await session.get(SellerWildberriesCredentials, seller_id)
    if row is None:
        return None, None
    content: str | None = None
    supplies: str | None = None
    if row.content_token_encrypted:
        content = decrypt_secret(row.content_token_encrypted)
    if row.supplies_token_encrypted:
        supplies = decrypt_secret(row.supplies_token_encrypted)
    return content, supplies


async def get_decrypted_marketplace_token(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> str | None:
    """Returns the unified WB token used for Marketplace/FBS API calls."""
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        return None
    row = await session.get(SellerWildberriesCredentials, seller_id)
    if row is None:
        return None
    if row.marketplace_token_encrypted:
        return decrypt_secret(row.marketplace_token_encrypted)
    # Один ключ на всё: при сохранении контентный ключ подставляется и в поле
    # маркетплейса, но у записей, заведённых до этого правила, оно осталось
    # пустым. Автоопрос таких селлеров при этом берёт в работу (ему довольно
    # любого из двух ключей) — и каждый проход завершался
    # «missing_marketplace_token», то есть заказы FBS молча не приезжали.
    if row.content_token_encrypted and row.marketplace_scope_ok is not False:
        return decrypt_secret(row.content_token_encrypted)
    return None
