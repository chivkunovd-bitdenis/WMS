"""Regression contract for the PDF counterexample from review WMS-684/586."""

from __future__ import annotations

import fitz
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.products import ProductCreate
from app.db.session import SessionLocal
from app.models.inbound_intake import InboundIntakeLine
from app.models.product import Product
from tests.test_wms586_acceptance_act_contract import (
    BASE,
    assert_pdf_rows,
    download,
    pdf,
    seed,
    workbook,
)


async def _replace_first_product_name(request_id, name: str) -> None:
    async with SessionLocal() as session:
        line = (
            await session.scalars(
                select(InboundIntakeLine)
                .where(InboundIntakeLine.request_id == request_id)
                .order_by(InboundIntakeLine.id)
            )
        ).first()
        assert line is not None
        product = await session.get(Product, line.product_id)
        assert product is not None
        product.name = name
        await session.commit()


async def _replace_product_names(request_id, expected, names: list[str]) -> None:
    async with SessionLocal() as session:
        for index, name in enumerate(names):
            product = await session.scalar(
                select(Product)
                .join(InboundIntakeLine, InboundIntakeLine.product_id == Product.id)
                .where(
                    InboundIntakeLine.request_id == request_id,
                    Product.sku_code == expected[index][3],
                )
            )
            assert product is not None
            product.name = name
            expected[index][1] = name
        await session.commit()


async def _observe_pdf(async_client, headers, request_id):
    transport = ASGITransport(app=async_client._transport.app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as observer:
        return await observer.get(f"{BASE}/{request_id}/acceptance-act.pdf", headers=headers)


async def test_pdf_preserves_every_explicit_line_of_a_valid_product_name(async_client):
    """R3/R6-R7/R9/R14: PDF and Excel retain the same accepted item name."""
    name = "Худи\nРазмер XL\nЦвет чёрный\nЗимняя коллекция\nУтеплённый хлопок"
    headers, request_id, _ = await seed(async_client, [(10, 8)])
    await _replace_first_product_name(request_id, name)

    xlsx = workbook(await download(async_client, headers, request_id, "xlsx"))
    assert xlsx["B4"].value == name

    document = pdf(await download(async_client, headers, request_id, "pdf"))
    rendered = "\n".join(page.get_text() for page in document)
    positions = [rendered.index(line) for line in name.splitlines()]
    assert positions == sorted(positions), "PDF must retain the complete multi-line product name"


async def test_pdf_exports_valid_255_character_name_across_page_boundaries(async_client):
    """R9/R14: accepted multi-line product data cannot turn PDF export into a 500."""
    name = "\n".join(f"Х{index:02d}" for index in range(64))
    assert len(name) == 255
    assert ProductCreate(name=name, sku_code="000000").name == name

    headers, request_id, expected = await seed(async_client, [(10, 8)])
    await _replace_first_product_name(request_id, name)
    expected[0][1] = name

    xlsx = workbook(await download(async_client, headers, request_id, "xlsx"))
    assert xlsx["B4"].value == name

    response = await _observe_pdf(async_client, headers, request_id)
    assert response.status_code == 200, response.text
    document = pdf(response.content)
    rendered = "".join("".join(page.get_text().split()) for page in document)
    assert "".join(name.split()) in rendered
    assert_pdf_rows(document, expected)


async def test_paginated_valid_255_name_does_not_overlap_following_product(async_client):
    """R14: a continued name must end before the next product's glyphs begin."""
    name = "\n".join("Х" for _ in range(128))
    assert len(name) == 255
    assert ProductCreate(name=name, sku_code="000001").name == name
    headers, request_id, expected = await seed(async_client, [(5, 3), (6, 4), (4, 5)])
    await _replace_product_names(
        request_id, expected, ["Предыдущий товар", name, "Следующий товар"]
    )

    xlsx = workbook(await download(async_client, headers, request_id, "xlsx"))
    assert [row[1] for row in xlsx.iter_rows(min_row=4, max_row=6, values_only=True)] == [
        "Предыдущий товар", name, "Следующий товар",
    ]
    response = await _observe_pdf(async_client, headers, request_id)
    assert response.status_code == 200, response.text
    document = pdf(response.content)
    assert_pdf_rows(document, expected)

    chars = [
        char
        for block in document[-1].get_text("rawdict")["blocks"]
        for line in block.get("lines", [])
        for span in line["spans"]
        for char in span["chars"]
        if 48 <= char["bbox"][0] < 252
    ]
    last_name_char = next(char for char in reversed(chars) if char["c"] == "Х")
    following_name_char = next(char for char in chars if char["c"] == "С")
    intersection = fitz.Rect(last_name_char["bbox"]) & fitz.Rect(following_name_char["bbox"])
    assert intersection.is_empty, list(intersection)


async def test_valid_255_name_with_empty_lines_does_not_add_blank_pdf_pages(async_client):
    """R14: visible data may continue, but empty line fragments must not create pages."""
    name = "Х" + "\n" * 253 + "Я"
    assert len(name) == 255
    assert ProductCreate(name=name, sku_code="000001").name == name
    headers, request_id, expected = await seed(async_client, [(5, 3), (6, 4), (4, 5)])
    await _replace_product_names(
        request_id, expected, ["Предыдущий товар", name, "Следующий товар"]
    )

    xlsx = workbook(await download(async_client, headers, request_id, "xlsx"))
    assert xlsx["B5"].value == name
    response = await _observe_pdf(async_client, headers, request_id)
    assert response.status_code == 200, response.text
    document = fitz.open(stream=response.content, filetype="pdf")
    assert_pdf_rows(document, expected)
    empty_pages = [number for number, page in enumerate(document, 1) if not page.get_text().strip()]
    assert empty_pages == []
