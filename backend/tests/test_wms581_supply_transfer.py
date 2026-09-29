"""WMS-581: перенос заказов WB в открытые поставки «в работе» и название новой поставки."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import func, select

from app.models.fbs_order import FbsOrder
from app.models.fbs_order_pick import FbsOrderPick
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_packing_box import FbsPackingBox, FbsPackingBoxItem
from app.models.fbs_supply import FbsSupply
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.models.warehouse_box import WarehouseBox
from app.services import fbs_supply_transfer_service as svc
from app.services.fbs_supply_service import start_supply_work
from app.services.fbs_workspace_service import get_supply_workspace
from app.services.packaging_task_service import pack_all_and_complete_fbs_task
from app.services.wildberries_errors import WildberriesClientError
from app.services.wildberries_fbs_client import MarketplaceSuppliesPage, _parse_supplies_page
from tests.test_fbs_supply_transfer import seed

KOLEDINO = 574101
TULA = 574103


def _supply(source: FbsSupply, **values) -> FbsSupply:
    return FbsSupply(
        tenant_id=source.tenant_id,
        seller_id=source.seller_id,
        warehouse_id=source.warehouse_id,
        delivery_type="warehouse_sc",
        **values,
    )


def _order(source: FbsSupply, supply: FbsSupply, wb_order_id: int, **values) -> FbsOrder:
    return FbsOrder(
        tenant_id=source.tenant_id,
        seller_id=source.seller_id,
        warehouse_id=source.warehouse_id,
        wb_order_id=wb_order_id,
        supply_id=supply.id,
        wb_supply_id=supply.wb_supply_id,
        status="assembling",
        mapping_status="mapped",
        reserve_status="reserved",
        created_at_wb=datetime.now(UTC),
        deadline_at=datetime.now(UTC) + timedelta(days=1),
        **values,
    )


async def _in_work_pair(session):
    """A (source) и B — обе «в работе», склад WB Коледино; у B есть задание упаковки."""
    tenant, source, _draft, orders, marking = await seed(session)
    for order in orders:
        order.wb_warehouse_id = KOLEDINO
    product = Product(
        tenant_id=tenant.id, seller_id=source.seller_id, name="Футболка", sku_code="WMS581"
    )
    location = StorageLocation(
        tenant_id=tenant.id,
        warehouse_id=source.warehouse_id,
        code="WMS581",
        barcode="WMS581-LOCATION",
    )
    task = PackagingTask(tenant_id=tenant.id, warehouse_id=source.warehouse_id, status="draft")
    session.add_all([product, location, task])
    await session.flush()
    in_work = _supply(
        source,
        wb_supply_id="WB-GI-B",
        name="Коледино утро",
        status="assembling",
        packaging_task_id=task.id,
    )
    session.add(in_work)
    await session.flush()
    resident = _order(source, in_work, 50, wb_warehouse_id=KOLEDINO, product_id=product.id)
    session.add(resident)
    await session.flush()
    session.add(
        PackagingTaskLine(
            task_id=task.id,
            product_id=product.id,
            storage_location_id=location.id,
            qty_total=1,
            qty_suggested_packed=0,
        )
    )
    await session.commit()
    return tenant, source, in_work, orders, marking, product, task


async def _transfer(session, tenant, source, orders, *, target=None, name=None, key="wms581"):
    async with httpx.AsyncClient() as client:
        return await svc.transfer_orders(
            session,
            tenant.id,
            source.id,
            order_ids=[order.id for order in orders],
            target_supply_id=target.id if target else None,
            idempotency_key=key,
            actor_user_id=uuid.uuid4(),
            http_client=client,
            name=name,
        )


@pytest.mark.asyncio
async def test_c1_targets_are_open_compatible_supplies_in_any_working_state(
    db_session, monkeypatch
):
    tenant, source, in_work, orders, _, _, _ = await _in_work_pair(db_session)
    other_wb_warehouse = _supply(source, wb_supply_id="WB-GI-C", name="C", status="assembling")
    delivered = _supply(source, wb_supply_id="WB-GI-D", name="D", status="in_delivery")
    db_session.add_all([other_wb_warehouse, delivered])
    await db_session.flush()
    db_session.add_all(
        [
            _order(source, other_wb_warehouse, 60, wb_warehouse_id=TULA),
            _order(source, delivered, 70, wb_warehouse_id=KOLEDINO),
        ]
    )
    await db_session.commit()

    targets = await svc.list_transfer_targets(
        db_session, tenant.id, source.id, [orders[0].id]
    )
    ids = [row["id"] for row in targets]
    assert str(in_work.id) in ids  # B: в работе, с заданием упаковки
    assert str(other_wb_warehouse.id) not in ids  # C: другой склад WB
    assert str(delivered.id) not in ids  # D: передана в доставку
    assert str(source.id) not in ids  # A: текущая
    row = next(row for row in targets if row["id"] == str(in_work.id))
    assert row["wb_supply_id"] == "WB-GI-B" and row["created_at"]

    # Без явного выбора сверка идёт по заказам исходной поставки — тот же результат.
    assert str(in_work.id) in [
        row["id"] for row in await svc.list_transfer_targets(db_session, tenant.id, source.id)
    ]
    # Несовместимую цель сервер не принимает и в WB не ходит.
    monkeypatch.setattr(svc, "_require_marketplace_token", AsyncMock(return_value="test"))
    create = AsyncMock()
    patch = AsyncMock()
    monkeypatch.setattr(svc, "create_marketplace_supply", create)
    monkeypatch.setattr(svc, "add_orders_to_marketplace_supply", patch)
    with pytest.raises(svc.FbsSupplyError, match="order_incompatible"):
        await _transfer(db_session, tenant, source, orders[:1], target=other_wb_warehouse)
    with pytest.raises(svc.FbsSupplyError, match="invalid_transfer_target"):
        await _transfer(db_session, tenant, source, orders[:1], target=delivered, key="d")
    create.assert_not_awaited()
    patch.assert_not_awaited()


@pytest.mark.asyncio
async def test_c2_transfer_into_supply_in_work_keeps_kiz_sticker_pick_and_packing(
    db_session, monkeypatch
):
    tenant, source, in_work, orders, marking, product, task = await _in_work_pair(db_session)
    moved = orders[0]
    moved.product_id = product.id
    moved.sticker_code = "5694425 3074"
    moved.pick_status = "picked"
    box = WarehouseBox(
        tenant_id=tenant.id, warehouse_id=source.warehouse_id, internal_barcode="WMS581-BOX"
    )
    db_session.add(box)
    await db_session.flush()
    packing_box = FbsPackingBox(
        tenant_id=tenant.id, supply_id=source.id, warehouse_box_id=box.id, box_number=1
    )
    db_session.add(packing_box)
    await db_session.flush()
    location_id = await db_session.scalar(
        select(StorageLocation.id).where(StorageLocation.code == "WMS581")
    )
    db_session.add_all(
        [
            FbsPackingBoxItem(tenant_id=tenant.id, box_id=packing_box.id, fbs_order_id=moved.id),
            FbsOrderPick(
                tenant_id=tenant.id,
                fbs_supply_id=source.id,
                fbs_order_id=moved.id,
                product_id=product.id,
                source_storage_location_id=location_id,
                sorting_storage_location_id=location_id,
                picked_at=datetime.now(UTC),
                scan_idempotency_key="wms581-pick",
            ),
        ]
    )
    await db_session.commit()
    monkeypatch.setattr(svc, "_require_marketplace_token", AsyncMock(return_value="test"))
    patch = AsyncMock()
    monkeypatch.setattr(svc, "add_orders_to_marketplace_supply", patch)
    monkeypatch.setattr(
        svc, "fetch_marketplace_supply_order_ids", AsyncMock(return_value=[1, 50])
    )

    result = await _transfer(db_session, tenant, source, [moved], target=in_work)

    assert result["state"] == "confirmed" and result["target_created"] is False
    assert patch.call_args.kwargs["supply_id"] == "WB-GI-B"
    assert moved.supply_id == in_work.id and moved.wb_supply_id == "WB-GI-B"
    assert moved.pack_status == "packed" and moved.sticker_code == "5694425 3074"
    assert moved.status == "assembling"
    await db_session.refresh(marking)
    assert marking.order_id == moved.id and marking.value == "unchanged-kiz"
    pick = await db_session.scalar(
        select(FbsOrderPick).where(FbsOrderPick.fbs_order_id == moved.id)
    )
    assert pick is not None and pick.fbs_supply_id == in_work.id
    assert (
        await db_session.scalar(
            select(func.count()).select_from(FbsPackingBoxItem).where(
                FbsPackingBoxItem.fbs_order_id == moved.id
            )
        )
        == 0
    )
    line = await db_session.scalar(
        select(PackagingTaskLine).where(PackagingTaskLine.task_id == task.id)
    )
    assert line is not None and line.qty_total == 2  # заказ попал в упаковку B
    # Название существующей поставки не меняется (R4).
    await db_session.refresh(in_work)
    assert in_work.name == "Коледино утро" and in_work.packaging_task_id == task.id

    target_view = await get_supply_workspace(db_session, tenant.id, in_work.id)
    moved_row = next(row for row in target_view["orders"] if row["id"] == str(moved.id))
    assert moved_row["sticker"]["code"] == "5694425 3074"
    source_view = await get_supply_workspace(db_session, tenant.id, source.id)
    assert str(moved.id) not in {row["id"] for row in source_view["orders"]}
    assert all(
        str(moved.id) not in str(box_row) for box_row in source_view["boxes"]
    )


@pytest.mark.asyncio
async def test_c3_new_supply_gets_typed_name_or_short_number(db_session, monkeypatch):
    tenant, source, _, orders, _ = await seed(db_session)
    monkeypatch.setattr(svc, "_require_marketplace_token", AsyncMock(return_value="test"))
    create = AsyncMock(side_effect=[{"id": "WB-GI-N1"}, {"id": "WB-GI-N2"}])
    monkeypatch.setattr(svc, "create_marketplace_supply", create)
    monkeypatch.setattr(svc, "fetch_marketplace_supplies_page", AsyncMock(return_value=_page()))
    monkeypatch.setattr(svc, "add_orders_to_marketplace_supply", AsyncMock())
    monkeypatch.setattr(
        svc, "fetch_marketplace_supply_order_ids", AsyncMock(side_effect=[[1], [2]])
    )

    named = await _transfer(db_session, tenant, source, orders[:1], name="  Коледино 29.09 ")
    assert named["state"] == "confirmed" and named["target_created"] is True
    assert named["target_supply_name"] == "Коледино 29.09"
    assert named["target_wb_supply_id"] == "WB-GI-N1"
    assert create.await_args_list[0].kwargs["name"] == "Коледино 29.09"
    created = await db_session.get(FbsSupply, uuid.UUID(named["target_supply_id"]))
    assert created is not None and created.name == "Коледино 29.09"

    unnamed = await _transfer(db_session, tenant, source, orders[1:], key="second")
    assert unnamed["state"] == "confirmed"
    assert re.fullmatch(r"Новая поставка № \d{5}", unnamed["target_supply_name"])
    assert create.await_args_list[1].kwargs["name"] == unnamed["target_supply_name"]
    assert not any(
        (supply.name or "").startswith("Перенос")
        for supply in await db_session.scalars(select(FbsSupply))
    )


def _page(*rows: tuple[str, str, datetime]) -> MarketplaceSuppliesPage:
    return _parse_supplies_page(
        {
            "supplies": [
                {"id": sid, "name": name, "done": False, "createdAt": created.isoformat()}
                for sid, name, created in rows
            ],
            "next": 0,
        }
    )


async def _lost_create(db_session, monkeypatch, name, existing=()):
    """Create request is lost; `existing` — WB supplies already there before it."""
    tenant, source, _, orders, _ = await seed(db_session)
    monkeypatch.setattr(svc, "_require_marketplace_token", AsyncMock(return_value="test"))
    monkeypatch.setattr(
        svc, "fetch_marketplace_supplies_page", AsyncMock(return_value=_page(*existing))
    )
    create = AsyncMock(side_effect=WildberriesClientError("transport_error"))
    monkeypatch.setattr(svc, "create_marketplace_supply", create)
    patch = AsyncMock()
    monkeypatch.setattr(svc, "add_orders_to_marketplace_supply", patch)
    monkeypatch.setattr(svc, "fetch_marketplace_supply_order_ids", AsyncMock(return_value=[1, 2]))
    first = await _transfer(db_session, tenant, source, orders, name=name)
    assert first["state"] == "pending_confirmation"
    return tenant, source, orders, create, patch


@pytest.mark.asyncio
async def test_c5_lost_create_with_typed_name_recovers_only_our_supply(db_session, monkeypatch):
    tenant, source, orders, create, patch = await _lost_create(
        db_session, monkeypatch, "Коледино 29.09"
    )
    now = datetime.now(UTC)
    # Та же подпись: старая поставка WB и уже известная WMS — не наши.
    db_session.add(
        _supply(source, wb_supply_id="WB-GI-KNOWN", name="Коледино 29.09", status="draft")
    )
    await db_session.commit()
    monkeypatch.setattr(
        svc,
        "fetch_marketplace_supplies_page",
        AsyncMock(
            return_value=_page(
                ("WB-GI-OLD", "Коледино 29.09", now - timedelta(days=1)),
                ("WB-GI-KNOWN", "Коледино 29.09", now),
                ("WB-GI-OURS", "Коледино 29.09", now),
            )
        ),
    )
    result = await _transfer(db_session, tenant, source, orders, name="Коледино 29.09")
    assert result["state"] == "confirmed"
    assert result["target_wb_supply_id"] == "WB-GI-OURS"
    assert create.await_count == 1 and patch.await_count == 1
    assert patch.call_args.kwargs["supply_id"] == "WB-GI-OURS"


@pytest.mark.asyncio
async def test_c5_ambiguous_or_foreign_same_name_stays_unknown_without_second_create(
    db_session, monkeypatch
):
    tenant, source, orders, create, patch = await _lost_create(
        db_session, monkeypatch, "Коледино 29.09"
    )
    now = datetime.now(UTC)
    supplies_before = await db_session.scalar(select(func.count()).select_from(FbsSupply))
    # Две свежие поставки с тем же названием — неоднозначно.
    monkeypatch.setattr(
        svc,
        "fetch_marketplace_supplies_page",
        AsyncMock(
            return_value=_page(
                ("WB-GI-X", "Коледино 29.09", now),
                ("WB-GI-Y", "Коледино 29.09", now),
            )
        ),
    )
    result = await _transfer(db_session, tenant, source, orders, name="Коледино 29.09")
    assert result["state"] == "pending_confirmation"
    # Только чужая старая поставка с тем же названием — тоже не наша.
    monkeypatch.setattr(
        svc,
        "fetch_marketplace_supplies_page",
        AsyncMock(return_value=_page(("WB-GI-OLD", "Коледино 29.09", now - timedelta(hours=3)))),
    )
    result = await _transfer(db_session, tenant, source, orders, name="Коледино 29.09")
    assert result["state"] == "pending_confirmation"
    assert create.await_count == 1 and patch.await_count == 0
    assert all(order.supply_id == source.id for order in orders)
    assert await db_session.scalar(select(func.count()).select_from(FbsSupply)) == supplies_before
    operation = await db_session.scalar(select(FbsWbOperation))
    assert operation is not None and operation.wb_object_id is None


# --- Ревью Astra 29.09.2026 (P1, P2): тесты перенесены из временного файла ревьюера. ---


@pytest.mark.asyncio
async def test_lost_create_must_not_adopt_a_single_recent_foreign_supply(db_session, monkeypatch):
    # Connection fails before WB creates ours; another operator already created
    # an identically named supply 30 seconds earlier, not yet imported to WMS.
    tenant, source, orders, _create, patch = await _lost_create(
        db_session, monkeypatch, "Коледино 29.09"
    )
    monkeypatch.setattr(
        svc,
        "fetch_marketplace_supplies_page",
        AsyncMock(
            return_value=_page(
                ("WB-GI-FOREIGN", "Коледино 29.09", datetime.now(UTC) - timedelta(seconds=30)),
            )
        ),
    )
    result = await _transfer(db_session, tenant, source, orders, name="Коледино 29.09")
    assert result["state"] == "pending_confirmation", (
        "A recent matching name is not proof this create succeeded"
    )
    patch.assert_not_awaited()


@pytest.mark.asyncio
async def test_fulfilled_order_round_trip_does_not_grow_plan(db_session, monkeypatch):
    tenant, source, target, orders, _marking, product, target_task = await _in_work_pair(
        db_session
    )
    moved = orders[0]
    moved.product_id = product.id
    orders[1].product_id = product.id
    location = await db_session.scalar(
        select(StorageLocation).where(StorageLocation.code == "WMS581")
    )
    task = PackagingTask(tenant_id=tenant.id, warehouse_id=source.warehouse_id, status="draft")
    db_session.add(task)
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
    fulfillment = FbsPackagingFulfillment(
        tenant_id=tenant.id,
        fbs_order_id=moved.id,
        packaging_task_id=task.id,
        packaging_task_line_id=line.id,
        fulfilled_at=datetime.now(UTC),
        pack_idempotency_key="original",
    )
    db_session.add(fulfillment)
    await db_session.commit()
    monkeypatch.setattr(svc, "_require_marketplace_token", AsyncMock(return_value="test"))
    patch = AsyncMock()
    monkeypatch.setattr(svc, "add_orders_to_marketplace_supply", patch)
    monkeypatch.setattr(
        svc, "fetch_marketplace_supply_order_ids", AsyncMock(side_effect=[[1, 50], [1, 2]])
    )
    first = await _transfer(db_session, tenant, source, [moved], target=target, key="there")
    assert first["state"] == "confirmed"
    second = await _transfer(db_session, tenant, target, [moved], target=source, key="back")
    assert second["state"] == "confirmed"
    await db_session.refresh(line)
    target_line = await db_session.scalar(
        select(PackagingTaskLine).where(PackagingTaskLine.task_id == target_task.id)
    )
    assert moved.supply_id == source.id and moved.pack_status == "packed"
    assert line.qty_total == 2, "Returning the same packed order must not add a new planned unit"
    assert target_line.qty_total == 1, "Departed order must leave the target plan"


# --- WMS-581: снимок WB перед созданием и «Всё упаковано» после переноса упакованного. ---


@pytest.mark.asyncio
async def test_c5_same_name_supply_from_snapshot_is_never_ours(db_session, monkeypatch):
    """Коллега создал «Коледино 29.09» за секунду до нас — он в снимке, и он не наш."""
    before = datetime.now(UTC) - timedelta(seconds=1)
    tenant, source, orders, create, patch = await _lost_create(
        db_session, monkeypatch, "Коледино 29.09", [("WB-GI-COLLEAGUE", "Коледино 29.09", before)]
    )
    operation = await db_session.scalar(select(FbsWbOperation))
    assert operation.request_summary_json["preexisting_wb_supply_ids"] == ["WB-GI-COLLEAGUE"]
    monkeypatch.setattr(
        svc,
        "fetch_marketplace_supplies_page",
        AsyncMock(return_value=_page(("WB-GI-COLLEAGUE", "Коледино 29.09", before))),
    )
    result = await _transfer(db_session, tenant, source, orders, name="Коледино 29.09")
    assert result["state"] == "pending_confirmation"
    patch.assert_not_awaited()
    # Наша поставка появилась в WB — теперь она единственный кандидат вне снимка.
    monkeypatch.setattr(
        svc,
        "fetch_marketplace_supplies_page",
        AsyncMock(
            return_value=_page(
                ("WB-GI-COLLEAGUE", "Коледино 29.09", before),
                ("WB-GI-OURS", "Коледино 29.09", datetime.now(UTC)),
            )
        ),
    )
    result = await _transfer(db_session, tenant, source, orders, name="Коледино 29.09")
    assert result["state"] == "confirmed" and result["target_wb_supply_id"] == "WB-GI-OURS"
    assert create.await_count == 1 and patch.call_args.kwargs["supply_id"] == "WB-GI-OURS"


@pytest.mark.asyncio
async def test_c5_no_snapshot_no_create(db_session, monkeypatch):
    tenant, source, _, orders, _ = await seed(db_session)
    monkeypatch.setattr(svc, "_require_marketplace_token", AsyncMock(return_value="test"))
    monkeypatch.setattr(
        svc,
        "fetch_marketplace_supplies_page",
        AsyncMock(side_effect=WildberriesClientError("transport_error")),
    )
    create = AsyncMock()
    monkeypatch.setattr(svc, "create_marketplace_supply", create)
    with pytest.raises(svc.FbsSupplyError, match="wb_supplies_unavailable") as caught:
        await _transfer(db_session, tenant, source, orders, name="Коледино 29.09")
    assert caught.value.retryable and caught.value.http_status == 503
    create.assert_not_awaited()
    assert await db_session.scalar(select(func.count()).select_from(FbsWbOperation)) == 0
    assert all(order.supply_id == source.id for order in orders)


async def _packed_in_source(db_session, tenant, source, moved, product):
    location = await db_session.scalar(
        select(StorageLocation).where(StorageLocation.code == "WMS581")
    )
    task = PackagingTask(tenant_id=tenant.id, warehouse_id=source.warehouse_id, status="draft")
    db_session.add(task)
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
    db_session.add(
        FbsPackagingFulfillment(
            tenant_id=tenant.id,
            fbs_order_id=moved.id,
            packaging_task_id=task.id,
            packaging_task_line_id=line.id,
            fulfilled_at=datetime.now(UTC),
            pack_idempotency_key="original",
        )
    )
    await db_session.commit()
    return line


@pytest.mark.asyncio
async def test_c2_pack_all_in_target_after_packed_order_arrives(db_session, monkeypatch):
    """Упакованный в A заказ пришёл в B «в работе»: «Всё упаковано» в B проходит."""
    tenant, source, target, orders, _, product, target_task = await _in_work_pair(db_session)
    moved = orders[0]
    moved.product_id = product.id
    orders[1].product_id = product.id
    source_line = await _packed_in_source(db_session, tenant, source, moved, product)
    monkeypatch.setattr(svc, "_require_marketplace_token", AsyncMock(return_value="test"))
    monkeypatch.setattr(svc, "add_orders_to_marketplace_supply", AsyncMock())
    monkeypatch.setattr(svc, "fetch_marketplace_supply_order_ids", AsyncMock(return_value=[1, 50]))
    assert (await _transfer(db_session, tenant, source, [moved], target=target))["state"] == (
        "confirmed"
    )
    await db_session.refresh(source_line)
    # A: упаковка переносимого заказа остаётся её историей, в работе — оставшийся заказ.
    assert (source_line.qty_total, source_line.qty_packed_in_task) == (2, 1)
    done = await pack_all_and_complete_fbs_task(
        db_session, tenant.id, target_task.id, acting_user_id=None
    )
    assert done.task.status == "done"
    resident = await db_session.scalar(select(FbsOrder).where(FbsOrder.wb_order_id == 50))
    assert resident.pack_status == "packed"
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(FbsPackagingFulfillment)
            .where(FbsPackagingFulfillment.fbs_order_id == moved.id)
        )
        == 1
    )


@pytest.mark.asyncio
async def test_c2_started_draft_does_not_plan_order_packed_elsewhere(db_session, monkeypatch):
    tenant, source, _, orders, _, product, _ = await _in_work_pair(db_session)
    draft = await db_session.scalar(select(FbsSupply).where(FbsSupply.name == "Target"))
    moved = orders[0]
    moved.product_id = product.id
    orders[1].product_id = product.id
    await _packed_in_source(db_session, tenant, source, moved, product)
    monkeypatch.setattr(svc, "_require_marketplace_token", AsyncMock(return_value="test"))
    monkeypatch.setattr(svc, "add_orders_to_marketplace_supply", AsyncMock())
    monkeypatch.setattr(svc, "fetch_marketplace_supply_order_ids", AsyncMock(return_value=[1, 2]))
    assert (await _transfer(db_session, tenant, source, orders, target=draft))["state"] == (
        "confirmed"
    )
    await start_supply_work(db_session, tenant.id, draft.id, actor_user_id=None)
    await db_session.refresh(draft)
    lines = list(
        await db_session.scalars(
            select(PackagingTaskLine).where(PackagingTaskLine.task_id == draft.packaging_task_id)
        )
    )
    assert [(line.product_id, line.qty_total) for line in lines] == [(product.id, 1)]
    done = await pack_all_and_complete_fbs_task(
        db_session, tenant.id, draft.packaging_task_id, acting_user_id=None
    )
    assert done.task.status == "done" and orders[1].pack_status == "packed"
