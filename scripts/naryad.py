#!/usr/bin/env python3
"""Наряд — вход в конвейер. Одна команда между «сказал в чате» и «полез в код».

Фича возникает спонтанно: владелец пишет в чат «убери рыжую заливку» — и работа
начинается. Наряд нужен, чтобы у этой работы за десять секунд появились границы:
какие экраны трогаем, какая полоса, что именно просили (дословно). Без наряда
хук запрещает править frontend/src — не по строгости, а потому что именно так
правки уезжали на соседние экраны.

  python3 scripts/naryad.py new "убрать заливку строк" --screens S-16,S-31 --lane мелкая
  python3 scripts/naryad.py show
  python3 scripts/naryad.py close
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from naryad_state import clear_current, current_slug, set_current  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "tasks"
REGISTRY = ROOT / "frontend" / "screens.registry.json"
LANES = ("мелкая", "обычная", "аварийная")


def registry() -> dict[str, dict]:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return {screen["id"]: screen for screen in data["screens"]}


def slugify(text: str) -> str:
    translit = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
        "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
        "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
        "ч": "ch", "ш": "sh", "щ": "sch", "ы": "y", "э": "e", "ю": "yu", "я": "ya",
        "ь": "", "ъ": "",
    }
    lowered = "".join(translit.get(ch, ch) for ch in text.lower())
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug[:40] or "naryad"


def cmd_new(args: argparse.Namespace) -> int:
    screens = [s.strip().upper() for s in args.screens.split(",") if s.strip()] if args.screens else []
    known = registry()
    unknown = [s for s in screens if s not in known]
    if unknown:
        print(f"нет таких экранов в реестре: {', '.join(unknown)}", file=sys.stderr)
        return 1
    if args.lane not in LANES:
        print(f"полоса должна быть одной из: {', '.join(LANES)}", file=sys.stderr)
        return 1

    stamp = datetime.now().strftime("%Y%m%d")
    slug = f"{stamp}-{slugify(args.text)}"
    folder = TASKS / slug
    folder.mkdir(parents=True, exist_ok=True)

    # Реестр хранит пути относительно frontend/, наряд — относительно корня репозитория:
    # в границы попадает и бэкенд, поэтому общий знаменатель только один — корень.
    files = sorted({f"frontend/{path}" for s in screens for path in known[s]["files"]})
    # Общий файл задевает соседние экраны, поэтому в границы попадает только явно,
    # флагом --shared, и в наряде видно, чьи ещё экраны он затрагивает.
    shared: dict[str, list[str]] = {}
    for screen_id in screens:
        for path, owners in known[screen_id].get("shared", {}).items():
            shared[f"frontend/{path}"] = owners
    requested_shared = [p.strip() for p in args.shared.split(",") if p.strip()] if args.shared else []
    unknown_shared = [p for p in requested_shared if p not in shared]
    if unknown_shared:
        print(f"эти файлы не относятся к выбранным экранам: {', '.join(unknown_shared)}", file=sys.stderr)
        return 1
    # Пути в наряде хранятся относительно frontend/ (так их отдаёт реестр), поэтому
    # ручной ввод нормализуем: «frontend/src/...» и «src/...» — это одно и то же.
    extra = [p.strip().removeprefix("./") for p in args.files.split(",") if p.strip()]
    files = sorted(set(files) | set(requested_shared) | set(extra))
    # Наряд без границ — это наряд, который ничего не охраняет: хук трактует пустой
    # список как «можно всё». Восемь экранов реестра (S-02, S-13, S-14, S-17, S-20,
    # S-28, S-29, S-30) собственных файлов не имеют — их компонент общий с соседним
    # экраном и лежит в shared. Поэтому пустые границы — отказ, а не молчание.
    if not files:
        candidates = "\n".join(f"  --shared {path}" for path in sorted(shared)) or "  (общих файлов у экрана тоже нет)"
        print(
            "У наряда нет ни одного файла в границах — так он ничего не охраняет.\n"
            f"У выбранных экранов собственных файлов нет. Включи нужный явно:\n{candidates}\n"
            "либо задай пути через --files.",
            file=sys.stderr,
        )
        if not any(folder.iterdir()):
            folder.rmdir()
        return 1

    lines = [
        f"# Наряд · {slug}",
        "",
        f"**Полоса:** {args.lane}",
        f"**Тип:** {args.kind}",
        f"**Заведён:** {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        "",
        "## Просили дословно",
        "",
        f"> {args.text}",
        "",
        "## Экраны",
        "",
    ]
    for screen_id in screens:
        screen = known[screen_id]
        lines.append(f"- `{screen_id}` {screen['route']} — {screen['component']}")
    if not screens:
        lines.append("- экраны не назначены (новый экран или не UI-задача)")
    lines += [
        "",
        "## Границы правки",
        "",
        "Разрешено трогать только эти файлы:",
        "",
    ]
    lines += [f"- `{path}`" for path in files] or ["- (границы не заданы)"]
    if shared:
        lines += [
            "",
            "## Общие файлы (в границы не входят)",
            "",
            "Правка любого из них задевает соседние экраны. Нужен — включай явно:",
            "`--shared <путь>` при создании наряда, и назови это в отчёте.",
            "",
        ]
        for path, owners in sorted(shared.items()):
            mark = "включён" if path in requested_shared else "не включён"
            lines.append(f"* `{path}` — экраны: {', '.join(owners)} ({mark})")
    lines += [
        "",
        "## Статус",
        "",
        (
            "- [ ] арх-решение — `ARCH.md` (обязательно: тип «домен»)"
            if args.kind == "домен"
            else "- [ ] арх-решение — не требуется (правка существующего)"
        ),
        "- [ ] контракт (обычная полоса)",
        "- [ ] разработка",
        "- [ ] критик исполнения",
        "- [ ] судья в живом браузере",
        "- [ ] доказательства в `docs/evidence/" + slug + "/`",
        "- [ ] влито",
        "",
    ]
    (folder / "NARYAD.md").write_text("\n".join(lines), encoding="utf-8")

    # Снимок уже изменённых файлов: без него сторож границ считал бы чужой незакоммиченный
    # хвост нарушением наряда и ругался бы на каждом шаге.
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "frontend/src"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.splitlines()
    (folder / "baseline-dirty.txt").write_text(
        "\n".join(sorted(line[3:].strip() for line in dirty)), encoding="utf-8"
    )
    if args.kind == "домен":
        (folder / "ARCH.md").write_text(
            "\n".join(
                [
                    f"# Арх-решение · {slug}",
                    "",
                    "Заполняет `solution-architect`. Пока нет строки подтверждения владельца,",
                    "правки кода заблокированы хуком.",
                    "",
                    "## Решение",
                    "## Варианты и цена",
                    "## Граница: мы / маркетплейс / человек руками",
                    "## Переиспользуем / расширяем / новое",
                    "## Риски внешнего API",
                    "## Чего не делаем в этой волне",
                    "## Вопросы владельцу",
                    "",
                    "## Подтверждение владельца",
                    "",
                    "Подтверждено владельцем: <дата>",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    set_current(slug)
    print(f"наряд открыт: tasks/{slug}/NARYAD.md")
    print(
        f"полоса: {args.lane}; экраны: {', '.join(screens) or 'не назначены'}; "
        f"файлов в границах: {len(files)}; общих рядом: {len(shared)}"
    )
    return 0


def cmd_show(_: argparse.Namespace) -> int:
    slug = current_slug()
    if not slug:
        print("открытого наряда нет на этой ветке")
        return 1
    path = TASKS / slug / "NARYAD.md"
    print(path.read_text(encoding="utf-8") if path.exists() else f"наряд {slug} потерян")
    return 0


def cmd_close(_: argparse.Namespace) -> int:
    clear_current()
    print("наряд закрыт")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    new = sub.add_parser("new", help="открыть наряд")
    new.add_argument("text", help="просьба владельца дословно")
    new.add_argument("--screens", default="", help="коды экранов через запятую, например S-16,S-31")
    new.add_argument("--lane", default="обычная", help=f"полоса: {', '.join(LANES)}")
    new.add_argument("--shared", default="", help="общие файлы, которые всё же нужно тронуть, через запятую")
    new.add_argument(
        "--kind",
        default="экран",
        choices=("экран", "домен"),
        help="«домен» — новый маркетплейс, интеграция или тип документа: требует ARCH.md до кода",
    )
    new.add_argument(
        "--files",
        default="",
        help="файлы в границах, когда экрана ещё нет в реестре (новый экран, бэкенд)",
    )
    new.set_defaults(func=cmd_new)

    sub.add_parser("show", help="показать текущий наряд").set_defaults(func=cmd_show)
    sub.add_parser("close", help="закрыть наряд").set_defaults(func=cmd_close)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
