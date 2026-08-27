from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from test_packaging_tasks import _register_admin

from app.db.session import SessionLocal
from app.models.marking_code import (
    EVENT_APPLIED,
    STATUS_APPLIED,
    STATUS_PRINTED,
    MarkingCode,
    MarkingCodeEvent,
)
from app.services.tokens import decode_access_token


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
    _h, _seller_id, pool_id, _, _ = await _seed_pool_with_codes(async_client)
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
    assert ledger.json()["total"] == 1
    rows = ledger.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["event_type"] == "imported"
    assert rows[0]["aggregated_count"] == 4

    by_doc = await async_client.get(
        "/operations/marking-codes/ledger",
        headers=h,
        params={"document": doc},
    )
    assert by_doc.status_code == 200
    assert by_doc.json()["total"] == 1
    assert by_doc.json()["rows"][0]["aggregated_count"] == 4


@pytest.mark.asyncio
async def test_ledger_excludes_external_fbs_registry_events(async_client: AsyncClient) -> None:
    # TC-NEW-FBS-KIZ-012: external FBS KIZ events are not pool consumption events.
    headers, seller_id, _pool_id, product_id, _ = await _seed_pool_with_codes(async_client)
    token = headers["Authorization"].removeprefix("Bearer ")
    tenant_id = uuid.UUID(str(decode_access_token(token)["tenant_id"]))

    async with SessionLocal() as session:
        code = MarkingCode(
            tenant_id=tenant_id,
            seller_id=uuid.UUID(seller_id),
            product_id=uuid.UUID(product_id),
            cis_code=f"010000000000777721{'E' * 20}0001",
            source="external_fbs",
            status=STATUS_APPLIED,
        )
        session.add(code)
        await session.flush()
        session.add(
            MarkingCodeEvent(
                tenant_id=tenant_id,
                seller_id=uuid.UUID(seller_id),
                code_id=code.id,
                event_type=EVENT_APPLIED,
            )
        )
        await session.commit()

    ledger = await async_client.get(
        "/operations/marking-codes/ledger",
        headers=headers,
        params={"seller_id": seller_id, "event_type": EVENT_APPLIED},
    )
    assert ledger.status_code == 200, ledger.text
    assert ledger.json() == {"rows": [], "total": 0}

    export = await async_client.get(
        "/operations/marking-codes/ledger/export",
        headers=headers,
        params={"seller_id": seller_id, "event_type": EVENT_APPLIED},
    )
    assert export.status_code == 200, export.text
    assert len(export.content.decode("utf-8-sig").strip().splitlines()) == 1


@pytest.mark.asyncio
async def test_ledger_date_range_filter(async_client: AsyncClient) -> None:
    h, seller_id, _, _, _ = await _seed_pool_with_codes(async_client)
    now = datetime.now(UTC)
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
    assert today_ledger.json()["total"] >= 1

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
    for row in body["rows"]:
        if row.get("aggregated_count"):
            assert row["cis_masked"] is None
        else:
            assert row["cis_masked"] is not None
            assert tail in row["cis_masked"]

    full = await async_client.get(
        "/operations/marking-codes/ledger",
        headers=h,
        params={"seller_id": seller_id},
    )
    assert full.status_code == 200
    assert full.json()["total"] >= body["total"]


@pytest.mark.asyncio
async def test_ledger_export_csv(async_client: AsyncClient) -> None:
    h, seller_id, _, _, codes = await _seed_pool_with_codes(async_client)
    params = {"seller_id": seller_id, "event_type": "imported"}

    ledger = await async_client.get(
        "/operations/marking-codes/ledger",
        headers=h,
        params=params,
    )
    assert ledger.status_code == 200
    expected_total = ledger.json()["total"]
    assert expected_total == 1

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
    rows = list(csv.DictReader(io.StringIO(text)))
    assert lines[0].split(",") == [
        "created_at",
        "event_type",
        "cis_code",
        "cis_masked",
        "pool_title",
        "gtin",
        "product_name",
        "product_sku",
        "seller_name",
        "document_number",
        "actor_email",
        "source_process",
    ]
    # CSV export keeps one row per raw event (not collapsed).
    assert len(rows) == 4
    assert {row["cis_code"] for row in rows} == set(codes)
    assert all(row["event_type"] == "imported" for row in rows)
    assert all(row["actor_email"] for row in rows)
    assert all(row["pool_title"] == "Read pool" for row in rows)


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
