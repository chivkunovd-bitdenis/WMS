"""TC-NEW-FBS-CANCEL-PACK — cancelled orders must stop before warehouse work."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_CANCELLED,
    MAPPING_STATUS_MAPPED,
    PACK_STATUS_PACKED,
    RESERVE_STATUS_RELEASED,
    STICKER_STATUS_PRINT_OPENED,
    FbsOrder,
)
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_DRAFT,
    FbsSupply,
)
from app.models.product import Product
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
)


async def _seed_cancelled_order(
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    wb_order_id: int,
    cancelled_at: datetime,
    assembled: bool,
    supply: FbsSupply,
) -> uuid.UUID:
    async with SessionLocal() as session:
        order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            wb_order_id=wb_order_id,
            wb_article="6020-4R/31",
            wb_barcode=f"BAR-{wb_order_id}",
            wb_supply_id=supply.wb_supply_id,
            status=FBS_ORDER_STATUS_CANCELLED,
            wb_status="waiting",
            supplier_status="canceled_by_client",
            created_at_wb=cancelled_at - timedelta(days=1),
            deadline_at=cancelled_at + timedelta(days=1),
            mapping_status=MAPPING_STATUS_MAPPED,
            reserve_status=RESERVE_STATUS_RELEASED,
            picked_at=cancelled_at - timedelta(hours=2) if assembled else None,
            packed_at=cancelled_at - timedelta(hours=1) if assembled else None,
            pack_status=PACK_STATUS_PACKED if assembled else "pending",
            sticker_status=STICKER_STATUS_PRINT_OPENED if assembled else "not_requested",
            updated_at=cancelled_at,
        )
        session.add(order)
        await session.commit()
        return order.id


async def _seed_list_scope(
    async_client: AsyncClient,
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, FbsSupply]:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, _location_id = await _create_seller_and_warehouse(
        async_client,
        headers,
        suffix,
        seller_name="ИП Чжоу",
    )
    product_id = await _create_product(
        async_client,
        headers,
        seller_id,
        sku="6020-4R/31",
        barcode=f"CANCEL-LIST-{suffix[-8:]}",
        name="Туфли",
    )
    async with SessionLocal() as session:
        supply = FbsSupply(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            wb_supply_id=f"WB-GI-{suffix[-9:]}",
            name="Отгрузка WB",
            status=FBS_SUPPLY_STATUS_DRAFT,
            delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        )
        session.add(supply)
        await session.commit()
        await session.refresh(supply)
        session.expunge(supply)
    return headers, tenant_id, seller_id, warehouse_id, product_id, supply


# TC-NEW-FBS-CANCEL-PACK-001 — only cancellation after a physical assembly trace is actionable.
@pytest.mark.asyncio
async def test_cancelled_after_pack_includes_after_assembly_and_excludes_before(
    async_client: AsyncClient,
) -> None:
    headers, tenant_id, seller_id, warehouse_id, product_id, supply = await _seed_list_scope(
        async_client
    )
    cancelled_at = datetime.now(UTC) - timedelta(minutes=5)
    included_id = await _seed_cancelled_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        product_id=product_id,
        wb_order_id=5590698457,
        cancelled_at=cancelled_at,
        assembled=True,
        supply=supply,
    )
    await _seed_cancelled_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        product_id=product_id,
        wb_order_id=5590698458,
        cancelled_at=cancelled_at + timedelta(minutes=1),
        assembled=False,
        supply=supply,
    )

    response = await async_client.get("/fbs/cancelled-after-pack", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert [item["order_id"] for item in body["items"]] == [str(included_id)]
    item = body["items"][0]
    assert item["wb_order_id"] == 5590698457
    assert item["product"]["article"] == "6020-4R/31"
    assert item["seller"]["name"] == "ИП Чжоу"
    assert item["supply"]["wb_supply_id"] == supply.wb_supply_id
    assert item["cancellation_reason"] == "Заказ отменён покупателем"
    assert item["sticker_printed"] is True
    assert item["supply_departed"] is False

    by_supply = await async_client.get(
        "/fbs/cancelled-after-pack",
        headers=headers,
        params={"supply_id": str(supply.id)},
    )
    assert by_supply.status_code == 200, by_supply.text
    assert [row["order_id"] for row in by_supply.json()["items"]] == [str(included_id)]


# TC-NEW-FBS-CANCEL-PACK-002 — tenant and seller boundaries plus cancellation-period filtering.
@pytest.mark.asyncio
async def test_cancelled_after_pack_is_tenant_scoped_and_filters_seller_period(
    async_client: AsyncClient,
) -> None:
    headers_a, tenant_a, seller_a, warehouse_a, product_a, supply_a = await _seed_list_scope(
        async_client
    )
    now = datetime.now(UTC)
    recent_a = await _seed_cancelled_order(
        tenant_id=tenant_a,
        seller_id=seller_a,
        warehouse_id=warehouse_a,
        product_id=product_a,
        wb_order_id=5590698460,
        cancelled_at=now - timedelta(hours=1),
        assembled=True,
        supply=supply_a,
    )

    suffix = str(time.time_ns())
    seller_response = await async_client.post(
        "/sellers", headers=headers_a, json={"name": f"Loviana {suffix}"}
    )
    assert seller_response.status_code in (200, 201), seller_response.text
    seller_other = uuid.UUID(seller_response.json()["id"])
    async with SessionLocal() as session:
        product_other = Product(
            tenant_id=tenant_a,
            seller_id=seller_other,
            name="Other",
            sku_code=f"OTHER-{suffix}",
        )
        supply_other = FbsSupply(
            tenant_id=tenant_a,
            seller_id=seller_other,
            warehouse_id=warehouse_a,
            wb_supply_id=f"WB-OTHER-{suffix[-8:]}",
            name="Other supply",
            status=FBS_SUPPLY_STATUS_DRAFT,
            delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        )
        session.add_all([product_other, supply_other])
        await session.commit()
        await session.refresh(product_other)
        await session.refresh(supply_other)
        session.expunge(supply_other)
        other_product_id = product_other.id
    await _seed_cancelled_order(
        tenant_id=tenant_a,
        seller_id=seller_other,
        warehouse_id=warehouse_a,
        product_id=other_product_id,
        wb_order_id=5590698461,
        cancelled_at=now - timedelta(days=3),
        assembled=True,
        supply=supply_other,
    )

    headers_b, tenant_b, seller_b, warehouse_b, product_b, supply_b = await _seed_list_scope(
        async_client
    )
    foreign_id = await _seed_cancelled_order(
        tenant_id=tenant_b,
        seller_id=seller_b,
        warehouse_id=warehouse_b,
        product_id=product_b,
        wb_order_id=5590698462,
        cancelled_at=now,
        assembled=True,
        supply=supply_b,
    )

    response = await async_client.get(
        "/fbs/cancelled-after-pack",
        headers=headers_a,
        params={
            "seller_id": str(seller_a),
            "cancelled_from": (now - timedelta(hours=2)).isoformat(),
            "cancelled_to": now.isoformat(),
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["order_id"] == str(recent_a)
    assert str(foreign_id) not in response.text
    own_b = await async_client.get("/fbs/cancelled-after-pack", headers=headers_b)
    assert own_b.status_code == 200, own_b.text
    assert [item["order_id"] for item in own_b.json()["items"]] == [str(foreign_id)]
