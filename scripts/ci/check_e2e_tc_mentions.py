#!/usr/bin/env python3
"""
When e2e specs change, require each touched file to reference at least one TC-ID
(TC-Sxx-yyy or TC-NEW) in a comment or test title — links automation to catalog.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

TC_PATTERN = re.compile(r"TC-(?:S\d{2}-\d{3}|NEW[-\w]*)", re.IGNORECASE)
REPO_ROOT = Path(__file__).resolve().parents[2]
E2E_PREFIX = REPO_ROOT / "frontend" / "tests-e2e"


def changed_spec_files(base_sha: str, head_sha: str) -> list[Path]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base_sha}...{head_sha}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        print(out.stderr, file=sys.stderr)
        return []
    paths: list[Path] = []
    for line in out.stdout.splitlines():
        raw = line.strip()
        if not raw.endswith(".spec.ts"):
            continue
        p = (REPO_ROOT / raw).resolve()
        try:
            p.relative_to(E2E_PREFIX.resolve())
        except ValueError:
            continue
        paths.append(p)
    return paths


def file_mentions_tc(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    return TC_PATTERN.search(text) is not None


def main() -> int:
    base = os.environ.get("PR_BASE_SHA", "").strip()
    head = os.environ.get("PR_HEAD_SHA", "").strip()
    if not base or not head:
        print("skip: PR_BASE_SHA / PR_HEAD_SHA not set", file=sys.stderr)
        return 0
    if not (REPO_ROOT / ".git").exists():
        print("skip: no .git", file=sys.stderr)
        return 0
    files = changed_spec_files(base, head)
    if not files:
        return 0
    bad = [p for p in files if not file_mentions_tc(p)]
    if bad:
        rel = "\n".join(f"  - {p.relative_to(REPO_ROOT)}" for p in bad)
        print(
            "error: changed Playwright specs must mention at least one TC-ID "
            "(TC-Sxx-yyy or TC-NEW-*) in a comment or test title:\n" + rel,
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
