"""WMS-363/401: marketplace filtering, Ozon positions and oldest pagination.

Exercises public HTTP responses in isolated tenants. The mobile client uses
/worklist; the legacy list retains its default of returning both marketplaces.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_NEW,
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
)
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_SOURCE_WMS,
    FBS_SUPPLY_STATUS_DRAFT,
    FbsSupply,
)
from app.services.tokens import decode_access_token


async def _register_ff_admin(async_client: AsyncClient) -> tuple[dict[str, str], str, uuid.UUID]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"WMS-363 {suffix}",
            "slug": f"wms363-{suffix}",
            "admin_email": f"wms363-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = reg.json()["access_token"]
    tenant_id = uuid.UUID(str(decode_access_token(token)["tenant_id"]))
    headers = {"Authorization": f"Bearer {token}"}
    return headers, suffix, tenant_id


async def _create_seller_and_warehouse(
    async_client: AsyncClient, headers: dict[str, str], suffix: str
) -> tuple[uuid.UUID, uuid.UUID]:
    seller = await async_client.post("/sellers", headers=headers, json={"name": f"Seller {suffix}"})
    assert seller.status_code in (200, 201), seller.text
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WH", "code": f"wh-{suffix[-8:]}"},
    )
    assert warehouse.status_code in (200, 201), warehouse.text
    return uuid.UUID(seller.json()["id"]), uuid.UUID(warehouse.json()["id"])


async def _seed_order(
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    marketplace: str,
    wb_order_id: int,
    external_order_id: str | None = None,
) -> uuid.UUID:
    now = datetime.now(UTC)
    order = FbsOrder(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        marketplace=marketplace,
        external_order_id=external_order_id,
        wb_order_id=wb_order_id,
        wb_rid=f"rid-{wb_order_id}",
        wb_nm_id=900000 + wb_order_id,
        wb_chrt_id=555,
        wb_article="ART-TSD",
        wb_barcode=f"BC-{wb_order_id}",
        price=199900,
        is_legal=False,
        cargo_type="1",
        wb_office_id=42,
        wb_warehouse_id=501001,
        can_pvz=False,
        status=FBS_ORDER_STATUS_NEW,
        created_at_wb=now - timedelta(hours=1),
        deadline_at=now + timedelta(hours=24),
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_RESERVED,
    )
    async with SessionLocal() as session:
        session.add(order)
        await session.commit()
    return order.id


async def _seed_supply(
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    marketplace: str,
    name: str,
) -> uuid.UUID:
    supply = FbsSupply(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        marketplace=marketplace,
        source=FBS_SUPPLY_SOURCE_WMS,
        name=name,
        status=FBS_SUPPLY_STATUS_DRAFT,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    )
    async with SessionLocal() as session:
        session.add(supply)
        await session.commit()
    return supply.id


async def _seed_wb_and_ozon(
    async_client: AsyncClient,
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Общий сетап: один WB-заказ и один Ozon-заказ у одного селлера."""
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _create_seller_and_warehouse(async_client, headers, suffix)
    wb_id = await _seed_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        marketplace="wb",
        wb_order_id=770001,
    )
    ozon_id = await _seed_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        marketplace="ozon",
        wb_order_id=770002,
        external_order_id="OZ-770002",
    )
    return headers, tenant_id, seller_id, wb_id, ozon_id


# TC-WMS-363-001
@pytest.mark.asyncio
async def test_get_fbs_orders_without_marketplace_returns_both(
    async_client: AsyncClient,
) -> None:
    """Обратная совместимость: без параметра TSD получает и WB, и Ozon."""
    headers, _tenant, _seller, wb_id, ozon_id = await _seed_wb_and_ozon(async_client)

    resp = await async_client.get("/operations/fbs-orders", headers=headers)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    ids = {row["id"] for row in rows}
    assert ids == {str(wb_id), str(ozon_id)}
    markets = {row["id"]: row["marketplace"] for row in rows}
    assert markets[str(wb_id)] == "wb"
    assert markets[str(ozon_id)] == "ozon"


# TC-WMS-363-002
@pytest.mark.asyncio
async def test_get_fbs_orders_marketplace_ozon_filter(async_client: AsyncClient) -> None:
    """`?marketplace=ozon` возвращает только Ozon-заказы."""
    headers, _tenant, _seller, _wb_id, ozon_id = await _seed_wb_and_ozon(async_client)

    resp = await async_client.get("/operations/fbs-orders?marketplace=ozon", headers=headers)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert [row["id"] for row in rows] == [str(ozon_id)]
    assert rows[0]["marketplace"] == "ozon"
    assert rows[0]["external_order_id"] == "OZ-770002"


# TC-WMS-363-003
@pytest.mark.asyncio
async def test_get_fbs_orders_marketplace_wb_filter(async_client: AsyncClient) -> None:
    """`?marketplace=wb` возвращает только WB-заказы (симметрия к Ozon)."""
    headers, _tenant, _seller, wb_id, _ozon_id = await _seed_wb_and_ozon(async_client)

    resp = await async_client.get("/operations/fbs-orders?marketplace=wb", headers=headers)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert [row["id"] for row in rows] == [str(wb_id)]
    assert rows[0]["marketplace"] == "wb"


# TC-WMS-363-004
@pytest.mark.asyncio
async def test_get_fbs_orders_marketplace_unknown_422(async_client: AsyncClient) -> None:
    """Незнакомый маркетплейс отсекается на входе (Query pattern), а не в рантайме."""
    headers, _tenant, _seller, _wb_id, _ozon_id = await _seed_wb_and_ozon(async_client)

    resp = await async_client.get("/operations/fbs-orders?marketplace=amazon", headers=headers)
    assert resp.status_code == 422, resp.text


# TC-WMS-363-005
@pytest.mark.asyncio
async def test_get_fbs_supplies_worklist_ozon_filter(async_client: AsyncClient) -> None:
    """`fbs-supplies/worklist?marketplace=ozon` возвращает только Ozon-поставки."""
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _create_seller_and_warehouse(async_client, headers, suffix)
    wb_supply = await _seed_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        marketplace="wb",
        name="WB supply",
    )
    ozon_supply = await _seed_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        marketplace="ozon",
        name="Ozon supply",
    )

    both = await async_client.get(
        "/operations/fbs-supplies/worklist?status_group=active", headers=headers
    )
    assert both.status_code == 200, both.text
    both_ids = {item["id"] for item in both.json()["items"]}
    assert both_ids == {str(wb_supply), str(ozon_supply)}

    ozon_only = await async_client.get(
        "/operations/fbs-supplies/worklist?status_group=active&marketplace=ozon",
        headers=headers,
    )
    assert ozon_only.status_code == 200, ozon_only.text
    ozon_items = ozon_only.json()["items"]
    assert [item["id"] for item in ozon_items] == [str(ozon_supply)]
    assert ozon_items[0]["marketplace"] == "ozon"


def _assert_response_marketplace_literal_enforced(payload: dict[str, Any]) -> None:
    """Response models объявлены `Literal["wb","ozon"]` — конкретных значений всего два."""
    assert payload["marketplace"] in ("wb", "ozon")


# TC-WMS-363-006
@pytest.mark.asyncio
async def test_response_marketplace_field_uses_literal(async_client: AsyncClient) -> None:
    """Response-схема ограничена Literal — ответы возвращают только "wb"/"ozon"."""
    headers, _tenant, _seller, _wb_id, _ozon_id = await _seed_wb_and_ozon(async_client)

    resp = await async_client.get("/operations/fbs-orders", headers=headers)
    assert resp.status_code == 200, resp.text
    for row in resp.json():
        _assert_response_marketplace_literal_enforced(row)


@pytest.mark.asyncio
async def test_mobile_worklist_oldest_paginates_before_deadline_and_scopes_tenant(
    async_client: AsyncClient,
) -> None:
    from app.models.fbs_order import FbsOrderProduct
    from app.models.product import Product
    from app.models.product_marketplace_link import ProductMarketplaceLink

    headers, tenant, seller, _, ozon_id = await _seed_wb_and_ozon(async_client)
    # Another tenant's otherwise matching posting must not appear.
    _, _, _, _, foreign_id = await _seed_wb_and_ozon(async_client)
    async with SessionLocal() as session:
        first = await session.get(FbsOrder, ozon_id)
        assert first is not None and first.warehouse_id is not None
        warehouse = first.warehouse_id
        first.created_at_wb = datetime.now(UTC) - timedelta(days=2)
        first.deadline_at = datetime.now(UTC) + timedelta(days=2)
        product = Product(
            tenant_id=tenant,
            seller_id=seller,
            name="Second position",
            sku_code="363-POS",
            wb_barcode="363-WB-ONLY",
        )
        session.add(product)
        await session.flush()
        session.add(ProductMarketplaceLink(
            tenant_id=tenant, seller_id=seller, product_id=product.id,
            marketplace="ozon", external_sku="363",
            external_barcodes=["363-OZON-BARCODE"],
        ))
        position = FbsOrderProduct(
            order_id=first.id,
            product_id=product.id,
            position_index=0,
            quantity=3,
            picked_quantity=1,
            ozon_sku=363,
        )
        session.add(position)
        await session.commit()
        position_id = position.id
    second = await _seed_order(
        tenant_id=tenant,
        seller_id=seller,
        warehouse_id=warehouse,
        marketplace="ozon",
        wb_order_id=770003,
    )
    params = {"marketplace": "ozon", "sort": "oldest", "limit": 1}
    url = "/operations/fbs-orders/worklist"
    page = await async_client.get(url, headers=headers, params=params)
    assert page.status_code == 200, page.text
    item = page.json()["items"][0]
    assert item["id"] == str(ozon_id)
    assert item["marketplace"] == "ozon" and item["external_order_id"] == "OZ-770002"
    assert item["positions"][0]["id"] == str(position_id)
    assert item["positions"][0]["barcode"] == "363-OZON-BARCODE"
    assert item["positions"][0]["quantity"] == 3
    cursor = page.json()["next_cursor"]
    tail = await async_client.get(url, headers=headers, params={**params, "cursor": cursor})
    assert tail.status_code == 200, tail.text
    assert [row["id"] for row in tail.json()["items"]] == [str(second)]
    assert str(foreign_id) not in str(page.json()) + str(tail.json())
    wrong_sort = await async_client.get(
        url, headers=headers, params={**params, "sort": "deadline", "cursor": cursor}
    )
    assert wrong_sort.status_code == 400
    default = await async_client.get(
        url, headers=headers, params={"marketplace": "ozon", "limit": 1}
    )
    assert default.json()["items"][0]["id"] == str(second)


@pytest.mark.asyncio
async def test_mobile_worklist_rejects_non_object_cursor(async_client: AsyncClient) -> None:
    import base64
    headers, *_ = await _seed_wb_and_ozon(async_client)
    response = await async_client.get(
        "/operations/fbs-orders/worklist", headers=headers,
        params={"sort": "oldest", "cursor": base64.urlsafe_b64encode(b"[]").decode()},
    )
    assert response.status_code == 400
