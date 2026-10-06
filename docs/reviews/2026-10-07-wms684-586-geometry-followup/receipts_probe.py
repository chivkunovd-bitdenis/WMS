"""Inspect retained API bytes only; no database, app or browser access."""
import json
from pathlib import Path

import fitz

OUT = Path(__file__).resolve().parent
COLUMNS = (24, 48, 252, 356, 434, 522, 570, 618, 698)
results = []
for suffix in ("64", "128", "empty-lines"):
    doc = fitz.open(OUT / f"pagination-{suffix}.pdf")
    all_chars = []
    pages = []
    for number, page in enumerate(doc, 1):
        chars = [char for block in page.get_text("rawdict")["blocks"]
                 for line in block.get("lines", []) for span in line["spans"]
                 for char in span["chars"] if not char["c"].isspace()]
        assert chars and all(page.rect.contains(fitz.Rect(c["bbox"])) for c in chars)
        assert list(page.rect) == [0.0, 0.0, 842.0, 595.0]
        all_chars.extend(chars)
        pages.append({"page": number, "visible_chars": len(chars),
                      "all_char_bounds_inside_page": True, "rect": list(page.rect)})
    numbers = []
    for column in (0, 5, 6, 7):
        words = [word[4] for page in doc for word in page.get_text("words",
                 clip=fitz.Rect(COLUMNS[column], 0, COLUMNS[column+1], 595))
                 if word[4].lstrip("+-").isdigit()]
        expected = {0: ["1", "2", "3"], 5: ["5", "6", "4", "15"],
                    6: ["3", "4", "5", "12"], 7: ["-2", "-2", "+1", "-3"]}[column]
        assert words == expected, (suffix, column, words)
        numbers.append({"column": column, "values": words})
    assert sum(page.get_text().count("Итого") for page in doc) == 1
    assert "Итого" in doc[-1].get_text()
    name_chars = [c for c in all_chars if 48 <= c["bbox"][0] < 252]
    if suffix == "empty-lines":
        assert sum(c["c"] == "Х" for c in name_chars) == 1
        assert sum(c["c"] == "Я" for c in name_chars) == 1
    last_chars = [c for block in doc[-1].get_text("rawdict")["blocks"]
                  for line in block.get("lines", []) for span in line["spans"]
                  for c in span["chars"] if 48 <= c["bbox"][0] < 252]
    tail = next(c for c in reversed(last_chars) if c["c"] == ("Я" if suffix == "empty-lines" else "Х"))
    following = next(c for c in last_chars if c["c"] == ("Т" if suffix == "empty-lines" else "С"))
    # The unchanged old empty-line probe keeps the seeded following name (Товар…),
    # while the 64/128 probe sets it explicitly to Следующий товар.
    gap = following["bbox"][1] - tail["bbox"][3]
    assert gap > 0, (suffix, tail, following)
    separators = [item[1].y for drawing in doc[-1].get_drawings()
                  for item in drawing["items"] if item[0] == "l"
                  and abs(item[1].y - item[2].y) < 0.001
                  and tail["bbox"][3] < item[1].y < following["bbox"][1]]
    assert separators, (suffix, "separator must lie between glyphs")
    results.append({"case": suffix, "pages": pages, "numeric_columns_once": numbers,
                    "totals_once_on_last_page": True, "last_name_glyph": tail,
                    "following_name_glyph": following, "gap_pt": gap,
                    "separator_y_between_glyphs": separators})
(OUT / "receipts.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
print(json.dumps([{ "case": r["case"], "pages": len(r["pages"]), "gap_pt": r["gap_pt"]}
                  for r in results], ensure_ascii=False))
