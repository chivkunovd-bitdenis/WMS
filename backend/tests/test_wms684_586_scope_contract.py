"""One-time K7/N3 and A11/A12 scope checks against the fixed owner-approved base."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = "4b298efc95be7b4b6b7fe5665be9f3671f1fe747"
REQUIREMENTS_BASE = "21eb4dfc6"
VIEW = "frontend/src/screens/ff/FfInboundRequestView.tsx"


def old(path):
    return subprocess.check_output(["git", "show", f"{BASE}:{path}"], cwd=ROOT, text=True)


def read(path):
    return (ROOT / path).read_text()


def waybill(source):
    start = source.index('data-testid="ff-inbound-print-waybill"')
    return source[start : source.index("</Button>", start)]


def test_protected_waybill_and_existing_settings_are_unchanged():
    for path in (
        "frontend/src/utils/printInboundReceivingSheet.ts",
        "frontend/src/utils/printInboundReceivingSheet.test.ts",
    ):
        assert read(path) == old(path), path
    before, after = old(VIEW), read(VIEW)
    assert waybill(before) == waybill(after)
    # Labels/action changes do not authorize changing other inbound handlers.
    for start, end in (
        ("  const submitToWarehouse =", "  type InboundBoxPrintTarget ="),
        ("  const scanToReceiving =", "  const selectedPalletBoxes ="),
    ):
        assert (
            before[before.index(start) : before.index(end)]
            == after[after.index(start) : after.index(end)]
        )
    assert 'data-testid="ff-inbound-discrepancy-acts"' not in after
    assert not re.search(r"fetch\([^\n]*(?:discrepancy-acts|discrepancy_acts)", after)


def test_task_sources_and_lane_boundaries_preserved():
    w684, w586 = read("docs/requirements/WMS-684.md"), read("docs/requirements/WMS-586.md")
    for marker in ("обращения1", "WMS-659", "WMS-681", "приёмки", "физическая"):
        assert marker in w684, marker
    for marker in (
        "source463",
        "source467",
        "source471",
        "Telegram130",
        "Telegram134",
        "Telegram653",
        "план-факт",
        "не пустой",
        "WMS-680",
        "обращение33",
    ):
        assert marker.lower() in w586.lower(), marker
    # Historical accepted results must survive the extension verbatim.
    for task in ("WMS-684", "WMS-586"):
        path = f"docs/requirements/{task}.md"
        snapshot = subprocess.check_output(
            ["git", "show", f"{REQUIREMENTS_BASE}:{path}"], cwd=ROOT, text=True
        )
        historical = (
            snapshot.split("\n## Новое обращение")[0]
            if task == "WMS-586"
            else snapshot.split("\n\n## Подготовка")[0]
        )
        assert read(path).startswith(historical)
    paths = set(
        subprocess.check_output(
            ["git", "diff", "--name-only", BASE], cwd=ROOT, text=True
        ).splitlines()
    )
    forbidden = [
        p
        for p in paths
        if p in {"AGENTS.md", "CLAUDE.md"}
        or p.startswith(
            (
                ".github/",
                "scripts/ci/",
                "backend/migrations/",
                "backend/alembic/",
                "backend/app/models/",
                "frontend/src/guards/",
                "guards/",
            )
        )
    ]
    assert forbidden == []
