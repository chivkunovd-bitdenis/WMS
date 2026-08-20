#!/usr/bin/env python3
"""Запрет на правку интерфейса без наряда и вне его границ.

Ровно так работа уезжала на соседние экраны: агент правил каталог и «заодно»
трогал остатки селлера. Хук проверяет две вещи и обе механически:
наряд открыт, и файл входит в границы этого наряда.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from naryad_state import current_slug  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
# Бэкенд был вне охраны целиком: 374 файла backend/app правились без всяких границ,
# хотя половина «сделал не то» — именно про сервер и данные.
WATCHED = ("frontend/src/", "backend/app/")


def naryad_text(slug: str) -> str:
    path = ROOT / "tasks" / slug / "NARYAD.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def boundaries(text: str) -> list[str]:
    return re.findall(r"^- `([^`]+)`$", text, re.M)


def shared_owners(text: str, rel: str) -> str:
    """Кого ещё заденет правка этого файла — чтобы отказ объяснял, а не просто запрещал."""
    match = re.search(rf"^\* `{re.escape(rel)}` — экраны: ([^(]+)", text, re.M)
    return match.group(1).strip() if match else ""


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0

    target = str(payload.get("tool_input", {}).get("file_path", ""))
    if not target:
        return 0
    try:
        rel = str(Path(target).resolve().relative_to(ROOT))
    except ValueError:
        return 0
    if not rel.startswith(WATCHED) or "/ui-kit/" in rel:
        return 0

    slug = current_slug()
    if not slug:
        print(
            f"Правка {rel} запрещена: нет открытого наряда.\n"
            'Открой: python3 scripts/naryad.py new "<просьба владельца дословно>" --screens S-xx --lane мелкая|обычная|аварийная',
            file=sys.stderr,
        )
        return 2

    # Гейт нулевой стадии: для нового домена код не начинается, пока владелец
    # не подтвердил арх-решение. Иначе решение уровня архитектуры принимается
    # походя, внутри задачи на конкретный экран, — так появилась галка «FBS-пул»,
    # на которой висело резервирование остатков.
    arch = ROOT / "tasks" / slug / "ARCH.md"
    if arch.exists():
        body = arch.read_text(encoding="utf-8")
        confirmed = re.search(r"Подтверждено владельцем:\s*(?!<дата>)\S+", body)
        if not confirmed:
            print(
                f"Наряд {slug} — новый домен, и арх-решение ещё не подтверждено.\n"
                f"Заполни tasks/{slug}/ARCH.md (роль solution-architect) и получи от владельца "
                "строку «Подтверждено владельцем: <дата>».\n"
                "До этого правки кода не начинаются.",
                file=sys.stderr,
            )
            return 2

    text = naryad_text(slug)
    allowed = boundaries(text)

    # Пустые границы раньше означали «можно всё» — ровно наоборот тому, зачем ворота
    # заводились. Теперь это отказ: наряд без границ чинится пересозданием.
    if not allowed:
        print(
            f"У наряда {slug} нет ни одного файла в границах — он ничего не охраняет.\n"
            "Заведи наряд заново, указав экран с собственными файлами, --shared или --files.",
            file=sys.stderr,
        )
        return 2

    # Храповик по бэкенду: если наряд вообще не заявлял серверных путей, правку
    # пропускаем с предупреждением — иначе сегодня встанет вся работа по бэкенду.
    # Как только в наряде появился хоть один backend/-путь, границы действуют строго.
    if rel.startswith("backend/") and not any(p.startswith("backend/") for p in allowed):
        print(
            f"{rel} правится вне заявленных границ наряда {slug}: серверных путей в наряде нет.\n"
            "Добавь их через --files при заведении наряда — скоро это станет отказом.",
            file=sys.stderr,
        )
        return 0

    if rel not in allowed:
        owners = shared_owners(text, rel)
        if owners:
            print(
                f"{rel} — общий файл, его тянут экраны: {owners}.\n"
                "Правка заденет их все. Если это осознанно — заведи наряд заново с "
                f"--shared {rel} и назови это в отчёте.",
                file=sys.stderr,
            )
            return 2
        listed = "\n".join(f"  {item}" for item in allowed)
        print(
            f"Правка {rel} вне границ наряда {slug}.\nВ границах только:\n{listed}\n"
            "Нужен другой экран — заведи наряд на него, а не расширяй этот молча.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
