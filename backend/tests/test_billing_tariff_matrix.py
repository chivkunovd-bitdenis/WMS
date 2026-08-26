from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.billing import BillingTariffMatrixConfig, BillingTariffServiceState
from app.models.tenant import Tenant
from app.services.billing_tariff_matrix_service import (
    BillingTariffMatrixError,
    ensure_disabled_tariff_matrix,
    get_tariff_matrix,
)


@pytest.mark.asyncio
async def test_new_tenant_gets_persisted_disabled_non_storage_matrix(async_client) -> None:
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Matrix tenant",
            "slug": f"matrix-{uuid.uuid4().hex}",
            "admin_email": f"matrix-{uuid.uuid4().hex}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    me = await async_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"}
    )
    assert me.status_code == 200, me.text
    tenant_id = uuid.UUID(me.json()["tenant_id"])

    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        config = await session.scalar(
            select(BillingTariffMatrixConfig).where(
                BillingTariffMatrixConfig.tenant_id == tenant_id
            )
        )
        assert config is not None
        states = (await session.scalars(
            select(BillingTariffServiceState).where(
                BillingTariffServiceState.tenant_id == tenant_id
            )
        )).all()
    assert {state.service_code for state in states} == {
        "inbound", "marketplace_outbound", "packing", "return"
    }
    assert all(not state.enabled for state in states)


@pytest.mark.asyncio
async def test_matrix_bootstrap_is_idempotent_and_missing_matrix_is_not_silent(
    async_client,
) -> None:
    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        tenant = Tenant(name="Matrix bootstrap", slug=f"matrix-bootstrap-{uuid.uuid4().hex}")
        session.add(tenant)
        await session.flush()
        first = await ensure_disabled_tariff_matrix(session, tenant=tenant)
        second = await ensure_disabled_tariff_matrix(session, tenant=tenant)
        assert first.id == second.id
        await session.commit()

    async with SessionLocal() as session:
        loaded = await get_tariff_matrix(session, tenant_id=tenant.id)
        assert loaded.id == first.id
        await session.execute(
            BillingTariffMatrixConfig.__table__.delete().where(
                BillingTariffMatrixConfig.id == first.id
            )
        )
        await session.commit()
        with pytest.raises(BillingTariffMatrixError, match="billing_tariff_matrix_config_missing"):
            await get_tariff_matrix(session, tenant_id=tenant.id)
