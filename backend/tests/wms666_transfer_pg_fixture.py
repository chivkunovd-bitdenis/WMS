"""Opt-in audit adapter: old transfer fixtures pass random, unpersisted actor UUIDs.

Create that exact synthetic actor before invoking the real service. No production
code, service result, marketplace outcome, or test assertion is replaced.
"""

import pytest


@pytest.fixture(autouse=True)
def persist_fixture_actor(monkeypatch, request):
    if request.node.module.__name__ not in {
        "test_fbs_supply_transfer",
        "test_wms581_supply_transfer",
    }:
        return
    from app.models.user import User
    from app.services import fbs_supply_transfer_service

    original = fbs_supply_transfer_service.transfer_orders

    async def with_existing_actor(session, tenant_id, source_id, **kwargs):
        actor_id = kwargs["actor_user_id"]
        if await session.get(User, actor_id) is None:
            session.add(
                User(
                    id=actor_id,
                    tenant_id=tenant_id,
                    password_hash="synthetic-not-a-login",
                    role="fulfillment_admin",
                )
            )
            await session.flush()
        return await original(session, tenant_id, source_id, **kwargs)

    monkeypatch.setattr(fbs_supply_transfer_service, "transfer_orders", with_existing_actor)
