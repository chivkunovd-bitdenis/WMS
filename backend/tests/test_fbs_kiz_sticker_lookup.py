# ruff: noqa: RUF002, RUF003
"""Скан стикера WB находит заказ по техническому коду с этикетки."""

from __future__ import annotations

import uuid

from app.models.fbs_order import FbsOrder
from app.services.fbs_kiz_service import _find_order_by_sticker, normalize_scanned_sticker
from app.services.fbs_sticker_code_service import (
    sticker_barcode_from_wb_row,
    sticker_code_from_wb_row,
)

# Реальный ответ WB, снятый с прода 20.08.2026
WB_ROW = {"partA": "5694425", "partB": "3074", "barcode": "*DUIkWJJF", "orderId": 5529353543}


def _order(**kw: object) -> FbsOrder:
    order = FbsOrder()
    order.id = uuid.uuid4()
    order.sticker_code = kw.get("sticker_code")
    order.sticker_barcode = kw.get("sticker_barcode")
    order.wb_barcode = kw.get("wb_barcode")
    return order


def test_wb_row_split_into_human_number_and_scanner_code() -> None:
    """Из ответа WB достаём оба значения: для глаз и для сканера."""
    assert sticker_code_from_wb_row(WB_ROW) == "5694425 3074"
    assert sticker_barcode_from_wb_row(WB_ROW) == "*DUIkWJJF"


def test_scan_finds_order_by_sticker_barcode() -> None:
    """Сканер отдаёт технический код — заказ должен найтись.

    Раньше поиск шёл только по человеческому номеру, и скан не находил ничего:
    оператор видел «Стикер не найден в этой поставке» на стикере из этой же поставки.
    """
    target = _order(sticker_code="5694425 3074", sticker_barcode="*DUIkWJJF")
    other = _order(sticker_code="5691530 4908", sticker_barcode="*DUBqocyI")

    scanned = normalize_scanned_sticker("*DUIkWJJF\n")
    assert _find_order_by_sticker([other, target], scanned) is target


def test_human_number_still_works_for_manual_entry() -> None:
    """Номер с этикетки, введённый руками, тоже должен находить заказ."""
    target = _order(sticker_code="5694425 3074", sticker_barcode="*DUIkWJJF")
    scanned = normalize_scanned_sticker("5694425 3074")
    assert _find_order_by_sticker([target], scanned) is target


def test_unknown_code_finds_nothing() -> None:
    target = _order(sticker_code="5694425 3074", sticker_barcode="*DUIkWJJF")
    assert _find_order_by_sticker([target], normalize_scanned_sticker("*ZZZZZZZZ")) is None
