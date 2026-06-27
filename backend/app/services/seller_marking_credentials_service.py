"""Persist marking integration credentials per seller (encrypted at rest)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.seller import Seller
from app.models.seller_marking_credentials import (
    EDO_ROUTES,
    MARKETPLACES,
    SIGNING_METHODS,
    SellerMarkingCredentials,
)
from app.services.integration_fernet import decrypt_secret, encrypt_secret


class SellerMarkingCredentialsError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _SkipSentinel:
    __slots__ = ()


SKIP: _SkipSentinel = _SkipSentinel()

SecretPatchValue = str | None | _SkipSentinel


@dataclass(frozen=True)
class MarkingCredentialsPublic:
    seller_id: uuid.UUID
    has_cz_token: bool
    has_suz_oms_token: bool
    has_mp_api_key: bool
    marketplace: str | None
    mchd_id: str | None
    mchd_valid_until: date | None
    signing_method: str
    edo_route: str
    auto_introduce: bool
    auto_emit_limit: int | None
    updated_at: datetime | None


@dataclass(frozen=True)
class MarkingCredentialsSecrets:
    cz_token: str | None
    suz_oms_token: str | None
    mp_api_key: str | None


async def _seller_in_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> Seller | None:
    seller = await session.get(Seller, seller_id)
    if seller is None or seller.tenant_id != tenant_id:
        return None
    return seller


def _row_to_public(
    seller_id: uuid.UUID, row: SellerMarkingCredentials | None
) -> MarkingCredentialsPublic:
    if row is None:
        return MarkingCredentialsPublic(
            seller_id=seller_id,
            has_cz_token=False,
            has_suz_oms_token=False,
            has_mp_api_key=False,
            marketplace=None,
            mchd_id=None,
            mchd_valid_until=None,
            signing_method="manual",
            edo_route="edo_light_roaming_diadoc",
            auto_introduce=False,
            auto_emit_limit=None,
            updated_at=None,
        )
    return MarkingCredentialsPublic(
        seller_id=seller_id,
        has_cz_token=bool(row.cz_token_enc),
        has_suz_oms_token=bool(row.suz_oms_token_enc),
        has_mp_api_key=bool(row.mp_api_key_enc),
        marketplace=row.marketplace,
        mchd_id=row.mchd_id,
        mchd_valid_until=row.mchd_valid_until,
        signing_method=row.signing_method,
        edo_route=row.edo_route,
        auto_introduce=row.auto_introduce,
        auto_emit_limit=row.auto_emit_limit,
        updated_at=row.updated_at,
    )


async def get_public_credentials(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> MarkingCredentialsPublic | None:
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        return None
    row = await session.get(SellerMarkingCredentials, seller_id)
    return _row_to_public(seller_id, row)


def _apply_secret_patch(
    row: SellerMarkingCredentials,
    *,
    field_name: str,
    value: SecretPatchValue,
) -> None:
    if value is SKIP:
        return
    attr = f"{field_name}_enc"
    if value is None:
        setattr(row, attr, None)
        return
    assert isinstance(value, str)
    stripped = value.strip()
    if not stripped:
        raise SellerMarkingCredentialsError("token_empty")
    setattr(row, attr, encrypt_secret(stripped))


async def patch_seller_credentials(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    cz_token: SecretPatchValue = SKIP,
    suz_oms_token: SecretPatchValue = SKIP,
    mp_api_key: SecretPatchValue = SKIP,
    marketplace: str | None | _SkipSentinel = SKIP,
    mchd_id: str | None | _SkipSentinel = SKIP,
    mchd_valid_until: date | None | _SkipSentinel = SKIP,
    signing_method: str | _SkipSentinel = SKIP,
    edo_route: str | _SkipSentinel = SKIP,
    auto_introduce: bool | _SkipSentinel = SKIP,
    auto_emit_limit: int | None | _SkipSentinel = SKIP,
) -> SellerMarkingCredentials | None:
    seller = await _seller_in_tenant(session, tenant_id, seller_id)
    if seller is None:
        return None

    patch_fields = (
        cz_token,
        suz_oms_token,
        mp_api_key,
        marketplace,
        mchd_id,
        mchd_valid_until,
        signing_method,
        edo_route,
        auto_introduce,
        auto_emit_limit,
    )
    if all(v is SKIP for v in patch_fields):
        raise SellerMarkingCredentialsError("empty_patch")

    row = await session.get(SellerMarkingCredentials, seller_id)
    if row is None:
        row = SellerMarkingCredentials(seller_id=seller_id, tenant_id=tenant_id)
        session.add(row)

    _apply_secret_patch(row, field_name="cz_token", value=cz_token)
    _apply_secret_patch(row, field_name="suz_oms_token", value=suz_oms_token)
    _apply_secret_patch(row, field_name="mp_api_key", value=mp_api_key)

    if marketplace is not SKIP:
        mp_value: str | None
        if isinstance(marketplace, str):
            if marketplace not in MARKETPLACES:
                raise SellerMarkingCredentialsError("invalid_marketplace")
            mp_value = marketplace
        else:
            mp_value = None
        row.marketplace = mp_value

    if mchd_id is not SKIP:
        if isinstance(mchd_id, str):
            row.mchd_id = mchd_id.strip() or None
        else:
            row.mchd_id = None

    if mchd_valid_until is not SKIP:
        until_value: date | None = mchd_valid_until if isinstance(mchd_valid_until, date) else None
        row.mchd_valid_until = until_value

    if signing_method is not SKIP:
        if not isinstance(signing_method, str) or signing_method not in SIGNING_METHODS:
            raise SellerMarkingCredentialsError("invalid_signing_method")
        row.signing_method = signing_method

    if edo_route is not SKIP:
        if not isinstance(edo_route, str) or edo_route not in EDO_ROUTES:
            raise SellerMarkingCredentialsError("invalid_edo_route")
        row.edo_route = edo_route

    if auto_introduce is not SKIP:
        if not isinstance(auto_introduce, bool):
            raise SellerMarkingCredentialsError("invalid_auto_introduce")
        row.auto_introduce = auto_introduce

    if auto_emit_limit is not SKIP:
        limit_value: int | None
        if isinstance(auto_emit_limit, int):
            if auto_emit_limit < 1:
                raise SellerMarkingCredentialsError("invalid_auto_emit_limit")
            limit_value = auto_emit_limit
        else:
            limit_value = None
        row.auto_emit_limit = limit_value

    row.updated_at = datetime.now(tz=UTC)
    await session.commit()
    await session.refresh(row)
    return row


async def get_decrypted_credentials_for_seller(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> MarkingCredentialsSecrets | None:
    """For integration jobs: returns decrypted secrets or None if seller missing."""
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        return None
    row = await session.get(SellerMarkingCredentials, seller_id)
    if row is None:
        return MarkingCredentialsSecrets(cz_token=None, suz_oms_token=None, mp_api_key=None)
    cz: str | None = None
    suz: str | None = None
    mp: str | None = None
    if row.cz_token_enc:
        cz = decrypt_secret(row.cz_token_enc)
    if row.suz_oms_token_enc:
        suz = decrypt_secret(row.suz_oms_token_enc)
    if row.mp_api_key_enc:
        mp = decrypt_secret(row.mp_api_key_enc)
    return MarkingCredentialsSecrets(cz_token=cz, suz_oms_token=suz, mp_api_key=mp)
