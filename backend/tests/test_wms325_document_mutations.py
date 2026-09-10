"""WMS-325 bounded writers: real transactions and authenticated HTTP identity."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.document_event import DocumentEvent
from app.models.fbs_order import FbsOrder
from app.models.fbs_packing_box import FbsPackingBox, FbsPackingBoxItem
from app.models.fbs_print_asset import FbsPrintAsset
from app.models.fbs_supply import FbsSupply
from app.models.inbound_intake import InboundIntakeRequest
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.marketplace_unload import (
    MarketplaceUnloadBox,
    MarketplaceUnloadBoxLine,
    MarketplaceUnloadRequest,
)
from app.models.operation_fact import OperationFact
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.user import User
from app.models.warehouse_box import WarehouseBox
from app.services import document_event_service as audit
from app.services import fbs_packing_box_service as boxes
from app.services import fbs_print_asset_service as printing
from app.services import packaging_task_service as packaging
from tests.test_document_events import _register_admin, _seed_document_data


async def seed(client):
    headers, claims = await _register_admin(client)
    data = await _seed_document_data(client, headers)
    ids = {key: uuid.UUID(value) for key, value in data.items()}
    ids.update(tenant_id=uuid.UUID(claims["tenant_id"]), user_id=uuid.UUID(claims["sub"]))
    async with SessionLocal() as session:
        session.add(
            InventoryBalance(
                tenant_id=ids["tenant_id"],
                product_id=ids["product_id"],
                storage_location_id=ids["location_id"],
                quantity=20,
                quantity_unpacked=20,
                quantity_packed=0,
            )
        )
        await session.commit()
    return headers, ids


async def history(client, headers, kind, doc_id):
    response = await client.get(
        "/operations/document-events",
        headers=headers,
        params={"document_type": kind, "document_id": str(doc_id)},
    )
    assert response.status_code == 200, response.text
    return list(reversed(response.json()))


async def test_outbound_http_auth_mutations_noop_and_snapshot(async_client: AsyncClient):
    h, ids = await seed(async_client)
    base = "/operations/outbound-shipment-requests"
    created = await async_client.post(
        base, headers=h, json={"warehouse_id": str(ids["warehouse_id"])}
    )
    assert created.status_code == 201, created.text
    rid = created.json()["id"]
    body = {
        "product_id": str(ids["product_id"]),
        "quantity": 5,
        "storage_location_id": str(ids["location_id"]),
        "actor_user_id": str(uuid.uuid4()),
    }
    added = await async_client.post(f"{base}/{rid}/lines", headers=h, json=body)
    assert added.status_code == 201, added.text
    lid = added.json()["id"]
    before = await history(async_client, h, "outbound_shipment", rid)
    # Same location is a true no-op; duplicate line must roll back without a fact.
    same = await async_client.patch(
        f"{base}/{rid}/lines/{lid}",
        headers=h,
        json={"storage_location_id": str(ids["location_id"])},
    )
    assert same.status_code == 200, same.text
    duplicate = await async_client.post(f"{base}/{rid}/lines", headers=h, json=body)
    assert duplicate.status_code >= 400
    assert await history(async_client, h, "outbound_shipment", rid) == before
    submitted = await async_client.post(
        f"{base}/{rid}/submit", headers=h, json={"planned_shipment_date": "2026-09-12"}
    )
    assert submitted.status_code == 200, submitted.text
    shipped = await async_client.post(
        f"{base}/{rid}/lines/{lid}/ship", headers=h, json={"quantity": 2}
    )
    assert shipped.status_code == 200, shipped.text
    posted = await async_client.post(f"{base}/{rid}/post", headers=h)
    assert posted.status_code == 200, posted.text
    rows = await history(async_client, h, "outbound_shipment", rid)
    assert [r["event_type"] for r in rows] == [
        "document_created",
        "line_added",
        "status_changed",
        "data_changed",
        "status_changed",
    ]
    assert rows[2]["payload"]["before"]["status"] == "draft"
    assert rows[2]["payload"]["after"]["planned_shipment_date"] == "2026-09-12"
    assert rows[3]["payload"]["before"]["lines"][0]["shipped_qty"] == 0
    assert rows[3]["payload"]["after"]["lines"][0]["shipped_qty"] == 2
    assert rows[4]["payload"]["after"]["lines"][0]["shipped_qty"] == 5
    for row in rows:
        assert row["actor"]["id"] == str(ids["user_id"])
        assert row["source"] == "user"
        assert set(row["payload"]) == {
            "before",
            "after",
            "actor_name_snapshot",
            "actor_user_id_snapshot",
        }
    old_name = rows[0]["actor"]["name"]
    async with SessionLocal() as session:
        user = await session.get(User, ids["user_id"])
        user.email = "renamed@example.com"
        await session.commit()
        assert await session.scalar(select(InventoryBalance.quantity)) == 15
        assert await session.scalar(select(func.sum(InventoryMovement.quantity_delta))) == -5
    renamed = await history(async_client, h, "outbound_shipment", rid)
    assert all(row["actor"]["name"] == old_name for row in renamed)
    other_h, _ = await _register_admin(async_client)
    assert await history(async_client, other_h, "outbound_shipment", rid) == []


async def test_outbound_delete_last_line_preserves_composition(async_client):
    h, ids = await seed(async_client)
    base = "/operations/outbound-shipment-requests"
    created = await async_client.post(
        base, headers=h, json={"warehouse_id": str(ids["warehouse_id"])}
    )
    rid = created.json()["id"]
    added = await async_client.post(
        f"{base}/{rid}/lines", headers=h, json={"product_id": str(ids["product_id"]), "quantity": 3}
    )
    assert added.status_code == 201, added.text
    lid = added.json()["id"]
    removed = await async_client.delete(f"{base}/{rid}/lines/{lid}", headers=h)
    assert removed.status_code == 200, removed.text
    rows = await history(async_client, h, "outbound_shipment", rid)
    assert rows[-1]["event_type"] == "line_removed"
    assert rows[-1]["payload"]["before"]["lines"][0]["line_id"] == lid
    assert rows[-1]["payload"]["after"]["lines"] == []
    assert rows[-1]["payload"]["after"]["seller_id"] is None


@pytest.mark.parametrize("decision", ["approve", "reject"])
async def test_discrepancy_lifecycle_and_line_deletion(async_client, decision):
    h, ids = await seed(async_client)
    async with SessionLocal() as session:
        inbound = InboundIntakeRequest(
            tenant_id=ids["tenant_id"],
            warehouse_id=ids["warehouse_id"],
            seller_id=ids["seller_id"],
            status="draft",
        )
        session.add(inbound)
        await session.commit()
        inbound_id = inbound.id
    base = "/operations/discrepancy-acts"
    created = await async_client.post(
        base, headers=h, json={"inbound_intake_request_id": str(inbound_id)}
    )
    assert created.status_code == 201, created.text
    aid = created.json()["id"]
    line_body = {"product_id": str(ids["product_id"]), "quantity": 2}
    added = await async_client.post(f"{base}/{aid}/lines", headers=h, json=line_body)
    assert added.status_code == 201, added.text
    removed = await async_client.delete(f"{base}/{aid}/lines/{added.json()['id']}", headers=h)
    assert removed.status_code == 204, removed.text
    added = await async_client.post(f"{base}/{aid}/lines", headers=h, json=line_body)
    assert added.status_code == 201, added.text
    submitted = await async_client.post(f"{base}/{aid}/submit", headers=h)
    assert submitted.status_code == 200, submitted.text
    decided = await async_client.post(f"{base}/{aid}/{decision}", headers=h)
    assert decided.status_code == 200, decided.text
    rows = await history(async_client, h, "discrepancy_act", aid)
    assert [r["event_type"] for r in rows] == [
        "document_created",
        "line_added",
        "line_removed",
        "line_added",
        "status_changed",
        "status_changed",
    ]
    assert rows[-1]["payload"]["before"]["status"] == "confirmed"
    assert rows[-1]["payload"]["after"]["status"] == (
        "approved" if decision == "approve" else "rejected"
    )
    assert all(row["actor"]["id"] == str(ids["user_id"]) for row in rows)
    retry = await async_client.post(f"{base}/{aid}/{decision}", headers=h)
    assert retry.status_code >= 400
    assert await history(async_client, h, "discrepancy_act", aid) == rows
    async with SessionLocal() as session:
        movements = list((await session.scalars(select(InventoryMovement))).all())
        assert len(movements) == (1 if decision == "approve" else 0)
        if movements:
            assert movements[0].quantity_delta == 2
            assert movements[0].actor_user_id == ids["user_id"]


async def seed_box(ids, count=2):
    async with SessionLocal() as session:
        supply = FbsSupply(
            tenant_id=ids["tenant_id"],
            seller_id=ids["seller_id"],
            warehouse_id=ids["warehouse_id"],
            name="Synthetic",
            status="assembling",
            delivery_type="warehouse_sc",
        )
        session.add(supply)
        await session.flush()
        box = FbsPackingBox(
            tenant_id=ids["tenant_id"],
            supply_id=supply.id,
            box_number=1,
            warehouse_box=WarehouseBox(
                tenant_id=ids["tenant_id"],
                warehouse_id=ids["warehouse_id"],
                internal_barcode="AUDIT-BOX",
            ),
        )
        session.add(box)
        await session.flush()
        orders = []
        for number in range(count):
            order = FbsOrder(
                tenant_id=ids["tenant_id"],
                seller_id=ids["seller_id"],
                warehouse_id=ids["warehouse_id"],
                supply_id=supply.id,
                wb_order_id=number + 1,
                created_at_wb=datetime.now(UTC),
                deadline_at=datetime.now(UTC),
                mapping_status="mapped",
                reserve_status="reserved",
                sticker_status="ready",
            )
            session.add(order)
            await session.flush()
            session.add(
                FbsPackingBoxItem(
                    tenant_id=ids["tenant_id"],
                    box_id=box.id,
                    fbs_order_id=order.id,
                    assigned_by_user_id=ids["user_id"],
                )
            )
            orders.append(order.id)
        await session.commit()
        return supply.id, box.id, orders


async def test_boxes_removal_clear_delete_actor_and_rollback(async_client):
    h, ids = await seed(async_client)
    sid, bid, orders = await seed_box(ids)
    async with SessionLocal() as session:
        remover = User(
            tenant_id=ids["tenant_id"],
            email="remover@example.com",
            password_hash="synthetic-unused",
            role="fulfillment_admin",
        )
        session.add(remover)
        await session.commit()
        remover_id = remover.id
    async with SessionLocal() as session:
        with audit.document_event_actor(remover_id):
            await boxes.remove_order(session, ids["tenant_id"], sid, bid, orders[0])
            await session.rollback()
    assert await history(async_client, h, "fbs_supply", sid) == []
    async with SessionLocal() as session:
        with audit.document_event_actor(remover_id):
            await boxes.remove_order(session, ids["tenant_id"], sid, bid, orders[0])
            await session.commit()
            await boxes.clear_box(session, ids["tenant_id"], sid, bid)
            await session.commit()
            await boxes.clear_box(session, ids["tenant_id"], sid, bid)
            await session.commit()
            await boxes.delete_box(session, ids["tenant_id"], sid, bid, "delete-audit-box")
            await session.commit()
        assert await session.get(FbsPackingBox, bid) is None
        assert await session.scalar(select(func.count()).select_from(FbsPackingBoxItem)) == 0
    rows = await history(async_client, h, "fbs_supply", sid)
    assert [row["event_type"] for row in rows] == [
        "box_item_removed",
        "box_item_removed",
        "box_deleted",
    ]
    assert {r["payload"]["before"]["fbs_order_id"] for r in rows[:2]} == {str(o) for o in orders}
    for row in rows[:2]:
        assert row["payload"]["before"]["assigned_by_user_id"] == str(ids["user_id"])
        assert row["payload"]["before"]["assigned_at"]
    assert all(row["actor"]["id"] == str(remover_id) for row in rows)
    async with SessionLocal() as session:
        remover = await session.get(User, remover_id)
        await session.delete(remover)
        await session.commit()
    after_delete = await history(async_client, h, "fbs_supply", sid)
    assert all(
        row["actor"] == {"id": str(remover_id), "name": "remover@example.com"}
        for row in after_delete
    )


async def test_distribution_both_directions_and_noop(async_client):
    h, ids = await seed(async_client)
    sid, _, _ = await seed_box(ids, count=0)
    async with SessionLocal() as session:
        with audit.document_event_actor(ids["user_id"]):
            for enabled in (True, True, False, False):
                await boxes.set_boxes_without_distribution(
                    session, ids["tenant_id"], sid, enabled, actor_user_id=ids["user_id"]
                )
                await session.commit()
    rows = await history(async_client, h, "fbs_supply", sid)
    assert len(rows) == 2
    assert rows[0]["payload"]["before"]["enabled"] is False
    assert rows[0]["payload"]["after"]["enabled"] is True
    enabled_state = rows[0]["payload"]["after"]
    disabled_before = rows[1]["payload"]["before"]
    assert disabled_before["enabled"] is True
    assert disabled_before["boxes_without_distribution_by_user_id"] == str(ids["user_id"])
    assert datetime.fromisoformat(disabled_before["boxes_without_distribution_at"]) == (
        datetime.fromisoformat(enabled_state["boxes_without_distribution_at"])
    )
    assert rows[1]["payload"]["after"]["enabled"] is False
    assert rows[1]["actor"]["id"] == str(ids["user_id"])


async def test_print_first_open_http_identity_noop_and_rollback(async_client, monkeypatch):
    h, ids = await seed(async_client)
    sid, _, orders = await seed_box(ids, count=1)
    monkeypatch.setattr(printing, "read_print_file", lambda *args, **kwargs: b"synthetic-print")
    async with SessionLocal() as session:
        asset = FbsPrintAsset(
            tenant_id=ids["tenant_id"],
            seller_id=ids["seller_id"],
            fbs_supply_id=sid,
            fbs_order_id=orders[0],
            kind="order_sticker",
            status="ready",
            storage_path="synthetic.png",
            content_type="image/png",
        )
        session.add(asset)
        await session.commit()
        aid = asset.id
        with audit.document_event_actor(ids["user_id"]):
            await printing.get_asset_binary_content(
                session, ids["tenant_id"], aid, user_id=uuid.uuid4(), record_print_opened=False
            )
            await session.commit()
            await printing.get_asset_binary_content(
                session, ids["tenant_id"], aid, user_id=uuid.uuid4()
            )
            await session.rollback()
    assert await history(async_client, h, "fbs_order", orders[0]) == []
    for _ in range(2):
        response = await async_client.get(f"/operations/fbs-print-assets/{aid}/content", headers=h)
        assert response.status_code == 200, response.text
    rows = await history(async_client, h, "fbs_order", orders[0])
    assert len(rows) == 1
    assert rows[0]["event_type"] == "print_opened"
    assert rows[0]["payload"]["before"]["sticker_status"] == "ready"
    assert rows[0]["payload"]["after"]["sticker_status"] == "print_opened"
    assert rows[0]["actor"]["id"] == str(ids["user_id"])
    assert "synthetic.png" not in str(rows)


async def test_confirm_packed_http_quantity_status_no_extra_work(async_client):
    h, ids = await seed(async_client)
    async with SessionLocal() as session:
        task = PackagingTask(
            tenant_id=ids["tenant_id"], warehouse_id=ids["warehouse_id"], status="draft"
        )
        task.lines = [
            PackagingTaskLine(
                product_id=ids["product_id"],
                storage_location_id=ids["location_id"],
                qty_total=10,
                qty_suggested_packed=3,
            )
        ]
        session.add(task)
        await session.commit()
        tid, lid = task.id, task.lines[0].id
    for qty in (3, 3, 1):
        response = await async_client.post(
            f"/operations/packaging-tasks/{tid}/lines/{lid}/confirm-packed",
            headers=h,
            json={"quantity": qty},
        )
        assert response.status_code == 200, response.text
    rows = await history(async_client, h, "packaging_task", tid)
    assert len(rows) == 2
    assert rows[0]["payload"]["before"]["status"] == "draft"
    assert rows[0]["payload"]["after"]["status"] == "in_progress"
    assert rows[1]["payload"]["before"]["qty_confirmed_packed"] == 3
    assert rows[1]["payload"]["after"]["qty_confirmed_packed"] == 1
    assert all(row["actor"]["id"] == str(ids["user_id"]) for row in rows)
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(OperationFact)) == 0
        assert await session.scalar(select(func.count()).select_from(InventoryMovement)) == 0
        assert await session.scalar(select(InventoryBalance.quantity)) == 20


async def test_box_pack_recalculation_system_even_with_viewer(async_client):
    h, ids = await seed(async_client)
    async with SessionLocal() as session:
        unload = MarketplaceUnloadRequest(
            tenant_id=ids["tenant_id"],
            warehouse_id=ids["warehouse_id"],
            seller_id=ids["seller_id"],
            status="confirmed",
        )
        session.add(unload)
        await session.flush()
        box = MarketplaceUnloadBox(request_id=unload.id, box_preset="standard")
        box.lines = [MarketplaceUnloadBoxLine(product_id=ids["product_id"], quantity=4)]
        session.add(box)
        task = PackagingTask(
            tenant_id=ids["tenant_id"],
            warehouse_id=ids["warehouse_id"],
            marketplace_unload_request_id=unload.id,
            status="draft",
        )
        task.lines = [
            PackagingTaskLine(
                product_id=ids["product_id"],
                storage_location_id=ids["location_id"],
                qty_total=10,
                qty_suggested_packed=0,
            )
        ]
        session.add(task)
        await session.commit()
        tid = task.id
        with audit.document_event_actor(ids["user_id"]):
            await packaging.sync_mp_task_packed_from_boxes(session, ids["tenant_id"], task)
            await session.rollback()
            task = await packaging.get_task(session, ids["tenant_id"], tid)
            await packaging.sync_mp_task_packed_from_boxes(session, ids["tenant_id"], task)
            await session.commit()
            await packaging.sync_mp_task_packed_from_boxes(session, ids["tenant_id"], task)
            await session.commit()
        assert await session.scalar(select(func.count()).select_from(OperationFact)) == 0
        assert await session.scalar(select(func.count()).select_from(InventoryMovement)) == 0
        assert await session.scalar(select(InventoryBalance.quantity)) == 20
    rows = await history(async_client, h, "packaging_task", tid)
    assert len(rows) == 1
    assert rows[0]["source"] == "system" and rows[0]["actor"] is None
    assert rows[0]["payload"]["before"]["qty_packed_in_task"] == 0
    assert rows[0]["payload"]["after"]["qty_packed_in_task"] == 4
    assert rows[0]["payload"]["before"]["status"] == "draft"
    assert rows[0]["payload"]["after"]["status"] == "in_progress"


async def test_history_storage_failure_does_not_block_outbound(async_client):
    from sqlalchemy import text

    from app.db.session import engine

    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL savepoint failure test")
    h, ids = await seed(async_client)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "ALTER TABLE document_event ADD CONSTRAINT wms325_test_reject "
                "CHECK (event_type <> 'document_created')"
            )
        )
    try:
        created = await async_client.post(
            "/operations/outbound-shipment-requests",
            headers=h,
            json={"warehouse_id": str(ids["warehouse_id"])},
        )
        assert created.status_code == 201, created.text
        rid = created.json()["id"]
        reread = await async_client.get(f"/operations/outbound-shipment-requests/{rid}", headers=h)
        assert reread.status_code == 200, reread.text
        assert await history(async_client, h, "outbound_shipment", rid) == []
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("ALTER TABLE document_event DROP CONSTRAINT wms325_test_reject")
            )


@pytest.mark.parametrize("kind", ["outbound_shipment", "discrepancy_act"])
async def test_creation_audit_rolls_back_with_document(async_client, monkeypatch, kind):
    from unittest.mock import AsyncMock

    from app.models.discrepancy_act import DiscrepancyAct
    from app.models.outbound_shipment import OutboundShipmentRequest
    from app.services import discrepancy_act_service, outbound_shipment_service

    _h, ids = await seed(async_client)
    async with SessionLocal() as session:
        with audit.document_event_actor(ids["user_id"]):
            with monkeypatch.context() as scoped:
                scoped.setattr(
                    session, "commit", AsyncMock(side_effect=RuntimeError("synthetic abort"))
                )
                with pytest.raises(RuntimeError, match="synthetic abort"):
                    if kind == "outbound_shipment":
                        await outbound_shipment_service.create_request(
                            session, ids["tenant_id"], warehouse_id=ids["warehouse_id"]
                        )
                    else:
                        await discrepancy_act_service.create_act(session, ids["tenant_id"])
                assert await session.scalar(select(func.count()).select_from(DocumentEvent)) == 1
            await session.rollback()
        model = OutboundShipmentRequest if kind == "outbound_shipment" else DiscrepancyAct
        assert await session.scalar(select(func.count()).select_from(model)) == 0
        assert await session.scalar(select(func.count()).select_from(DocumentEvent)) == 0
