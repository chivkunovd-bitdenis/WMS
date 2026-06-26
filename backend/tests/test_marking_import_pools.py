from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import func, select
from test_packaging_tasks import _register_admin

from app.db.session import SessionLocal
from app.models.marking_code import (
    EVENT_IMPORTED,
    STATUS_AVAILABLE,
    MarkingCode,
    MarkingCodeEvent,
    MarkingCodeImport,
    MarkingPool,
    MarkingPoolProduct,
)


def _pools_json(specs: list[dict[str, object]]) -> str:
    return json.dumps(specs)


async def _import_files(
    async_client: AsyncClient,
    headers: dict[str, str],
    *,
    seller_id: str,
    pools: list[dict[str, object]],
    files: list[tuple[str, bytes]],
) -> Response:
    multipart_files = [
        ("files", (name, content, "text/csv")) for name, content in files
    ]
    return await async_client.post(
        "/operations/marking-codes/import",
        headers=headers,
        data={"seller_id": seller_id, "pools_json": _pools_json(pools)},
        files=multipart_files,
    )


@pytest.mark.asyncio
async def test_import_single_gtin_creates_pool_and_links_products(
    async_client: AsyncClient,
) -> None:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Import Seller", "email": f"imp-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    product_ids: list[str] = []
    for i in range(3):
        pr = await async_client.post(
            "/products",
            headers=h,
            json={
                "name": f"Товар {i}",
                "sku_code": f"IMP-{uuid.uuid4().hex[:5]}-{i}",
                "length_mm": 10,
                "width_mm": 10,
                "height_mm": 10,
                "seller_id": seller_id,
            },
        )
        product_ids.append(pr.json()["id"])

    gtin = "00000000001234"
    codes = [f"01{gtin}21{'A' * 20}{i:04d}" for i in range(5)]
    csv_body = "cis\n" + "\n".join(codes)
    imp = await _import_files(
        async_client,
        h,
        seller_id=seller_id,
        pools=[{"title": "Куртки зима", "product_ids": product_ids}],
        files=[("codes.csv", csv_body.encode())],
    )
    assert imp.status_code == 200, imp.text
    body = imp.json()
    assert body["accepted_count"] == 5
    assert body["document_number"].startswith("ЗАГРКМ-")
    assert len(body["pools"]) == 1
    assert body["pools"][0]["accepted"] == 5
    pool_id = uuid.UUID(body["pools"][0]["pool_id"])

    async with SessionLocal() as session:
        pool = await session.get(MarkingPool, pool_id)
        assert pool is not None
        assert pool.title == "Куртки зима"
        links = (
            await session.execute(
                select(MarkingPoolProduct).where(MarkingPoolProduct.pool_id == pool_id)
            )
        ).scalars().all()
        assert len(links) == 3
        available = (
            await session.execute(
                select(func.count(MarkingCode.id)).where(
                    MarkingCode.pool_id == pool_id,
                    MarkingCode.status == STATUS_AVAILABLE,
                )
            )
        ).scalar_one()
        assert available == 5
        events = (
            await session.execute(
                select(func.count(MarkingCodeEvent.id)).where(
                    MarkingCodeEvent.event_type == EVENT_IMPORTED,
                    MarkingCodeEvent.document_number == body["document_number"],
                )
            )
        ).scalar_one()
        assert events == 5


@pytest.mark.asyncio
async def test_import_two_gtins_creates_two_pools(async_client: AsyncClient) -> None:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "2GTIN", "email": f"2g-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    gtin_a = "00000000000001"
    gtin_b = "00000000000002"
    codes = [
        f"01{gtin_a}21{'B' * 20}0001",
        f"01{gtin_b}21{'C' * 20}0002",
    ]
    csv_body = "cis\n" + "\n".join(codes)
    imp = await _import_files(
        async_client,
        h,
        seller_id=seller_id,
        pools=[
            {"gtin": gtin_a, "title": "Пул A", "product_ids": []},
            {"gtin": gtin_b, "title": "Пул B", "product_ids": []},
        ],
        files=[("codes.csv", csv_body.encode())],
    )
    assert imp.status_code == 200, imp.text
    assert imp.json()["accepted_count"] == 2
    assert len(imp.json()["pools"]) == 2


@pytest.mark.asyncio
async def test_import_duplicates_and_invalid(async_client: AsyncClient) -> None:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Dup", "email": f"dup-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    gtin = "00000000009999"
    cis = f"01{gtin}21{'D' * 20}0001"
    csv_first = f"cis\n{cis}\nshort"
    imp1 = await _import_files(
        async_client,
        h,
        seller_id=seller_id,
        pools=[{"title": "Dup pool", "product_ids": []}],
        files=[("codes.csv", csv_first.encode())],
    )
    assert imp1.status_code == 200, imp1.text
    assert imp1.json()["accepted_count"] == 1
    assert imp1.json()["skipped_count"] == 1

    imp2 = await _import_files(
        async_client,
        h,
        seller_id=seller_id,
        pools=[{"title": "Dup pool", "product_ids": []}],
        files=[("codes.csv", f"cis\n{cis}".encode())],
    )
    assert imp2.status_code == 200, imp2.text
    assert imp2.json()["accepted_count"] == 0
    assert imp2.json()["skipped_count"] == 1
    assert any(r["reason"] == "duplicate" for r in imp2.json()["skip_reasons"])


@pytest.mark.asyncio
async def test_import_assigns_document_number_on_batch(async_client: AsyncClient) -> None:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Doc", "email": f"doc-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    gtin = "00000000005555"
    cis = f"01{gtin}21{'E' * 20}0001"
    imp = await _import_files(
        async_client,
        h,
        seller_id=seller_id,
        pools=[{"title": "Doc pool", "product_ids": []}],
        files=[("codes.csv", f"cis\n{cis}".encode())],
    )
    assert imp.status_code == 200, imp.text
    import_id = uuid.UUID(imp.json()["import_id"])
    async with SessionLocal() as session:
        batch = await session.get(MarkingCodeImport, import_id)
        assert batch is not None
        assert batch.document_number == imp.json()["document_number"]


@pytest.mark.asyncio
async def test_import_preview_groups_by_gtin(async_client: AsyncClient) -> None:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Preview Seller", "email": f"prev-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    gtin = "00000000009999"
    cis = f"01{gtin}21{'P' * 20}0001"
    preview = await async_client.post(
        "/operations/marking-codes/import/preview",
        headers=h,
        data={"seller_id": seller_id},
        files=[("files", ("codes.csv", f"cis\n{cis}".encode(), "text/csv"))],
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["total_codes"] == 1
    assert len(body["groups"]) == 1
    assert body["groups"][0]["gtin"] == gtin
