from __future__ import annotations

import json
import threading
import uuid
from types import SimpleNamespace

import fitz
import pytest
import zxingcpp
from httpx import AsyncClient
from marking_datamatrix_test_helpers import encode_datamatrix_png
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
    page.insert_image(fitz.Rect(60, 64, 106, 110), stream=encode_datamatrix_png(cis))
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
    page.insert_image(fitz.Rect(20, 60, 170, 210), stream=encode_datamatrix_png(cis_a))
    page.insert_image(fitz.Rect(200, 60, 350, 210), stream=encode_datamatrix_png(cis_b))
    pdf_bytes = bytes(doc.tobytes())
    doc.close()
    return pdf_bytes


def _build_stored_label_artifact(
    cis: str,
    *,
    distorted: bool,
) -> bytes:
    """Production-like persisted PDF: exact CIS plus an embedded Data Matrix image."""
    barcode = zxingcpp.create_barcode(
        cis.encode("utf-8"),
        format=zxingcpp.DataMatrix,
        force_square=distorted,
    )
    image = zxingcpp.write_barcode_to_image(
        barcode,
        scale=8,
        add_quiet_zones=True,
    )
    height, width = image.shape
    png = fitz.Pixmap(fitz.csGRAY, width, height, bytes(image), 0).tobytes("png")

    doc = fitz.open()
    try:
        page = doc.new_page(width=164, height=113)
        page.insert_text((92, 14), "HONEST", fontsize=9)
        page.insert_text((92, 27), "SIGN", fontsize=9)
        page.insert_text((92, 43), "GTIN 4630321689835", fontsize=6)
        page.insert_text((92, 55), "KM 5TVsOggEdo6!!", fontsize=6)
        page.insert_text((92, 106), "crypto-tail-control", fontsize=5)
        if distorted:
            # Same defect as the production screenshot: a square symbol is
            # embedded at 90x35 pt, so every module is ~2.5x wider than tall.
            target = fitz.Rect(8, 45, 98, 80)
            page.insert_image(target, stream=png, keep_proportion=False)
        else:
            # A valid rectangular ECC200 symbol keeps the source image aspect;
            # its overall shape is wide but its individual modules are square.
            target = fitz.Rect(8, 45, 98, 45 + 90 * height / width)
            page.insert_image(target, stream=png, keep_proportion=True)
        return bytes(doc.tobytes())
    finally:
        doc.close()


def _rendered_module_pitches(pdf_bytes: bytes, cis: str) -> tuple[float, float, tuple[float, ...]]:
    """Independent raster assertion over the actual PDF page sent to Chrome."""
    from statistics import median

    from app.services.marking_datamatrix_service import decode_datamatrix_codes_on_pdf_page

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        matches = [
            (page, item)
            for page in doc
            for item in decode_datamatrix_codes_on_pdf_page(page)
            if item.value == cis
        ]
        assert len(matches) == 1
        page, decoded = matches[0]
        box = fitz.Rect(decoded.page_rect)
        pix = page.get_pixmap(
            matrix=fitz.Matrix(600 / 72, 600 / 72),
            clip=box,
            colorspace=fitz.csGRAY,
            alpha=False,
        )
        samples = pix.samples

        def is_black(x: int, y: int) -> bool:
            return samples[y * pix.stride + x] < 128

        dark = [
            (x, y)
            for y in range(pix.height)
            for x in range(pix.width)
            if is_black(x, y)
        ]
        min_x = min(x for x, _ in dark)
        max_x = max(x for x, _ in dark)
        min_y = min(y for _, y in dark)
        max_y = max(y for _, y in dark)

        def runs(values: list[bool]) -> list[int]:
            result: list[int] = []
            previous = values[0]
            start = 0
            for index, value in enumerate(values[1:], 1):
                if value == previous:
                    continue
                result.append(index - start)
                previous = value
                start = index
            result.append(len(values) - start)
            return [value for value in result if value >= 2]

        horizontal_edges = [
            runs([is_black(x, y) for x in range(min_x, max_x + 1)])
            for y in (min_y, max_y)
        ]
        vertical_edges = [
            runs([is_black(x, y) for y in range(min_y, max_y + 1)])
            for x in (min_x, max_x)
        ]
        horizontal = max(horizontal_edges, key=len)
        vertical = max(vertical_edges, key=len)
        assert len(horizontal) >= 8 and len(vertical) >= 8
        return float(median(horizontal)), float(median(vertical)), decoded.page_rect
    finally:
        doc.close()


def _assert_rendered_quiet_zone(
    pdf_bytes: bytes,
    cis: str,
    module_pitch: float,
) -> None:
    """Assert one white module around the decoded symbol in the final PDF raster."""
    from app.services.marking_datamatrix_service import decode_datamatrix_codes_on_pdf_page

    scale = 600 / 72
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        matches = [
            (page, item)
            for page in doc
            for item in decode_datamatrix_codes_on_pdf_page(page)
            if item.value == cis
        ]
        assert len(matches) == 1
        page, decoded = matches[0]
        pix = page.get_pixmap(
            matrix=fitz.Matrix(scale, scale),
            colorspace=fitz.csGRAY,
            alpha=False,
        )
        x0, y0, x1, y1 = (round(value * scale) for value in decoded.page_rect)
        width = max(round(module_pitch), 2)
        # Decoder bounds can differ from the anti-aliased black edge by one
        # pixel. Skip that edge pixel, then require a full module of white.
        guard = 2
        strips = [
            [
                pix.samples[y * pix.stride + x]
                for y in range(y0 + guard, y1 - guard + 1)
                for x in range(x0 - guard - width, x0 - guard)
            ],
            [
                pix.samples[y * pix.stride + x]
                for y in range(y0 + guard, y1 - guard + 1)
                for x in range(x1 + guard, x1 + guard + width)
            ],
            [
                pix.samples[y * pix.stride + x]
                for y in range(y0 - guard - width, y0 - guard)
                for x in range(x0 + guard, x1 - guard + 1)
            ],
            [
                pix.samples[y * pix.stride + x]
                for y in range(y1 + guard, y1 + guard + width)
                for x in range(x0 + guard, x1 - guard + 1)
            ],
        ]
        assert all(strip and min(strip) >= 240 for strip in strips)
    finally:
        doc.close()


@pytest.mark.asyncio
async def test_pdf_import_stores_label_artifact_per_cis(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api import marking_codes as api
    from app.services import marking_code_service as svc
    from app.services.marking_label_artifact_service import pdf_bytes_to_png

    loop_thread_id = threading.get_ident()
    checked: set[str] = set()

    def require_worker(name: str, original: object) -> object:
        def wrapped(*args: object, **kwargs: object) -> object:
            assert threading.get_ident() != loop_thread_id, name
            checked.add(name)
            return original(*args, **kwargs)  # type: ignore[operator]
        return wrapped

    monkeypatch.setattr(svc, "parse_import_file", require_worker("parse", svc.parse_import_file))
    monkeypatch.setattr(
        svc,
        "is_printable_label_artifact",
        require_worker("validate", svc.is_printable_label_artifact),
    )
    monkeypatch.setattr(api, "pdf_bytes_to_png", require_worker("render", pdf_bytes_to_png))
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
    preview = await async_client.post(
        "/operations/marking-codes/import/preview",
        headers=h,
        data={"seller_id": seller_id},
        files=[("files", ("labels.pdf", pdf_bytes, "application/pdf"))],
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["total_codes"] == 1
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
        assert pdf.content == code.label_artifact_pdf
        infos = await svc._printed_code_infos([code])
        assert infos[0].has_label_artifact is True
        assert infos[0].cis_code == cis

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
    assert checked == {"parse", "validate", "render"}


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
    page.insert_image(fitz.Rect(118, 10, 164, 65), stream=encode_datamatrix_png(cis))
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


def _build_two_line_ai_wrapped_label_pdf(gtin14: str, serial: str) -> bytes:
    """Real seller label shape: '(01) <gtin>' and '(21) <serial>' printed on
    two separate lines (label too narrow for the full code on one line),
    surrounded by unrelated product-description text — see the
    Chin-56005_*.pdf example from the bugreport."""
    doc = fitz.open()
    page = doc.new_page(width=164, height=234)
    page.insert_text((12, 18), "Наименование товара: Женская", fontsize=7)
    page.insert_text((12, 30), "куртка / Women's jacket.", fontsize=7)
    page.insert_text((12, 42), "Торговая марка: FADIN", fontsize=7)
    page.insert_text((12, 54), "Размер: 46 Цвет: бежевый", fontsize=7)
    page.insert_text((12, 90), f"(01) {gtin14}", fontsize=6)
    page.insert_text((12, 102), f"(21) {serial}", fontsize=6)
    page.insert_text((12, 120), "Состав: внешний слой 100% полиэстер,", fontsize=7)
    page.insert_text((12, 132), "наполнитель 100% био-пух", fontsize=7)
    page.insert_image(
        fitz.Rect(40, 142, 120, 222),
        stream=encode_datamatrix_png(f"01{gtin14}21{serial}"),
    )
    pdf_bytes = bytes(doc.tobytes())
    doc.close()
    return pdf_bytes


@pytest.mark.asyncio
async def test_pdf_import_parses_cis_wrapped_in_parens_across_two_lines(
    async_client: AsyncClient,
) -> None:
    """Bugfix regression: seller PDFs that print '(01) <gtin>' and
    '(21) <serial>' on two separate, parenthesized lines used to yield
    'чз не найдены' (no valid codes found) because the parser only accepted
    a bare, single-line 'AI01<gtin>AI21<serial>' shape."""
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "PDF Wrapped Seller", "email": f"s-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201
    seller_id = seller.json()["id"]

    sku = f"SKU-PDF-WRAP-{uuid.uuid4().hex[:6]}"
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "PDF wrapped-cis product",
            "sku_code": sku,
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    assert pr.status_code == 200
    product_id = pr.json()["id"]

    gtin14 = "04630321688296"
    serial = "5E'qvbnH(hTbG"
    pdf_bytes = _build_two_line_ai_wrapped_label_pdf(gtin14, serial)

    filename = "Chin-56005_beige_46_TGHU6649210_1pcs.pdf"
    preview = await async_client.post(
        "/operations/marking-codes/import/preview",
        headers=h,
        data={"seller_id": seller_id},
        files=[("files", (filename, pdf_bytes, "application/pdf"))],
    )
    assert preview.status_code == 200, preview.text
    preview_body = preview.json()
    assert preview_body["total_codes"] == 1
    assert preview_body["invalid_count"] == 0
    assert preview_body["groups"][0]["gtin"] == gtin14

    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "Wrapped pool", "product_ids": [product_id]}],
            ),
        },
        files=[("files", (filename, pdf_bytes, "application/pdf"))],
    )
    assert imp.status_code == 200, imp.text
    assert imp.json()["accepted_count"] == 1

    codes = await async_client.get(
        f"/operations/marking-codes/products/{product_id}/codes",
        headers=h,
    )
    assert codes.status_code == 200
    row = codes.json()[0]
    assert row["cis_code"].endswith(serial)
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


@pytest.mark.asyncio
async def test_label_artifact_tape_merges_pdfs_in_order(async_client: AsyncClient) -> None:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Tape Seller", "email": f"s-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201
    seller_id = seller.json()["id"]

    sku = f"SKU-TAPE-{uuid.uuid4().hex[:6]}"
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Tape product",
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
    cis_a = f"01{gtin14}21{'E' * 20}0001"
    cis_b = f"01{gtin14}21{'F' * 20}0002"
    pdf_bytes = _build_two_label_pdf(cis_a, cis_b)
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps([{"title": "Tape pool", "product_ids": [product_id]}]),
        },
        files=[("files", ("labels.pdf", pdf_bytes, "application/pdf"))],
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
    id_a = rows[0]["id"]
    id_b = rows[1]["id"]

    tape = await async_client.post(
        "/operations/marking-codes/label-artifact-tape",
        headers=h,
        json={"code_ids": [id_a, id_a, id_b]},
    )
    assert tape.status_code == 200, tape.text
    assert tape.headers["content-type"] == "application/pdf"
    merged = fitz.open(stream=tape.content, filetype="pdf")
    try:
        assert merged.page_count == 3
    finally:
        merged.close()


@pytest.mark.asyncio
async def test_label_artifact_tape_merges_outside_event_loop_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import marking_code_service, marking_label_artifact_service

    tenant_id = uuid.uuid4()
    loop_thread_id = threading.get_ident()
    merge_thread_ids: list[int] = []
    validation_thread_ids: list[int] = []

    class FakeSession:
        async def get(self, _model: object, _code_id: uuid.UUID) -> object:
            assert threading.get_ident() == loop_thread_id
            return SimpleNamespace(
                tenant_id=tenant_id,
                label_artifact_pdf=b"label-pdf",
                cis_code="cis",
            )

    def fake_merge(
        parts: list[bytes],
        page_width_mm: float | None,
        page_height_mm: float | None,
        *,
        cis_codes: list[str] | None = None,
    ) -> bytes:
        assert parts == [b"label-pdf"]
        assert page_width_mm == 60
        assert page_height_mm == 40
        assert cis_codes == ["cis"]
        merge_thread_ids.append(threading.get_ident())
        return b"merged-pdf"

    def validate(*_args: object) -> bool:
        validation_thread_ids.append(threading.get_ident())
        return True

    monkeypatch.setattr(marking_code_service, "is_printable_label_artifact", validate)
    monkeypatch.setattr(
        marking_label_artifact_service,
        "merge_label_artifact_pdfs_for_print",
        fake_merge,
    )

    result = await marking_code_service.build_label_artifact_tape_pdf(
        FakeSession(),  # type: ignore[arg-type]
        tenant_id,
        [uuid.uuid4()],
        60,
        40,
    )

    assert result == b"merged-pdf"
    assert merge_thread_ids and merge_thread_ids[0] != loop_thread_id
    assert validation_thread_ids == merge_thread_ids


def test_merge_label_artifact_pdfs_empty_raises() -> None:
    from app.services.marking_label_artifact_service import merge_label_artifact_pdfs

    with pytest.raises(ValueError, match="empty_parts"):
        merge_label_artifact_pdfs([])


def test_fit_label_artifact_pdf_to_page_sets_tall_page_size() -> None:
    from app.services.marking_label_artifact_service import fit_label_artifact_pdf_to_page

    src = fitz.open()
    src.new_page(width=170, height=113)
    src_bytes = bytes(src.tobytes())
    src.close()

    fitted_bytes = fit_label_artifact_pdf_to_page(src_bytes, 60, 80)
    fitted = fitz.open(stream=fitted_bytes, filetype="pdf")
    try:
        rect = fitted[0].rect
        assert abs(rect.width - 60 * 72 / 25.4) < 1.5
        assert abs(rect.height - 80 * 72 / 25.4) < 1.5
    finally:
        fitted.close()


@pytest.mark.parametrize(
    "cis",
    [
        "010463032168983521ABC123",
        "0104630321689835215TVsOggEdo6!!\x1d91ABCD\x1d92" + "x" * 20,
    ],
    ids=["short", "long-with-gs"],
)
def test_native_artifact_print_repairs_anisotropic_modules_and_preserves_cis(
    cis: str,
) -> None:
    from app.services.marking_label_artifact_service import fit_label_artifact_pdf_to_page

    stored = _build_stored_label_artifact(cis, distorted=True)

    # This is the deployed pre-hotfix behavior: uniform page fitting cannot
    # undo distortion already embedded inside the stored seller PDF.
    before = fit_label_artifact_pdf_to_page(stored, 58, 40)
    before_x, before_y, _ = _rendered_module_pitches(before, cis)
    assert before_x / before_y > 2

    # The real artifact-tape path has the canonical CIS and can surgically
    # replace only the distorted matrix before the same page fitting step.
    after = fit_label_artifact_pdf_to_page(stored, 58, 40, cis)
    after_x, after_y, bounds = _rendered_module_pitches(after, cis)
    assert abs(after_x - after_y) <= 1
    assert abs((bounds[2] - bounds[0]) - (bounds[3] - bounds[1])) <= 1.5
    _assert_rendered_quiet_zone(after, cis, min(after_x, after_y))

    repaired = fitz.open(stream=after, filetype="pdf")
    try:
        assert repaired.page_count == 1
        assert abs(repaired[0].rect.width - 58 * 72 / 25.4) < 1.5
        assert abs(repaired[0].rect.height - 40 * 72 / 25.4) < 1.5
        text = repaired[0].get_text("text")
        assert "HONEST" in text
        assert "GTIN 4630321689835" in text
        assert "crypto-tail-control" in text
    finally:
        repaired.close()


def test_native_artifact_tape_repairs_each_page_in_order() -> None:
    from app.services.marking_code_service import _validated_label_artifact_tape
    from app.services.marking_datamatrix_service import decode_datamatrix_codes_on_pdf_page

    cis_a = "0104630321689835215TVsOggEdo6!!\x1d91ABCD\x1d92" + "a" * 20
    cis_b = "0104630321689835215TVsOggEdo7!!\x1d91EFGH\x1d92" + "b" * 20
    tape = _validated_label_artifact_tape(
        [
            (_build_stored_label_artifact(cis_a, distorted=True), cis_a),
            (_build_stored_label_artifact(cis_b, distorted=True), cis_b),
        ],
        58,
        40,
    )

    doc = fitz.open(stream=tape, filetype="pdf")
    try:
        assert doc.page_count == 2
        assert [
            [item.value for item in decode_datamatrix_codes_on_pdf_page(page)]
            for page in doc
        ] == [[cis_a], [cis_b]]
    finally:
        doc.close()
    for cis in (cis_a, cis_b):
        pitch_x, pitch_y, _ = _rendered_module_pitches(tape, cis)
        assert abs(pitch_x - pitch_y) <= 1


def test_native_artifact_keeps_valid_rectangular_datamatrix_modules() -> None:
    from app.services.marking_label_artifact_service import fit_label_artifact_pdf_to_page

    cis = "0104630321689835215TVsOggEdo6!!\x1d91ABCD\x1d92" + "x" * 20
    stored = _build_stored_label_artifact(cis, distorted=False)
    fitted = fit_label_artifact_pdf_to_page(stored, 58, 40, cis)
    pitch_x, pitch_y, bounds = _rendered_module_pitches(fitted, cis)

    assert abs(pitch_x - pitch_y) <= 1
    assert (bounds[2] - bounds[0]) / (bounds[3] - bounds[1]) > 2


@pytest.mark.parametrize(
    ("width_mm", "height_mm"),
    [(58, 40), (60, 40), (60, 80), (70, 120)],
)
def test_native_artifact_repair_preserves_supported_page_sizes(
    width_mm: int,
    height_mm: int,
) -> None:
    from app.services.marking_label_artifact_service import fit_label_artifact_pdf_to_page

    cis = "0104630321689835215TVsOggEdo6!!\x1d91ABCD\x1d92" + "x" * 20
    stored = _build_stored_label_artifact(cis, distorted=True)
    fitted_bytes = fit_label_artifact_pdf_to_page(stored, width_mm, height_mm, cis)

    fitted = fitz.open(stream=fitted_bytes, filetype="pdf")
    try:
        assert fitted.page_count == 1
        assert abs(fitted[0].rect.width - width_mm * 72 / 25.4) < 1.5
        assert abs(fitted[0].rect.height - height_mm * 72 / 25.4) < 1.5
    finally:
        fitted.close()
    pitch_x, pitch_y, _ = _rendered_module_pitches(fitted_bytes, cis)
    assert abs(pitch_x - pitch_y) <= 1


@pytest.mark.parametrize(
    ("width_mm", "height_mm"),
    [
        (58, 40),
        (60, 40),
        (60, 80),
        (70, 120),
        (80, 60),
        (40, 58),
    ],
)
def test_fit_label_artifact_pdf_all_label_sizes(width_mm: int, height_mm: int) -> None:
    """Seller PDF 60x40mm → каждый размер наклейки даёт страницу нужного физ. размера."""
    from app.services.marking_label_artifact_service import fit_label_artifact_pdf_to_page

    src = fitz.open()
    src.new_page(width=170, height=113)
    src_bytes = bytes(src.tobytes())
    src.close()

    fitted_bytes = fit_label_artifact_pdf_to_page(src_bytes, float(width_mm), float(height_mm))
    fitted = fitz.open(stream=fitted_bytes, filetype="pdf")
    try:
        rect = fitted[0].rect
        assert abs(rect.width - width_mm * 72 / 25.4) < 1.5
        assert abs(rect.height - height_mm * 72 / 25.4) < 1.5
        pix = fitted[0].get_pixmap(matrix=fitz.Matrix(4, 4), alpha=False)
        assert pix.width > 100
        assert pix.height > 100
    finally:
        fitted.close()
