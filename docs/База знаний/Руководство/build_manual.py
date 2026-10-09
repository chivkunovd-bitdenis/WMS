#!/usr/bin/env python3
"""Build the WMS customer handbook from its five Markdown chapters.

The text PDF and Word document share the same parsed chapter content. The
illustrated PDF is produced only when approved screenshot entries exist in the
chapter illustration manifests. Screenshot manifests are owned by the chapter
authors; this script reads them but does not rewrite them.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Mm, Pt, RGBColor
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    Image as PdfImage,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents


MANUAL_DIR = Path(__file__).resolve().parent
KB_DIR = MANUAL_DIR.parent
REPO_ROOT = MANUAL_DIR.parents[2]
QA_DIR = MANUAL_DIR / ".qa"
LOGO_PATH = REPO_ROOT / "frontend/public/portal-logo-ff.png"
MANIFESTS = (
    MANUAL_DIR / "иллюстрации_01_03.json",
    MANUAL_DIR / "иллюстрации_02_04.json",
    MANUAL_DIR / "иллюстрации_05.json",
)
CHAPTER_FILES = (
    "01_Приёмка_каталог_возвраты.md",
    "02_Маркетплейсы_FBS_маркировка.md",
    "03_Остатки_ячейки_расчёты.md",
    "04_FBO_Stage_G.md",
    "05_Отгрузка_календарь.md",
)

PURPLE = "5B45C7"
PURPLE_DARK = "3F2E93"
PURPLE_PALE = "F3F0FF"
INK = "24213A"
MUTED = "69667A"
RULE = "DAD5F2"
WHITE = "FFFFFF"
PDF_FONT = "ManualArial"
PDF_FONT_BOLD = "ManualArial-Bold"
PDF_FONT_ITALIC = "ManualArial-Italic"
PDF_FONT_BOLD_ITALIC = "ManualArial-BoldItalic"

PDF_PURPLE = colors.HexColor(f"#{PURPLE}")
PDF_PURPLE_DARK = colors.HexColor(f"#{PURPLE_DARK}")
PDF_PURPLE_PALE = colors.HexColor(f"#{PURPLE_PALE}")
PDF_INK = colors.HexColor(f"#{INK}")
PDF_MUTED = colors.HexColor(f"#{MUTED}")
PDF_RULE = colors.HexColor(f"#{RULE}")


@dataclass
class Heading:
    chapter: Path
    level: int
    title: str
    bookmark: str
    slug: str


@dataclass
class Block:
    kind: str
    content: Any
    heading: Heading | None = None


@dataclass
class Chapter:
    path: Path
    title: str
    blocks: list[Block] = field(default_factory=list)
    headings: list[Heading] = field(default_factory=list)


@dataclass
class Figure:
    chapter: Path
    after_heading: str
    image_path: Path
    caption: str
    callouts: list[dict[str, Any]]
    source_rects: list[dict[str, Any]] = field(default_factory=list)


def slugify(text: str) -> str:
    text = re.sub(r"[`*_]", "", text.lower())
    text = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
    return re.sub(r"[\s\-]+", "-", text).strip("-")


def markdown_plain(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    return text.strip()


def normalized_heading(text: str) -> str:
    return markdown_plain(re.sub(r"^#{1,6}\s+", "", text.strip())).casefold()


def strip_frontmatter(lines: list[str]) -> list[str]:
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                return lines[index + 1 :]
    return lines


def clean_customer_text(text: str) -> str:
    """Remove audit-only sentences without touching the customer procedure."""
    text = re.sub(
        r"(?<=[.!?])\s*[^.!?]*\[[^\]]+\]\(проверка_\d+\.md\)[^.!?]*\.?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def parse_chapter(path: Path, index: int) -> Chapter:
    lines = strip_frontmatter(path.read_text(encoding="utf-8").splitlines())
    clean_lines: list[str] = []
    skip_toc = False
    for line in lines:
        if re.match(r"^##\s+Оглавление\s*$", line.strip(), re.IGNORECASE):
            skip_toc = True
            continue
        if skip_toc:
            if re.match(r"^#{1,2}\s+", line.strip()):
                skip_toc = False
            else:
                continue
        if re.match(r"^##\s+(?:Проверка|Источники|Нерешённые вопросы)\b", line.strip(), re.IGNORECASE):
            continue
        clean_lines.append(line.rstrip())

    title = path.stem.replace("_", " ")
    for line in clean_lines:
        match = re.match(r"^#\s+(.+)$", line.strip())
        if match:
            title = markdown_plain(match.group(1))
            break

    chapter = Chapter(path=path, title=title)
    heading_counter = 0
    cursor = 0
    while cursor < len(clean_lines):
        current = clean_lines[cursor].strip()
        if not current:
            cursor += 1
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", current)
        if heading_match:
            level = len(heading_match.group(1))
            text = markdown_plain(heading_match.group(2))
            heading_counter += 1
            bookmark = f"c{index:02d}_h{heading_counter:03d}"
            heading = Heading(path, level, text, bookmark, slugify(text))
            chapter.headings.append(heading)
            chapter.blocks.append(Block("heading", text, heading))
            cursor += 1
            continue

        if current in {"---", "***", "___"}:
            chapter.blocks.append(Block("rule", None))
            cursor += 1
            continue

        if current.startswith("|") and cursor + 1 < len(clean_lines) and re.match(
            r"^\s*\|?\s*:?-{2,}", clean_lines[cursor + 1]
        ):
            table_lines: list[str] = [current]
            cursor += 1
            cursor += 1  # separator row
            while cursor < len(clean_lines) and clean_lines[cursor].strip().startswith("|"):
                table_lines.append(clean_lines[cursor].strip())
                cursor += 1
            rows = [
                [clean_customer_text(cell.strip()) for cell in row.strip().strip("|").split("|")]
                for row in table_lines
            ]
            chapter.blocks.append(Block("table", rows))
            continue

        if re.match(r"^>\s?", current):
            quote_lines: list[str] = []
            while cursor < len(clean_lines) and re.match(r"^\s*>\s?", clean_lines[cursor]):
                quote_lines.append(re.sub(r"^\s*>\s?", "", clean_lines[cursor].strip()))
                cursor += 1
            chapter.blocks.append(Block("quote", " ".join(quote_lines)))
            continue

        list_match = re.match(r"^(?:[-+*]|\d+[.)])\s+", current)
        if list_match:
            first_number = re.match(r"^(\d+)[.)]\s+", current)
            ordered = first_number is not None
            start_number = int(first_number.group(1)) if first_number else 1
            items: list[str] = []
            while cursor < len(clean_lines):
                item_line = clean_lines[cursor].strip()
                item_match = re.match(r"^(?:[-+*]|\d+[.)])\s+(.*)$", item_line)
                if not item_match:
                    break
                item = item_match.group(1)
                cursor += 1
                continuation: list[str] = []
                while cursor < len(clean_lines):
                    following = clean_lines[cursor]
                    if not following.strip():
                        break
                    if re.match(r"^\s*(?:[-+*]|\d+[.)])\s+", following):
                        break
                    if re.match(r"^#{1,6}\s+", following.strip()) or following.strip().startswith("|"):
                        break
                    continuation.append(following.strip())
                    cursor += 1
                items.append(clean_customer_text(" ".join([item, *continuation]).strip()))
                if cursor < len(clean_lines) and not clean_lines[cursor].strip():
                    # Keep a blank line inside one Markdown list if another item follows.
                    next_nonblank = cursor + 1
                    while next_nonblank < len(clean_lines) and not clean_lines[next_nonblank].strip():
                        next_nonblank += 1
                    if next_nonblank < len(clean_lines) and re.match(
                        r"^\s*(?:[-+*]|\d+[.)])\s+", clean_lines[next_nonblank]
                    ):
                        cursor = next_nonblank
                        continue
                    break
            # Preserve an explicit Markdown list start when prose separates
            # two fragments of the same numbered procedure (for example 1–3,
            # explanatory paragraph, then 4–5).
            chapter.blocks.append(Block("list", (ordered, start_number, items)))
            continue

        paragraph_lines: list[str] = []
        while cursor < len(clean_lines):
            candidate = clean_lines[cursor].strip()
            if not candidate:
                break
            if re.match(r"^#{1,6}\s+", candidate) or candidate in {"---", "***", "___"}:
                break
            if candidate.startswith("|") or re.match(r"^(?:[-+*]|\d+[.)])\s+", candidate):
                break
            paragraph_lines.append(candidate)
            cursor += 1
        paragraph = clean_customer_text(" ".join(paragraph_lines))
        if paragraph:
            chapter.blocks.append(Block("paragraph", paragraph))
        if cursor < len(clean_lines) and not clean_lines[cursor].strip():
            cursor += 1

    return chapter


def make_heading_map(chapters: list[Chapter]) -> dict[tuple[str, str], Heading]:
    mapping: dict[tuple[str, str], Heading] = {}
    for chapter in chapters:
        for heading in chapter.headings:
            mapping[(chapter.path.name, heading.slug)] = heading
        first = next((h for h in chapter.headings if h.level == 1), None)
        if first:
            mapping[(chapter.path.name, "")] = first
    aliases = {
        "02-proverit-ostatok-i-dvizheniya-tovara.md": ("03_Остатки_ячейки_расчёты.md", "2-проверить-отчёт-остатки-и-движения"),
        "02-razmeshchenie.md": ("03_Остатки_ячейки_расчёты.md", "3-найти-ячейку-или-тару-и-проверить-перемещения"),
    }
    for alias, target in aliases.items():
        if target in mapping:
            mapping[(alias, "")] = mapping[target]
    return mapping


LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
INLINE_TOKEN_RE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|\*[^*]+\*)")


def resolve_markdown_link(
    source: Path,
    href: str,
    headings: dict[tuple[str, str], Heading],
) -> tuple[str | None, str]:
    if href.startswith(("https://", "http://", "mailto:")):
        return href, ""
    path_text, _, fragment = href.partition("#")
    target_path = (source.parent / path_text).resolve() if path_text else source.resolve()
    target_name = target_path.name
    target_slug = slugify(fragment.replace("#", "")) if fragment else ""
    heading = headings.get((target_name, target_slug)) or headings.get((target_name, ""))
    if heading:
        return f"#{heading.bookmark}", heading.title
    return None, ""


def split_inline(text: str) -> list[tuple[str, str]]:
    pieces: list[tuple[str, str]] = []
    cursor = 0
    for match in INLINE_TOKEN_RE.finditer(text):
        if match.start() > cursor:
            pieces.append(("text", text[cursor : match.start()]))
        value = match.group(0)
        if value.startswith("**"):
            pieces.append(("bold", value[2:-2]))
        elif value.startswith("`"):
            pieces.append(("code", value[1:-1]))
        else:
            pieces.append(("italic", value[1:-1]))
        cursor = match.end()
    if cursor < len(text):
        pieces.append(("text", text[cursor:]))
    return pieces


def pdf_inline(text: str, source: Path, headings: dict[tuple[str, str], Heading]) -> str:
    output: list[str] = []
    cursor = 0
    for match in LINK_RE.finditer(text):
        output.append(_pdf_inline_no_links(text[cursor : match.start()]))
        label, href = match.groups()
        target, replacement = resolve_markdown_link(source, href, headings)
        shown = replacement or label
        content = _pdf_inline_no_links(shown)
        if target and target.startswith("#"):
            output.append(f'<link href="{html.escape(target, quote=True)}" color="#{PURPLE}"><u>{content}</u></link>')
        elif target and target.startswith(("http://", "https://", "mailto:")):
            output.append(f'<link href="{html.escape(target, quote=True)}" color="#{PURPLE}"><u>{content}</u></link>')
        else:
            output.append(content)
        cursor = match.end()
    output.append(_pdf_inline_no_links(text[cursor:]))
    return "".join(output)


def _pdf_inline_no_links(text: str) -> str:
    return "".join(_pdf_format_text(value, kind) for kind, value in split_inline(text))


def _pdf_format_text(text: str, kind: str = "text") -> str:
    escaped = html.escape(text, quote=False).replace("\n", " ")
    if kind == "bold":
        return f"<b>{escaped}</b>"
    if kind == "italic":
        return f"<i>{escaped}</i>"
    if kind == "code":
        return f'<font name="{PDF_FONT}" backColor="#{PURPLE_PALE}">{escaped}</font>'
    return escaped


def add_docx_inline(paragraph: Any, text: str, source: Path, headings: dict[tuple[str, str], Heading]) -> None:
    cursor = 0
    for match in LINK_RE.finditer(text):
        _docx_inline_runs(paragraph, text[cursor : match.start()])
        label, href = match.groups()
        target, replacement = resolve_markdown_link(source, href, headings)
        shown = replacement or label
        if target and target.startswith("#"):
            add_internal_hyperlink(paragraph, target[1:], shown)
        elif target and target.startswith(("http://", "https://", "mailto:")):
            add_external_hyperlink(paragraph, target, shown)
        else:
            _docx_inline_runs(paragraph, shown)
        cursor = match.end()
    _docx_inline_runs(paragraph, text[cursor:])


def _docx_inline_runs(paragraph: Any, text: str) -> None:
    for kind, value in split_inline(text):
        run = paragraph.add_run(value)
        if kind == "bold":
            run.bold = True
        elif kind == "italic":
            run.italic = True
        elif kind == "code":
            run.font.name = "Courier New"
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor.from_string(PURPLE_DARK)


def add_external_hyperlink(paragraph: Any, url: str, text: str) -> None:
    relationship = paragraph.part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship)
    run = OxmlElement("w:r")
    props = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), PURPLE)
    props.append(color)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    props.append(underline)
    run.append(props)
    text_node = OxmlElement("w:t")
    text_node.text = text
    run.append(text_node)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def add_internal_hyperlink(
    paragraph: Any,
    anchor: str,
    text: str,
    *,
    bold: bool = False,
    font_size_pt: float | None = None,
    color_hex: str = PURPLE,
) -> None:
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("w:anchor"), anchor)
    hyperlink.set(qn("w:history"), "1")
    run = OxmlElement("w:r")
    props = OxmlElement("w:rPr")
    fonts = OxmlElement("w:rFonts")
    fonts.set(qn("w:ascii"), "Arial")
    fonts.set(qn("w:hAnsi"), "Arial")
    props.append(fonts)
    color = OxmlElement("w:color")
    color.set(qn("w:val"), color_hex)
    props.append(color)
    if bold:
        props.append(OxmlElement("w:b"))
    if font_size_pt is not None:
        size = OxmlElement("w:sz")
        size.set(qn("w:val"), str(round(font_size_pt * 2)))
        props.append(size)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    props.append(underline)
    run.append(props)
    text_node = OxmlElement("w:t")
    text_node.text = text
    run.append(text_node)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def add_bookmark(paragraph: Any, name: str, bookmark_id: int) -> None:
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(bookmark_id))
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(bookmark_id))
    paragraph._p.insert(0, start)
    paragraph._p.append(end)


def add_field(paragraph: Any, instruction: str) -> None:
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction_node = OxmlElement("w:instrText")
    instruction_node.set(qn("xml:space"), "preserve")
    instruction_node.text = instruction
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    text_node = OxmlElement("w:t")
    text_node.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for child in (begin, instruction_node, separate, text_node, end):
        run._r.append(child)


def set_cell_shading(cell: Any, fill: str) -> None:
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().append(shading)


def repeat_table_header(row: Any) -> None:
    table_row_properties = row._tr.get_or_add_trPr()
    repeat = OxmlElement("w:tblHeader")
    repeat.set(qn("w:val"), "true")
    table_row_properties.append(repeat)


def add_docx_table(doc: Any, rows: list[list[str]], source: Path, headings: dict[tuple[str, str], Heading]) -> None:
    if not rows:
        return
    columns = max(len(row) for row in rows)
    table = doc.add_table(rows=1, cols=columns)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    header = table.rows[0]
    repeat_table_header(header)
    for column in range(columns):
        cell = header.cells[column]
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        set_cell_shading(cell, PURPLE)
        paragraph = cell.paragraphs[0]
        paragraph.paragraph_format.space_after = Pt(2)
        add_docx_inline(paragraph, rows[0][column] if column < len(rows[0]) else "", source, headings)
        for run in paragraph.runs:
            run.font.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)
            run.font.size = Pt(8)
    for row_index, row_data in enumerate(rows[1:]):
        cells = table.add_row().cells
        for column in range(columns):
            cell = cells[column]
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
            if row_index % 2 == 1:
                set_cell_shading(cell, PURPLE_PALE)
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_after = Pt(2)
            add_docx_inline(paragraph, row_data[column] if column < len(row_data) else "", source, headings)
            for run in paragraph.runs:
                run.font.size = Pt(8)
    doc.add_paragraph().paragraph_format.space_after = Pt(1)


def load_figures() -> list[Figure]:
    figures: list[Figure] = []
    for manifest_path in MANIFESTS:
        if not manifest_path.exists():
            continue
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = payload.get("entries") or payload.get("assets") or []
        for item in entries:
            if item.get("approved") is False or item.get("status") in {"pending", "rejected"}:
                continue
            chapter_name = str(item.get("chapter", ""))
            after_heading = str(item.get("after_heading") or item.get("after_section") or "")
            image_value = str(item.get("image") or item.get("filename") or "")
            if not image_value:
                raise ValueError(f"В манифесте {manifest_path.name} есть иллюстрация без image/filename.")
            candidate_paths = [
                (manifest_path.parent / image_value).resolve(),
                (MANUAL_DIR / "assets" / "01_03" / image_value).resolve(),
                (MANUAL_DIR / "assets" / "02_04" / image_value).resolve(),
            ]
            source_path = str(item.get("sourcepath", ""))
            if source_path:
                source_candidate = Path(source_path)
                candidate_paths.append(source_candidate if source_candidate.is_absolute() else REPO_ROOT / source_candidate)
            image_path = next((candidate for candidate in candidate_paths if candidate.exists()), None)
            if image_path is None:
                raise FileNotFoundError(f"Изображение из {manifest_path.name} не найдено: {image_value}")
            figures.append(
                Figure(
                    chapter=Path(chapter_name),
                    after_heading=after_heading,
                    image_path=image_path,
                    caption=str(item.get("caption", "")),
                    callouts=list(item.get("callouts", [])),
                    source_rects=list(item.get("callouts", [])),
                )
            )
    return figures


def validate_figures(chapters: list[Chapter], figures: list[Figure]) -> None:
    for figure in figures:
        chapter = next(
            (
                chapter
                for chapter in chapters
                if figure.chapter.name
                and (chapter.path.name == figure.chapter.name or chapter.path.name.endswith(figure.chapter.name))
            ),
            None,
        )
        if chapter is None:
            raise ValueError(f"Глава иллюстрации отсутствует в сборке: {figure.chapter.name or '(не указана)'}")
        heading_names = {normalized_heading(item.title) for item in chapter.headings}
        if not figure.after_heading or normalized_heading(figure.after_heading) not in heading_names:
            raise ValueError(
                f"Заголовок для иллюстрации не найден в {chapter.path.name}: {figure.after_heading or '(не указан)'}"
            )
        if figure.callouts:
            numbers: list[int] = []
            try:
                from PIL import Image
            except ImportError as error:
                raise RuntimeError("Для проверки координат выносок нужна библиотека Pillow.") from error
            with Image.open(figure.image_path) as image:
                image_width, image_height = image.size
            for index, item in enumerate(figure.callouts, start=1):
                if not isinstance(item, dict):
                    raise ValueError(f"Выноска {index} в {figure.image_path.name} должна быть объектом.")
                raw_number = item.get("n", item.get("number"))
                try:
                    number = int(raw_number)
                except (TypeError, ValueError) as error:
                    raise ValueError(
                        f"У выноски {index} в {figure.image_path.name} нет целого номера n/number."
                    ) from error
                numbers.append(number)
                rect = item.get("rect")
                if not isinstance(rect, (list, tuple)) or len(rect) != 4:
                    raise ValueError(f"У выноски {number} в {figure.image_path.name} нужен rect=[x,y,w,h].")
                try:
                    x, y, width, height = [float(value) for value in rect]
                except (TypeError, ValueError) as error:
                    raise ValueError(f"Координаты rect выноски {number} должны быть числами.") from error
                if width < 8 or height < 8:
                    raise ValueError(
                        f"Отклонена выноска {number} в {figure.image_path.name}: rect должен покрывать видимый элемент "
                        f"(ширина и высота не меньше 8 px), получено {width:g}×{height:g} px."
                    )
                if x < 0 or y < 0 or x + width > image_width or y + height > image_height:
                    raise ValueError(
                        f"Координаты rect выноски {number} в {figure.image_path.name} выходят за границы "
                        f"изображения {image_width}×{image_height} px."
                    )
                marker = item.get("marker")
                if marker is not None:
                    if not isinstance(marker, (list, tuple)) or len(marker) != 2:
                        raise ValueError(f"У marker выноски {number} в {figure.image_path.name} ожидается [x,y].")
                    try:
                        marker_x, marker_y = [float(value) for value in marker]
                    except (TypeError, ValueError) as error:
                        raise ValueError(f"Координаты marker выноски {number} должны быть числами.") from error
                    if not (0 <= marker_x < image_width and 0 <= marker_y < image_height):
                        raise ValueError(
                            f"Координаты marker выноски {number} в {figure.image_path.name} выходят за границы "
                            f"изображения {image_width}×{image_height} px."
                        )
            expected = list(range(1, len(figure.callouts) + 1))
            if numbers != expected:
                raise ValueError(
                    f"Номера выносок в {figure.image_path.name} должны идти подряд с 1; "
                    f"получено {numbers}, ожидалось {expected}."
                )


def figure_for(chapter: Chapter, heading: str, figures: list[Figure]) -> list[Figure]:
    return [
        figure
        for figure in figures
        if (not figure.chapter.name or figure.chapter.name == chapter.path.name or chapter.path.name.endswith(figure.chapter.name))
        and normalized_heading(figure.after_heading) == normalized_heading(heading)
    ]


def _figure_size(figure: Figure) -> tuple[int, int]:
    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError("Для чтения размеров скриншота нужна библиотека Pillow.") from error
    with Image.open(figure.image_path) as image:
        return image.size


def _resolve_marker_positions(
    figure: Figure,
    source_width: int,
    source_height: int,
    scale_x: float,
    scale_y: float,
    marker_radius: float,
) -> list[tuple[float, float]]:
    """Use supplied markers or place them outside the control bounds without covering another target."""
    gap = 2.0
    radius_x = marker_radius / scale_x
    radius_y = marker_radius / scale_y
    gap_x = gap / scale_x
    gap_y = gap / scale_y
    rects = [[float(value) for value in item["rect"]] for item in figure.callouts]
    positions: list[tuple[float, float]] = []

    def overlaps_rect(point: tuple[float, float], rect: list[float]) -> bool:
        px, py = point
        x, y, rect_width, rect_height = rect
        return (
            px + radius_x > x
            and px - radius_x < x + rect_width
            and py + radius_y > y
            and py - radius_y < y + rect_height
        )

    def fits(point: tuple[float, float]) -> bool:
        px, py = point
        if px < radius_x or py < radius_y or px > source_width - radius_x or py > source_height - radius_y:
            return False
        if any(overlaps_rect(point, rect) for rect in rects):
            return False
        for other_x, other_y in positions:
            dx, dy = (px - other_x) * scale_x, (py - other_y) * scale_y
            if dx * dx + dy * dy < (2 * marker_radius + gap) ** 2:
                return False
        return True

    for index, rect in enumerate(rects):
        x, y, rect_width, rect_height = rect
        marker = figure.callouts[index].get("marker")
        if marker is not None:
            point = (float(marker[0]), float(marker[1]))
            if not fits(point):
                raise ValueError(
                    f"Позиция marker выноски {index + 1} в {figure.image_path.name} перекрывает целевой элемент, "
                    "другую выноску или выходит за край изображения."
                )
            positions.append(point)
            continue

        candidates = (
            (x + rect_width / 2, y - radius_y - gap_y),
            (x + rect_width + radius_x + gap_x, y + rect_height / 2),
            (x - radius_x - gap_x, y + rect_height / 2),
            (x + rect_width / 2, y + rect_height + radius_y + gap_y),
        )
        point = next((candidate for candidate in candidates if fits(candidate)), None)
        if point is None:
            raise ValueError(
                f"Не удалось автоматически поставить номер выноски {index + 1} в {figure.image_path.name} "
                "вне отмеченных контролов. Добавьте marker=[x,y] в манифест."
            )
        positions.append(point)
    return positions


def draw_figure_callouts(
    canvas: Any,
    figure: Figure,
    width: float,
    height: float,
    source_width: int,
    source_height: int,
) -> None:
    """Draw crisp vector control outlines and numbered markers over an unchanged source image."""
    scale_x = width / source_width
    scale_y = height / source_height
    radius = 6.4  # 4.5 mm diameter on the final page
    positions = _resolve_marker_positions(figure, source_width, source_height, scale_x, scale_y, radius)
    for index, item in enumerate(figure.callouts):
        x, y, rect_width, rect_height = [float(value) for value in item["rect"]]
        x0 = x * scale_x
        x1 = (x + rect_width) * scale_x
        y0 = height - (y + rect_height) * scale_y
        y1 = height - y * scale_y
        marker_x, marker_y = positions[index]
        cx = marker_x * scale_x
        cy = height - marker_y * scale_y

        # The leader approaches the nearest edge of the outlined control and stops just short of it.
        nearest_x = min(max(cx, x0), x1)
        nearest_y = min(max(cy, y0), y1)
        dx, dy = nearest_x - cx, nearest_y - cy
        distance = (dx * dx + dy * dy) ** 0.5
        if distance > radius + 2:
            ux, uy = dx / distance, dy / distance
            start_x, start_y = cx + ux * (radius + 0.8), cy + uy * (radius + 0.8)
            end_x, end_y = nearest_x - ux * 1.0, nearest_y - uy * 1.0
            canvas.saveState()
            canvas.setLineCap(1)
            canvas.setStrokeColor(colors.white)
            canvas.setLineWidth(3.0)
            canvas.line(start_x, start_y, end_x, end_y)
            canvas.setStrokeColor(PDF_PURPLE)
            canvas.setLineWidth(1.15)
            canvas.line(start_x, start_y, end_x, end_y)
            canvas.restoreState()

        canvas.saveState()
        canvas.setLineCap(1)
        canvas.setStrokeColor(colors.white)
        canvas.setLineWidth(3.0)
        canvas.rect(x0, y0, x1 - x0, y1 - y0, stroke=1, fill=0)
        canvas.setStrokeColor(PDF_PURPLE)
        canvas.setLineWidth(1.5)  # approximately 2 px at a 96 dpi review render
        canvas.rect(x0, y0, x1 - x0, y1 - y0, stroke=1, fill=0)
        canvas.setFillColor(PDF_PURPLE)
        canvas.setStrokeColor(colors.white)
        canvas.setLineWidth(1.15)
        canvas.circle(cx, cy, radius, stroke=1, fill=1)
        number = str(item.get("n", item.get("number")))
        canvas.setFillColor(colors.white)
        canvas.setFont(PDF_FONT_BOLD, 9.2)
        canvas.drawCentredString(cx, cy - 3.15, number)
        canvas.restoreState()


class PdfFigureImage(Flowable):
    def __init__(self, figure: Figure, max_width: float, max_height: float):
        super().__init__()
        self.figure = figure
        self.max_width = max_width
        self.max_height = max_height
        self.source_width, self.source_height = _figure_size(figure)
        self.width = 0
        self.height = 0

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        scale = min(
            self.max_width / self.source_width,
            self.max_height / self.source_height,
            avail_width / self.source_width,
            1.0,
        )
        self.width = self.source_width * scale
        self.height = self.source_height * scale
        return self.width, self.height

    def draw(self) -> None:
        self.canv.drawImage(
            ImageReader(str(self.figure.image_path)),
            0,
            0,
            width=self.width,
            height=self.height,
            preserveAspectRatio=False,
            mask="auto",
        )
        if self.figure.callouts:
            draw_figure_callouts(
                self.canv,
                self.figure,
                self.width,
                self.height,
                self.source_width,
                self.source_height,
            )


def build_qa_figure_pdfs(figures: list[Figure], output_dir: Path | None = None) -> list[Path]:
    """Write review PDFs at the exact image size used in the final handbook."""
    from reportlab.pdfgen import canvas as pdf_canvas

    register_pdf_fonts()
    output_dir = output_dir or QA_DIR / "figure_review"
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for index, figure in enumerate(figures, start=1):
        flowable = PdfFigureImage(
            figure,
            max_width=A4[0] - 36 * mm,
            max_height=A4[1] - 65 * mm,
        )
        display_width, display_height = flowable.wrap(A4[0] - 36 * mm, A4[1] - 65 * mm)
        output_path = output_dir / f"{index:02d}-{figure.image_path.stem}.pdf"
        pdf = pdf_canvas.Canvas(str(output_path), pagesize=(display_width, display_height))
        flowable.drawOn(pdf, 0, 0)
        pdf.showPage()
        pdf.save()
        outputs.append(output_path)
    return outputs


def callout_legend(figure: Figure) -> str:
    labels: list[str] = []
    for item in figure.callouts:
        if not isinstance(item, dict):
            continue
        number = item.get("n", item.get("number", item.get("label", "")))
        label = item.get("label") if item.get("n") is not None else item.get("text", item.get("target", ""))
        if number and label:
            labels.append(f"{number} — {label}")
    return "; ".join(labels)


def register_pdf_fonts() -> None:
    """Embed fonts with Cyrillic glyphs so every PDF viewer renders Russian text."""
    fonts = {
        PDF_FONT: "/System/Library/Fonts/Supplemental/Arial.ttf",
        PDF_FONT_BOLD: "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        PDF_FONT_ITALIC: "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
        PDF_FONT_BOLD_ITALIC: "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf",
    }
    for name, path in fonts.items():
        if name not in pdfmetrics.getRegisteredFontNames():
            if not Path(path).exists():
                raise FileNotFoundError(f"Не найден шрифт для PDF: {path}")
            pdfmetrics.registerFont(TTFont(name, path))
    pdfmetrics.registerFontFamily(
        PDF_FONT,
        normal=PDF_FONT,
        bold=PDF_FONT_BOLD,
        italic=PDF_FONT_ITALIC,
        boldItalic=PDF_FONT_BOLD_ITALIC,
    )


def pdf_styles() -> dict[str, ParagraphStyle]:
    register_pdf_fonts()
    base = getSampleStyleSheet()
    return {
        "body": ParagraphStyle(
            "ManualBody", parent=base["BodyText"], fontName=PDF_FONT, fontSize=9.4,
            leading=13.2, textColor=PDF_INK, spaceAfter=6.5, alignment=TA_LEFT,
            allowWidows=0, allowOrphans=0,
        ),
        "h1": ParagraphStyle("ManualH1", parent=base["Heading1"], fontName=PDF_FONT_BOLD, fontSize=21,
            leading=25, textColor=PDF_PURPLE_DARK, spaceBefore=2, spaceAfter=15, keepWithNext=True),
        "h2": ParagraphStyle("ManualH2", parent=base["Heading2"], fontName=PDF_FONT_BOLD, fontSize=15,
            leading=18, textColor=PDF_PURPLE_DARK, spaceBefore=12, spaceAfter=7, keepWithNext=True),
        "h3": ParagraphStyle("ManualH3", parent=base["Heading3"], fontName=PDF_FONT_BOLD, fontSize=11.5,
            leading=14, textColor=PDF_INK, spaceBefore=9, spaceAfter=5, keepWithNext=True),
        "small": ParagraphStyle("ManualSmall", parent=base["BodyText"], fontName=PDF_FONT, fontSize=8,
            leading=10.5, textColor=PDF_MUTED, spaceAfter=4),
        "quote": ParagraphStyle("ManualQuote", parent=base["BodyText"], fontName=PDF_FONT_ITALIC, fontSize=9.2,
            leading=12.4, textColor=PDF_INK, leftIndent=10, rightIndent=8, borderColor=PDF_PURPLE,
            borderWidth=2, borderPadding=7, backColor=PDF_PURPLE_PALE, spaceBefore=4, spaceAfter=8),
        "list": ParagraphStyle("ManualList", parent=base["BodyText"], fontName=PDF_FONT, fontSize=9.2,
            leading=12.5, textColor=PDF_INK, spaceAfter=3.5),
        "caption": ParagraphStyle("ManualCaption", parent=base["BodyText"], fontName=PDF_FONT_BOLD, fontSize=8.6,
            leading=11, textColor=PDF_PURPLE_DARK, alignment=TA_CENTER, spaceBefore=5, spaceAfter=3),
        "legend": ParagraphStyle("ManualLegend", parent=base["BodyText"], fontName=PDF_FONT, fontSize=7.8,
            leading=10.2, textColor=PDF_MUTED, spaceAfter=8),
        "table": ParagraphStyle("ManualTable", parent=base["BodyText"], fontName=PDF_FONT, fontSize=7.7,
            leading=10, textColor=PDF_INK, spaceAfter=0),
        "tablehead": ParagraphStyle("ManualTableHead", parent=base["BodyText"], fontName=PDF_FONT_BOLD, fontSize=7.8,
            leading=10, textColor=colors.white, spaceAfter=0),
        "coverbrand": ParagraphStyle("CoverBrand", parent=base["Title"], fontName=PDF_FONT_BOLD, fontSize=18,
            leading=21, textColor=PDF_PURPLE_DARK, alignment=TA_LEFT, spaceAfter=4),
        "coverkicker": ParagraphStyle("CoverKicker", parent=base["BodyText"], fontName=PDF_FONT_BOLD, fontSize=10,
            leading=14, textColor=PDF_PURPLE, alignment=TA_LEFT, spaceAfter=8),
        "covertitle": ParagraphStyle("CoverTitle", parent=base["Title"], fontName=PDF_FONT_BOLD, fontSize=29,
            leading=34, textColor=PDF_INK, alignment=TA_LEFT, spaceAfter=10),
        "coversubtitle": ParagraphStyle("CoverSubtitle", parent=base["BodyText"], fontName=PDF_FONT, fontSize=13,
            leading=18, textColor=PDF_MUTED, alignment=TA_LEFT),
        "toc_title": ParagraphStyle("ManualTOCTitle", parent=base["Heading1"], fontName=PDF_FONT_BOLD, fontSize=18,
            leading=21, textColor=PDF_PURPLE_DARK, spaceBefore=0, spaceAfter=9, keepWithNext=True),
        "toc0": ParagraphStyle("ManualTOC0", parent=base["BodyText"], fontName=PDF_FONT_BOLD, fontSize=9.4,
            leading=11.2, textColor=PDF_PURPLE_DARK, leftIndent=0, firstLineIndent=0, spaceBefore=1, spaceAfter=0),
        "toc1": ParagraphStyle("ManualTOC1", parent=base["BodyText"], fontName=PDF_FONT, fontSize=7.8,
            leading=8.6, textColor=PDF_INK, leftIndent=12, firstLineIndent=0, spaceAfter=0),
    }


class HandbookPdfTemplate(BaseDocTemplate):
    def __init__(self, filename: str, title: str, **kwargs: Any) -> None:
        self.handbook_title = title
        super().__init__(filename, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                         topMargin=20 * mm, bottomMargin=18 * mm, title=title, author="КоробВМС", **kwargs)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="body",
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates(PageTemplate(id="manual", frames=frame, onPage=self._draw_page))

    def _draw_page(self, canvas: Any, doc: Any) -> None:
        if doc.page == 1:
            return
        canvas.saveState()
        width, height = A4
        canvas.setStrokeColor(PDF_RULE)
        canvas.setLineWidth(0.6)
        canvas.line(self.leftMargin, height - 14 * mm, width - self.rightMargin, height - 14 * mm)
        canvas.setFont(PDF_FONT_BOLD, 7.6)
        canvas.setFillColor(PDF_PURPLE_DARK)
        canvas.drawString(self.leftMargin, height - 11.2 * mm, "КОРОБВМС  ·  РУКОВОДСТВО WMS")
        canvas.setStrokeColor(PDF_RULE)
        canvas.line(self.leftMargin, 12 * mm, width - self.rightMargin, 12 * mm)
        canvas.setFont(PDF_FONT, 8)
        canvas.setFillColor(PDF_MUTED)
        canvas.drawRightString(width - self.rightMargin, 8 * mm, f"Страница {doc.page}")
        canvas.restoreState()

    def afterFlowable(self, flowable: Flowable) -> None:
        heading = getattr(flowable, "manual_heading", None)
        if heading is None:
            return
        key = heading.bookmark
        self.canv.bookmarkPage(key)
        outline_level = heading.level - 1
        if 1 <= heading.level <= 3:
            self.canv.addOutlineEntry(heading.title, key, level=outline_level, closed=False)
        toc_level = 0 if heading.level == 1 else 1 if heading.level == 2 else None
        if toc_level is not None:
            self.notify("TOCEntry", (toc_level, heading.title, self.page, key))


def make_pdf_heading(text: str, style: ParagraphStyle, heading: Heading) -> Paragraph:
    paragraph = Paragraph(pdf_inline(text, heading.chapter, _CURRENT_HEADINGS), style)
    paragraph.manual_heading = heading
    return paragraph


def _figure_flowables(
    figure: Figure,
    styles: dict[str, ParagraphStyle],
    max_image_height: float | None = None,
) -> list[Flowable]:
    max_width = A4[0] - 36 * mm
    max_height = max_image_height or A4[1] - 65 * mm
    image = PdfFigureImage(figure, max_width=max_width, max_height=max_height)
    image.hAlign = "CENTER"
    figure_flowables: list[Flowable] = [Spacer(1, 3 * mm), image]
    if figure.caption:
        figure_flowables.append(Paragraph(html.escape(figure.caption), styles["caption"]))
    legend = callout_legend(figure)
    if legend:
        figure_flowables.append(Paragraph(html.escape(legend), styles["legend"]))
    return figure_flowables


def _anchored_figure_max_height(
    heading: Paragraph,
    figure: Figure,
    styles: dict[str, ParagraphStyle],
) -> float:
    """Reserve room for the anchor heading and the first figure's caption/legend."""
    content_width = A4[0] - 36 * mm
    frame_height = A4[1] - 38 * mm
    reserved = heading.wrap(content_width, frame_height)[1]
    reserved += heading.style.spaceBefore or 0
    reserved += heading.style.spaceAfter or 0
    reserved += 3 * mm + 16  # Figure spacer and a safety allowance for flowable spacing.
    extras: list[Paragraph] = []
    if figure.caption:
        extras.append(Paragraph(html.escape(figure.caption), styles["caption"]))
    legend = callout_legend(figure)
    if legend:
        extras.append(Paragraph(html.escape(legend), styles["legend"]))
    for paragraph in extras:
        reserved += paragraph.wrap(content_width, frame_height)[1]
        reserved += paragraph.style.spaceBefore or 0
        reserved += paragraph.style.spaceAfter or 0
    available = frame_height - reserved
    if available < 120:
        raise ValueError(
            f"Заголовок и подпись иллюстрации не оставляют безопасной высоты для кадра: {figure.image_path.name}"
        )
    return min(A4[1] - 65 * mm, available)


def _add_pdf_figure(
    story: list[Flowable],
    figure: Figure,
    chapter_index: int,
    figure_index: int,
    styles: dict[str, ParagraphStyle],
    heading: Paragraph | None = None,
) -> None:
    if heading is not None:
        max_height = _anchored_figure_max_height(heading, figure, styles)
        if figure.image_path.name == "tsd-login.png":
            max_height = max(120, max_height - 45)
        story.append(KeepTogether([heading, *_figure_flowables(figure, styles, max_height)]))
    else:
        story.append(KeepTogether(_figure_flowables(figure, styles)))


def chapter_story(chapters: list[Chapter], include_figures: bool = False) -> tuple[list[Flowable], list[Heading]]:
    global _CURRENT_HEADINGS
    _CURRENT_HEADINGS = make_heading_map(chapters)
    styles = pdf_styles()
    story: list[Flowable] = []
    story.extend(_cover_story(styles))
    story.append(PageBreak())
    story.append(Paragraph("Оглавление", styles["toc_title"]))
    toc = TableOfContents()
    toc.levelStyles = [styles["toc0"], styles["toc1"]]
    toc.dotsMinLevel = 0
    story.append(toc)
    story.append(PageBreak())

    figures = load_figures() if include_figures else []
    all_headings: list[Heading] = []
    figure_count = 0
    for chapter_index, chapter in enumerate(chapters, start=1):
        if chapter_index > 1:
            story.append(PageBreak())
        for block_index, block in enumerate(chapter.blocks):
            if block.kind == "heading" and block.heading:
                heading = block.heading
                all_headings.append(heading)
                style_name = "h1" if heading.level == 1 else "h2" if heading.level == 2 else "h3"
                heading_flowable = make_pdf_heading(block.content, styles[style_name], heading)
                if include_figures:
                    anchored_figures = figure_for(chapter, heading.title, figures)
                    for figure_index, figure in enumerate(anchored_figures):
                        figure_count += 1
                        _add_pdf_figure(
                            story,
                            figure,
                            chapter_index,
                            figure_count,
                            styles,
                            heading=heading_flowable if figure_index == 0 else None,
                        )
                        if figure_index == 0:
                            heading_flowable = None
                if heading_flowable is not None:
                    story.append(heading_flowable)
            elif block.kind == "paragraph":
                story.append(Paragraph(pdf_inline(block.content, chapter.path, _CURRENT_HEADINGS), styles["body"]))
            elif block.kind == "quote":
                story.append(Paragraph(pdf_inline(block.content, chapter.path, _CURRENT_HEADINGS), styles["quote"]))
            elif block.kind == "rule":
                story.extend([Spacer(1, 2 * mm), Table([[""]], colWidths=[A4[0] - 36 * mm], rowHeights=[0.7], style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), PDF_RULE)])), Spacer(1, 2 * mm)])
            elif block.kind == "list":
                ordered, start_number, items = block.content
                list_flowables: list[Flowable] = []
                for item_index, item in enumerate(items, start=start_number):
                    bullet = f"{item_index}." if ordered else "•"
                    list_flowables.append(Paragraph(
                        f'<font color="#{PURPLE}"><b>{bullet}</b></font>&nbsp;&nbsp;{pdf_inline(item, chapter.path, _CURRENT_HEADINGS)}',
                        ParagraphStyle("ManualListItem", parent=styles["list"], leftIndent=13, firstLineIndent=-13),
                    ))
                previous_is_heading = block_index > 0 and chapter.blocks[block_index - 1].kind == "heading"
                is_final_short_list = (
                    include_figures
                    and chapter_index == len(chapters)
                    and block_index == len(chapter.blocks) - 1
                    and len(items) <= 6
                    and previous_is_heading
                    and story
                    and getattr(story[-1], "manual_heading", None) is not None
                )
                if is_final_short_list:
                    heading_flowable = story.pop()
                    story.append(KeepTogether([heading_flowable, *list_flowables]))
                else:
                    story.extend(list_flowables)
            elif block.kind == "table":
                rows: list[list[Paragraph]] = []
                for row_index, row in enumerate(block.content):
                    style = styles["tablehead"] if row_index == 0 else styles["table"]
                    rows.append([Paragraph(pdf_inline(cell, chapter.path, _CURRENT_HEADINGS), style) for cell in row])
                col_count = max((len(row) for row in rows), default=1)
                widths = [(A4[0] - 36 * mm) / col_count] * col_count
                table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
                table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), PDF_PURPLE),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PDF_PURPLE_PALE]),
                    ("GRID", (0, 0), (-1, -1), 0.35, PDF_RULE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]))
                story.append(table)
                story.append(Spacer(1, 3 * mm))
    return story, all_headings


_CURRENT_HEADINGS: dict[tuple[str, str], Heading] = {}


def _cover_story(styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    story: list[Flowable] = [Spacer(1, 28 * mm)]
    if LOGO_PATH.exists():
        logo = PdfImage(str(LOGO_PATH), width=44 * mm, height=44 * mm)
        logo.hAlign = "LEFT"
        story.append(logo)
    story.extend([
        Spacer(1, 13 * mm),
        Paragraph("КОРОБВМС", styles["coverbrand"]),
        Paragraph("ЕДИНОЕ РУКОВОДСТВО ПО ПРОЦЕССАМ WMS", styles["coverkicker"]),
        Paragraph("Фулфилмент, маркетплейсы и складской учёт", styles["covertitle"]),
        Paragraph(
            "Приёмка и возвраты · FBS и маркировка · остатки, ячейки и расчёты<br/>FBO · Stage&nbsp;G",
            styles["coversubtitle"],
        ),
        Spacer(1, 2 * mm),
        Paragraph("Редакция: 09.10.2026", styles["small"]),
        Spacer(1, 10 * mm),
        Table([[""]], colWidths=[110 * mm], rowHeights=[1.5], style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), PDF_PURPLE)])),
        Spacer(1, 6 * mm),
        Paragraph("Пошаговые инструкции для селлера и сотрудника фулфилмента", styles["small"]),
    ])
    return story


def build_pdf(chapters: list[Chapter], output: Path, include_figures: bool = False) -> None:
    register_pdf_fonts()
    output.parent.mkdir(parents=True, exist_ok=True)
    story, _ = chapter_story(chapters, include_figures=include_figures)
    doc = HandbookPdfTemplate(str(output), "Руководство WMS · КоробВМС", allowSplitting=1)
    doc.multiBuild(story, maxPasses=4)


def set_docx_styles(doc: Any) -> None:
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(10)
    normal.font.color.rgb = RGBColor.from_string(INK)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.12
    heading_settings = {
        "Heading 1": (19, PURPLE_DARK, 12, 7),
        "Heading 2": (14, PURPLE_DARK, 11, 5),
        "Heading 3": (11.5, INK, 9, 4),
    }
    for name, (size, color, before, after) in heading_settings.items():
        style = styles[name]
        style.font.name = "Arial"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True
    styles["Title"].font.name = "Arial"
    styles["Title"].font.size = Pt(30)
    styles["Title"].font.bold = True
    styles["Title"].font.color.rgb = RGBColor.from_string(INK)
    styles["Subtitle"].font.name = "Arial"
    styles["Subtitle"].font.size = Pt(13)
    styles["Subtitle"].font.color.rgb = RGBColor.from_string(MUTED)
    for style_name in ("List Bullet", "List Number"):
        style = styles[style_name]
        style.font.name = "Arial"
        style.font.size = Pt(10)
        style.paragraph_format.space_after = Pt(3)


def setup_docx_header_footer(section: Any) -> None:
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.top_margin = Mm(26)
    section.bottom_margin = Mm(18)
    section.left_margin = Mm(19)
    section.right_margin = Mm(19)
    section.different_first_page_header_footer = True
    header = section.header
    paragraph = header.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    if LOGO_PATH.exists():
        paragraph.add_run().add_picture(str(LOGO_PATH), width=Inches(0.25))
    run = paragraph.add_run("  КоробВМС  ·  Руководство WMS")
    run.bold = True
    run.font.name = "Arial"
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor.from_string(PURPLE_DARK)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = footer.add_run("Страница ")
    run.font.name = "Arial"
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor.from_string(MUTED)
    add_field(footer, " PAGE ")


def add_docx_toc(doc: Any, chapters: list[Chapter]) -> None:
    heading = doc.add_heading("Оглавление", level=1)
    heading.paragraph_format.keep_with_next = True
    for chapter in chapters:
        title_heading = next((item for item in chapter.headings if item.level == 1), None)
        if title_heading:
            paragraph = doc.add_paragraph()
            paragraph.paragraph_format.left_indent = Mm(0)
            paragraph.paragraph_format.space_after = Pt(4)
            add_internal_hyperlink(
                paragraph,
                title_heading.bookmark,
                title_heading.title,
                bold=True,
                font_size_pt=10,
                color_hex=PURPLE_DARK,
            )
        for item in chapter.headings:
            if item.level != 2:
                continue
            paragraph = doc.add_paragraph()
            paragraph.paragraph_format.left_indent = Mm(6)
            paragraph.paragraph_format.space_after = Pt(2)
            add_internal_hyperlink(
                paragraph,
                item.bookmark,
                item.title,
                font_size_pt=9,
                color_hex=INK,
            )


def build_docx(chapters: list[Chapter], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    set_docx_styles(doc)
    section = doc.sections[0]
    setup_docx_header_footer(section)
    props = doc.core_properties
    props.title = "Руководство WMS · КоробВМС"
    props.subject = "Единое руководство по процессам фулфилмента"
    props.author = "КоробВМС"
    props.keywords = "WMS, фулфилмент, приёмка, FBS, FBO, остатки"

    doc.add_paragraph().paragraph_format.space_after = Pt(18)
    if LOGO_PATH.exists():
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(18)
        p.add_run().add_picture(str(LOGO_PATH), width=Inches(1.45))
    brand = doc.add_paragraph()
    brand.paragraph_format.space_after = Pt(3)
    run = brand.add_run("КОРОБВМС")
    run.bold = True
    run.font.name = "Arial"
    run.font.size = Pt(17)
    run.font.color.rgb = RGBColor.from_string(PURPLE_DARK)
    kicker = doc.add_paragraph()
    kicker.paragraph_format.space_after = Pt(18)
    run = kicker.add_run("ЕДИНОЕ РУКОВОДСТВО ПО ПРОЦЕССАМ WMS")
    run.bold = True
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor.from_string(PURPLE)
    title = doc.add_paragraph(style="Title")
    title.add_run("Фулфилмент, маркетплейсы и складской учёт")
    subtitle = doc.add_paragraph(style="Subtitle")
    subtitle.add_run("Приёмка и возвраты · FBS и маркировка · остатки, ячейки и расчёты\nFBO · Stage\u00a0G")
    revision = doc.add_paragraph()
    revision.paragraph_format.space_after = Pt(18)
    run = revision.add_run("Редакция: 09.10.2026")
    run.font.name = "Arial"
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor.from_string(MUTED)
    doc.add_page_break()

    headings = make_heading_map(chapters)
    add_docx_toc(doc, chapters)
    doc.add_page_break()
    bookmark_id = 1
    for chapter_index, chapter in enumerate(chapters, start=1):
        if chapter_index > 1:
            doc.add_page_break()
        for block in chapter.blocks:
            if block.kind == "heading" and block.heading:
                heading = block.heading
                level = 1 if heading.level == 1 else min(heading.level, 3)
                paragraph = doc.add_heading(level=level)
                add_docx_inline(paragraph, block.content, chapter.path, headings)
                add_bookmark(paragraph, heading.bookmark, bookmark_id)
                bookmark_id += 1
            elif block.kind == "paragraph":
                paragraph = doc.add_paragraph()
                add_docx_inline(paragraph, block.content, chapter.path, headings)
            elif block.kind == "quote":
                paragraph = doc.add_paragraph()
                paragraph.paragraph_format.left_indent = Mm(5)
                paragraph.paragraph_format.right_indent = Mm(4)
                paragraph.paragraph_format.space_before = Pt(4)
                paragraph.paragraph_format.space_after = Pt(8)
                ppr = paragraph._p.get_or_add_pPr()
                shading = OxmlElement("w:shd")
                shading.set(qn("w:fill"), PURPLE_PALE)
                ppr.append(shading)
                add_docx_inline(paragraph, block.content, chapter.path, headings)
                for run in paragraph.runs:
                    run.italic = True
            elif block.kind == "list":
                ordered, start_number, items = block.content
                for item_index, item in enumerate(items, start=start_number):
                    paragraph = doc.add_paragraph()
                    paragraph.paragraph_format.left_indent = Mm(7)
                    paragraph.paragraph_format.first_line_indent = Mm(-5)
                    paragraph.paragraph_format.space_after = Pt(3)
                    paragraph.add_run(f"{item_index}. " if ordered else "• ")
                    add_docx_inline(paragraph, item, chapter.path, headings)
            elif block.kind == "table":
                add_docx_table(doc, block.content, chapter.path, headings)
            elif block.kind == "rule":
                paragraph = doc.add_paragraph()
                ppr = paragraph._p.get_or_add_pPr()
                borders = OxmlElement("w:pBdr")
                bottom = OxmlElement("w:bottom")
                bottom.set(qn("w:val"), "single")
                bottom.set(qn("w:sz"), "6")
                bottom.set(qn("w:color"), PURPLE)
                borders.append(bottom)
                ppr.append(borders)
    settings = doc.settings.element
    update_fields = settings.find(qn("w:updateFields"))
    if update_fields is None:
        update_fields = OxmlElement("w:updateFields")
        settings.append(update_fields)
    update_fields.set(qn("w:val"), "true")
    doc.save(output)


def load_chapters(allow_missing: bool = False) -> list[Chapter]:
    missing: list[str] = []
    chapters: list[Chapter] = []
    for index, filename in enumerate(CHAPTER_FILES, start=1):
        path = MANUAL_DIR / filename
        if not path.exists():
            missing.append(filename)
            continue
        chapters.append(parse_chapter(path, index))
    if missing and not allow_missing:
            raise FileNotFoundError("Ожидаются все пять глав; отсутствуют: " + ", ".join(missing))
    if not chapters:
        raise FileNotFoundError("Не найдены Markdown-главы для сборки.")
    if missing:
        print("PREVIEW ONLY; временно пропущены: " + ", ".join(missing), file=sys.stderr)
    return chapters


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true", help="Собрать пробную версию из доступных глав в Руководство/.qa")
    parser.add_argument("--illustrated", action="store_true", help="Дополнительно собрать PDF с изображениями из manifests")
    parser.add_argument("--allow-missing", action="store_true", help="Разрешить временную сборку, если не все главы готовы")
    args = parser.parse_args()
    preview = args.preview or args.allow_missing
    chapters = load_chapters(allow_missing=preview)
    if preview:
        output_dir = QA_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = output_dir / "WMS_Руководство_текст_preview.pdf"
        docx_path = output_dir / "WMS_Руководство_текст_preview.docx"
    else:
        output_dir = KB_DIR
        pdf_path = output_dir / "WMS_Руководство_текст.pdf"
        docx_path = output_dir / "WMS_Руководство_текст.docx"
    build_pdf(chapters, pdf_path, include_figures=False)
    build_docx(chapters, docx_path)
    print(f"PDF: {pdf_path}")
    print(f"DOCX: {docx_path}")
    if args.illustrated:
        figures = load_figures()
        if not figures:
            raise RuntimeError("Иллюстрированный PDF не создан: в согласованных manifests пока нет доступных изображений.")
        validate_figures(chapters, figures)
        if preview:
            review_pdfs = build_qa_figure_pdfs(figures)
            print("Figure review PDFs:")
            for review_pdf in review_pdfs:
                print(f"- {review_pdf}")
        illustrated_path = (QA_DIR if preview else KB_DIR) / (
            "WMS_Руководство_с_иллюстрациями_preview.pdf" if preview else "WMS_Руководство_с_иллюстрациями.pdf"
        )
        build_pdf(chapters, illustrated_path, include_figures=True)
        print(f"Illustrated PDF: {illustrated_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
