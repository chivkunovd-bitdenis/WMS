"""BOX-SVC-01: xlsx box import parser."""

from __future__ import annotations

import io
import uuid

import pytest
from openpyxl import Workbook  # type: ignore[import-untyped]

from app.services.box_import_service import (
    BoxImportError,
    ProductCatalogRow,
    parse_box_import_xlsx,
)


def _xlsx_bytes(rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _catalog(
    *,
    product_id: uuid.UUID | None = None,
    sku: str = "SKU-1",
    barcode: str = "2047892455639",
) -> list[ProductCatalogRow]:
    pid = product_id or uuid.uuid4()
    return [
        ProductCatalogRow(
            product_id=pid,
            sku_code=sku,
            product_name="Test product",
            wb_primary_barcode=barcode,
            wb_barcodes=(barcode,),
        )
    ]


def test_parse_valid_file_groups_boxes_and_merges_duplicates() -> None:
    content = _xlsx_bytes(
        [
            ["Штрих-код", "Кол-во", "Адрес"],
            ["2047892455639", 2, "1"],
            ["2047892455639", 1, "1"],
            ["2047892573616", 1, "2"],
        ]
    )
    cat = _catalog(barcode="2047892455639")
    cat.append(
        ProductCatalogRow(
            product_id=uuid.uuid4(),
            sku_code="SKU-2",
            product_name="Second",
            wb_primary_barcode="2047892573616",
            wb_barcodes=("2047892573616",),
        )
    )
    result = parse_box_import_xlsx(content, filename="boxes.xlsx", catalog=cat)
    assert result.summary.boxes_count == 2
    assert result.summary.total_units == 4
    box1 = next(b for b in result.boxes if b.address == "1")
    assert box1.lines[0].quantity == 3
    assert result.errors == ()


def test_missing_column_raises() -> None:
    content = _xlsx_bytes([["Штрих-код", "Кол-во"], ["2047892455639", 1]])
    with pytest.raises(BoxImportError) as exc:
        parse_box_import_xlsx(content, filename="bad.xlsx", catalog=_catalog())
    assert exc.value.code == "missing_column"


def test_unsupported_file_type() -> None:
    with pytest.raises(BoxImportError) as exc:
        parse_box_import_xlsx(b"not-xlsx", filename="file.csv", catalog=_catalog())
    assert exc.value.code == "unsupported_file_type"


def test_unknown_barcode_in_errors() -> None:
    content = _xlsx_bytes(
        [
            ["Штрих-код", "Кол-во", "Адрес"],
            ["9999999999999", 2, "1"],
            ["2047892455639", 1, "1"],
        ]
    )
    result = parse_box_import_xlsx(content, filename="mix.xlsx", catalog=_catalog())
    assert any(e.code == "barcode_not_found" for e in result.errors)
    assert result.summary.boxes_count == 1
    assert len(result.boxes[0].lines) == 2


def test_fractional_quantity_row_error() -> None:
    content = _xlsx_bytes(
        [
            ["Штрих-код", "Кол-во", "Адрес"],
            ["2047892455639", 1.5, "1"],
        ]
    )
    result = parse_box_import_xlsx(content, filename="frac.xlsx", catalog=_catalog())
    assert any(e.code == "invalid_quantity" for e in result.errors)
