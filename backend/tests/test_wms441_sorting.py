"""WMS-441: committed placement, retries, source ownership and completion."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal, engine
from app.models.inbound_intake import InboundIntakeDistributionLine, InboundIntakeLine
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.user import User
from app.models.warehouse_map_event import WarehouseMapEvent
from app.services import inbound_intake_service as intake
from app.services import inbound_sorting_service as sorting
from app.services import warehouse_map_service as warehouse_map
from tests.test_inbound_intake_service_sort_be01 import _auth_ids, _mixed_sorting_request


async def place(tenant, actor, req, product, cell, qty, op=None):
    async with SessionLocal() as session:
        result = await sorting.apply_loose_putaway(
            session,
            tenant,
            req,
            operation_id=op or uuid.uuid4(),
            product_id=product,
            storage_location_id=cell,
            quantity=qty,
            performer_id=actor,
        )
        return result.status, result.lines[0].posted_qty


async def stock(product, cell):
    async with SessionLocal() as session:
        return await session.scalar(
            select(func.coalesce(func.sum(InventoryBalance.quantity), 0)).where(
                InventoryBalance.product_id == product, InventoryBalance.storage_location_id == cell
            )
        )


@pytest.mark.asyncio
async def test_split_repeat_new_scan_and_completion(async_client: AsyncClient):
    tenant, actor = await _auth_ids(async_client)
    req, product, _box, a, b = await _mixed_sorting_request(
        async_client, tenant, actor, loose_qty=3, box_qty=0
    )
    op = uuid.uuid4()
    assert await place(tenant, actor, req, product, a, 1, op) == ("sorting", 1)
    assert await place(tenant, actor, req, product, a, 1, op) == ("sorting", 1)
    with pytest.raises(intake.InboundIntakeError, match="operation_conflict"):
        await place(tenant, actor, req, product, b, 1, op)
    assert await place(tenant, actor, req, product, a, 1) == ("sorting", 2)
    assert await place(tenant, actor, req, product, b, 1) == ("done", 3)
    assert await place(tenant, actor, req, product, a, 1, op) == ("done", 3)
    assert await stock(product, a) == 2
    assert await stock(product, b) == 1
    async with SessionLocal() as session:
        doc = await intake.get_request(session, tenant, req)
        assert doc.distribution_completed_at is not None
        assert doc.posted_at is not None
        assert intake.sorting_remaining_qty(doc) == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(InventoryMovement)
                .where(
                    InventoryMovement.inbound_intake_line_id == doc.lines[0].id,
                    InventoryMovement.quantity_delta < 0,
                )
            )
            == 3
        )


@pytest.mark.asyncio
async def test_loose_putaway_keeps_a_b_authors_in_existing_map_journal(
    async_client: AsyncClient,
):
    tenant, first_actor = await _auth_ids(async_client)
    req, product, _box, first_cell, second_cell = await _mixed_sorting_request(
        async_client, tenant, first_actor, loose_qty=2, box_qty=0
    )
    async with SessionLocal() as session:
        first_user = await session.get(User, first_actor)
        assert first_user is not None
        first_user.full_name = "Анна Размещение WMS443"
        second_user = User(
            tenant_id=tenant,
            email=f"wms443-place-{uuid.uuid4()}@example.com",
            full_name="Борис Размещение WMS443",
            password_hash="test-no-login",
            role="admin",
        )
        session.add(second_user)
        await session.commit()
        second_actor = second_user.id

    first_operation = uuid.uuid4()
    second_operation = uuid.uuid4()
    assert await place(tenant, first_actor, req, product, first_cell, 1, first_operation) == (
        "sorting", 1
    )
    assert await place(tenant, second_actor, req, product, second_cell, 1, second_operation) == (
        "done", 2
    )
    # A lost client response may be replayed by whoever is currently signed in;
    # it must preserve both the original placement and its original author.
    assert await place(tenant, second_actor, req, product, first_cell, 1, first_operation) == (
        "done", 2
    )

    async with SessionLocal() as session:
        events = list(
            await session.scalars(
                select(WarehouseMapEvent)
                .where(
                    WarehouseMapEvent.tenant_id == tenant,
                    WarehouseMapEvent.id.in_([first_operation, second_operation]),
                )
                .order_by(WarehouseMapEvent.id)
            )
        )
        assert {(event.id, event.actor_user_id, event.quantity) for event in events} == {
            (first_operation, first_actor, 1),
            (second_operation, second_actor, 1),
        }
        assert len(events) == 2
        document = await intake.get_request(session, tenant, req)
        assert document is not None
        journal = (await warehouse_map.get_warehouse_map(
            session, tenant, document.warehouse_id
        ))["journal"]
        operation_ids = {str(first_operation), str(second_operation)}
        visible = [row for row in journal if row["id"] in operation_ids]
        visible_values = {
            (row["actor_name"], row["from_label"], row["to_label"], row["qty"])
            for row in visible
        }
        assert visible_values == {
            ("Анна Размещение WMS443", "Сортировка", "A", 1),
            ("Борис Размещение WMS443", "Сортировка", "B", 1),
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("box_first", [False, True])
async def test_mixed_box_loose_no_double_consumption(async_client: AsyncClient, box_first):
    tenant, actor = await _auth_ids(async_client)
    req, product, box, a, b = await _mixed_sorting_request(
        async_client, tenant, actor, loose_qty=1, box_qty=2
    )

    async def box_place():
        async with SessionLocal() as session:
            doc, moved = await intake.apply_box_putaway(
                session, tenant, req, box, storage_location_id=a, performer_id=actor
            )
            assert moved == 2
            return doc.status

    if box_first:
        assert await box_place() == "sorting"
        assert await place(tenant, actor, req, product, b, 1) == ("done", 3)
    else:
        assert await place(tenant, actor, req, product, b, 1) == ("sorting", 1)
        with pytest.raises(intake.InboundIntakeError, match="qty_exceeds_accepted"):
            await place(tenant, actor, req, product, b, 1)
        assert await box_place() == "done"
    assert await stock(product, a) == 2
    assert await stock(product, b) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", [1, 2])
async def test_concurrent_last_unit_or_sufficient_units(async_client: AsyncClient, quantity):
    if engine.dialect.name != "postgresql":
        pytest.skip("Real row-lock concurrency requires PostgreSQL")
    tenant, actor = await _auth_ids(async_client)
    req, product, _box, a, b = await _mixed_sorting_request(
        async_client, tenant, actor, loose_qty=quantity, box_qty=0
    )
    from app.models.user import User

    async with SessionLocal() as session:
        second_actor = User(
            tenant_id=tenant,
            email=f"second-{uuid.uuid4()}@example.com",
            password_hash="test-no-login",
            role="admin",
        )
        session.add(second_actor)
        await session.commit()
        second_actor_id = second_actor.id
    gate = asyncio.Event()

    async def submit(cell, performer):
        await gate.wait()
        try:
            return await place(tenant, performer, req, product, cell, 1)
        except intake.InboundIntakeError as exc:
            return exc.code

    tasks = [
        asyncio.create_task(submit(cell, performer))
        for cell, performer in [(a, actor), (b, second_actor_id)]
    ]
    gate.set()
    results = await asyncio.gather(*tasks)
    assert len([result for result in results if isinstance(result, tuple)]) == quantity
    assert await stock(product, a) + await stock(product, b) == quantity


@pytest.mark.asyncio
async def test_failure_rollback_and_tenant_isolation(async_client: AsyncClient):
    tenant, actor = await _auth_ids(async_client)
    req, product, _box, a, _b = await _mixed_sorting_request(
        async_client, tenant, actor, loose_qty=2, box_qty=0
    )
    with pytest.raises(intake.InboundIntakeError, match="location_not_found"):
        await place(tenant, actor, req, product, uuid.uuid4(), 1)
    with pytest.raises(intake.InboundIntakeError, match="request_not_found"):
        await place(uuid.uuid4(), actor, req, product, a, 1)
    assert await place(tenant, actor, req, product, a, 1) == ("sorting", 1)
    async with SessionLocal() as session:
        await intake.replace_distribution_lines(session, tenant, req, lines=[])
        assert (
            await session.scalar(
                select(func.count())
                .select_from(InboundIntakeDistributionLine)
                .where(InboundIntakeDistributionLine.request_id == req)
            )
            == 1
        )


@pytest.mark.asyncio
async def test_web_context_two_documents_same_sku(async_client: AsyncClient):
    tenant, actor = await _auth_ids(async_client)
    req, product, _box, a, b = await _mixed_sorting_request(
        async_client, tenant, actor, loose_qty=2, box_qty=0
    )
    async with SessionLocal() as session:
        first = await intake.get_request(session, tenant, req)
        warehouse_id = first.warehouse_id
        second = await intake.create_request(session, tenant, warehouse_id=warehouse_id)
        second_id = second.id
        await intake.add_line(session, tenant, second_id, product_id=product, expected_qty=7)
        session.expire_all()
        await intake.begin_receiving(session, tenant, second_id, actor_user_id=actor)
        second = await intake.get_request(session, tenant, second_id)
        await intake.set_line_actual_qty(
            session, tenant, second_id, second.lines[0].id, actual_qty=3
        )
        await intake.complete_receiving(session, tenant, second_id, actor_user_id=actor)
        source = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.product_id == product,
                InventoryBalance.quantity > 0,
                InventoryBalance.container_id.is_(None),
            )
        )
        source_id = source.id
    op = uuid.uuid4()
    for _attempt in range(2):
        async with SessionLocal() as session:
            await warehouse_map.place_sorting_object(
                session,
                tenant_id=tenant,
                warehouse_id=warehouse_id,
                actor_user_id=actor,
                kind="product",
                object_id=source_id,
                cell_id=a,
                to_id=None,
                quantity=2,
                inbound_request_id=req,
                operation_id=op,
            )
    assert await stock(product, a) == 2
    async with SessionLocal() as session:
        second = await intake.get_request(session, tenant, second_id)
        assert second.status == "sorting"
        assert intake.sorting_remaining_qty(second) == 3
        first_map = await warehouse_map.get_sorting_objects(
            session, tenant, warehouse_id, inbound_request_id=req
        )
        assert sum(row["qty"] for row in first_map["lines"] if row["holder"] is None) == 0
    async with SessionLocal() as session:
        placed_balance = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.product_id == product,
                InventoryBalance.storage_location_id == a,
            )
        )
        await warehouse_map.place_sorting_object(
            session,
            tenant_id=tenant,
            warehouse_id=warehouse_id,
            actor_user_id=actor,
            kind="product",
            object_id=placed_balance.id,
            cell_id=b,
            to_id=None,
            quantity=1,
            inbound_request_id=req,
            operation_id=uuid.uuid4(),
        )
        moved_map = await warehouse_map.get_sorting_objects(
            session, tenant, warehouse_id, inbound_request_id=req
        )
        own_places = {
            cell["id"]: sum(row["qty"] for row in cell["lines"]) for cell in moved_map["cells"]
        }
        assert own_places[str(a)] == 1
        assert own_places[str(b)] == 1
    assert await place(tenant, actor, second_id, product, b, 3) == ("done", 3)
    assert await stock(product, b) == 4


@pytest.mark.asyncio
async def test_reconcile_requires_linked_movements_and_does_not_move_again(
    async_client: AsyncClient,
):
    tenant, actor = await _auth_ids(async_client)
    req, product, _box, a, _b = await _mixed_sorting_request(
        async_client, tenant, actor, loose_qty=1, box_qty=0
    )
    async with SessionLocal() as session:
        with pytest.raises(intake.InboundIntakeError, match="sorting_reconciliation_unproven"):
            await sorting.reconcile_linked_putaway(session, tenant, req)
        await session.rollback()
        untouched = await intake.get_request(session, tenant, req)
        assert untouched.status == "sorting"
    await place(tenant, actor, req, product, a, 1)
    async with SessionLocal() as session:
        doc = await intake.get_request(session, tenant, req)
        doc.status = "sorting"
        doc.posted_at = None
        doc.distribution_completed_at = None
        doc.lines[0].posted_qty = 0
        await session.commit()
        count = await session.scalar(select(func.count()).select_from(InventoryMovement))
        repaired = await sorting.reconcile_linked_putaway(session, tenant, req)
        assert repaired.status == "done"
        assert await session.scalar(select(func.count()).select_from(InventoryMovement)) == count
    assert await stock(product, a) == 1


@pytest.mark.asyncio
async def test_defect_fact_and_zero_line(async_client: AsyncClient):
    tenant, actor = await _auth_ids(async_client)
    req, product, _box, a, _b = await _mixed_sorting_request(
        async_client, tenant, actor, loose_qty=3, box_qty=0
    )
    async with SessionLocal() as session:
        line = await session.scalar(
            select(InboundIntakeLine).where(InboundIntakeLine.request_id == req)
        )
        line.expected_qty = 100
        line.defective_qty = 1
        from app.services.catalog_service import create_product

        zero_product = await create_product(
            session,
            tenant,
            name="Zero fact",
            sku_code=f"zero-{uuid.uuid4()}",
            length_mm=10,
            width_mm=10,
            height_mm=10,
        )
        session.add(
            InboundIntakeLine(
                request_id=req, product_id=zero_product.id, expected_qty=10, actual_qty=0
            )
        )
        await session.commit()
    assert await place(tenant, actor, req, product, a, 3) == ("done", 3)
    assert await stock(product, a) == 2
    async with SessionLocal() as session:
        total = await session.scalar(
            select(func.sum(InventoryBalance.quantity)).where(
                InventoryBalance.product_id == product
            )
        )
        assert total == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("operation_type", ["inbound", "return"])
async def test_completion_charge_and_author_once(async_client: AsyncClient, operation_type):
    from datetime import date

    from app.models.billing import BillingLedgerEntry, BillingTariffVersion
    from app.models.operation_fact import OperationFact
    from app.models.product import Product
    from app.models.tenant import Tenant
    from app.services.catalog_service import create_seller

    tenant, actor = await _auth_ids(async_client)
    req, product, _box, a, _b = await _mixed_sorting_request(
        async_client, tenant, actor, loose_qty=2, box_qty=0
    )
    async with SessionLocal() as session:
        seller = await create_seller(session, tenant, name="WMS441 seller")
        doc = await intake.get_request(session, tenant, req)
        doc.seller_id = seller.id
        doc.operation_type = operation_type
        prod = await session.get(Product, product)
        prod.seller_id = seller.id
        org = await session.get(Tenant, tenant)
        org.billing_enabled_from = date(2020, 1, 1)
        session.add(
            BillingTariffVersion(
                tenant_id=tenant,
                service_code=operation_type,
                unit="item",
                amount=100,
                valid_from=date(2020, 1, 1),
            )
        )
        await session.commit()
    op = uuid.uuid4()
    assert await place(tenant, actor, req, product, a, 2, op) == ("done", 2)
    assert await place(tenant, None, req, product, a, 2, op) == ("done", 2)
    async with SessionLocal() as session:
        charges = list(
            (
                await session.scalars(
                    select(BillingLedgerEntry).where(
                        BillingLedgerEntry.source_type == "inbound_intake",
                        BillingLedgerEntry.source_id == req,
                    )
                )
            ).all()
        )
        assert len(charges) == 1
        assert charges[0].quantity == 2
        assert charges[0].performer_id == actor
        assert charges[0].service_code == operation_type
        facts = list(
            (
                await session.scalars(select(OperationFact).where(OperationFact.document_id == req))
            ).all()
        )
        assert len(facts) == 1
        assert facts[0].actor_user_id == actor
        doc = await intake.get_request(session, tenant, req)
        assert doc.completed_by_user_id == actor


@pytest.mark.asyncio
@pytest.mark.parametrize("on_pallet", [False, True])
async def test_cargo_and_pallet_putaway_updates_source_document(
    async_client: AsyncClient,
    on_pallet,
):
    from app.models.inbound_intake import InboundIntakeCargoPlace, InboundIntakeCargoPlaceLine
    from app.services import pallet_service

    tenant, actor = await _auth_ids(async_client)
    req, product, _box, a, _b = await _mixed_sorting_request(
        async_client, tenant, actor, loose_qty=2, box_qty=0
    )
    async with SessionLocal() as session:
        doc = await intake.get_request(session, tenant, req)
        warehouse_id = doc.warehouse_id
        source = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.product_id == product, InventoryBalance.quantity == 2
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
        cargo_id = cargo.id
        session.add(
            InboundIntakeCargoPlaceLine(
                tenant_id=tenant, cargo_place_id=cargo_id, product_id=product, quantity=2
            )
        )
        source.container_kind = "cargo_place"
        source.container_id = cargo_id
        object_id, kind = cargo_id, "cargo_place"
        if on_pallet:
            pallet = await pallet_service.create_pallet(
                session, tenant, warehouse_id=warehouse_id, inbound_request_id=req, commit=False
            )
            cargo.pallet_id = pallet.id
            object_id, kind = pallet.id, "pallet"
        await session.commit()
    async with SessionLocal() as session:
        await warehouse_map.place_sorting_object(
            session,
            tenant_id=tenant,
            warehouse_id=warehouse_id,
            actor_user_id=actor,
            kind=kind,
            object_id=object_id,
            cell_id=a,
            to_id=None,
            quantity=None,
            inbound_request_id=req,
            operation_id=uuid.uuid4(),
        )
    async with SessionLocal() as session:
        doc = await intake.get_request(session, tenant, req)
        assert doc.status == "done"
        assert doc.cargo_places[0].lines[0].posted_qty == 2
    assert await stock(product, a) == 2


@pytest.mark.asyncio
async def test_failure_after_debit_rolls_back_all_effects(async_client: AsyncClient, monkeypatch):
    from app.services import inventory_service

    tenant, actor = await _auth_ids(async_client)
    req, product, _box, a, _b = await _mixed_sorting_request(
        async_client, tenant, actor, loose_qty=1, box_qty=0
    )
    original = inventory_service.record_movement_and_adjust_balance

    async def fail_destination(*args, **kwargs):
        if kwargs.get("quantity_delta", 0) > 0:
            raise RuntimeError("test injected write failure")
        return await original(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(inventory_service, "record_movement_and_adjust_balance", fail_destination)
        with pytest.raises(RuntimeError, match="test injected"):
            await place(tenant, actor, req, product, a, 1)
    assert await stock(product, a) == 0
    assert await place(tenant, actor, req, product, a, 1) == ("done", 1)


@pytest.mark.asyncio
async def test_http_contract_and_reopen_after_lost_response(async_client: AsyncClient):
    from app.services.tokens import create_access_token

    tenant, actor = await _auth_ids(async_client)
    req, product, _box, a, _b = await _mixed_sorting_request(
        async_client, tenant, actor, loose_qty=1, box_qty=0
    )
    headers = {
        "Authorization": "Bearer "
        + create_access_token(user_id=actor, tenant_id=tenant, role="admin")
    }
    url = f"/operations/inbound-intake-requests/{req}/loose-putaway"
    body = {
        "operation_id": str(uuid.uuid4()),
        "product_id": str(product),
        "storage_location_id": str(a),
        "quantity": 1,
    }
    invalid = await async_client.post(url, headers=headers, json={**body, "quantity": 0})
    assert invalid.status_code == 422
    placed = await async_client.post(url, headers=headers, json=body)
    assert placed.status_code == 200, placed.text
    assert placed.json()["status"] == "done"
    assert placed.json()["sorting_remaining_qty"] == 0
    assert placed.json()["lines"][0]["posted_qty"] == 1
    repeated = await async_client.post(url, headers=headers, json=body)
    assert repeated.status_code == 200
    reread = await async_client.get(f"/operations/inbound-intake-requests/{req}", headers=headers)
    assert reread.json()["status"] == "done"
    assert await stock(product, a) == 1
