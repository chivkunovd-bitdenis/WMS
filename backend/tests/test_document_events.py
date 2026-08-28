from __future__ import annotations

import importlib.util
import logging
import os
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import BackgroundTasks, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.session import SessionLocal
from app.models.document_event import (
    DOCUMENT_TYPE_FBS_SUPPLY,
    DOCUMENT_TYPE_INBOUND_INTAKE,
    DOCUMENT_TYPE_MARKETPLACE_UNLOAD,
    EVENT_LINE_QTY_CHANGED,
    EVENT_PLANNED_DATE_CHANGED,
    EVENT_STATUS_CHANGED,
    SOURCE_SYSTEM,
    SOURCE_USER,
    DocumentEvent,
)
from app.models.fbs_order import FBS_ORDER_STATUS_CANCELLED, FBS_ORDER_STATUS_DONE, FbsOrder
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.inventory_balance import InventoryBalance
from app.models.marketplace_unload import (
    MarketplaceUnloadBox,
    MarketplaceUnloadBoxLine,
    MarketplaceUnloadLine,
    MarketplaceUnloadRequest,
)
from app.services import document_event_service as event_svc
from app.services import fbs_packaging_integration_service as fbs_packaging_svc
from app.services import fbs_shipment_service as fbs_shipment_svc
from app.services import fbs_tracking_service as fbs_tracking_svc
from app.services import inbound_intake_service as inbound_svc
from app.services import marketplace_unload_service as unload_svc
from app.services.document_event_service import (
    DocumentEventActorMiddleware,
    DocumentEventError,
    document_event_actor,
    record_document_event,
    system_document_events,
)
from app.services.marketplace_provider import FakeMarketplaceTransport, OzonMarketplaceProvider
from app.services.tokens import decode_access_token


async def _register_admin(async_client: AsyncClient) -> tuple[dict[str, str], dict[str, object]]:
    suffix = str(time.time_ns())
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Journal {suffix}",
            "slug": f"journal-{suffix}",
            "admin_email": f"journal-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    token = str(response.json()["access_token"])
    return {"Authorization": f"Bearer {token}"}, decode_access_token(token)


async def _seed_document_data(async_client: AsyncClient, headers: dict[str, str]) -> dict[str, str]:
    suffix = str(time.time_ns())
    seller = await async_client.post("/sellers", headers=headers, json={"name": f"Seller {suffix}"})
    assert seller.status_code in (200, 201), seller.text
    seller_id = seller.json()["id"]
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Journal warehouse", "code": f"journal-{suffix[-10:]}"},
    )
    assert warehouse.status_code == 200, warehouse.text
    warehouse_id = warehouse.json()["id"]
    location = await async_client.post(
        f"/warehouses/{warehouse_id}/locations",
        headers=headers,
        json={"code": f"CELL-{suffix[-6:]}"},
    )
    assert location.status_code == 200, location.text
    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Journal product",
            "sku_code": f"JOURNAL-{suffix}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    assert product.status_code == 200, product.text
    return {
        "seller_id": seller_id,
        "warehouse_id": warehouse_id,
        "location_id": location.json()["id"],
        "product_id": product.json()["id"],
    }


async def _create_inbound_draft(
    async_client: AsyncClient,
    headers: dict[str, str],
    data: dict[str, str],
    *,
    operation_type: str = "inbound",
    marketplace: str | None = None,
) -> tuple[str, str]:
    base = "/operations/inbound-intake-requests"
    request = await async_client.post(
        base,
        headers=headers,
        json={
            "warehouse_id": data["warehouse_id"],
            "seller_id": data["seller_id"],
            "operation_type": operation_type,
            "marketplace": marketplace,
        },
    )
    assert request.status_code == 201, request.text
    request_id = request.json()["id"]
    line = await async_client.post(
        f"{base}/{request_id}/lines",
        headers=headers,
        json={
            "product_id": data["product_id"],
            "expected_qty": 5,
            "storage_location_id": data["location_id"],
        },
    )
    assert line.status_code == 201, line.text
    return request_id, line.json()["id"]


# TC-NEW-DOCUMENT-JOURNAL-001 — full inbound status chain and admin-only paged read.
@pytest.mark.asyncio
async def test_inbound_status_chain_is_visible_through_document_events_api(
    async_client: AsyncClient,
) -> None:
    headers, token_payload = await _register_admin(async_client)
    data = await _seed_document_data(async_client, headers)
    request_id, line_id = await _create_inbound_draft(async_client, headers, data)
    base = "/operations/inbound-intake-requests"

    planned = await async_client.patch(
        f"{base}/{request_id}",
        headers=headers,
        json={"planned_box_count": 1, "planned_delivery_date": "2026-08-26"},
    )
    assert planned.status_code == 200, planned.text
    submitted = await async_client.post(f"{base}/{request_id}/submit", headers=headers)
    assert submitted.status_code == 200, submitted.text
    receiving = await async_client.post(f"{base}/{request_id}/begin-receiving", headers=headers)
    assert receiving.status_code == 200, receiving.text
    actual = await async_client.patch(
        f"{base}/{request_id}/lines/{line_id}/actual",
        headers=headers,
        json={"actual_qty": 5},
    )
    assert actual.status_code == 200, actual.text
    sorting = await async_client.post(f"{base}/{request_id}/verify", headers=headers)
    assert sorting.status_code == 200, sorting.text
    done = await async_client.post(f"{base}/{request_id}/post", headers=headers)
    assert done.status_code == 200, done.text

    response = await async_client.get(
        "/operations/document-events",
        headers=headers,
        params={
            "document_type": DOCUMENT_TYPE_INBOUND_INTAKE,
            "document_id": request_id,
            "limit": 50,
            "offset": 0,
        },
    )
    assert response.status_code == 200, response.text
    events = response.json()
    status_events = [event for event in reversed(events) if event["event_type"] == "status_changed"]
    assert [(event["payload"]["from"], event["payload"]["to"]) for event in status_events] == [
        ("draft", "submitted"),
        ("submitted", "receiving"),
        ("receiving", "sorting"),
        ("sorting", "done"),
    ]
    assert [event["qty"] for event in status_events] == [0, 0, 5, 5]
    assert all(event["source"] == SOURCE_USER for event in status_events)
    assert all(event["actor"]["id"] == token_payload["sub"] for event in status_events)
    assert all(event["actor"]["name"].startswith("journal-") for event in status_events)
    assert any(event["event_type"] == "line_added" for event in events)
    assert any(event["event_type"] == "planned_date_changed" for event in events)
    assert any(event["event_type"] == "line_qty_changed" for event in events)

    first_page = await async_client.get(
        "/operations/document-events",
        headers=headers,
        params={
            "document_type": DOCUMENT_TYPE_INBOUND_INTAKE,
            "document_id": request_id,
            "limit": 2,
            "offset": 0,
        },
    )
    second_page = await async_client.get(
        "/operations/document-events",
        headers=headers,
        params={
            "document_type": DOCUMENT_TYPE_INBOUND_INTAKE,
            "document_id": request_id,
            "limit": 2,
            "offset": 2,
        },
    )
    assert [row["id"] for row in first_page.json()] == [row["id"] for row in events[:2]]
    assert not {row["id"] for row in first_page.json()} & {row["id"] for row in second_page.json()}

    seller_email = f"journal-seller-{time.time_ns()}@example.com"
    account = await async_client.post(
        "/auth/seller-accounts",
        headers=headers,
        json={
            "seller_id": data["seller_id"],
            "email": seller_email,
            "password": "password123",
        },
    )
    assert account.status_code in (200, 201), account.text
    login = await async_client.post(
        "/auth/login", json={"email": seller_email, "password": "password123"}
    )
    seller_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    forbidden = await async_client.get(
        "/operations/document-events",
        headers=seller_headers,
        params={
            "document_type": DOCUMENT_TYPE_INBOUND_INTAKE,
            "document_id": request_id,
        },
    )
    assert forbidden.status_code == 403


# TC-NEW-DOCUMENT-JOURNAL-002 — idempotency, actor contract, duplicate qty changes, system source.
@pytest.mark.asyncio
async def test_event_write_contract_and_repeated_quantity_changes(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, token_payload = await _register_admin(async_client)
    data = await _seed_document_data(async_client, headers)
    request_id, line_id = await _create_inbound_draft(async_client, headers, data)
    tenant_id = uuid.UUID(str(token_payload["tenant_id"]))
    actor_id = uuid.UUID(str(token_payload["sub"]))

    async with SessionLocal() as session:
        inserted = await record_document_event(
            session,
            tenant_id=tenant_id,
            document_type=DOCUMENT_TYPE_INBOUND_INTAKE,
            document_id=uuid.UUID(request_id),
            event_type=EVENT_PLANNED_DATE_CHANGED,
            source=SOURCE_USER,
            actor_user_id=actor_id,
            payload_json={"field": "manual", "value_before": None, "value_after": "x"},
            idempotency_key=f"{request_id}:planned:manual",
        )
        duplicate = await record_document_event(
            session,
            tenant_id=tenant_id,
            document_type=DOCUMENT_TYPE_INBOUND_INTAKE,
            document_id=uuid.UUID(request_id),
            event_type=EVENT_PLANNED_DATE_CHANGED,
            source=SOURCE_USER,
            actor_user_id=actor_id,
            payload_json={"field": "manual", "value_before": None, "value_after": "x"},
            idempotency_key=f"{request_id}:planned:manual",
        )
        await session.commit()
    assert inserted is True
    assert duplicate is False

    original_execute = AsyncConnection.execute
    execute_calls = 0

    async def fail_first_execute(
        connection: AsyncConnection, *args: object, **kwargs: object
    ) -> object:
        nonlocal execute_calls
        execute_calls += 1
        if execute_calls == 1:
            raise IntegrityError("insert document_event", {}, RuntimeError("foreign key"))
        return await original_execute(connection, *args, **kwargs)  # type: ignore[call-overload]

    with monkeypatch.context() as patch:
        patch.setattr(AsyncConnection, "execute", fail_first_execute)
        async with SessionLocal() as session:
            with pytest.raises(IntegrityError, match="foreign key"):
                await record_document_event(
                    session,
                    tenant_id=tenant_id,
                    document_type=DOCUMENT_TYPE_INBOUND_INTAKE,
                    document_id=uuid.UUID(request_id),
                    event_type=EVENT_PLANNED_DATE_CHANGED,
                    source=SOURCE_USER,
                    actor_user_id=actor_id,
                    payload_json={"field": "manual"},
                    idempotency_key=f"{request_id}:not-a-duplicate",
                )

    async with SessionLocal() as session:
        for _ in range(2):
            assert await record_document_event(
                session,
                tenant_id=tenant_id,
                document_type=DOCUMENT_TYPE_INBOUND_INTAKE,
                document_id=uuid.UUID(request_id),
                event_type=EVENT_LINE_QTY_CHANGED,
                source=SOURCE_USER,
                actor_user_id=actor_id,
                qty=9,
                product_id=uuid.UUID(data["product_id"]),
                payload_json={"qty_before": 8, "qty_after": 9},
            )
        await session.commit()

    async with SessionLocal() as session:
        with pytest.raises(DocumentEventError, match="user_actor_required"):
            await record_document_event(
                session,
                tenant_id=tenant_id,
                document_type=DOCUMENT_TYPE_INBOUND_INTAKE,
                document_id=uuid.UUID(request_id),
                event_type=EVENT_STATUS_CHANGED,
                source=SOURCE_USER,
                actor_user_id=None,
                payload_json={"from": "draft", "to": "submitted"},
            )

    async with SessionLocal() as session:
        line = await session.get(InboundIntakeLine, uuid.UUID(line_id))
        assert line is not None
        with document_event_actor(actor_id):
            line.expected_qty = 7
            await session.commit()
            line.expected_qty = 7
            line.expected_qty = 8
            await session.commit()
        request = await session.get(InboundIntakeRequest, uuid.UUID(request_id))
        assert request is not None
        with system_document_events():
            request.planned_delivery_date = date(2026, 8, 27)
            await session.commit()

    async with SessionLocal() as session:
        rows = list(
            (
                await session.scalars(
                    select(DocumentEvent).where(DocumentEvent.document_id == uuid.UUID(request_id))
                )
            ).all()
        )
    qty_changes = [row for row in rows if row.event_type == EVENT_LINE_QTY_CHANGED]
    qty_pairs = [
        (row.payload_json["qty_before"], row.payload_json["qty_after"])
        for row in qty_changes
        if row.payload_json != {"qty_before": 8, "qty_after": 9}
    ]
    assert qty_pairs == [
        (5, 7),
        (7, 8),
    ]
    system_rows = [
        row
        for row in rows
        if row.event_type == EVENT_PLANNED_DATE_CHANGED and row.source == SOURCE_SYSTEM
    ]
    assert len(system_rows) == 1
    assert system_rows[0].actor_user_id is None
    identical_calls = [
        row for row in qty_changes if row.payload_json == {"qty_before": 8, "qty_after": 9}
    ]
    assert len(identical_calls) == 2


# TC-NEW-DOCUMENT-JOURNAL-003 — all FBS and unload statuses use factual quantities.
@pytest.mark.asyncio
async def test_fbs_and_marketplace_unload_status_sequences(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, token_payload = await _register_admin(async_client)
    data = await _seed_document_data(async_client, headers)
    tenant_id = uuid.UUID(str(token_payload["tenant_id"]))
    actor_id = uuid.UUID(str(token_payload["sub"]))
    seller_id = uuid.UUID(data["seller_id"])
    warehouse_id = uuid.UUID(data["warehouse_id"])
    product_id = uuid.UUID(data["product_id"])

    async with SessionLocal() as session:
        supply = FbsSupply(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            wb_supply_id="journal-supply",
            name="Journal supply",
            delivery_type="warehouse_sc",
        )
        session.add(supply)
        await session.flush()
        order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            wb_order_id=987654321,
            supply_id=supply.id,
            created_at_wb=datetime.now(UTC),
            deadline_at=datetime.now(UTC) + timedelta(days=1),
            mapping_status="mapped",
            reserve_status="reserved",
        )
        session.add(order)
        await session.commit()

        async def fulfillment_ready(*_args: object, **_kwargs: object) -> bool:
            return True

        monkeypatch.setattr(fbs_packaging_svc, "_all_active_orders_fulfilled", fulfillment_ready)
        with document_event_actor(actor_id):
            supply = await fbs_packaging_svc.update_supply_status(
                session,
                tenant_id,
                supply.id,
                FBS_SUPPLY_STATUS_ASSEMBLING,
            )
            await session.commit()
            supply.packaging_task_id = None
            await session.flush()
            promoted = await fbs_packaging_svc.try_promote_fbs_supply_if_ready(
                session, tenant_id, supply.id, actor_user_id=actor_id
            )
            assert promoted is not None
            assert promoted.status == FBS_SUPPLY_STATUS_PACKED
            await session.commit()
            await session.refresh(supply, attribute_names=["orders"])
            await fbs_shipment_svc._apply_local_delivered(session, supply, list(supply.orders))
            await session.commit()
            order.status = FBS_ORDER_STATUS_DONE
            await fbs_tracking_svc._maybe_complete_supply(session, supply)
            await session.commit()
        supply_id = supply.id

        unload = MarketplaceUnloadRequest(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            seller_id=seller_id,
            marketplace="ozon",
            status="draft",
            planned_shipment_date=date(2026, 8, 29),
        )
        session.add(unload)
        await session.flush()
        session.add(
            MarketplaceUnloadLine(
                request_id=unload.id,
                product_id=product_id,
                quantity=4,
            )
        )
        box = MarketplaceUnloadBox(request_id=unload.id, box_preset="manual")
        session.add(box)
        await session.flush()
        session.add(MarketplaceUnloadBoxLine(box_id=box.id, product_id=product_id, quantity=3))
        session.add(
            InventoryBalance(
                tenant_id=tenant_id,
                storage_location_id=uuid.UUID(data["location_id"]),
                product_id=product_id,
                quantity=10,
            )
        )
        await session.commit()
        with document_event_actor(actor_id):
            await unload_svc.plan_request(session, tenant_id, unload.id)
            await unload_svc.unplan_request(session, tenant_id, unload.id)
            await unload_svc.plan_request(session, tenant_id, unload.id)
            await unload_svc.confirm_request(session, tenant_id, unload.id)
            unload_svc.enter_collecting_if_needed(unload)
            await session.commit()

            async def packaging_done(*_args: object, **_kwargs: object) -> None:
                return None

            monkeypatch.setattr(
                "app.services.packaging_task_service.assert_unload_packaging_done",
                packaging_done,
            )
            await unload_svc.complete_unload(
                session,
                tenant_id,
                unload.id,
                acknowledge_discrepancy=True,
                performer_id=actor_id,
                ozon_provider=OzonMarketplaceProvider(transport=FakeMarketplaceTransport()),
            )
        cancelled = MarketplaceUnloadRequest(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            seller_id=seller_id,
            marketplace="ozon",
            status="draft",
            planned_shipment_date=date(2026, 8, 30),
        )
        session.add(cancelled)
        await session.flush()
        session.add(
            MarketplaceUnloadLine(
                request_id=cancelled.id,
                product_id=product_id,
                quantity=1,
            )
        )
        await session.commit()
        with document_event_actor(actor_id):
            await unload_svc.plan_request(session, tenant_id, cancelled.id)
            await unload_svc.cancel_request(session, tenant_id, cancelled.id, performer_id=actor_id)
        unload_id = unload.id
        cancelled_id = cancelled.id

    async with SessionLocal() as session:
        fbs_events = list(
            (
                await session.scalars(
                    select(DocumentEvent)
                    .where(
                        DocumentEvent.document_type == DOCUMENT_TYPE_FBS_SUPPLY,
                        DocumentEvent.document_id == supply_id,
                        DocumentEvent.event_type == EVENT_STATUS_CHANGED,
                    )
                    .order_by(DocumentEvent.occurred_at)
                )
            ).all()
        )
        unload_events = list(
            (
                await session.scalars(
                    select(DocumentEvent)
                    .where(
                        DocumentEvent.document_type == DOCUMENT_TYPE_MARKETPLACE_UNLOAD,
                        DocumentEvent.document_id == unload_id,
                        DocumentEvent.event_type == EVENT_STATUS_CHANGED,
                    )
                    .order_by(DocumentEvent.occurred_at)
                )
            ).all()
        )
        cancelled_events = list(
            (
                await session.scalars(
                    select(DocumentEvent).where(
                        DocumentEvent.document_id == cancelled_id,
                        DocumentEvent.event_type == EVENT_STATUS_CHANGED,
                    )
                )
            ).all()
        )
    assert [(row.payload_json["from"], row.payload_json["to"]) for row in fbs_events] == [
        ("draft", "assembling"),
        ("assembling", "packed"),
        ("packed", "in_delivery"),
        ("in_delivery", "done"),
    ]
    assert [row.qty for row in fbs_events] == [1, 1, 1, 1]
    assert [(row.payload_json["from"], row.payload_json["to"]) for row in unload_events] == [
        ("draft", "submitted"),
        ("submitted", "draft"),
        ("draft", "submitted"),
        ("submitted", "confirmed"),
        ("confirmed", "collecting"),
        ("collecting", "shipped"),
    ]
    assert [row.qty for row in unload_events] == [3, 3, 3, 3, 3, 3]
    assert [(row.payload_json["from"], row.payload_json["to"]) for row in cancelled_events] == [
        ("draft", "submitted"),
        ("submitted", "cancelled"),
    ]


# TC-NEW-DOCUMENT-JOURNAL-004 — journal insert failure is logged and warehouse commit survives.
@pytest.mark.asyncio
async def test_journal_failure_does_not_rollback_document_change(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    headers, token_payload = await _register_admin(async_client)
    data = await _seed_document_data(async_client, headers)
    request_id, _ = await _create_inbound_draft(async_client, headers, data)
    actor_id = uuid.UUID(str(token_payload["sub"]))

    def fail_insert(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("journal unavailable")

    monkeypatch.setattr(event_svc, "_insert_event_row", fail_insert)
    caplog.set_level(logging.ERROR, logger=event_svc.__name__)
    async with SessionLocal() as session:
        request = await session.get(InboundIntakeRequest, uuid.UUID(request_id))
        assert request is not None
        with document_event_actor(actor_id):
            request.planned_delivery_date = date(2026, 8, 30)
            await session.commit()

    async with SessionLocal() as session:
        request = await session.get(InboundIntakeRequest, uuid.UUID(request_id))
        assert request is not None
        assert request.planned_delivery_date == date(2026, 8, 30)
    assert "document event write failed" in caplog.text


# TC-NEW-DOCUMENT-JOURNAL-005 — every document-data event keeps its fixed payload schema.
@pytest.mark.asyncio
async def test_all_inbound_document_data_event_types(
    async_client: AsyncClient,
) -> None:
    headers, token_payload = await _register_admin(async_client)
    data = await _seed_document_data(async_client, headers)
    request_id, line_id = await _create_inbound_draft(async_client, headers, data)
    actor_id = uuid.UUID(str(token_payload["sub"]))
    second_warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Second journal warehouse", "code": f"journal-2-{time.time_ns()}"},
    )
    assert second_warehouse.status_code == 200, second_warehouse.text

    async with SessionLocal() as session:
        request = await session.get(InboundIntakeRequest, uuid.UUID(request_id))
        line = await session.get(InboundIntakeLine, uuid.UUID(line_id))
        assert request is not None
        assert line is not None
        with document_event_actor(actor_id):
            request.warehouse_id = uuid.UUID(second_warehouse.json()["id"])
            request.planned_delivery_date = date(2026, 9, 1)
            line.defective_qty = 1
            await session.commit()
            line.expected_qty = 6
            await session.commit()
            await session.delete(line)
            await session.commit()

    async with SessionLocal() as session:
        events = list(
            (
                await session.scalars(
                    select(DocumentEvent).where(DocumentEvent.document_id == uuid.UUID(request_id))
                )
            ).all()
        )
    by_type: dict[str, list[DocumentEvent]] = {}
    for event in events:
        by_type.setdefault(event.event_type, []).append(event)
    assert {
        "line_added",
        "line_removed",
        "line_qty_changed",
        "warehouse_changed",
        "planned_date_changed",
        "defect_qty_changed",
    }.issubset(by_type)
    assert by_type["line_removed"][-1].payload_json == {"qty_before": 6, "qty_after": 0}
    assert by_type["line_qty_changed"][-1].payload_json == {
        "qty_before": 5,
        "qty_after": 6,
    }
    assert by_type["warehouse_changed"][-1].payload_json["field"] == "warehouse_id"
    assert by_type["planned_date_changed"][-1].payload_json["field"] == ("planned_delivery_date")
    assert by_type["defect_qty_changed"][-1].payload_json == {
        "field": "defective_qty",
        "value_before": 0,
        "value_after": 1,
    }


# TC-NEW-DOCUMENT-JOURNAL-006 — a real return route keeps the same complete status journal.
@pytest.mark.asyncio
async def test_return_status_chain_and_defect_are_recorded_through_api(
    async_client: AsyncClient,
) -> None:
    headers, _ = await _register_admin(async_client)
    data = await _seed_document_data(async_client, headers)
    request_id, line_id = await _create_inbound_draft(
        async_client,
        headers,
        data,
        operation_type="return",
        marketplace="ozon",
    )
    base = "/operations/inbound-intake-requests"

    planned = await async_client.patch(
        f"{base}/{request_id}", headers=headers, json={"planned_box_count": 1}
    )
    assert planned.status_code == 200, planned.text
    submitted = await async_client.post(f"{base}/{request_id}/submit", headers=headers)
    assert submitted.status_code == 200, submitted.text
    receiving = await async_client.post(f"{base}/{request_id}/begin-receiving", headers=headers)
    assert receiving.status_code == 200, receiving.text
    actual = await async_client.patch(
        f"{base}/{request_id}/lines/{line_id}/actual",
        headers=headers,
        json={"actual_qty": 5},
    )
    assert actual.status_code == 200, actual.text
    defect = await async_client.patch(
        f"{base}/{request_id}/lines/{line_id}/defective",
        headers=headers,
        json={"defective_qty": 1},
    )
    assert defect.status_code == 200, defect.text
    sorting = await async_client.post(f"{base}/{request_id}/verify", headers=headers)
    assert sorting.status_code == 200, sorting.text
    done = await async_client.post(f"{base}/{request_id}/post", headers=headers)
    assert done.status_code == 200, done.text

    async with SessionLocal() as session:
        rows = list(
            (
                await session.scalars(
                    select(DocumentEvent)
                    .where(DocumentEvent.document_id == uuid.UUID(request_id))
                    .order_by(DocumentEvent.occurred_at)
                )
            ).all()
        )
    statuses = [row for row in rows if row.event_type == EVENT_STATUS_CHANGED]
    assert [(row.payload_json["from"], row.payload_json["to"]) for row in statuses] == [
        ("draft", "submitted"),
        ("submitted", "receiving"),
        ("receiving", "sorting"),
        ("sorting", "done"),
    ]
    assert [row.qty for row in statuses] == [0, 0, 5, 5]
    defects = [row for row in rows if row.event_type == "defect_qty_changed"]
    assert len(defects) == 1
    assert defects[0].payload_json["value_after"] == 1


# TC-NEW-DOCUMENT-JOURNAL-007 — Starlette background work drops the request actor.
@pytest.mark.asyncio
async def test_background_service_status_transition_is_system_authored(
    async_client: AsyncClient,
) -> None:
    headers, _ = await _register_admin(async_client)
    data = await _seed_document_data(async_client, headers)
    request_id, _ = await _create_inbound_draft(async_client, headers, data)
    base = "/operations/inbound-intake-requests"
    planned = await async_client.patch(
        f"{base}/{request_id}", headers=headers, json={"planned_box_count": 1}
    )
    assert planned.status_code == 200, planned.text

    background_app = FastAPI()
    background_app.add_middleware(DocumentEventActorMiddleware)

    @background_app.post("/run")
    async def run_in_background(background_tasks: BackgroundTasks) -> dict[str, bool]:
        async def submit_document() -> None:
            async with SessionLocal() as session:
                await inbound_svc.submit_request(
                    session,
                    uuid.UUID(data["tenant_id"]),
                    uuid.UUID(request_id),
                )

        background_tasks.add_task(submit_document)
        return {"scheduled": True}

    data["tenant_id"] = str(decode_access_token(headers["Authorization"].split()[1])["tenant_id"])
    transport = ASGITransport(app=background_app)
    async with AsyncClient(transport=transport, base_url="http://journal.test") as client:
        response = await client.post("/run", headers=headers)
    assert response.status_code == 200, response.text

    async with SessionLocal() as session:
        rows = list(
            (
                await session.scalars(
                    select(DocumentEvent).where(
                        DocumentEvent.document_id == uuid.UUID(request_id),
                        DocumentEvent.event_type == EVENT_STATUS_CHANGED,
                    )
                )
            ).all()
        )
    assert len(rows) == 1
    assert rows[0].payload_json == {"from": "draft", "to": "submitted"}
    assert rows[0].source == SOURCE_SYSTEM
    assert rows[0].actor_user_id is None


# TC-NEW-DOCUMENT-JOURNAL-008 — direct start and reopen edges use the real inbound API.
@pytest.mark.asyncio
async def test_inbound_direct_receiving_and_reopen_status_edges(
    async_client: AsyncClient,
) -> None:
    headers, _ = await _register_admin(async_client)
    data = await _seed_document_data(async_client, headers)
    base = "/operations/inbound-intake-requests"

    direct_id, _ = await _create_inbound_draft(async_client, headers, data)
    direct = await async_client.post(f"{base}/{direct_id}/begin-receiving", headers=headers)
    assert direct.status_code == 200, direct.text
    assert direct.json()["status"] == "receiving"

    reopen_id, line_id = await _create_inbound_draft(async_client, headers, data)
    planned = await async_client.patch(
        f"{base}/{reopen_id}", headers=headers, json={"planned_box_count": 1}
    )
    assert planned.status_code == 200, planned.text
    submitted = await async_client.post(f"{base}/{reopen_id}/submit", headers=headers)
    assert submitted.status_code == 200, submitted.text
    receiving = await async_client.post(f"{base}/{reopen_id}/begin-receiving", headers=headers)
    assert receiving.status_code == 200, receiving.text
    actual = await async_client.patch(
        f"{base}/{reopen_id}/lines/{line_id}/actual",
        headers=headers,
        json={"actual_qty": 5},
    )
    assert actual.status_code == 200, actual.text
    sorting = await async_client.post(f"{base}/{reopen_id}/verify", headers=headers)
    assert sorting.status_code == 200, sorting.text
    reopened = await async_client.post(f"{base}/{reopen_id}/reopen-receiving", headers=headers)
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "receiving"

    async with SessionLocal() as session:
        rows = list(
            (
                await session.scalars(
                    select(DocumentEvent).where(
                        DocumentEvent.document_id.in_([uuid.UUID(direct_id), uuid.UUID(reopen_id)]),
                        DocumentEvent.event_type == EVENT_STATUS_CHANGED,
                    )
                )
            ).all()
        )
    edges = [
        (str(row.document_id), row.payload_json["from"], row.payload_json["to"], row.qty)
        for row in rows
    ]
    assert (direct_id, "draft", "receiving", 0) in edges
    assert (reopen_id, "sorting", "receiving", 5) in edges


# TC-NEW-DOCUMENT-JOURNAL-009 — cancellation detaches drive all FBS reverse edges.
@pytest.mark.asyncio
async def test_fbs_detach_reverse_status_edges(async_client: AsyncClient) -> None:
    headers, token_payload = await _register_admin(async_client)
    data = await _seed_document_data(async_client, headers)
    tenant_id = uuid.UUID(str(token_payload["tenant_id"]))
    actor_id = uuid.UUID(str(token_payload["sub"]))
    seller_id = uuid.UUID(data["seller_id"])
    warehouse_id = uuid.UUID(data["warehouse_id"])
    product_id = uuid.UUID(data["product_id"])

    async with SessionLocal() as session:
        supplies: list[FbsSupply] = []
        cancel_orders: list[FbsOrder] = []
        for index, (status, order_count) in enumerate(
            (("packed", 2), ("assembling", 1), ("packed", 1)), start=1
        ):
            supply = FbsSupply(
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                wb_supply_id=f"journal-reverse-{index}",
                name=f"Journal reverse {index}",
                delivery_type="warehouse_sc",
                status=status,
            )
            session.add(supply)
            await session.flush()
            for order_index in range(order_count):
                order = FbsOrder(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    warehouse_id=warehouse_id,
                    product_id=product_id,
                    wb_order_id=988000000 + index * 10 + order_index,
                    supply_id=supply.id,
                    status=status,
                    created_at_wb=datetime.now(UTC),
                    deadline_at=datetime.now(UTC) + timedelta(days=1),
                    mapping_status="mapped",
                    reserve_status="reserved",
                )
                session.add(order)
                if order_index == 0:
                    cancel_orders.append(order)
            supplies.append(supply)
        await session.commit()

        with document_event_actor(actor_id):
            for order in cancel_orders:
                order.status = FBS_ORDER_STATUS_CANCELLED
                await fbs_packaging_svc.detach_cancelled_order_from_supply(
                    session, tenant_id, order, actor_user_id=actor_id
                )
                await session.commit()

        supply_ids = [supply.id for supply in supplies]

    async with SessionLocal() as session:
        rows = list(
            (
                await session.scalars(
                    select(DocumentEvent)
                    .where(
                        DocumentEvent.document_id.in_(supply_ids),
                        DocumentEvent.event_type == EVENT_STATUS_CHANGED,
                    )
                    .order_by(DocumentEvent.occurred_at)
                )
            ).all()
        )
    assert [(row.payload_json["from"], row.payload_json["to"], row.qty) for row in rows] == [
        ("packed", "assembling", 1),
        ("assembling", "draft", 0),
        ("packed", "draft", 0),
    ]
    assert all(row.actor_user_id == actor_id and row.source == SOURCE_USER for row in rows)


# TC-NEW-DOCUMENT-JOURNAL-010 — both cancellable unload execution states are journalled.
@pytest.mark.asyncio
async def test_unload_confirmed_and_collecting_cancel_status_edges(
    async_client: AsyncClient,
) -> None:
    headers, token_payload = await _register_admin(async_client)
    data = await _seed_document_data(async_client, headers)
    tenant_id = uuid.UUID(str(token_payload["tenant_id"]))
    actor_id = uuid.UUID(str(token_payload["sub"]))

    async with SessionLocal() as session:
        requests = [
            MarketplaceUnloadRequest(
                tenant_id=tenant_id,
                warehouse_id=uuid.UUID(data["warehouse_id"]),
                seller_id=uuid.UUID(data["seller_id"]),
                marketplace="ozon",
                status=status,
            )
            for status in ("confirmed", "collecting")
        ]
        session.add_all(requests)
        await session.commit()
        with document_event_actor(actor_id):
            for request in requests:
                await unload_svc.cancel_request(
                    session, tenant_id, request.id, performer_id=actor_id
                )
        request_ids = [request.id for request in requests]

    async with SessionLocal() as session:
        rows = list(
            (
                await session.scalars(
                    select(DocumentEvent)
                    .where(
                        DocumentEvent.document_id.in_(request_ids),
                        DocumentEvent.event_type == EVENT_STATUS_CHANGED,
                    )
                    .order_by(DocumentEvent.occurred_at)
                )
            ).all()
        )
    assert [(row.payload_json["from"], row.payload_json["to"]) for row in rows] == [
        ("confirmed", "cancelled"),
        ("collecting", "cancelled"),
    ]
    assert all(row.actor_user_id == actor_id and row.source == SOURCE_USER for row in rows)


# TC-NEW-DOCUMENT-JOURNAL-011 — execute the migration trigger on real PostgreSQL.
@pytest.mark.postgresql_concurrency
def test_postgresql_trigger_is_system_authored_and_failure_isolated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_url = os.environ.get("WMS_TEST_DATABASE_URL")
    if raw_url is None or raw_url.startswith("sqlite"):
        pytest.skip("PostgreSQL WMS_TEST_DATABASE_URL required for trigger execution")
    sync_url = make_url(raw_url).set(drivername="postgresql+psycopg")
    engine = create_engine(sync_url)
    schema = f"journal_trigger_{uuid.uuid4().hex}"
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260825_0107_document_event.py"
    )
    spec = importlib.util.spec_from_file_location("document_event_migration_test", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            connection.execute(text("CREATE TABLE tenants (id uuid PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE users (id uuid PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE products (id uuid PRIMARY KEY)"))
            connection.execute(
                text(
                    "CREATE TABLE fbs_supplies ("
                    "id uuid PRIMARY KEY, tenant_id uuid NOT NULL, status text NOT NULL)"
                )
            )
            connection.execute(
                text("CREATE TABLE fbs_orders (id uuid PRIMARY KEY, supply_id uuid)")
            )
            operations = Operations(MigrationContext.configure(connection))
            monkeypatch.setattr(migration, "op", operations)
            migration.upgrade()

            tenant_id = uuid.uuid4()
            supply_id = uuid.uuid4()
            connection.execute(text("INSERT INTO tenants (id) VALUES (:id)"), {"id": tenant_id})
            connection.execute(
                text(
                    "INSERT INTO fbs_supplies (id, tenant_id, status) "
                    "VALUES (:id, :tenant_id, 'draft')"
                ),
                {"id": supply_id, "tenant_id": tenant_id},
            )
            connection.execute(
                text(
                    "ALTER TABLE document_event ADD CONSTRAINT reject_system_event "
                    "CHECK (source <> 'system')"
                )
            )
            connection.execute(
                text("UPDATE fbs_supplies SET status = 'assembling' WHERE id = :id"),
                {"id": supply_id},
            )
            assert (
                connection.scalar(
                    text("SELECT status FROM fbs_supplies WHERE id = :id"), {"id": supply_id}
                )
                == "assembling"
            )
            assert connection.scalar(text("SELECT count(*) FROM document_event")) == 0

            connection.execute(
                text("ALTER TABLE document_event DROP CONSTRAINT reject_system_event")
            )
            connection.execute(
                text("UPDATE fbs_supplies SET status = 'packed' WHERE id = :id"),
                {"id": supply_id},
            )
            event_row = connection.execute(
                text(
                    "SELECT source, actor_user_id, payload_json->>'from', "
                    "payload_json->>'to', qty FROM document_event"
                )
            ).one()
            assert tuple(event_row) == ("system", None, "assembling", "packed", 0)
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
