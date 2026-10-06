"""Regression contract for the PDF counterexample from review WMS-684/586."""

from __future__ import annotations

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

    transport = ASGITransport(app=async_client._transport.app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as observer:
        response = await observer.get(f"{BASE}/{request_id}/acceptance-act.pdf", headers=headers)
    assert response.status_code == 200, response.text
    document = pdf(response.content)
    rendered = "".join("".join(page.get_text().split()) for page in document)
    assert "".join(name.split()) in rendered
    assert_pdf_rows(document, expected)
