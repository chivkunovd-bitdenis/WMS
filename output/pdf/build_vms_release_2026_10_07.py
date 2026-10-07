import json
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "output/pdf/vms-release-2026-10-07-content.json"
OUT = ROOT / "output/pdf/vms-release-2026-10-07.pdf"
pdfmetrics.registerFont(TTFont("Arial", "/System/Library/Fonts/Supplemental/Arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"))

NAVY = colors.HexColor("#142B45")
TEAL = colors.HexColor("#12A89D")
MUTED = colors.HexColor("#68798A")
RULE = colors.HexColor("#DFE7EB")
PALE = colors.HexColor("#EAF7F6")
TITLE_STYLE = ParagraphStyle("feature-title", fontName="Arial-Bold", fontSize=13, leading=16, textColor=NAVY)
BODY_STYLE = ParagraphStyle("feature-body", fontName="Arial", fontSize=10.6, leading=14.4, textColor=NAVY, spaceAfter=5)


def icon(c, x, top, num):
    """Small category pictograms, drawn as vector paths for reliable rendering."""
    c.saveState()
    c.setFillColor(PALE)
    c.circle(x + 13, top - 13, 13, fill=1, stroke=0)
    c.setStrokeColor(TEAL)
    c.setFillColor(colors.white)
    c.setLineWidth(1.5)
    if num == 6:  # Undo / reverse action
        c.arc(x + 7, top - 19, x + 20, top - 7, 55, 245)
        c.line(x + 8, top - 10, x + 8, top - 15)
        c.line(x + 8, top - 10, x + 13, top - 10)
    elif num in (3, 21, 22, 23):  # Box or label
        c.rect(x + 7, top - 19, 12, 11, fill=0, stroke=1)
        c.line(x + 7, top - 11, x + 13, top - 7)
        c.line(x + 19, top - 11, x + 13, top - 7)
        c.line(x + 13, top - 7, x + 13, top - 13)
    elif num in (4, 5, 7, 27):  # Barcode / scan
        for i, h in enumerate((8, 12, 6, 10, 13, 7, 11)):
            c.setLineWidth(1 if i % 2 else 1.7)
            c.line(x + 8 + i * 1.6, top - 19, x + 8 + i * 1.6, top - 19 + h)
    elif num == 10:  # Bidirectional handoff / sync
        c.arc(x + 7, top - 20, x + 20, top - 7, 35, 230)
        c.arc(x + 6, top - 20, x + 19, top - 7, 215, 230)
        c.line(x + 17, top - 9, x + 20, top - 10)
        c.line(x + 17, top - 9, x + 17, top - 12)
    elif num in (14, 17, 18):  # Document
        c.roundRect(x + 7, top - 19, 12, 12, 2, fill=0, stroke=1)
        c.line(x + 10, top - 10, x + 16, top - 10)
        c.line(x + 10, top - 13, x + 16, top - 13)
        c.line(x + 10, top - 16, x + 14, top - 16)
    elif num in (19, 20):  # Storage cells
        c.rect(x + 7, top - 19, 12, 12, fill=0, stroke=1)
        c.line(x + 13, top - 19, x + 13, top - 7)
        c.line(x + 7, top - 13, x + 19, top - 13)
    elif num in (25, 26):  # Mobile terminal
        c.roundRect(x + 9, top - 20, 8, 14, 2, fill=0, stroke=1)
        c.circle(x + 13, top - 17.5, 0.7, fill=1, stroke=0)
    elif num in (8, 15, 16):  # Filter
        c.line(x + 7, top - 8, x + 19, top - 8)
        c.line(x + 9, top - 8, x + 12, top - 13)
        c.line(x + 17, top - 8, x + 14, top - 13)
        c.line(x + 12, top - 13, x + 12, top - 18)
        c.line(x + 14, top - 13, x + 14, top - 18)
    else:  # Generic checklist / progress
        c.roundRect(x + 7, top - 19, 12, 12, 2, fill=0, stroke=1)
        c.line(x + 10, top - 13, x + 12, top - 16)
        c.line(x + 12, top - 16, x + 17, top - 10)
    c.restoreState()


def footer(c, page, total):
    w, _ = A4
    margin = 46
    c.setStrokeColor(RULE)
    c.line(margin, 34, w - margin, 34)
    c.setFillColor(MUTED)
    c.setFont("Arial", 8.5)
    c.drawString(margin, 20, "VMS · Обновления")
    c.drawRightString(w - margin, 20, f"{page:02d} / {total:02d}")


def main():
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    items = data["items"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    w, h = A4
    margin = 46
    x_icon = margin
    x_text = margin + 37
    text_width = w - margin - x_text
    top_start = h - 105
    bottom_limit = 51
    c = canvas.Canvas(str(OUT), pagesize=A4)
    c.setTitle(f'{data["title"]} · {data["date"]}')
    c.setAuthor("VMS")
    def page_header(page_no):
        c.setFillColor(TEAL)
        c.roundRect(margin, h - 55, 5, 27, 2, fill=1, stroke=0)
        c.setFillColor(NAVY)
        c.setFont("Arial-Bold", 23)
        c.drawString(margin + 15, h - 46, data["title"])
        c.setFillColor(MUTED)
        c.setFont("Arial", 10)
        c.drawRightString(w - margin, h - 40, data["date"])
        c.setStrokeColor(RULE)
        c.line(margin, h - 72, w - margin, h - 72)

    prepared = []
    for item in items:
        number = item["number"]
        title_text = f'<font color="#12A89D">{number:02d}</font>  {escape(item["title"])}'
        title_p = Paragraph(title_text, TITLE_STYLE)
        title_w, title_h = title_p.wrap(text_width, h)
        paras = [Paragraph(escape(s), BODY_STYLE) for s in item["paragraphs"]]
        para_sizes = [p.wrap(text_width, h) for p in paras]
        # Exact vertical cost of title, paragraphs, divider and 8 pt item gap.
        block_height = title_h + 17 + sum(ph for _, ph in para_sizes) + 5 * len(paras)
        prepared.append((item, title_p, title_h, paras, para_sizes, block_height))

    page_ranges = [(1, 6), (7, 12), (13, 17), (18, 22), (23, 27)]
    page_items = [prepared[start - 1:end] for start, end in page_ranges]
    for page_no, records in enumerate(page_items, 1):
        expected = sum(record[-1] for record in records)
        if expected > top_start - bottom_limit:
            raise ValueError(f"Page {page_no} content exceeds available height: {expected:.1f} pt")

    total_pages = len(page_items)
    for page, records in enumerate(page_items, 1):
        page_header(page)
        y = top_start
        for item, title_p, title_h, paras, para_sizes, block_height in records:
            icon(c, x_icon, y, item["number"])
            title_p.drawOn(c, x_text, y - title_h)
            cursor = y - title_h - 7
            for p, (_, ph) in zip(paras, para_sizes):
                p.drawOn(c, x_text, cursor - ph)
                cursor -= ph + 5
            divider_y = cursor - 2
            c.setStrokeColor(RULE)
            c.setLineWidth(0.6)
            c.line(x_text, divider_y, w - margin, divider_y)
            y = divider_y - 8
        if y < bottom_limit:
            raise ValueError(f"Page {page} content extends below footer area: {y:.1f} pt")
        footer(c, page, total_pages)
        if page < total_pages:
            c.showPage()
    c.save()


if __name__ == "__main__":
    main()
