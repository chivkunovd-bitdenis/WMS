"""WMS-440 PostgreSQL proof of creation and scanner attempt serialization."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal, engine
from app.models.inbound_intake import InboundIntakeRequest
from app.services import inbound_intake_service as svc
from app.services.tokens import decode_access_token
from tests.test_wms440_ff_intake import _setup


@pytest.mark.asyncio
async def test_create_and_scans_concurrent_attempt_identity(async_client: AsyncClient) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row and unique-index locks required")
    headers, wid, sid, pid = await _setup(async_client)
    tenant = uuid.UUID(str(decode_access_token(headers["Authorization"].split()[1])["tenant_id"]))
    attempt = uuid.uuid4()

    async def create() -> uuid.UUID:
        async with SessionLocal() as db:
            result = await svc.create_request(
                db,
                tenant,
                warehouse_id=uuid.UUID(wid),
                seller_id=uuid.UUID(sid),
                client_request_id=attempt,
            )
            return result.id

    ids = await asyncio.wait_for(asyncio.gather(create(), create()), 20)
    assert ids[0] == ids[1]
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(InboundIntakeRequest)) == 1

    async def scan(mutation_id: uuid.UUID) -> uuid.UUID:
        async with SessionLocal() as db:
            line = await svc.add_line(
                db,
                tenant,
                ids[0],
                product_id=uuid.UUID(pid),
                expected_qty=1,
                increment=True,
                mutation_id=mutation_id,
            )
            return line.id

    scan_attempt = uuid.uuid4()
    lines = await asyncio.wait_for(asyncio.gather(scan(scan_attempt), scan(scan_attempt)), 20)
    assert lines[0] == lines[1]
    await asyncio.wait_for(asyncio.gather(scan(uuid.uuid4()), scan(uuid.uuid4())), 20)
    async with SessionLocal() as db:
        request = await svc.get_request(db, tenant, ids[0])
        assert request is not None
        assert len(request.lines) == 1
        assert request.lines[0].actual_qty == 3


@pytest.mark.asyncio
async def test_concurrent_tare_scans_consume_ff_loose_units_once(async_client: AsyncClient) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks required")
    from app.services import inbound_intake_box_service as boxes

    headers, wid, sid, pid = await _setup(async_client)
    tenant = uuid.UUID(str(decode_access_token(headers["Authorization"].split()[1])["tenant_id"]))
    product = uuid.UUID(pid)
    async with SessionLocal() as db:
        request = await svc.create_request(
            db, tenant, warehouse_id=uuid.UUID(wid), seller_id=uuid.UUID(sid)
        )
        rid = request.id
        await svc.add_line(db, tenant, rid, product_id=product, expected_qty=3)
        first = await boxes.create_open_box(db, tenant, rid)
        second = await boxes.create_open_box(db, tenant, rid)
        first_id, second_id = first.id, second.id

    async def scan(bid: uuid.UUID, attempt: uuid.UUID) -> None:
        async with SessionLocal() as db:
            await boxes.scan_product_into_box(
                db,
                tenant,
                rid,
                bid,
                barcode="synthetic",
                product_id_hint=product,
                mutation_id=attempt,
            )

    same_attempt = uuid.uuid4()
    await asyncio.wait_for(
        asyncio.gather(
            scan(first_id, same_attempt),
            scan(first_id, same_attempt),
            scan(second_id, uuid.uuid4()),
        ),
        20,
    )
    async with SessionLocal() as db:
        request = await svc.get_request(db, tenant, rid)
        assert request is not None
        assert request.lines[0].actual_qty == 1
        assert await svc.effective_actual_qty(db, rid, request.lines[0]) == 3
        assert sum(ln.quantity for box in request.boxes for ln in box.lines) == 2
