from __future__ import annotations

from typing import cast


def pdf_bytes_to_png(pdf_bytes: bytes, dpi: int = 300) -> bytes:
    try:
        import fitz  # pymupdf
    except ImportError as exc:
        raise RuntimeError("pdf_support_unavailable") from exc
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if doc.page_count < 1:
            raise ValueError("empty_pdf")
        page = doc[0]
        scale = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return cast(bytes, pix.tobytes("png"))
    finally:
        doc.close()
