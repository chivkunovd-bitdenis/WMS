"""Independent API leg of the stale cargo selection in SortingViewModel.

Run from the WMS-441 backend with -p tests.conftest against a private PostgreSQL DB.
The test deliberately asserts the observed defect so evidence can be reproduced.
No production data, device or shared runtime is used.
"""
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


@pytest.mark.asyncio
async def test_stale_sorting_cargo_can_be_placed_a_second_time(async_client):
    tenant, actor = await _auth_ids(async_client)
    req, product, _, a, b = await _mixed_sorting_request(
        async_client, tenant, actor, loose_qty=2, box_qty=0
    )
    async with SessionLocal() as session:
        doc = await intake.get_request(session, tenant, req)
        warehouse = doc.warehouse_id
        source = await session.scalar(select(InventoryBalance).where(
            InventoryBalance.product_id == product,
            InventoryBalance.quantity > 0,
            InventoryBalance.container_id.is_(None),
        ))
        cargo = InboundIntakeCargoPlace(
            tenant_id=tenant, request_id=req, place_number=1,
            internal_barcode=f"astra-cargo-{uuid.uuid4()}",
            storage_location_id=source.storage_location_id,
        )
        session.add(cargo)
        await session.flush()
        cargo_id = cargo.id
        session.add(InboundIntakeCargoPlaceLine(
            tenant_id=tenant, cargo_place_id=cargo.id, product_id=product, quantity=2,
        ))
        source.container_kind, source.container_id = "cargo_place", cargo.id
        await session.commit()
    headers = {"Authorization": "Bearer " + create_access_token(
        user_id=actor, tenant_id=tenant, role="admin"
    )}
    route = f"/warehouses/{warehouse}/sorting-objects/place"
    # Exact CargoPlacePutawayBody shape emitted by the new Android path.
    first = await async_client.post(route, headers=headers, json={
        "kind": "cargo_place", "id": str(cargo_id), "cell_id": str(a),
    })
    assert first.status_code == 200, first.text
    # Ignore this successful response, modelling post-commit response loss.
    # VM's Err branch does not refresh or clear target. Scanning B and confirming
    # uses its same still-pending target; no UUID or document context is sent.
    second = await async_client.post(route, headers=headers, json={
        "kind": "cargo_place", "id": str(cargo_id), "cell_id": str(b),
    })
    assert second.status_code == 200, second.text
    assert await stock(product, a) == 0
    assert await stock(product, b) == 2
    async with SessionLocal() as session:
        doc = await intake.get_request(session, tenant, req)
        assert doc.status == "done" and doc.lines[0].posted_qty == 2
        rows = list((await session.scalars(select(InventoryMovement).where(
            InventoryMovement.product_id == product,
            InventoryMovement.movement_type.in_(["stock_transfer_out", "stock_transfer_in", "warehouse_map_move"]),
        ))).all())
        assert len(rows) == 4
        print({"first_http": first.status_code, "second_http": second.status_code,
               "posted": doc.lines[0].posted_qty, "status": doc.status,
               "cell_a": 0, "cell_b": 2,
               "movements": sorted((r.movement_type, r.quantity_delta) for r in rows)})


@pytest.mark.asyncio
async def test_web_cargo_contents_exact_operation_replay_spends_another_unit(async_client):
    tenant, actor = await _auth_ids(async_client)
    req, product, _, a, _ = await _mixed_sorting_request(
        async_client, tenant, actor, loose_qty=3, box_qty=0
    )
    async with SessionLocal() as session:
        doc = await intake.get_request(session, tenant, req)
        warehouse = doc.warehouse_id
        source = await session.scalar(select(InventoryBalance).where(
            InventoryBalance.product_id == product, InventoryBalance.quantity > 0,
            InventoryBalance.container_id.is_(None),
        ))
        balance_id = source.id
        cargo = InboundIntakeCargoPlace(
            tenant_id=tenant, request_id=req, place_number=1,
            internal_barcode=f"astra-cargo-replay-{uuid.uuid4()}",
            storage_location_id=source.storage_location_id,
        )
        session.add(cargo)
        await session.flush()
        session.add(InboundIntakeCargoPlaceLine(
            tenant_id=tenant, cargo_place_id=cargo.id, product_id=product, quantity=3,
        ))
        source.container_kind, source.container_id = "cargo_place", cargo.id
        await session.commit()
    headers = {"Authorization": "Bearer " + create_access_token(
        user_id=actor, tenant_id=tenant, role="admin"
    )}
    route = f"/warehouses/{warehouse}/sorting-objects/place"
    # Exact FfSortingObjectsPage body: goods nested in a cargo place use
    # kind=product as well. The web persists and auto-replays this SAME body.
    body = {"kind": "product", "id": str(balance_id), "cell_id": str(a),
            "to_id": None, "qty": 1, "inbound_request_id": str(req),
            "operation_id": str(uuid.uuid4())}
    first = await async_client.post(route, headers=headers, json=body)
    assert first.status_code == 200, first.text
    assert await stock(product, a) == 1
    # Same HTTP body, including operation_id, following lost response/reload.
    replay = await async_client.post(route, headers=headers, json=body)
    assert replay.status_code == 200, replay.text
    assert await stock(product, a) == 2
    async with SessionLocal() as session:
        doc = await intake.get_request(session, tenant, req)
        assert doc.lines[0].posted_qty == 2
        assert doc.cargo_places[0].lines[0].posted_qty == 2
        rows = list((await session.scalars(select(InventoryMovement).where(
            InventoryMovement.product_id == product,
            InventoryMovement.movement_type.in_(["stock_transfer_out", "stock_transfer_in"]),
        ))).all())
        assert len(rows) == 4
        print({"probe": "web_cargo_same_uuid", "first_http": first.status_code,
               "replay_http": replay.status_code, "confirmed_quantity": 1,
               "actual_posted": 2, "actual_cell": 2, "movement_count": len(rows),
               "distinct_transfer_groups": len({str(r.transfer_group_id) for r in rows})})
