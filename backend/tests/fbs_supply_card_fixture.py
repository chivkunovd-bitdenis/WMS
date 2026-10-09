"""Isolated saved data for supply-card contracts; no product operations are mocked."""

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models import Base
from app.models.fbs_packing_box import FbsPackingBox
from app.models.fbs_supply import FbsSupply
from app.models.warehouse_box import WarehouseBox
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
    _seed_pick_supply,
)
from tests.test_fbs_supply_from_orders import (
    _create_product as _create_ready_product,
)
from tests.test_fbs_supply_from_orders import (
    _create_ready_order,
    _setup_seller_with_token,
)
from tests.test_fbs_supply_from_orders import (
    _register_ff_admin as _register_add_admin,
)


async def seed(client, marketplace="wb", count=2):
    headers, suffix, tenant = await _register_ff_admin(client)
    seller, warehouse, location = await _create_seller_and_warehouse(client, headers, suffix)
    product = await _create_product(
        client, headers, seller, sku=f"card-{suffix}", barcode=f"460{suffix[-9:]}"
    )
    supply, orders, _ = await _seed_pick_supply(
        client,
        headers,
        tenant,
        seller,
        warehouse,
        location,
        product,
        stock_qty=8,
        order_specs=[(i + 1, timedelta(hours=3)) for i in range(count)],
        barcode=f"460{suffix[-9:]}",
        marketplace=marketplace,
        position_quantity=3,
    )
    async with SessionLocal() as session:
        row = await session.get(FbsSupply, supply)
        row.status = "assembling"
        await session.commit()
    return headers, tenant, supply, orders


async def empty_neighbor(supply_id):
    async with SessionLocal() as session:
        old = await session.get(FbsSupply, supply_id)
        row = FbsSupply(
            tenant_id=old.tenant_id,
            seller_id=old.seller_id,
            warehouse_id=old.warehouse_id,
            marketplace=old.marketplace,
            wb_supply_id=f"WB-{uuid.uuid4()}",
            name="Empty target",
            status="assembling",
            delivery_type=old.delivery_type,
        )
        session.add(row)
        await session.commit()
        return row.id


async def boxes(tenant, supply, count=2):
    result = []
    async with SessionLocal() as session:
        row = await session.get(FbsSupply, supply)
        for i in range(count):
            physical = WarehouseBox(
                tenant_id=tenant,
                warehouse_id=row.warehouse_id,
                internal_barcode=f"TEST-{uuid.uuid4()}",
            )
            session.add(physical)
            await session.flush()
            box = FbsPackingBox(
                tenant_id=tenant, supply_id=supply, warehouse_box_id=physical.id, box_number=i + 1
            )
            session.add(box)
            await session.flush()
            result.append(box.id)
        await session.commit()
    return result


async def snapshot(exclude=()):
    async with SessionLocal() as session:
        return {
            table.name: sorted(
                repr(tuple(row)) for row in (await session.execute(select(table))).all()
            )
            for table in Base.metadata.sorted_tables
            if table.name not in exclude
        }


async def ready_wb_supply(client, monkeypatch):
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    headers, suffix = await _register_add_admin(client)
    me = await client.get("/auth/me", headers=headers)
    tenant = uuid.UUID(me.json()["tenant_id"])
    seller, warehouse, location = await _setup_seller_with_token(client, headers, suffix)
    product = await _create_ready_product(client, headers, seller, sku=f"wms723-{suffix}")
    orders = [
        await _create_ready_order(
            tenant,
            uuid.UUID(seller),
            uuid.UUID(warehouse),
            uuid.UUID(location),
            product,
            order_id=723000 + i,
        )
        for i in range(3)
    ]
    response = await client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "WMS723",
            "order_ids": [str(orders[0])],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 201, response.text
    supply = uuid.UUID(response.json()["supply"]["id"])
    return headers, tenant, supply, orders


async def add_orders(client, headers, supply, orders, key="same-add-operation"):
    return await client.post(
        f"/operations/fbs-supplies/{supply}/orders/batch",
        headers=headers,
        json={"order_ids": [str(i) for i in orders], "idempotency_key": key},
    )
