#!/usr/bin/env python3
"""Проверка новых миграций Alembic на разрушительные операции.

За неделю подряд прошло 15 миграций, и все они только добавляли (колонки, таблицы,
индексы) — это единственное, что спасло прод при недокатанном деплое: старый код
поверх новой БД не терял данные, потому что откатывать было нечего. Разрушительная
миграция (drop_table/drop_column, обязательная колонка без дефолта, DELETE/TRUNCATE/
DROP через op.execute) может проскочить ревью — этот скрипт ловит её на CI до раскатки.
Санкцию на осознанно разрушительную миграцию даёт владелец через переменную окружения
WMS_DESTRUCTIVE_MIGRATION_APPROVED=yes — иначе выход с кодом 1.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSIONS_DIR = ROOT / "backend" / "alembic" / "versions"

DROP_RE = re.compile(r"\b(?:op|batch_op)\.(?:drop_table|drop_column)\(")
ALTER_RE = re.compile(r"\b(?:op|batch_op)\.alter_column\(")
EXECUTE_RE = re.compile(r"\bop\.execute\(")
DESTRUCTIVE_SQL_RE = re.compile(r"\b(DELETE|TRUNCATE|DROP)\b", re.IGNORECASE)
UPGRADE_DEF_RE = re.compile(r"^def upgrade\(")
ANY_DEF_RE = re.compile(r"^def \w+\(")


def changed_migrations() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=10, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        # git недоступен (нет origin/main, не репозиторий и т.п.) — перестраховываемся
        # и проверяем все миграции, а не пропускаем проверку молча.
        return sorted(VERSIONS_DIR.glob("*.py"))
    paths = {ROOT / line for line in out.stdout.splitlines() if line.strip()}
    return sorted(p for p in paths if p.parent == VERSIONS_DIR and p.suffix == ".py" and p.exists())


def _upgrade_range(lines: list[str]) -> tuple[int, int]:
    # downgrade() по построению зеркалит upgrade() и полон drop_* — это не риск,
    # риск только в том, что реально накатится в проде, то есть в upgrade().
    start = None
    for i, line in enumerate(lines):
        if UPGRADE_DEF_RE.match(line):
            start = i
        elif start is not None and ANY_DEF_RE.match(line):
            return start, i
    return (start, len(lines)) if start is not None else (0, 0)


def find_destructive(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start, end = _upgrade_range(lines)
    findings = []
    for i in range(start, end):
        line = lines[i]
        block = "\n".join(lines[i : i + 8])
        if DROP_RE.search(line):
            findings.append(f"{path.name}:{i + 1}: {line.strip()}")
        elif ALTER_RE.search(line) and "nullable=False" in block and "server_default" not in block:
            findings.append(f"{path.name}:{i + 1}: {line.strip()}  (nullable=False без server_default)")
        elif EXECUTE_RE.search(line) and DESTRUCTIVE_SQL_RE.search(block):
            findings.append(f"{path.name}:{i + 1}: {line.strip()}")
    return findings


def main() -> int:
    migrations = changed_migrations()
    if not migrations:
        print("новых миграций относительно origin/main нет")
        return 0

    all_findings: dict[str, list[str]] = {}
    for path in migrations:
        findings = find_destructive(path)
        if findings:
            all_findings[path.name] = findings

    if not all_findings:
        print(f"проверено миграций: {len(migrations)}, разрушительных операций не найдено")
        return 0

    print("Найдены потенциально разрушительные операции в новых миграциях:", file=sys.stderr)
    for name in sorted(all_findings):
        for line in all_findings[name]:
            print(f"  {line}", file=sys.stderr)

    if os.environ.get("WMS_DESTRUCTIVE_MIGRATION_APPROVED") == "yes":
        print("\nWMS_DESTRUCTIVE_MIGRATION_APPROVED=yes — санкция получена, пропускаю.")
        return 0

    print(
        "\nВыкатка требует явной санкции владельца: выставь "
        "WMS_DESTRUCTIVE_MIGRATION_APPROVED=yes, чтобы снять блок.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
