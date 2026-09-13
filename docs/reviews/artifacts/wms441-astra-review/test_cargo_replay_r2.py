"""Independent probes of the new cargo sorting operation contract, backend 082c2540."""
import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.inbound_intake import InboundIntakeCargoPlace, InboundIntakeCargoPlaceLine
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.services import inbound_intake_service as intake
from app.services.tokens import create_access_token
from tests.test_inbound_intake_service_sort_be01 import _auth_ids, _mixed_sorting_request
from tests.test_wms441_sorting import stock


async def cargo_fixture(client, defective=0):
    tenant, actor = await _auth_ids(client)
    req, product, _, a, b = await _mixed_sorting_request(
        client, tenant, actor, loose_qty=2, box_qty=0
    )
    async with SessionLocal() as session:
        doc = await intake.get_request(session, tenant, req)
        doc.lines[0].defective_qty = defective
        warehouse = doc.warehouse_id
        source = await session.scalar(select(InventoryBalance).where(
            InventoryBalance.product_id == product, InventoryBalance.quantity > 0,
            InventoryBalance.container_id.is_(None),
        ))
        cargo = InboundIntakeCargoPlace(
            tenant_id=tenant, request_id=req, place_number=1,
            internal_barcode=f"astra-r2-{uuid.uuid4()}",
            storage_location_id=source.storage_location_id,
        )
        session.add(cargo)
        await session.flush()
        session.add(InboundIntakeCargoPlaceLine(
            tenant_id=tenant, cargo_place_id=cargo.id, product_id=product, quantity=2,
        ))
        source.container_kind, source.container_id = "cargo_place", cargo.id
        await session.commit()
        body = {"kind": "cargo_place", "id": str(cargo.id), "cell_id": str(a),
                "inbound_request_id": str(req), "operation_id": str(uuid.uuid4())}
    headers = {"Authorization": "Bearer " + create_access_token(
        user_id=actor, tenant_id=tenant, role="admin"
    )}
    return f"/warehouses/{warehouse}/sorting-objects/place", headers, body, tenant, req, product, a, b


@pytest.mark.asyncio
async def test_exact_cargo_replay_is_one_transfer(async_client):
    route, headers, body, tenant, req, product, a, b = await cargo_fixture(async_client)
    first = await async_client.post(route, headers=headers, json=body)
    replay = await async_client.post(route, headers=headers, json=body)
    conflict = await async_client.post(route, headers=headers, json={**body, "cell_id": str(b)})
    assert [first.status_code, replay.status_code, conflict.status_code] == [200, 200, 409]
    assert await stock(product, a) == 2
    async with SessionLocal() as session:
        rows = list((await session.scalars(select(InventoryMovement).where(
            InventoryMovement.transfer_group_id == uuid.UUID(body["operation_id"]),
        ))).all())
        assert len(rows) == 2
    print({"probe": "cargo_same_uuid", "http": [200, 200, 409], "movements": 2})


@pytest.mark.asyncio
async def test_two_stale_sorting_clients_cannot_move_last_cargo_twice(async_client):
    route, headers, body, tenant, req, product, a, b = await cargo_fixture(async_client)
    # Both operators selected the same pending cargo before either received a reply.
    other = {**body, "cell_id": str(b), "operation_id": str(uuid.uuid4())}
    responses = await asyncio.gather(
        async_client.post(route, headers=headers, json=body),
        async_client.post(route, headers=headers, json=other),
    )
    statuses = [r.status_code for r in responses]
    async with SessionLocal() as session:
        doc = await intake.get_request(session, tenant, req)
        rows = list((await session.scalars(select(InventoryMovement).where(
            InventoryMovement.product_id == product,
            InventoryMovement.quantity_delta < 0,
            InventoryMovement.movement_type.in_(["stock_transfer_out", "warehouse_map_move"]),
        ))).all())
        print({"probe": "two_stale_sorting_clients", "http": statuses,
               "outgoing_movements": len(rows), "posted": doc.lines[0].posted_qty,
               "cell_a": await stock(product, a), "cell_b": await stock(product, b)})
        assert len(rows) == 1, "Second sorting context became a new generic relocation"


@pytest.mark.asyncio
async def test_defect_only_cargo_replays_original_target(async_client):
    route, headers, body, *_ = await cargo_fixture(async_client, defective=2)
    first = await async_client.post(route, headers=headers, json=body)
    replay = await async_client.post(route, headers=headers, json=body)
    print({"probe": "defect_only_same_uuid", "first": first.status_code,
           "replay": replay.status_code, "detail": replay.json() if replay.status_code != 200 else None})
    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
