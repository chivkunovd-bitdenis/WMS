from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.cli.repair_wb_sold_writeoffs import (
    Selection,
    audit_id,
    manifest_sha256,
    prepare,
    repair,
    reversal_id,
)
from app.db.session import SessionLocal
from app.models.document_event import DocumentEvent
from app.models.fbs_order import FbsOrder
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_count import InventoryCount, InventoryCountLine
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse

PAST = datetime(2026, 9, 2, 10, tzinfo=UTC)
LATER = datetime(2026, 9, 21, 10, tzinfo=UTC)
EVIDENCE = "WMS-503 confirmed historical automatic WB sold write-off without local handover"


async def seed(session, *, recount=False, uncounted=False, packed_negative=False):
    tenant = Tenant(id=uuid.uuid4(), name="Repair test", slug=uuid.uuid4().hex)
    seller = Seller(id=uuid.uuid4(), tenant_id=tenant.id, name="Seller")
    warehouse = Warehouse(id=uuid.uuid4(), tenant_id=tenant.id, code="W", name="Warehouse")
    location = StorageLocation(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        warehouse_id=warehouse.id,
        code="SORT",
        barcode=uuid.uuid4().hex,
    )
    product = Product(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        seller_id=seller.id,
        name="Bottle",
        sku_code=uuid.uuid4().hex,
    )
    user = User(id=uuid.uuid4(), tenant_id=tenant.id, password_hash="unused", role="ff_admin")
    session.add_all([tenant, seller, warehouse, location, product, user])
    await session.flush()
    order = FbsOrder(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        product_id=product.id,
        wb_order_id=123,
        marketplace="wb",
        created_at_wb=PAST,
        deadline_at=PAST,
        mapping_status="mapped",
        reserve_status="released",
        status="done",
        wb_status="sold",
    )
    original = InventoryMovement(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        product_id=product.id,
        seller_id=seller.id,
        storage_location_id=location.id,
        warehouse_id=warehouse.id,
        quantity_delta=-1,
        movement_type="fbs_shipment",
        created_at=PAST,
    )
    session.add_all([order, original])
    await session.flush()
    ledger = FbsShipmentReversalLedger(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        fbs_order_id=order.id,
        product_id=product.id,
        storage_location_id=location.id,
        quantity=1,
        source_mode="forced_negative",
        negative_quantity=1,
        shortage_quantity=1,
        shipment_movement_id=original.id,
        created_at=PAST,
        written_off_at=PAST,
    )
    balance = InventoryBalance(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        product_id=product.id,
        storage_location_id=location.id,
        quantity=199,
        quantity_unpacked=200 if packed_negative else 199,
        quantity_packed=-1 if packed_negative else 0,
    )
    intake = InventoryMovement(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        product_id=product.id,
        seller_id=seller.id,
        storage_location_id=location.id,
        warehouse_id=warehouse.id,
        quantity_delta=200,
        movement_type="inbound_intake",
        created_at=LATER,
    )
    session.add_all([ledger, balance, intake])
    line = None
    if recount or uncounted:
        count = InventoryCount(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            created_by_user_id=user.id,
            status="posted",
            source="warehouse",
            created_at=LATER,
            posted_at=LATER,
        )
        line = InventoryCountLine(
            id=uuid.uuid4(),
            count_id=count.id,
            product_id=product.id,
            storage_location_id=location.id,
            expected_quantity=199,
            actual_quantity=200 if recount else None,
            posted_delta=1 if recount else None,
        )
        session.add_all([count, line])
        if recount:
            balance.quantity = balance.quantity_unpacked = 200
            session.add(
                InventoryMovement(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    product_id=product.id,
                    seller_id=seller.id,
                    storage_location_id=location.id,
                    warehouse_id=warehouse.id,
                    quantity_delta=1,
                    movement_type="inventory_count",
                    inventory_count_line_id=line.id,
                    created_at=LATER,
                )
            )
    await session.commit()
    return ledger.id, balance.id, line.id if line else None


@pytest.mark.asyncio
async def test_exact_correction_replays_after_lost_response_and_preserves_history(db_session):
    ledger_id, balance_id, _ = await seed(db_session)
    plan = await prepare(db_session, [Selection(ledger_id=ledger_id, evidence=EVIDENCE)])
    digest = manifest_sha256(plan)
    checked = await repair(db_session, plan, expected_sha256=digest)
    assert checked["restored_units"] == 1
    assert (await db_session.get(InventoryBalance, balance_id)).quantity == 199
    await db_session.rollback()
    async with SessionLocal() as session, session.begin():
        result = await repair(session, plan, expected_sha256=digest, apply=True)
        assert result["balances"][0]["after"] == 200
        assert not session.info.get("fbs_stock_publish_pending")
    async with SessionLocal() as session, session.begin():
        repeated = await repair(session, plan, expected_sha256=digest, apply=True)
        assert repeated["status"] == "already_applied"
        assert (await session.get(InventoryBalance, balance_id)).quantity == 200
        assert await session.scalar(select(func.count()).select_from(InventoryMovement)) == 3
        assert (await session.get(DocumentEvent, audit_id(ledger_id))).payload_json[
            "manifest_sha256"
        ] == digest
        ledger = await session.get(FbsShipmentReversalLedger, ledger_id)
        original = await session.get(InventoryMovement, ledger.shipment_movement_id)
        assert original.quantity_delta == -1
        assert ledger.reversal_movement_id == reversal_id(ledger_id)


@pytest.mark.asyncio
async def test_snapshot_change_digest_mismatch_and_transaction_rollback(db_session):
    ledger_id, balance_id, _ = await seed(db_session)
    plan = await prepare(db_session, [Selection(ledger_id=ledger_id, evidence=EVIDENCE)])
    with pytest.raises(ValueError, match="SHA256"):
        await repair(db_session, plan, expected_sha256="bad", apply=True)
    balance = await db_session.get(InventoryBalance, balance_id)
    balance.quantity += 1
    balance.quantity_unpacked += 1
    await db_session.flush()
    with pytest.raises(ValueError, match="evidence changed"):
        await repair(db_session, plan, expected_sha256=manifest_sha256(plan), apply=True)
    await db_session.rollback()
    async with SessionLocal() as session:
        with pytest.raises(RuntimeError, match="lost transaction"):
            async with session.begin():
                await repair(session, plan, expected_sha256=manifest_sha256(plan), apply=True)
                raise RuntimeError("lost transaction")
    async with SessionLocal() as session:
        assert (await session.get(InventoryBalance, balance_id)).quantity == 199
        assert (await session.get(FbsShipmentReversalLedger, ledger_id)).reversed_at is None
        assert await session.get(DocumentEvent, audit_id(ledger_id)) is None
        assert await session.get(InventoryMovement, reversal_id(ledger_id)) is None


@pytest.mark.asyncio
async def test_real_recount_absorbs_correction_without_adding_inventory(db_session):
    ledger_id, balance_id, line_id = await seed(db_session, recount=True)
    with pytest.raises(ValueError, match="physical recount"):
        await prepare(db_session, [Selection(ledger_id=ledger_id, evidence=EVIDENCE)])
    choice = Selection(
        ledger_id=ledger_id,
        action="absorbed_by_inventory_count",
        count_line_id=line_id,
        evidence=EVIDENCE,
    )
    plan = await prepare(db_session, [choice])
    result = await repair(db_session, plan, expected_sha256=manifest_sha256(plan), apply=True)
    await db_session.commit()
    assert result["restored_units"] == 0 and result["absorbed_units"] == 1
    assert (await db_session.get(InventoryBalance, balance_id)).quantity == 200
    assert await db_session.get(InventoryMovement, reversal_id(ledger_id)) is None
    assert (await repair(db_session, plan, expected_sha256=manifest_sha256(plan), apply=True))[
        "status"
    ] == "already_applied"


@pytest.mark.asyncio
async def test_uncounted_null_line_is_not_a_reset(db_session):
    ledger_id, _, line_id = await seed(db_session, uncounted=True)
    choice = Selection(
        ledger_id=ledger_id,
        action="absorbed_by_inventory_count",
        count_line_id=line_id,
        evidence=EVIDENCE,
    )
    with pytest.raises(ValueError, match="completed physical recount"):
        await prepare(db_session, [choice])
    plan = await prepare(db_session, [Selection(ledger_id=ledger_id, evidence=EVIDENCE)])
    result = await repair(db_session, plan, expected_sha256=manifest_sha256(plan), apply=True)
    assert result["restored_units"] == 1


@pytest.mark.asyncio
async def test_split_dimensions_restore_explicit_packed_debt(db_session):
    ledger_id, balance_id, _ = await seed(db_session, packed_negative=True)
    plan = await prepare(
        db_session, [Selection(ledger_id=ledger_id, evidence=EVIDENCE, packed_quantity=1)]
    )
    await repair(db_session, plan, expected_sha256=manifest_sha256(plan), apply=True)
    balance = await db_session.get(InventoryBalance, balance_id)
    assert (balance.quantity, balance.quantity_unpacked, balance.quantity_packed) == (200, 200, 0)


@pytest.mark.asyncio
async def test_silent_previous_repair_and_tenant_mismatch_are_rejected(db_session):
    ledger_id, balance_id, _ = await seed(db_session)
    balance = await db_session.get(InventoryBalance, balance_id)
    balance.quantity += 1
    balance.quantity_unpacked += 1
    await db_session.commit()
    plan = await prepare(db_session, [Selection(ledger_id=ledger_id, evidence=EVIDENCE)])
    with pytest.raises(ValueError, match="previous silent repair"):
        await repair(db_session, plan, expected_sha256=manifest_sha256(plan), apply=True)
    ledger = await db_session.get(FbsShipmentReversalLedger, ledger_id)
    ledger.tenant_id = uuid.uuid4()
    await db_session.flush()
    with pytest.raises(ValueError, match=r"scope|mismatch"):
        await prepare(db_session, [Selection(ledger_id=ledger_id, evidence=EVIDENCE)])
