"""API tests for bulk «поставить fbs_stock_limit по фактическому остатку».

Эндпоинт: PATCH /products/fbs-stock-limit/from-balance/bulk

TC-NEW-FBS-STOCK-FROM-BALANCE-001: остаток на одном складе становится лимитом как есть.
TC-NEW-FBS-STOCK-FROM-BALANCE-002: занятое (бронь под FBS-заказ) вычитается из остатка.
TC-NEW-FBS-STOCK-FROM-BALANCE-003: старая разнарядка по складам обнуляется (quantity=0),
    а не удаляется — даже если она была больше нового остатка.
TC-NEW-FBS-STOCK-FROM-BALANCE-004: товар чужого тенанта не находится и не меняется.
TC-NEW-FBS-STOCK-FROM-BALANCE-005: остаток с нескольких складов тенанта складывается
    в один пул.
TC-NEW-FBS-STOCK-FROM-BALANCE-006: в ответе видно, сколько складов сброшено по каждому
    товару и у скольких товаров вообще была разнарядка.
"""

from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_order import FbsOrder, FbsOrderReservation
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product import Product
from app.services import inventory_service


async def _register_tenant_with_seller(async_client: AsyncClient) -> dict[str, object]:
    """Регистрирует тенанта, селлера и учётку селлера, отдаёт готовые заголовки."""
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS balance {suffix}",
            "slug": f"fbs-balance-{suffix}",
            "admin_email": f"fbs-balance-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    admin_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    seller = await async_client.post(
        "/sellers", headers=admin_headers, json={"name": f"Seller {suffix}"}
    )
    assert seller.status_code in (200, 201), seller.text
    seller_id = seller.json()["id"]

    seller_email = f"fbs-balance-seller-{suffix}@example.com"
    created_account = await async_client.post(
        "/auth/seller-accounts",
        headers=admin_headers,
        json={"seller_id": seller_id, "email": seller_email, "password": "password123"},
    )
    assert created_account.status_code in (200, 201), created_account.text
    seller_login = await async_client.post(
        "/auth/login",
        json={"email": seller_email, "password": "password123"},
    )
    assert seller_login.status_code == 200, seller_login.text
    seller_headers = {"Authorization": f"Bearer {seller_login.json()['access_token']}"}

    return {
        "suffix": suffix,
        "admin_headers": admin_headers,
        "seller_headers": seller_headers,
        "seller_id": seller_id,
    }


async def _create_warehouse_with_location(
    async_client: AsyncClient, admin_headers: dict[str, str], code_suffix: str
) -> tuple[str, str]:
    warehouse = await async_client.post(
        "/warehouses",
        headers=admin_headers,
        json={"name": f"WH {code_suffix}", "code": f"wh-{code_suffix}"},
    )
    assert warehouse.status_code in (200, 201), warehouse.text
    warehouse_id = warehouse.json()["id"]
    location = await async_client.post(
        f"/warehouses/{warehouse_id}/locations",
        headers=admin_headers,
        json={"code": f"cell-{code_suffix}"},
    )
    assert location.status_code in (200, 201), location.text
    return warehouse_id, location.json()["id"]


async def _create_product(
    async_client: AsyncClient, admin_headers: dict[str, str], seller_id: str, sku_suffix: str
) -> str:
    product = await async_client.post(
        "/products",
        headers=admin_headers,
        json={
            "name": f"Product {sku_suffix}",
            "sku_code": f"FBSBAL-{sku_suffix}",
            "seller_id": seller_id,
        },
    )
    assert product.status_code in (200, 201), product.text
    return str(product.json()["id"])


@pytest.mark.asyncio
async def test_apply_from_balance_sets_limit_to_actual_stock(async_client: AsyncClient) -> None:
    """У товара на складе есть остаток — после вызова fbs_stock_limit равен ему."""
    ctx = await _register_tenant_with_seller(async_client)
    admin_headers = ctx["admin_headers"]
    seller_headers = ctx["seller_headers"]
    suffix = str(ctx["suffix"])

    _warehouse_id, location_id = await _create_warehouse_with_location(
        async_client, admin_headers, suffix
    )
    product_id = await _create_product(async_client, admin_headers, str(ctx["seller_id"]), suffix)

    async with SessionLocal() as session:
        product = await session.get(Product, uuid.UUID(product_id))
        assert product is not None
        tenant_id = product.tenant_id
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product.id,
            storage_location_id=uuid.UUID(location_id),
            quantity_delta=10,
            movement_type="inbound_intake",
        )
        await session.commit()

    resp = await async_client.patch(
        "/products/fbs-stock-limit/from-balance/bulk",
        headers=seller_headers,
        json={"product_ids": [product_id]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["updated_count"] == 1
    assert body["updated"] == [
        {"product_id": product_id, "fbs_stock_limit": 10, "reset_warehouses_count": 0}
    ]
    assert body["skipped"] == []
    assert body["pool_reset_products_count"] == 0

    rows = (await async_client.get("/products/ff-catalog", headers=admin_headers)).json()
    row = next(r for r in rows if r["id"] == product_id)
    assert row["fbs_stock_limit"] == 10
    assert row["fbs_stock_sync_enabled"] is True


@pytest.mark.asyncio
async def test_apply_from_balance_subtracts_reserved(async_client: AsyncClient) -> None:
    """Занятое под FBS-заказ вычитается: лимит становится равен доступному, не полному."""
    ctx = await _register_tenant_with_seller(async_client)
    admin_headers = ctx["admin_headers"]
    seller_headers = ctx["seller_headers"]
    seller_id = str(ctx["seller_id"])
    suffix = str(ctx["suffix"])

    warehouse_id, location_id = await _create_warehouse_with_location(
        async_client, admin_headers, suffix
    )
    product_id = await _create_product(async_client, admin_headers, seller_id, suffix)

    async with SessionLocal() as session:
        product = await session.get(Product, uuid.UUID(product_id))
        assert product is not None
        tenant_id = product.tenant_id
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product.id,
            storage_location_id=uuid.UUID(location_id),
            quantity_delta=10,
            movement_type="inbound_intake",
        )
        order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=uuid.UUID(seller_id),
            warehouse_id=uuid.UUID(warehouse_id),
            product_id=product.id,
            wb_order_id=910_001,
            created_at_wb=product.created_at,
            deadline_at=product.created_at,
            mapping_status="mapped",
            reserve_status="reserved",
        )
        session.add(order)
        await session.flush()
        session.add(
            FbsOrderReservation(
                tenant_id=tenant_id,
                fbs_order_id=order.id,
                product_id=product.id,
                warehouse_id=uuid.UUID(warehouse_id),
                quantity=3,
            )
        )
        await session.commit()

    resp = await async_client.patch(
        "/products/fbs-stock-limit/from-balance/bulk",
        headers=seller_headers,
        json={"product_ids": [product_id]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["updated_count"] == 1
    assert body["updated"] == [
        {"product_id": product_id, "fbs_stock_limit": 7, "reset_warehouses_count": 0}
    ]
    assert body["skipped"] == []


@pytest.mark.asyncio
async def test_apply_from_balance_resets_pool_to_zero_without_deleting(
    async_client: AsyncClient,
) -> None:
    """Смена общего остатка обесценивает старую раскладку по складам.

    Владелец решил: разнарядка сбрасывается всегда (не только при конфликте), и
    товар при этом всё равно обновляется — «не трогаем конфликтный товар» отменено.
    Строка в fbs_binding_stock_pools должна остаться с quantity=0, а не исчезнуть:
    удаление увело бы товар из публикации в WB, и там завис бы старый остаток.
    """
    ctx = await _register_tenant_with_seller(async_client)
    admin_headers = ctx["admin_headers"]
    seller_headers = ctx["seller_headers"]
    seller_id = str(ctx["seller_id"])
    suffix = str(ctx["suffix"])

    warehouse_id, location_id = await _create_warehouse_with_location(
        async_client, admin_headers, suffix
    )
    product_id = await _create_product(async_client, admin_headers, seller_id, suffix)

    pool_id: uuid.UUID
    async with SessionLocal() as session:
        product = await session.get(Product, uuid.UUID(product_id))
        assert product is not None
        tenant_id = product.tenant_id
        # Остаток меньше того, что уже разложено по складам (5 < 8) — раньше это
        # было причиной пропустить товар, теперь его всё равно обновляют.
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product.id,
            storage_location_id=uuid.UUID(location_id),
            quantity_delta=5,
            movement_type="inbound_intake",
        )
        binding = FbsWarehouseBinding(
            tenant_id=tenant_id,
            seller_id=uuid.UUID(seller_id),
            wb_warehouse_id=555_001,
            wms_warehouse_id=uuid.UUID(warehouse_id),
        )
        session.add(binding)
        await session.flush()
        pool = FbsBindingStockPool(
            tenant_id=tenant_id,
            binding_id=binding.id,
            product_id=product.id,
            quantity=8,
        )
        session.add(pool)
        await session.flush()
        pool_id = pool.id
        await session.commit()

    resp = await async_client.patch(
        "/products/fbs-stock-limit/from-balance/bulk",
        headers=seller_headers,
        json={"product_ids": [product_id]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["updated_count"] == 1
    assert body["updated"] == [
        {"product_id": product_id, "fbs_stock_limit": 5, "reset_warehouses_count": 1}
    ]
    assert body["skipped"] == []
    assert body["pool_reset_products_count"] == 1

    rows = (await async_client.get("/products/ff-catalog", headers=admin_headers)).json()
    row = next(r for r in rows if r["id"] == product_id)
    assert row["fbs_stock_limit"] == 5

    async with SessionLocal() as session:
        pool_after = await session.get(FbsBindingStockPool, pool_id)
        assert pool_after is not None, "строку разнарядки нельзя удалять, только обнулять"
        assert pool_after.quantity == 0


@pytest.mark.asyncio
async def test_apply_from_balance_reports_reset_warehouses_count(
    async_client: AsyncClient,
) -> None:
    """В ответе видно, сколько складов сброшено по товару и сколько товаров задето."""
    ctx = await _register_tenant_with_seller(async_client)
    admin_headers = ctx["admin_headers"]
    seller_headers = ctx["seller_headers"]
    seller_id = str(ctx["seller_id"])
    suffix = str(ctx["suffix"])

    warehouse_1, location_1 = await _create_warehouse_with_location(
        async_client, admin_headers, f"{suffix}-1"
    )
    warehouse_2, _location_2 = await _create_warehouse_with_location(
        async_client, admin_headers, f"{suffix}-2"
    )
    product_with_pools_id = await _create_product(
        async_client, admin_headers, seller_id, f"{suffix}-with-pools"
    )
    product_without_pools_id = await _create_product(
        async_client, admin_headers, seller_id, f"{suffix}-no-pools"
    )

    async with SessionLocal() as session:
        product_a = await session.get(Product, uuid.UUID(product_with_pools_id))
        product_b = await session.get(Product, uuid.UUID(product_without_pools_id))
        assert product_a is not None
        assert product_b is not None
        tenant_id = product_a.tenant_id

        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_a.id,
            storage_location_id=uuid.UUID(location_1),
            quantity_delta=20,
            movement_type="inbound_intake",
        )
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_b.id,
            storage_location_id=uuid.UUID(location_1),
            quantity_delta=4,
            movement_type="inbound_intake",
        )

        binding_1 = FbsWarehouseBinding(
            tenant_id=tenant_id,
            seller_id=uuid.UUID(seller_id),
            wb_warehouse_id=555_101,
            wms_warehouse_id=uuid.UUID(warehouse_1),
        )
        binding_2 = FbsWarehouseBinding(
            tenant_id=tenant_id,
            seller_id=uuid.UUID(seller_id),
            wb_warehouse_id=555_102,
            wms_warehouse_id=uuid.UUID(warehouse_2),
        )
        session.add_all([binding_1, binding_2])
        await session.flush()
        # Товару А разложили по двум складам, товару B — вообще не раскладывали.
        session.add_all(
            [
                FbsBindingStockPool(
                    tenant_id=tenant_id,
                    binding_id=binding_1.id,
                    product_id=product_a.id,
                    quantity=3,
                ),
                FbsBindingStockPool(
                    tenant_id=tenant_id,
                    binding_id=binding_2.id,
                    product_id=product_a.id,
                    quantity=4,
                ),
            ]
        )
        await session.commit()

    resp = await async_client.patch(
        "/products/fbs-stock-limit/from-balance/bulk",
        headers=seller_headers,
        json={"product_ids": [product_with_pools_id, product_without_pools_id]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["updated_count"] == 2
    updated_by_id = {item["product_id"]: item for item in body["updated"]}
    assert updated_by_id[product_with_pools_id]["reset_warehouses_count"] == 2
    assert updated_by_id[product_without_pools_id]["reset_warehouses_count"] == 0
    # Разнарядка реально была только у одного из двух обновлённых товаров.
    assert body["pool_reset_products_count"] == 1

    async with SessionLocal() as session:
        pools = (
            await session.execute(
                select(FbsBindingStockPool.quantity).where(
                    FbsBindingStockPool.product_id == uuid.UUID(product_with_pools_id)
                )
            )
        ).scalars().all()
        assert list(pools) == [0, 0]


@pytest.mark.asyncio
async def test_apply_from_balance_does_not_touch_other_tenant_product(
    async_client: AsyncClient,
) -> None:
    """Товар чужого тенанта не находится этим селлером и не меняется."""
    ctx_a = await _register_tenant_with_seller(async_client)
    ctx_b = await _register_tenant_with_seller(async_client)

    admin_headers_b = ctx_b["admin_headers"]
    suffix_b = str(ctx_b["suffix"])
    _warehouse_b, location_b = await _create_warehouse_with_location(
        async_client, admin_headers_b, suffix_b
    )
    product_b_id = await _create_product(
        async_client, admin_headers_b, str(ctx_b["seller_id"]), suffix_b
    )

    async with SessionLocal() as session:
        product_b = await session.get(Product, uuid.UUID(product_b_id))
        assert product_b is not None
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=product_b.tenant_id,
            product_id=product_b.id,
            storage_location_id=uuid.UUID(location_b),
            quantity_delta=9,
            movement_type="inbound_intake",
        )
        await session.commit()

    resp = await async_client.patch(
        "/products/fbs-stock-limit/from-balance/bulk",
        headers=ctx_a["seller_headers"],
        json={"product_ids": [product_b_id]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["updated_count"] == 0
    assert body["updated"] == []
    assert body["skipped"] == [{"product_id": product_b_id, "reason": "not_found"}]
    assert body["pool_reset_products_count"] == 0

    async with SessionLocal() as session:
        product_b_after = await session.get(Product, uuid.UUID(product_b_id))
        assert product_b_after is not None
        assert product_b_after.fbs_stock_limit is None


@pytest.mark.asyncio
async def test_apply_from_balance_sums_across_warehouses(async_client: AsyncClient) -> None:
    """Остаток по нескольким складам тенанта складывается в один пул."""
    ctx = await _register_tenant_with_seller(async_client)
    admin_headers = ctx["admin_headers"]
    seller_headers = ctx["seller_headers"]
    seller_id = str(ctx["seller_id"])
    suffix = str(ctx["suffix"])

    _wh_1, location_1 = await _create_warehouse_with_location(
        async_client, admin_headers, f"{suffix}-1"
    )
    _wh_2, location_2 = await _create_warehouse_with_location(
        async_client, admin_headers, f"{suffix}-2"
    )
    product_id = await _create_product(async_client, admin_headers, seller_id, suffix)

    async with SessionLocal() as session:
        product = await session.get(Product, uuid.UUID(product_id))
        assert product is not None
        tenant_id = product.tenant_id
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product.id,
            storage_location_id=uuid.UUID(location_1),
            quantity_delta=4,
            movement_type="inbound_intake",
        )
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product.id,
            storage_location_id=uuid.UUID(location_2),
            quantity_delta=6,
            movement_type="inbound_intake",
        )
        await session.commit()

    resp = await async_client.patch(
        "/products/fbs-stock-limit/from-balance/bulk",
        headers=seller_headers,
        json={"product_ids": [product_id]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["updated"] == [
        {"product_id": product_id, "fbs_stock_limit": 10, "reset_warehouses_count": 0}
    ]


@pytest.mark.asyncio
async def test_apply_from_balance_rejects_empty_product_ids(async_client: AsyncClient) -> None:
    """Пустой список product_ids — понятная ошибка, а не 500."""
    ctx = await _register_tenant_with_seller(async_client)
    resp = await async_client.patch(
        "/products/fbs-stock-limit/from-balance/bulk",
        headers=ctx["seller_headers"],
        json={"product_ids": []},
    )
    assert resp.status_code == 422, resp.text
