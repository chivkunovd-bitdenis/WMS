"""Extract only the four verified long-sleeve labels; no provider or database writes."""
import json
from pathlib import Path

from pypdf import PdfReader, PdfWriter

root = Path(__file__).resolve().parents[3]
out = root / "output/pdf/artmaks-unused-20261001"
snapshot = json.loads((out / "verification.json").read_text())
wanted = ["5850207 7242", "5850208 1619", "5851386 2923", "5851430 9273"]
by_code = {row["sticker_code"]: row for row in snapshot["rows"]}
reader = PdfReader(out / "WB-unused-QR-58x40.pdf")
writer = PdfWriter()
for code in wanted:
    row = by_code[code]
    assert row["sku_code"] in ("ФА_МОД202а/052/46", "ФА_МОД202а/052/52")
    writer.add_page(reader.pages[row["pdf_page"] - 1])
writer.add_metadata({"/Title": "Четыре QR для оставшихся лонгсливов - 58 x 40 мм"})
target = out / "QR-4-longsleeves-only-58x40.pdf"
with target.open("wb") as stream:
    writer.write(stream)
assert len(PdfReader(target).pages) == 4
print(target)
