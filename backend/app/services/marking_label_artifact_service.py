from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from statistics import median
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    import fitz

    from app.services.marking_datamatrix_service import DecodedDataMatrix


@dataclass(frozen=True)
class ExtractedLabelArtifact:
    cis: str
    gtin: str
    label_pdf: bytes
    source_page_index: int
    code_valid: bool = True


def pdf_bytes_to_png(
    pdf_bytes: bytes,
    dpi: int = 600,
    *,
    cis_code: str | None = None,
) -> bytes:
    try:
        import fitz  # pymupdf
    except ImportError as exc:
        raise RuntimeError("pdf_support_unavailable") from exc
    prepared_pdf = _prepare_label_artifact_pdf(pdf_bytes, cis_code)
    doc = fitz.open(stream=prepared_pdf, filetype="pdf")
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


def _edge_module_pitch(
    samples: bytes,
    stride: int,
    bounds: tuple[int, int, int, int],
    *,
    horizontal: bool,
) -> float | None:
    min_x, min_y, max_x, max_y = bounds

    def is_black(x: int, y: int) -> bool:
        return samples[y * stride + x] < 128

    edge_lines = (
        (min_y, min(min_y + 1, max_y), max(max_y - 1, min_y), max_y)
        if horizontal
        else (min_x, min(min_x + 1, max_x), max(max_x - 1, min_x), max_x)
    )
    candidates: list[tuple[float, int, float]] = []
    for edge in dict.fromkeys(edge_lines):
        values = (
            [is_black(x, edge) for x in range(min_x, max_x + 1)]
            if horizontal
            else [is_black(edge, y) for y in range(min_y, max_y + 1)]
        )
        if not values:
            continue
        runs: list[int] = []
        previous = values[0]
        start = 0
        for index, value in enumerate(values[1:], 1):
            if value == previous:
                continue
            run = index - start
            if run >= 2:
                runs.append(run)
            previous = value
            start = index
        final_run = len(values) - start
        if final_run >= 2:
            runs.append(final_run)
        # The alternating ECC200 finder edge has one run per module. Solid
        # finder edges and arbitrary label artwork do not provide this signal.
        if len(runs) < 8:
            continue
        pitch = float(median(runs))
        deviation = float(median(abs(run - pitch) for run in runs)) / max(pitch, 1.0)
        candidates.append((deviation, -len(runs), pitch))
    return min(candidates)[2] if candidates else None


def _datamatrix_module_pitches(
    page: object,
    rect: object,
    dpi: int = 600,
) -> tuple[float, float] | None:
    """Measure physical X/Y module steps on the two alternating finder edges."""
    import fitz  # pymupdf

    pg = cast(fitz.Page, page)
    box = fitz.Rect(rect) & pg.rect
    if box.is_empty or box.width <= 0 or box.height <= 0:
        return None
    scale = dpi / 72.0
    pix = pg.get_pixmap(
        matrix=fitz.Matrix(scale, scale),
        clip=box,
        colorspace=fitz.csGRAY,
        alpha=False,
    )
    samples = pix.samples
    min_x, min_y = pix.width, pix.height
    max_x = max_y = -1
    for y in range(pix.height):
        row_offset = y * pix.stride
        for x in range(pix.width):
            if samples[row_offset + x] >= 128:
                continue
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    if max_x < min_x or max_y < min_y:
        return None
    bounds = (min_x, min_y, max_x, max_y)
    pitch_x = _edge_module_pitch(samples, pix.stride, bounds, horizontal=True)
    pitch_y = _edge_module_pitch(samples, pix.stride, bounds, horizontal=False)
    if pitch_x is None or pitch_y is None:
        return None
    return pitch_x, pitch_y


def _square_datamatrix_pdf(cis_code: str) -> tuple[bytes, float]:
    """Return a vector square Data Matrix and outer/inner side ratio (quiet zone included)."""
    import fitz  # pymupdf
    import zxingcpp

    barcode = zxingcpp.create_barcode(
        cis_code.encode("utf-8"),
        format=zxingcpp.DataMatrix,
        force_square=True,
    )
    raw = zxingcpp.write_barcode_to_image(barcode, scale=1, add_quiet_zones=False)
    module_rows, module_columns = raw.shape
    if module_rows != module_columns or module_rows < 1:
        raise ValueError("datamatrix_square_encoding_failed")
    svg = zxingcpp.write_barcode_to_svg(
        barcode,
        scale=1,
        add_quiet_zones=True,
    ).encode("utf-8")
    svg_doc = fitz.open(stream=svg, filetype="svg")
    try:
        outer_side = float(svg_doc[0].rect.width)
        return cast(bytes, svg_doc.convert_to_pdf()), outer_side / float(module_rows)
    finally:
        svg_doc.close()


def _repair_distorted_datamatrix_pdf(pdf_bytes: bytes, cis_code: str) -> bytes:
    """Replace only an anisotropically scaled Data Matrix inside a stored label PDF."""
    import fitz  # pymupdf

    from app.services.marking_datamatrix_service import decode_datamatrix_codes_on_pdf_page

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    replacement: fitz.Document | None = None
    try:
        if doc.page_count < 1:
            return pdf_bytes
        page = doc[0]
        decoded = decode_datamatrix_codes_on_pdf_page(page, dpi=600)
        matching = [item for item in decoded if item.value == cis_code]
        distorted: list[DecodedDataMatrix] = []
        for item in matching:
            pitches = _datamatrix_module_pitches(page, item.page_rect)
            if pitches is None:
                continue
            pitch_x, pitch_y = pitches
            if max(pitch_x, pitch_y) / max(min(pitch_x, pitch_y), 0.01) >= 1.2:
                distorted.append(item)
        if not distorted:
            return pdf_bytes

        replacement_bytes, quiet_zone_ratio = _square_datamatrix_pdf(cis_code)
        replacement = fitz.open(stream=replacement_bytes, filetype="pdf")
        for item in distorted:
            symbol = fitz.Rect(item.page_rect) & page.rect
            # Preserve the smaller (not stretched) physical module step. The
            # replacement side adds only the standard one-module quiet zone.
            target_side = min(
                symbol.width,
                symbol.height,
            ) * quiet_zone_ratio
            target_side = min(target_side, page.rect.width, page.rect.height)
            center = (symbol.tl + symbol.br) / 2
            target = fitz.Rect(
                center.x - target_side / 2,
                center.y - target_side / 2,
                center.x + target_side / 2,
                center.y + target_side / 2,
            )
            dx = (
                page.rect.x0 - target.x0
                if target.x0 < page.rect.x0
                else min(page.rect.x1 - target.x1, 0.0)
            )
            dy = (
                page.rect.y0 - target.y0
                if target.y0 < page.rect.y0
                else min(page.rect.y1 - target.y1, 0.0)
            )
            target += (dx, dy, dx, dy)
            erase = symbol | target
            erase = fitz.Rect(
                max(page.rect.x0, erase.x0 - 0.5),
                max(page.rect.y0, erase.y0 - 0.5),
                min(page.rect.x1, erase.x1 + 0.5),
                min(page.rect.y1, erase.y1 + 0.5),
            )
            page.draw_rect(erase, color=None, fill=(1, 1, 1), overlay=True)
            page.show_pdf_page(
                target,
                replacement,
                0,
                keep_proportion=True,
                overlay=True,
            )
        return cast(bytes, doc.tobytes())
    finally:
        if replacement is not None:
            replacement.close()
        doc.close()


def _prepare_label_artifact_pdf(pdf_bytes: bytes, cis_code: str | None) -> bytes:
    """Repair only a proven distorted symbol; otherwise preserve the PDF exactly."""
    return (
        _repair_distorted_datamatrix_pdf(pdf_bytes, cis_code)
        if cis_code
        else pdf_bytes
    )


def fit_label_artifact_pdf_to_page(
    pdf_bytes: bytes,
    page_width_mm: float,
    page_height_mm: float,
    cis_code: str | None = None,
) -> bytes:
    """Вписывает PDF селлера (обычно 60x40 альбом) на страницу выбранного размера наклейки."""
    import fitz  # pymupdf

    if page_width_mm <= 0 or page_height_mm <= 0:
        raise ValueError("invalid_page_size")

    prepared_pdf = _prepare_label_artifact_pdf(pdf_bytes, cis_code)
    src = fitz.open(stream=prepared_pdf, filetype="pdf")
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
    *,
    cis_codes: list[str] | None = None,
) -> bytes:
    if cis_codes is not None and len(cis_codes) != len(parts):
        raise ValueError("artifact_cis_count_mismatch")
    if page_width_mm is not None and page_height_mm is not None:
        fitted = [
            fit_label_artifact_pdf_to_page(
                part,
                page_width_mm,
                page_height_mm,
                cis_codes[index] if cis_codes is not None else None,
            )
            for index, part in enumerate(parts)
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
    # Flatten lines across *all* text blocks in page order (not per-block):
    # some seller labels print "(01) <gtin>" and "(21) <serial>" as two
    # separate text objects (each becomes its own PyMuPDF block with one
    # line), because the label generator places each AI on its own text run
    # rather than wrapping a single paragraph.
    lines: list[dict[str, Any]] = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        lines.extend(block.get("lines", []))
    line_texts = [
        "".join(str(span.get("text", "")) for span in line.get("spans", []))
        for line in lines
    ]
    for index, line in enumerate(lines):
        spans = line.get("spans", [])
        line_text = line_texts[index]
        # Fall back to a joined window with the next line when the current
        # line alone has no match — covers the split-AI case above. Only do
        # this when the *next* line has no self-contained match of its own,
        # otherwise an unrelated line preceding a normal single-line CIS
        # (e.g. a "Честный знак" caption) would falsely "absorb" the next
        # line's real match under a wrong, union-of-both bounding box.
        next_line = lines[index + 1] if index + 1 < len(lines) else None
        search_text = line_text
        joined_with_next = False
        if (
            not cis_re.search(search_text)
            and next_line is not None
            and not cis_re.search(line_texts[index + 1])
        ):
            search_text = line_text + line_texts[index + 1]
            joined_with_next = True
        if not cis_re.search(search_text):
            continue
        for match in cis_re.finditer(search_text):
            cis = normalize_cis(f"01{match.group('gtin')}21{match.group('serial')}")
            if cis is None or cis in seen:
                continue
            seen.add(cis)
            line_bbox = fitz.Rect(line["bbox"])
            span_rects = [fitz.Rect(span["bbox"]) for span in spans if span.get("bbox")]
            if joined_with_next and next_line is not None:
                line_bbox |= fitz.Rect(next_line["bbox"])
                span_rects += [
                    fitz.Rect(span["bbox"])
                    for span in next_line.get("spans", [])
                    if span.get("bbox")
                ]
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
    x0, y0, x1, y1 = content.x0, content.y0, content.x1, content.y1
    for _, rect in cis_boxes:
        other = cast(fitz.Rect, rect)
        if other == bbox:
            continue
        dx = abs((other.x0 + other.x1) - (bbox.x0 + bbox.x1))
        dy = abs((other.y0 + other.y1) - (bbox.y0 + bbox.y1))
        same_row = max(other.y0, bbox.y0) < min(other.y1, bbox.y1)
        same_column = max(other.x0, bbox.x0) < min(other.x1, bbox.x1)
        # Separate neighbours along the gap between them, never through a symbol.
        if same_row or dx >= dy:
            if other.x1 <= bbox.x0:
                x0 = max(x0, (other.x1 + bbox.x0) / 2)
            elif other.x0 >= bbox.x1:
                x1 = min(x1, (bbox.x1 + other.x0) / 2)
        if same_column or dy > dx:
            if other.y1 <= bbox.y0:
                y0 = max(y0, (other.y1 + bbox.y0) / 2)
            elif other.y0 >= bbox.y1:
                y1 = min(y1, (bbox.y1 + other.y0) / 2)

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


def _looks_like_raster_datamatrix(page: object, rect: object) -> bool:
    """Reject ordinary square logos/photos; retain dense monochrome matrix symbols."""
    import fitz  # pymupdf

    pg = cast(fitz.Page, page)
    box = cast(fitz.Rect, rect)
    try:
        pix = pg.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), clip=box, colorspace=fitz.csGRAY)
    except Exception:
        return False
    if pix.width < 16 or pix.height < 16:
        return False
    pixels = pix.samples
    total = len(pixels)
    dark = sum(value < 64 for value in pixels)
    light = sum(value > 191 for value in pixels)
    if (dark + light) / total < 0.82 or not 0.12 <= dark / total <= 0.68:
        return False
    transitions = 0
    comparisons = 0
    width = pix.width
    height = pix.height
    for y in range(height):
        offset = y * width
        for x in range(1, width):
            transitions += (pixels[offset + x] < 128) != (pixels[offset + x - 1] < 128)
            comparisons += 1
    for y in range(1, height):
        offset = y * width
        previous = offset - width
        for x in range(width):
            transitions += (pixels[offset + x] < 128) != (pixels[previous + x] < 128)
            comparisons += 1
    if comparisons == 0 or transitions / comparisons < 0.025:
        return False

    dark_points = [
        (index % width, index // width)
        for index, value in enumerate(pixels)
        if value < 128
    ]
    if not dark_points:
        return False
    x0 = min(point[0] for point in dark_points)
    x1 = max(point[0] for point in dark_points)
    y0 = min(point[1] for point in dark_points)
    y1 = max(point[1] for point in dark_points)
    if x1 - x0 < 12 or y1 - y0 < 12:
        return False

    sides = [
        [pixels[y0 * width + x] < 128 for x in range(x0, x1 + 1)],
        [pixels[y * width + x1] < 128 for y in range(y0, y1 + 1)],
        [pixels[y1 * width + x] < 128 for x in range(x0, x1 + 1)],
        [pixels[y * width + x0] < 128 for y in range(y0, y1 + 1)],
    ]

    def side_stats(values: list[bool]) -> tuple[float, float]:
        dark_fraction = sum(values) / len(values)
        transition_rate = sum(
            values[index] != values[index - 1] for index in range(1, len(values))
        ) / max(len(values) - 1, 1)
        return dark_fraction, transition_rate

    stats = [side_stats(side) for side in sides]
    solid = [dark_fraction >= 0.85 for dark_fraction, _ in stats]
    alternating = [
        0.2 <= dark_fraction <= 0.8 and transition_rate >= 0.025
        for dark_fraction, transition_rate in stats
    ]
    # ECC200 DataMatrix has a solid L-shaped finder border and alternating
    # modules on the opposite two sides. This rejects checker logos and most
    # square product artwork while retaining a symbol whose payload is damaged.
    return any(
        solid[index]
        and solid[(index + 1) % 4]
        and alternating[(index + 2) % 4]
        and alternating[(index + 3) % 4]
        for index in range(4)
    )


def _rect_key(rect: object) -> tuple[float, float, float, float]:
    import fitz  # pymupdf

    box = cast(fitz.Rect, rect)
    return tuple(round(value, 1) for value in (box.x0, box.y0, box.x1, box.y1))


def _vector_datamatrix_candidates(page: object, frames: list[object]) -> list[object]:
    """Locate dense vector module grids without treating every square artwork as a code."""
    import fitz  # pymupdf

    pg = cast(fitz.Page, page)
    modules: list[fitz.Rect] = []
    for drawing in pg.get_drawings():
        raw = drawing.get("rect")
        if raw is None:
            continue
        rect = fitz.Rect(raw)
        if not 0.7 <= rect.width / max(rect.height, 0.01) <= 1.3:
            continue
        if 0.5 <= rect.width <= 16 and 0.5 <= rect.height <= 16:
            modules.append(rect)
    if len(modules) < 20:
        return []

    groups: dict[tuple[float, float, float, float] | None, list[fitz.Rect]] = {}
    for module in modules:
        containing = [
            cast(fitz.Rect, frame)
            for frame in frames
            if _rect_contains(frame, module)
            and cast(fitz.Rect, frame).get_area() >= module.get_area() * 25
        ]
        frame = min(containing, key=lambda rect: float(rect.get_area())) if containing else None
        groups.setdefault(_rect_key(frame) if frame is not None else None, []).append(module)

    candidates: list[object] = []
    for group in groups.values():
        if len(group) < 20:
            continue
        bounds = fitz.Rect(group[0])
        filled_area = 0.0
        for module in group:
            bounds |= module
            filled_area += float(module.get_area())
        if not 0.7 <= bounds.width / max(bounds.height, 0.01) <= 1.3:
            continue
        density = filled_area / max(float(bounds.get_area()), 0.01)
        if 0.08 <= density <= 0.8 and _looks_like_raster_datamatrix(page, bounds):
            candidates.append(bounds)
    return candidates


def _rows_in_source_order(
    rows: list[tuple[str, str, bool, object]],
) -> list[tuple[str, str, bool, object]]:
    """Order symbols like labels on the source page: rows first, then left to right."""
    import fitz  # pymupdf

    grouped: list[tuple[fitz.Rect, list[tuple[str, str, bool, object]]]] = []
    for row in sorted(rows, key=lambda item: cast(fitz.Rect, item[3]).y0):
        box = cast(fitz.Rect, row[3])
        target_index: int | None = None
        for index, (row_bounds, _) in enumerate(grouped):
            overlap = max(0.0, min(row_bounds.y1, box.y1) - max(row_bounds.y0, box.y0))
            if overlap >= min(row_bounds.height, box.height) * 0.35:
                target_index = index
                break
        if target_index is None:
            grouped.append((fitz.Rect(box), [row]))
            continue
        bounds, members = grouped[target_index]
        bounds |= box
        members.append(row)

    ordered: list[tuple[str, str, bool, object]] = []
    for _, members in sorted(grouped, key=lambda group: group[0].y0):
        ordered.extend(sorted(members, key=lambda item: cast(fitz.Rect, item[3]).x0))
    return ordered


def extract_label_artifacts_from_pdf(content: bytes) -> list[ExtractedLabelArtifact]:
    try:
        import fitz  # pymupdf
    except ImportError as exc:
        raise RuntimeError("pdf_support_unavailable") from exc

    from app.services.marking_datamatrix_service import decode_datamatrix_codes_on_pdf_page

    _, normalize_cis, extract_gtin_from_cis = _cis_helpers()
    artifacts: list[ExtractedLabelArtifact] = []
    seen: set[str] = set()
    doc = fitz.open(stream=content, filetype="pdf")
    try:
        for page_index in range(doc.page_count):
            page = doc[page_index]
            frames = _drawing_rects(page)
            detected = decode_datamatrix_codes_on_pdf_page(page, include_errors=True)
            decoded = [item for item in detected if item.valid]
            text_boxes = _find_cis_boxes_on_page(page)
            decoded_rows: list[tuple[str, str, bool, object]] = []
            for item in decoded:
                normalized = normalize_cis(item.value)
                gtin = extract_gtin_from_cis(item.value) if normalized is not None else None
                # Text may locate a label, but never supplies or completes its payload.
                box = fitz.Rect(item.page_rect)
                matching_text = [
                    fitz.Rect(rect) for prefix, rect in text_boxes
                    if item.value == prefix or item.value.startswith(prefix + "\x1d")
                ]
                if matching_text:
                    nearest = min(
                        matching_text,
                        key=lambda rect: abs(rect.x0 - box.x0) + abs(rect.y0 - box.y0),
                    )
                    box |= nearest
                # Preserve the exact decoded payload. Validation and normalized lookup
                # are separate concerns; downstream printing relies on these bytes.
                decoded_rows.append(
                    (item.value, gtin or "", normalized is not None and bool(gtin), box)
                )
            decoded_frames = {
                _rect_key(frame)
                for _, _, _, decoded_box in decoded_rows
                if (frame := _frame_rect_for_cis(decoded_box, frames)) is not None
            }
            # A page may contain several labels while only some DataMatrix symbols
            # decode. Retain only matrix-like raster/vector regions from a different
            # label frame. A generic square logo or product photo must not become a
            # synthetic damaged KIZ.
            damaged_boxes = [fitz.Rect(item.page_rect) for item in detected if not item.valid]
            for image_info in page.get_image_info():
                image_box = fitz.Rect(image_info["bbox"])
                if image_box.width < 20 or image_box.height < 20:
                    continue
                aspect = image_box.width / image_box.height
                if not 0.75 <= aspect <= 1.33:
                    continue
                if not _looks_like_raster_datamatrix(page, image_box):
                    continue
                if any(
                    (image_box & cast(fitz.Rect, decoded_box)).get_area()
                    >= image_box.get_area() * 0.25
                    for _, _, _, decoded_box in decoded_rows
                ):
                    continue
                frame = _frame_rect_for_cis(image_box, frames)
                if frame is not None and _rect_key(frame) in decoded_frames:
                    continue
                if any(
                    (image_box & existing).get_area() >= image_box.get_area() * 0.5
                    for existing in damaged_boxes
                ):
                    continue
                damaged_boxes.append(image_box)
            for vector_box in _vector_datamatrix_candidates(page, frames):
                candidate = cast(fitz.Rect, vector_box)
                if any(
                    (candidate & cast(fitz.Rect, decoded_box)).get_area()
                    >= candidate.get_area() * 0.25
                    for _, _, _, decoded_box in decoded_rows
                ):
                    continue
                frame = _frame_rect_for_cis(candidate, frames)
                if frame is not None and _rect_key(frame) in decoded_frames:
                    continue
                if any(
                    (candidate & existing).get_area() >= candidate.get_area() * 0.5
                    for existing in damaged_boxes
                ):
                    continue
                damaged_boxes.append(candidate)
            for damaged_box in damaged_boxes:
                decoded_rows.append(("", "", False, damaged_box))
            decoded_rows = _rows_in_source_order(decoded_rows)
            cis_boxes = [(cis, box) for cis, _, _, box in decoded_rows]
            if not decoded_rows:
                # No decoded or geometrically identified matrix exists on this page.
                # Do not guess from arbitrary artwork: an ordinary square image is
                # not evidence of a damaged marking code.
                continue
            for cis, gtin, code_valid, cis_bbox in decoded_rows:
                if code_valid:
                    if cis in seen:
                        continue
                    seen.add(cis)
                label_rect = _label_rect_for_cis(cis_bbox, cis_boxes, frames, page)
                label_pdf = crop_pdf_page_to_single_label_pdf(doc, page_index, label_rect)
                artifacts.append(
                    ExtractedLabelArtifact(
                        cis=cis,
                        gtin=gtin,
                        label_pdf=label_pdf,
                        source_page_index=page_index,
                        code_valid=code_valid,
                    ),
                )
    finally:
        doc.close()
    return artifacts
