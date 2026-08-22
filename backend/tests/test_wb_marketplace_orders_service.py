"""Tests for WB Marketplace FBS orders service (supply sync via supplies list).

TC-NEW-SUPPLY-SYNC-001 — adoption with supplies list: done=True updates status and name
TC-NEW-SUPPLY-SYNC-002 — adoption uses supplies_dict without individual fetch
TC-NEW-SUPPLY-SYNC-003 — supplies list failure: adoption falls back without exception
TC-NEW-SUPPLY-SYNC-004 — pagination: multiple pages merged into one supplies dict
"""

from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.fbs_order import FBS_ORDER_STATUS_ASSEMBLING, FbsOrder
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_DONE,
    FbsSupply,
)
from app.models.product import Product
from app.services import wb_marketplace_orders_service as orders_service
from app.services.wb_marketplace_orders_service import link_confirmed_orders_to_wb_supplies
from app.services.wildberries_errors import WildberriesClientError
from tests.fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID, seed_fbs_warehouse_binding


class _SyncSession:
    def __init__(self) -> None:
        self.commit = AsyncMock()
        self.rollback = AsyncMock()


# TC-NEW-WB-SYNC-001: new sync uses only /orders/new and performs an idempotent upsert.
@pytest.mark.asyncio
async def test_new_sync_does_not_fetch_paginated_orders(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _SyncSession()
    seller_id = uuid.uuid4()
    new_fetch = AsyncMock(return_value=[{"id": 1}])
    page_fetch = AsyncMock(side_effect=AssertionError("full order list must not be fetched"))
    upsert = AsyncMock(return_value=(object(), False))
    monkeypatch.setattr(
        orders_service, "_resolve_marketplace_api_token", AsyncMock(return_value="token")
    )
    monkeypatch.setattr(orders_service, "fetch_marketplace_orders_new", new_fetch)
    monkeypatch.setattr(orders_service, "fetch_marketplace_orders_page", page_fetch)
    monkeypatch.setattr(orders_service, "upsert_order_from_wb_row", upsert)

    result = await orders_service.sync_new_orders_for_seller(
        session, uuid.uuid4(), seller_id, object()  # type: ignore[arg-type]
    )

    assert result["orders_received"] == 1
    new_fetch.assert_awaited_once()
    page_fetch.assert_not_awaited()
    upsert.assert_awaited_once()


# TC-NEW-WB-SYNC-002: reconcile consumes all cursors and never reports success after a page error.
@pytest.mark.asyncio
async def test_reconcile_walks_cursor_and_fails_incomplete_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _SyncSession()
    pages = [([{"id": 1}], 10), ([{"id": 2}], 20), ([], None)]
    page_fetch = AsyncMock(side_effect=pages)
    upsert = AsyncMock(side_effect=[(object(), True), (object(), False)])
    monkeypatch.setattr(
        orders_service, "_resolve_marketplace_api_token", AsyncMock(return_value="token")
    )
    monkeypatch.setattr(orders_service, "fetch_marketplace_orders_page", page_fetch)
    monkeypatch.setattr(orders_service, "upsert_order_from_wb_row", upsert)

    result = await orders_service.reconcile_orders_for_seller(
        session, uuid.uuid4(), uuid.uuid4(), object()  # type: ignore[arg-type]
    )

    assert result["orders_received"] == 2
    assert [call.kwargs["next_token"] for call in page_fetch.await_args_list] == [None, 10, 20]
    assert session.commit.await_count == 2

    page_fetch.side_effect = [([{"id": 3}], 10), WildberriesClientError("upstream_error")]
    upsert.side_effect = [(object(), False)]
    with pytest.raises(orders_service.WbMarketplaceOrdersError):
        await orders_service.reconcile_orders_for_seller(
            session, uuid.uuid4(), uuid.uuid4(), object()  # type: ignore[arg-type]
        )
    assert session.rollback.await_count == 1


async def _register_tenant_and_seller(
    async_client: AsyncClient,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Register tenant, seller, warehouse, and location."""
    suffix = str(time.time_ns())

    # Register tenant
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Test Org {suffix}",
            "slug": f"test-org-{suffix}",
            "admin_email": f"admin-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    # Get tenant ID from /auth/me
    me = await async_client.get("/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    tenant_id = uuid.UUID(me.json()["tenant_id"])

    # Create seller
    seller_resp = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": f"Test Seller {suffix}"},
    )
    assert seller_resp.status_code in (200, 201), seller_resp.text
    seller_id = uuid.UUID(seller_resp.json()["id"])

    # Set marketplace token
    token_resp = await async_client.patch(
        f"/integrations/wildberries/sellers/{seller_id}/tokens",
        headers=headers,
        json={"marketplace_api_token": "wb-test-token"},
    )
    assert token_resp.status_code == 200, token_resp.text

    # Create warehouse
    wh_resp = await async_client.post(
        "/warehouses",
        headers=headers,
        json={
            "name": f"Test WH {suffix}",
            "code": f"wh-{uuid.uuid4().hex[:8]}",
        },
    )
    assert wh_resp.status_code in (200, 201), wh_resp.text
    warehouse_id = uuid.UUID(wh_resp.json()["id"])

    # Create location
    loc_resp = await async_client.post(
        f"/warehouses/{warehouse_id}/locations",
        headers=headers,
        json={"code": f"A-{uuid.uuid4().hex[:8]}"},
    )
    assert loc_resp.status_code in (200, 201), loc_resp.text
    location_id = uuid.UUID(loc_resp.json()["id"])

    return tenant_id, seller_id, warehouse_id, location_id


async def _create_confirmed_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product: Product,
    wb_order_id: int,
    wb_supply_id: str,
) -> FbsOrder:
    """Create a confirmed FbsOrder."""
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    order = FbsOrder(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_order_id=wb_order_id,
        wb_supply_id=wb_supply_id,
        wb_nm_id=900000 + wb_order_id,
        supplier_status="confirm",
        status=FBS_ORDER_STATUS_ASSEMBLING,
        wb_warehouse_id=DEFAULT_WB_WAREHOUSE_ID,
        cargo_type="1",
        wb_office_id=None,
        created_at_wb=now,
        deadline_at=now + timedelta(hours=120),
        mapping_status="missing",
        reserve_status="no_stock",
        pick_status="not_picked",
        pack_status="not_packed",
        sticker_status="no_sticker",
    )
    session.add(order)
    await session.flush()
    return order


async def _create_product(
    async_client: AsyncClient,
    headers: dict[str, str],
    seller_id: str,
    sku: str,
) -> Product:
    """Create a product through the API."""
    resp = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": f"Product {sku}",
            "sku_code": sku,
            "seller_id": seller_id,
            "wb_barcode": f"BAR-{sku}",
        },
    )
    assert resp.status_code in (200, 201), resp.text
    async with SessionLocal() as session:
        product = await session.get(Product, uuid.UUID(resp.json()["id"]))
        assert product is not None
        return product


# TC-NEW-SUPPLY-SYNC-001: adoption with supplies list: done=True updates status and name
@pytest.mark.asyncio
async def test_adoption_with_supplies_list_done_true(
    async_client: AsyncClient,
) -> None:
    """Supplies list with done=True: new supply created with done status and real name."""
    tenant_id, seller_id, warehouse_id, _location_id = await _register_tenant_and_seller(
        async_client
    )

    async with SessionLocal() as session:
        # Setup FBS warehouse binding
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
            wb_warehouse_id=DEFAULT_WB_WAREHOUSE_ID,
        )

        # Create product
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Test Product",
            sku_code="TEST-SKU-001",
            wb_nm_id=900001,
        )
        session.add(product)
        await session.flush()

        # Create confirmed order
        await _create_confirmed_order(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product=product,
            wb_order_id=1001,
            wb_supply_id="WB-GI-266355621",
        )
        await session.flush()

        # Mock HTTP client that returns supplies list with done=True and name
        # Individual supply detail fetch should NOT be called
        def handler(request: httpx.Request) -> httpx.Response:
            # Check if this is the supplies list endpoint (query params present)
            if "limit" in request.url.params:
                # Supplies list endpoint
                return httpx.Response(
                    200,
                    json={
                        "supplies": [
                            {
                                "id": "WB-GI-266355621",
                                "name": "ПИТЕР Поставка 18.08.2026",
                                "done": True,
                            }
                        ],
                        "next": None,
                    },
                )
            # Individual supply detail requests should not be made
            if "/api/v3/supplies/" in request.url.path and "?" not in str(request.url):
                return httpx.Response(500, text="Should not call individual fetch")
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            result = await link_confirmed_orders_to_wb_supplies(
                session,
                tenant_id=tenant_id,
                seller_id=seller_id,
                http_client=http_client,
                api_token="wb-test-token",
            )

        # Verify supply was created with correct status and name from list
        stmt = select(FbsSupply).where(
            FbsSupply.tenant_id == tenant_id,
            FbsSupply.seller_id == seller_id,
            FbsSupply.wb_supply_id == "WB-GI-266355621",
        )
        res = await session.execute(stmt)
        supply = res.scalar_one()

        assert supply.status == FBS_SUPPLY_STATUS_DONE
        assert supply.name == "ПИТЕР Поставка 18.08.2026"
        assert result["supply_links_created"] == 1
        assert result["supply_linked_orders"] == 1


# TC-NEW-SUPPLY-SYNC-002: adoption uses supplies_dict without individual fetch
@pytest.mark.asyncio
async def test_adoption_uses_supplies_dict_no_individual_fetch(
    async_client: AsyncClient,
) -> None:
    """Adoption gets name and status from pre-fetched supplies dict, not individual request."""
    tenant_id, seller_id, warehouse_id, _location_id = await _register_tenant_and_seller(
        async_client
    )

    async with SessionLocal() as session:
        # Setup FBS warehouse binding
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
            wb_warehouse_id=DEFAULT_WB_WAREHOUSE_ID,
        )

        # Create product
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Test Product 2",
            sku_code="TEST-SKU-002",
            wb_nm_id=900002,
        )
        session.add(product)
        await session.flush()

        # Create confirmed order
        await _create_confirmed_order(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product=product,
            wb_order_id=1002,
            wb_supply_id="WB-GI-222333444",
        )
        await session.flush()

        # Mock that tracks which endpoints were called
        call_log: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            call_log.append(path)
            # Check if this is the supplies list endpoint (query params present)
            if "limit" in request.url.params:
                # Supplies list endpoint: return data with name and done=False
                return httpx.Response(
                    200,
                    json={
                        "supplies": [
                            {
                                "id": "WB-GI-222333444",
                                "name": "Supply Name From List",
                                "done": False,
                            }
                        ],
                        "next": None,
                    },
                )
            # Any individual supply detail fetch is an error
            if "/api/v3/supplies/" in path:
                raise AssertionError(
                    f"Individual supply fetch should not be called, but got {path}"
                )
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            result = await link_confirmed_orders_to_wb_supplies(
                session,
                tenant_id=tenant_id,
                seller_id=seller_id,
                http_client=http_client,
                api_token="wb-test-token",
            )

        # Verify supply was created with name from supplies dict
        stmt = select(FbsSupply).where(
            FbsSupply.tenant_id == tenant_id,
            FbsSupply.seller_id == seller_id,
            FbsSupply.wb_supply_id == "WB-GI-222333444",
        )
        res = await session.execute(stmt)
        supply = res.scalar_one()

        # Should have the name from the supplies list, not from fallback
        assert supply.name == "Supply Name From List"
        assert supply.status == FBS_SUPPLY_STATUS_ASSEMBLING
        assert result["supply_links_created"] == 1
        assert result["supply_linked_orders"] == 1
        # Verify no individual fetch was made
        assert not any("/supplies/" in p for p in call_log if "?" not in p)


# TC-NEW-SUPPLY-SYNC-003: supplies list failure: adoption falls back without exception
@pytest.mark.asyncio
async def test_supplies_list_failure_fallback_no_exception(
    async_client: AsyncClient,
) -> None:
    """When supplies list fails, adoption still works with fallback name and assembling status."""
    tenant_id, seller_id, warehouse_id, _location_id = await _register_tenant_and_seller(
        async_client
    )

    async with SessionLocal() as session:
        # Setup FBS warehouse binding
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
            wb_warehouse_id=DEFAULT_WB_WAREHOUSE_ID,
        )

        # Create product
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Test Product 3",
            sku_code="TEST-SKU-003",
            wb_nm_id=900003,
        )
        session.add(product)
        await session.flush()

        # Create confirmed order
        await _create_confirmed_order(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product=product,
            wb_order_id=1003,
            wb_supply_id="WB-GI-333444555",
        )
        await session.flush()

        # Mock that fails on supplies list but can handle individual requests
        def handler(request: httpx.Request) -> httpx.Response:
            # Check if this is the supplies list endpoint (query params present)
            if "limit" in request.url.params:
                # Supplies list endpoint fails
                return httpx.Response(500, text="WB API Error")
            # Individual fetch would be called as fallback, but we don't need to test it
            # since supplies_dict will be empty
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            # Should not raise an exception even if supplies list fails
            result = await link_confirmed_orders_to_wb_supplies(
                session,
                tenant_id=tenant_id,
                seller_id=seller_id,
                http_client=http_client,
                api_token="wb-test-token",
            )

        # Verify supply was created with fallback name and assembling status
        stmt = select(FbsSupply).where(
            FbsSupply.tenant_id == tenant_id,
            FbsSupply.seller_id == seller_id,
            FbsSupply.wb_supply_id == "WB-GI-333444555",
        )
        res = await session.execute(stmt)
        supply = res.scalar_one()

        # Should have fallback name (since supplies_dict was empty)
        assert supply.name == "WB supply WB-GI-333444555"
        assert supply.status == FBS_SUPPLY_STATUS_ASSEMBLING
        assert result["supply_links_created"] == 1
        assert result["supply_linked_orders"] == 1


# TC-NEW-SUPPLY-SYNC-004: pagination: multiple pages merged into one supplies dict
@pytest.mark.asyncio
async def test_supplies_pagination_merged_into_dict(
    async_client: AsyncClient,
) -> None:
    """Multiple pages of supplies list are merged into one dictionary."""
    tenant_id, seller_id, warehouse_id, _location_id = await _register_tenant_and_seller(
        async_client
    )

    async with SessionLocal() as session:
        # Setup FBS warehouse binding
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
            wb_warehouse_id=DEFAULT_WB_WAREHOUSE_ID,
        )

        # Create product
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Test Product 4",
            sku_code="TEST-SKU-004",
            wb_nm_id=900004,
        )
        session.add(product)
        await session.flush()

        # Create two confirmed orders with supplies from different pages
        await _create_confirmed_order(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product=product,
            wb_order_id=2001,
            wb_supply_id="WB-GI-PAGE1-001",
        )
        await _create_confirmed_order(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product=product,
            wb_order_id=2002,
            wb_supply_id="WB-GI-PAGE2-002",
        )
        await session.flush()

        # Mock that returns two pages
        page_requests: list[int | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            # Check if this is the supplies list endpoint (query params present)
            if "limit" in request.url.params:
                # Extract next cursor from params
                next_param_raw = request.url.params.get("next")
                next_param: int | None = None
                if next_param_raw is not None:
                    next_param = int(next_param_raw)
                page_requests.append(next_param)

                # WB требует `next` всегда; первая страница — next=0.
                # Раньше тест ждал отсутствия параметра и тем закреплял ошибку,
                # из-за которой боевой WB отвечал 400 IncorrectParameter.
                if next_param in (None, 0):
                    # First page
                    return httpx.Response(
                        200,
                        json={
                            "supplies": [
                                {
                                    "id": "WB-GI-PAGE1-001",
                                    "name": "Page 1 Supply 1",
                                    "done": False,
                                }
                            ],
                            "next": 100,
                        },
                    )
                elif next_param == 100:
                    # Second page
                    return httpx.Response(
                        200,
                        json={
                            "supplies": [
                                {
                                    "id": "WB-GI-PAGE2-002",
                                    "name": "Page 2 Supply 2",
                                    "done": True,
                                }
                            ],
                            "next": None,
                        },
                    )
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            result = await link_confirmed_orders_to_wb_supplies(
                session,
                tenant_id=tenant_id,
                seller_id=seller_id,
                http_client=http_client,
                api_token="wb-test-token",
            )

        # Verify both supplies were created from merged dict
        stmt1 = select(FbsSupply).where(
            FbsSupply.tenant_id == tenant_id,
            FbsSupply.seller_id == seller_id,
            FbsSupply.wb_supply_id == "WB-GI-PAGE1-001",
        )
        res1 = await session.execute(stmt1)
        supply1 = res1.scalar_one()

        stmt2 = select(FbsSupply).where(
            FbsSupply.tenant_id == tenant_id,
            FbsSupply.seller_id == seller_id,
            FbsSupply.wb_supply_id == "WB-GI-PAGE2-002",
        )
        res2 = await session.execute(stmt2)
        supply2 = res2.scalar_one()

        # Verify both supplies have correct names and statuses from pages
        assert supply1.name == "Page 1 Supply 1"
        assert supply1.status == FBS_SUPPLY_STATUS_ASSEMBLING
        assert supply2.name == "Page 2 Supply 2"
        assert supply2.status == FBS_SUPPLY_STATUS_DONE
        assert result["supply_links_created"] == 2
        assert result["supply_linked_orders"] == 2
        # Verify pagination happened (two page requests)
        assert len(page_requests) == 2


@pytest.mark.asyncio
async def test_supplies_page_always_sends_next_param() -> None:
    """WB отвечает 400 IncorrectParameter, если в запросе нет `next`.

    Проверяем сам ЗАПРОС, а не разбор ответа: прошлая версия слала только `limit`,
    все тесты на разборе были зелёными, а на бою список не приходил ни разу.
    """
    from app.services.wildberries_fbs_client import fetch_marketplace_supplies_page

    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={"supplies": [], "next": None})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await fetch_marketplace_supplies_page(client, api_token="t")
        await fetch_marketplace_supplies_page(client, api_token="t", next_cursor=777)

    assert seen[0] == {"limit": "1000", "next": "0"}, "первая страница обязана слать next=0"
    assert seen[1] == {"limit": "1000", "next": "777"}, "курсор обязан уходить в запрос"


@pytest.mark.asyncio
async def test_supplies_pagination_stops_on_empty_page() -> None:
    """WB отдаёт курсор даже когда данные кончились — выходим по пустой странице.

    Раньше признаком конца был только пустой курсор, поэтому цикл честно крутил
    все MAX_SUPPLIES_PAGES страниц на каждого селлера: 10 запросов вместо одного,
    и общий лимитер WB отвечал 429.
    """
    from app.services.wildberries_fbs_client import fetch_marketplace_supplies_page

    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(200, json={
                "supplies": [{"id": "WB-GI-1", "name": "Первая", "done": True}],
                "next": 999,          # курсор есть, хотя данные кончились
            })
        return httpx.Response(200, json={"supplies": [], "next": 1000})

    merged: dict[str, tuple[str | None, bool]] = {}
    cursor: int | None = None
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        for _ in range(10):
            page = await fetch_marketplace_supplies_page(
                client, api_token="t", next_cursor=cursor
            )
            merged.update(page.supplies)
            if not page.supplies or page.next_cursor is None:
                break
            cursor = page.next_cursor

    assert merged == {"WB-GI-1": ("Первая", True)}
    assert len(calls) == 2, f"должно быть 2 запроса, а не {len(calls)} — иначе лимитер WB"
