#!/usr/bin/env python3
"""Карточка правил — включается сама на каждое сообщение владельца.

Правила, которые надо вспомнить, не работают: за неделю разбора ни один регламент
из 753 строк не остановил ни одной потери. Поэтому короткая карточка подмешивается
в контекст автоматически, вместе с состоянием текущего наряда.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from naryad_state import current_slug  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    sys.stdin.read()  # вход хука не нужен, но его надо вычитать
    slug = current_slug()
    naryad = f"открыт наряд `{slug}`" if slug else "наряда нет — правки frontend/src заблокированы"

    print(
        "\n".join(
            [
                "<wms-правила>",
                f"Наряд: {naryad}. Открыть: python3 scripts/naryad.py new \"<просьба дословно>\" --screens S-xx --lane мелкая|обычная|аварийная",
                "Экран — единица работы, коды в frontend/screens.registry.json. Правки только внутри файлов своего экрана.",
                "Интерфейс собирается из frontend/src/ui-kit/. Своя вёрстка таблиц, чипов и кнопок — дефект (docs/product/UX_CANON_RU.md).",
                "Мелкая полоса — без контракта. Обычная (меняется состав данных или действий) — сначала контракт, код после подтверждения.",
                "«Сделано» без файла-доказательства в docs/evidence/<наряд>/ не считается. Проверка кодом и API вместо живого экрана не засчитывается.",
                "Перед сдачей фронт: npx tsc --noEmit -p tsconfig.app.json, python3 scripts/ui/ui_guard.py, python3 scripts/ui/ui_kit_usage_guard.py. Бэк: ruff, mypy, pytest, python3 scripts/ci/back_guard.py.",
                "Новый роут — только вместе с тестом. Миграции только добавляющие: удаление — отдельное решение владельца.",
                "</wms-правила>",
            ]
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
