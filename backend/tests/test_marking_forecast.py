from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from test_packaging_tasks import _register_admin

from app.db.session import SessionLocal
from app.models.marking_code import EVENT_PRINTED, MarkingCode, MarkingCodeEvent, MarkingPool
from app.models.notification import Notification
from app.services import marking_code_service as mc_svc
from app.services.marking_low_stock_service import run_marking_low_stock_for_tenant


async def _seed_pool(
    async_client: AsyncClient,
) -> tuple[dict[str, str], str, str]:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Fc Seller", "email": f"fc-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Fc товар",
            "sku_code": f"FC-{uuid.uuid4().hex[:6]}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    product_id = pr.json()["id"]
    gtin = "00000000008888"
    codes = [f"01{gtin}21{'G' * 20}{i:04d}" for i in range(40)]
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "Forecast pool", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("codes.csv", ("cis\n" + "\n".join(codes)).encode(), "text/csv"))],
    )
    assert imp.status_code == 200, imp.text
    pool_id = imp.json()["pools"][0]["pool_id"]
    return h, seller_id, pool_id


@pytest.mark.asyncio
async def test_compute_forecast_days_unit() -> None:
    assert mc_svc.compute_forecast_days(40, 210) == 1.3
    assert mc_svc.compute_forecast_days(40, 0) is None


@pytest.mark.asyncio
async def test_pool_list_includes_forecast_from_events(async_client: AsyncClient) -> None:
    h, seller_id, pool_id = await _seed_pool(async_client)

    async with SessionLocal() as session:
        codes = list(
            (
                await session.execute(
                    select(MarkingCode).where(MarkingCode.pool_id == uuid.UUID(pool_id))
                )
            ).scalars()
        )
        when = datetime.now(UTC) - timedelta(days=1)
        for code in codes[:30]:
            await mc_svc.record_event(
                session,
                code=code,
                event_type=EVENT_PRINTED,
                actor=None,
                copies=7,
            )
            event = (
                await session.execute(
                    select(MarkingCodeEvent)
                    .where(MarkingCodeEvent.code_id == code.id)
                    .order_by(MarkingCodeEvent.created_at.desc())
                    .limit(1)
                )
            ).scalar_one()
            event.created_at = when
        await session.commit()

    pools = await async_client.get(
        f"/operations/marking-codes/pools?seller_id={seller_id}",
        headers=h,
    )
    row = next(p for p in pools.json() if p["id"] == pool_id)
    assert row["consumption_7d"] == 210
    assert row["forecast_days"] == 1.3
    assert row["loaded"] == 40


@pytest.mark.asyncio
async def test_set_pool_threshold_api(async_client: AsyncClient) -> None:
    h, _seller_id, pool_id = await _seed_pool(async_client)
    patched = await async_client.put(
        f"/operations/marking-codes/pools/{pool_id}/threshold",
        headers=h,
        json={"low_stock_threshold": 50, "forecast_days_threshold": 2},
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["low_stock_threshold"] == 50
    assert body["forecast_days_threshold"] == 2


@pytest.mark.asyncio
async def test_low_stock_job_notifies_seller(async_client: AsyncClient) -> None:
    h, seller_id, pool_id = await _seed_pool(async_client)

    await async_client.put(
        f"/operations/marking-codes/pools/{pool_id}/threshold",
        headers=h,
        json={"low_stock_threshold": 100, "forecast_days_threshold": 2},
    )

    async with SessionLocal() as session:
        pool = await session.get(MarkingPool, uuid.UUID(pool_id))
        assert pool is not None
        sent = await run_marking_low_stock_for_tenant(session, pool.tenant_id)
        assert sent == 1

    notes = await async_client.get("/operations/notifications", headers=h)
    assert notes.status_code == 200
    assert notes.json()["unread_count"] == 0

    async with SessionLocal() as session:
        note = (
            await session.execute(
                select(Notification).where(Notification.type == "marking_low_stock")
            )
        ).scalar_one()
        assert note.recipient_id == seller_id
        assert note.severity == "critical"
