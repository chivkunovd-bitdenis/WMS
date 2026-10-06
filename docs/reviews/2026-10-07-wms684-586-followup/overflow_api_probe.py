"""Review evidence only: real API, isolated pytest SQLite, no external actions."""
from __future__ import annotations

import json
from pathlib import Path

import fitz
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.products import ProductCreate
from app.services.inbound_acceptance_act_service import _pdf_row_height
from tests.test_wms586_acceptance_act_contract import BASE, seed, workbook
from tests.test_wms586_review_regression_contract import _replace_first_product_name

OUT = Path(__file__).resolve().parent


@pytest.mark.asyncio
async def test_pdf_retains_supported_names_when_the_row_overflows(async_client):
    cases = [
        ("multiline-original", "Худи\nРазмер XL\nЦвет чёрный\nЗимняя коллекция\nУтеплённый хлопок"),
        ("wide-255", "Ш" * 250 + "Товар"),
        ("multiline-255", "\n".join(f"Х{i:02d}" for i in range(64))),
    ]
    results = []
    # Use the same application and session override, but observe its real HTTP 500
    # instead of having the ASGI test transport re-raise the server exception.
    transport = ASGITransport(app=async_client._transport.app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as observer:
        for label, name in cases:
            validated = ProductCreate(name=name, sku_code="000000")
            assert validated.name == name
            headers, request_id, _ = await seed(async_client, [(10, 8)])
            await _replace_first_product_name(request_id, name)
            xlsx = await observer.get(f"{BASE}/{request_id}/acceptance-act.xlsx", headers=headers)
            assert xlsx.status_code == 200
            assert workbook(xlsx.content)["B4"].value == name
            (OUT / f"{label}.xlsx").write_bytes(xlsx.content)
            response = await observer.get(f"{BASE}/{request_id}/acceptance-act.pdf", headers=headers)
            result = {
                "case": label, "name": name, "name_length": len(name),
                "explicit_lines": len(name.splitlines()), "product_model_accepts": True,
                "initial_row_height": _pdf_row_height((name, "000АРТ-000", "000000", "0460000000000")),
                "xlsx_status": xlsx.status_code, "xlsx_retains_name": True,
                "pdf_status": response.status_code,
                "pdf_content_type": response.headers.get("content-type"),
            }
            if response.status_code == 200:
                (OUT / f"{label}.pdf").write_bytes(response.content)
                document = fitz.open(stream=response.content, filetype="pdf")
                normalized = "".join("".join(page.get_text().split()) for page in document)
                result["pdf_retains_name"] = "".join(name.split()) in normalized
                result["page_count"] = len(document)
                result["empty_pages"] = [n for n, page in enumerate(document, 1) if not page.get_text().strip()]
                result["outside_page_words"] = [
                    {"page": n, "word": word[4]} for n, page in enumerate(document, 1)
                    for word in page.get_text("words") if not page.rect.contains(fitz.Rect(word[:4]))
                ]
                document[0].get_pixmap(dpi=110).save(OUT / f"{label}.png")
            else:
                result["pdf_error_body"] = response.text
            results.append(result)
    (OUT / "overflow-api-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    assert all(case["pdf_status"] == 200 and case.get("pdf_retains_name") for case in results), results
