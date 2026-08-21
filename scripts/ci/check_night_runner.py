#!/usr/bin/env python3
"""Проверка оркестратора без единого вызова модели.

Смысл: главный страх владельца — «скрипт споткнётся об то, что модель не вернула, и ночь
умрёт». Поэтому проверяется ровно поведение на плохих входах: файла нет, секции нет, файл
битый, роль неизвестна. Ни один такой случай не имеет права бросить исключение — он обязан
честно вернуть «шаг не пройден».
"""
from __future__ import annotations

import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import night as n  # noqa: E402

СЛУЧАИ: list[tuple[str, str, object, object]] = []


def main() -> int:
    t = pathlib.Path(tempfile.mkdtemp())
    беды: list[str] = []

    def проверь(имя: str, факт, ждём) -> None:
        if факт != ждём:
            беды.append(f"{имя}: получил {факт!r}, ждал {ждём!r}")

    проверь("нет файла", n.артефакт_готов(t, "reviewer")[0], False)

    (t / "REVIEW.md").write_text("## Проверено и нормально\nвсё ок\n", encoding="utf-8")
    проверь("нет обязательной секции", n.артефакт_готов(t, "reviewer")[0], False)

    (t / "REVIEW.md").write_text("## Находки\n\n## Проверено и нормально\nсмотрел\n", encoding="utf-8")
    проверь("пустые Находки — шаг пройден", n.артефакт_готов(t, "reviewer")[0], True)
    проверь("пустые Находки — без возврата", n.есть_находки(t, "reviewer"), False)

    (t / "REVIEW.md").write_text(
        "## Находки\n- fbs.py:81 упадёт на статусе sorted\n\n## Проверено и нормально\nда\n",
        encoding="utf-8")
    проверь("непустые Находки — возврат", n.есть_находки(t, "reviewer"), True)

    (t / "REVIEW.md").write_text("## Находки\nнет\n\n## Проверено и нормально\nда\n", encoding="utf-8")
    проверь("«нет» словом — без возврата", n.есть_находки(t, "reviewer"), False)

    (t / "JUDGE.md").write_text("\x00 мусор без секций", encoding="utf-8", errors="replace")
    проверь("битый файл — не пройден, без исключения", n.артефакт_готов(t, "ux-judge")[0], False)

    (t / "RAZBOR.md").write_text("## Экраны\n- S-03 FBS\n", encoding="utf-8")
    проверь("экран из реестра — фронтовик", n.выбрать_dev(t), "screen-dev")
    (t / "RAZBOR.md").write_text("## Экраны\nэкран будет создан\n", encoding="utf-8")
    проверь("без экрана — бэкендер", n.выбрать_dev(t), "backend-dev")

    (t / "RAZBOR.md").write_text("## Тип\nбаг\n## Экраны\n- S-03\n", encoding="utf-8")
    проверь("тип читается", n.поле(t, "RAZBOR.md", "Тип").strip(), "баг")
    проверь("нет секции — пусто, без падения", n.поле(t, "RAZBOR.md", "Нетути"), "")

    проверь("неизвестная роль не роняет цепочку", n.артефакт_готов(t, "выдуманная")[0], True)

    for р in {r for ц in n.ЦЕПОЧКИ.values() for r in ц if r != "dev"}:
        if р not in n.АРТЕФАКТ:
            беды.append(f"роль {р} в цепочке, но её нет в таблице АРТЕФАКТ")

    if беды:
        print("ПРОВЕРКА ОРКЕСТРАТОРА КРАСНАЯ:", file=sys.stderr)
        for б in беды:
            print(f"  - {б}", file=sys.stderr)
        return 1
    print("оркестратор: все случаи сошлись")
    return 0


if __name__ == "__main__":
    sys.exit(main())
