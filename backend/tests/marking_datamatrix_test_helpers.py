"""Real synthetic DataMatrix fixtures, using the encoder from 94c8e674."""

from __future__ import annotations

import fitz
import zxingcpp


def encode_datamatrix_png(value: str) -> bytes:
    barcode = zxingcpp.create_barcode(value.encode("utf-8"), format=zxingcpp.DataMatrix)
    image = zxingcpp.write_barcode_to_image(barcode, scale=8)
    height, width = image.shape
    pixmap = fitz.Pixmap(fitz.csGRAY, width, height, bytes(image), 0)
    return bytes(pixmap.tobytes("png"))


def build_datamatrix_pdf(
    values: list[str],
    *,
    caption: bool = True,
    columns: int | None = None,
) -> bytes:
    doc = fitz.open()
    try:
        columns = columns or len(values)
        page = doc.new_page(
            width=200 * columns, height=220 * ((len(values) + columns - 1) // columns)
        )
        for index, value in enumerate(values):
            left = index % columns * 200
            top = index // columns * 220
            if caption:
                page.insert_text((left + 10, top + 20), value.split("\x1d")[0], fontsize=6)
            page.insert_image(
                fitz.Rect(left + 20, top + 40, left + 180, top + 200),
                stream=encode_datamatrix_png(value),
            )
        return bytes(doc.tobytes())
    finally:
        doc.close()
