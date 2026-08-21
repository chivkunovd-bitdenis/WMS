#!/usr/bin/env python3
"""Сторож канона: запрещает НОВЫЕ отступления, не требуя переписать старое.

Прямой запрет «никакой своей вёрстки таблиц» сегодня сделал бы CI красным на 33 файлах,
и его бы просто отключили. Поэтому работает храповик: текущий уровень нарушений
записывается в базовую линию, а падение происходит только когда нарушений стало больше.
Экран, который и так в работе, переезжает на ui-kit и уменьшает базовую линию.

Запуск:  python3 scripts/ui/ui_guard.py           — проверить
         python3 scripts/ui/ui_guard.py --update  — пересобрать базовую линию
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / "src"
BASELINE = ROOT / "docs" / "product" / "ui-guard-baseline.json"
EXEMPT_DIRS = {"ui-kit", "mui"}

RULES = {
    # Своя вёрстка таблицы: причина, по которой «разъехалось на одном экране» вообще возможно.
    "своя-таблица": re.compile(r"<TableHead\b"),
    # Чип мимо StatusChip: отсюда шесть тонов на 21 статус и фразы вместо статусов.
    "свой-чип": re.compile(r"<Chip\b"),
    # Кнопка мимо Actions: отсюда «Закрыть» в трёх видах в девяти местах.
    "своя-кнопка": re.compile(r"<Button\b"),
    # Цвет мимо темы.
    "свой-цвет": re.compile(r"#[0-9a-fA-F]{6}\b"),
    # Экран-монолит: в файле на 3000 строк любая правка — лотерея.
    "экран-монолит": None,
}
MONOLITH_LINES = 600


def scan() -> dict[str, dict[str, int]]:
    found: dict[str, dict[str, int]] = {}
    for path in sorted(SRC.rglob("*.tsx")):
        if any(part in EXEMPT_DIRS for part in path.parts):
            continue
        rel = str(path.relative_to(ROOT / "frontend"))
        text = path.read_text(encoding="utf-8", errors="replace")
        counts = {}
        for rule, pattern in RULES.items():
            if pattern is None:
                continue
            hits = len(pattern.findall(text))
            if hits:
                counts[rule] = hits
        lines = text.count("\n") + 1
        if lines > MONOLITH_LINES:
            counts["экран-монолит"] = lines
        if counts:
            found[rel] = counts
    return found


def main() -> int:
    current = scan()
    if "--update" in sys.argv or not BASELINE.exists():
        BASELINE.write_text(json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        # Строки монолита считаем отдельно: складывать их с числом кнопок бессмысленно.
        marks = sum(
            value for counts in current.values() for rule, value in counts.items() if rule != "экран-монолит"
        )
        monoliths = sum(1 for counts in current.values() if "экран-монолит" in counts)
        print(
            f"базовая линия записана: {len(current)} файлов, "
            f"{marks} отступлений, {monoliths} экранов-монолитов"
        )
        return 0

    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    regressions = []
    for rel, counts in current.items():
        for rule, value in counts.items():
            was = baseline.get(rel, {}).get(rule, 0)
            if value > was:
                regressions.append(f"{rel}: {rule} {was} → {value}")

    improved = []
    for rel, counts in baseline.items():
        for rule, was in counts.items():
            value = current.get(rel, {}).get(rule, 0)
            if value < was:
                improved.append(f"{rel}: {rule} {was} → {value}")

    for line in improved:
        print(f"стало лучше  {line}")
    for line in regressions:
        print(f"НОВОЕ НАРУШЕНИЕ  {line}", file=sys.stderr)

    if regressions:
        print(
            "\nКанон: экраны собираются из frontend/src/ui-kit/. "
            "Если отступление осознанное — обнови базовую линию флагом --update и объясни причину в PR.",
            file=sys.stderr,
        )
        return 1
    print("новых отступлений нет")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
