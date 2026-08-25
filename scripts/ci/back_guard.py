#!/usr/bin/env python3
"""Сторож канона для бэкенда — храповик по образцу scripts/ui/ui_guard.py.

Прямой запрет отступлений покрасил бы CI сразу на сотнях мест, и его бы выключили.
Базовая линия фиксирует текущий уровень, CI падает только когда нарушений стало больше.

Запуск: без флага — проверить, --update — пересобрать базовую линию.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"
API_DIR = APP / "api"
SERVICES_DIR = APP / "services"
TESTS_DIR = ROOT / "backend" / "tests"
BASELINE = ROOT / "docs" / "backend-guard-baseline.json"
MONOLITH_LINES = 800

ROUTE_RE = re.compile(r'@router\.(?:get|post|put|patch|delete)\(\s*"([^"]*)"')
PREFIX_RE = re.compile(r'prefix\s*=\s*"([^"]*)"')
DEF_RE = re.compile(r"^[ \t]*(?:async\s+)?def\s+\w+\s*\(", re.MULTILINE)
EXCEPT_RE = re.compile(r"^[ \t]*except(?:\s+Exception)?:\s*$", re.MULTILINE)
LOG_RE = re.compile(r"\blog\w*\.")
TODO_RE = re.compile(r"\b(TODO|FIXME)\b")
REF_RE = re.compile(r"tasks/|#\d+")

def _route_regex(full_path: str) -> re.Pattern[str]:
    """Ищем в тестах ПОЛНЫЙ путь роута, а не его последний сегмент.

    Сначала здесь сравнивался последний статический сегмент, и роут «/status»
    считался покрытым, потому что слово «status» встречается в любом наборе тестов.
    Проверка, которая почти никогда не срабатывает, бесполезна: подставной роут
    прошёл мимо неё на первом же испытании. Теперь параметры заменяются на любой
    сегмент, а остальные части пути обязаны совпасть по порядку.
    """
    parts = []
    for seg in full_path.strip("/").split("/"):
        parts.append(r"[^/\"']+" if seg.startswith("{") and seg.endswith("}") else re.escape(seg))
    return re.compile("/" + "/".join(parts))

def _untested_routes(text: str, tests_text: str) -> int:
    prefix = (m.group(1) if (m := PREFIX_RE.search(text)) else "").rstrip("/")
    count = 0
    for m in ROUTE_RE.finditer(text):
        full = (prefix + m.group(1)) or "/"
        if not _route_regex(full).search(tests_text):
            count += 1
    return count

def _defs_without_return_type(text: str) -> int:
    # Сигнатура часто многострочная: ищем "->" в заголовке между скобками и двоеточием.
    count = 0
    for m in DEF_RE.finditer(text):
        i, depth = m.end() - 1, 0
        while i < len(text):
            depth += text[i] == "("
            depth -= text[i] == ")"
            if text[i] == ")" and depth == 0:
                break
            i += 1
        colon = text.find(":", i)
        if colon != -1 and "->" not in text[i + 1 : colon]:
            count += 1
    return count

def _bare_except(text: str) -> int:
    lines = text.splitlines()
    starts = (text.count("\n", 0, m.start()) for m in EXCEPT_RE.finditer(text))
    return sum(not any(LOG_RE.search(x) for x in lines[i : i + 3]) for i in starts)

def _todo_without_task(text: str) -> int:
    return sum(1 for line in text.splitlines() if TODO_RE.search(line) and not REF_RE.search(line))

def scan() -> dict[str, dict[str, int]]:
    tests_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in TESTS_DIR.rglob("*.py"))
    found: dict[str, dict[str, int]] = {}
    for path in sorted(APP.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        counts: dict[str, int] = {}
        lines = text.count("\n") + 1
        if lines > MONOLITH_LINES:
            counts["файл-монолит"] = lines
        if path.is_relative_to(API_DIR) and (n := _untested_routes(text, tests_text)):
            counts["роут-без-теста"] = n
        if path.is_relative_to(SERVICES_DIR) and (n := _defs_without_return_type(text)):
            counts["функция-без-типа"] = n
        if n := _bare_except(text):
            counts["голый-except"] = n
        if n := _todo_without_task(text):
            counts["todo-без-задачи"] = n
        if counts:
            found[str(path.relative_to(ROOT))] = counts
    return found

def _summary(current: dict[str, dict[str, int]]) -> str:
    totals: dict[str, int] = {}
    for counts in current.values():
        for rule, value in counts.items():
            totals[rule] = totals.get(rule, 0) + value
    return ", ".join(f"{rule}: {value}" for rule, value in sorted(totals.items())) or "нет отступлений"

def main() -> int:
    current = scan()
    if "--update" in sys.argv or not BASELINE.exists():
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        print(f"базовая линия записана: {len(current)} файлов ({_summary(current)})")
        return 0
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    regressions, improved = [], []
    for rel, counts in current.items():
        for rule, value in counts.items():
            was = baseline.get(rel, {}).get(rule, 0)
            if value > was:
                regressions.append(f"{rel}: {rule} {was} → {value}")
    for rel, counts in baseline.items():
        for rule, was in counts.items():
            value = current.get(rel, {}).get(rule, 0)
            if value < was:
                improved.append(f"{rel}: {rule} {was} → {value}")
    for line in improved:
        print(f"стало лучше  {line}")
    for line in regressions:
        print(f"НОВОЕ НАРУШЕНИЕ  {line}", file=sys.stderr)
    print(f"сводка по типам: {_summary(current)}")
    if regressions:
        print("\nОсознанное отступление? Обнови линию флагом --update, объясни причину в PR.", file=sys.stderr)
        return 1
    print("новых отступлений нет")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
