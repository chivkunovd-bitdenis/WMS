"""WMS-381: срок подписки, остаток дней и блокировка системы."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.tenant import Tenant
from app.models.user import User
from app.services.subscription_service import subscription_state


async def _register(client: AsyncClient, slug: str) -> dict[str, str]:
    response = await client.post(
        "/auth/register",
        json={
            "organization_name": f"Org {slug}",
            "slug": slug,
            "admin_email": f"admin-{slug}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _set_paid_until(email: str, value: date | None) -> None:
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        tenant = await session.get(Tenant, user.tenant_id)
        assert tenant is not None
        tenant.subscription_paid_until = value
        await session.commit()


def test_state_without_date_never_blocks() -> None:
    """Пока дата не проставлена, подписка не применяется вообще."""
    tenant = Tenant(name="Без подписки", slug="no-sub")
    state = subscription_state(tenant, today=date(2026, 9, 6))
    assert state.enabled is False
    assert state.blocked is False
    assert state.days_left is None


def test_state_counts_days_and_blocks_after_last_day() -> None:
    tenant = Tenant(name="С подпиской", slug="with-sub")
    tenant.subscription_paid_until = date(2026, 9, 30)

    remaining = subscription_state(tenant, today=date(2026, 9, 6))
    assert remaining.days_left == 24
    assert remaining.blocked is False

    # Последний оплаченный день ещё рабочий.
    last_day = subscription_state(tenant, today=date(2026, 9, 30))
    assert last_day.days_left == 0
    assert last_day.blocked is False

    expired = subscription_state(tenant, today=date(2026, 10, 1))
    assert expired.days_left == 0
    assert expired.blocked is True


@pytest.mark.asyncio
async def test_subscription_endpoint_reports_days_left(async_client: AsyncClient) -> None:
    headers = await _register(async_client, "sub-days")
    email = "admin-sub-days@example.com"

    before = await async_client.get("/subscription", headers=headers)
    assert before.status_code == 200, before.text
    assert before.json()["enabled"] is False
    assert before.json()["price_rub"] == 10000

    await _set_paid_until(email, date.today() + timedelta(days=12))
    after = await async_client.get("/subscription", headers=headers)
    assert after.status_code == 200, after.text
    body = after.json()
    assert body["enabled"] is True
    assert body["days_left"] == 12
    assert body["blocked"] is False


@pytest.mark.asyncio
async def test_expired_subscription_blocks_work_but_not_login(
    async_client: AsyncClient,
) -> None:
    headers = await _register(async_client, "sub-blocked")
    email = "admin-sub-blocked@example.com"

    working = await async_client.get("/sellers", headers=headers)
    assert working.status_code == 200, working.text

    await _set_paid_until(email, date.today() - timedelta(days=1))

    blocked = await async_client.get("/sellers", headers=headers)
    assert blocked.status_code == 402
    assert blocked.json()["detail"] == "subscription_expired"

    # Вход, профиль и экран подписки обязаны работать: иначе человек не увидит,
    # почему его закрыли, и не сможет оплатить.
    login = await async_client.post(
        "/auth/login", json={"email": email, "password": "password123"}
    )
    assert login.status_code == 200, login.text
    assert (await async_client.get("/auth/me", headers=headers)).status_code == 200
    state = await async_client.get("/subscription", headers=headers)
    assert state.status_code == 200
    assert state.json()["blocked"] is True


@pytest.mark.asyncio
async def test_subscription_of_one_tenant_does_not_touch_another(
    async_client: AsyncClient,
) -> None:
    first = await _register(async_client, "sub-tenant-one")
    second = await _register(async_client, "sub-tenant-two")
    await _set_paid_until("admin-sub-tenant-one@example.com", date.today() - timedelta(days=5))

    assert (await async_client.get("/sellers", headers=first)).status_code == 402
    assert (await async_client.get("/sellers", headers=second)).status_code == 200
