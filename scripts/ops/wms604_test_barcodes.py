"""Generate the ten synthetic Code128 scanner inputs for WMS-604."""

from pathlib import Path

from reportlab.graphics.barcode.code128 import Code128
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

OUTPUT = Path(__file__).resolve().parents[2] / "docs/evidence/WMS-604/test-barcodes.pdf"
canvas = Canvas(str(OUTPUT), pagesize=A4, invariant=1)
canvas.setTitle("WMS scan check - 10 synthetic Code128 barcodes")
canvas.setFont("Helvetica-Bold", 16)
canvas.drawString(15 * mm, 280 * mm, "WMS SCAN CHECK - TEST ONLY")
canvas.setFont("Helvetica", 10)
canvas.drawString(15 * mm, 271 * mm, "sellerfocus.pro/packing-scan-check/")
for index in range(10):
    value = f"290000000{index + 1:04d}"
    x = (15 + (index % 2) * 100) * mm
    y = (232 - (index // 2) * 48) * mm
    barcode = Code128(value, barHeight=18 * mm, barWidth=0.38 * mm)
    barcode.drawOn(canvas, x, y)
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(x, y - 6 * mm, value)
    canvas.setFont("Helvetica", 9)
    canvas.drawString(x, y - 11 * mm, f"QR: WMS-PRINT-TEST-{index + 1:02d}")
canvas.save()
print(OUTPUT)
