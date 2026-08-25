#!/usr/bin/env python3
"""Какой наряд открыт — состояние, привязанное к ветке, а не к проекту целиком.

Раньше это был один файл `tasks/_current` с одной строкой. На одной задаче за раз
работало, на волне из тридцати — нет: каждый следующий `naryad new` затирал
предыдущий, и хук границ начинал судить задачу №7 по списку файлов задачи №30.
Отказа при этом не было: либо правка отклонялась без причины, либо — если списки
случайно пересеклись — проходила, охраняемая от имени чужого наряда.

Теперь `tasks/_current` — каталог, в нём файл на ветку. Рабочая копия (git worktree)
всегда сидит на своей ветке, поэтому наряды тридцати параллельных задач не видят
друг друга. Состояние локальное и в гит не попадает.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT_DIR = ROOT / "tasks" / "_current"


def branch() -> str:
    """Имя текущей ветки в виде, пригодном для имени файла."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=ROOT, capture_output=True, text=True,
    )
    name = (result.stdout or "").strip() or "HEAD"
    return re.sub(r"[^A-Za-z0-9._-]+", "__", name)


def _slot() -> Path:
    return CURRENT_DIR / branch()


def _migrate_legacy() -> None:
    """Старый однослотовый файл превращаем в запись текущей ветки и убираем."""
    if CURRENT_DIR.exists() and CURRENT_DIR.is_file():
        legacy = CURRENT_DIR.read_text(encoding="utf-8").strip()
        CURRENT_DIR.unlink()
        CURRENT_DIR.mkdir(parents=True, exist_ok=True)
        if legacy:
            _slot().write_text(legacy, encoding="utf-8")


def current_slug() -> str:
    _migrate_legacy()
    slot = _slot()
    return slot.read_text(encoding="utf-8").strip() if slot.exists() else ""


def set_current(slug: str) -> None:
    _migrate_legacy()
    CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    _slot().write_text(slug, encoding="utf-8")


def clear_current() -> None:
    _migrate_legacy()
    slot = _slot()
    if slot.exists():
        slot.unlink()


def open_slugs() -> dict[str, str]:
    """Все открытые наряды: ветка -> slug. Нужно волне, чтобы видеть картину целиком."""
    _migrate_legacy()
    if not CURRENT_DIR.exists():
        return {}
    return {
        path.name: path.read_text(encoding="utf-8").strip()
        for path in sorted(CURRENT_DIR.iterdir())
        if path.is_file()
    }
