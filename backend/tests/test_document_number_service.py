from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.services.document_number_service import (
    DOC_TYPE_INBOUND,
    DOC_TYPE_PACKAGING,
    DOC_TYPE_UNLOAD,
    document_date_msk,
    format_document_number,
    next_document_number,
    peek_next_counter,
)
from app.services.tokens import decode_access_token

MSK = ZoneInfo("Europe/Moscow")


async def _tenant_id(async_client: AsyncClient) -> uuid.UUID:
    email = f"docnum-{uuid.uuid4().hex[:8]}@example.com"
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "DocNum FF",
            "slug": f"docnum-{uuid.uuid4().hex[:8]}",
            "admin_email": email,
            "password": "password123",
        },
    )
    assert reg.status_code in (200, 201), reg.text
    token = reg.json()["access_token"]
    return uuid.UUID(str(decode_access_token(token)["tenant_id"]))


@pytest.mark.asyncio
async def test_next_document_number_sequential_same_day(async_client: AsyncClient) -> None:
    tenant_id = await _tenant_id(async_client)
    async with SessionLocal() as session:
        n1 = await next_document_number(session, tenant_id, DOC_TYPE_PACKAGING)
        await session.commit()
    async with SessionLocal() as session:
        n2 = await next_document_number(session, tenant_id, DOC_TYPE_PACKAGING)
        await session.commit()

    assert n1.startswith("УПАК-")
    assert n1.endswith("-1")
    assert n2.endswith("-2")
    assert n1.rsplit("-", 1)[0] == n2.rsplit("-", 1)[0]


@pytest.mark.asyncio
async def test_next_document_number_independent_doc_types(async_client: AsyncClient) -> None:
    tenant_id = await _tenant_id(async_client)
    async with SessionLocal() as session:
        pkg = await next_document_number(session, tenant_id, DOC_TYPE_PACKAGING)
        inbound = await next_document_number(session, tenant_id, DOC_TYPE_INBOUND)
        unload = await next_document_number(session, tenant_id, DOC_TYPE_UNLOAD)
        await session.commit()

    assert pkg.startswith("УПАК-") and pkg.endswith("-1")
    assert inbound.startswith("ПРИЕМ-") and inbound.endswith("-1")
    assert unload.startswith("ОТГР-") and unload.endswith("-1")


@pytest.mark.asyncio
async def test_next_document_number_resets_next_day(async_client: AsyncClient) -> None:
    tenant_id = await _tenant_id(async_client)
    today = datetime(2026, 6, 26, 12, 0, tzinfo=MSK)
    tomorrow = datetime(2026, 6, 27, 9, 0, tzinfo=MSK)

    async with SessionLocal() as session:
        n_today = await next_document_number(
            session, tenant_id, DOC_TYPE_PACKAGING, as_of=today
        )
        await session.commit()
    async with SessionLocal() as session:
        n_tomorrow = await next_document_number(
            session, tenant_id, DOC_TYPE_PACKAGING, as_of=tomorrow
        )
        await session.commit()

    assert n_today.endswith("-1")
    assert n_tomorrow.endswith("-1")
    assert document_date_msk(today) != document_date_msk(tomorrow)


@pytest.mark.asyncio
async def test_next_document_number_concurrent_no_duplicates(async_client: AsyncClient) -> None:
    tenant_id = await _tenant_id(async_client)

    async def one() -> str:
        async with SessionLocal() as session:
            number = await next_document_number(session, tenant_id, DOC_TYPE_PACKAGING)
            await session.commit()
            return number

    numbers = await asyncio.gather(*[one() for _ in range(12)])
    counters = [int(n.rsplit("-", 1)[-1]) for n in numbers]
    assert len(set(counters)) == len(counters)
    assert sorted(counters) == list(range(1, len(counters) + 1))


def test_format_document_number_padding() -> None:
    seq_date = document_date_msk(datetime(2026, 6, 5, 10, 0, tzinfo=MSK))
    assert format_document_number(DOC_TYPE_PACKAGING, seq_date, 3) == "УПАК-26-06-05-3"


@pytest.mark.asyncio
async def test_peek_next_counter_empty(async_client: AsyncClient) -> None:
    tenant_id = await _tenant_id(async_client)
    async with SessionLocal() as session:
        assert await peek_next_counter(session, tenant_id, DOC_TYPE_PACKAGING) == 0


@pytest.mark.asyncio
async def test_inbound_and_unload_api_assign_document_number(async_client: AsyncClient) -> None:
    email = f"docnum-api-{uuid.uuid4().hex[:8]}@example.com"
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "DocNum API",
            "slug": f"docnum-api-{uuid.uuid4().hex[:8]}",
            "admin_email": email,
            "password": "password123",
        },
    )
    assert reg.status_code in (200, 201), reg.text
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    wh = await async_client.post("/warehouses", headers=h, json={"name": "W", "code": "w-dn"})
    assert wh.status_code == 200, wh.text
    wh_id = wh.json()["id"]

    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Seller DN"},
    )
    assert seller.status_code in (200, 201), seller.text
    seller_id = seller.json()["id"]

    inbound = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=h,
        json={"warehouse_id": wh_id, "seller_id": seller_id},
    )
    assert inbound.status_code == 201, inbound.text
    inbound_body = inbound.json()
    assert inbound_body["document_number"].startswith("ПРИЕМ-")
    assert inbound_body["document_number"].endswith("-1")

    unload = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=h,
        json={"warehouse_id": wh_id, "seller_id": seller_id},
    )
    assert unload.status_code == 201, unload.text
    unload_body = unload.json()
    assert unload_body["document_number"].startswith("ОТГР-")
    assert unload_body["document_number"].endswith("-1")
