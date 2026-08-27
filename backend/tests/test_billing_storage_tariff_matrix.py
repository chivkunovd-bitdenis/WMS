"""Хранение — полноправная услуга матрицы тарифов.

Держать его на отдельном экране означало единственную услугу с другим местом
настройки: остальные задавались в Настройках, а хранение — на экране «Хранение»
и с привязкой к складу. Владелец попросил задавать все тарифы в одном месте и
по одной модели: общая ставка плюс индивидуальная на селлера.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.billing import BillingTariffVersionV2
from app.models.user import User

FULL_SERVICES = [
    {"service_code": "inbound", "enabled": False},
    {"service_code": "marketplace_outbound", "enabled": False},
    {"service_code": "packing", "enabled": False},
    {"service_code": "return", "enabled": True},
    {"service_code": "storage", "enabled": True},
]


async def _admin(async_client: AsyncClient, suffix: str) -> tuple[dict[str, str], uuid.UUID]:
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Хранение в матрице",
            "slug": suffix,
            "admin_email": f"{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    me = await async_client.get("/auth/me", headers=headers)
    return headers, uuid.UUID(me.json()["tenant_id"])


def _storage_version(**overrides: object) -> dict[str, object]:
    version = {
        "seller_id": None,
        "product_id": None,
        "employee_user_id": None,
        "service_code": "storage",
        "unit": "liter_day",
        "enabled": True,
        "rate": 250,
        "valid_from_at": "2026-08-27T09:00:00Z",
        "valid_to_at": None,
    }
    version.update(overrides)
    return version


@pytest.mark.asyncio
async def test_storage_is_a_matrix_service_with_a_common_rate(async_client: AsyncClient) -> None:
    """TC-NEW-401: хранение приходит в матрице и сохраняется общей ставкой."""
    suffix = f"storage-matrix-{uuid.uuid4().hex[:8]}"
    headers, tenant_id = await _admin(async_client, suffix)

    matrix = await async_client.get("/billing/tariff-matrix", headers=headers)
    assert matrix.status_code == 200, matrix.text
    services = {row["service_code"]: row for row in matrix.json()["services"]}
    assert "storage" in services
    # Единица по природе услуги: подставленная «за штуку» уронила бы сохранение.
    assert services["storage"]["unit"] == "liter_day"

    saved = await async_client.put(
        "/billing/tariff-matrix",
        headers=headers,
        json={
            "revision": matrix.json()["revision"],
            "services": FULL_SERVICES,
            "versions": [_storage_version()],
        },
    )
    assert saved.status_code == 200, saved.text

    async with SessionLocal() as session:
        stored = list(
            (
                await session.scalars(
                    select(BillingTariffVersionV2).where(
                        BillingTariffVersionV2.tenant_id == tenant_id,
                        BillingTariffVersionV2.service_code == "storage",
                    )
                )
            ).all()
        )
    assert [(row.rate, row.unit, row.seller_id) for row in stored] == [(250, "liter_day", None)]


@pytest.mark.asyncio
async def test_storage_takes_an_individual_seller_rate(async_client: AsyncClient) -> None:
    """TC-NEW-402: хранению задаётся своя ставка на конкретного селлера."""
    suffix = f"storage-seller-{uuid.uuid4().hex[:8]}"
    headers, tenant_id = await _admin(async_client, suffix)
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Луна"})
    seller_id = seller.json()["id"]

    matrix = await async_client.get("/billing/tariff-matrix", headers=headers)
    saved = await async_client.put(
        "/billing/tariff-matrix",
        headers=headers,
        json={
            "revision": matrix.json()["revision"],
            "services": FULL_SERVICES,
            "versions": [
                _storage_version(),
                _storage_version(seller_id=seller_id, rate=100),
            ],
        },
    )
    assert saved.status_code == 200, saved.text

    async with SessionLocal() as session:
        stored = {
            (row.seller_id, row.rate)
            for row in (
                await session.scalars(
                    select(BillingTariffVersionV2).where(
                        BillingTariffVersionV2.tenant_id == tenant_id,
                        BillingTariffVersionV2.service_code == "storage",
                    )
                )
            ).all()
        }
    assert stored == {(None, 250), (uuid.UUID(seller_id), 100)}


@pytest.mark.asyncio
async def test_storage_rejects_a_per_item_unit(async_client: AsyncClient) -> None:
    """TC-NEW-403: хранение за штуку не принимается — это враньё в расчёте."""
    suffix = f"storage-unit-{uuid.uuid4().hex[:8]}"
    headers, _tenant_id = await _admin(async_client, suffix)
    matrix = await async_client.get("/billing/tariff-matrix", headers=headers)

    rejected = await async_client.put(
        "/billing/tariff-matrix",
        headers=headers,
        json={
            "revision": matrix.json()["revision"],
            "services": FULL_SERVICES,
            "versions": [_storage_version(unit="item")],
        },
    )
    assert rejected.status_code >= 400, rejected.text


@pytest.mark.asyncio
async def test_storage_is_not_an_employee_rate(async_client: AsyncClient) -> None:
    """TC-NEW-404: хранение сотруднику не начисляется, это не его работа."""
    suffix = f"storage-employee-{uuid.uuid4().hex[:8]}"
    headers, tenant_id = await _admin(async_client, suffix)
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.tenant_id == tenant_id))
        assert user is not None
        employee_id = str(user.id)

    matrix = await async_client.get("/billing/tariff-matrix", headers=headers)
    rejected = await async_client.put(
        "/billing/tariff-matrix",
        headers=headers,
        json={
            "revision": matrix.json()["revision"],
            "services": FULL_SERVICES,
            "versions": [
                _storage_version(employee_user_id=employee_id, unit="item", rate=10),
            ],
        },
    )
    assert rejected.status_code >= 400, rejected.text
    assert datetime.now(UTC) is not None
