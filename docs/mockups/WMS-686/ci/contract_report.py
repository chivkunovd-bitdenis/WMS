#!/usr/bin/env python3
"""WMS-686: сводка прогона контракта тестов — что зелёное, что красное и почему.

Красный тест нового поведения допустим только как падение на проверке (assertion).
Отказ сборки/фикстуры/импорта, падение зелёного на базе теста и пустой прогон —
ошибка контракта, а не «ожидаемый RED».
"""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def junit_cases(path: Path, prefix: str) -> list[dict[str, str]]:
    cases = []
    for case in ET.parse(path).getroot().iter("testcase"):
        name = case.get("name", "")
        classname = case.get("classname", "")
        failure = case.find("failure")
        error = case.find("error")
        skipped = case.find("skipped")
        if failure is not None:
            message = (failure.get("message") or failure.text or "").strip()
            state = "red" if "AssertionError" in (failure.text or "") or message.startswith("assert") or "AssertionError" in message else "broken"
        elif error is not None:
            message, state = (error.get("message") or "").strip(), "broken"
        elif skipped is not None:
            message, state = (skipped.get("message") or "").strip(), "broken"
        else:
            message, state = "", "green"
        module = f"{prefix}/{classname.replace('.', '/')}.py" if classname else prefix
        cases.append({"id": f"{module}::{name}", "state": state, "reason": message.splitlines()[0][:300] if message else ""})
    return cases


def vitest_cases(path: Path, root: Path) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = []
    for file in data.get("testResults", []):
        rel = Path(file["name"]).resolve().relative_to(root.resolve()).as_posix()
        if file.get("status") == "failed" and not file.get("assertionResults"):
            cases.append({"id": rel, "state": "broken", "reason": (file.get("message") or "")[:300]})
        for test in file.get("assertionResults", []):
            failures = "\n".join(test.get("failureMessages") or [])
            if test.get("status") == "passed":
                state, reason = "green", ""
            elif test.get("status") == "failed":
                state = "red" if "AssertionError" in failures else "broken"
                reason = failures.strip().splitlines()[0][:300] if failures.strip() else ""
            else:
                state, reason = "broken", test.get("status", "")
            cases.append({"id": f"{rel}::{test.get('title', '')}", "state": state, "reason": reason})
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--junit", action="append", default=[], help="каталог_pytest=путь/к/junit.xml, например backend=backend.xml")
    parser.add_argument("--vitest", action="append", default=[], type=Path)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cases: list[dict[str, str]] = []
    for item in args.junit:
        prefix, _, path = item.partition("=")
        cases.extend(junit_cases(Path(path), prefix))
    for path in args.vitest:
        cases.extend(vitest_cases(path, args.root))
    green_expected = json.loads(args.expected.read_text(encoding="utf-8"))["green"]
    problems = []
    if not cases:
        problems.append("Контракт не выполнен: ни одного теста.")
    for case in cases:
        if case["state"] == "broken":
            problems.append(f"Не на проверке: {case['id']}: {case['reason']}")
        if case["state"] != "green" and any(case["id"].startswith(expected) for expected in green_expected):
            problems.append(f"Зелёный на базе тест упал: {case['id']}: {case['reason']}")
    for expected in green_expected:
        if not any(case["id"].startswith(expected) for case in cases):
            problems.append(f"Ожидаемый зелёный тест не выполнен: {expected}")
    lines = ["| Тест | Результат | Причина |", "| --- | --- | --- |"]
    for case in cases:
        reason = case["reason"].replace("|", "\\|")
        lines.append(f"| `{case['id']}` | {case['state'].upper()} | {reason} |")
    counts = {state: sum(1 for case in cases if case["state"] == state) for state in ("green", "red", "broken")}
    summary = (f"## WMS-686 · контракт тестов\n\nGREEN: {counts['green']} · RED (функции нет, падение на проверке): "
               f"{counts['red']} · BROKEN: {counts['broken']}\n\n" + "\n".join(lines) + "\n")
    if problems:
        summary += "\n### Ошибки контракта\n\n" + "\n".join(f"- {problem}" for problem in problems) + "\n"
    args.out.write_text(summary, encoding="utf-8")
    print(summary)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
