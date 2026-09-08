"""Decode actual DataMatrix payloads and their PDF page coordinates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

_DEFAULT_DPI = 600


@dataclass(frozen=True)
class DecodedDataMatrix:
    """Decoded bytes as text, preserving GS, with bounds in PDF points."""

    value: str
    page_rect: tuple[float, float, float, float]


def decode_datamatrix_codes_on_pdf_page(
    page: object,
    dpi: int = _DEFAULT_DPI,
) -> list[DecodedDataMatrix]:
    """Render a PDF page and decode its DataMatrix symbols (from 94c8e674)."""
    try:
        import zxingcpp
    except ImportError as exc:
        raise RuntimeError("datamatrix_support_unavailable") from exc
    import fitz  # pymupdf

    pg = cast(fitz.Page, page)
    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)
    pixmap = pg.get_pixmap(matrix=matrix, alpha=False)
    image_format = zxingcpp.ImageFormat.RGB if pixmap.n >= 3 else zxingcpp.ImageFormat.Lum
    # ImageView does not own its buffer. PyMuPDF's samples returns a bytes copy,
    # which must stay alive until read_barcodes finishes using its native pointer.
    samples = pixmap.samples
    view = zxingcpp.ImageView(samples, pixmap.width, pixmap.height, image_format)
    formats = zxingcpp.BarcodeFormats(zxingcpp.DataMatrix)
    results = zxingcpp.read_barcodes(view, formats=formats)

    decoded: list[DecodedDataMatrix] = []
    for result in results:
        if not result.valid:
            continue
        # The text accessor can render GS as a visible placeholder; use actual bytes.
        try:
            value = result.bytes.decode("utf-8")
        except UnicodeDecodeError:
            value = result.bytes.decode("latin-1")
        if not value:
            continue
        position = result.position
        xs = (
            position.top_left.x,
            position.top_right.x,
            position.bottom_right.x,
            position.bottom_left.x,
        )
        ys = (
            position.top_left.y,
            position.top_right.y,
            position.bottom_right.y,
            position.bottom_left.y,
        )
        page_rect = (
            min(xs) / scale,
            min(ys) / scale,
            max(xs) / scale,
            max(ys) / scale,
        )
        decoded.append(DecodedDataMatrix(value=value, page_rect=page_rect))
    return decoded
