#!/usr/bin/env python3
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TestCase:
    tc_id: str
    title: str


TC_HEADING_RE = re.compile(r"^###\s+(TC-[A-Z0-9-]+)\s+(.*)\s*$")
TC_MENTION_RE = re.compile(r"TC-(?:S\d{2}-\d{3}|NEW[-\w]*)", re.IGNORECASE)


def parse_tc_catalog(path: Path) -> list[TestCase]:
    out: list[TestCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = TC_HEADING_RE.match(line)
        if not m:
            continue
        out.append(TestCase(tc_id=m.group(1).strip(), title=m.group(2).strip()))
    return out


def scan_e2e_mentions(e2e_dir: Path) -> dict[str, set[str]]:
    """Return tc_id -> set(spec relative paths)."""
    mentions: dict[str, set[str]] = {}
    for spec in sorted(e2e_dir.glob("*.spec.ts")):
        text = spec.read_text(encoding="utf-8")
        found = {m.group(0).upper() for m in TC_MENTION_RE.finditer(text)}
        for tc in found:
            mentions.setdefault(tc, set()).add(spec.name)
    return mentions


def render_markdown(cases: list[TestCase], mentions: dict[str, set[str]]) -> str:
    total = len(cases)
    covered = sum(1 for tc in cases if tc.tc_id.upper() in mentions)
    lines: list[str] = []
    lines.append("# TC automation coverage (Playwright e2e)")
    lines.append("")
    lines.append(
        f"- Catalog: `docs/IMPLEMENTED_PRODUCT_SCENARIOS_TEST_CASES_EN.md` ({total} TC headings)"
    )
    lines.append(f"- Covered by e2e (TC mentioned in `frontend/tests-e2e/*.spec.ts`): {covered}/{total}")
    lines.append("")
    lines.append("## Coverage table")
    lines.append("")
    lines.append("| TC-ID | Title | Automated (e2e) | Specs |")
    lines.append("|------|-------|------------------|-------|")
    for tc in cases:
        key = tc.tc_id.upper()
        specs = sorted(mentions.get(key, set()))
        automated = "Y" if specs else "N"
        spec_cell = ", ".join(f"`{s}`" for s in specs) if specs else ""
        title = tc.title.replace("|", "\\|")
        lines.append(f"| `{tc.tc_id}` | {title} | {automated} | {spec_cell} |")
    lines.append("")
    lines.append("## Gaps (not yet automated)")
    lines.append("")
    for tc in cases:
        if tc.tc_id.upper() not in mentions:
            lines.append(f"- `{tc.tc_id}` — {tc.title}")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- This report is a *traceability map*, not a proof of correctness.")
    lines.append("- A TC is considered automated if its ID is mentioned in a Playwright spec (title or comment).")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    catalog = repo / "docs" / "IMPLEMENTED_PRODUCT_SCENARIOS_TEST_CASES_EN.md"
    e2e_dir = repo / "frontend" / "tests-e2e"
    out_doc = repo / "docs" / "TC_AUTOMATION_COVERAGE.md"

    cases = parse_tc_catalog(catalog)
    mentions = scan_e2e_mentions(e2e_dir)
    out_doc.write_text(render_markdown(cases, mentions), encoding="utf-8")
    print(f"Wrote {out_doc.relative_to(repo)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

