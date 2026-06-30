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
