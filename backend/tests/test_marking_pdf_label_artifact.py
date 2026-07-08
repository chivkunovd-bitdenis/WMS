from __future__ import annotations

import json
import uuid

import fitz
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from test_packaging_tasks import _register_admin

from app.db.session import SessionLocal
from app.models.marking_code import MarkingCode


def _build_label_pdf(cis: str, footer_text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=164, height=113)
    page.insert_text((12, 24), "Честный знак", fontsize=8)
    page.insert_text((12, 42), cis, fontsize=6)
    page.insert_text((12, 58), footer_text, fontsize=7)
    pdf_bytes = bytes(doc.tobytes())
    doc.close()
    return pdf_bytes


def _build_two_label_pdf(cis_a: str, cis_b: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=360, height=240)
    page.insert_text((12, 24), "Честный знак", fontsize=8)
    page.insert_text((12, 42), cis_a, fontsize=6)
    page.insert_text((190, 24), "Честный знак", fontsize=8)
    page.insert_text((190, 42), cis_b, fontsize=6)
    pdf_bytes = bytes(doc.tobytes())
    doc.close()
    return pdf_bytes


@pytest.mark.asyncio
async def test_pdf_import_stores_label_artifact_per_cis(async_client: AsyncClient) -> None:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "PDF Seller", "email": f"s-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201
    seller_id = seller.json()["id"]

    sku = f"SKU-PDF-{uuid.uuid4().hex[:6]}"
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "PDF label product",
            "sku_code": sku,
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    assert pr.status_code == 200
    product_id = pr.json()["id"]

    gtin14 = "04600000000001"
    cis = f"01{gtin14}21{'D' * 20}0001"
    pdf_bytes = _build_label_pdf(cis, "control footer")
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "PDF pool", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("labels.pdf", pdf_bytes, "application/pdf"))],
    )
    assert imp.status_code == 200, imp.text
    assert imp.json()["accepted_count"] == 1

    codes = await async_client.get(
        f"/operations/marking-codes/products/{product_id}/codes",
        headers=h,
    )
    assert codes.status_code == 200
    row = codes.json()[0]
    assert row["has_label_artifact"] is True
    code_id = row["id"]

    png = await async_client.get(
        f"/operations/marking-codes/codes/{code_id}/label-artifact?format=png",
        headers=h,
    )
    assert png.status_code == 200
    assert png.headers["content-type"] == "image/png"
    assert len(png.content) > 100

    pdf = await async_client.get(
        f"/operations/marking-codes/codes/{code_id}/label-artifact?format=pdf",
        headers=h,
    )
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")

    async with SessionLocal() as session:
        code = (
            await session.execute(select(MarkingCode).where(MarkingCode.id == uuid.UUID(code_id)))
        ).scalar_one()
        assert code.label_artifact_pdf is not None
        assert code.label_artifact_pdf.startswith(b"%PDF")

    from app.models.marking_code import MarkingCodeImportFile
    from app.services.marking_import_storage_service import read_marking_import_source_pdf

    import_id = imp.json()["import_id"]
    async with SessionLocal() as session:
        source_file = (
            await session.execute(
                select(MarkingCodeImportFile).where(
                    MarkingCodeImportFile.import_batch_id == uuid.UUID(import_id),
                ),
            )
        ).scalar_one()
        assert source_file.original_filename == "labels.pdf"
        assert source_file.size_bytes == len(pdf_bytes)
        stored_pdf = read_marking_import_source_pdf(source_file.storage_key)
        assert stored_pdf == pdf_bytes


@pytest.mark.asyncio
async def test_pdf_import_succeeds_when_source_storage_disabled(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.marking_import_storage_service.get_object_storage_backend",
        lambda: None,
    )

    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "No storage seller", "email": f"s-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201
    seller_id = seller.json()["id"]

    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "No storage product",
            "sku_code": f"SKU-NS-{uuid.uuid4().hex[:6]}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    assert pr.status_code == 200
    product_id = pr.json()["id"]

    gtin14 = "04600000000003"
    cis = f"01{gtin14}21{'F' * 20}0001"
    pdf_bytes = _build_label_pdf(cis, "storage disabled")
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "No storage pool", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("labels.pdf", pdf_bytes, "application/pdf"))],
    )
    assert imp.status_code == 200, imp.text
    assert imp.json()["accepted_count"] == 1

    from app.models.marking_code import MarkingCodeImportFile

    import_id = imp.json()["import_id"]
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(MarkingCodeImportFile).where(
                    MarkingCodeImportFile.import_batch_id == uuid.UUID(import_id),
                ),
            )
        ).scalars().all()
        assert rows == []


@pytest.mark.asyncio
async def test_csv_import_does_not_store_source_pdf(async_client: AsyncClient) -> None:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "CSV Seller", "email": f"s-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201
    seller_id = seller.json()["id"]

    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "CSV product",
            "sku_code": f"SKU-CSV-{uuid.uuid4().hex[:6]}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    assert pr.status_code == 200
    product_id = pr.json()["id"]

    gtin14 = "04600000000002"
    cis = f"01{gtin14}21{'E' * 20}0001"
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "CSV pool", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("codes.csv", f"cis\n{cis}".encode(), "text/csv"))],
    )
    assert imp.status_code == 200, imp.text

    from app.models.marking_code import MarkingCodeImportFile

    import_id = imp.json()["import_id"]
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(MarkingCodeImportFile).where(
                    MarkingCodeImportFile.import_batch_id == uuid.UUID(import_id),
                ),
            )
        ).scalars().all()
        assert rows == []


def _build_seller_style_label_pdf(cis: str) -> bytes:
    """One CIS per page plus product description lines (seller PDF shape)."""
    doc = fitz.open()
    page = doc.new_page(width=170, height=113)
    page.insert_text((12, 18), "Спортивные леггинсы", fontsize=7)
    page.insert_text((12, 30), "тайтсы", fontsize=7)
    page.insert_text((12, 42), "ЧЕРНЫЙ,АНТРАЦИТОВЫ", fontsize=7)
    page.insert_text((12, 54), "Й цвет черный.белый.тд", fontsize=7)
    page.insert_text((12, 66), "разм L", fontsize=7)
    page.insert_text((12, 90), cis, fontsize=6)
    pdf_bytes = bytes(doc.tobytes())
    doc.close()
    return pdf_bytes


@pytest.mark.asyncio
async def test_pdf_import_stores_artifact_when_page_has_product_text_plus_one_cis(
    async_client: AsyncClient,
) -> None:
    """Seller PDF: product description must not block single-label artifact."""
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "PDF Seller Style", "email": f"s-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201
    seller_id = seller.json()["id"]

    sku = f"SKU-PDF-STYLE-{uuid.uuid4().hex[:6]}"
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "PDF seller style product",
            "sku_code": sku,
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    assert pr.status_code == 200
    product_id = pr.json()["id"]

    gtin14 = "02900446283341"
    cis = f"01{gtin14}21{'bTkx0VXUAVzAB' * 2}"
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "PDF seller style pool", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("labels.pdf", _build_seller_style_label_pdf(cis), "application/pdf"))],
    )
    assert imp.status_code == 200, imp.text
    assert imp.json()["accepted_count"] == 1

    codes = await async_client.get(
        f"/operations/marking-codes/products/{product_id}/codes",
        headers=h,
    )
    assert codes.status_code == 200
    row = codes.json()[0]
    assert row["has_label_artifact"] is True

    artifact = await async_client.get(
        f"/operations/marking-codes/codes/{row['id']}/label-artifact?format=png",
        headers=h,
    )
    assert artifact.status_code == 200
    assert len(artifact.content) > 100


@pytest.mark.asyncio
async def test_pdf_import_does_not_reuse_multi_label_page_as_artifact(
    async_client: AsyncClient,
) -> None:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "PDF Multi Seller", "email": f"s-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201
    seller_id = seller.json()["id"]

    sku = f"SKU-PDF-MULTI-{uuid.uuid4().hex[:6]}"
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "PDF multi label product",
            "sku_code": sku,
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    assert pr.status_code == 200
    product_id = pr.json()["id"]

    gtin14 = "04600000000002"
    cis_a = f"01{gtin14}21{'E' * 20}0001"
    cis_b = f"01{gtin14}21{'E' * 20}0002"
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "PDF multi pool", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("labels.pdf", _build_two_label_pdf(cis_a, cis_b), "application/pdf"))],
    )
    assert imp.status_code == 200, imp.text
    assert imp.json()["accepted_count"] == 2

    codes = await async_client.get(
        f"/operations/marking-codes/products/{product_id}/codes",
        headers=h,
    )
    assert codes.status_code == 200
    rows = codes.json()
    assert len(rows) == 2
    assert {row["has_label_artifact"] for row in rows} == {True}

    by_cis = {row["cis_code"]: row for row in rows}
    for cis in (cis_a, cis_b):
        row = by_cis[cis]
        artifact = await async_client.get(
            f"/operations/marking-codes/codes/{row['id']}/label-artifact?format=pdf",
            headers=h,
        )
        assert artifact.status_code == 200
        assert artifact.content.startswith(b"%PDF")
        doc = fitz.open(stream=artifact.content, filetype="pdf")
        try:
            text = doc[0].get_text("text")
            assert cis in text
            other = cis_b if cis == cis_a else cis_a
            assert other not in text
            source = fitz.open(stream=_build_two_label_pdf(cis_a, cis_b), filetype="pdf")
            try:
                assert doc[0].rect.get_area() < source[0].rect.get_area()
            finally:
                source.close()
        finally:
            doc.close()


@pytest.mark.asyncio
async def test_csv_import_has_no_label_artifact(async_client: AsyncClient) -> None:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "CSV Seller", "email": f"s-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201
    seller_id = seller.json()["id"]

    sku = f"SKU-CSV-{uuid.uuid4().hex[:6]}"
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "CSV product",
            "sku_code": sku,
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    assert pr.status_code == 200
    product_id = pr.json()["id"]

    gtin14 = "04600000000003"
    cis = f"01{gtin14}21{'F' * 20}0001"
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "CSV pool", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("codes.csv", f"cis,sku_code\n{cis},{sku}\n", "text/csv"))],
    )
    assert imp.status_code == 200, imp.text
    assert imp.json()["accepted_count"] == 1

    codes = await async_client.get(
        f"/operations/marking-codes/products/{product_id}/codes",
        headers=h,
    )
    assert codes.status_code == 200
    row = codes.json()[0]
    assert row["has_label_artifact"] is False

    artifact = await async_client.get(
        f"/operations/marking-codes/codes/{row['id']}/label-artifact?format=png",
        headers=h,
    )
    assert artifact.status_code == 404
    assert artifact.json()["detail"] == "label_artifact_missing"


def test_pdf_bytes_to_png_trims_whitespace_margins() -> None:
    from app.services.marking_label_artifact_service import pdf_bytes_to_png

    doc = fitz.open()
    page = doc.new_page(width=400, height=400)
    page.insert_text((24, 36), "Честный знак", fontsize=10)
    page.insert_text((24, 56), "01" + "0" * 14 + "21" + "A" * 20, fontsize=6)
    loose_pdf = bytes(doc.tobytes())
    doc.close()

    loose = fitz.open(stream=pdf_bytes_to_png(loose_pdf, dpi=72), filetype="png")
    try:
        loose_pix = loose[0].get_pixmap()
        assert loose_pix.width <= 300
        assert loose_pix.height <= 300
    finally:
        loose.close()

    tight_pdf = _build_label_pdf("01" + "0" * 14 + "21" + "B" * 20, "footer")
    tight = fitz.open(stream=pdf_bytes_to_png(tight_pdf, dpi=150), filetype="png")
    try:
        tight_pix = tight[0].get_pixmap()
        assert tight_pix.width > 50
        assert tight_pix.height > 50
    finally:
        tight.close()
