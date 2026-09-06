"""WMS-382: оплата подписки через ЮKassa.

Настоящую ЮKassa здесь не зовём: подменяем транспорт, чтобы проверить нашу
арифметику продления и защиту от двойного зачёта одной оплаты.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.subscription_payment import SubscriptionPayment
from app.models.tenant import Tenant
from app.models.user import User
from app.services import subscription_payment_service as svc


class _FakeYooKassa:
    """Минимальная ЮKassa: создаёт платёж и отдаёт заданный статус."""

    def __init__(self, status: str = "pending", paid: bool = False) -> None:
        self.status = status
        self.paid = paid
        self.created: list[dict[str, Any]] = []
        self.idempotence_keys: list[str] = []

    def client_factory(self, *args: Any, **kwargs: Any) -> _FakeYooKassa:
        return self

    async def __aenter__(self) -> _FakeYooKassa:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.created.append(kwargs.get("json") or {})
        self.idempotence_keys.append((kwargs.get("headers") or {}).get("Idempotence-Key", ""))
        return httpx.Response(
            200,
            json={
                "id": "2f0e1a-test-payment",
                "status": "pending",
                "confirmation": {"confirmation_url": "https://yoomoney.test/checkout"},
            },
            request=httpx.Request("POST", url),
        )

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": "2f0e1a-test-payment", "status": self.status, "paid": self.paid},
            request=httpx.Request("GET", url),
        )


@pytest.fixture
def yookassa_keys() -> Any:
    shop, secret = settings.yookassa_shop_id, settings.yookassa_secret_key
    settings.yookassa_shop_id = "test-shop"
    settings.yookassa_secret_key = "test-secret"
    yield
    settings.yookassa_shop_id, settings.yookassa_secret_key = shop, secret


async def _register_admin(client: AsyncClient, slug: str) -> dict[str, str]:
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


async def _tenant_by_admin(email: str) -> Tenant:
    async with SessionLocal() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one()
        tenant = await session.get(Tenant, user.tenant_id)
        assert tenant is not None
        return tenant


async def _set_paid_until(email: str, value: date | None) -> None:
    async with SessionLocal() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one()
        tenant = await session.get(Tenant, user.tenant_id)
        assert tenant is not None
        tenant.subscription_paid_until = value
        await session.commit()


def test_extension_never_burns_paid_days() -> None:
    """Продление добавляет месяц к уже оплаченному сроку, а не обнуляет его."""
    tenant = Tenant(name="Продление", slug="renew")
    today = svc.today_msk()

    tenant.subscription_paid_until = today + timedelta(days=10)
    svc.extend_paid_until(tenant)
    assert tenant.subscription_paid_until == today + timedelta(days=40)

    # Просроченная подписка считается от сегодня, а не от старой даты.
    tenant.subscription_paid_until = today - timedelta(days=100)
    svc.extend_paid_until(tenant)
    assert tenant.subscription_paid_until == today + timedelta(days=30)


@pytest.mark.asyncio
async def test_pay_without_keys_reports_conflict(async_client: AsyncClient) -> None:
    headers = await _register_admin(async_client, "pay-no-keys")
    response = await async_client.post("/subscription/pay", headers=headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "payments_not_configured"


@pytest.mark.asyncio
async def test_payment_creates_link_and_activates_after_success(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, yookassa_keys: Any
) -> None:
    headers = await _register_admin(async_client, "pay-flow")
    email = "admin-pay-flow@example.com"
    await _set_paid_until(email, date.today() - timedelta(days=1))

    fake = _FakeYooKassa()
    monkeypatch.setattr(httpx, "AsyncClient", fake.client_factory)

    started = await async_client.post("/subscription/pay", headers=headers)
    assert started.status_code == 200, started.text
    assert started.json()["confirmation_url"] == "https://yoomoney.test/checkout"
    assert fake.created[0]["amount"]["value"] == "10000.00"
    assert fake.idempotence_keys[0]
    assert fake.created[0]["metadata"]["product"] == "wms"

    # Состав чека выведен опытным путём на боевом магазине: без него ЮKassa
    # отвечает «Receipt is missing», без предмета расчёта — «paymentSubject».
    item = fake.created[0]["receipt"]["items"][0]
    assert fake.created[0]["receipt"]["customer"]["email"] == email
    assert item["payment_subject"] == "service"
    assert item["payment_mode"] == "full_payment"
    assert item["vat_code"] == 1
    assert item["amount"]["value"] == "10000.00"

    # Пока оплата не прошла, подписка не продлевается.
    pending = await async_client.post("/subscription/sync", headers=headers)
    assert pending.status_code == 200
    assert pending.json()["activated"] is False

    fake.status, fake.paid = "succeeded", True
    activated = await async_client.post("/subscription/sync", headers=headers)
    assert activated.status_code == 200
    assert activated.json()["activated"] is True

    tenant = await _tenant_by_admin(email)
    assert tenant.subscription_paid_until == svc.today_msk() + timedelta(days=30)

    state = await async_client.get("/subscription", headers=headers)
    assert state.json()["blocked"] is False
    assert state.json()["days_left"] == 30


@pytest.mark.asyncio
async def test_one_payment_extends_only_once(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, yookassa_keys: Any
) -> None:
    """Повторный опрос той же оплаты не должен добавлять второй месяц."""
    headers = await _register_admin(async_client, "pay-once")
    email = "admin-pay-once@example.com"

    fake = _FakeYooKassa(status="succeeded", paid=True)
    monkeypatch.setattr(httpx, "AsyncClient", fake.client_factory)

    assert (await async_client.post("/subscription/pay", headers=headers)).status_code == 200
    assert (await async_client.post("/subscription/sync", headers=headers)).json()["activated"]

    tenant = await _tenant_by_admin(email)
    first = tenant.subscription_paid_until

    repeated = await async_client.post("/subscription/sync", headers=headers)
    assert repeated.json()["activated"] is False

    tenant = await _tenant_by_admin(email)
    assert tenant.subscription_paid_until == first


@pytest.mark.asyncio
async def test_blocked_tenant_can_still_pay(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, yookassa_keys: Any
) -> None:
    """Закрытая подписка не должна запирать сами кнопки оплаты."""
    headers = await _register_admin(async_client, "pay-blocked")
    await _set_paid_until("admin-pay-blocked@example.com", date.today() - timedelta(days=3))

    assert (await async_client.get("/sellers", headers=headers)).status_code == 402

    fake = _FakeYooKassa()
    monkeypatch.setattr(httpx, "AsyncClient", fake.client_factory)
    assert (await async_client.post("/subscription/pay", headers=headers)).status_code == 200
    assert (await async_client.post("/subscription/sync", headers=headers)).status_code == 200


@pytest.mark.asyncio
async def test_payment_is_scoped_to_its_tenant(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, yookassa_keys: Any
) -> None:
    """Оплата одной организации не продлевает подписку другой."""
    first = await _register_admin(async_client, "pay-scope-one")
    await _register_admin(async_client, "pay-scope-two")
    await _set_paid_until("admin-pay-scope-two@example.com", date.today() + timedelta(days=5))

    fake = _FakeYooKassa(status="succeeded", paid=True)
    monkeypatch.setattr(httpx, "AsyncClient", fake.client_factory)
    assert (await async_client.post("/subscription/pay", headers=first)).status_code == 200
    assert (await async_client.post("/subscription/sync", headers=first)).json()["activated"]

    other = await _tenant_by_admin("admin-pay-scope-two@example.com")
    assert other.subscription_paid_until == date.today() + timedelta(days=5)

    async with SessionLocal() as session:
        rows = (await session.execute(select(SubscriptionPayment))).scalars().all()
        assert len(rows) == 1
        assert rows[0].status == "succeeded"


@pytest.mark.asyncio
async def test_seller_cannot_start_payment(
    async_client: AsyncClient, yookassa_keys: Any
) -> None:
    headers = await _register_admin(async_client, "pay-rights")
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Селлер"})
    account = await async_client.post(
        "/auth/seller-accounts",
        headers=headers,
        json={"seller_id": seller.json()["id"], "email": "seller-pay-rights@example.com"},
    )
    assert account.status_code == 201, account.text

    from tests.auth_helpers import set_password_via_link

    assert (
        await set_password_via_link(
            async_client, "seller-pay-rights@example.com", "parolselera123"
        )
    ).status_code == 200
    login = await async_client.post(
        "/auth/login",
        json={"email": "seller-pay-rights@example.com", "password": "parolselera123"},
    )
    seller_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    denied = await async_client.post("/subscription/pay", headers=seller_headers)
    assert denied.status_code == 403
