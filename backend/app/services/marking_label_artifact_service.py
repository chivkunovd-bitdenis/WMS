from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    import fitz


@dataclass(frozen=True)
class ExtractedLabelArtifact:
    cis: str
    gtin: str
    label_pdf: bytes
    source_page_index: int


def pdf_bytes_to_png(pdf_bytes: bytes, dpi: int = 600) -> bytes:
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
        matrix = fitz.Matrix(scale, scale)
        clip = _content_clip_rect(page)
        if clip is not None:
            pix = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
        else:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
        return cast(bytes, pix.tobytes("png"))
    finally:
        doc.close()


def merge_label_artifact_pdfs(parts: list[bytes]) -> bytes:
    """Склеивает одностраничные PDF-этикетки селлера в одну ленту для печати."""
    if not parts:
        raise ValueError("empty_parts")
    import fitz  # pymupdf

    out = fitz.open()
    try:
        for part in parts:
            src = fitz.open(stream=part, filetype="pdf")
            try:
                out.insert_pdf(src)
            finally:
                src.close()
        return cast(bytes, out.tobytes())
    finally:
        out.close()


def _mm_to_pt(mm: float) -> float:
    return mm * 72.0 / 25.4


def fit_label_artifact_pdf_to_page(
    pdf_bytes: bytes,
    page_width_mm: float,
    page_height_mm: float,
) -> bytes:
    """Вписывает PDF селлера (обычно 60x40 альбом) на страницу выбранного размера наклейки."""
    import fitz  # pymupdf

    if page_width_mm <= 0 or page_height_mm <= 0:
        raise ValueError("invalid_page_size")

    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if src.page_count < 1:
            raise ValueError("empty_pdf")
        src_page = src[0]
        src_rect = src_page.rect
        page_w_pt = _mm_to_pt(page_width_mm)
        page_h_pt = _mm_to_pt(page_height_mm)

        src_landscape = src_rect.width > src_rect.height * 1.05
        target_tall = page_height_mm / page_width_mm >= 1.2
        rotate = 90 if target_tall and src_landscape else 0

        if rotate in (90, 270):
            content_w = src_rect.height
            content_h = src_rect.width
        else:
            content_w = src_rect.width
            content_h = src_rect.height

        scale = min(page_w_pt / content_w, page_h_pt / content_h)
        draw_w = content_w * scale
        draw_h = content_h * scale
        x0 = (page_w_pt - draw_w) / 2
        y0 = (page_h_pt - draw_h) / 2
        target = fitz.Rect(x0, y0, x0 + draw_w, y0 + draw_h)

        out = fitz.open()
        try:
            page = out.new_page(width=page_w_pt, height=page_h_pt)
            page.show_pdf_page(target, src, 0, rotate=rotate)
            return cast(bytes, out.tobytes())
        finally:
            out.close()
    finally:
        src.close()


def merge_label_artifact_pdfs_for_print(
    parts: list[bytes],
    page_width_mm: float | None = None,
    page_height_mm: float | None = None,
) -> bytes:
    if page_width_mm is not None and page_height_mm is not None:
        fitted = [
            fit_label_artifact_pdf_to_page(part, page_width_mm, page_height_mm) for part in parts
        ]
        return merge_label_artifact_pdfs(fitted)
    return merge_label_artifact_pdfs(parts)


def _content_clip_rect(page: object) -> object | None:
    import fitz  # pymupdf

    pg = cast(fitz.Page, page)
    page_rect = pg.rect
    clip = fitz.Rect(page_rect)
    found = False
    for block in pg.get_text("blocks"):
        clip |= fitz.Rect(block[:4])
        found = True
    for drawing in pg.get_drawings():
        rect = drawing.get("rect")
        if rect is None:
            continue
        clip |= fitz.Rect(rect)
        found = True
    if not found:
        return None
    if clip.get_area() >= page_rect.get_area() * 0.98:
        return None
    pad = max(2.0, min(page_rect.width, page_rect.height) * 0.01)
    return cast(
        object,
        fitz.Rect(
            max(page_rect.x0, clip.x0 - pad),
            max(page_rect.y0, clip.y0 - pad),
            min(page_rect.x1, clip.x1 + pad),
            min(page_rect.y1, clip.y1 + pad),
        ),
    )


def crop_pdf_page_to_single_label_pdf(doc: object, page_index: int, rect: object) -> bytes:
    import fitz  # pymupdf

    src = cast(fitz.Document, doc)
    clip = cast(fitz.Rect, rect)
    out = fitz.open()
    try:
        page = out.new_page(width=clip.width, height=clip.height)
        page.show_pdf_page(page.rect, src, page_index, clip=clip)
        return cast(bytes, out.tobytes())
    finally:
        out.close()


def _cis_helpers() -> tuple[
    re.Pattern[str],
    Callable[[str], str | None],
    Callable[[str], str | None],
]:
    from app.services.marking_code_service import (
        _CIS_CANDIDATE_RE,
        extract_gtin_from_cis,
        normalize_cis,
    )

    return _CIS_CANDIDATE_RE, normalize_cis, extract_gtin_from_cis


def _find_cis_boxes_on_page(page: object) -> list[tuple[str, object]]:
    import fitz  # pymupdf

    cis_re, normalize_cis, _ = _cis_helpers()
    pg = cast(fitz.Page, page)
    found: list[tuple[str, fitz.Rect]] = []
    seen: set[str] = set()
    page_dict = pg.get_text("dict")
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            line_text = "".join(str(span.get("text", "")) for span in spans)
            if not cis_re.search(line_text):
                continue
            for match in cis_re.finditer(line_text):
                cis = normalize_cis(match.group(0))
                if cis is None or cis in seen:
                    continue
                seen.add(cis)
                line_bbox = fitz.Rect(line["bbox"])
                span_rects = [fitz.Rect(span["bbox"]) for span in spans if span.get("bbox")]
                if span_rects:
                    content_rect = span_rects[0]
                    for rect in span_rects[1:]:
                        content_rect |= rect
                    found.append((cis, content_rect | line_bbox))
                else:
                    found.append((cis, line_bbox))
    return found


def _drawing_rects(page: object) -> list[object]:
    import fitz  # pymupdf

    pg = cast(fitz.Page, page)
    rects: list[fitz.Rect] = []
    for drawing in pg.get_drawings():
        rect = drawing.get("rect")
        if rect is not None:
            candidate = fitz.Rect(rect)
            if candidate.width > 1 and candidate.height > 1:
                rects.append(candidate)
    return rects


def _rect_contains(outer: object, inner: object) -> bool:
    import fitz  # pymupdf

    o = cast(fitz.Rect, outer)
    i = cast(fitz.Rect, inner)
    return bool(
        o.x0 <= i.x0 + 0.5
        and o.y0 <= i.y0 + 0.5
        and o.x1 >= i.x1 - 0.5
        and o.y1 >= i.y1 - 0.5
    )


def _frame_rect_for_cis(cis_bbox: object, frames: list[object]) -> object | None:
    import fitz  # pymupdf

    bbox = cast(fitz.Rect, cis_bbox)
    candidates: list[fitz.Rect] = []
    for frame in frames:
        rect = cast(fitz.Rect, frame)
        if not _rect_contains(rect, bbox):
            continue
        if rect.get_area() <= bbox.get_area() * 1.02:
            continue
        candidates.append(rect)
    if not candidates:
        return None
    best = min(candidates, key=lambda rect: float(rect.get_area()))
    return cast(object | None, best)


def _content_rect_for_page(page: object) -> object:
    import fitz  # pymupdf

    pg = cast(fitz.Page, page)
    blocks = pg.get_text("blocks")
    if not blocks:
        return pg.rect
    rect = fitz.Rect(blocks[0][:4])
    for block in blocks[1:]:
        rect |= fitz.Rect(block[:4])
    return rect | pg.rect


def _fallback_label_rect(
    cis_bbox: object,
    cis_boxes: list[tuple[str, object]],
    page_rect: object,
    content_rect: object,
) -> object:
    import fitz  # pymupdf

    bbox = cast(fitz.Rect, cis_bbox)
    page = cast(fitz.Rect, page_rect)
    content = cast(fitz.Rect, content_rect)
    ordered = sorted(
        cis_boxes,
        key=lambda item: (cast(fitz.Rect, item[1]).y0, cast(fitz.Rect, item[1]).x0),
    )
    index = next(i for i, (cis, _) in enumerate(ordered) if cast(fitz.Rect, _).intersects(bbox))
    prev_box = cast(fitz.Rect, ordered[index - 1][1]) if index > 0 else None
    next_box = cast(fitz.Rect, ordered[index + 1][1]) if index + 1 < len(ordered) else None

    y0 = content.y0
    y1 = content.y1
    if prev_box is not None and abs(prev_box.y0 - bbox.y0) < abs(prev_box.x0 - bbox.x0):
        y0 = max(content.y0, (prev_box.y1 + bbox.y0) / 2)
    if next_box is not None and abs(next_box.y0 - bbox.y0) < abs(next_box.x0 - bbox.x0):
        y1 = min(content.y1, (bbox.y1 + next_box.y0) / 2)

    x0 = content.x0
    x1 = content.x1
    if prev_box is not None and abs(prev_box.x0 - bbox.x0) >= abs(prev_box.y0 - bbox.y0):
        x0 = max(content.x0, (prev_box.x1 + bbox.x0) / 2)
    if next_box is not None and abs(next_box.x0 - bbox.x0) >= abs(next_box.y0 - bbox.y0):
        x1 = min(content.x1, (bbox.x1 + next_box.x0) / 2)

    expanded = fitz.Rect(x0, y0, x1, y1)
    pad = max(2.0, min(bbox.width, bbox.height) * 0.08)
    expanded.x0 = max(page.x0, expanded.x0 - pad)
    expanded.y0 = max(page.y0, expanded.y0 - pad)
    expanded.x1 = min(page.x1, expanded.x1 + pad)
    expanded.y1 = min(page.y1, expanded.y1 + pad)
    return expanded


def _label_rect_for_cis(
    cis_bbox: object,
    cis_boxes: list[tuple[str, object]],
    frames: list[object],
    page: object,
) -> object:
    import fitz  # pymupdf

    pg = cast(fitz.Page, page)
    framed = _frame_rect_for_cis(cis_bbox, frames)
    if framed is not None:
        return framed
    if len(cis_boxes) == 1:
        content = _content_rect_for_page(page)
        content_rect = cast(fitz.Rect, content)
        page_rect = pg.rect
        if content_rect.get_area() < page_rect.get_area() * 0.85:
            return content_rect
        return page_rect
    return _fallback_label_rect(cis_bbox, cis_boxes, pg.rect, _content_rect_for_page(page))


def extract_label_artifacts_from_pdf(content: bytes) -> list[ExtractedLabelArtifact]:
    try:
        import fitz  # pymupdf
    except ImportError as exc:
        raise RuntimeError("pdf_support_unavailable") from exc

    _, _, extract_gtin_from_cis = _cis_helpers()
    artifacts: list[ExtractedLabelArtifact] = []
    seen: set[str] = set()
    doc = fitz.open(stream=content, filetype="pdf")
    try:
        for page_index in range(doc.page_count):
            page = doc[page_index]
            cis_boxes = _find_cis_boxes_on_page(page)
            if not cis_boxes:
                continue
            frames = _drawing_rects(page)
            for cis, cis_bbox in cis_boxes:
                if cis in seen:
                    continue
                seen.add(cis)
                label_rect = _label_rect_for_cis(cis_bbox, cis_boxes, frames, page)
                label_pdf = crop_pdf_page_to_single_label_pdf(doc, page_index, label_rect)
                gtin = extract_gtin_from_cis(cis) or ""
                artifacts.append(
                    ExtractedLabelArtifact(
                        cis=cis,
                        gtin=gtin,
                        label_pdf=label_pdf,
                        source_page_index=page_index,
                    ),
                )
    finally:
        doc.close()
    return artifacts
