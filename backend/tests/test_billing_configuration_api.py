from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.billing import BillingLedgerEntry, BillingTariffVersion
from app.models.tenant import Tenant


async def _register_admin(async_client: AsyncClient, label: str) -> dict[str, str]:
    suffix = f"{label}-{time.time_ns()}"
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Billing {label}",
            "slug": suffix,
            "admin_email": f"{suffix}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _ff_profile() -> dict[str, str]:
    return {
        "legal_name": "Фулфилмент",
        "inn": "7707083893",
        "bank_name": "Банк",
        "bik": "044525225",
        "settlement_account": "40702810000000000001",
        "correspondent_account": "30101810400000000225",
    }


@pytest.mark.asyncio
async def test_billing_configuration_api_validates_profiles_tariffs_and_tenant_boundary(
    async_client: AsyncClient,
) -> None:
    owner_headers = await _register_admin(async_client, "owner")
    other_headers = await _register_admin(async_client, "other")
    foreign_seller = await async_client.post(
        "/sellers", headers=other_headers, json={"name": "Чужой селлер"}
    )
    assert foreign_seller.status_code == 201, foreign_seller.text
    foreign_seller_id = uuid.UUID(foreign_seller.json()["id"])

    invalid_ff = await async_client.put(
        "/billing/profiles/ff",
        headers=owner_headers,
        json={**_ff_profile(), "bank_name": "   "},
    )
    assert invalid_ff.status_code == 400
    assert invalid_ff.json()["detail"] == "Для реквизитов ФФ заполните банковские поля"

    saved_ff = await async_client.put(
        "/billing/profiles/ff", headers=owner_headers, json=_ff_profile()
    )
    assert saved_ff.status_code == 200, saved_ff.text
    assert saved_ff.json()["bank_name"] == "Банк"

    invalid_inn = await async_client.put(
        "/billing/profiles/ff",
        headers=owner_headers,
        json={**_ff_profile(), "legal_name": "Не должно сохраниться", "inn": "7707083894"},
    )
    assert invalid_inn.status_code == 400
    assert invalid_inn.json()["detail"] == "Проверьте ИНН: контрольное число не совпадает"
    unchanged_ff = await async_client.get("/billing/profiles/ff", headers=owner_headers)
    assert unchanged_ff.status_code == 200
    assert unchanged_ff.json()["legal_name"] == "Фулфилмент"
    assert unchanged_ff.json()["inn"] == "7707083893"

    foreign_profile = await async_client.put(
        f"/billing/profiles/sellers/{foreign_seller_id}",
        headers=owner_headers,
        json={"legal_name": "Чужой", "inn": "7707083893"},
    )
    assert foreign_profile.status_code == 400
    assert foreign_profile.json()["detail"] == "Селлер не найден в текущем tenant"

    tariff = {
        "service_code": "inbound",
        "unit": "document",
        "amount": "0.00",
        "valid_from": "2026-09-01",
    }
    created = await async_client.post("/billing/tariffs", headers=owner_headers, json=tariff)
    assert created.status_code == 201, created.text
    assert created.json()["amount"] == 0

    future_tariff = await async_client.post(
        "/billing/tariffs",
        headers=owner_headers,
        json={**tariff, "amount": "45.00", "valid_from": "2026-11-01"},
    )
    assert future_tariff.status_code == 201, future_tariff.text
    assert future_tariff.json()["amount"] == 4500

    async with SessionLocal() as session:
        persisted_tariffs = (await session.scalars(
            select(BillingTariffVersion).where(
                BillingTariffVersion.id.in_(
                    (uuid.UUID(created.json()["id"]), uuid.UUID(future_tariff.json()["id"]))
                )
            )
        )).all()
    assert {tariff.amount for tariff in persisted_tariffs} == {0, 4500}

    for invalid_amount in ("-0.01", "45.001"):
        invalid_amount_response = await async_client.post(
            "/billing/tariffs",
            headers=owner_headers,
            json={**tariff, "amount": invalid_amount, "valid_from": "2026-12-01"},
        )
        assert invalid_amount_response.status_code == 422

    conflicting = await async_client.post(
        "/billing/tariffs",
        headers=owner_headers,
        json={**tariff, "amount": "10.00", "valid_from": "2026-10-01"},
    )
    assert conflicting.status_code == 400
    assert conflicting.json()["detail"] == "Дата пересекает будущую версию ставки"

    tariffs = await async_client.get("/billing/tariffs", headers=owner_headers)
    assert tariffs.status_code == 200
    assert [item["valid_from"] for item in tariffs.json()] == ["2026-11-01", "2026-09-01"]
    assert [item["valid_to"] for item in tariffs.json()] == [None, "2026-10-31"]
    assert [item["amount"] for item in tariffs.json()] == [4500, 0]


@pytest.mark.asyncio
async def test_creating_covering_tariffs_reprices_unpriced_entries_in_kopecks(
    async_client: AsyncClient,
) -> None:
    headers = await _register_admin(async_client, "repricing")

    async with SessionLocal() as session:
        tenant_id = await session.scalar(
            select(Tenant.id).where(Tenant.name == "Billing repricing")
        )
        assert tenant_id is not None
        entries = {
            "document": BillingLedgerEntry(
                tenant_id=tenant_id,
                service_code="inbound",
                source="inbound",
                source_type="repricing-document",
                source_id=uuid.uuid4(),
                unit="document",
                quantity=Decimal("7"),
                occurred_at=datetime(2026, 9, 2, 12, tzinfo=UTC),
            ),
            "item": BillingLedgerEntry(
                tenant_id=tenant_id,
                service_code="marketplace_outbound",
                source="marketplace_outbound",
                source_type="repricing-item",
                source_id=uuid.uuid4(),
                unit="item",
                quantity=Decimal("2.5"),
                occurred_at=datetime(2026, 9, 2, 12, tzinfo=UTC),
            ),
            "liter_day": BillingLedgerEntry(
                tenant_id=tenant_id,
                service_code="storage_liter_day",
                source="storage_measurement",
                source_type="repricing-liter-day",
                source_id=uuid.uuid4(),
                unit="liter_day",
                quantity=Decimal("12.5"),
                occurred_at=datetime(2026, 9, 2, 12, tzinfo=UTC),
            ),
        }
        session.add_all(entries.values())
        await session.commit()
        entry_ids = {name: entry.id for name, entry in entries.items()}

    tariffs = (
        ("inbound", "document", "45.00"),
        ("marketplace_outbound", "item", "12.34"),
        ("storage_liter_day", "liter_day", "0.15"),
    )
    tariff_ids: dict[str, uuid.UUID] = {}
    for service_code, unit, amount in tariffs:
        response = await async_client.post(
            "/billing/tariffs",
            headers=headers,
            json={
                "service_code": service_code,
                "unit": unit,
                "amount": amount,
                "valid_from": "2026-09-01",
            },
        )
        assert response.status_code == 201, response.text
        tariff_ids[unit] = uuid.UUID(response.json()["id"])

    async with SessionLocal() as session:
        repriced = {
            name: await session.get(BillingLedgerEntry, entry_id)
            for name, entry_id in entry_ids.items()
        }
        await session.flush()

    document = repriced["document"]
    assert document is not None
    assert document.tariff_version_id == tariff_ids["document"]
    assert document.unit == "document"
    assert document.quantity == Decimal("1")
    assert isinstance(document.rate, int) and document.rate == 4500
    assert isinstance(document.amount, int) and document.amount == 4500

    item = repriced["item"]
    assert item is not None
    assert item.tariff_version_id == tariff_ids["item"]
    assert item.unit == "item"
    assert item.quantity == Decimal("2.5")
    assert isinstance(item.rate, int) and item.rate == 1234
    assert isinstance(item.amount, int) and item.amount == 3085

    liter_day = repriced["liter_day"]
    assert liter_day is not None
    assert liter_day.tariff_version_id == tariff_ids["liter_day"]
    assert liter_day.unit == "liter_day"
    assert liter_day.quantity == Decimal("12.5")
    assert isinstance(liter_day.rate, int) and liter_day.rate == 15
    assert isinstance(liter_day.amount, int) and liter_day.amount == 188
