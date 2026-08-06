from __future__ import annotations

import uuid

import pytest

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.services.wildberries_credentials_service import get_decrypted_marketplace_token


@pytest.mark.asyncio
async def test_test_emulator_uses_synthetic_token_without_stored_credentials(
    async_client: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del async_client
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    async with SessionLocal() as session:
        session.add(Tenant(id=tenant_id, name="Emulator token tenant", slug=f"emu-{tenant_id.hex}"))
        session.add(Seller(id=seller_id, tenant_id=tenant_id, name="Tokenless seller"))
        await session.commit()

        monkeypatch.setattr(settings, "fbs_test_emulator_enabled", True)
        token = await get_decrypted_marketplace_token(session, tenant_id, seller_id)

    assert token == f"wms-test-{seller_id}"


@pytest.mark.asyncio
async def test_test_emulator_never_issues_token_for_foreign_seller(
    async_client: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del async_client
    tenant_id = uuid.uuid4()
    other_tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    async with SessionLocal() as session:
        session.add(Tenant(id=tenant_id, name="Tenant A", slug=f"a-{tenant_id.hex}"))
        session.add(Tenant(id=other_tenant_id, name="Tenant B", slug=f"b-{other_tenant_id.hex}"))
        session.add(Seller(id=seller_id, tenant_id=other_tenant_id, name="Foreign seller"))
        await session.commit()

        monkeypatch.setattr(settings, "fbs_test_emulator_enabled", True)
        token = await get_decrypted_marketplace_token(session, tenant_id, seller_id)

    assert token is None
