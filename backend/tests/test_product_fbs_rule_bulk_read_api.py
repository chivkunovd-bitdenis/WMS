"""Пакетное чтение правил остатка FBS через один HTTP-запрос.

TC-NEW-FBS-RULE-BULK-READ-001: несколько своих товаров возвращаются одной пачкой.
TC-NEW-FBS-RULE-BULK-READ-002: товар другого тенанта скрыт целиком.
TC-NEW-FBS-RULE-BULK-READ-003: селлер не может прочитать правило другого селлера.
TC-NEW-FBS-RULE-BULK-READ-004: пачка ограничена 200 товарами.
"""

from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient


async def _register_tenant(
    async_client: AsyncClient, label: str
) -> tuple[dict[str, str], str]:
    suffix = f"{time.time_ns()}-{uuid.uuid4().hex[:6]}"
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS rule bulk {label}",
            "slug": f"fbs-rule-bulk-{label.lower()}-{suffix}",
            "admin_email": f"fbs-rule-bulk-{label.lower()}-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    return headers, suffix


async def _create_seller(
    async_client: AsyncClient,
    headers: dict[str, str],
    *,
    name: str,
) -> str:
    response = await async_client.post("/sellers", headers=headers, json={"name": name})
    assert response.status_code in (200, 201), response.text
    return str(response.json()["id"])


async def _create_product(
    async_client: AsyncClient,
    headers: dict[str, str],
    *,
    seller_id: str,
    suffix: str,
) -> str:
    response = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": f"Товар {suffix}",
            "sku_code": f"FBS-RULE-{suffix}",
            "seller_id": seller_id,
        },
    )
    assert response.status_code in (200, 201), response.text
    return str(response.json()["id"])


async def _seller_headers(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    *,
    seller_id: str,
    suffix: str,
) -> dict[str, str]:
    email = f"fbs-rule-seller-{suffix}@example.com"
    created = await async_client.post(
        "/auth/seller-accounts",
        headers=admin_headers,
        json={"seller_id": seller_id, "email": email, "password": "password123"},
    )
    assert created.status_code in (200, 201), created.text
    login = await async_client.post(
        "/auth/login", json={"email": email, "password": "password123"}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _set_rule(
    async_client: AsyncClient,
    headers: dict[str, str],
    product_id: str,
    percent: int,
) -> None:
    response = await async_client.put(
        f"/products/{product_id}/fbs-rule",
        headers=headers,
        json={
            "publish": True,
            "same_everywhere": True,
            "percent": percent,
            "by_warehouse": {},
        },
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_bulk_read_returns_rules_for_multiple_products(
    async_client: AsyncClient,
) -> None:
    # Дано два товара одного тенанта с разными правилами. Когда экран отправляет
    # их одной пачкой, тогда получает обе настройки в исходном порядке.
    headers, suffix = await _register_tenant(async_client, "Many")
    seller_id = await _create_seller(async_client, headers, name="Селлер пачки")
    first_id = await _create_product(
        async_client, headers, seller_id=seller_id, suffix=f"{suffix}-1"
    )
    second_id = await _create_product(
        async_client, headers, seller_id=seller_id, suffix=f"{suffix}-2"
    )
    await _set_rule(async_client, headers, first_id, 30)
    await _set_rule(async_client, headers, second_id, 70)

    response = await async_client.post(
        "/products/fbs-rule/bulk",
        headers=headers,
        json={"product_ids": [second_id, first_id]},
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["product_id"] for item in items] == [second_id, first_id]
    assert [item["percent"] for item in items] == [70, 30]
    assert all(item["publish"] is True for item in items)
    assert all(item["published_now"] == 0 for item in items)


@pytest.mark.asyncio
async def test_bulk_read_hides_product_from_other_tenant(
    async_client: AsyncClient,
) -> None:
    # Негатив: наличие одного чужого ID отклоняет всю пачку; частичного ответа,
    # по которому можно подтвердить существование чужого товара, нет.
    own_headers, own_suffix = await _register_tenant(async_client, "Own")
    own_seller = await _create_seller(async_client, own_headers, name="Свой селлер")
    own_product = await _create_product(
        async_client,
        own_headers,
        seller_id=own_seller,
        suffix=f"{own_suffix}-own",
    )
    foreign_headers, foreign_suffix = await _register_tenant(async_client, "Foreign")
    foreign_seller = await _create_seller(
        async_client, foreign_headers, name="Чужой селлер"
    )
    foreign_product = await _create_product(
        async_client,
        foreign_headers,
        seller_id=foreign_seller,
        suffix=f"{foreign_suffix}-foreign",
    )

    response = await async_client.post(
        "/products/fbs-rule/bulk",
        headers=own_headers,
        json={"product_ids": [own_product, foreign_product]},
    )

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "product_not_found"


@pytest.mark.asyncio
async def test_bulk_read_rejects_product_from_other_seller(
    async_client: AsyncClient,
) -> None:
    # Ограничение роли: селлер читает правила только своего каталога, даже если
    # знает UUID товара другого селлера того же фулфилмента.
    admin_headers, suffix = await _register_tenant(async_client, "SellerScope")
    own_seller = await _create_seller(async_client, admin_headers, name="Селлер А")
    other_seller = await _create_seller(async_client, admin_headers, name="Селлер Б")
    own_product = await _create_product(
        async_client,
        admin_headers,
        seller_id=own_seller,
        suffix=f"{suffix}-a",
    )
    other_product = await _create_product(
        async_client,
        admin_headers,
        seller_id=other_seller,
        suffix=f"{suffix}-b",
    )
    seller_headers = await _seller_headers(
        async_client,
        admin_headers,
        seller_id=own_seller,
        suffix=suffix,
    )

    response = await async_client.post(
        "/products/fbs-rule/bulk",
        headers=seller_headers,
        json={"product_ids": [own_product, other_product]},
    )

    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "forbidden"


@pytest.mark.asyncio
async def test_bulk_read_rejects_more_than_two_hundred_products(
    async_client: AsyncClient,
) -> None:
    # Негатив: 201-й ID даёт 422 с понятным пределом; сервер не начинает поиск
    # и расчёт правил для заведомо слишком большой пачки.
    headers, _suffix = await _register_tenant(async_client, "Limit")
    response = await async_client.post(
        "/products/fbs-rule/bulk",
        headers=headers,
        json={"product_ids": [str(uuid.uuid4()) for _ in range(201)]},
    )

    assert response.status_code == 422, response.text
    messages = [item["msg"] for item in response.json()["detail"]]
    assert any("максимум для 200 товаров" in message for message in messages)
