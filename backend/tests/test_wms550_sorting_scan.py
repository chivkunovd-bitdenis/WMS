"""Scanner unit placement, source ownership and durable retries."""

import asyncio
import uuid

import pytest
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.inbound_intake import InboundIntakeBoxLine, InboundIntakeDistributionLine
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.services import inbound_intake_service as intake
from app.services import warehouse_map_service as warehouse_map
from app.services.sorting_scan_service import scan_product
from tests.test_inbound_intake_service_sort_be01 import _auth_ids, _mixed_sorting_request


async def seed(client, *, loose=0, boxed=3):
    tenant, actor = await _auth_ids(client)
    req, product, box, cell, other_cell = await _mixed_sorting_request(
        client, tenant, actor, loose_qty=loose, box_qty=boxed
    )
    async with SessionLocal() as session:
        item = await session.get(Product, product)
        item.wb_barcode = "WMS550-SKU"
        request = await intake.get_request(session, tenant, req)
        warehouse = request.warehouse_id
        await session.commit()
    args = dict(tenant_id=tenant, actor_user_id=actor, warehouse_id=warehouse,
                inbound_request_id=req, cell_id=cell, barcode="WMS550-SKU")
    return args, product, box, other_cell


async def scan(args, operation=None, **overrides):
    async with SessionLocal() as session:
        return await scan_product(session, **(args | overrides),
                                  operation_id=operation or uuid.uuid4())


async def qty(product, cell):
    async with SessionLocal() as session:
        return await session.scalar(select(func.coalesce(func.sum(InventoryBalance.quantity), 0))
                                    .where(InventoryBalance.product_id == product,
                                           InventoryBalance.storage_location_id == cell))


@pytest.mark.asyncio
async def test_box_unit_scan_repeat_and_completion(async_client):
    args, product, box, other_cell = await seed(async_client, boxed=2)
    op = uuid.uuid4()
    assert (await scan(args, op))["moved_qty"] == 1
    assert await scan(args, op) == {"id": str(op), "moved_qty": 1}
    with pytest.raises(warehouse_map.WarehouseMapError, match="operation_conflict"):
        await scan(args, op, cell_id=other_cell)
    assert await qty(product, args["cell_id"]) == 1
    async with SessionLocal() as session:
        content = await session.scalar(select(InboundIntakeBoxLine).where(
            InboundIntakeBoxLine.box_id == box))
        assert content.posted_qty == 1
    await scan(args)
    assert await qty(product, args["cell_id"]) == 2
    with pytest.raises(warehouse_map.WarehouseMapError, match="nothing_to_move"):
        await scan(args)
    assert await scan(args, op) == {"id": str(op), "moved_qty": 1}
    async with SessionLocal() as session:
        request = await intake.get_request(session, args["tenant_id"], args["inbound_request_id"])
        assert request.lines[0].posted_qty == 2
        assert request.status == "done"
        receipts = await session.scalar(select(func.count())
                                        .select_from(InboundIntakeDistributionLine).where(
                                            InboundIntakeDistributionLine.request_id == request.id))
        assert receipts == 2


@pytest.mark.asyncio
async def test_scan_loose_into_selected_container_and_retry(async_client):
    args, product, _box, _ = await seed(async_client, loose=2, boxed=0)
    async with SessionLocal() as session:
        target = await warehouse_map.create_sorting_object(
            session, args["tenant_id"], args["warehouse_id"], kind="box",
            inbound_request_id=args["inbound_request_id"],
        )
        target_id = uuid.UUID(target["id"])
        await warehouse_map.place_sorting_object(
            session, tenant_id=args["tenant_id"], warehouse_id=args["warehouse_id"],
            actor_user_id=args["actor_user_id"], kind="box", object_id=target_id,
            cell_id=args["cell_id"], to_id=None, quantity=None,
            inbound_request_id=args["inbound_request_id"],
        )
    op = uuid.uuid4()
    await scan(args, op, to_id=target_id)
    await scan(args, op, to_id=target_id)
    await scan(args, to_id=target_id)
    assert await qty(product, args["cell_id"]) == 2
    with pytest.raises(warehouse_map.WarehouseMapError, match="already_in_target"):
        await scan(args, to_id=target_id)


@pytest.mark.asyncio
async def test_multiple_sources_are_not_guessed(async_client):
    args, product, _, _ = await seed(async_client, loose=2, boxed=2)
    with pytest.raises(warehouse_map.WarehouseMapError, match="ambiguous_source"):
        await scan(args)
    assert await qty(product, args["cell_id"]) == 0


@pytest.mark.asyncio
async def test_wrong_document_barcode_and_tenant_cannot_consume(async_client):
    args, product, _, _ = await seed(async_client)
    with pytest.raises(warehouse_map.WarehouseMapError, match="product_not_on_request"):
        await scan(args, barcode="NOT-ON-DOCUMENT")
    with pytest.raises(warehouse_map.WarehouseMapError, match="inbound_request_not_found"):
        await scan(args, tenant_id=uuid.uuid4())
    assert await qty(product, args["cell_id"]) == 0


@pytest.mark.asyncio
async def test_two_scanners_cannot_spend_last_unit_twice(async_client):
    args, product, _, _ = await seed(async_client, boxed=1)
    results = await asyncio.gather(scan(args), scan(args), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert await qty(product, args["cell_id"]) == 1
