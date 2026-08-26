from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.billing import BillingTariffMatrixConfig
from app.models.tenant import Tenant
from app.services.billing_tariff_matrix_service import ensure_disabled_tariff_matrix


@pytest.mark.asyncio
async def test_bootstrap_matrix_creation_is_idempotent_for_existing_tenant(async_client) -> None:
    async with SessionLocal() as session:
        tenant = Tenant(name="Bootstrap matrix", slug=f"bootstrap-matrix-{uuid.uuid4().hex}")
        session.add(tenant)
        await session.flush()
        first = await ensure_disabled_tariff_matrix(session, tenant=tenant)
        await session.commit()
        tenant_id = tenant.id

    async with SessionLocal() as session:
        existing = await session.scalar(select(Tenant).where(Tenant.id == tenant_id))
        assert existing is not None
        second = await ensure_disabled_tariff_matrix(session, tenant=existing)
        await session.commit()
        configs = (await session.scalars(
            select(BillingTariffMatrixConfig).where(
                BillingTariffMatrixConfig.tenant_id == tenant_id
            )
        )).all()

    assert second.id == first.id
    assert len(configs) == 1
