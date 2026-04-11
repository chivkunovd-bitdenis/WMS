"""Persist Wildberries API tokens per seller (encrypted at rest)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

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
) -> tuple[bool, bool, datetime | None] | None:
    """(has_content, has_supplies, updated_at) or None if seller not in tenant."""
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        return None
    row = await session.get(SellerWildberriesCredentials, seller_id)
    if row is None:
        return False, False, None
    return (
        bool(row.content_token_encrypted),
        bool(row.supplies_token_encrypted),
        row.updated_at,
    )


async def patch_seller_tokens(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    content_api_token: TokenPatchValue,
    supplies_api_token: TokenPatchValue,
) -> SellerWildberriesCredentials | None:
    """
    content_api_token / supplies_api_token:
    - ``SKIP``: do not change field
    - ``None``: clear stored token
    - non-empty ``str``: replace with encrypted value
    """
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        return None

    if content_api_token is SKIP and supplies_api_token is SKIP:
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

    row.updated_at = now
    await session.commit()
    await session.refresh(row)
    return row


async def get_decrypted_tokens_for_seller(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> tuple[str | None, str | None] | None:
    """For sync jobs: returns (content_token, supplies_token) or None if seller missing."""
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
