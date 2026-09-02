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
    {"service_code": "fbs_order", "enabled": False},
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


@pytest.mark.asyncio
async def test_report_prices_storage_by_the_matrix_and_prefers_the_seller_rate(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-405: хранение в отчёте считается по матрице, своя ставка бьёт общую."""
    from datetime import time as datetime_time
    from datetime import timedelta
    from decimal import Decimal

    from app.models.inventory_movement import InventoryMovement
    from app.models.product import Product
    from app.services.sorting_location_service import get_or_create_sorting_location
    from app.services.storage_measurement_service import MOSCOW

    suffix = f"storage-price-{uuid.uuid4().hex[:8]}"
    headers, tenant_id = await _admin(async_client, suffix)
    warehouse = await async_client.post(
        "/warehouses", headers=headers, json={"name": f"Склад {suffix}", "code": f"W{suffix[-6:]}"}
    )
    warehouse_id = uuid.UUID(warehouse.json()["id"])
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Луна"})
    seller_id = uuid.UUID(seller.json()["id"])

    today = datetime.now(MOSCOW).date()
    date_from = today - timedelta(days=2)
    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Товар хранения",
            sku_code=f"sku-{suffix}",
            volume_liters=Decimal("2"),
            dimensions_source="manual",
        )
        session.add(product)
        await session.flush()
        location = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
        session.add(
            InventoryMovement(
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                storage_location_id=location.id,
                product_id=product.id,
                quantity_delta=3,
                movement_type="matrix_storage_price_test",
                created_at=datetime.combine(date_from, datetime_time.min, MOSCOW),
            )
        )
        await session.commit()

    params = f"date_from={date_from.isoformat()}&date_to={today.isoformat()}&include_finance=true"

    async def storage_row() -> dict[str, object]:
        response = await async_client.get(
            f"/billing/seller-report/sellers/{seller_id}/details?{params}", headers=headers
        )
        assert response.status_code == 200, response.text
        return response.json()["storage_row"]

    # Без ставки в матрице хранение стоит ноль: старые складские тарифы больше
    # не читаются, и это осознанное решение владельца, а не потеря данных.
    assert (await storage_row())["amount_kopecks"] == 0

    matrix = await async_client.get("/billing/tariff-matrix", headers=headers)
    common_only = await async_client.put(
        "/billing/tariff-matrix",
        headers=headers,
        json={
            "revision": matrix.json()["revision"],
            "services": FULL_SERVICES,
            "versions": [
                _storage_version(rate=100, valid_from_at="2020-01-01T00:00:00Z"),
            ],
        },
    )
    assert common_only.status_code == 200, common_only.text
    with_common = (await storage_row())["amount_kopecks"]
    assert isinstance(with_common, int) and with_common > 0

    matrix = await async_client.get("/billing/tariff-matrix", headers=headers)
    with_seller = await async_client.put(
        "/billing/tariff-matrix",
        headers=headers,
        json={
            "revision": matrix.json()["revision"],
            "services": FULL_SERVICES,
            "versions": [
                _storage_version(rate=100, valid_from_at="2020-01-01T00:00:00Z"),
                # Своя ставка вдвое дешевле и заведена РАНЬШЕ общей по дате:
                # точность обязана победить дату.
                _storage_version(
                    seller_id=str(seller_id), rate=50, valid_from_at="2019-01-01T00:00:00Z"
                ),
            ],
        },
    )
    assert with_seller.status_code == 200, with_seller.text
    assert (await storage_row())["amount_kopecks"] == with_common // 2
