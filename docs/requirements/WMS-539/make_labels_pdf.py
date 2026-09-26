"""WMS-539: PDF with one 58x40 mm label per storage cell.

Top: cell name (as in the client's file). Middle: CODE128 of the standard system
barcode (LOC-…) — the value every WMS scan field looks up. Bottom: the barcode
value in text. Usage: python3 make_labels_pdf.py CELLS_JSON OUT_PDF
"""
import json
import sys

from reportlab.graphics.barcode.code128 import Code128
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

pdfmetrics.registerFont(TTFont("ArialBold", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"))
pdfmetrics.registerFont(TTFont("CourierNew", "/System/Library/Fonts/Supplemental/Courier New.ttf"))

W, H = 58 * mm, 40 * mm
QUIET = 2.5 * mm  # white zone on each side of the bars
cells = json.load(open(sys.argv[1], encoding="utf-8"))
c = canvas.Canvas(sys.argv[2], pagesize=(W, H))
c.setTitle("Этикетки ячеек ArtMaks")
for cell in cells:
    name, value = cell["code"], cell["barcode"]
    size = 17
    while pdfmetrics.stringWidth(name, "ArialBold", size) > W - 4 * mm:
        size -= 0.5
    c.setFont("ArialBold", size)
    c.drawCentredString(W / 2, H - 2 * mm - size * 0.75, name)
    probe = Code128(value, barWidth=1, barHeight=20 * mm, quiet=0)
    bar_width = (W - 2 * QUIET) / probe.width
    bc = Code128(value, barWidth=bar_width, barHeight=20 * mm, quiet=0)
    bc.drawOn(c, (W - bc.width) / 2, 7 * mm)
    c.setFont("CourierNew", 8)
    c.drawCentredString(W / 2, 3 * mm, value)
    c.showPage()
c.save()
print(len(cells), "labels ->", sys.argv[2])
