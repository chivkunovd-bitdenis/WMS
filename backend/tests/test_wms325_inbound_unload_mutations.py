"""WMS-325: bounded intake/unload writers, against an isolated PostgreSQL database."""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text

from app.db.session import SessionLocal
from app.models.document_event import DocumentEvent
from app.models.inbound_intake import InboundIntakeBox, InboundIntakeRequest
from app.models.inventory_movement import InventoryMovement
from app.models.marketplace_unload import MarketplaceUnloadBox, MarketplaceUnloadRequest
from app.models.operation_fact import OperationFact
from app.models.tenant import Tenant
from app.models.user import User
from app.services import document_event_service as audit
from app.services import inbound_intake_box_service as inbound_boxes
from app.services import inbound_intake_service as inbound
from app.services import marketplace_unload_box_service as unload_boxes
from app.services import marketplace_unload_service as unload
from tests.test_document_events import _register_admin, _seed_document_data

INBOUND = "/operations/inbound-intake-requests"
UNLOAD = "/operations/marketplace-unload-requests"


async def seed(client: AsyncClient) -> tuple[dict[str, str], dict[str, uuid.UUID]]:
    headers, claims = await _register_admin(client)
    data = await _seed_document_data(client, headers)
    ids = {key: uuid.UUID(value) for key, value in data.items()}
    ids.update(tenant_id=uuid.UUID(str(claims["tenant_id"])), user_id=uuid.UUID(str(claims["sub"])))
    return headers, ids


async def create(
    client: AsyncClient,
    headers: dict[str, str],
    ids: dict[str, uuid.UUID],
    base: str = INBOUND,
) -> str:
    response = await client.post(
        base,
        headers=headers,
        json={
            "warehouse_id": str(ids["warehouse_id"]),
            "seller_id": str(ids["seller_id"]),
            "actor_user_id": str(uuid.uuid4()),
            "free_text": "DO-NOT-AUDIT-THIS-NOTE",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def events(doc_id: str | uuid.UUID) -> list[DocumentEvent]:
    async with SessionLocal() as session:
        return list(
            (
                await session.scalars(
                    select(DocumentEvent)
                    .where(
                        DocumentEvent.document_id == uuid.UUID(str(doc_id)),
                    )
                    .order_by(DocumentEvent.occurred_at, DocumentEvent.id)
                )
            ).all()
        )


def mutations(rows: list[DocumentEvent]) -> list[DocumentEvent]:
    return [row for row in rows if row.event_type in {"document_created", "data_changed"}]


async def set_status(
    model: type[InboundIntakeRequest] | type[MarketplaceUnloadRequest],
    doc_id: str,
    value: str,
) -> None:
    async with SessionLocal() as session:
        obj = await session.get(model, uuid.UUID(str(doc_id)))
        assert isinstance(obj, (InboundIntakeRequest, MarketplaceUnloadRequest))
        obj.status = value
        await session.commit()


async def test_inbound_fields_noop_storage_actor_snapshot_and_no_observer_duplicates(
    async_client: AsyncClient,
) -> None:
    h, ids = await seed(async_client)
    rid = await create(async_client, h, ids)
    initial = mutations(await events(rid))
    assert len(initial) == 1 and initial[0].event_type == "document_created"
    assert initial[0].payload_json["before"] is None
    patch = {"planned_box_count": 3, "waybill_number": "  WAYBILL-325  "}
    for _ in range(2):
        response = await async_client.patch(f"{INBOUND}/{rid}", headers=h, json=patch)
        assert response.status_code == 200, response.text
    changes = mutations(await events(rid))
    assert len(changes) == 2
    changed = next(row for row in changes if row.event_type == "data_changed")
    assert changed.payload_json["before"] == {"planned_box_count": None, "waybill_number": None}
    assert changed.payload_json["after"] == {
        "planned_box_count": 3,
        "waybill_number": "WAYBILL-325",
    }
    # Date is already observed: exactly one existing event, no new explicit duplicate.
    response = await async_client.patch(
        f"{INBOUND}/{rid}", headers=h, json={"planned_delivery_date": "2026-09-15"}
    )
    assert response.status_code == 200, response.text
    rows = await events(rid)
    assert sum(row.event_type == "planned_date_changed" for row in rows) == 1
    assert len(mutations(rows)) == 2
    line = await async_client.post(
        f"{INBOUND}/{rid}/lines",
        headers=h,
        json={"product_id": str(ids["product_id"]), "expected_qty": 2},
    )
    assert line.status_code == 201, line.text
    lid = line.json()["id"]
    async with SessionLocal() as session:
        tenant = await session.get(Tenant, ids["tenant_id"])
        assert tenant is not None
        tenant.address_storage_enabled = True
        await session.commit()
    for _ in range(2):
        response = await async_client.patch(
            f"{INBOUND}/{rid}/lines/{lid}",
            headers=h,
            json={"storage_location_id": str(ids["location_id"])},
        )
        assert response.status_code == 200, response.text
    rows = await events(rid)
    locations = [row for row in mutations(rows) if row.payload_json["after"].get("line_id")]
    assert len(locations) == 1
    assert locations[0].payload_json["before"]["storage_location_id"] is None
    assert locations[0].payload_json["after"]["storage_location_id"] == str(ids["location_id"])
    assert sum(row.event_type == "line_added" for row in rows) == 1
    old_name = initial[0].payload_json["actor_name_snapshot"]
    async with SessionLocal() as session:
        tenant = await session.get(Tenant, ids["tenant_id"])
        assert tenant is not None
        tenant.address_storage_enabled = False
        user = await session.get(User, ids["user_id"])
        assert user is not None
        user.email = "renamed-wms325@example.com"
        await session.commit()
    response = await async_client.patch(
        f"{INBOUND}/{rid}/lines/{lid}",
        headers=h,
        json={"storage_location_id": str(ids["location_id"])},
    )
    assert response.status_code == 200, response.text
    rows = mutations(await events(rid))
    assert len(rows) == 4
    assert any(
        r.payload_json["before"].get("storage_location_id") == str(ids["location_id"])
        and r.payload_json["after"]["storage_location_id"] is None
        for r in rows
        if r.payload_json["before"]
    )
    for row in rows:
        assert row.actor_user_id == ids["user_id"] and row.source == "user"
        assert row.payload_json["actor_user_id_snapshot"] == str(ids["user_id"])
        assert "DO-NOT-AUDIT-THIS-NOTE" not in json.dumps(row.payload_json)
    assert (await events(rid))[0].payload_json["actor_name_snapshot"] == old_name


async def test_inbound_box_damage_close_print_delete_and_tenant_boundary(
    async_client: AsyncClient,
) -> None:
    h, ids = await seed(async_client)
    rid = await create(async_client, h, ids)
    await set_status(InboundIntakeRequest, rid, "receiving")
    response = await async_client.post(f"{INBOUND}/{rid}/boxes", headers=h)
    assert response.status_code == 201, response.text
    bid = response.json()["id"]
    foreign_h, _ = await _register_admin(async_client)
    damage_url = f"{INBOUND}/{rid}/boxes/{bid}/damaged"
    for headers, expected in [(foreign_h, 404), ({}, 401)]:
        response = await async_client.patch(damage_url, headers=headers, json={"is_damaged": True})
        assert response.status_code == expected, response.text
    for value in (True, True, False):
        response = await async_client.patch(
            damage_url, headers=h, json={"is_damaged": value, "actor_user_id": str(uuid.uuid4())}
        )
        assert response.status_code == 200, response.text
    response = await async_client.post(f"{INBOUND}/{rid}/boxes/{bid}/close", headers=h)
    assert response.status_code == 200, response.text
    retry = await async_client.post(f"{INBOUND}/{rid}/boxes/{bid}/close", headers=h)
    assert retry.status_code == 409, retry.text
    for _ in range(2):
        response = await async_client.post(
            f"{INBOUND}/{rid}/boxes/{bid}/mark-label-printed", headers=h
        )
        assert response.status_code == 200, response.text
    response = await async_client.delete(f"{INBOUND}/{rid}/boxes/{bid}", headers=h)
    assert response.status_code == 204, response.text
    rows = [r for r in mutations(await events(rid)) if r.event_type == "data_changed"]
    assert len(rows) == 7  # creation, on/off, close, print/reprint, deletion
    damage_rows = [
        r
        for r in rows
        if r.payload_json["before"]
        and r.payload_json["after"]
        and r.payload_json["before"]["is_damaged"] != r.payload_json["after"]["is_damaged"]
    ]
    assert len(damage_rows) == 2
    deletion = next(r for r in rows if r.payload_json["after"] is None)
    assert deletion.payload_json["before"]["container_id"] == bid
    assert deletion.payload_json["before"]["intake_closed"] is True
    assert all(r.actor_user_id == ids["user_id"] and r.source == "user" for r in rows)
    async with SessionLocal() as session:
        assert await session.get(InboundIntakeBox, uuid.UUID(bid)) is None
        assert await session.scalar(select(func.count()).select_from(InventoryMovement)) == 0
        assert await session.scalar(select(func.count()).select_from(OperationFact)) == 0


async def test_cargo_and_precreated_boxes_survive_document_delete_and_creation_retry(
    async_client: AsyncClient,
) -> None:
    h, ids = await seed(async_client)
    rid = await create(async_client, h, ids)
    async with SessionLocal() as session:
        req = await inbound.get_request(session, ids["tenant_id"], uuid.UUID(rid))
        assert req is not None
        with audit.document_event_actor(ids["user_id"]):
            boxes = await inbound_boxes.create_boxes_for_request(
                session,
                ids["tenant_id"],
                req,
                box_count=2,
            )
            await session.commit()
            again = await inbound_boxes.create_boxes_for_request(
                session,
                ids["tenant_id"],
                req,
                box_count=2,
            )
            await session.commit()
        assert {b.id for b in boxes} == {b.id for b in again}
        box_ids = {str(b.id) for b in boxes}
    response = await async_client.post(
        f"{INBOUND}/{rid}/cargo-places", headers=h, json={"quantity": 2}
    )
    assert response.status_code == 201, response.text
    place_ids = {p["id"] for p in response.json()}
    for pid in place_ids:
        response = await async_client.post(
            f"{INBOUND}/{rid}/cargo-places/{pid}/mark-label-printed",
            headers=h,
        )
        assert response.status_code == 200, response.text
    response = await async_client.delete(f"{INBOUND}/{rid}", headers=h)
    assert response.status_code == 204, response.text
    rows = mutations(await events(rid))
    assert len(rows) == 8  # doc + 2 boxes + 2 cargo + 2 prints + doc deletion
    deletion = next(r for r in rows if r.payload_json["after"] is None)
    assert {c["container_id"] for c in deletion.payload_json["before"]["containers"]} == (
        box_ids | place_ids
    )
    assert all(r.actor_user_id == ids["user_id"] for r in rows)
    async with SessionLocal() as session:
        assert await session.get(InboundIntakeRequest, uuid.UUID(rid)) is None


async def test_unload_box_lifecycle_and_document_cascade(async_client: AsyncClient) -> None:
    h, ids = await seed(async_client)
    rid = await create(async_client, h, ids, UNLOAD)
    await set_status(MarketplaceUnloadRequest, rid, "confirmed")
    response = await async_client.post(
        f"{UNLOAD}/{rid}/boxes", headers=h, json={"box_preset": "60_40_40"}
    )
    assert response.status_code == 201, response.text
    bid = response.json()["id"]
    response = await async_client.post(f"{UNLOAD}/{rid}/boxes/{bid}/close", headers=h)
    assert response.status_code == 200, response.text
    response = await async_client.post(f"{UNLOAD}/{rid}/boxes/{bid}/close", headers=h)
    assert response.status_code == 409, response.text
    response = await async_client.delete(f"{UNLOAD}/{rid}/boxes/{bid}", headers=h)
    assert response.status_code == 204, response.text
    response = await async_client.post(
        f"{UNLOAD}/{rid}/boxes/batch", headers=h, json={"count": 2, "box_preset": "60_40_40"}
    )
    assert response.status_code == 201, response.text
    batch_ids = {b["id"] for b in response.json()}
    rows = await events(rid)
    assert sum(r.event_type == "status_changed" for r in rows) == 2  # fixture + real collecting
    assert len(mutations(rows)) == 6
    await set_status(MarketplaceUnloadRequest, rid, "draft")
    response = await async_client.delete(f"{UNLOAD}/{rid}", headers=h)
    assert response.status_code == 204, response.text
    rows = mutations(await events(rid))
    assert len(rows) == 7
    deleted = next(
        r
        for r in rows
        if r.payload_json["after"] is None and "request_id" in r.payload_json["before"]
    )
    assert {c["container_id"] for c in deleted.payload_json["before"]["containers"]} == batch_ids
    assert all(r.actor_user_id == ids["user_id"] and r.source == "user" for r in rows)
    async with SessionLocal() as session:
        assert await session.get(MarketplaceUnloadRequest, uuid.UUID(rid)) is None
        assert await session.scalar(select(func.count()).select_from(InventoryMovement)) == 0
        assert await session.scalar(select(func.count()).select_from(OperationFact)) == 0


async def test_unload_automatic_empty_box_cleanup_records_system_context(
    async_client: AsyncClient,
) -> None:
    h, ids = await seed(async_client)
    rid = await create(async_client, h, ids, UNLOAD)
    await set_status(MarketplaceUnloadRequest, rid, "confirmed")
    async with SessionLocal() as session:
        with audit.document_event_actor(ids["user_id"]):
            boxes = await unload_boxes.create_boxes_batch(
                session,
                ids["tenant_id"],
                uuid.UUID(rid),
                count=2,
                box_preset="60_40_40",
            )
            box_ids = {str(b.id) for b in boxes}
            with audit.system_document_events():
                req = await unload.get_request(session, ids["tenant_id"], uuid.UUID(rid))
                assert req is not None
                await unload.delete_empty_boxes_for_ship(session, req)
                await session.commit()
    deletions = [r for r in mutations(await events(rid)) if r.payload_json["after"] is None]
    assert {r.payload_json["before"]["container_id"] for r in deletions} == box_ids
    assert all(r.source == "system" and r.actor_user_id is None for r in deletions)
    assert all("actor_name_snapshot" not in r.payload_json for r in deletions)


@pytest.mark.parametrize("kind", ["inbound", "unload"])
async def test_failed_business_commit_rolls_back_new_box_and_audit(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    h, ids = await seed(async_client)
    base = INBOUND if kind == "inbound" else UNLOAD
    rid = await create(async_client, h, ids, base)
    model = InboundIntakeRequest if kind == "inbound" else MarketplaceUnloadRequest
    await set_status(model, rid, "receiving" if kind == "inbound" else "confirmed")
    old_ids = {r.id for r in await events(rid)}
    async with SessionLocal() as session:

        async def reject_commit() -> None:
            # A real flush has persisted both writes in this still uncommitted transaction.
            await session.flush()
            raise RuntimeError("synthetic business commit rejected")

        monkeypatch.setattr(session, "commit", reject_commit)
        with audit.document_event_actor(ids["user_id"]), pytest.raises(RuntimeError):
            if kind == "inbound":
                await inbound_boxes.create_open_box(session, ids["tenant_id"], uuid.UUID(rid))
            else:
                await unload_boxes.create_open_box(
                    session,
                    ids["tenant_id"],
                    uuid.UUID(rid),
                    box_preset="60_40_40",
                )
        await session.rollback()
    assert {r.id for r in await events(rid)} == old_ids
    box_model = InboundIntakeBox if kind == "inbound" else MarketplaceUnloadBox
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(box_model)) == 0


@pytest.mark.parametrize("kind", ["inbound", "unload"])
async def test_postgres_audit_insert_failure_does_not_abort_document_create(
    async_client: AsyncClient, kind: str
) -> None:
    h, ids = await seed(async_client)
    async with SessionLocal() as session:
        assert session.bind is not None and session.bind.dialect.name == "postgresql"
        # Only our synthetic database; actual PostgreSQL error inside the existing savepoint.
        await session.execute(
            text("""
            CREATE FUNCTION wms325_reject_audit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'synthetic audit rejected'; END $$
        """)
        )
        await session.execute(
            text("""
            CREATE TRIGGER wms325_reject_audit BEFORE INSERT ON document_event
            FOR EACH ROW EXECUTE FUNCTION wms325_reject_audit()
        """)
        )
        await session.commit()
    try:
        base = INBOUND if kind == "inbound" else UNLOAD
        rid = await create(async_client, h, ids, base)
        model = InboundIntakeRequest if kind == "inbound" else MarketplaceUnloadRequest
        async with SessionLocal() as session:
            assert await session.get(model, uuid.UUID(rid)) is not None
        assert await events(rid) == []
    finally:
        async with SessionLocal() as session:
            await session.execute(text("DROP TRIGGER wms325_reject_audit ON document_event"))
            await session.execute(text("DROP FUNCTION wms325_reject_audit()"))
            await session.commit()


@pytest.mark.parametrize("flow", ["attach", "copy"])
async def test_unload_ready_box_writers_audit_once_after_success(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    flow: str,
) -> None:
    from tests.test_marketplace_unload_and_discrepancy_acts import (
        test_marketplace_unload_attach_allow_over_plan,
        test_marketplace_unload_box_remove_copy_delete,
    )

    # Reuse actual warehouse scenarios (including rejected operations and stock assertions).
    # Add the missing audit assertions without modifying the existing tests or their writers.
    if flow == "attach":
        await test_marketplace_unload_attach_allow_over_plan(async_client, monkeypatch)
    else:
        await test_marketplace_unload_box_remove_copy_delete(async_client, monkeypatch)
    async with SessionLocal() as session:
        rows = list(
            (
                await session.scalars(
                    select(DocumentEvent).where(
                        DocumentEvent.document_type == "marketplace_unload",
                        DocumentEvent.event_type == "data_changed",
                    )
                )
            ).all()
        )
        closed_creations = [
            r
            for r in rows
            if r.payload_json["before"] is None and r.payload_json["after"]["closed"]
        ]
        assert len(closed_creations) == 1  # failed attach/copy has no history artifact
        row = closed_creations[0]
        box = await session.get(
            MarketplaceUnloadBox, uuid.UUID(row.payload_json["after"]["container_id"])
        )
        assert box is not None and box.closed_at is not None
        assert box.request_id == row.document_id
        assert row.actor_user_id is not None and row.source == "user"
        assert row.payload_json["actor_user_id_snapshot"] == str(row.actor_user_id)
        actor = await session.get(User, row.actor_user_id)
        assert actor is not None and row.payload_json["actor_name_snapshot"] == actor.email


async def test_coordinator_zero_box_discrepancy_still_allows_receiving(
    async_client: AsyncClient,
) -> None:
    from tests.test_inbound_intake_service_be01 import _auth_ids, _setup_request

    tenant_id, actor_id = await _auth_ids(async_client)
    request_id, _ = await _setup_request(async_client, tenant_id, expected_qty=5)
    async with SessionLocal() as session:
        with audit.document_event_actor(actor_id):
            await inbound.begin_receiving(session, tenant_id, request_id, actor_user_id=actor_id)
            req = await inbound.get_request(session, tenant_id, request_id)
            assert req is not None
            await inbound.set_line_actual_qty(
                session,
                tenant_id,
                request_id,
                req.lines[0].id,
                actual_qty=5,
            )
            done = await inbound.complete_receiving(
                session,
                tenant_id,
                request_id,
                actor_user_id=actor_id,
            )
        assert done.planned_box_count == 1 and done.actual_box_count == 0
        assert done.boxes_discrepancy is True and done.has_discrepancy is True
        assert done.status == "sorting" and done.lines[0].actual_qty == 5
        assert await session.scalar(select(func.sum(InventoryMovement.quantity_delta))) == 5
