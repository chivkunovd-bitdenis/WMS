"""WMS-586: «Акт приёмки» — Excel по завершённой приёмке: план, факт и расхождение.

Факт берётся тем же правилом, что и при проведении документа
(`_accepted_qty_for_line`: принятое количество строки), поэтому акт совпадает
с тем, что приёмка положила на склад. До завершения приёмки факта ещё нет —
акт не формируется.
"""
from __future__ import annotations

import io
import math
import re
import uuid
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from openpyxl import Workbook  # type: ignore[import-untyped]
from openpyxl.styles import Alignment, Font  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_intake import InboundIntakeRequest
from app.services.inbound_intake_service import (
    OPERATION_TYPE_RETURN,
    InboundIntakeError,
    _accepted_qty_for_line,
    get_request,
)

# Те же «приёмка закрыта», что и на экране (inboundReceivingHelpers):
# сортировка/проверена — приёмка завершена, done/posted — документ проведён.
_CLOSED_STATUSES = frozenset({"sorting", "verified", "done", "posted"})
_MOSCOW = ZoneInfo("Europe/Moscow")
_HEADERS = ("№", "Товар", "Артикул продавца", "SKU", "ШК", "План", "Факт", "Расхождение")


def _document_label(req: InboundIntakeRequest) -> str:
    return "Возврат" if req.operation_type == OPERATION_TYPE_RETURN else "Приёмка"


def _document_number(req: InboundIntakeRequest) -> str:
    return (req.display_number or req.document_number or str(req.id)).strip()


def _document_date(req: InboundIntakeRequest) -> str:
    created: datetime = req.created_at
    # SQLite test/local storage returns a naive value even for DateTime(timezone=True).
    # Application timestamps are UTC, so never let the host timezone move a document
    # across the Moscow calendar boundary.
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return created.astimezone(_MOSCOW).strftime("%d.%m.%Y")


def acceptance_act_title(req: InboundIntakeRequest) -> str:
    # Владелец 29.09.2026: без повествовательных шапок — только номер и дата.
    return f"{_document_label(req)} {_document_number(req)} от {_document_date(req)}"


def acceptance_act_filename(req: InboundIntakeRequest) -> str:
    return acceptance_act_filename_for_format(req, "xlsx")


def acceptance_act_filename_for_format(req: InboundIntakeRequest, file_format: str) -> str:
    number = re.sub(r"[^\w\-]+", "", _document_number(req)) or "doc"
    return f"Акт приёмки {number} от {_document_date(req)}.{file_format}"


def _text(value: str | None) -> str:
    return (value or "").strip()


async def build_acceptance_act_workbook(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    seller_product_owner_id: uuid.UUID | None = None,
) -> tuple[InboundIntakeRequest, bytes]:
    req = await get_request(
        session, tenant_id, request_id, seller_product_owner_id=seller_product_owner_id
    )
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status not in _CLOSED_STATUSES:
        raise InboundIntakeError("reception_not_closed")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Акт приёмки"
    bold = Font(bold=True)

    sheet.append([acceptance_act_title(req)])
    sheet["A1"].font = Font(bold=True, size=14)
    sheet.append([])
    sheet.append(list(_HEADERS))
    header_row = sheet.max_row
    for cell in sheet[header_row]:
        cell.font = bold
        cell.alignment = Alignment(vertical="center", wrap_text=True)

    total_plan = total_fact = 0
    for index, line in enumerate(req.lines, start=1):
        product = line.product
        plan = int(line.expected_qty or 0)
        fact = int(_accepted_qty_for_line(line))
        total_plan += plan
        total_fact += fact
        row = [
            index,
            _text(product.name if product else None),
            _text(product.wb_vendor_code if product else None),
            _text(product.sku_code if product else None),
            _text(product.wb_barcode if product else None),
            plan,
            fact,
            fact - plan,
        ]
        sheet.append(row)
        # Текстовые ячейки — строго текст: «=…» в названии не должно стать формулой,
        # а ШК из цифр — числом с потерей ведущих нулей.
        for column in range(2, 6):
            sheet.cell(row=sheet.max_row, column=column).data_type = "s"
        diff_cell = sheet.cell(row=sheet.max_row, column=8)
        diff_cell.number_format = "+0;-0;0"
        if fact != plan:
            diff_cell.font = Font(bold=True, color="B00020")

    sheet.append(["", "Итого", "", "", "", total_plan, total_fact, total_fact - total_plan])
    total_row = sheet.max_row
    for cell in sheet[total_row]:
        cell.font = bold
    sheet.cell(row=total_row, column=8).number_format = "+0;-0;0"

    for letter, width in zip("ABCDEFGH", (5, 48, 22, 18, 18, 9, 9, 13), strict=True):
        sheet.column_dimensions[letter].width = width
    sheet.freeze_panes = sheet.cell(row=header_row + 1, column=1)

    buffer = io.BytesIO()
    workbook.save(buffer)
    return req, buffer.getvalue()


def _pdf_row_height(values: tuple[str, str, str, str]) -> float:
    """Reserve enough vertical space for wrapped identifiers before drawing a row."""
    character_widths = (43, 22, 17, 19)
    lines = max(
        math.ceil(len(value) / width) if value else 1
        for value, width in zip(values, character_widths, strict=True)
    )
    return max(15.0, lines * 9.5 + 5.0)


def _pdf_textbox(
    page: Any,
    rect: object,
    text: str,
    *,
    size: float,
    color: tuple[float, float, float] | None = None,
    align: int = 0,
) -> None:
    """Write Cyrillic text with the bundled CJK font, shrinking only when necessary."""
    import fitz

    box = fitz.Rect(rect)
    for font_size in (size, 7.0, 6.0, 5.0):
        shape = page.new_shape()
        if (
            shape.insert_textbox(
                box, text, fontsize=font_size, fontname="wms", color=color, align=align
            )
            >= 0
        ):
            shape.commit()
            return
    # A row's height is deliberately calculated with a margin. This fallback is
    # retained for unusual user text rather than silently omitting it.
    page.insert_textbox(box, text, fontsize=5.0, fontname="wms", color=color, align=align)


async def build_acceptance_act_pdf(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    seller_product_owner_id: uuid.UUID | None = None,
) -> tuple[InboundIntakeRequest, bytes]:
    """Render the same plan/fact/discrepancy act as the Excel export into PDF."""
    import fitz

    req = await get_request(
        session, tenant_id, request_id, seller_product_owner_id=seller_product_owner_id
    )
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status not in _CLOSED_STATUSES:
        raise InboundIntakeError("reception_not_closed")

    rows: list[tuple[int, str, str, str, str, int, int, int]] = []
    total_plan = total_fact = 0
    for index, line in enumerate(req.lines, start=1):
        product = line.product
        plan = int(line.expected_qty or 0)
        fact = int(_accepted_qty_for_line(line))
        total_plan += plan
        total_fact += fact
        rows.append((
            index,
            _text(product.name if product else None),
            _text(product.wb_vendor_code if product else None),
            _text(product.sku_code if product else None),
            _text(product.wb_barcode if product else None),
            plan,
            fact,
            fact - plan,
        ))

    page_width, page_height = 842.0, 595.0  # A4 landscape in points.
    left, right, top, bottom = 24.0, 24.0, 24.0, 28.0
    widths = (24.0, 204.0, 104.0, 78.0, 88.0, 48.0, 48.0, 80.0)
    columns = [left]
    for width in widths:
        columns.append(columns[-1] + width)

    document = fitz.open()

    def start_page() -> tuple[Any, float]:
        page = document.new_page(width=page_width, height=page_height)
        page.insert_font(fontname="wms", fontbuffer=fitz.Font("cjk").buffer)
        _pdf_textbox(
            page,
            fitz.Rect(left, top, page_width - right, top + 20),
            acceptance_act_title(req),
            size=14.0,
        )
        header_top = top + 28
        for index, header in enumerate(_HEADERS):
            _pdf_textbox(
                page,
                fitz.Rect(columns[index] + 2, header_top, columns[index + 1] - 2, header_top + 18),
                header,
                size=7.0,
                align=1,
            )
        page.draw_line(
            (left, header_top + 20),
            (page_width - right, header_top + 20),
            color=(0.55, 0.55, 0.55),
            width=0.5,
        )
        return page, header_top + 24

    page, y = start_page()
    for index, name, vendor, sku, barcode, plan, fact, difference in rows:
        row_height = _pdf_row_height((name, vendor, sku, barcode))
        if y + row_height + 24 > page_height - bottom:
            page, y = start_page()
        fields = (
            str(index), name, vendor, sku, barcode, str(plan), str(fact),
            f"{difference:+d}" if difference else "0",
        )
        for column, value in enumerate(fields):
            color = (176 / 255, 0.0, 32 / 255) if column == 7 and difference else None
            _pdf_textbox(
                page,
                fitz.Rect(columns[column] + 2, y + 2, columns[column + 1] - 2, y + row_height - 1),
                value,
                size=7.5,
                color=color,
                align=1 if column in {0, 5, 6, 7} else 0,
            )
        page.draw_line(
            (left, y + row_height),
            (page_width - right, y + row_height),
            color=(0.8, 0.8, 0.8),
            width=0.3,
        )
        y += row_height

    if y + 24 > page_height - bottom:
        page, y = start_page()
    totals = (
        "", "Итого", "", "", "", str(total_plan), str(total_fact),
        f"{total_fact - total_plan:+d}" if total_fact != total_plan else "0",
    )
    for column, value in enumerate(totals):
        _pdf_textbox(
            page,
            fitz.Rect(columns[column] + 2, y + 2, columns[column + 1] - 2, y + 19),
            value,
            size=8.0,
            align=1 if column in {0, 5, 6, 7} else 0,
        )
    document.subset_fonts()
    return req, bytes(document.tobytes(garbage=4, deflate=True, no_new_id=True))
