"""WMS-666: expose each order's current seller/product marking pool count."""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.fbs_order import (
    CHECK_STATUS_OK,
    MARKING_KIND_SGTIN,
    META_STATUS_ACCEPTED,
    FbsOrder,
    FbsOrderMarking,
)
from app.models.fbs_supply import FbsSupply
from app.models.marking_code import EVENT_PRINTED, STATUS_AVAILABLE, MarkingCode, MarkingCodeEvent
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.product import Product
from app.services import fbs_order_tape_print_service as tape
from tests.test_fbs_kiz import _patch_wb_acceptance
from tests.test_fbs_order_tape_concurrency import stock_snapshot
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
    _seed_pick_supply,
)


async def _bare_supply_with_pool(
    async_client: AsyncClient,
    *,
    headers: dict[str, str],
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    location_id: uuid.UUID,
    product_id: uuid.UUID,
    suffix: str,
    order_count: int,
    pool_count: int,
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    supply_id, order_ids, _ = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=0,
        order_specs=[(index + 1, timedelta(hours=3 + index)) for index in range(order_count)],
        barcode=f"2300{suffix[-9:]}",
    )
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        supply = await session.get(FbsSupply, supply_id)
        orders = list(
            (await session.execute(select(FbsOrder).where(FbsOrder.id.in_(order_ids))))
            .scalars()
        )
        assert product is not None and supply is not None
        product.requires_honest_sign = True
        supply.status = "assembling"
        supply.packaging_task_id = None
        for order in orders:
            order.required_meta_json = ["sgtin"]
        session.add_all(
            MarkingCode(
                tenant_id=tenant_id,
                seller_id=seller_id,
                product_id=product_id,
                cis_code=f"010000000000012321{seller_id.hex[:8]}{index:04d}",
                gtin="00000000000001",
                status=STATUS_AVAILABLE,
            )
            for index in range(pool_count)
        )
        await session.commit()
    return supply_id, order_ids


@pytest.mark.asyncio
async def test_bare_workspace_reports_current_pool_per_product_and_seller(
    async_client: AsyncClient,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_a, warehouse_a, location_a = await _create_seller_and_warehouse(
        async_client, headers, suffix,
    )
    product_a = await _create_product(
        async_client, headers, seller_a, sku=f"wms666-bare-a-{suffix[-8:]}",
        barcode=f"2300{suffix[-9:]}",
    )
    supply_a, order_ids_a = await _bare_supply_with_pool(
        async_client,
        headers=headers,
        tenant_id=tenant_id,
        seller_id=seller_a,
        warehouse_id=warehouse_a,
        location_id=location_a,
        product_id=product_a,
        suffix=f"a{suffix}",
        order_count=2,
        pool_count=2,
    )

    seller_b, warehouse_b, location_b = await _create_seller_and_warehouse(
        async_client, headers, f"{suffix}-b",
    )
    product_b = await _create_product(
        async_client, headers, seller_b, sku=f"wms666-bare-b-{suffix[-8:]}",
        barcode=f"2301{suffix[-9:]}",
    )
    supply_b, order_ids_b = await _bare_supply_with_pool(
        async_client,
        headers=headers,
        tenant_id=tenant_id,
        seller_id=seller_b,
        warehouse_id=warehouse_b,
        location_id=location_b,
        product_id=product_b,
        suffix=f"b{suffix}",
        order_count=1,
        pool_count=1,
    )

    response_a = await async_client.get(
        f"/operations/fbs-supplies/{supply_a}/workspace", headers=headers,
    )
    response_b = await async_client.get(
        f"/operations/fbs-supplies/{supply_b}/workspace", headers=headers,
    )
    assert response_a.status_code == 200, response_a.text
    assert response_b.status_code == 200, response_b.text
    body_a = response_a.json()
    body_b = response_b.json()

    # The bare supply has no accounting task; its workspace still knows the
    # actual seller/product pool. Both same-product orders see that read-only
    # pool count, and the other seller's row sees only its own pool.
    assert body_a["supply"]["packaging_task_id"] is None
    assert body_b["supply"]["packaging_task_id"] is None
    assert all(row["product"]["requires_honest_sign"] for row in body_a["orders"])
    assert all(row["product"]["requires_honest_sign"] for row in body_b["orders"])
    assert body_a["marking_pool"]["available"] == 2
    assert body_b["marking_pool"]["available"] == 1
    by_id_a = {row["id"]: row for row in body_a["orders"]}
    by_id_b = {row["id"]: row for row in body_b["orders"]}
    assert set(by_id_a) == {str(order_id) for order_id in order_ids_a}
    assert set(by_id_b) == {str(order_id) for order_id in order_ids_b}
    assert [by_id_a[str(order_id)]["marking_available_count"] for order_id in order_ids_a] == [2, 2]
    assert by_id_b[str(order_ids_b[0])]["marking_available_count"] == 1


@pytest.mark.asyncio
async def test_bare_supply_manual_tape_allocates_pool_cis_without_packaging_task(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix,
    )
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"wms666-bare-tape-{suffix[-8:]}",
        barcode=f"2302{suffix[-9:]}",
    )
    supply_id, order_ids = await _bare_supply_with_pool(
        async_client,
        headers=headers,
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        location_id=location_id,
        product_id=product_id,
        suffix=f"t{suffix}",
        order_count=1,
        pool_count=2,
    )
    sent_values = _patch_wb_acceptance(monkeypatch)
    monkeypatch.setattr(
        tape.marking_svc, "require_marketplace_token", AsyncMock(return_value="test"),
    )
    before_stock = await stock_snapshot()
    async with SessionLocal() as session:
        initial_pool = list((await session.scalars(
            select(MarkingCode).where(
                MarkingCode.tenant_id == tenant_id,
                MarkingCode.seller_id == seller_id,
                MarkingCode.product_id == product_id,
                MarkingCode.status == STATUS_AVAILABLE,
            )
        )).all())
    assert len(initial_pool) == 2

    response = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/order-print-tape",
        headers=headers,
        json={
            "order_ids": [str(order_ids[0])],
            "layout_json": {"units": [{"block": "cz", "copies": 1}]},
            "allow_partial": False,
            "include_order_qr": False,
            "reprint": False,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["order_errors"] == []
    assert body["ready"] == 1
    assert body["missing"] == 0
    printed = body["orders"][0]["printed_codes"]
    assert len(printed) == 1
    assert printed[0]["cis_code"] == body["orders"][0]["codes"][0]
    assert sent_values == {700001: printed[0]["cis_code"]}
    assert printed[0]["cis_code"] in {code.cis_code for code in initial_pool}
    async with SessionLocal() as session:
        assigned_code = await session.get(MarkingCode, uuid.UUID(printed[0]["id"]))
        # Manual tape must persist its order/code binding; the separate late
        # print-binding validation API is outside this release's contract.
        assigned_marking = (await session.scalars(
            select(FbsOrderMarking).where(
                FbsOrderMarking.order_id == order_ids[0],
                FbsOrderMarking.marking_code_id == uuid.UUID(printed[0]["id"]),
            )
        )).one()
        remaining_pool = list((await session.scalars(
            select(MarkingCode).where(
                MarkingCode.tenant_id == tenant_id,
                MarkingCode.seller_id == seller_id,
                MarkingCode.product_id == product_id,
                MarkingCode.status == STATUS_AVAILABLE,
            )
        )).all())
        assert assigned_code is not None
        assert assigned_marking is not None
        assert assigned_code.cis_code == printed[0]["cis_code"]
        assert assigned_code.status == "printed"
        assert assigned_marking.order_id == order_ids[0]
        assert assigned_marking.marking_code_id == assigned_code.id
        assert assigned_marking.value == printed[0]["cis_code"]
        assert len(remaining_pool) == 1
        assert remaining_pool[0].id in {code.id for code in initial_pool}
        assert remaining_pool[0].id != assigned_code.id
    after_stock = await stock_snapshot()
    assert after_stock == before_stock, "manual KIZ allocation is not a stock movement"
    workspace = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/workspace", headers=headers,
    )
    assert workspace.status_code == 200, workspace.text
    assert workspace.json()["supply"]["packaging_task_id"] is None


@pytest.mark.asyncio
async def test_task_with_missing_product_line_manual_tape_allocates_pool_cis(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix,
    )
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"wms666-task-no-line-{suffix[-8:]}",
        barcode=f"2303{suffix[-9:]}",
    )
    supply_id, order_ids = await _bare_supply_with_pool(
        async_client,
        headers=headers,
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        location_id=location_id,
        product_id=product_id,
        suffix=f"n{suffix}",
        order_count=1,
        pool_count=2,
    )
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        task = PackagingTask(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            status="in_progress",
        )
        session.add(task)
        await session.flush()
        task_id = task.id
        supply.packaging_task_id = task_id
        await session.commit()
    sent_values = _patch_wb_acceptance(monkeypatch)
    monkeypatch.setattr(
        tape.marking_svc, "require_marketplace_token", AsyncMock(return_value="test"),
    )
    before_stock = await stock_snapshot()
    async with SessionLocal() as session:
        task = await session.get(PackagingTask, task_id)
        supply = await session.get(FbsSupply, supply_id)
        task_lines = list((await session.scalars(
            select(PackagingTaskLine).where(PackagingTaskLine.task_id == task_id)
        )).all())
        pool_before = list((await session.scalars(
            select(MarkingCode).where(
                MarkingCode.tenant_id == tenant_id,
                MarkingCode.seller_id == seller_id,
                MarkingCode.product_id == product_id,
                MarkingCode.status == STATUS_AVAILABLE,
            )
        )).all())
        assert task is not None and supply is not None
        assert supply.packaging_task_id == task_id
        assert all(line.product_id != product_id for line in task_lines)
        assert len(pool_before) == 2

    response = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/order-print-tape",
        headers=headers,
        json={
            "order_ids": [str(order_ids[0])],
            "layout_json": {"units": [{"block": "cz", "copies": 1}]},
            "allow_partial": False,
            "include_order_qr": False,
            "reprint": False,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    async with SessionLocal() as session:
        supply_after = await session.get(FbsSupply, supply_id)
        task_after = await session.get(PackagingTask, task_id)
        task_lines_after = list((await session.scalars(
            select(PackagingTaskLine).where(PackagingTaskLine.task_id == task_id)
        )).all())
        pool_after_response = list((await session.scalars(
            select(MarkingCode).where(
                MarkingCode.tenant_id == tenant_id,
                MarkingCode.seller_id == seller_id,
                MarkingCode.product_id == product_id,
                MarkingCode.status == STATUS_AVAILABLE,
            )
        )).all())
        assert supply_after is not None and supply_after.packaging_task_id == task_id
        assert task_after is not None and task_after.status == "in_progress"
        assert all(line.product_id != product_id for line in task_lines_after)
        assert len(pool_after_response) == 1
        assert pool_after_response[0].id in {code.id for code in pool_before}
    assert await stock_snapshot() == before_stock
    assert body["order_errors"] == []
    assert body["ready"] == 1
    assert body["missing"] == 0
    printed = body["orders"][0]["printed_codes"]
    assert len(printed) == 1
    assert printed[0]["cis_code"] == body["orders"][0]["codes"][0]
    assert sent_values == {700001: printed[0]["cis_code"]}
    assert printed[0]["cis_code"] in {code.cis_code for code in pool_before}
    async with SessionLocal() as session:
        printed_code = await session.get(MarkingCode, uuid.UUID(printed[0]["id"]))
        assigned = (await session.scalars(
            select(FbsOrderMarking).where(
                FbsOrderMarking.order_id == order_ids[0],
                FbsOrderMarking.marking_code_id == uuid.UUID(printed[0]["id"]),
            )
        )).one()
        assert printed_code is not None and printed_code.status == "printed"
        assert assigned is not None and assigned.order_id == order_ids[0]
        assert assigned.marking_code_id == printed_code.id
        assert printed_code.cis_code == printed[0]["cis_code"]
        assert assigned.value == printed[0]["cis_code"]
    assert await stock_snapshot() == before_stock


@pytest.mark.parametrize(
    ("qty_confirmed_packed", "qty_marking_printed"),
    [(1, 0), (0, 1)],
    ids=["packaging-need-zero", "accounting-already-records-print"],
)
@pytest.mark.asyncio
async def test_current_order_kiz_can_be_allocated_when_task_line_has_no_remaining_need(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    qty_confirmed_packed: int,
    qty_marking_printed: int,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix,
    )
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"wms666-no-line-need-{suffix[-8:]}",
        barcode=f"2304{suffix[-9:]}",
    )
    supply_id, order_ids = await _bare_supply_with_pool(
        async_client,
        headers=headers,
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        location_id=location_id,
        product_id=product_id,
        suffix=f"l{suffix}",
        order_count=1,
        pool_count=2,
    )
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        task = PackagingTask(tenant_id=tenant_id, warehouse_id=warehouse_id, status="in_progress")
        session.add(task)
        await session.flush()
        line = PackagingTaskLine(
            task_id=task.id,
            product_id=product_id,
            storage_location_id=location_id,
            qty_total=1,
            qty_confirmed_packed=qty_confirmed_packed,
            qty_marking_printed=qty_marking_printed,
        )
        session.add(line)
        await session.flush()
        task_id, line_id = task.id, line.id
        supply.packaging_task_id = task_id
        await session.commit()

    sent_values = _patch_wb_acceptance(monkeypatch)
    monkeypatch.setattr(
        tape.marking_svc, "require_marketplace_token", AsyncMock(return_value="test"),
    )
    before_stock = await stock_snapshot()
    async with SessionLocal() as session:
        initial_pool = list((await session.scalars(
            select(MarkingCode).where(
                MarkingCode.tenant_id == tenant_id,
                MarkingCode.seller_id == seller_id,
                MarkingCode.product_id == product_id,
                MarkingCode.status == STATUS_AVAILABLE,
            )
        )).all())
        assert len(initial_pool) == 2

    response = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/order-print-tape",
        headers=headers,
        json={
            "order_ids": [str(order_ids[0])],
            "layout_json": {"units": [{"block": "cz", "copies": 1}]},
            "allow_partial": False,
            "include_order_qr": False,
            "reprint": False,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    async with SessionLocal() as session:
        supply_after = await session.get(FbsSupply, supply_id)
        task_after = await session.get(PackagingTask, task_id)
        line_after = await session.get(PackagingTaskLine, line_id)
        pool_after_response = list((await session.scalars(
            select(MarkingCode).where(
                MarkingCode.tenant_id == tenant_id,
                MarkingCode.seller_id == seller_id,
                MarkingCode.product_id == product_id,
                MarkingCode.status == STATUS_AVAILABLE,
            )
        )).all())
        assert supply_after is not None and supply_after.packaging_task_id == task_id
        assert task_after is not None and task_after.status == "in_progress"
        assert line_after is not None
        assert line_after.qty_confirmed_packed == qty_confirmed_packed
        assert line_after.qty_marking_printed == qty_marking_printed
        assert len(pool_after_response) == 1
        assert pool_after_response[0].id in {code.id for code in initial_pool}
    assert await stock_snapshot() == before_stock
    assert body["order_errors"] == []
    assert body["ready"] == 1
    assert body["missing"] == 0
    printed = body["orders"][0]["printed_codes"]
    assert len(printed) == 1
    assert printed[0]["cis_code"] == body["orders"][0]["codes"][0]
    assert sent_values == {700001: printed[0]["cis_code"]}
    assert printed[0]["cis_code"] in {code.cis_code for code in initial_pool}
    async with SessionLocal() as session:
        printed_code = await session.get(MarkingCode, uuid.UUID(printed[0]["id"]))
        assigned = (await session.scalars(
            select(FbsOrderMarking).where(
                FbsOrderMarking.order_id == order_ids[0],
                FbsOrderMarking.marking_code_id == uuid.UUID(printed[0]["id"]),
            )
        )).one()
        assert printed_code is not None and printed_code.status == "printed"
        assert assigned is not None and assigned.order_id == order_ids[0]
        assert assigned.marking_code_id == printed_code.id
        assert printed_code.cis_code == printed[0]["cis_code"]
        assert assigned.value == printed[0]["cis_code"]
    assert await stock_snapshot() == before_stock


@pytest.mark.asyncio
async def test_taskless_print_assignment_conflict_does_not_spend_unbound_pool_code(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix,
    )
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"wms666-bind-conflict-{suffix[-8:]}",
        barcode=f"2305{suffix[-9:]}",
    )
    supply_id, order_ids = await _bare_supply_with_pool(
        async_client,
        headers=headers,
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        location_id=location_id,
        product_id=product_id,
        suffix=f"c{suffix}",
        order_count=1,
        pool_count=2,
    )
    existing_value = f"010{suffix[-12:]}21ALREADY-BOUND"
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_ids[0])
        assert order is not None
        existing = FbsOrderMarking(
            order_id=order.id,
            tenant_id=tenant_id,
            kind=MARKING_KIND_SGTIN,
            value=existing_value,
            source="wb",
            check_status=CHECK_STATUS_OK,
            meta_status=META_STATUS_ACCEPTED,
            marking_code_id=None,
        )
        session.add(existing)
        await session.commit()
        existing_marking_id = existing.id

    monkeypatch.setattr(
        tape.marking_svc, "require_marketplace_token", AsyncMock(return_value="test"),
    )
    before_stock = await stock_snapshot()
    async with SessionLocal() as session:
        initial_pool = list((await session.scalars(
            select(MarkingCode).where(
                MarkingCode.tenant_id == tenant_id,
                MarkingCode.seller_id == seller_id,
                MarkingCode.product_id == product_id,
                MarkingCode.status == STATUS_AVAILABLE,
            )
        )).all())
        assert len(initial_pool) == 2

    response = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/order-print-tape",
        headers=headers,
        json={
            "order_ids": [str(order_ids[0])],
            "layout_json": {"units": [{"block": "cz", "copies": 1}]},
            "allow_partial": False,
            "include_order_qr": False,
            "reprint": False,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["order_errors"]
    async with SessionLocal() as session:
        current = await session.get(FbsOrderMarking, existing_marking_id)
        current_pool = list((await session.scalars(
            select(MarkingCode).where(
                MarkingCode.tenant_id == tenant_id,
                MarkingCode.seller_id == seller_id,
                MarkingCode.product_id == product_id,
            )
        )).all())
        printed_events = list((await session.scalars(
            select(MarkingCodeEvent).where(
                MarkingCodeEvent.code_id.in_([code.id for code in initial_pool]),
                MarkingCodeEvent.event_type == EVENT_PRINTED,
            )
        )).all())
        assert current is not None
        assert current.value == existing_value
        assert current.marking_code_id is None
        assert current.meta_status == META_STATUS_ACCEPTED
        assert len(current_pool) == 2
        assert {code.id for code in current_pool} == {code.id for code in initial_pool}
        assert (
            all(code.status == STATUS_AVAILABLE for code in current_pool)
            and not printed_events
        ), {
            "pool_statuses": [code.status for code in current_pool],
            "printed_event_types": [event.event_type for event in printed_events],
        }
    assert await stock_snapshot() == before_stock
