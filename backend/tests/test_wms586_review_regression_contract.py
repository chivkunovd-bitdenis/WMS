"""Regression contract for the PDF counterexample from review WMS-684/586."""

from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.inbound_intake import InboundIntakeLine
from app.models.product import Product
from tests.test_wms586_acceptance_act_contract import download, pdf, seed, workbook


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
