from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

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
from app.models.seller import Seller
from app.services import marking_code_service as mc_svc


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
async def test_existing_cis_lookup_chunks_above_postgresql_parameter_limit() -> None:
    session = AsyncMock()
    empty_rows = MagicMock()
    empty_rows.all.return_value = []
    session.scalars.return_value = empty_rows
    cis_codes = [f"cis-{index}" for index in range(65_536)]

    existing = await mc_svc._existing_import_cis_codes(
        session,
        uuid.uuid4(),
        cis_codes,
    )

    assert existing == set()
    chunk_sizes: list[int] = []
    for call in session.scalars.await_args_list:
        statement = call.args[0]
        list_parameters = [
            value for value in statement.compile().params.values() if isinstance(value, list)
        ]
        assert len(list_parameters) == 1
        chunk_sizes.append(len(list_parameters[0]))
    assert chunk_sizes == [50_000, 15_536]
    assert max(chunk_sizes) + 1 < 65_535


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
    assert body["groups"][0]["suggested_title"] == "GTIN …9999"


@pytest.mark.asyncio
async def test_import_preview_ignores_existing_same_gtin_pools_without_mutation(
    async_client: AsyncClient,
) -> None:
    h = await _register_admin(async_client)
    seller_response = await async_client.post(
        "/sellers",
        headers=h,
        json={
            "name": "Preview duplicates",
            "email": f"prev-dups-{uuid.uuid4().hex[:8]}@example.com",
        },
    )
    seller_id = uuid.UUID(seller_response.json()["id"])
    gtin = "00000000008123"

    async with SessionLocal() as session:
        seller = await session.get(Seller, seller_id)
        assert seller is not None
        session.add_all(
            [
                MarkingPool(
                    tenant_id=seller.tenant_id,
                    seller_id=seller.id,
                    gtin=gtin,
                    title="Historical upload",
                ),
                MarkingPool(
                    tenant_id=seller.tenant_id,
                    seller_id=seller.id,
                    gtin=gtin,
                    title="Corrected upload",
                ),
            ]
        )
        await session.commit()
        before = {
            "pools": list(
                (
                    await session.execute(
                        select(MarkingPool.id, MarkingPool.title).where(
                            MarkingPool.tenant_id == seller.tenant_id,
                            MarkingPool.seller_id == seller.id,
                        )
                    )
                ).all()
            ),
            "imports": int(
                (
                    await session.execute(
                        select(func.count(MarkingCodeImport.id)).where(
                            MarkingCodeImport.tenant_id == seller.tenant_id
                        )
                    )
                ).scalar_one()
            ),
            "codes": int(
                (
                    await session.execute(
                        select(func.count(MarkingCode.id)).where(
                            MarkingCode.tenant_id == seller.tenant_id
                        )
                    )
                ).scalar_one()
            ),
            "links": int(
                (
                    await session.execute(
                        select(func.count(MarkingPoolProduct.id)).where(
                            MarkingPoolProduct.tenant_id == seller.tenant_id
                        )
                    )
                ).scalar_one()
            ),
            "events": int(
                (
                    await session.execute(
                        select(func.count(MarkingCodeEvent.id)).where(
                            MarkingCodeEvent.tenant_id == seller.tenant_id
                        )
                    )
                ).scalar_one()
            ),
        }

    cis = f"01{gtin}21{'V' * 20}0001"
    preview = await async_client.post(
        "/operations/marking-codes/import/preview",
        headers=h,
        data={"seller_id": str(seller_id)},
        files=[("files", ("codes.csv", f"cis\n{cis}".encode(), "text/csv"))],
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["groups"] == [
        {"gtin": gtin, "codes_count": 1, "suggested_title": "GTIN …8123"}
    ]

    async with SessionLocal() as session:
        seller = await session.get(Seller, seller_id)
        assert seller is not None
        after = {
            "pools": list(
                (
                    await session.execute(
                        select(MarkingPool.id, MarkingPool.title).where(
                            MarkingPool.tenant_id == seller.tenant_id,
                            MarkingPool.seller_id == seller.id,
                        )
                    )
                ).all()
            ),
            "imports": int(
                (
                    await session.execute(
                        select(func.count(MarkingCodeImport.id)).where(
                            MarkingCodeImport.tenant_id == seller.tenant_id
                        )
                    )
                ).scalar_one()
            ),
            "codes": int(
                (
                    await session.execute(
                        select(func.count(MarkingCode.id)).where(
                            MarkingCode.tenant_id == seller.tenant_id
                        )
                    )
                ).scalar_one()
            ),
            "links": int(
                (
                    await session.execute(
                        select(func.count(MarkingPoolProduct.id)).where(
                            MarkingPoolProduct.tenant_id == seller.tenant_id
                        )
                    )
                ).scalar_one()
            ),
            "events": int(
                (
                    await session.execute(
                        select(func.count(MarkingCodeEvent.id)).where(
                            MarkingCodeEvent.tenant_id == seller.tenant_id
                        )
                    )
                ).scalar_one()
            ),
        }
    assert after == before


@pytest.mark.asyncio
async def test_import_creates_fresh_pool_and_leaves_same_gtin_pools_untouched(
    async_client: AsyncClient,
) -> None:
    h = await _register_admin(async_client)
    seller_response = await async_client.post(
        "/sellers",
        headers=h,
        json={
            "name": "Fresh upload seller",
            "email": f"fresh-upload-{uuid.uuid4().hex[:8]}@example.com",
        },
    )
    seller_id = uuid.UUID(seller_response.json()["id"])
    product_ids: list[uuid.UUID] = []
    for index in range(2):
        product = await async_client.post(
            "/products",
            headers=h,
            json={
                "name": f"Fresh product {index}",
                "sku_code": f"FRESH-{uuid.uuid4().hex[:8]}-{index}",
                "length_mm": 10,
                "width_mm": 10,
                "height_mm": 10,
                "seller_id": str(seller_id),
            },
        )
        assert product.status_code == 200, product.text
        product_ids.append(uuid.UUID(product.json()["id"]))

    gtin = "00000000008124"
    async with SessionLocal() as session:
        seller = await session.get(Seller, seller_id)
        assert seller is not None
        historical = MarkingPool(
            tenant_id=seller.tenant_id,
            seller_id=seller.id,
            gtin=gtin,
            title="Historical generic pool",
        )
        corrected = MarkingPool(
            tenant_id=seller.tenant_id,
            seller_id=seller.id,
            gtin=gtin,
            title="Corrected linked pool",
        )
        session.add_all([historical, corrected])
        await session.flush()
        session.add(
            MarkingPoolProduct(
                tenant_id=seller.tenant_id,
                pool_id=corrected.id,
                product_id=product_ids[0],
            )
        )
        await session.commit()
        existing_pool_ids = {historical.id, corrected.id}
        before_links = set(
            (
                await session.execute(
                    select(MarkingPoolProduct.pool_id, MarkingPoolProduct.product_id).where(
                        MarkingPoolProduct.pool_id.in_(existing_pool_ids)
                    )
                )
            ).all()
        )

    cis = f"01{gtin}21{'N' * 20}0001"
    imported = await _import_files(
        async_client,
        h,
        seller_id=str(seller_id),
        pools=[
            {
                "gtin": gtin,
                "title": "Current upload",
                "product_ids": [str(product_id) for product_id in product_ids],
            }
        ],
        files=[("codes.csv", f"cis\n{cis}".encode())],
    )
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert body["accepted_count"] == 1
    assert len(body["pools"]) == 1
    fresh_pool_id = uuid.UUID(body["pools"][0]["pool_id"])
    assert fresh_pool_id not in existing_pool_ids

    async with SessionLocal() as session:
        pools = list(
            (
                await session.execute(
                    select(MarkingPool).where(
                        MarkingPool.seller_id == seller_id,
                        MarkingPool.gtin == gtin,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert {(pool.id, pool.title) for pool in pools} == {
            (historical.id, "Historical generic pool"),
            (corrected.id, "Corrected linked pool"),
            (fresh_pool_id, "Current upload"),
        }
        code = (
            await session.execute(
                select(MarkingCode).where(MarkingCode.cis_code == cis)
            )
        ).scalar_one()
        assert code.pool_id == fresh_pool_id
        fresh_links = set(
            (
                await session.execute(
                    select(MarkingPoolProduct.product_id).where(
                        MarkingPoolProduct.pool_id == fresh_pool_id
                    )
                )
            ).scalars()
        )
        assert fresh_links == set(product_ids)
        after_links = set(
            (
                await session.execute(
                    select(MarkingPoolProduct.pool_id, MarkingPoolProduct.product_id).where(
                        MarkingPoolProduct.pool_id.in_(existing_pool_ids)
                    )
                )
            ).all()
        )
        assert after_links == before_links


@pytest.mark.asyncio
async def test_fresh_import_pool_is_isolated_by_tenant_and_seller(
    async_client: AsyncClient,
) -> None:
    current_headers = await _register_admin(async_client)
    current_seller_response = await async_client.post(
        "/sellers",
        headers=current_headers,
        json={
            "name": "Current seller",
            "email": f"current-{uuid.uuid4().hex[:8]}@example.com",
        },
    )
    other_seller_response = await async_client.post(
        "/sellers",
        headers=current_headers,
        json={
            "name": "Other seller",
            "email": f"other-{uuid.uuid4().hex[:8]}@example.com",
        },
    )
    other_tenant_headers = await _register_admin(async_client)
    other_tenant_seller_response = await async_client.post(
        "/sellers",
        headers=other_tenant_headers,
        json={
            "name": "Other tenant seller",
            "email": f"other-tenant-{uuid.uuid4().hex[:8]}@example.com",
        },
    )
    current_seller_id = uuid.UUID(current_seller_response.json()["id"])
    other_seller_id = uuid.UUID(other_seller_response.json()["id"])
    other_tenant_seller_id = uuid.UUID(other_tenant_seller_response.json()["id"])
    product_response = await async_client.post(
        "/products",
        headers=current_headers,
        json={
            "name": "Isolated product",
            "sku_code": f"ISOLATED-{uuid.uuid4().hex[:8]}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": str(current_seller_id),
        },
    )
    assert product_response.status_code == 200, product_response.text
    product_id = product_response.json()["id"]
    gtin = "00000000008125"

    async with SessionLocal() as session:
        current_seller = await session.get(Seller, current_seller_id)
        other_seller = await session.get(Seller, other_seller_id)
        other_tenant_seller = await session.get(Seller, other_tenant_seller_id)
        assert current_seller is not None
        assert other_seller is not None
        assert other_tenant_seller is not None
        seeded = [
            MarkingPool(
                tenant_id=current_seller.tenant_id,
                seller_id=current_seller.id,
                gtin=gtin,
                title="Current historical",
            ),
            MarkingPool(
                tenant_id=other_seller.tenant_id,
                seller_id=other_seller.id,
                gtin=gtin,
                title="Other seller historical",
            ),
            MarkingPool(
                tenant_id=other_tenant_seller.tenant_id,
                seller_id=other_tenant_seller.id,
                gtin=gtin,
                title="Other tenant historical",
            ),
        ]
        session.add_all(seeded)
        await session.commit()
        seeded_ids = {pool.id for pool in seeded}

    cis = f"01{gtin}21{'I' * 20}0001"
    imported = await _import_files(
        async_client,
        current_headers,
        seller_id=str(current_seller_id),
        pools=[
            {
                "gtin": gtin,
                "title": "Isolated current upload",
                "product_ids": [product_id],
            }
        ],
        files=[("codes.csv", f"cis\n{cis}".encode())],
    )
    assert imported.status_code == 200, imported.text
    fresh_pool_id = uuid.UUID(imported.json()["pools"][0]["pool_id"])
    assert fresh_pool_id not in seeded_ids

    async with SessionLocal() as session:
        all_pools = list(
            (
                await session.execute(
                    select(MarkingPool).where(MarkingPool.gtin == gtin)
                )
            )
            .scalars()
            .all()
        )
        assert {(pool.id, pool.title) for pool in all_pools} == {
            (seeded[0].id, "Current historical"),
            (seeded[1].id, "Other seller historical"),
            (seeded[2].id, "Other tenant historical"),
            (fresh_pool_id, "Isolated current upload"),
        }
        fresh_pool = await session.get(MarkingPool, fresh_pool_id)
        assert fresh_pool is not None
        assert fresh_pool.tenant_id == current_seller.tenant_id
        assert fresh_pool.seller_id == current_seller_id


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
    gtin = "00000000007777"
    cis = f"01{gtin}21{'F' * 20}0001"
    pools: list[dict[str, object]] = [{"title": "Idem pool", "product_ids": []}]
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
    async with SessionLocal() as session:
        pools_after_first = int(
            (
                await session.execute(
                    select(func.count(MarkingPool.id)).where(
                        MarkingPool.seller_id == uuid.UUID(seller_id),
                        MarkingPool.gtin == gtin,
                    )
                )
            ).scalar_one()
        )

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
    assert second_body["pools"] == []
    assert second_body["document_number"].startswith("ЗАГРКМ-")
    assert second_body["document_number"] != first_doc

    async with SessionLocal() as session:
        count = (
            await session.execute(
                select(func.count(MarkingCode.id)).where(MarkingCode.cis_code == cis)
            )
        ).scalar_one()
        assert int(count) == 1
        pools_after_second = int(
            (
                await session.execute(
                    select(func.count(MarkingPool.id)).where(
                        MarkingPool.seller_id == uuid.UUID(seller_id),
                        MarkingPool.gtin == gtin,
                    )
                )
            ).scalar_one()
        )
        assert pools_after_second == pools_after_first == 1
