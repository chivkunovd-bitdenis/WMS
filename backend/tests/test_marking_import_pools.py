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
    MarkingCodeImportFile,
    MarkingPool,
    MarkingPoolProduct,
)
from app.services import marking_code_service as marking_service


def _pools_json(specs: list[dict[str, object]]) -> str:
    return json.dumps(specs)


async def _create_product(
    async_client: AsyncClient,
    headers: dict[str, str],
    seller_id: str,
    *,
    name: str,
) -> str:
    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": name,
            "sku_code": f"IMP-{uuid.uuid4().hex[:10]}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    assert product.status_code == 200, product.text
    return str(product.json()["id"])


async def _seller_marking_write_counts(seller_id: str) -> dict[str, int]:
    seller_uuid = uuid.UUID(seller_id)
    async with SessionLocal() as session:
        queries = {
            "imports": select(func.count(MarkingCodeImport.id)).where(
                MarkingCodeImport.seller_id == seller_uuid
            ),
            "source_files": select(func.count(MarkingCodeImportFile.id))
            .join(
                MarkingCodeImport,
                MarkingCodeImport.id == MarkingCodeImportFile.import_batch_id,
            )
            .where(MarkingCodeImport.seller_id == seller_uuid),
            "pools": select(func.count(MarkingPool.id)).where(MarkingPool.seller_id == seller_uuid),
            "pool_products": select(func.count(MarkingPoolProduct.id))
            .join(MarkingPool, MarkingPool.id == MarkingPoolProduct.pool_id)
            .where(MarkingPool.seller_id == seller_uuid),
            "codes": select(func.count(MarkingCode.id)).where(MarkingCode.seller_id == seller_uuid),
            "events": select(func.count(MarkingCodeEvent.id)).where(
                MarkingCodeEvent.seller_id == seller_uuid
            ),
        }
        return {
            name: int((await session.execute(query)).scalar_one())
            for name, query in queries.items()
        }


async def _import_files(
    async_client: AsyncClient,
    headers: dict[str, str],
    *,
    seller_id: str,
    pools: list[dict[str, object]],
    files: list[tuple[str, bytes]],
) -> Response:
    multipart_files = [("files", (name, content, "text/csv")) for name, content in files]
    return await async_client.post(
        "/operations/marking-codes/import",
        headers=headers,
        data={"seller_id": seller_id, "pools_json": _pools_json(pools)},
        files=multipart_files,
    )


@pytest.mark.asyncio
async def test_import_rejects_all_empty_product_assignments_before_writes(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": "Empty assignments", "email": f"empty-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = str(seller.json()["id"])
    gtin_a = "00000000000101"
    gtin_b = "00000000000102"
    codes = [f"01{gtin_a}21{'E' * 20}0001", f"01{gtin_b}21{'F' * 20}0002"]
    persistence_calls: list[object] = []

    monkeypatch.setattr(
        marking_service,
        "_persist_import_source_pdfs",
        lambda *args, **kwargs: persistence_calls.append((args, kwargs)),
    )
    response = await _import_files(
        async_client,
        headers,
        seller_id=seller_id,
        pools=[
            {"gtin": gtin_a, "title": "Empty A", "product_ids": []},
            {"gtin": gtin_b, "title": "Empty B", "product_ids": []},
        ],
        files=[("empty.csv", ("cis\n" + "\n".join(codes)).encode())],
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"] == "manual_import_product_required"
    assert persistence_calls == []
    assert await _seller_marking_write_counts(seller_id) == {
        "imports": 0,
        "source_files": 0,
        "pools": 0,
        "pool_products": 0,
        "codes": 0,
        "events": 0,
    }


@pytest.mark.asyncio
async def test_import_rejects_mixed_covered_and_uncovered_gtins_before_writes(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=headers,
        json={
            "name": "Partial assignments",
            "email": f"partial-{uuid.uuid4().hex[:8]}@example.com",
        },
    )
    seller_id = str(seller.json()["id"])
    product_id = await _create_product(async_client, headers, seller_id, name="Assigned product")
    gtin_a = "00000000000201"
    gtin_b = "00000000000202"
    codes = [f"01{gtin_a}21{'G' * 20}0001", f"01{gtin_b}21{'H' * 20}0002"]
    persistence_calls: list[object] = []

    monkeypatch.setattr(
        marking_service,
        "_persist_import_source_pdfs",
        lambda *args, **kwargs: persistence_calls.append((args, kwargs)),
    )
    response = await _import_files(
        async_client,
        headers,
        seller_id=seller_id,
        pools=[{"gtin": gtin_a, "title": "Covered A", "product_ids": [product_id]}],
        files=[("partial.csv", ("cis\n" + "\n".join(codes)).encode())],
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"] == "manual_import_product_required"
    assert persistence_calls == []
    assert await _seller_marking_write_counts(seller_id) == {
        "imports": 0,
        "source_files": 0,
        "pools": 0,
        "pool_products": 0,
        "codes": 0,
        "events": 0,
    }


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
            (
                await session.execute(
                    select(MarkingPoolProduct).where(MarkingPoolProduct.pool_id == pool_id)
                )
            )
            .scalars()
            .all()
        )
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
    product_id = await _create_product(async_client, h, seller_id, name="Two GTIN product")
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
            {"gtin": gtin_a, "title": "Пул A", "product_ids": [product_id]},
            {"gtin": gtin_b, "title": "Пул B", "product_ids": [product_id]},
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
    product_id = await _create_product(async_client, h, seller_id, name="Duplicate product")
    gtin = "00000000009999"
    cis = f"01{gtin}21{'D' * 20}0001"
    csv_first = f"cis\n{cis}\nshort"
    imp1 = await _import_files(
        async_client,
        h,
        seller_id=seller_id,
        pools=[{"title": "Dup pool", "product_ids": [product_id]}],
        files=[("codes.csv", csv_first.encode())],
    )
    assert imp1.status_code == 200, imp1.text
    assert imp1.json()["accepted_count"] == 1
    assert imp1.json()["skipped_count"] == 1

    imp2 = await _import_files(
        async_client,
        h,
        seller_id=seller_id,
        pools=[{"title": "Dup pool", "product_ids": [product_id]}],
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
    product_id = await _create_product(async_client, h, seller_id, name="Document product")
    gtin = "00000000005555"
    cis = f"01{gtin}21{'E' * 20}0001"
    imp = await _import_files(
        async_client,
        h,
        seller_id=seller_id,
        pools=[{"title": "Doc pool", "product_ids": [product_id]}],
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


@pytest.mark.asyncio
async def test_import_same_cis_twice_idempotent(async_client: AsyncClient) -> None:
    """TC-NEW CZ-H7: repeat import of same CIS is safe and reports skipped duplicate."""
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Idem", "email": f"idem-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    product_id = await _create_product(async_client, h, seller_id, name="Idempotent product")
    gtin = "00000000007777"
    cis = f"01{gtin}21{'F' * 20}0001"
    pools: list[dict[str, object]] = [{"title": "Idem pool", "product_ids": [product_id]}]
    csv_body = f"cis\n{cis}".encode()

    first = await _import_files(
        async_client,
        h,
        seller_id=seller_id,
        pools=pools,
        files=[("codes.csv", csv_body)],
    )
    assert first.status_code == 200, first.text
    assert first.json()["accepted_count"] == 1
    first_doc = first.json()["document_number"]

    second = await _import_files(
        async_client,
        h,
        seller_id=seller_id,
        pools=pools,
        files=[("codes.csv", csv_body)],
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["accepted_count"] == 0
    assert second_body["skipped_count"] == 1
    assert any(r["reason"] == "duplicate" for r in second_body["skip_reasons"])
    assert second_body["document_number"].startswith("ЗАГРКМ-")
    assert second_body["document_number"] != first_doc

    async with SessionLocal() as session:
        count = (
            await session.execute(
                select(func.count(MarkingCode.id)).where(MarkingCode.cis_code == cis)
            )
        ).scalar_one()
        assert int(count) == 1
