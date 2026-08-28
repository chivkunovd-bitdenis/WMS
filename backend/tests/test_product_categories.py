"""TC-NEW-A2-001..004: WB subject categories on tenant- and seller-scoped products."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.product import Product
from app.models.seller_shop_delegation import SellerShopDelegation
from app.services.tokens import decode_access_token
from app.services.wildberries_product_import_service import upsert_products_from_wb_cards


async def _register_admin(
    async_client: AsyncClient,
    *,
    suffix: str,
) -> tuple[dict[str, str], uuid.UUID]:
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Product categories {suffix}",
            "slug": f"product-categories-{suffix}",
            "admin_email": f"product-categories-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    token = str(response.json()["access_token"])
    return {"Authorization": f"Bearer {token}"}, uuid.UUID(
        str(decode_access_token(token)["tenant_id"])
    )


async def _seed_product(
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID | None,
    sku_code: str,
    category: str | None,
) -> Product:
    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name=f"Товар {sku_code}",
            sku_code=sku_code,
            category=category,
        )
        session.add(product)
        await session.commit()
        await session.refresh(product)
        return product


async def _allow_seller_shop(user_id: str, seller_id: str) -> None:
    async with SessionLocal() as session:
        session.add(
            SellerShopDelegation(
                user_id=uuid.UUID(user_id),
                target_seller_id=uuid.UUID(seller_id),
                enabled=True,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_wb_subject_category_is_trimmed_for_every_variant_and_blank_resync_preserves_it(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    admin_headers, tenant_id = await _register_admin(async_client, suffix=suffix)
    seller = await async_client.post("/sellers", headers=admin_headers, json={"name": "Категории"})
    assert seller.status_code == 201, seller.text
    seller_id = uuid.UUID(str(seller.json()["id"]))

    card = {
        "nmID": 1001,
        "vendorCode": f"CAT-{suffix}",
        "title": "Футболка",
        "subjectName": "  Футболки  ",
        "sizes": [
            {"chrtID": 1, "techSize": "S", "skus": [f"{suffix}01"]},
            {"chrtID": 2, "techSize": "M", "skus": [f"{suffix}02"]},
        ],
    }
    async with SessionLocal() as session:
        stats = await upsert_products_from_wb_cards(session, tenant_id, seller_id, [card])
        assert stats["products_created"] == 2
        rows = list(
            (
                await session.execute(
                    select(Product).where(
                        Product.tenant_id == tenant_id,
                        Product.seller_id == seller_id,
                    )
                )
            ).scalars()
        )
        assert {row.category for row in rows} == {"Футболки"}

        card["subjectName"] = "Брюки"
        await upsert_products_from_wb_cards(session, tenant_id, seller_id, [card])
        assert {row.category for row in rows} == {"Брюки"}

        card["subjectName"] = "   "
        await upsert_products_from_wb_cards(session, tenant_id, seller_id, [card])
        assert {row.category for row in rows} == {"Брюки"}

        card["subjectName"] = ["не строка"]
        await upsert_products_from_wb_cards(session, tenant_id, seller_id, [card])
        assert {row.category for row in rows} == {"Брюки"}

        del card["subjectName"]
        await upsert_products_from_wb_cards(session, tenant_id, seller_id, [card])
        assert {row.category for row in rows} == {"Брюки"}

        empty_subject_card = {
            "nmID": 1002,
            "vendorCode": f"EMPTY-{suffix}",
            "title": "Без предмета",
            "subjectName": "   ",
            "sizes": [{"chrtID": 3, "techSize": "L", "skus": [f"{suffix}03"]}],
        }
        await upsert_products_from_wb_cards(session, tenant_id, seller_id, [empty_subject_card])
        empty_subject = await session.scalar(
            select(Product).where(Product.wb_barcode == f"{suffix}03")
        )
        assert empty_subject is not None
        assert empty_subject.category is None

    products = await async_client.get("/products", headers=admin_headers)
    assert products.status_code == 200, products.text
    imported = [row for row in products.json() if row["seller_id"] == str(seller_id)]
    assert {row["category"] for row in imported} == {"Брюки", None}


@pytest.mark.asyncio
async def test_product_categories_are_unique_sorted_nonempty_and_tenant_isolated(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    admin_headers, tenant_id = await _register_admin(async_client, suffix=suffix)
    seller = await async_client.post("/sellers", headers=admin_headers, json={"name": "Основной"})
    assert seller.status_code == 201, seller.text
    seller_id = uuid.UUID(str(seller.json()["id"]))

    await _seed_product(
        tenant_id=tenant_id, seller_id=seller_id, sku_code=f"CAT-TEE-{suffix}", category="Футболки"
    )
    await _seed_product(
        tenant_id=tenant_id, seller_id=seller_id, sku_code=f"CAT-PANTS-{suffix}", category="Брюки"
    )
    await _seed_product(
        tenant_id=tenant_id, seller_id=seller_id, sku_code=f"CAT-DUP-{suffix}", category="Футболки"
    )
    await _seed_product(
        tenant_id=tenant_id, seller_id=seller_id, sku_code=f"CAT-NULL-{suffix}", category=None
    )

    other_headers, other_tenant_id = await _register_admin(
        async_client, suffix=f"other-{suffix}"
    )
    other_seller = await async_client.post(
        "/sellers", headers=other_headers, json={"name": "Чужой"}
    )
    assert other_seller.status_code == 201, other_seller.text
    await _seed_product(
        tenant_id=other_tenant_id,
        seller_id=uuid.UUID(str(other_seller.json()["id"])),
        sku_code=f"CAT-OTHER-{suffix}",
        category="Чужая категория",
    )

    categories = await async_client.get("/products/categories", headers=admin_headers)
    assert categories.status_code == 200, categories.text
    assert categories.json() == ["Брюки", "Футболки"]

    products = await async_client.get("/products", headers=admin_headers)
    assert products.status_code == 200, products.text
    by_sku = {row["sku_code"]: row for row in products.json()}
    assert by_sku[f"CAT-NULL-{suffix}"]["category"] is None
    assert by_sku[f"CAT-TEE-{suffix}"]["category"] == "Футболки"
    assert f"CAT-OTHER-{suffix}" not in by_sku


@pytest.mark.asyncio
async def test_product_categories_follow_effective_seller_scope_and_empty_state(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    admin_headers, tenant_id = await _register_admin(async_client, suffix=suffix)
    seller_one = await async_client.post(
        "/sellers/with-account",
        headers=admin_headers,
        json={
            "name": "Первый селлер",
            "email": f"first-category-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert seller_one.status_code == 201, seller_one.text
    seller_one_id = uuid.UUID(str(seller_one.json()["seller_id"]))
    seller_two = await async_client.post(
        "/sellers", headers=admin_headers, json={"name": "Второй селлер"}
    )
    assert seller_two.status_code == 201, seller_two.text
    seller_two_id = uuid.UUID(str(seller_two.json()["id"]))

    await _seed_product(
        tenant_id=tenant_id,
        seller_id=seller_one_id,
        sku_code=f"CAT-FIRST-{suffix}",
        category="Платья",
    )
    await _seed_product(
        tenant_id=tenant_id,
        seller_id=seller_two_id,
        sku_code=f"CAT-SECOND-{suffix}",
        category="Куртки",
    )

    login = await async_client.post(
        "/auth/login",
        json={"email": f"first-category-{suffix}@example.com", "password": "password123"},
    )
    assert login.status_code == 200, login.text
    seller_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    categories = await async_client.get("/products/categories", headers=seller_headers)
    assert categories.status_code == 200, categories.text
    assert categories.json() == ["Платья"]
    products = await async_client.get("/products", headers=seller_headers)
    assert products.status_code == 200, products.text
    assert {row["sku_code"] for row in products.json()} == {f"CAT-FIRST-{suffix}"}

    empty_seller = await async_client.post(
        "/sellers/with-account",
        headers=admin_headers,
        json={
            "name": "Без категорий",
            "email": f"empty-category-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert empty_seller.status_code == 201, empty_seller.text
    empty_seller_id = uuid.UUID(str(empty_seller.json()["seller_id"]))
    await _seed_product(
        tenant_id=tenant_id,
        seller_id=empty_seller_id,
        sku_code=f"CAT-EMPTY-{suffix}",
        category=None,
    )
    empty_login = await async_client.post(
        "/auth/login",
        json={"email": f"empty-category-{suffix}@example.com", "password": "password123"},
    )
    assert empty_login.status_code == 200, empty_login.text
    empty_headers = {"Authorization": f"Bearer {empty_login.json()['access_token']}"}
    empty_categories = await async_client.get("/products/categories", headers=empty_headers)
    assert empty_categories.status_code == 200, empty_categories.text
    assert empty_categories.json() == []


@pytest.mark.asyncio
async def test_categories_trim_duplicate_values_keep_exact_distinct_names_and_static_route(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-A2-002: route must aggregate canonical values, not a UUID endpoint."""
    suffix = str(int(time.time() * 1000))
    admin_headers, tenant_id = await _register_admin(async_client, suffix=suffix)
    seller = await async_client.post("/sellers", headers=admin_headers, json={"name": "Категории"})
    assert seller.status_code == 201, seller.text
    seller_id = uuid.UUID(str(seller.json()["id"]))

    for ordinal, category in enumerate(("  Alpha  ", "Alpha", "Beta", "alpha")):
        await _seed_product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            sku_code=f"CAT-NORMALIZED-{suffix}-{ordinal}",
            category=category,
        )

    response = await async_client.get("/products/categories", headers=admin_headers)
    assert response.status_code == 200, response.text
    # ``Alpha`` and ``alpha`` intentionally remain separate: A-2 has no taxonomy.
    assert response.json() == ["Alpha", "Beta", "alpha"]


@pytest.mark.asyncio
async def test_categories_follow_switched_effective_seller_but_admin_sees_tenant_scope(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-A2-003: a delegating seller cannot retain home-shop categories."""
    suffix = str(int(time.time() * 1000))
    admin_headers, tenant_id = await _register_admin(async_client, suffix=suffix)
    home = await async_client.post(
        "/sellers/with-account",
        headers=admin_headers,
        json={
            "name": "Домашний магазин",
            "email": f"vitalik-category-home-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert home.status_code == 201, home.text
    home_seller_id = uuid.UUID(str(home.json()["seller_id"]))
    delegated = await async_client.post(
        "/sellers",
        headers=admin_headers,
        json={"name": "Делегированный магазин"},
    )
    assert delegated.status_code == 201, delegated.text
    delegated_seller_id = uuid.UUID(str(delegated.json()["id"]))
    await _seed_product(
        tenant_id=tenant_id,
        seller_id=home_seller_id,
        sku_code=f"CAT-HOME-{suffix}",
        category="Домашняя категория",
    )
    await _seed_product(
        tenant_id=tenant_id,
        seller_id=delegated_seller_id,
        sku_code=f"CAT-DELEGATED-{suffix}",
        category="Делегированная категория",
    )
    await _allow_seller_shop(str(home.json()["user_id"]), str(delegated_seller_id))

    login = await async_client.post(
        "/auth/login",
        json={"email": f"vitalik-category-home-{suffix}@example.com", "password": "password123"},
    )
    assert login.status_code == 200, login.text
    home_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    home_categories = await async_client.get("/products/categories", headers=home_headers)
    assert home_categories.status_code == 200, home_categories.text
    assert home_categories.json() == ["Домашняя категория"]

    switched = await async_client.post(
        "/auth/switch-seller",
        headers=home_headers,
        json={"seller_id": str(delegated_seller_id)},
    )
    assert switched.status_code == 200, switched.text
    delegated_headers = {"Authorization": f"Bearer {switched.json()['access_token']}"}
    delegated_categories = await async_client.get("/products/categories", headers=delegated_headers)
    assert delegated_categories.status_code == 200, delegated_categories.text
    assert delegated_categories.json() == ["Делегированная категория"]

    admin_categories = await async_client.get("/products/categories", headers=admin_headers)
    assert admin_categories.status_code == 200, admin_categories.text
    assert admin_categories.json() == ["Делегированная категория", "Домашняя категория"]


CATEGORY_REVISION = "20260828_0221"


def test_product_category_migration_is_additive_and_the_only_head() -> None:
    """TC-NEW-A2-004: historical products must remain untouched by a branched migration."""
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    script = ScriptDirectory.from_config(config)
    # Голова должна быть одна: две головы — это разъехавшиеся ветки миграций,
    # и на выкатке они дадут отказ. А вот её номер закреплять нельзя: каждая
    # следующая миграция сдвигает голову, и тест ломался бы без причины.
    assert len(script.get_heads()) == 1, script.get_heads()
    revision = script.get_revision(CATEGORY_REVISION)
    assert revision is not None
    source = Path(revision.path).read_text(encoding="utf-8")
    assert "op.add_column(\"products\"" in source
    assert "nullable=True" in source
    assert "op.execute" not in source
    assert "op.alter_column" not in source
