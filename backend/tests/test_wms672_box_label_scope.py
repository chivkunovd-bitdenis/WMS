"""C9: real API/services on pytest's private SQLite, never shared PostgreSQL.

Fixtures seed already existing boxes directly: this is not WMS-659 box creation.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal, engine
from app.models import Base
from app.models.inbound_intake import InboundIntakeBox, InboundIntakeRequest
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_reservation import InventoryReservation
from app.models.outbound_shipment import OutboundShipmentLine, OutboundShipmentRequest
from app.models.storage_location import StorageLocation
from app.services import inbound_intake_box_service as boxes
from app.services.tokens import decode_access_token

BASE = "/operations/inbound-intake-requests"


async def seed(client: AsyncClient, count: int) -> tuple[dict[str, str], uuid.UUID, uuid.UUID, list[uuid.UUID]]:
    suffix = uuid.uuid4().hex
    reg = await client.post("/auth/register", json={
        "organization_name": f"672-{suffix}", "slug": f"672-{suffix}",
        "admin_email": f"672-{suffix}@example.com", "password": "synthetic-password-672",
    })
    assert reg.status_code == 200, reg.text
    token = reg.json()["access_token"]
    tenant = uuid.UUID(decode_access_token(token)["tenant_id"])
    headers = {"Authorization": f"Bearer {token}"}
    wh = await client.post("/warehouses", headers=headers, json={"name": "672 warehouse", "code": suffix})
    assert wh.status_code == 200, wh.text
    wid = uuid.UUID(wh.json()["id"])
    seller = await client.post("/sellers", headers=headers, json={"name": "672 seller"})
    assert seller.status_code in (200, 201), seller.text
    sid = uuid.UUID(seller.json()["id"])
    product = await client.post("/products", headers=headers, json={
        "name": "672 stock sentinel", "sku_code": suffix, "seller_id": str(sid),
        "length_mm": 100, "width_mm": 100, "height_mm": 100,
    })
    assert product.status_code == 200, product.text
    pid = uuid.UUID(product.json()["id"])
    req = await client.post(BASE, headers=headers, json={"warehouse_id": str(wid), "seller_id": str(sid)})
    assert req.status_code == 201, req.text
    rid = uuid.UUID(req.json()["id"])
    ids = [uuid.uuid4() for _ in range(count)]
    async with SessionLocal() as session:
        document = await session.get(InboundIntakeRequest, rid)
        assert document is not None
        document.status = "receiving"
        location = StorageLocation(tenant_id=tenant, warehouse_id=wid, code="672-cell", barcode=f"LOC-{suffix}")
        session.add(location)
        await session.flush()
        session.add(InventoryBalance(tenant_id=tenant, storage_location_id=location.id, product_id=pid, quantity=19))
        outbound = OutboundShipmentRequest(tenant_id=tenant, warehouse_id=wid, seller_id=sid, status="draft")
        session.add(outbound)
        await session.flush()
        line = OutboundShipmentLine(request_id=outbound.id, product_id=pid, quantity=3, storage_location_id=location.id)
        session.add(line)
        await session.flush()
        session.add(InventoryReservation(tenant_id=tenant, outbound_shipment_line_id=line.id,
                                       product_id=pid, warehouse_id=wid, storage_location_id=location.id, quantity=3))
        # Reverse insertion order proves that the real service sorts, not the fixture.
        for i in reversed(range(count)):
            session.add(InboundIntakeBox(id=ids[i], tenant_id=tenant, request_id=rid,
                                        box_number=i + 1, internal_barcode=f"INB-{i + 1:012X}",
                                        storage_location_id=location.id))
        await session.commit()
    return headers, tenant, rid, ids


async def snapshot() -> dict[str, list[str]]:
    """Reread the DB, including real nonempty stock/reservation/location sentinels."""
    async with SessionLocal() as session:
        return {table.name: sorted(repr(tuple(row)) for row in (await session.execute(select(table))).all())
                for table in Base.metadata.sorted_tables}


@pytest.mark.asyncio
async def test_c9_foreign_document_and_injected_box_rejected_without_any_mutation(async_client: AsyncClient) -> None:
    assert engine.url.get_backend_name() == "sqlite", "672 contract uses a private SQLite DB only"
    ah, at, ar, aids = await seed(async_client, 300)
    bh, bt, br, bids = await seed(async_client, 1)
    before = await snapshot()
    denied = await async_client.get(f"{BASE}/{ar}", headers=bh)
    assert denied.status_code == 404
    assert "INB-" not in denied.text
    for headers, rid, bid in [(bh, ar, aids[0]), (ah, ar, bids[0]), (ah, br, aids[-1])]:
        response = await async_client.post(f"{BASE}/{rid}/boxes/{bid}/mark-label-printed", headers=headers)
        assert response.status_code == 404, response.text
    async with SessionLocal() as session:
        assert await boxes.list_boxes_with_lines(session, bt, ar) == []
        ordered = await boxes.list_boxes_with_lines(session, at, ar)
        assert [box.id for box in ordered] == aids
        assert [box.box_number for box in ordered] == list(range(1, 301))
        assert all(box.label_printed_at is None for box in ordered)
    assert await snapshot() == before


@pytest.mark.asyncio
async def test_c9_valid_technical_mark_preserves_business_data_and_box_identity(async_client: AsyncClient) -> None:
    assert engine.url.get_backend_name() == "sqlite"
    headers, _tenant, rid, ids = await seed(async_client, 1)
    before = await snapshot()
    response = await async_client.post(f"{BASE}/{rid}/boxes/{ids[0]}/mark-label-printed", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["id"] == str(ids[0])
    assert response.json()["internal_barcode"] == "INB-000000000001"
    assert response.json()["label_printed_at"] is not None  # technical only, no paper proof
    after = await snapshot()
    changed = {name for name in before if before[name] != after[name]}
    # Existing technical mark/audit may change; inventory, products, requests and reservations may not.
    assert changed <= {"inbound_intake_boxes", "document_event"}, changed
