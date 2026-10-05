"""One-time architectural boundary for WMS-653 (C12)."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_wms653_diff_does_not_add_storage_status_background_retry_or_timer() -> None:
    """C12: WMS-653 remains presentation over the existing delivery operation."""
    _git("rev-parse", "--verify", "origin/etalon")
    changed = {
        line.strip()
        for line in _git("diff", "--name-only", "origin/etalon...HEAD").splitlines()
        if line.strip()
    }

    forbidden_roots = (
        "backend/alembic/versions/",
        "backend/app/models/",
        "backend/app/tasks/",
    )
    forbidden = sorted(
        path for path in changed if path.startswith(forbidden_roots)
    )
    assert forbidden == [], (
        "WMS-653 must not add a table/migration, model-backed status or background task: "
        f"{forbidden}"
    )

    product_diff = _git(
        "diff",
        "--unified=0",
        "origin/etalon...HEAD",
        "--",
        "backend/app",
        "frontend/src",
        ":(exclude)frontend/src/**/*.test.ts",
        ":(exclude)frontend/src/**/*.test.tsx",
    )
    added = "\n".join(
        line[1:]
        for line in product_diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    forbidden_additions = {
        "setInterval(": "automatic polling/timer",
        "setTimeout(": "automatic timer",
        "BackgroundTasks(": "background task",
        "@celery_app.task": "Celery task",
    }
    found = [label for marker, label in forbidden_additions.items() if marker in added]
    assert found == [], f"WMS-653 added forbidden automation: {found}"

    # The neighbouring scan/print regressions remain part of the suite: this
    # task may reuse the common Alert area but must not replace those flows.
    for relative in (
        "backend/tests/test_fbs_kiz.py",
        "backend/tests/test_fbs_print_assets.py",
        "frontend/src/screens/v2/FfFbsSupplyWorkspace.scan.dom.test.tsx",
    ):
        assert (ROOT / relative).is_file(), f"neighbour regression disappeared: {relative}"
