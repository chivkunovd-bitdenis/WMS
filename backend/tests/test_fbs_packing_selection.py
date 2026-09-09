"""WMS-085: selected printing/clearing stays within selected orders and marking stock."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from test_fbs_kiz import (
    _cis,
    _create_order,
    _create_supply,
    _patch_wb_acceptance,
    _register_ff_admin,
    _setup_seller_warehouse,
)

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderMarking, FbsOrderReservation
from app.models.fbs_supply import FbsSupply
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.marking_code import MarkingCode, MarkingCodeEvent
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.product import Product
from app.services.wildberries_errors import WildberriesClientError


async def seed_selection(client: AsyncClient):
    headers, suffix = await _register_ff_admin(client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(client, headers, suffix)
    supply_id = await _create_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        suffix=suffix,
    )
    orders = [
        await _create_order(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            supply_id=supply_id,
            suffix=suffix,
            wb_order_id=985000 + i,
            sticker_code=f"9850 {i:04}",
            wb_barcode=f"9850{i:04}",
            with_packaging=i == 0,
            status="assembling",
        )
        for i in range(5)
    ]
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        task = await session.get(PackagingTask, orders[0].packaging_task_id)
        first_line = await session.get(PackagingTaskLine, orders[0].packaging_task_line_id)
        assert supply and task and first_line
        supply.name = "WMS-085 · выбор и ЧЗ"
        supply.status = "assembling"
        task.status = "in_progress"
        first_line.qty_total = 3
        first_line.qty_packed_in_task = 0
        first_line.qty_marking_printed = 1
        for i, seeded in enumerate(orders):
            order = await session.get(FbsOrder, seeded.order_id)
            assert order
            if i < 3:
                order.product_id = orders[0].product_id
            order.required_meta_json = ["sgtin"] if i < 4 else []
            product = await session.get(Product, order.product_id)
            assert product
            product.name = (
                "А · ЧЗ не хватает"
                if i < 3
                else "Б · ЧЗ достаточно"
                if i == 3
                else "В · без маркировки"
            )
            product.requires_honest_sign = i < 4
            if i >= 3:
                session.add(
                    PackagingTaskLine(
                        task_id=task.id,
                        product_id=product.id,
                        storage_location_id=first_line.storage_location_id,
                        qty_total=1,
                        qty_suggested_packed=0,
                        qty_confirmed_packed=0,
                        qty_packed_in_task=0,
                    )
                )
            session.add(
                FbsOrderReservation(
                    tenant_id=tenant_id,
                    fbs_order_id=order.id,
                    product_id=product.id,
                    warehouse_id=warehouse_id,
                    quantity=1,
                )
            )
        for seeded in [orders[0], orders[3], orders[4]]:
            session.add(
                InventoryBalance(
                    tenant_id=tenant_id,
                    product_id=seeded.product_id,
                    storage_location_id=first_line.storage_location_id,
                    quantity=10,
                    quantity_unpacked=10,
                    quantity_packed=0,
                )
            )
        used = MarkingCode(
            tenant_id=tenant_id,
            seller_id=seller_id,
            product_id=orders[0].product_id,
            cis_code=_cis("USED085"),
            source="pool",
            status="applied",
            packaging_task_line_id=first_line.id,
            printed_at=datetime.now(UTC),
            applied_at=datetime.now(UTC),
        )
        session.add(used)
        await session.flush()
        session.add(
            FbsOrderMarking(
                tenant_id=tenant_id,
                order_id=orders[0].order_id,
                kind="sgtin",
                value=used.cis_code,
                marking_code_id=used.id,
                source="pool",
                meta_status="accepted",
                check_status="ok",
            )
        )
        for product_id, count, prefix in [
            (orders[0].product_id, 1, "A085"),
            (orders[3].product_id, 3, "B085"),
        ]:
            for i in range(count):
                session.add(
                    MarkingCode(
                        tenant_id=tenant_id,
                        seller_id=seller_id,
                        product_id=product_id,
                        cis_code=_cis(f"{prefix}{i}"),
                        source="pool",
                        status="available",
                    )
                )
        await session.commit()
    return headers, supply_id, orders


async def inventory_snapshot():
    async with SessionLocal() as session:
        return (
            (
                await session.execute(
                    select(
                        InventoryBalance.id,
                        InventoryBalance.quantity,
                        InventoryBalance.quantity_unpacked,
                        InventoryBalance.quantity_packed,
                    ).order_by(InventoryBalance.id)
                )
            ).all(),
            (
                await session.execute(
                    select(FbsOrderReservation.id, FbsOrderReservation.quantity).order_by(
                        FbsOrderReservation.id
                    )
                )
            ).all(),
            await session.scalar(select(func.count()).select_from(InventoryMovement)),
            (
                await session.execute(
                    select(PackagingTaskLine.id, PackagingTaskLine.qty_packed_in_task).order_by(
                        PackagingTaskLine.id
                    )
                )
            ).all(),
        )


@pytest.mark.asyncio
async def test_selected_tape_reuses_code_and_clear_never_changes_inventory(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, supply_id, orders = await seed_selection(async_client)
    before = await inventory_snapshot()
    from app.services import fbs_marking_service as marking_svc

    sent = _patch_wb_acceptance(monkeypatch)
    put = AsyncMock(wraps=marking_svc.put_marketplace_order_meta)
    monkeypatch.setattr(marking_svc, "put_marketplace_order_meta", put)
    requested = [str(orders[i].order_id) for i in (0, 1)]
    payload = {
        "order_ids": requested,
        "layout_json": {"units": [{"block": "cz", "copies": 1}]},
        "allow_partial": False,
        "include_order_qr": False,
        "reprint": False,
    }
    url = f"/operations/fbs-supplies/{supply_id}/order-print-tape"
    printed = await async_client.post(url, headers=headers, json=payload)
    assert printed.status_code == 200, printed.text
    assert printed.json()["order_errors"] == [], printed.text
    assert [row["order_id"] for row in printed.json()["orders"]] == requested
    # The first order already has an accepted code; only the new binding goes to WB.
    assert set(sent) == {orders[1].wb_order_id}
    assert put.await_count == 1
    for reprint in (False, True):
        response = await async_client.post(
            url, headers=headers, json={**payload, "reprint": reprint}
        )
        assert response.status_code == 200, response.text
        assert [row["codes"] for row in response.json()["orders"]] == [
            row["codes"] for row in printed.json()["orders"]
        ]
    assert put.await_count == 1
    assert await inventory_snapshot() == before
    async with SessionLocal() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MarkingCode)
                .where(
                    MarkingCode.product_id == orders[0].product_id,
                    MarkingCode.status == "available",
                )
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MarkingCode)
                .where(
                    MarkingCode.product_id == orders[3].product_id,
                    MarkingCode.status == "available",
                )
            )
            == 3
        )
        assert await session.scalar(select(func.count()).select_from(FbsOrderMarking)) == 2
    deleted = []

    async def delete(client, *, order_id, **kwargs):
        deleted.append(order_id)
        if order_id == orders[1].wb_order_id:
            raise WildberriesClientError("rate_limited", status_code=429)

    monkeypatch.setattr("app.services.fbs_kiz_service.delete_marketplace_order_meta", delete)
    first = await async_client.delete(
        f"/operations/fbs-orders/{orders[0].order_id}/kiz", headers=headers
    )
    assert first.status_code == 204, first.text
    failed = await async_client.delete(
        f"/operations/fbs-orders/{orders[1].order_id}/kiz", headers=headers
    )
    assert failed.status_code >= 400, failed.text
    workspace = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/workspace", headers=headers
    )
    assert workspace.status_code == 200, workspace.text
    states = {row["id"]: row["metadata"]["states"] for row in workspace.json()["orders"]}
    assert states[requested[0]][0]["value_tail"] is None
    assert states[requested[1]][0]["value_tail"] is not None
    assert deleted == [orders[0].wb_order_id, orders[1].wb_order_id]
    async with SessionLocal() as session:
        # WMS-084: a confirmed operator detach releases the binding, not the
        # physical label. The code must also stay out of the available print pool.
        detached = await session.scalar(
            select(MarkingCode).where(MarkingCode.cis_code == _cis("USED085"))
        )
        assert detached is not None
        assert detached.status == "applied"
        assert detached.source == "pool"
        assert detached.packaging_task_line_id is None
        assert await session.scalar(
            select(FbsOrderMarking.id).where(FbsOrderMarking.marking_code_id == detached.id)
        ) is None
        assert await session.scalar(select(func.count()).select_from(MarkingCode)) == 5
    assert await inventory_snapshot() == before

    async def delete_ok(client, **kwargs):
        pass

    monkeypatch.setattr("app.services.fbs_kiz_service.delete_marketplace_order_meta", delete_ok)
    retry = await async_client.delete(
        f"/operations/fbs-orders/{orders[1].order_id}/kiz",
        headers=headers,
    )
    assert retry.status_code == 204, retry.text
    async with SessionLocal() as session:
        old_code = (
            (
                await session.execute(
                    select(MarkingCode).where(
                        MarkingCode.product_id == orders[0].product_id,
                    )
                )
            )
            .scalars()
            .first()
        )
        assert old_code
        for i in range(3):
            session.add(
                MarkingCode(
                    tenant_id=old_code.tenant_id,
                    seller_id=old_code.seller_id,
                    product_id=old_code.product_id,
                    cis_code=_cis(f"CORRECT085{i}"),
                    source="pool",
                    status="available",
                )
            )
        await session.commit()
    corrected = await async_client.post(
        url,
        headers=headers,
        json={
            **payload,
            "order_ids": [str(order.order_id) for order in orders[:3]],
        },
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["order_errors"] == [], corrected.text
    assert len(corrected.json()["orders"]) == 3
    assert await inventory_snapshot() == before


@pytest.mark.asyncio
async def test_clear_after_pool_to_external_replacement_releases_marking_need(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, _supply_id, orders = await seed_selection(async_client)
    before = await inventory_snapshot()
    _patch_wb_acceptance(monkeypatch)

    async def delete_ok(client, **kwargs):
        pass

    monkeypatch.setattr("app.services.fbs_kiz_service.delete_marketplace_order_meta", delete_ok)
    replacement = await async_client.post(
        "/operations/fbs-orders/kiz/commit",
        headers=headers,
        json={
            "idempotency_key": "replace-before-clear085",
            "pairs": [
                {
                    "order_id": str(orders[0].order_id),
                    "value": _cis("EXTERNAL085"),
                    "confirmed": True,
                }
            ],
        },
    )
    assert replacement.status_code == 200, replacement.text
    assert replacement.json()[0]["status"] == "ok", replacement.text
    cleared = await async_client.delete(
        f"/operations/fbs-orders/{orders[0].order_id}/kiz",
        headers=headers,
    )
    assert cleared.status_code == 204, cleared.text
    async with SessionLocal() as session:
        line = await session.get(PackagingTaskLine, orders[0].packaging_task_line_id)
        assert line
        assert line.qty_marking_printed == line.qty_marking_external == 0
    assert await inventory_snapshot() == before


@pytest.mark.asyncio
async def test_clear_rejected_code_keeps_code_in_history(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, _supply_id, orders = await seed_selection(async_client)
    before = await inventory_snapshot()
    async with SessionLocal() as session:
        marking = (await session.execute(select(FbsOrderMarking))).scalar_one()
        marking.meta_status = "rejected"
        await session.commit()

    async def delete_ok(client, **kwargs):
        pass

    monkeypatch.setattr("app.services.fbs_kiz_service.delete_marketplace_order_meta", delete_ok)
    response = await async_client.delete(
        f"/operations/fbs-orders/{orders[0].order_id}/kiz",
        headers=headers,
    )
    assert response.status_code == 204, response.text
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(FbsOrderMarking)) == 0
        detached = await session.scalar(
            select(MarkingCode).where(MarkingCode.cis_code == _cis("USED085"))
        )
        assert detached is not None
        assert detached.status == "applied"
        assert detached.source == "pool"
        assert detached.packaging_task_line_id is None
        event = (await session.execute(
            select(MarkingCodeEvent).where(MarkingCodeEvent.code_id == detached.id)
        )).scalar_one()
        assert event.event_type == "voided"
        assert event.reason == "отмена оператором"
        assert event.packaging_task_line_id == orders[0].packaging_task_line_id
    assert await inventory_snapshot() == before
