"""Narrow independent review evidence; real API on isolated pytest SQLite only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import fitz
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.products import ProductCreate
from app.db.session import SessionLocal
from app.models.inbound_intake import InboundIntakeLine
from app.models.product import Product
from tests.test_wms586_acceptance_act_contract import BASE, assert_pdf_rows, pdf, seed, workbook

OUT = Path(__file__).resolve().parent
COLUMNS = (24, 48, 252, 356, 434, 522, 570, 618, 698)


def compact(text):
    return "".join(text.split())


@pytest.mark.asyncio
async def test_paginated_names_keep_all_text_and_numeric_fields_once(async_client):
    results = []
    transport = ASGITransport(app=async_client._transport.app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as observer:
        for count in (64, 128):
            name = "\n".join(f"Х{i:02d}" for i in range(64)) if count == 64 else "\n".join("Х" for _ in range(128))
            assert len(name) == 255
            assert ProductCreate(name=name, sku_code="000001").name == name
            headers, request_id, expected = await seed(async_client, [(5, 3), (6, 4), (4, 5)])
            names = ["Предыдущий товар", name, "Следующий товар"]
            async with SessionLocal() as session:
                for i, value in enumerate(names):
                    product = await session.scalar(
                        select(Product).join(InboundIntakeLine, InboundIntakeLine.product_id == Product.id)
                        .where(InboundIntakeLine.request_id == request_id, Product.sku_code == expected[i][3])
                    )
                    assert product is not None
                    product.name = value
                    expected[i][1] = value
                await session.commit()

            responses = {}
            for fmt in ("xlsx", "pdf"):
                response = await observer.get(f"{BASE}/{request_id}/acceptance-act.{fmt}", headers=headers)
                assert response.status_code == 200, (count, fmt, response.text)
                content = response.content
                (OUT / f"pagination-{count}.{fmt}").write_bytes(content)
                responses[fmt] = response
            sheet = workbook(responses["xlsx"].content)
            assert [list(row) for row in sheet.iter_rows(min_row=4, max_row=6, values_only=True)] == expected
            assert [cell.value for cell in sheet[7]][5:] == [15, 12, -3]
            document = pdf(responses["pdf"].content)
            assert_pdf_rows(document, expected)
            assert "Итого" in document[-1].get_text()

            column_texts = [
                "".join(compact(page.get_text(clip=fitz.Rect(COLUMNS[column], 0, COLUMNS[column+1], page.rect.height))) for page in document)
                for column in range(8)
            ]
            field_counts = []
            for row in expected:
                counts = [column_texts[column].count(compact(str(row[column]))) for column in (1, 2, 3, 4)]
                assert counts == [1, 1, 1, 1], (row[0], counts)
                field_counts.append({"row": row[0], "name_vendor_sku_barcode_counts": counts})
            if count == 64:
                assert all(column_texts[1].count(f"Х{i:02d}") == 1 for i in range(64))
            else:
                assert column_texts[1].count("Х") == 128

            numeric_columns = []
            for column in (0, 5, 6, 7):
                words = [
                    word[4] for page in document
                    for word in page.get_text("words", clip=fitz.Rect(COLUMNS[column], 0, COLUMNS[column+1], page.rect.height))
                    if word[4].lstrip("+-").isdigit()
                ]
                expected_numbers = [str(row[column]) for row in expected]
                if column == 7:
                    expected_numbers = [f"{row[column]:+d}" if row[column] else "0" for row in expected]
                if column != 0:
                    expected_numbers.append("-3" if column == 7 else str(sum(row[column] for row in expected)))
                assert words == expected_numbers, (column, words, expected_numbers)
                numeric_columns.append({"column": column, "observed": words, "expected": expected_numbers})

            pages = []
            for n, page in enumerate(document, 1):
                text = page.get_text()
                body_start = 76 if "Приёмка" in text else 0
                body_words = [word for word in page.get_text("words") if word[1] >= body_start]
                assert body_words, (n, "header-only or empty page")
                outside = [word[4] for word in page.get_text("words") if not page.rect.contains(fitz.Rect(word[:4]))]
                assert not outside, (n, outside)
                name_words = page.get_text("words", clip=fitz.Rect(48, 0, 252, page.rect.height))
                fragment_tokens = [word[4] for word in name_words if word[4].startswith("Х")]
                page.get_pixmap(dpi=110).save(OUT / f"pagination-{count}-page-{n}.png")
                pages.append({"page": n, "rect": list(page.rect), "body_word_count": len(body_words),
                              "outside_words": outside, "fragment_line_count": len(fragment_tokens),
                              "fragment_first": fragment_tokens[0] if fragment_tokens else None,
                              "fragment_last": fragment_tokens[-1] if fragment_tokens else None})
            assert sum(page["fragment_line_count"] for page in pages) == count
            assert sum(page.get_text().count("Итого") for page in document) == 1
            results.append({"lines": count, "name_length": len(name), "product_model_accepts": True,
                            "status_pdf": responses["pdf"].status_code, "status_xlsx": responses["xlsx"].status_code,
                            "pages": pages, "field_counts": field_counts, "numeric_columns": numeric_columns,
                            "totals": [15, 12, -3], "totals_count": 1, "source_rows": expected,
                            "pdf_sha256": hashlib.sha256(responses["pdf"].content).hexdigest(),
                            "xlsx_sha256": hashlib.sha256(responses["xlsx"].content).hexdigest()})
    (OUT / "pagination-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")


@pytest.mark.asyncio
async def test_empty_line_fragments_do_not_emit_blank_pdf_pages(async_client):
    """Same permitted 255-character boundary, with consecutive empty lines."""
    name = "Х" + "\n" * 253 + "Я"
    assert len(name) == 255
    assert ProductCreate(name=name, sku_code="000001").name == name
    headers, request_id, expected = await seed(async_client, [(5, 3), (6, 4), (4, 5)])
    expected[1][1] = name
    async with SessionLocal() as session:
        product = await session.scalar(
            select(Product).join(InboundIntakeLine, InboundIntakeLine.product_id == Product.id)
            .where(InboundIntakeLine.request_id == request_id, Product.sku_code == expected[1][3])
        )
        assert product is not None
        product.name = name
        await session.commit()
    transport = ASGITransport(app=async_client._transport.app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as observer:
        xlsx = await observer.get(f"{BASE}/{request_id}/acceptance-act.xlsx", headers=headers)
        response = await observer.get(f"{BASE}/{request_id}/acceptance-act.pdf", headers=headers)
    assert xlsx.status_code == response.status_code == 200
    assert workbook(xlsx.content)["B5"].value == name
    (OUT / "pagination-empty-lines.xlsx").write_bytes(xlsx.content)
    (OUT / "pagination-empty-lines.pdf").write_bytes(response.content)
    document = fitz.open(stream=response.content, filetype="pdf")
    assert_pdf_rows(document, expected)
    empties = [n for n, page in enumerate(document, 1) if not page.get_text().strip()]
    (OUT / "empty-line-results.json").write_text(json.dumps({
        "name": name, "name_length": len(name), "lines": len(name.splitlines()),
        "product_model_accepts": True, "status_pdf": response.status_code,
        "status_xlsx": xlsx.status_code, "pages": len(document),
        "empty_pages": empties, "empty_page_drawing_counts": [len(document[n-1].get_drawings()) for n in empties],
        "all_text_and_quantities_preserved": True,
    }, ensure_ascii=False, indent=2) + "\n")
    for n in [1, 2, *empties, len(document)]:
        document[n-1].get_pixmap(dpi=80).save(OUT / f"pagination-empty-lines-page-{n}.png")
    assert not empties, f"permitted 255-character name generated blank PDF pages: {empties}"
