from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError

from app.db.physical_warehouse_guard import install_guards, remove_guards
from app.db.session import SessionLocal
from app.models.background_job import BackgroundJob
from app.models.fbs_order import FbsOrder, FbsOrderReservation
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox
from app.services import catalog_service
from app.services import physical_warehouse_repair_service as repair
from app.services.defect_warehouse_service import get_or_create_defect_location
from app.services.fbs_warehouse_binding_service import is_auto_fbs_wms_warehouse


async def seed(session, *, second=False):
    tenant = Tenant(name="Fixture", slug=uuid.uuid4().hex)
    session.add(tenant)
    await session.flush()
    seller = Seller(tenant_id=tenant.id, name="Owner")
    other = Seller(tenant_id=tenant.id, name="Other owner")
    legacy = Warehouse(tenant_id=tenant.id, name="Legacy", code="fbs-wb-1887957",
                       is_operational=False)
    target = Warehouse(tenant_id=tenant.id, name="Physical", code="physical")
    session.add_all([seller, other, legacy, target])
    if second:
        session.add(Warehouse(tenant_id=tenant.id, name="Second", code="second"))
    await session.flush()
    product = Product(tenant_id=tenant.id, seller_id=seller.id, name="SKU", sku_code="sku")
    other_product = Product(tenant_id=tenant.id, seller_id=other.id, name="Other", sku_code="other")
    old_loc = StorageLocation(tenant_id=tenant.id, warehouse_id=legacy.id,
                              code="__SORTING__", barcode="OLD")
    new_loc = StorageLocation(tenant_id=tenant.id, warehouse_id=target.id,
                              code="__SORTING__", barcode="NEW")
    session.add_all([product, other_product, old_loc, new_loc])
    await session.flush()
    box = WarehouseBox(tenant_id=tenant.id, warehouse_id=legacy.id,
                       storage_location_id=old_loc.id, internal_barcode="BOX")
    session.add(box)
    await session.flush()
    session.add_all([
        InventoryBalance(tenant_id=tenant.id, product_id=product.id,
                         storage_location_id=old_loc.id, quantity=619,
                         container_id=box.id, container_kind="box"),
        InventoryBalance(tenant_id=tenant.id, product_id=product.id,
                         storage_location_id=old_loc.id, quantity=8),
        InventoryBalance(tenant_id=tenant.id, product_id=product.id,
                         storage_location_id=new_loc.id, quantity=392),
        InventoryBalance(tenant_id=tenant.id, product_id=other_product.id,
                         storage_location_id=old_loc.id, quantity=0),
    ])
    binding = FbsWarehouseBinding(tenant_id=tenant.id, seller_id=seller.id,
                                  wb_warehouse_id=2067199, wms_warehouse_id=target.id,
                                  stock_sync_enabled=True, served=True)
    session.add(binding)
    order = FbsOrder(tenant_id=tenant.id, seller_id=seller.id, warehouse_id=legacy.id,
                     product_id=product.id, wb_order_id=123, created_at_wb=datetime.now(UTC),
                     deadline_at=datetime.now(UTC), mapping_status="mapped",
                     reserve_status="reserved")
    session.add(order)
    await session.flush()
    session.add(FbsOrderReservation(tenant_id=tenant.id, product_id=product.id,
                                   fbs_order_id=order.id, warehouse_id=legacy.id, quantity=3))
    session.add(InventoryMovement(tenant_id=tenant.id, product_id=product.id,
                                  seller_id=seller.id, warehouse_id=legacy.id,
                                  storage_location_id=old_loc.id, quantity_delta=627,
                                  movement_type="inbound"))
    await session.commit()
    return tenant, legacy, target, old_loc, new_loc, product, box


async def maybe_install(session):
    if session.get_bind().dialect.name == "postgresql":
        await (await session.connection()).run_sync(install_guards)
        await session.commit()


async def cleanup(session):
    await session.rollback()
    await (await session.connection()).run_sync(remove_guards)
    await session.commit()


async def test_repair_conserves_627_containers_other_seller_and_replays(db_session):
    session = db_session
    tenant, legacy, target, old_loc, new_loc, _product, _box = await seed(session)
    run = uuid.uuid4()
    await maybe_install(session)
    try:
        prepared = await repair.prepare(session, run_id=run, tenant_id=tenant.id,
                                        source_id=legacy.id)
        assert prepared["status"] == "prepared"
        assert prepared["before"]["on_hand"] == 1019
        movement_before = (await session.execute(select(
            InventoryMovement.id, InventoryMovement.created_at,
            InventoryMovement.quantity_delta, InventoryMovement.movement_type,
        ))).one()
        await session.commit()
        result = await repair.apply(session, run)
        assert result["status"] == "completed"
        await session.commit()
        assert await repair.apply(session, run) == result  # lost response after commit
        assert (await repair.verify(session, run))["matches_committed_snapshot"]
        assert not (await repair.verify(session, run))["source_exists"]
        assert await session.scalar(select(func.sum(InventoryBalance.quantity))) == 1019
        assert await session.scalar(select(func.count(WarehouseBox.id))) == 1
        assert await session.scalar(select(WarehouseBox.warehouse_id)) == target.id
        assert await session.scalar(select(WarehouseBox.storage_location_id)) == new_loc.id
        assert await session.scalar(select(func.count(BackgroundJob.id))) == 1
        assert await session.scalar(select(FbsWarehouseBinding.stock_sync_enabled)) is True
        assert await session.scalar(select(FbsOrderReservation.warehouse_id)) == target.id
        assert await session.scalar(select(FbsOrderReservation.quantity)) == 3
        assert await session.scalar(select(InventoryMovement.warehouse_id)) == target.id
        assert (await session.execute(select(
            InventoryMovement.id, InventoryMovement.created_at,
            InventoryMovement.quantity_delta, InventoryMovement.movement_type,
        ))).one() == movement_before
        stock = result["result"]["after"]["stock"]
        assert sum(row["free"] for row in stock) == 1016
        await session.commit()
        assert (await repair.rollback(session, run))["status"] == "rolled_back"
        await session.commit()
        assert await session.scalar(select(func.sum(InventoryBalance.quantity)).where(
            InventoryBalance.storage_location_id == old_loc.id)) == 627
        assert await session.scalar(select(WarehouseBox.warehouse_id)) == legacy.id
    finally:
        await cleanup(session)


async def test_drift_and_ambiguous_target_are_durable_blockers(db_session):
    session = db_session
    tenant, legacy, target, *_ = await seed(session, second=True)
    blocked = await repair.prepare(session, run_id=uuid.uuid4(), tenant_id=tenant.id,
                                   source_id=legacy.id)
    assert blocked["status"] == "blocked"
    run = uuid.uuid4()
    prepared = await repair.prepare(session, run_id=run, tenant_id=tenant.id,
                                    source_id=legacy.id, target_id=target.id)
    assert prepared["status"] == "prepared"
    await session.commit()
    await session.execute(update(InventoryBalance).values(quantity=InventoryBalance.quantity + 1))
    await session.commit()
    assert (await repair.apply(session, run))["status"] == "stale"
    await session.commit()
    assert await session.scalar(select(func.count(Warehouse.id))) == 3


async def test_failure_before_commit_leaves_entire_original_graph(db_session):
    session = db_session
    tenant, legacy, _target, old_loc, *_ = await seed(session)
    tenant_id, legacy_id, old_id = tenant.id, legacy.id, old_loc.id
    run = uuid.uuid4()
    await repair.prepare(session, run_id=run, tenant_id=tenant_id, source_id=legacy_id)
    await session.commit()
    await repair.apply(session, run)
    await session.rollback()  # process loss before COMMIT
    assert await session.scalar(select(func.sum(InventoryBalance.quantity)).where(
        InventoryBalance.storage_location_id == old_id)) == 627
    assert (await repair.apply(session, run))["status"] == "completed"
    await session.commit()


async def test_already_repaired_stock_is_not_added_again(db_session):
    session = db_session
    tenant, legacy, target, old_loc, _new_loc, *_ = await seed(session)
    # Equivalent to the completed emergency repair: move the old location's
    # balances/box to physical warehouse without adding any quantity.
    old_loc.code = "emergency-repaired-location"
    old_loc.warehouse_id = target.id
    await session.execute(update(WarehouseBox).values(warehouse_id=target.id))
    await session.commit()
    run = uuid.uuid4()
    await repair.prepare(session, run_id=run, tenant_id=tenant.id, source_id=legacy.id)
    await session.commit()
    await repair.apply(session, run)
    await session.commit()
    assert await session.scalar(select(func.sum(InventoryBalance.quantity))) == 1019


@pytest.mark.parametrize("via_location", [False, True])
@pytest.mark.parametrize("operational_legacy", [False, True])
async def test_bulk_writes_to_known_legacy_uuid_are_rejected(
    db_session, via_location, operational_legacy,
):
    session = db_session
    tenant, legacy, _target, old_loc, _, product, _ = await seed(session)
    legacy.is_operational = operational_legacy
    await session.commit()
    tenant_id, legacy_id, loc_id, product_id = tenant.id, legacy.id, old_loc.id, product.id
    await (await session.connection()).run_sync(install_guards)
    await session.commit()
    try:
        with pytest.raises(IntegrityError, match="physical_warehouse_required"):
            if via_location:
                await session.execute(update(InventoryBalance).where(
                    InventoryBalance.storage_location_id == loc_id).values(quantity=800))
            else:
                await session.execute(insert(StorageLocation).values(
                    id=uuid.uuid4(), tenant_id=tenant_id, warehouse_id=legacy_id,
                    code="ILLEGAL", barcode="ILLEGAL"))
        await session.rollback()
        defect = await get_or_create_defect_location(session, tenant_id)
        assert not is_auto_fbs_wms_warehouse(await session.get(Warehouse, defect.warehouse_id))
        await session.commit()
        with pytest.raises(IntegrityError, match="physical_warehouse_required"):
            async with session.begin_nested():
                await session.execute(insert(InventoryBalance).values(
                    id=uuid.uuid4(), tenant_id=tenant_id, product_id=product_id,
                    storage_location_id=defect.id, quantity=1))
        assert await catalog_service.get_warehouse(session, tenant_id, legacy_id) is None
        assert await catalog_service.get_warehouse(
            session, tenant_id, legacy_id, include_non_operational=True) is not None
    finally:
        await cleanup(session)


async def test_parallel_same_run_returns_one_result(db_session):
    if db_session.get_bind().dialect.name != "postgresql":
        pytest.skip("PostgreSQL transaction concurrency")
    tenant, legacy, *_ = await seed(db_session)
    run = uuid.uuid4()
    await repair.prepare(db_session, run_id=run, tenant_id=tenant.id, source_id=legacy.id)
    await db_session.commit()

    async def apply_once():
        async with SessionLocal() as session, session.begin():
            return await repair.apply(session, run)

    results = await asyncio.gather(apply_once(), apply_once())
    assert results[0] == results[1]
    assert results[0]["result"]["after"]["on_hand"] == 1019


async def test_every_physical_fk_is_guarded_against_internal_insert(db_session):
    from app.models import Base

    session = db_session
    tenant, legacy, _, old_loc, *_ = await seed(session)
    tenant_id, legacy_id, location_id = tenant.id, legacy.id, old_loc.id
    await (await session.connection()).run_sync(install_guards)
    await session.commit()
    try:
        checked = 0
        for table in Base.metadata.tables.values():
            for fk in table.foreign_keys:
                parent = fk.column.table.name
                if parent not in {"warehouses", "storage_locations"}:
                    continue
                with pytest.raises(IntegrityError, match="physical_warehouse_required"):
                    async with session.begin_nested():
                        values = {
                            "id": uuid.uuid4(),
                            fk.parent.name: legacy_id if parent == "warehouses" else location_id,
                        }
                        if "tenant_id" in table.c:
                            values["tenant_id"] = tenant_id
                        await session.execute(insert(table).values(**values))
                checked += 1
        assert checked > 45
    finally:
        await cleanup(session)


async def test_foreign_tenant_and_historical_unique_collision_block_repair(db_session):
    from app.models.warehouse_storage_rack import WarehouseStorageRack

    session = db_session
    tenant, legacy, target, *_ = await seed(session)
    foreign = Tenant(name="Other tenant", slug=uuid.uuid4().hex)
    session.add(foreign)
    await session.flush()
    foreign_target = Warehouse(tenant_id=foreign.id, name="Foreign", code="physical")
    session.add(foreign_target)
    await session.commit()
    report = await repair.prepare(session, run_id=uuid.uuid4(), tenant_id=tenant.id,
                                  source_id=legacy.id, target_id=foreign_target.id)
    assert report["status"] == "blocked"
    session.add_all([
        WarehouseStorageRack(tenant_id=tenant.id, warehouse_id=legacy.id, name="A"),
        WarehouseStorageRack(tenant_id=tenant.id, warehouse_id=target.id, name="A"),
    ])
    await session.commit()
    report = await repair.prepare(session, run_id=uuid.uuid4(), tenant_id=tenant.id,
                                  source_id=legacy.id, target_id=target.id)
    assert report["status"] == "blocked"
    assert any("unique_collision" in blocker for blocker in report["blockers"])


async def test_publication_is_scoped_and_recoverable_after_provider_failure(
    db_session, monkeypatch,
):
    from app.services import physical_warehouse_repair_publish as publisher
    from app.services.fbs_stock_sync_service import FbsStockSyncResult

    tenant, legacy, target, _, _, product, _ = await seed(db_session)
    run = uuid.uuid4()
    await repair.prepare(db_session, run_id=run, tenant_id=tenant.id, source_id=legacy.id)
    await db_session.commit()
    await repair.apply(db_session, run)
    await db_session.commit()
    calls = []

    async def fake_sync(session, tenant_id, seller_id, binding, http_client, *, product_ids):
        calls.append((binding.wb_warehouse_id, product_ids))
        assert binding.wms_warehouse_id == target.id
        if len(calls) == 1:
            raise TimeoutError("response lost")
        return FbsStockSyncResult(products_targeted=1, products_confirmed=1)

    monkeypatch.setattr(publisher, "sync_binding_stocks", fake_sync)
    assert (await publisher.publish(run))["publication"] == "pending"
    with pytest.raises(repair.WarehouseRepairError, match="rollback_blocked_after_publication"):
        await repair.rollback(db_session, run)
    await db_session.commit()
    assert await db_session.scalar(select(func.sum(InventoryBalance.quantity))) == 1019
    assert (await publisher.publish(run))["publication"] == "confirmed"
    assert (await publisher.publish(run))["publication"] == "confirmed"
    assert calls == [(2067199, {product.id}), (2067199, {product.id})]


@pytest.mark.parametrize("marketplace", ["wb", "ozon"])
async def test_binding_rejects_legacy_and_defect_but_defect_service_works(db_session, marketplace):
    from app.services.fbs_warehouse_binding_service import FbsWarehouseBindingError, upsert_binding

    tenant, legacy, _, _, _, product, _ = await seed(db_session)
    defect = await get_or_create_defect_location(db_session, tenant.id)
    await db_session.commit()
    for warehouse_id in (legacy.id, defect.warehouse_id):
        with pytest.raises(FbsWarehouseBindingError, match="warehouse_not_found"):
            await upsert_binding(db_session, tenant.id, product.seller_id, 999,
                                 wms_warehouse_id=warehouse_id, stock_sync_enabled=False,
                                 marketplace=marketplace, external_warehouse_id="999")


async def nested_intake(session, tenant, legacy, product):
    from app.models.inbound_intake import (
        InboundIntakeBox,
        InboundIntakeBoxLine,
        InboundIntakeRequest,
    )
    request = InboundIntakeRequest(tenant_id=tenant.id, warehouse_id=legacy.id,
                                  seller_id=product.seller_id, status="sorting")
    session.add(request)
    await session.flush()
    box = InboundIntakeBox(tenant_id=tenant.id, request_id=request.id,
                          box_number=1, internal_barcode="NESTED")
    session.add(box)
    await session.flush()
    line = InboundIntakeBoxLine(box_id=box.id, product_id=product.id, quantity=1)
    session.add(line)
    await session.commit()
    return request, box, line


async def test_nested_document_write_is_guarded_without_location(db_session):
    from app.models.inbound_intake import InboundIntakeBoxLine

    session = db_session
    tenant, legacy, _, _, _, product, _ = await seed(session)
    _, _, line = await nested_intake(session, tenant, legacy, product)
    line_id = line.id
    await (await session.connection()).run_sync(install_guards)
    await session.commit()
    try:
        with pytest.raises(IntegrityError, match="physical_warehouse_required"):
            await session.execute(update(InboundIntakeBoxLine).where(
                InboundIntakeBoxLine.id == line_id).values(quantity=2))
    finally:
        await cleanup(session)


@pytest.mark.parametrize("insert_new", [False, True])
async def test_nested_document_drift_blocks_rollback(db_session, insert_new):
    from app.models.inbound_intake import InboundIntakeBoxLine

    session = db_session
    tenant, legacy, _, _, _, product, _ = await seed(session)
    _, box, line = await nested_intake(session, tenant, legacy, product)
    run = uuid.uuid4()
    await repair.prepare(session, run_id=run, tenant_id=tenant.id, source_id=legacy.id)
    await session.commit()
    await repair.apply(session, run)
    await session.commit()
    if insert_new:
        other = await session.scalar(select(Product.id).where(Product.id != product.id))
        session.add(InboundIntakeBoxLine(box_id=box.id, product_id=other, quantity=2))
    else:
        line.quantity = 2
    await session.commit()
    with pytest.raises(repair.WarehouseRepairError, match="rollback_blocked_by_later_changes"):
        await repair.rollback(session, run)


async def test_legacy_identity_cannot_be_reactivated_or_renamed(db_session):
    if db_session.get_bind().dialect.name != "postgresql":
        pytest.skip("PostgreSQL immutable warehouse identity")
    session = db_session
    tenant, legacy, _, _old, _, product, _ = await seed(session)
    legacy_id = legacy.id
    await (await session.connection()).run_sync(install_guards)
    await session.commit()
    try:
        for values in ({"is_operational": True}, {"code": "ordinary"}):
            with pytest.raises(IntegrityError, match="warehouse_code_reserved"):
                async with session.begin_nested():
                    await session.execute(update(Warehouse).where(
                        Warehouse.id == legacy_id).values(**values))
        defect = await get_or_create_defect_location(session, tenant.id)
        await session.execute(update(Warehouse).where(
            Warehouse.id == defect.warehouse_id).values(is_operational=True))
        await session.commit()
        assert await catalog_service.get_warehouse(
            session, tenant.id, defect.warehouse_id) is None
        with pytest.raises(IntegrityError, match="physical_warehouse_required"):
            async with session.begin_nested():
                await session.execute(insert(InventoryBalance).values(
                    tenant_id=tenant.id, product_id=product.id,
                    storage_location_id=defect.id, quantity=1))
    finally:
        await cleanup(session)


@pytest.mark.parametrize("source_default", [False, True])
async def test_prepare_evaluates_partial_unique_print_index(db_session, source_default):
    from app.models.print_connection import PrintConnection

    session = db_session
    tenant, legacy, target, *_ = await seed(session)
    for wh, default in [(legacy, source_default), (target, True)]:
        session.add(PrintConnection(
            id=uuid.uuid4(), tenant_id=tenant.id, warehouse_id=wh.id,
            token_hash=uuid.uuid4().hex, pairing_expires_at=datetime.now(UTC),
            queue_name="test", platform="test", is_default=default,
        ))
    await session.commit()
    report = await repair.prepare(session, run_id=uuid.uuid4(), tenant_id=tenant.id,
                                  source_id=legacy.id)
    assert report["status"] == ("blocked" if source_default else "prepared")
    if source_default:
        assert "unique_index_collision:print_connections:uq_print_connection_destination" in (
            report["blockers"])


async def test_binding_rule_drift_blocks_rollback(db_session):
    from app.models.fbs_binding_stock_pool import FbsBindingStockPool

    session = db_session
    tenant, legacy, _, _, _, product, _ = await seed(session)
    run = uuid.uuid4()
    await repair.prepare(session, run_id=run, tenant_id=tenant.id, source_id=legacy.id)
    await session.commit()
    await repair.apply(session, run)
    await session.commit()
    binding = await session.scalar(select(FbsWarehouseBinding))
    session.add(FbsBindingStockPool(tenant_id=tenant.id, product_id=product.id,
                                    binding_id=binding.id, quantity=1))
    await session.commit()
    with pytest.raises(repair.WarehouseRepairError, match="rollback_blocked_by_later_changes"):
        await repair.rollback(session, run)


@pytest.mark.parametrize("seller_specific", [False, True])
async def test_prepare_evaluates_partial_unique_tariff_index(db_session, seller_specific):
    from app.models.billing import BillingTariffVersion

    session = db_session
    tenant, legacy, target, _, _, product, _ = await seed(session)
    for warehouse in (legacy, target):
        session.add(BillingTariffVersion(
            tenant_id=tenant.id, warehouse_id=warehouse.id,
            seller_id=product.seller_id if seller_specific else None,
            service_code="storage_liter_day", unit="liter_day", amount=1,
            valid_from=datetime.now(UTC).date(),
        ))
    await session.commit()
    report = await repair.prepare(session, run_id=uuid.uuid4(), tenant_id=tenant.id,
                                  source_id=legacy.id)
    assert report["status"] == "blocked"
    suffix = "seller" if seller_specific else "common"
    assert ("unique_index_collision:billing_tariff_versions:"
            f"uq_billing_tariff_version_warehouse_{suffix}") in report["blockers"]


async def test_prepare_evaluates_expression_unique_allocation_index(db_session):
    from app.models.marketplace_unload import (
        MarketplaceUnloadPickAllocation,
        MarketplaceUnloadRequest,
    )

    session = db_session
    tenant, legacy, _, old_loc, new_loc, product, _ = await seed(session)
    request = MarketplaceUnloadRequest(tenant_id=tenant.id, warehouse_id=legacy.id,
                                       seller_id=product.seller_id, status="draft")
    session.add(request)
    await session.flush()
    for location in (old_loc, new_loc):
        session.add(MarketplaceUnloadPickAllocation(
            request_id=request.id, product_id=product.id,
            storage_location_id=location.id, quantity=1,
        ))
    await session.commit()
    report = await repair.prepare(session, run_id=uuid.uuid4(), tenant_id=tenant.id,
                                  source_id=legacy.id)
    assert report["status"] == "blocked"
    assert ("unique_index_collision:marketplace_unload_pick_allocations:"
            "uq_mp_unload_pick_req_product_loc_container") in report["blockers"]


@pytest.mark.parametrize("invalid_parent", ["seller", "pallet", "container", "third_warehouse"])
async def test_repair_rejects_foreign_parent_outside_source_target(db_session, invalid_parent):
    from app.models.pallet import Pallet

    session = db_session
    tenant, legacy, _, old_loc, _, _, box = await seed(session)
    foreign = Tenant(name="Foreign", slug=uuid.uuid4().hex)
    session.add(foreign)
    await session.flush()
    parent_tenant = tenant.id if invalid_parent == "third_warehouse" else foreign.id
    seller = Seller(tenant_id=parent_tenant, name="Foreign seller")
    warehouse = Warehouse(tenant_id=parent_tenant, code="foreign", name="Foreign warehouse")
    session.add_all([seller, warehouse])
    await session.flush()
    pallet = Pallet(tenant_id=parent_tenant, warehouse_id=warehouse.id,
                    code="FOREIGN", barcode="FOREIGN")
    foreign_box = WarehouseBox(tenant_id=parent_tenant, warehouse_id=warehouse.id,
                               internal_barcode="FOREIGN")
    session.add_all([pallet, foreign_box])
    await session.flush()
    if invalid_parent == "seller":
        await session.execute(update(InventoryMovement).values(seller_id=seller.id))
    elif invalid_parent == "pallet":
        box.pallet_id = pallet.id
    else:
        await session.execute(update(InventoryBalance).where(
            InventoryBalance.storage_location_id == old_loc.id,
            InventoryBalance.container_id == box.id,
        ).values(container_id=foreign_box.id))
    await session.commit()
    report = await repair.prepare(session, run_id=uuid.uuid4(), tenant_id=tenant.id,
                                  source_id=legacy.id)
    assert report["status"] == "blocked", report


async def test_repair_parent_ownership_drift_between_prepare_and_apply(db_session):
    session = db_session
    tenant, legacy, _, _, _, product, _ = await seed(session)
    foreign = Tenant(name="Foreign", slug=uuid.uuid4().hex)
    session.add(foreign)
    await session.commit()
    run = uuid.uuid4()
    await repair.prepare(session, run_id=run, tenant_id=tenant.id, source_id=legacy.id)
    await session.commit()
    await session.execute(update(Seller).where(Seller.id == product.seller_id)
                          .values(tenant_id=foreign.id))
    await session.commit()
    assert (await repair.apply(session, run))["status"] == "stale"
    assert await session.get(Warehouse, legacy.id) is not None


async def test_repair_checks_all_columns_of_composite_parent(db_session):
    session = db_session
    tenant, _, _, _, _, _, _ = await seed(session)
    foreign = Tenant(name="Foreign", slug=uuid.uuid4().hex)
    session.add(foreign)
    await session.flush()
    product = Product(tenant_id=foreign.id, name="Foreign", sku_code="foreign")
    session.add(product)
    await session.commit()
    # An enabled composite SQL FK already rejects this row. Validate a legacy
    # snapshot defensively too, e.g. imported while constraints were disabled.
    state = await repair._reference_state(session, tenant.id, {
        "billing_ledger_lines": [{"id": str(uuid.uuid4()), "tenant_id": str(tenant.id),
                                  "product_id": str(product.id)}],
    })
    assert any("composite_parent_mismatch:billing_ledger_lines:" in blocker
               for row in state for blocker in row["blockers"])


@pytest.mark.parametrize("parent_kind", ["pallet", "location", "pallet_location"])
async def test_repair_rejects_box_parent_in_third_same_tenant_warehouse(db_session, parent_kind):
    from app.models.pallet import Pallet

    session = db_session
    tenant, legacy, target, _, _, _, box = await seed(session)
    third = Warehouse(tenant_id=tenant.id, code="third", name="Third")
    session.add(third)
    await session.flush()
    location = StorageLocation(tenant_id=tenant.id, warehouse_id=third.id,
                               code="THIRD", barcode="THIRD")
    pallet = Pallet(tenant_id=tenant.id, warehouse_id=third.id, code="THIRD", barcode="THIRD")
    session.add_all([location, pallet])
    await session.flush()
    if parent_kind == "pallet_location":
        pallet.warehouse_id = legacy.id
        pallet.storage_location_id = location.id
        box.pallet_id = pallet.id
    elif parent_kind == "pallet":
        box.pallet_id = pallet.id
    else:
        box.storage_location_id = location.id
    await session.commit()
    report = await repair.prepare(session, run_id=uuid.uuid4(), tenant_id=tenant.id,
                                  source_id=legacy.id, target_id=target.id)
    assert report["status"] == "blocked", report
    assert any("physical_parent_outside_repair_scope:warehouse_boxes:" in blocker
               for blocker in report["blockers"])


@pytest.mark.parametrize("phase", ["apply", "rollback"])
async def test_physical_parent_scope_drift_is_blocked(db_session, phase):
    from app.models.pallet import Pallet

    session = db_session
    tenant, legacy, target, _, _, _, box = await seed(session)
    third = Warehouse(tenant_id=tenant.id, code="third", name="Third")
    pallet = Pallet(tenant_id=tenant.id, warehouse_id=target.id, code="VALID", barcode="VALID")
    session.add_all([third, pallet])
    await session.flush()
    box.pallet_id = pallet.id
    await session.commit()
    run = uuid.uuid4()
    report = await repair.prepare(session, run_id=run, tenant_id=tenant.id,
                                  source_id=legacy.id, target_id=target.id)
    assert report["status"] == "prepared"
    await session.commit()
    if phase == "rollback":
        await repair.apply(session, run)
        await session.commit()
    pallet.warehouse_id = third.id
    await session.commit()
    if phase == "apply":
        assert (await repair.apply(session, run))["status"] == "stale"
    else:
        with pytest.raises(repair.WarehouseRepairError, match="rollback_blocked_by_later_changes"):
            await repair.rollback(session, run)


async def test_historical_movement_container_is_not_current_placement(db_session):
    session = db_session
    tenant, legacy, target, _, _, _, _ = await seed(session)
    third = Warehouse(tenant_id=tenant.id, code="third", name="Third")
    session.add(third)
    await session.flush()
    historical_box = WarehouseBox(tenant_id=tenant.id, warehouse_id=third.id,
                                   internal_barcode="HISTORY")
    session.add(historical_box)
    await session.flush()
    await session.execute(update(InventoryMovement).values(
        container_kind="box", container_id=historical_box.id))
    await session.commit()
    run = uuid.uuid4()
    report = await repair.prepare(session, run_id=run, tenant_id=tenant.id,
                                  source_id=legacy.id, target_id=target.id)
    assert report["status"] == "prepared", report
    await session.commit()
    assert (await repair.apply(session, run))["status"] == "completed"
    assert await session.scalar(select(WarehouseBox.warehouse_id).where(
        WarehouseBox.id == historical_box.id)) == third.id
