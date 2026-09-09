"""WMS-056: appending audit rows on receiving-tare composition edits.

Removing a product from a receiving box or cargo place physically deletes the
row (`quantity=0` -> `session.delete(line)`). The row itself has no
`removed_at/removed_by`, so without an append-only audit fact history is lost.
These tests pin the existing document_event journal picking up the fact — with
actor, timestamp, container reference, product, qty_before and qty_after.
"""

from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient
from inbound_box_intake_helpers import set_planned_boxes
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.document_event import (
    DOCUMENT_TYPE_INBOUND_INTAKE,
    EVENT_TARE_LINE_QTY_CHANGED,
    SOURCE_USER,
    DocumentEvent,
)
from app.services import inbound_intake_service as intake_svc
from app.services.tokens import decode_access_token


async def _register_admin(
    async_client: AsyncClient, suffix: str
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID]:
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"TareAudit {suffix}",
            "slug": f"tare-audit-{suffix}",
            "admin_email": f"tare-audit-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = str(reg.json()["access_token"])
    payload = decode_access_token(token)
    return (
        {"Authorization": f"Bearer {token}"},
        uuid.UUID(str(payload["tenant_id"])),
        uuid.UUID(str(payload["sub"])),
    )


async def _submitted_request(
    async_client: AsyncClient,
    ah: dict[str, str],
    suffix: str,
    *,
    expected_qty: int = 5,
) -> tuple[uuid.UUID, uuid.UUID, str]:
    wh = await async_client.post(
        "/warehouses", headers=ah, json={"name": "W", "code": f"w-{suffix}"}
    )
    assert wh.status_code == 200, wh.text
    wid = wh.json()["id"]
    seller = await async_client.post(
        "/sellers", headers=ah, json={"name": f"Seller {suffix}"}
    )
    assert seller.status_code in (200, 201), seller.text
    seller_id = seller.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"sku-{suffix}",
            "seller_id": seller_id,
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
        },
    )
    assert pr.status_code == 200, pr.text
    pid = uuid.UUID(pr.json()["id"])
    sku = pr.json()["sku_code"]
    cr = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=ah,
        json={"warehouse_id": wid, "seller_id": seller_id},
    )
    assert cr.status_code == 201, cr.text
    rid = uuid.UUID(cr.json()["id"])
    ln = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/lines",
        headers=ah,
        json={"product_id": str(pid), "expected_qty": expected_qty},
    )
    assert ln.status_code == 201, ln.text
    await set_planned_boxes(
        async_client, "/operations/inbound-intake-requests", str(rid), ah
    )
    sub = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/submit", headers=ah
    )
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] == intake_svc.STATUS_SUBMITTED
    return rid, pid, sku


async def _fetch_tare_events(
    tenant_id: uuid.UUID, request_id: uuid.UUID
) -> list[DocumentEvent]:
    async with SessionLocal() as session:
        rows = await session.scalars(
            select(DocumentEvent)
            .where(
                DocumentEvent.tenant_id == tenant_id,
                DocumentEvent.document_type == DOCUMENT_TYPE_INBOUND_INTAKE,
                DocumentEvent.document_id == request_id,
                DocumentEvent.event_type == EVENT_TARE_LINE_QTY_CHANGED,
            )
            .order_by(DocumentEvent.occurred_at.asc(), DocumentEvent.created_at.asc())
        )
        return list(rows.all())


@pytest.mark.asyncio
async def test_box_line_removal_writes_audit_row_with_actor_and_qty_before_after(
    async_client: AsyncClient,
) -> None:
    """PUT box line quantity to 0 physically deletes the row — audit fact must survive.

    Records who removed, when, from which container, which product, qty_before, qty_after.
    """
    suffix = str(int(time.time() * 1000))
    ah, tenant_id, actor_user_id = await _register_admin(async_client, suffix)
    rid, pid, _sku = await _submitted_request(async_client, ah, suffix, expected_qty=3)

    box = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/boxes", headers=ah
    )
    assert box.status_code == 201, box.text
    box_id = box.json()["id"]

    put_two = await async_client.put(
        f"/operations/inbound-intake-requests/{rid}/boxes/{box_id}/lines/{pid}",
        headers=ah,
        json={"quantity": 2},
    )
    assert put_two.status_code == 200, put_two.text

    put_zero = await async_client.put(
        f"/operations/inbound-intake-requests/{rid}/boxes/{box_id}/lines/{pid}",
        headers=ah,
        json={"quantity": 0},
    )
    assert put_zero.status_code == 200, put_zero.text

    events = await _fetch_tare_events(tenant_id, rid)
    # 0 -> 2 then 2 -> 0
    assert len(events) == 2, [
        (e.event_type, e.payload_json) for e in events
    ]

    grow, remove = events
    assert grow.actor_user_id == actor_user_id
    assert grow.source == SOURCE_USER
    assert grow.product_id == pid
    assert grow.qty == 2
    assert grow.payload_json["container_kind"] == "box"
    assert grow.payload_json["container_id"] == box_id
    assert grow.payload_json["qty_before"] == 0
    assert grow.payload_json["qty_after"] == 2
    assert grow.occurred_at is not None

    assert remove.actor_user_id == actor_user_id
    assert remove.source == SOURCE_USER
    assert remove.product_id == pid
    assert remove.qty == 0
    assert remove.payload_json["container_kind"] == "box"
    assert remove.payload_json["container_id"] == box_id
    assert remove.payload_json["qty_before"] == 2
    assert remove.payload_json["qty_after"] == 0
    assert remove.occurred_at is not None


@pytest.mark.asyncio
async def test_cargo_place_line_removal_writes_audit_row(
    async_client: AsyncClient,
) -> None:
    """Cargo place has the same physical-delete-on-zero path (WMS-056 evidence)."""
    suffix = str(int(time.time() * 1000) + 1)
    ah, tenant_id, actor_user_id = await _register_admin(async_client, suffix)
    rid, pid, _sku = await _submitted_request(async_client, ah, suffix, expected_qty=3)

    place_resp = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/cargo-places",
        headers=ah,
        json={"quantity": 1},
    )
    assert place_resp.status_code == 201, place_resp.text
    places = place_resp.json()
    assert isinstance(places, list) and places, places
    place_id = places[0]["id"]

    put_two = await async_client.put(
        f"/operations/inbound-intake-requests/{rid}/cargo-places/{place_id}/lines/{pid}",
        headers=ah,
        json={"quantity": 2},
    )
    assert put_two.status_code == 200, put_two.text

    put_zero = await async_client.put(
        f"/operations/inbound-intake-requests/{rid}/cargo-places/{place_id}/lines/{pid}",
        headers=ah,
        json={"quantity": 0},
    )
    assert put_zero.status_code == 200, put_zero.text

    events = await _fetch_tare_events(tenant_id, rid)
    assert len(events) == 2, [
        (e.event_type, e.payload_json) for e in events
    ]
    grow, remove = events
    assert grow.payload_json["container_kind"] == "cargo_place"
    assert grow.payload_json["container_id"] == place_id
    assert grow.payload_json["qty_after"] == 2
    assert grow.actor_user_id == actor_user_id
    assert grow.source == SOURCE_USER

    assert remove.payload_json["container_kind"] == "cargo_place"
    assert remove.payload_json["qty_before"] == 2
    assert remove.payload_json["qty_after"] == 0
    assert remove.actor_user_id == actor_user_id
