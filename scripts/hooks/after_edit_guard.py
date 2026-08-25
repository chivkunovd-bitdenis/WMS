#!/usr/bin/env python3
"""После правки интерфейса — сразу сторож канона, а не через неделю в ревью."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    target = str(payload.get("tool_input", {}).get("file_path", ""))
    if "frontend/src" not in target:
        return 0

    result = subprocess.run(
        [sys.executable, "scripts/ui/ui_guard.py"], cwd=ROOT, capture_output=True, text=True
    )
    if result.returncode != 0:
        print(result.stdout + result.stderr, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
