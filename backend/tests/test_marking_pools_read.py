from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from test_packaging_tasks import _register_admin

from app.db.session import SessionLocal
from app.models.marking_code import (
    STATUS_PRINTED,
    MarkingCode,
)


async def _seed_pool_with_codes(
    async_client: AsyncClient,
) -> tuple[dict[str, str], str, str, str, list[str]]:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Read Seller", "email": f"rd-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Read товар",
            "sku_code": f"RD-{uuid.uuid4().hex[:6]}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    product_id = pr.json()["id"]
    gtin = "00000000007777"
    codes = [f"01{gtin}21{'F' * 20}{i:04d}" for i in range(4)]
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "Read pool", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("codes.csv", ("cis\n" + "\n".join(codes)).encode(), "text/csv"))],
    )
    assert imp.status_code == 200, imp.text
    pool_id = imp.json()["pools"][0]["pool_id"]
    return h, seller_id, pool_id, product_id, codes


@pytest.mark.asyncio
async def test_list_pools_status_aggregates(async_client: AsyncClient) -> None:
    h, seller_id, pool_id, product_id, _ = await _seed_pool_with_codes(async_client)
    pools = await async_client.get(
        f"/operations/marking-codes/pools?seller_id={seller_id}",
        headers=h,
    )
    assert pools.status_code == 200, pools.text
    row = next(p for p in pools.json() if p["id"] == pool_id)
    assert row["available"] == 4
    assert row["printed"] == 0
    assert len(row["products"]) == 1
    assert row["products"][0]["id"] == product_id
    assert row["forecast_days"] is None

    async with SessionLocal() as session:
        code = (
            await session.execute(
                select(MarkingCode).where(MarkingCode.pool_id == uuid.UUID(pool_id)).limit(1)
            )
        ).scalar_one()
        code.status = STATUS_PRINTED
        await session.commit()

    pools2 = await async_client.get(
        f"/operations/marking-codes/pools?seller_id={seller_id}",
        headers=h,
    )
    row2 = next(p for p in pools2.json() if p["id"] == pool_id)
    assert row2["available"] == 3
    assert row2["printed"] == 1


@pytest.mark.asyncio
async def test_pool_detail_and_codes(async_client: AsyncClient) -> None:
    h, _seller_id, pool_id, _, _codes = await _seed_pool_with_codes(async_client)
    detail = await async_client.get(
        f"/operations/marking-codes/pools/{pool_id}",
        headers=h,
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["title"] == "Read pool"
    assert len(body["import_batches"]) == 1
    assert body["import_batches"][0]["document_number"].startswith("ЗАГРКМ-")

    listed = await async_client.get(
        f"/operations/marking-codes/pools/{pool_id}/codes?status=available",
        headers=h,
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 4
    assert all(r["cis_masked"].startswith("…") for r in listed.json())


@pytest.mark.asyncio
async def test_pool_codes_foreign_pool_returns_404(async_client: AsyncClient) -> None:
    h, _seller_id, pool_id, _, _ = await _seed_pool_with_codes(async_client)
    other = await _register_admin(async_client)
    resp = await async_client.get(
        f"/operations/marking-codes/pools/{pool_id}/codes",
        headers=other,
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "pool_not_found"


@pytest.mark.asyncio
async def test_ledger_filters(async_client: AsyncClient) -> None:
    h, seller_id, pool_id, _, _ = await _seed_pool_with_codes(async_client)
    detail = await async_client.get(
        f"/operations/marking-codes/pools/{pool_id}",
        headers=h,
    )
    doc = detail.json()["import_batches"][0]["document_number"]

    ledger = await async_client.get(
        "/operations/marking-codes/ledger",
        headers=h,
        params={"seller_id": seller_id, "event_type": "imported"},
    )
    assert ledger.status_code == 200
    assert ledger.json()["total"] >= 4
    assert all(r["event_type"] == "imported" for r in ledger.json()["rows"])

    by_doc = await async_client.get(
        "/operations/marking-codes/ledger",
        headers=h,
        params={"document": doc},
    )
    assert by_doc.status_code == 200
    assert by_doc.json()["total"] == 4


@pytest.mark.asyncio
async def test_ledger_date_range_filter(async_client: AsyncClient) -> None:
    h, seller_id, _, _, _ = await _seed_pool_with_codes(async_client)
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    future = (now + timedelta(days=365)).date().isoformat()

    today_ledger = await async_client.get(
        "/operations/marking-codes/ledger",
        headers=h,
        params={
            "seller_id": seller_id,
            "date_from": f"{today}T00:00:00",
            "date_to": f"{today}T23:59:59",
        },
    )
    assert today_ledger.status_code == 200
    assert today_ledger.json()["total"] >= 4

    future_ledger = await async_client.get(
        "/operations/marking-codes/ledger",
        headers=h,
        params={
            "seller_id": seller_id,
            "date_from": f"{future}T00:00:00",
            "date_to": f"{future}T23:59:59",
        },
    )
    assert future_ledger.status_code == 200
    assert future_ledger.json()["total"] == 0


@pytest.mark.asyncio
async def test_ledger_cis_mask_filter(async_client: AsyncClient) -> None:
    h, seller_id, pool_id, _, _ = await _seed_pool_with_codes(async_client)
    codes = await async_client.get(
        f"/operations/marking-codes/pools/{pool_id}/codes",
        headers=h,
    )
    assert codes.status_code == 200
    masked = codes.json()[0]["cis_masked"]
    tail = masked.lstrip("…")[:4]

    by_mask = await async_client.get(
        "/operations/marking-codes/ledger",
        headers=h,
        params={"seller_id": seller_id, "cis_mask": tail},
    )
    assert by_mask.status_code == 200
    body = by_mask.json()
    assert body["total"] >= 1
    assert all(tail in row["cis_masked"] for row in body["rows"])

    full = await async_client.get(
        "/operations/marking-codes/ledger",
        headers=h,
        params={"seller_id": seller_id},
    )
    assert full.status_code == 200
    assert full.json()["total"] >= body["total"]


@pytest.mark.asyncio
async def test_ledger_export_csv(async_client: AsyncClient) -> None:
    h, seller_id, _, _, _ = await _seed_pool_with_codes(async_client)
    params = {"seller_id": seller_id, "event_type": "imported"}

    ledger = await async_client.get(
        "/operations/marking-codes/ledger",
        headers=h,
        params=params,
    )
    assert ledger.status_code == 200
    expected_total = ledger.json()["total"]
    assert expected_total >= 4

    export = await async_client.get(
        "/operations/marking-codes/ledger/export",
        headers=h,
        params=params,
    )
    assert export.status_code == 200
    assert "text/csv" in export.headers["content-type"]
    assert "attachment" in export.headers["content-disposition"]
    text = export.content.decode("utf-8-sig")
    lines = [line for line in text.strip().splitlines() if line]
    assert lines[0].startswith("created_at,event_type,cis_masked")
    assert len(lines) - 1 == expected_total
    assert all("imported" in line for line in lines[1:])


@pytest.mark.asyncio
async def test_code_history_timeline(async_client: AsyncClient) -> None:
    h, _seller_id, pool_id, _, _ = await _seed_pool_with_codes(async_client)
    codes = await async_client.get(
        f"/operations/marking-codes/pools/{pool_id}/codes",
        headers=h,
    )
    code_id = codes.json()[0]["id"]
    history = await async_client.get(
        f"/operations/marking-codes/codes/{code_id}/history",
        headers=h,
    )
    assert history.status_code == 200
    assert len(history.json()) >= 1
    assert history.json()[0]["event_type"] == "imported"
