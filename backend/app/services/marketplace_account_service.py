from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketplace_account import MarketplaceAccount
from app.models.seller import Seller
from app.services.integration_fernet import decrypt_secret, encrypt_secret

PUBLIC_STATUS_KEYS = {
    "marketplace",
    "connected",
    "validation_status",
    "last_validated_at",
    "last_validation_error",
    "credentials_updated_at",
    "last_synced_at",
    "last_sync_error",
}


class MarketplaceAccountError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class SellerNotFound(MarketplaceAccountError):
    def __init__(self) -> None:
        super().__init__("seller_not_found")


@dataclass(frozen=True)
class SavedAccount:
    account_id: uuid.UUID
    credentials_updated_at: datetime | None
    status: dict[str, object]


def public_status_for(row: MarketplaceAccount | None) -> dict[str, object]:
    if row is None or not row.is_active:
        return {
            "marketplace": "ozon",
            "connected": False,
            "validation_status": "not_configured",
            "last_validated_at": None,
            "last_validation_error": None,
            "credentials_updated_at": None,
            "last_synced_at": None,
            "last_sync_error": None,
        }
    return {
        "marketplace": "ozon",
        "connected": True,
        "validation_status": row.validation_status,
        "last_validated_at": row.last_validated_at,
        "last_validation_error": row.last_validation_error_code,
        "credentials_updated_at": row.credentials_updated_at,
        "last_synced_at": row.last_synced_at,
        "last_sync_error": row.last_sync_error_code,
    }


class MarketplaceAccountService:
    """Data lifecycle for the one hidden Ozon account slot used by S-32."""

    SellerNotFound = SellerNotFound

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _seller_in_tenant(
        self, tenant_id: uuid.UUID, seller_id: uuid.UUID, *, lock: bool = False
    ) -> Seller:
        statement = select(Seller).where(Seller.id == seller_id)
        if lock:
            # Serialise primary-slot changes on the existing seller row. This is
            # effective on Postgres and harmless for the SQLite test schema.
            statement = statement.with_for_update()
        seller = (await self.session.execute(statement)).scalar_one_or_none()
        if seller is None or seller.tenant_id != tenant_id:
            raise SellerNotFound()
        return seller

    async def _row(
        self, tenant_id: uuid.UUID, seller_id: uuid.UUID, *, lock: bool = False
    ) -> MarketplaceAccount | None:
        statement = select(MarketplaceAccount).where(
            MarketplaceAccount.tenant_id == tenant_id,
            MarketplaceAccount.seller_id == seller_id,
            MarketplaceAccount.marketplace == "ozon",
            MarketplaceAccount.account_slot == "primary",
        )
        if lock:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def public_status(self, tenant_id: uuid.UUID, seller_id: uuid.UUID) -> dict[str, object]:
        await self._seller_in_tenant(tenant_id, seller_id)
        return public_status_for(await self._row(tenant_id, seller_id))

    async def save_validated_candidate(
        self,
        tenant_id: uuid.UUID,
        seller_id: uuid.UUID,
        actor_id: uuid.UUID,
        client_id: str,
        api_key: str,
    ) -> SavedAccount:
        # The seller row is the durable lock target.  It exists before the primary
        # account row and therefore serializes the first-create race on databases
        # that support SELECT ... FOR UPDATE (notably PostgreSQL).  The uniqueness
        # constraint remains the last line of defence if an older database ignores
        # that lock or two writers arrive through another code path.
        for attempt in range(2):
            try:
                await self._seller_in_tenant(tenant_id, seller_id, lock=True)
                row = await self._row(tenant_id, seller_id, lock=True)
                now = datetime.now(tz=UTC)
                if row is not None and row.secret_encrypted and row.external_account_id is not None:
                    current_key = decrypt_secret(row.secret_encrypted)
                    same_pair = row.external_account_id == client_id and hmac.compare_digest(
                        current_key, api_key
                    )
                else:
                    same_pair = False
                if row is None:
                    row = MarketplaceAccount(
                        tenant_id=tenant_id,
                        seller_id=seller_id,
                        marketplace="ozon",
                        account_slot="primary",
                        created_by_user_id=actor_id,
                    )
                    self.session.add(row)
                if not same_pair:
                    row.external_account_id = client_id
                    row.secret_encrypted = encrypt_secret(api_key)
                    row.credentials_updated_at = now
                    row.created_by_user_id = row.created_by_user_id or actor_id
                row.is_active = True
                row.validation_status = "valid"
                row.last_validated_at = now
                row.last_validation_error_code = None
                row.updated_by_user_id = actor_id
                row.disconnected_at = None
                row.disconnected_by_user_id = None
                await self.session.commit()
                await self.session.refresh(row)
                return SavedAccount(row.id, row.credentials_updated_at, public_status_for(row))
            except IntegrityError:
                await self.session.rollback()
                if attempt:
                    raise
        raise RuntimeError("unreachable")

    async def update_stored_validation(
        self,
        tenant_id: uuid.UUID,
        seller_id: uuid.UUID,
        actor_id: uuid.UUID,
        *,
        validation_status: str,
        error_code: str | None,
    ) -> dict[str, object]:
        await self._seller_in_tenant(tenant_id, seller_id)
        row = await self._row(tenant_id, seller_id, lock=True)
        if row is None or not row.is_active or not row.secret_encrypted:
            raise MarketplaceAccountError("ozon_not_connected")
        row.validation_status = validation_status
        row.last_validation_error_code = error_code
        row.last_validated_at = datetime.now(tz=UTC)
        row.updated_by_user_id = actor_id
        await self.session.commit()
        await self.session.refresh(row)
        return public_status_for(row)

    async def stored_credentials(
        self, tenant_id: uuid.UUID, seller_id: uuid.UUID
    ) -> tuple[str, str]:
        await self._seller_in_tenant(tenant_id, seller_id)
        row = await self._row(tenant_id, seller_id)
        if (
            row is None
            or not row.is_active
            or not row.secret_encrypted
            or not row.external_account_id
        ):
            raise MarketplaceAccountError("ozon_not_connected")
        return row.external_account_id, decrypt_secret(row.secret_encrypted)

    async def disconnect(
        self, tenant_id: uuid.UUID, seller_id: uuid.UUID, actor_id: uuid.UUID
    ) -> None:
        await self._seller_in_tenant(tenant_id, seller_id)
        row = await self._row(tenant_id, seller_id, lock=True)
        if row is None or not row.is_active:
            return
        now = datetime.now(tz=UTC)
        row.secret_encrypted = None
        row.external_account_id = None
        row.is_active = False
        row.validation_status = "not_configured"
        row.last_validated_at = None
        row.last_validation_error_code = None
        row.last_synced_at = None
        row.last_sync_error_code = None
        row.credentials_updated_at = None
        row.updated_by_user_id = actor_id
        row.disconnected_at = now
        row.disconnected_by_user_id = actor_id
        await self.session.commit()
