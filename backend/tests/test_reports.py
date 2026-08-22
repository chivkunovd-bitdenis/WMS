"""Тесты для API /reports."""

from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.roles import FULFILLMENT_ADMIN, SELLER_STAFF
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse
from app.models.inventory_balance import InventoryBalance
from app.models.storage_location import StorageLocation
from app.services.passwords import hash_password
from tests.conftest import async_client


@pytest.mark.asyncio
async def test_list_reports_ff_staff(async_client: AsyncClient, session: AsyncSession):
    """ФФ-сотрудник видит полный список отчётов."""
    # Создать тенант и сотрудника
    tenant = Tenant(name="Test Tenant", slug="test-tenant")
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)

    user = User(
        tenant_id=tenant.id,
        email="ff@test.local",
        password_hash=hash_password("password"),
        role=FULFILLMENT_ADMIN,
        seller_id=None,
    )
    session.add(user)
    await session.commit()

    # Авторизоваться
    response = await async_client.post(
        "/auth/login",
        json={"email": "ff@test.local", "password": "password"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]

    # Получить список отчётов
    response = await async_client.get(
        "/reports",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "reports" in data
    assert len(data["reports"]) > 0
    assert any(r["report_id"] == "product_movements" for r in data["reports"])


@pytest.mark.asyncio
async def test_list_reports_seller_staff(async_client: AsyncClient, session: AsyncSession):
    """Продавец видит только доступные ему отчёты."""
    # Создать тенант, селлера и его сотрудника
    tenant = Tenant(name="Test Tenant", slug="test-tenant-2")
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)

    seller = Seller(tenant_id=tenant.id, name="Test Seller")
    session.add(seller)
    await session.commit()
    await session.refresh(seller)

    user = User(
        tenant_id=tenant.id,
        email="seller@test.local",
        password_hash=hash_password("password"),
        role=SELLER_STAFF,
        seller_id=seller.id,
    )
    session.add(user)
    await session.commit()

    # Авторизоваться
    response = await async_client.post(
        "/auth/login",
        json={"email": "seller@test.local", "password": "password"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]

    # Получить список отчётов
    response = await async_client.get(
        "/reports",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "reports" in data
    assert len(data["reports"]) > 0


@pytest.mark.asyncio
async def test_get_report_not_found(async_client: AsyncClient, session: AsyncSession):
    """GET /reports/{report_id} для несуществующего отчёта возвращает 404."""
    # Создать сотрудника
    tenant = Tenant(name="Test Tenant", slug="test-tenant-3")
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)

    user = User(
        tenant_id=tenant.id,
        email="ff@test.local",
        password_hash=hash_password("password"),
        role=FULFILLMENT_ADMIN,
        seller_id=None,
    )
    session.add(user)
    await session.commit()

    # Авторизоваться
    response = await async_client.post(
        "/auth/login",
        json={"email": "ff@test.local", "password": "password"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]

    # Запросить несуществующий отчёт
    response = await async_client.get(
        "/reports/nonexistent",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_report_product_movements(async_client: AsyncClient, session: AsyncSession):
    """GET /reports/product_movements возвращает данные отчёта."""
    # Создать сотрудника
    tenant = Tenant(name="Test Tenant", slug="test-tenant-4")
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)

    user = User(
        tenant_id=tenant.id,
        email="ff@test.local",
        password_hash=hash_password("password"),
        role=FULFILLMENT_ADMIN,
        seller_id=None,
    )
    session.add(user)
    await session.commit()

    # Авторизоваться
    response = await async_client.post(
        "/auth/login",
        json={"email": "ff@test.local", "password": "password"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]

    # Запросить отчёт
    response = await async_client.get(
        "/reports/product_movements",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "period": "month",
            "compare": "previous",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "meta" in data
    assert "rows" in data
    assert "totals" in data
    assert "chart" in data
    assert data["meta"]["report_id"] == "product_movements"


@pytest.mark.asyncio
async def test_export_report_xlsx(async_client: AsyncClient, session: AsyncSession):
    """GET /reports/{report_id}/export?format=xlsx возвращает XLSX файл."""
    # Создать сотрудника
    tenant = Tenant(name="Test Tenant", slug="test-tenant-5")
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)

    user = User(
        tenant_id=tenant.id,
        email="ff@test.local",
        password_hash=hash_password("password"),
        role=FULFILLMENT_ADMIN,
        seller_id=None,
    )
    session.add(user)
    await session.commit()

    # Авторизоваться
    response = await async_client.post(
        "/auth/login",
        json={"email": "ff@test.local", "password": "password"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]

    # Запросить экспорт
    response = await async_client.get(
        "/reports/product_movements/export",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "format": "xlsx",
            "period": "month",
            "compare": "previous",
        },
    )
    assert response.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_export_report_csv(async_client: AsyncClient, session: AsyncSession):
    """GET /reports/{report_id}/export?format=csv возвращает CSV файл."""
    # Создать сотрудника
    tenant = Tenant(name="Test Tenant", slug="test-tenant-6")
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)

    user = User(
        tenant_id=tenant.id,
        email="ff@test.local",
        password_hash=hash_password("password"),
        role=FULFILLMENT_ADMIN,
        seller_id=None,
    )
    session.add(user)
    await session.commit()

    # Авторизоваться
    response = await async_client.post(
        "/auth/login",
        json={"email": "ff@test.local", "password": "password"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]

    # Запросить экспорт
    response = await async_client.get(
        "/reports/product_movements/export",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "format": "csv",
            "period": "month",
            "compare": "previous",
        },
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_get_report_date_validation(async_client: AsyncClient, session: AsyncSession):
    """Проверка валидации дат периода."""
    # Создать сотрудника
    tenant = Tenant(name="Test Tenant", slug="test-tenant-7")
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)

    user = User(
        tenant_id=tenant.id,
        email="ff@test.local",
        password_hash=hash_password("password"),
        role=FULFILLMENT_ADMIN,
        seller_id=None,
    )
    session.add(user)
    await session.commit()

    # Авторизоваться
    response = await async_client.post(
        "/auth/login",
        json={"email": "ff@test.local", "password": "password"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]

    # Запросить отчёт с датой 'от' позже даты 'по'
    response = await async_client.get(
        "/reports/product_movements",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "period": "custom",
            "date_from": "2026-01-31",
            "date_to": "2026-01-01",
        },
    )
    assert response.status_code == 400
    assert "позже" in response.json()["detail"].lower()
