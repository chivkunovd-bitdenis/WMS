#!/usr/bin/env python3
"""Границы наряда действуют и для правок через shell.

Хуки на Edit/Write закрывают только «культурный» путь: агент может изменить файл
через python3/sed внутри Bash и пройти мимо запрета — я сам так сделал, пока
проверял визуальные эталоны. Поэтому после каждой команды сверяем, что реально
изменилось в рабочем дереве, а не что агент собирался изменить.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from naryad_state import current_slug  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def changed_now() -> set[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain", "frontend/src"], cwd=ROOT, capture_output=True, text=True
    )
    return {line[3:].strip() for line in result.stdout.splitlines() if line[3:].strip()}


def main() -> int:
    sys.stdin.read()
    slug = current_slug()
    if not slug:
        return 0  # без наряда правки блокирует другой хук, здесь дублировать нечего

    folder = ROOT / "tasks" / slug
    naryad = (folder / "NARYAD.md").read_text(encoding="utf-8") if (folder / "NARYAD.md").exists() else ""
    allowed = set(re.findall(r"^- `([^`]+)`$", naryad, re.M))
    baseline_file = folder / "baseline-dirty.txt"
    baseline = set(baseline_file.read_text(encoding="utf-8").split()) if baseline_file.exists() else set()

    trespass = sorted(
        path
        for path in changed_now() - baseline
        if path not in allowed and "/ui-kit/" not in path
    )
    if trespass:
        listed = "\n".join(f"  {item}" for item in trespass)
        print(
            f"Изменены файлы вне границ наряда {slug}:\n{listed}\n"
            "Верни их в исходное состояние или заведи наряд, который их включает "
            "(общие файлы — через --shared).",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
