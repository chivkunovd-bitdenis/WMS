from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import func, select

from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_supply import FbsSupply
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services import fbs_packaging_integration_service as pack_svc
from app.services import fbs_supply_transfer_service as svc
from app.services.fbs_supply_service import start_supply_work
from app.services.wildberries_errors import WildberriesClientError
from app.services.wildberries_fbs_client import MarketplaceSuppliesPage


async def seed(session):
    tenant = Tenant(name="Transfer", slug=uuid.uuid4().hex)
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(tenant=tenant, name="WH", code=uuid.uuid4().hex)
    source = FbsSupply(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        wb_supply_id="WB-source",
        name="Source",
        status="assembling",
        delivery_type="warehouse_sc",
    )
    target = FbsSupply(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        wb_supply_id="WB-target",
        name="Target",
        status="draft",
        delivery_type="warehouse_sc",
    )
    session.add_all([tenant, seller, warehouse, source, target])
    await session.flush()
    orders = [
        FbsOrder(
            tenant_id=tenant.id,
            seller_id=seller.id,
            warehouse_id=warehouse.id,
            wb_order_id=i,
            supply_id=source.id,
            wb_supply_id=source.wb_supply_id,
            status="assembling",
            mapping_status="mapped",
            reserve_status="reserved",
            created_at_wb=datetime.now(UTC),
            deadline_at=datetime.now(UTC) + timedelta(days=1),
            pack_status="packed" if i == 1 else "pending",
        )
        for i in [1, 2]
    ]
    session.add_all(orders)
    await session.flush()
    marking = FbsOrderMarking(
        tenant_id=tenant.id,
        order_id=orders[0].id,
        kind="kiz",
        value="unchanged-kiz",
        meta_status="confirmed",
    )
    session.add(marking)
    await session.commit()
    return tenant, source, target, orders, marking


async def invoke(session, tenant, source, target, orders, key="transfer"):
    async with httpx.AsyncClient() as client:
        return await svc.transfer_orders(
            session,
            tenant.id,
            source.id,
            order_ids=[o.id for o in orders],
            target_supply_id=target.id if target else None,
            idempotency_key=key,
            actor_user_id=uuid.uuid4(),
            http_client=client,
        )


@pytest.mark.asyncio
async def test_transfer_preserves_kiz_packing_and_replays_once(db_session, monkeypatch):
    tenant, source, target, orders, marking = await seed(db_session)
    monkeypatch.setattr(svc, "_require_marketplace_token", AsyncMock(return_value="test"))
    patch = AsyncMock()
    monkeypatch.setattr(svc, "add_orders_to_marketplace_supply", patch)
    monkeypatch.setattr(svc, "fetch_marketplace_supply_order_ids", AsyncMock(return_value=[1]))
    result = await invoke(db_session, tenant, source, target, orders[:1])
    assert result["state"] == "confirmed"
    assert orders[0].supply_id == target.id and orders[1].supply_id == source.id
    assert orders[0].pack_status == "packed" and orders[0].reserve_status == "reserved"
    await db_session.refresh(marking)
    assert marking.value == "unchanged-kiz" and marking.order_id == orders[0].id
    assert target.packaging_task_id is None and target.status == "draft"
    assert await invoke(db_session, tenant, source, target, orders[:1]) == result
    assert patch.await_count == 1


@pytest.mark.asyncio
async def test_unknown_patch_partial_then_reconcile_without_replay(db_session, monkeypatch):
    tenant, source, target, orders, _ = await seed(db_session)
    monkeypatch.setattr(svc, "_require_marketplace_token", AsyncMock(return_value="test"))
    patch = AsyncMock(side_effect=WildberriesClientError("transport_error"))
    monkeypatch.setattr(svc, "add_orders_to_marketplace_supply", patch)
    monkeypatch.setattr(
        svc, "fetch_marketplace_supply_order_ids", AsyncMock(side_effect=[[1], [1, 2]])
    )
    result = await invoke(db_session, tenant, source, target, orders)
    assert result["state"] == "pending_confirmation"
    assert result["transferred_order_ids"] == [str(orders[0].id)]
    assert result["pending_order_ids"] == [str(orders[1].id)]
    assert orders[0].supply_id == target.id and orders[1].supply_id == source.id
    result = await invoke(db_session, tenant, source, target, orders, key="browser-reloaded")
    assert result["state"] == "confirmed" and patch.await_count == 1


@pytest.mark.asyncio
async def test_unknown_create_recovers_named_supply_without_second_post(db_session, monkeypatch):
    tenant, source, _, orders, _ = await seed(db_session)
    monkeypatch.setattr(svc, "_require_marketplace_token", AsyncMock(return_value="test"))
    create = AsyncMock(side_effect=WildberriesClientError("transport_error"))
    monkeypatch.setattr(svc, "create_marketplace_supply", create)
    patch = AsyncMock()
    monkeypatch.setattr(svc, "add_orders_to_marketplace_supply", patch)
    monkeypatch.setattr(svc, "fetch_marketplace_supply_order_ids", AsyncMock(return_value=[1, 2]))
    assert (await invoke(db_session, tenant, source, None, orders))[
        "state"
    ] == "pending_confirmation"
    operation = await db_session.scalar(select(FbsWbOperation))
    name = operation.request_summary_json["name"]
    monkeypatch.setattr(
        svc,
        "fetch_marketplace_supplies_page",
        AsyncMock(
            return_value=MarketplaceSuppliesPage(
                supplies={"WB-created": (name, False)}, next_cursor=None
            )
        ),
    )
    result = await invoke(db_session, tenant, source, None, orders)
    assert result["state"] == "confirmed" and create.await_count == 1 and patch.await_count == 1
    assert await db_session.scalar(select(func.count()).select_from(FbsSupply)) == 3


@pytest.mark.asyncio
async def test_known_rejection_is_failed_not_unknown(db_session, monkeypatch):
    tenant, source, target, orders, _ = await seed(db_session)
    monkeypatch.setattr(svc, "_require_marketplace_token", AsyncMock(return_value="test"))
    monkeypatch.setattr(
        svc,
        "add_orders_to_marketplace_supply",
        AsyncMock(side_effect=WildberriesClientError("upstream_error", status_code=409)),
    )
    monkeypatch.setattr(svc, "fetch_marketplace_supply_order_ids", AsyncMock(return_value=[]))
    result = await invoke(db_session, tenant, source, target, orders)
    assert result["state"] == "failed" and not result["pending_order_ids"]
    assert len(result["failed_order_ids"]) == 2
    assert all(o.supply_id == source.id for o in orders)


@pytest.mark.asyncio
async def test_targets_and_mutations_enforce_scope_and_draft(db_session, monkeypatch):
    tenant, source, target, orders, _ = await seed(db_session)
    monkeypatch.setattr(svc, "_require_marketplace_token", AsyncMock(return_value="test"))
    patch = AsyncMock()
    monkeypatch.setattr(svc, "add_orders_to_marketplace_supply", patch)
    assert [
        row["id"] for row in await svc.list_transfer_targets(db_session, tenant.id, source.id)
    ] == [str(target.id)]
    target.status = "assembling"
    await db_session.commit()
    assert await svc.list_transfer_targets(db_session, tenant.id, source.id) == []
    with pytest.raises(svc.FbsSupplyError, match="invalid_transfer_target"):
        await invoke(db_session, tenant, source, target, orders)
    with pytest.raises(svc.FbsSupplyError, match="supply_not_found"):
        await svc.list_transfer_targets(db_session, uuid.uuid4(), source.id)
    patch.assert_not_awaited()


@pytest.mark.asyncio
async def test_packed_transfer_can_start_target_without_second_fulfillment(db_session, monkeypatch):
    tenant, source, target, orders, marking = await seed(db_session)
    product = Product(
        tenant_id=tenant.id, seller_id=source.seller_id, name="Packed product", sku_code="TRANSFER"
    )
    location = StorageLocation(
        tenant_id=tenant.id,
        warehouse_id=source.warehouse_id,
        code="TRANSFER",
        barcode="TRANSFER-LOCATION",
    )
    task = PackagingTask(tenant_id=tenant.id, warehouse_id=source.warehouse_id, status="draft")
    db_session.add_all([product, location, task])
    await db_session.flush()
    line = PackagingTaskLine(
        task_id=task.id,
        product_id=product.id,
        storage_location_id=location.id,
        qty_total=2,
        qty_confirmed_packed=0,
        qty_packed_in_task=1,
    )
    db_session.add(line)
    await db_session.flush()
    source.packaging_task_id = task.id
    for order in orders:
        order.product_id = product.id
    fulfillment = FbsPackagingFulfillment(
        tenant_id=tenant.id,
        fbs_order_id=orders[0].id,
        packaging_task_id=task.id,
        packaging_task_line_id=line.id,
        fulfilled_at=datetime.now(UTC),
        pack_idempotency_key="original-pack",
    )
    db_session.add(fulfillment)
    await db_session.commit()
    monkeypatch.setattr(svc, "_require_marketplace_token", AsyncMock(return_value="test"))
    monkeypatch.setattr(svc, "add_orders_to_marketplace_supply", AsyncMock())
    monkeypatch.setattr(svc, "fetch_marketplace_supply_order_ids", AsyncMock(return_value=[1]))
    result = await invoke(db_session, tenant, source, target, orders[:1])
    assert result["state"] == "confirmed"
    await start_supply_work(db_session, tenant.id, target.id, actor_user_id=None)
    await db_session.refresh(fulfillment)
    await db_session.refresh(marking)
    assert fulfillment.packaging_task_id == task.id  # original work/billing history
    await db_session.refresh(line)
    assert line.qty_total == 2 and line.qty_packed_in_task == 1
    assert line.qty_total - line.qty_confirmed_packed - line.qty_packed_in_task == 1
    assert marking.value == "unchanged-kiz" and marking.order_id == orders[0].id
    assert orders[0].pack_status == "packed"
    assert await db_session.scalar(select(func.count()).select_from(FbsPackagingFulfillment)) == 1
    loaded = await pack_svc._load_supply(db_session, tenant.id, target.id, with_orders=True)
    with pytest.raises(pack_svc.FbsPackagingIntegrationError, match="order_already_packed"):
        await pack_svc._resolve_order_for_pack_unit(
            db_session,
            loaded,
            product.id,
            explicit_order_id=orders[0].id,
        )


@pytest.mark.asyncio
async def test_crash_between_batches_resumes_only_unsent_batch(db_session, monkeypatch):
    tenant, source, target, orders, _ = await seed(db_session)
    template = orders[1]
    for i in range(3, 102):
        order = FbsOrder(
            tenant_id=tenant.id,
            seller_id=source.seller_id,
            warehouse_id=source.warehouse_id,
            wb_order_id=i,
            supply_id=source.id,
            wb_supply_id=source.wb_supply_id,
            status="assembling",
            mapping_status="mapped",
            reserve_status="reserved",
            created_at_wb=template.created_at_wb,
            deadline_at=template.deadline_at,
        )
        db_session.add(order)
        orders.append(order)
    await db_session.commit()
    monkeypatch.setattr(svc, "_require_marketplace_token", AsyncMock(return_value="test"))
    # Process stops after the first dispatch; its result is deliberately unknown.
    patch = AsyncMock(side_effect=RuntimeError("process stopped"))
    monkeypatch.setattr(svc, "add_orders_to_marketplace_supply", patch)
    with pytest.raises(RuntimeError, match="process stopped"):
        await invoke(db_session, tenant, source, target, orders)
    first_batch = set(patch.call_args.kwargs["order_ids"])
    assert len(first_batch) == 100
    read = AsyncMock(side_effect=[list(first_batch), list(range(1, 102))])
    monkeypatch.setattr(svc, "fetch_marketplace_supply_order_ids", read)
    patch = AsyncMock()
    monkeypatch.setattr(svc, "add_orders_to_marketplace_supply", patch)
    result = await invoke(db_session, tenant, source, target, orders)
    assert result["state"] == "confirmed"
    assert patch.await_count == 1
    assert set(patch.call_args.kwargs["order_ids"]) == set(range(1, 102)) - first_batch


@pytest.mark.asyncio
async def test_target_started_during_wb_wait_receives_incoming_task_line(db_session, monkeypatch):
    tenant, source, target, orders, _ = await seed(db_session)
    product = Product(
        tenant_id=tenant.id, seller_id=source.seller_id, name="Incoming", sku_code="INCOMING"
    )
    db_session.add(product)
    await db_session.flush()
    orders[1].product_id = product.id
    await db_session.commit()
    monkeypatch.setattr(svc, "_require_marketplace_token", AsyncMock(return_value="test"))

    async def start_target(*args, **kwargs):
        await pack_svc.create_packaging_task_for_supply(db_session, tenant.id, target.id)
        target.status = "assembling"
        await db_session.commit()

    monkeypatch.setattr(svc, "add_orders_to_marketplace_supply", start_target)
    monkeypatch.setattr(svc, "fetch_marketplace_supply_order_ids", AsyncMock(return_value=[2]))
    result = await invoke(db_session, tenant, source, target, orders[1:])
    assert result["state"] == "confirmed"
    assert orders[1].status == "assembling"
    lines = list(
        await db_session.scalars(
            select(PackagingTaskLine).where(
                PackagingTaskLine.task_id == target.packaging_task_id,
            )
        )
    )
    assert len(lines) == 1 and lines[0].product_id == product.id and lines[0].qty_total == 1
