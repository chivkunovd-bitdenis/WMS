"""Read retained API PDFs; no database, browser, network or product mutations."""
import json
from pathlib import Path

import fitz

OUT = Path(__file__).resolve().parent
results = []
for count in (64, 128):
    document = fitz.open(OUT / f"pagination-{count}.pdf")
    page = document[-1]
    chars = [
        char for block in page.get_text("rawdict")["blocks"]
        for line in block.get("lines", []) for span in line["spans"] for char in span["chars"]
        if 48 <= char["bbox"][0] < 252
    ]
    last_char = [char for char in chars if char["c"] == "Х"][-1]
    next_char = [char for char in chars if char["c"] == "С"][0]
    intersection = fitz.Rect(last_char["bbox"]) & fitz.Rect(next_char["bbox"])
    results.append({"lines": count, "last_name_char": last_char,
                    "next_row_first_char": next_char, "intersection_bbox": list(intersection),
                    "intersects": not intersection.is_empty})
    top = min(last_char["bbox"][1], next_char["bbox"][1]) - 12
    page.get_pixmap(matrix=fitz.Matrix(4, 4), clip=fitz.Rect(30, top, 260, top+48)).save(OUT / f"pagination-{count}-boundary.png")
(OUT / "boundary-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
assert not results[-1]["intersects"], "128-line name overlaps the following row; see retained raster and coordinates"
