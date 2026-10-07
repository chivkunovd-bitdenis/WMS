"""WMS-666: expose each order's current seller/product marking pool count."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.marking_code import STATUS_AVAILABLE, MarkingCode
from app.models.product import Product
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
    _seed_pick_supply,
)


async def _bare_supply_with_pool(
    async_client: AsyncClient,
    *,
    headers: dict[str, str],
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    location_id: uuid.UUID,
    product_id: uuid.UUID,
    suffix: str,
    order_count: int,
    pool_count: int,
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    supply_id, order_ids, _ = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=0,
        order_specs=[(index + 1, timedelta(hours=3 + index)) for index in range(order_count)],
        barcode=f"2300{suffix[-9:]}",
    )
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        supply = await session.get(FbsSupply, supply_id)
        orders = list(
            (await session.execute(select(FbsOrder).where(FbsOrder.id.in_(order_ids))))
            .scalars()
        )
        assert product is not None and supply is not None
        product.requires_honest_sign = True
        supply.status = "assembling"
        supply.packaging_task_id = None
        for order in orders:
            order.required_meta_json = ["sgtin"]
        session.add_all(
            MarkingCode(
                tenant_id=tenant_id,
                seller_id=seller_id,
                product_id=product_id,
                cis_code=f"010000000000012321{seller_id.hex[:8]}{index:04d}",
                gtin="00000000000001",
                status=STATUS_AVAILABLE,
            )
            for index in range(pool_count)
        )
        await session.commit()
    return supply_id, order_ids


@pytest.mark.asyncio
async def test_bare_workspace_reports_current_pool_per_product_and_seller(
    async_client: AsyncClient,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_a, warehouse_a, location_a = await _create_seller_and_warehouse(
        async_client, headers, suffix,
    )
    product_a = await _create_product(
        async_client, headers, seller_a, sku=f"wms666-bare-a-{suffix[-8:]}",
        barcode=f"2300{suffix[-9:]}",
    )
    supply_a, order_ids_a = await _bare_supply_with_pool(
        async_client,
        headers=headers,
        tenant_id=tenant_id,
        seller_id=seller_a,
        warehouse_id=warehouse_a,
        location_id=location_a,
        product_id=product_a,
        suffix=f"a{suffix}",
        order_count=2,
        pool_count=2,
    )

    seller_b, warehouse_b, location_b = await _create_seller_and_warehouse(
        async_client, headers, f"{suffix}-b",
    )
    product_b = await _create_product(
        async_client, headers, seller_b, sku=f"wms666-bare-b-{suffix[-8:]}",
        barcode=f"2301{suffix[-9:]}",
    )
    supply_b, order_ids_b = await _bare_supply_with_pool(
        async_client,
        headers=headers,
        tenant_id=tenant_id,
        seller_id=seller_b,
        warehouse_id=warehouse_b,
        location_id=location_b,
        product_id=product_b,
        suffix=f"b{suffix}",
        order_count=1,
        pool_count=1,
    )

    response_a = await async_client.get(
        f"/operations/fbs-supplies/{supply_a}/workspace", headers=headers,
    )
    response_b = await async_client.get(
        f"/operations/fbs-supplies/{supply_b}/workspace", headers=headers,
    )
    assert response_a.status_code == 200, response_a.text
    assert response_b.status_code == 200, response_b.text
    body_a = response_a.json()
    body_b = response_b.json()

    # The bare supply has no accounting task; its workspace still knows the
    # actual seller/product pool. Both same-product orders see that read-only
    # pool count, and the other seller's row sees only its own pool.
    assert body_a["supply"]["packaging_task_id"] is None
    assert body_b["supply"]["packaging_task_id"] is None
    assert all(row["product"]["requires_honest_sign"] for row in body_a["orders"])
    assert all(row["product"]["requires_honest_sign"] for row in body_b["orders"])
    assert body_a["marking_pool"]["available"] == 2
    assert body_b["marking_pool"]["available"] == 1
    by_id_a = {row["id"]: row for row in body_a["orders"]}
    by_id_b = {row["id"]: row for row in body_b["orders"]}
    assert set(by_id_a) == {str(order_id) for order_id in order_ids_a}
    assert set(by_id_b) == {str(order_id) for order_id in order_ids_b}
    assert [by_id_a[str(order_id)]["marking_available_count"] for order_id in order_ids_a] == [2, 2]
    assert by_id_b[str(order_ids_b[0])]["marking_available_count"] == 1
