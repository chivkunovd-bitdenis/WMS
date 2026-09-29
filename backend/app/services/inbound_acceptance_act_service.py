"""WMS-586: «Акт приёмки» — Excel по завершённой приёмке: план, факт и расхождение.

Факт берётся тем же правилом, что и при проведении документа
(`_accepted_qty_for_line`: принятое количество строки), поэтому акт совпадает
с тем, что приёмка положила на склад. До завершения приёмки факта ещё нет —
акт не формируется.
"""
from __future__ import annotations

import io
import re
import uuid
from datetime import datetime
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
    return created.astimezone(_MOSCOW).strftime("%d.%m.%Y")


def acceptance_act_title(req: InboundIntakeRequest) -> str:
    # Владелец 29.09.2026: без повествовательных шапок — только номер и дата.
    return f"{_document_label(req)} {_document_number(req)} от {_document_date(req)}"


def acceptance_act_filename(req: InboundIntakeRequest) -> str:
    number = re.sub(r"[^\w\-]+", "", _document_number(req)) or "doc"
    return f"Акт приёмки {number} от {_document_date(req)}.xlsx"


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
