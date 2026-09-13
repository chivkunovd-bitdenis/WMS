"""Executable reproductions of the WMS-441 independent review findings."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.inbound_intake import InboundIntakeCargoPlace, InboundIntakeCargoPlaceLine
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.services import inbound_intake_service as intake
from app.services import warehouse_map_service as warehouse_map
from app.services.tokens import create_access_token
from tests.test_inbound_intake_service_sort_be01 import _auth_ids, _mixed_sorting_request
from tests.test_wms441_sorting import place, stock


@pytest.mark.asyncio
@pytest.mark.parametrize("box_qty", [0, 2])
async def test_legacy_distribution_can_place_cargo_without_consuming_boxes(
    async_client: AsyncClient,
    box_qty,
):
    tenant, actor = await _auth_ids(async_client)
    req, product, box_id, cell, other = await _mixed_sorting_request(
        async_client, tenant, actor, loose_qty=2, box_qty=box_qty
    )
    async with SessionLocal() as session:
        source = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.product_id == product,
                InventoryBalance.quantity > 0,
                InventoryBalance.container_id.is_(None),
            )
        )
        cargo = InboundIntakeCargoPlace(
            tenant_id=tenant,
            request_id=req,
            place_number=1,
            internal_barcode=f"cargo-{uuid.uuid4()}",
            storage_location_id=source.storage_location_id,
        )
        session.add(cargo)
        await session.flush()
        session.add(
            InboundIntakeCargoPlaceLine(
                tenant_id=tenant, cargo_place_id=cargo.id, product_id=product, quantity=2
            )
        )
        source.container_kind, source.container_id = "cargo_place", cargo.id
        await session.commit()
    with pytest.raises(intake.InboundIntakeError, match="qty_exceeds_accepted"):
        await place(tenant, actor, req, product, cell, 1)
    async with SessionLocal() as session:
        await intake.replace_distribution_lines(
            session, tenant, req, lines=[(None, product, cell, 2)]
        )
        result = await intake.complete_distribution(session, tenant, req, performer_id=actor)
        assert result.status == ("done" if box_qty == 0 else "sorting")
        assert result.cargo_places[0].lines[0].posted_qty == 2
    assert await stock(product, cell) == 2
    if box_qty:
        with pytest.raises(intake.InboundIntakeError, match="qty_exceeds_accepted"):
            await place(tenant, actor, req, product, cell, 1)
        async with SessionLocal() as session:
            result, moved = await intake.apply_box_putaway(
                session, tenant, req, box_id, storage_location_id=other, performer_id=actor
            )
            assert result.status == "done" and moved == box_qty
        assert await stock(product, other) == box_qty


@pytest.mark.asyncio
@pytest.mark.parametrize("first_path", ["legacy", "mobile"])
async def test_partial_putaway_then_legacy_edit_scan_preserves_receipt(
    async_client: AsyncClient,
    first_path,
):
    tenant, actor = await _auth_ids(async_client)
    req, product, _box, a, b = await _mixed_sorting_request(
        async_client, tenant, actor, loose_qty=4, box_qty=0
    )
    operation_id = uuid.uuid4()
    async with SessionLocal() as session:
        prod = await session.get(Product, product)
        prod.sku_code = "441-review-barcode"
        await session.commit()
        if first_path == "legacy":
            await intake.replace_distribution_lines(
                session, tenant, req, lines=[(None, product, a, 1)]
            )
            await intake.complete_distribution(session, tenant, req, performer_id=actor)
    if first_path == "mobile":
        await place(tenant, actor, req, product, a, 1, operation_id)
    async with SessionLocal() as session:
        await intake.replace_distribution_lines(session, tenant, req, lines=[(None, product, b, 2)])
        await intake.scan_distribution_barcode(
            session, tenant, req, barcode="441-review-barcode", active_storage_location_id=b
        )
        result = await intake.complete_distribution(session, tenant, req, performer_id=actor)
        assert result.status == "done"
    if first_path == "mobile":
        assert await place(tenant, actor, req, product, a, 1, operation_id) == ("done", 4)
    assert await stock(product, a) == 1
    assert await stock(product, b) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("placed_qty", [1, 2])
async def test_runtime_reconciles_proven_historical_unlinked_map_without_new_movement(
    async_client: AsyncClient,
    placed_qty,
):
    tenant, actor = await _auth_ids(async_client)
    req, product, _box, cell, other = await _mixed_sorting_request(
        async_client, tenant, actor, loose_qty=2, box_qty=0
    )
    async with SessionLocal() as session:
        doc = await intake.get_request(session, tenant, req)
        warehouse_id = doc.warehouse_id
        source = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.product_id == product, InventoryBalance.quantity > 0
            )
        )
        await warehouse_map.move_object(
            session,
            tenant_id=tenant,
            warehouse_id=warehouse_id,
            actor_user_id=actor,
            kind="product",
            object_id=source.id,
            to_kind="cell",
            to_id=cell,
            quantity=placed_qty,
        )
        session.expire_all()
        doc = await intake.get_request(session, tenant, req)
        assert doc.status == "sorting" and doc.lines[0].posted_qty == 0
        count_before = await session.scalar(select(func.count()).select_from(InventoryMovement))
    headers = {
        "Authorization": "Bearer "
        + create_access_token(user_id=actor, tenant_id=tenant, role="admin")
    }
    response = await async_client.post(
        f"/operations/inbound-intake-requests/{req}/reconcile-sorting", headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == ("done" if placed_qty == 2 else "sorting")
    async with SessionLocal() as session:
        assert (
            await session.scalar(select(func.count()).select_from(InventoryMovement))
            == count_before
        )
    assert await stock(product, cell) == placed_qty
    repeated = await async_client.post(
        f"/operations/inbound-intake-requests/{req}/reconcile-sorting", headers=headers
    )
    assert repeated.status_code == 200
    if placed_qty == 1:
        async with SessionLocal() as session:
            await intake.replace_distribution_lines(
                session, tenant, req, lines=[(None, product, other, 1)]
            )
            completed = await intake.complete_distribution(session, tenant, req, performer_id=actor)
            assert completed.status == "done"
        assert await stock(product, other) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("original_group_link", [True, False])
async def test_mobile_receipt_survives_older_same_cell_draft(
    async_client: AsyncClient,
    original_group_link,
):
    tenant, actor = await _auth_ids(async_client)
    req, product, _box, a, b = await _mixed_sorting_request(
        async_client, tenant, actor, loose_qty=4, box_qty=0
    )
    async with SessionLocal() as session:
        await intake.replace_distribution_lines(session, tenant, req, lines=[(None, product, a, 3)])
    op = uuid.uuid4()
    await place(tenant, actor, req, product, a, 1, op)
    if not original_group_link:
        from sqlalchemy import update

        async with SessionLocal() as session:
            await session.execute(
                update(InventoryMovement)
                .where(
                    InventoryMovement.transfer_group_id == op,
                )
                .values(transfer_group_id=uuid.uuid4())
            )
            await session.commit()
    async with SessionLocal() as session:
        rows = await intake.replace_distribution_lines(session, tenant, req, lines=[])
        assert [(row.id, row.quantity) for row in rows] == [(op, 1)]
        await intake.replace_distribution_lines(
            session, tenant, req, lines=[(None, product, a, 1), (None, product, b, 3)]
        )
        await intake.complete_distribution(session, tenant, req, performer_id=actor)
    assert await place(tenant, actor, req, product, a, 1, op) == ("done", 4)
    assert await stock(product, a) == 1
    assert await stock(product, b) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("unknown_source", ["mixed_ledger", "missing_ledger"])
async def test_runtime_repair_refuses_ambiguous_source_ownership(
    async_client: AsyncClient,
    unknown_source,
):
    from app.services import inventory_service

    tenant, actor = await _auth_ids(async_client)
    req, product, _box, cell, _other = await _mixed_sorting_request(
        async_client, tenant, actor, loose_qty=2, box_qty=0
    )
    async with SessionLocal() as session:
        doc = await intake.get_request(session, tenant, req)
        warehouse_id = doc.warehouse_id
        source = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.product_id == product, InventoryBalance.quantity > 0
            )
        )
        if unknown_source == "mixed_ledger":
            await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=tenant,
                product_id=product,
                storage_location_id=source.storage_location_id,
                quantity_delta=1,
                movement_type="stock_transfer_in",
                actor_user_id=actor,
            )
        else:
            source.quantity += 1
            source.quantity_unpacked += 1
        await session.commit()
        await warehouse_map.move_object(
            session,
            tenant_id=tenant,
            warehouse_id=warehouse_id,
            actor_user_id=actor,
            kind="product",
            object_id=source.id,
            to_kind="cell",
            to_id=cell,
            quantity=1,
        )
        count_before = await session.scalar(select(func.count()).select_from(InventoryMovement))
    headers = {
        "Authorization": "Bearer "
        + create_access_token(user_id=actor, tenant_id=tenant, role="admin")
    }
    response = await async_client.post(
        f"/operations/inbound-intake-requests/{req}/reconcile-sorting", headers=headers
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "sorting_reconciliation_unproven"
    async with SessionLocal() as session:
        doc = await intake.get_request(session, tenant, req)
        assert doc.status == "sorting" and doc.lines[0].posted_qty == 0
        assert (
            await session.scalar(select(func.count()).select_from(InventoryMovement))
            == count_before
        )
        maps = list(
            (
                await session.scalars(
                    select(InventoryMovement).where(
                        InventoryMovement.movement_type == "warehouse_map_move"
                    )
                )
            ).all()
        )
        assert all(row.inbound_intake_line_id is None for row in maps)


@pytest.mark.asyncio
async def test_historical_group_with_two_products_keeps_document_ownership(
    async_client: AsyncClient,
):
    from sqlalchemy import update

    from app.models.inbound_intake import InboundIntakeLine
    from app.services import inbound_sorting_service, inventory_service
    from app.services.catalog_service import create_product

    tenant, actor = await _auth_ids(async_client)
    req, first_product, _box, cell, _other = await _mixed_sorting_request(
        async_client, tenant, actor, loose_qty=2, box_qty=0
    )
    async with SessionLocal() as session:
        doc = await intake.get_request(session, tenant, req)
        warehouse_id = doc.warehouse_id
        first_source = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.product_id == first_product, InventoryBalance.quantity > 0
            )
        )
        source_location = first_source.storage_location_id
        second = await create_product(
            session,
            tenant,
            name="Second historical item",
            sku_code=f"second-{uuid.uuid4()}",
            length_mm=10,
            width_mm=10,
            height_mm=10,
        )
        second_id = second.id
        second_line = InboundIntakeLine(
            request_id=req, product_id=second_id, expected_qty=1, actual_qty=1
        )
        session.add(second_line)
        await session.flush()
        await inventory_service.apply_inbound_receive(
            session,
            tenant_id=tenant,
            product_id=second_id,
            storage_location_id=source_location,
            quantity=1,
            inbound_intake_line_id=second_line.id,
            movement_type="inbound_intake",
            actor_user_id=actor,
        )
        await session.commit()
        sources = list(
            (
                await session.scalars(
                    select(InventoryBalance).where(
                        InventoryBalance.storage_location_id == source_location,
                        InventoryBalance.product_id.in_([first_product, second_id]),
                        InventoryBalance.quantity > 0,
                    )
                )
            ).all()
        )
        for source in sources:
            await warehouse_map.move_object(
                session,
                tenant_id=tenant,
                warehouse_id=warehouse_id,
                actor_user_id=actor,
                kind="product",
                object_id=source.id,
                to_kind="cell",
                to_id=cell,
                quantity=source.quantity,
            )
        await session.execute(
            update(InventoryMovement)
            .where(
                InventoryMovement.tenant_id == tenant,
                InventoryMovement.movement_type == "warehouse_map_move",
            )
            .values(transfer_group_id=uuid.uuid4())
        )
        await session.commit()
    async with SessionLocal() as session:
        result = await inbound_sorting_service.reconcile_linked_putaway(session, tenant, req)
        assert result.status == "done"
        assert sorted(line.posted_qty for line in result.lines) == [1, 2]
    assert await stock(first_product, cell) == 2
    assert await stock(second_id, cell) == 1
