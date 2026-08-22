from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient


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
    assert created.json()["amount"] == "0.00"

    future_tariff = await async_client.post(
        "/billing/tariffs",
        headers=owner_headers,
        json={**tariff, "amount": "15.00", "valid_from": "2026-11-01"},
    )
    assert future_tariff.status_code == 201, future_tariff.text

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
    assert [item["amount"] for item in tariffs.json()] == ["15.00", "0.00"]
