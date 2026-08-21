#!/usr/bin/env python3
"""Ночной оркестратор WMS.

Запускает агентов по цепочке ролей и следит только за одним: появился ли на диске файл,
который роль обязана была оставить. Состояние конвейера — это файлы, а не ответы модели.
Поэтому забытое агентом поле, непредусмотренный вердикт или оборванный ответ не могут
подвесить очередь: файла нет — шаг не пройден, карточка откладывается, остальные едут.

  вечер:  python3 scripts/night.py вечер night/2026-08-22.md
  ночь:   python3 scripts/night.py ночь  night/2026-08-22

Повторный запуск продолжает с того места, где встали: шаг, чей файл уже лежит, пропускается.
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
from dataclasses import dataclass
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path

КОРЕНЬ = Path(__file__).resolve().parents[1]
ТАЙМАУТ = 20 * 60          # один шаг не имеет права съесть ночь
ПОВТОРОВ = 1               # столько раз перезапускаем шаг, не оставивший файла
КРУГОВ = 2                 # столько раз возвращаем карточку разработчику по находкам

# Роль → файл, который она обязана оставить, и секции, которые в нём обязаны быть.
# None вместо файла означает «шаг проверяется гейтами, а не артефактом».
АРТЕФАКТ = {
    "intake":             ("ISTOCHNIK.md",     ["Дословно"]),
    "analyst":            ("RAZBOR.md",        ["Дословно", "Что сейчас", "Что должно быть", "Тип"]),
    "requirement-critic": ("SVERKA.md",        ["Тип", "Расхождения"]),
    "solution-architect": ("ARCH.md",          ["Как это решают другие", "Решение", "Границы"]),
    "ux-architect":       ("CONTRACT.md",      ["Контракт", "Канон"]),
    "ui-critic":          ("DESIGN-REVIEW.md", ["Находки"]),
    "tester":             ("CASES.md",         ["Назначенные кейсы"]),
    "breaker":            ("CASES.md",         ["Ломающие кейсы", "Смежные кейсы"]),
    "screen-dev":         ("DEV.md",           ["Изменённые файлы", "Гейты"]),
    "backend-dev":        ("DEV.md",           ["Изменённые файлы", "Гейты"]),
    "arch-critic":        (None,               []),
    "product":            ("RESHENIYA.md",     ["Решения", "Открытых вопросов не осталось"]),
    "reviewer":           ("REVIEW.md",        ["Находки"]),
    "clicker":            ("CLICKS.md",        ["Пройденные кейсы", "Не прошло"]),
    "ux-judge":           ("JUDGE.md",         ["Находки", "Пройденные кейсы"]),
    # guard из таблицы убран сознательно: его механические проверки (типы, тесты, сторож
    # канона, границы) оркестратор гоняет сам после разработки. Отдельный агент, повторяющий
    # то же самое, — лишний вызов модели и лишняя роль, которая притворяется работой.
    "blocker-collector":  ("BLOCKERS.md",     ["Блокировки", "Без обоснования", "Разошлись слои"]),
    "blocker-skeptic":    ("SKEPTIC.md",      ["Находки", "Проверено"]),
    "product-acceptor":   ("OTCHET.md",        ["Сделано", "Не доехало", "Решения продакта", "Оформление"]),
}

# Что роль требует на входе. Списком альтернатив: годится любой из вариантов.
# Проверяется при старте — цепочка, где шагу не хватает входа, не запускается вообще.
#
# Волна r04 легла именно здесь: у бага не было контракта, а screen-dev в своём описании
# требует «строго по готовому CONTRACT.md»; и ui-critic, который по своему же описанию
# проверяет РЕАЛИЗОВАННЫЙ экран, стоял до разработки и честно находил, что её нет.
# Обе поломки видны из этой таблицы за секунду и без единого потраченного токена.
ТРЕБУЕТ: dict[str, list[tuple[str, ...]]] = {
    "analyst":            [("ISTOCHNIK.md",)],
    "requirement-critic": [("RAZBOR.md",)],
    "solution-architect": [("RAZBOR.md",)],
    # Для фичи и домена вход проектировщика — разбор; арх-решение появляется только у домена.
    "ux-architect":       [("RAZBOR.md",)],
    "product":            [("RAZBOR.md",)],
    "tester":             [("RAZBOR.md",)],
    "breaker":            [("CASES.md",)],
    # Багу отдельный контракт не нужен: «что должно быть» из разбора плюс кейсы — это и есть
    # задание. Городить ради бага дорогого проектировщика значит платить опусом за то,
    # что уже написано.
    "screen-dev":         [("CONTRACT.md",), ("RAZBOR.md", "CASES.md")],
    "backend-dev":        [("CONTRACT.md",), ("RAZBOR.md", "CASES.md")],
    "reviewer":           [("DEV.md",)],
    "ui-critic":          [("DEV.md",)],
    "clicker":            [("CASES.md", "DEV.md")],
    "ux-judge":           [("CLICKS.md",)],
    "blocker-collector":  [("KANDIDATY.md",)],
    "blocker-skeptic":    [("BLOCKERS.md",)],
}

# Пути по типам задач. Порядок продиктован тем, что роли требуют на входе, а не вкусом:
# критик исполнения смотрит уже написанный код, поэтому стоит после разработки и ревью.
ЦЕПОЧКИ = {
    "баг":   ["tester", "dev", "reviewer", "ui-critic", "clicker", "ux-judge"],
    "фича":  ["ux-architect", "product", "tester", "breaker", "dev", "reviewer",
              "ui-critic", "clicker", "ux-judge"],
    "домен": ["solution-architect", "ux-architect", "product", "tester", "breaker",
              "dev", "reviewer", "ui-critic", "clicker", "ux-judge"],
    # Разовый проход сборки реестра блокировок. Ничего не правит — только читает код
    # и пишет документы, поэтому им же безопасно обкатать сам оркестратор.
    "блокировки": ["blocker-collector", "blocker-skeptic"],
}

# Роли, чьи находки возвращают карточку разработчику.
СУДЬИ = ("reviewer", "ux-judge", "ui-critic")

# Codex запускается только в явно выбранном режиме. По умолчанию сохраняем
# существующий Claude-путь, чтобы безопасная проверка оркестратора не могла
# случайно начать волну другим исполнителем.
ИСПОЛНИТЕЛЬ = os.environ.get("NIGHT_EXECUTOR", "claude").strip().lower()
ИССЛЕДОВАТЕЛИ = {"analyst", "solution-architect"}
# Эти роли используют живой браузер или подключённые плагины; им нужен
# пользовательский конфиг Codex. Остальные роли изолируются от него.
РОЛИ_С_ПОЛНЫМ_КОНФИГОМ = {"clicker", "ux-judge"}
ДОПУСТИМЫЕ_ПРОФИЛИ = {"sol", "terra", "luna"}
ПРОФИЛЬ_ПО_КЛАССУ = {"opus": "sol", "sonnet": "terra", "haiku": "luna"}


def создать_свежую_волну(исходник: Path, run_id: str,
                       базовый_каталог: Path | None = None) -> Path:
    """Создаёт отдельный каталог нового прогона, не переиспользуя старую волну."""
    исходный_путь = Path(исходник)
    исходник = исходный_путь.resolve()
    if not run_id or Path(run_id).name != run_id or run_id in {".", ".."}:
        raise ValueError("run_id должен быть непустым именем без разделителей пути")
    база = Path(базовый_каталог or (КОРЕНЬ / "night")).resolve()
    новая = база / f"{исходник.stem}-{run_id}"
    if новая.exists():
        raise FileExistsError(f"каталог свежей волны уже существует: {новая}")
    новая.mkdir(parents=True, exist_ok=False)
    (новая / "RUN.json").write_text(
        json.dumps({"source": str(исходный_путь), "run_id": run_id},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return новая


@dataclass(frozen=True)
class РабочаяКарточка:
    """Изолированный checkout карточки; исходная волна при этом не изменяется."""

    ид: str
    lane: int
    корень: Path
    волна: Path
    папка: Path
    ветка: str
    base_sha: str = ""


def _имя_ветки(волна: Path, ид: str, полоса: int) -> str:
    def safe(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9._/-]+", "-", value).strip("-/. ") or "card"
    return f"night/{safe(волна.name)}/lane-{полоса}/{safe(ид)}"


def _git(*аргументы: str, cwd: Path = КОРЕНЬ) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *аргументы], cwd=cwd, capture_output=True,
                          text=True, check=False)


def _worktree_пути() -> dict[str, Path]:
    р = _git("worktree", "list", "--porcelain")
    результат: dict[str, Path] = {}
    путь: Path | None = None
    ветка = ""
    for строка in р.stdout.splitlines():
        if строка.startswith("worktree "):
            путь = Path(строка[9:])
        elif строка.startswith("branch refs/heads/") and путь is not None:
            ветка = строка[len("branch refs/heads/"):]
            результат[ветка] = путь
    return результат


def _создать_рабочую_карточку(ид: str, волна: Path, полоса: int) -> РабочаяКарточка:
    """Создаёт или возобновляет карточный worktree, не трогая исходную волну."""
    ветка = _имя_ветки(волна, ид, полоса)
    путь = КОРЕНЬ.parent / ".night-worktrees" / волна.name / f"lane-{полоса}-{ид}"
    существующие = _worktree_пути()
    зарегистрированный = существующие.get(ветка)
    if зарегистрированный is not None:
        путь = зарегистрированный
    elif not путь.exists():
        путь.parent.mkdir(parents=True, exist_ok=True)
        р = _git("worktree", "add", "-b", ветка, str(путь), "HEAD")
        if р.returncode != 0:
            # Resume после частично прерванного запуска: ветка уже есть, но
            # worktree ещё не зарегистрирован.
            р = _git("worktree", "add", str(путь), ветка)
        if р.returncode != 0:
            raise RuntimeError(f"не удалось создать worktree {путь}: {р.stderr.strip()}")
    elif зарегистрированный is None:
        raise RuntimeError(f"путь worktree занят и не зарегистрирован git: {путь}")

    рабочая_волна = путь / "night" / волна.name
    рабочая_папка = рабочая_волна / "cards" / ид
    рабочая_папка.mkdir(parents=True, exist_ok=True)
    исходная_папка = волна / "cards" / ид
    if исходная_папка.exists():
        shutil.copytree(исходная_папка, рабочая_папка, dirs_exist_ok=True)
    for имя in ("MAP.md", "QUEUE.md"):
        источник = волна / имя
        if источник.exists() and not (рабочая_волна / имя).exists():
            рабочая_волна.mkdir(parents=True, exist_ok=True)
            shutil.copy2(источник, рабочая_волна / имя)
    база = _git("rev-parse", "HEAD", cwd=КОРЕНЬ).stdout.strip()
    return РабочаяКарточка(ид, полоса, путь, рабочая_волна, рабочая_папка, ветка, база)


def рабочие_карточки(волна: Path, карточки_: list[str], полос: int) -> dict[str, РабочаяКарточка]:
    """Подготовка до пула важна: git worktree add не должен гоняться параллельно."""
    if полос < 1:
        raise ValueError("число полос должно быть больше нуля")
    return {ид: _создать_рабочую_карточку(ид, волна, н % полос + 1)
            for н, ид in enumerate(карточки_)}


def очистить_рабочие_карточки(волна: Path, удалить: bool = False) -> list[str]:
    """Возвращает список карточных worktree; удаление только по явному флагу.

    Ветки намеренно не удаляются: результат карточки должен оставаться доступным
    для отдельного review/merge после ночи.
    """
    префикс = f"night/{волна.name}/"
    найдено = []
    for ветка, путь in _worktree_пути().items():
        if not ветка.startswith(префикс):
            continue
        статус = _git("status", "--porcelain", cwd=путь)
        чисто = статус.returncode == 0 and not статус.stdout.strip()
        if удалить and чисто:
            р = _git("worktree", "remove", str(путь))
            найдено.append(f"{ветка}: {'удалён' if р.returncode == 0 else 'ошибка удаления'}")
        else:
            найдено.append(f"{ветка}: {путь} ({'чистый' if чисто else 'есть изменения'})")
    return найдено


def _профиль_ошибка(профиль: str | None) -> str | None:
    if профиль is not None and профиль not in ДОПУСТИМЫЕ_ПРОФИЛИ:
        return (f"недопустимый профиль Codex: {профиль!r}; "
                "допустимы только 'sol', 'terra' и 'luna'")
    return None


def профиль_роли(роль: str, профиль: str | None = None) -> str:
    """Переносит класс модели из роли Claude в эквивалентный профиль Codex."""
    if профиль is not None:
        return профиль
    файл = КОРЕНЬ / ".claude" / "agents" / f"{роль}.md"
    инструкция = файл.read_text(encoding="utf-8", errors="replace") if файл.exists() else ""
    совпадение = re.search(r"^model:\s*(opus|sonnet|haiku)\s*$", инструкция, re.M)
    if not совпадение:
        raise ValueError(f"у роли {роль!r} не указан model: opus|sonnet|haiku")
    return ПРОФИЛЬ_ПО_КЛАССУ[совпадение.group(1)]


def роль_с_инъекцией(роль: str, промпт: str, профиль: str | None = None) -> str:
    """Явно закрепляет владельца роли при запуске через Codex.

    Источник истины — поле model в полном файле роли: opus → Sol,
    sonnet → Terra, haiku → Luna.
    """
    исполнитель = профиль_роли(роль, профиль).capitalize()
    файл = КОРЕНЬ / ".claude" / "agents" / f"{роль}.md"
    инструкция = файл.read_text(encoding="utf-8", errors="replace") if файл.exists() else ""
    return (f"Профиль исполнителя: {исполнитель}. Выполняй только роль `{роль}`.\n"
            "Не читай секреты, ключи, токены, .env или кабинеты учётных данных.\n"
            f"Полный текст инструкции роли:\n{инструкция}\n\n" + промпт)


def _codex_текст(вывод: str) -> str:
    """Извлекает человекочитаемый хвост из JSONL Codex, не доверяя ему как гейту."""
    сообщения: list[str] = []
    ошибки: list[str] = []
    for строка in вывод.splitlines():
        try:
            событие = json.loads(строка)
        except json.JSONDecodeError:
            if строка.strip():
                сообщения.append(строка.strip())
            continue
        if not isinstance(событие, dict):
            continue
        if событие.get("type") == "error" or событие.get("error"):
            ошибки.append(str(событие.get("error") or событие.get("message") or событие))
            continue
        item = событие.get("item")
        if isinstance(item, dict):
            текст = item.get("text") or item.get("content")
            if isinstance(текст, str) and текст.strip():
                сообщения.append(текст.strip())
        текст = событие.get("text")
        if isinstance(текст, str) and текст.strip():
            сообщения.append(текст.strip())
    итог = сообщения + [f"ошибка Codex: {e}" for e in ошибки]
    return "\n".join(итог)[-2000:]


def _запустить_codex(роль: str, промпт: str, профиль: str | None = None,
                     cwd: Path = КОРЕНЬ) -> tuple[int, str]:
    if ошибка := _профиль_ошибка(профиль):
        return 2, ошибка
    бинарник = os.environ.get("NIGHT_CODEX_BIN", "codex")
    if not shutil.which(бинарник):
        return 127, f"в PATH нет команды {бинарник}"
    try:
        профиль_cli = профиль_роли(роль, профиль)
        модель = f"gpt-5.6-{профиль_cli}"
        effort = "low" if профиль_cli == "luna" else "medium"
        команда = [бинарник, "--ask-for-approval", "never", "--sandbox", "workspace-write",
                   "--model", модель, "--config", f"model_reasoning_effort={effort}",
                   ]
        if роль in ИССЛЕДОВАТЕЛИ:
            команда.append("--search")
        команда.append("exec")
        if роль not in РОЛИ_С_ПОЛНЫМ_КОНФИГОМ:
            команда.append("--ignore-user-config")
        команда.append("--json")
        команда.append(роль_с_инъекцией(роль, промпт, профиль_cli))
        р = subprocess.run(
            команда,
            cwd=cwd, capture_output=True, text=True, timeout=ТАЙМАУТ,
        )
        вывод = (р.stdout or "") + ("\n" + р.stderr if р.stderr else "")
        return р.returncode, _codex_текст(вывод)
    except subprocess.TimeoutExpired:
        return 124, f"шаг превысил {ТАЙМАУТ // 60} минут и снят"
    except Exception as е:                                   # noqa: BLE001
        return 1, f"не удалось запустить Codex: {е}"


def журнал(волна: Path, строка: str) -> None:
    # Время нужно не для красоты: без него по журналу не отличить работающий шаг
    # от повисшего, а ночью это единственный способ понять, жив ли прогон.
    метка = time.strftime("%H:%M")
    строка = строка if строка.startswith(("#", "\n#")) or not строка.strip() else f"{метка} {строка}"
    print(строка, flush=True)
    (волна / "JOURNAL.md").open("a", encoding="utf-8").write(строка + "\n")


def запустить(роль: str, промпт: str, профиль: str | None = None,
             cwd: Path = КОРЕНЬ) -> tuple[int, str]:
    """Один вызов агента. Падение подпроцесса — это просто ненулевой код, а не исключение."""
    if ошибка := _профиль_ошибка(профиль):
        return 2, ошибка
    if ИСПОЛНИТЕЛЬ == "codex":
        return _запустить_codex(роль, промпт, профиль, cwd)
    try:
        р = subprocess.run(
            ["claude", "-p", промпт, "--agent", роль,
             # Без этого первая же запись файла упирается в запрос разрешения,
             # которого ночью некому дать, и агент честно останавливается.
             "--permission-mode", "acceptEdits"],
            cwd=cwd, capture_output=True, text=True, timeout=ТАЙМАУТ,
        )
        return р.returncode, (р.stdout or р.stderr or "")[-2000:]
    except subprocess.TimeoutExpired:
        return 124, f"шаг превысил {ТАЙМАУТ // 60} минут и снят"
    except Exception as е:                                   # noqa: BLE001
        return 1, f"не удалось запустить агента: {е}"


def секции(текст: str) -> set[str]:
    return {m.strip() for m in re.findall(r"^#{1,4}\s+(.+?)\s*$", текст, re.M)}


# Формулировки, которыми артефакт останавливает сам себя до утра. Ночью на них некому
# ответить, и карточка умирает. Волна r04 легла в том числе так: контракты 07/08/09 сами
# записали «не разрешает разработку до подтверждения владельца» — гейт был убран из роли,
# но просочился через чужой артефакт, прочитанный следующей ролью.
САМОСТОП = re.compile(
    r"(ждём|ждем|до|перед)\s+(подтверждени[ея]\s+)?владельц"
    r"|не\s+разрешает\s+разработку"
    r"|код\s+не\s+начина"
    r"|требуется\s+решение\s+владельца"
    r"|до\s+продуктового\s+вердикта", re.I)


# Что роли кладут по ходу работы. Это следы процесса, а не изменение продукта, и ревьюер
# не должен считать их выходом за границы экрана: в волне r04 он именно так забраковал
# карточки 01 и 02 за файлы `tests/cases/*.md`, которые писал тестировщик по своей роли.
СТАДИЙНЫЕ = ("night/", "tasks/", "tests/cases/", "docs/evidence/", "docs/blockers/",
             "docs/process/", "docs/product/ui-inventory.json")


def дифф_реализации(корень: Path) -> list[str]:
    """Только те файлы, которые действительно меняют продукт."""
    р = _git("status", "--porcelain", cwd=корень)
    файлы = []
    for строка in р.stdout.splitlines():
        путь = строка[3:].strip()
        if путь and not путь.startswith(СТАДИЙНЫЕ):
            файлы.append(путь)
    return sorted(файлы)


def артефакт_готов(папка: Path, роль: str) -> tuple[bool, str]:
    """Единственная проверка, которую делает оркестратор. Никакого разбора вердиктов."""
    имя, нужны = АРТЕФАКТ.get(роль, (None, []))
    if имя is None:
        return True, ""
    файл = папка / имя
    if not файл.exists():
        return False, f"нет файла {имя}"
    текст = файл.read_text(encoding="utf-8", errors="replace")
    if роль in СУДЯЩИЕ and not ВЕРДИКТ.search(текст):
        return False, f"в {имя} нет машинной строки «ВЕРДИКТ: ...»"
    сам = САМОСТОП.search(текст)
    if сам and роль not in ("product", "product-acceptor"):
        return False, (f"{имя} останавливает сам себя формулировкой «{сам.group(0)}»: "
                       f"открытые вопросы закрывает роль product, а не владелец ночью")
    есть = секции(текст)
    нет = [s for s in нужны if not any(s.lower() in e.lower() for e in есть)]
    if нет:
        return False, f"в {имя} нет секций: {', '.join(нет)}"
    return True, ""


# Роли, чей вердикт управляет маршрутом. Каждая обязана поставить машинную строку.
СУДЯЩИЕ = ("requirement-critic", "product", "reviewer", "ui-critic", "ux-judge", "blocker-skeptic")

# Единственная строка, которую оркестратор разбирает в чужом тексте.
ВЕРДИКТ = re.compile(r"^\s*ВЕРДИКТ:\s*(ЧИСТО|РЕШЕНО|НАХОДКИ|НЕ\s+РЕШЕНО)\s*(\d+)?\s*$", re.M | re.I)


def вердикт(папка: Path, роль: str) -> tuple[str, str]:
    """Читает машинный вердикт роли. Прозу не разбирает — и в этом весь смысл.

    Раньше здесь стоял поиск по словам внутри секции «Находки», и он дважды подвёл в одну
    ночь: «Нарушений не найдено» было прочитано как находка, а «нет, тип неверный: это домен»
    сбило определение типа, потому что рядом стояло слово «фича». Разбирать свободный текст
    ради управляющего решения — это ровно тот класс хрупкости, на котором умер прошлый
    конвейер, только переехавший из ответа модели внутрь файла.

    Теперь роль обязана поставить одну однозначную строку. Нет строки — шаг не пройден,
    громко и сразу, а не молча-успешно.
    """
    имя, _ = АРТЕФАКТ.get(роль, (None, []))
    if имя is None or not (папка / имя).exists():
        return "", f"нет файла {имя}"
    м = ВЕРДИКТ.search((папка / имя).read_text(encoding="utf-8", errors="replace"))
    if not м:
        return "", f"в {имя} нет строки «ВЕРДИКТ: ЧИСТО» или «ВЕРДИКТ: НАХОДКИ N»"
    слово = re.sub(r"\s+", " ", м.group(1).upper())
    сколько = м.group(2) or ""
    return ("чисто" if слово in ("ЧИСТО", "РЕШЕНО") else "находки"), сколько


def есть_находки(папка: Path, роль: str) -> bool:
    """Возвращает ли роль карточку назад. Только по машинному вердикту."""
    if роль not in СУДЯЩИЕ:
        return False
    исход, _ = вердикт(папка, роль)
    return исход == "находки"


def поле(папка: Path, файл: str, секция: str) -> str:
    п = папка / файл
    if not п.exists():
        return ""
    m = re.search(rf"^#{{1,4}}\s*{re.escape(секция)}\s*$(.*?)(?=^#{{1,4}}\s|\Z)",
                  п.read_text(encoding="utf-8", errors="replace"), re.M | re.S)
    return m.group(1).strip() if m else ""


def тип_карточки(папка: Path) -> str:
    """Берёт исправленный критиком тип. Сначала машинная строка, проза — запасной путь."""
    for файл in ("SVERKA.md", "RAZBOR.md"):
        м = re.search(r"^\s*ТИП:\s*(баг|фича|домен|отложить)\s*$",
                      (папка / файл).read_text(encoding="utf-8", errors="replace")
                      if (папка / файл).exists() else "", re.M | re.I)
        if м:
            return м.group(1).lower()
    for файл in ("SVERKA.md", "RAZBOR.md"):
        текст = поле(папка, файл, "Тип").lower()
        верный = re.search(r"верн(?:ый|о)\s*(?:тип\s*)?(?:[-—:]\s*)?`?(баг|фича|домен)`?", текст)
        if верный:
            return верный.group(1)
        найдено = set(re.findall(r"(?<![а-яё])(баг|фича|домен)(?![а-яё])", текст))
        if len(найдено) == 1:
            return найдено.pop()
    return ""


def выбрать_dev(папка: Path) -> str:
    """Экран из реестра — правит фронт, иначе бэкенд."""
    return "screen-dev" if re.search(r"\bS-\d\d\b", поле(папка, "RAZBOR.md", "Экраны")) else "backend-dev"


def проверить_сохранение(рабочая: РабочаяКарточка) -> tuple[bool, str]:
    """Dev обязан оставить коммит; разрешены только ночные артефакты."""
    sha = _git("rev-parse", "HEAD", cwd=рабочая.корень)
    if sha.returncode != 0 or not sha.stdout.strip():
        return False, "у карточки нет branch SHA"
    if getattr(рабочая, "base_sha", "") and sha.stdout.strip() == рабочая.base_sha:
        return False, "dev не оставил отдельный коммит в карточной ветке"
    статус = _git("status", "--porcelain", cwd=рабочая.корень)
    грязные = []
    for строка in статус.stdout.splitlines():
        путь = строка[3:].strip()
        if путь.startswith("night/") or путь.startswith("docs/evidence/"):
            continue
        грязные.append(путь)
    if грязные:
        return False, "грязный implementation diff: " + ", ".join(грязные[:8])
    return True, sha.stdout.strip()


def проверить_вход_волны(волна: Path, ид_список: list[str]) -> list[str]:
    ошибки = []
    if not (волна / "MAP.md").exists() or not all(
            s.lower() in " ".join(секции((волна / "MAP.md").read_text(encoding="utf-8"))) .lower()
            for s in ("Карта", "Порядок")):
        ошибки.append("MAP.md: нет секций «Карта» и «Порядок»")
    for ид in ид_список:
        папка = волна / "cards" / ид
        for файл, нужны in (("RAZBOR.md", АРТЕФАКТ["analyst"][1]),
                            ("SVERKA.md", АРТЕФАКТ["requirement-critic"][1])):
            текст = (папка / файл).read_text(encoding="utf-8", errors="replace") if (папка / файл).exists() else ""
            есть = секции(текст)
            if any(not any(s.lower() in e.lower() for e in есть) for s in нужны):
                ошибки.append(f"{ид}/{файл}: обязательные секции отсутствуют")
    return ошибки


ПОЛОСА: dict[str, int] = {}          # карточка -> номер полосы стенда
СТЕНД: dict[tuple[str, str], str] = {}  # карточка/worktree SHA -> строка с адресом и кредами
_АКТИВНАЯ_ВОЛНА: Path | None = None


def санитарный_снимок(корень: Path = КОРЕНЬ) -> Path | None:
    """Только существующий sanitized snapshot из главного checkout, без fallback."""
    снимок = (корень / ".stand" / "sanitized-latest.dump").resolve()
    return снимок if снимок.name == "sanitized-latest.dump" and снимок.is_file() else None


def _сигинтум(_сигнал: int, _кадр: object) -> None:
    if _АКТИВНАЯ_ВОЛНА is not None:
        журнал(_АКТИВНАЯ_ВОЛНА, "получен SIGINT; результаты сохранены, продолжение возможно через resume")
    raise KeyboardInterrupt


def поднять_стенд(полоса: int, рабочая: РабочаяКарточка | None = None) -> str:
    """Стенд поднимает скрипт, а не агент.

    Агенту, которому дали искать стенд самому, ничего не стоит найти «похожий» и молча
    проверить не то — а хуже честного отказа только успешный отчёт о проверке чужого экрана.
    Поэтому кликер получает готовые адрес и пароль строкой в промпте.
    """
    корень = рабочая.корень if рабочая else КОРЕНЬ
    ид = рабочая.ид if рабочая else f"lane-{полоса}"
    снимок = санитарный_снимок(КОРЕНЬ)
    if снимок is None:
        return ""
    sha_р = _git("rev-parse", "HEAD", cwd=корень)
    sha = sha_р.stdout.strip() if sha_р.returncode == 0 else "unknown"
    ключ = (ид, sha)
    if ключ in СТЕНД:
        return СТЕНД[ключ]
    env = os.environ.copy()
    env.update({"WMS_STAND_FORCE_RECREATE": "1", "COMPOSE_BUILD": "1",
                "COMPOSE_FORCE_RECREATE": "1", "WMS_API_PORT": f"3008{полоса}",
                "WMS_WEB_PORT": f"3017{полоса}", "WMS_SELLER_WEB_PORT": f"3018{полоса}",
                "WMS_DB_PORT": f"3043{полоса}", "WMS_REDIS_PORT": f"3037{полоса}",
                "WMS_SANITIZED_SNAPSHOT": str(снимок)})
    compose = ["docker", "compose", "-p", f"wms-lane-{полоса}",
               "-f", str(корень / "docker-compose.yml"),
               "-f", str(корень / "docker-compose.lane.yml")]
    # `up.sh` intentionally owns restoring the snapshot, but it does not accept
    # compose flags. Build and remove the previous lane containers here so its
    # subsequent `up -d` can only start images from this card worktree.
    build = subprocess.run(compose + ["build"], cwd=корень, env=env,
                           capture_output=True, text=True, timeout=15 * 60)
    if build.returncode != 0:
        return ""
    recreate = subprocess.run(compose + ["rm", "-sf"], cwd=корень, env=env,
                               capture_output=True, text=True, timeout=5 * 60)
    if recreate.returncode != 0:
        return ""
    р = subprocess.run([str(корень / "scripts/stand/up.sh"), str(полоса)],
                       cwd=корень, env=env, capture_output=True, text=True, timeout=15 * 60)
    хвост = (р.stdout or "") + (р.stderr or "")
    СТЕНД[ключ] = хвост[-600:] if р.returncode == 0 else ""
    return СТЕНД[ключ]


def промпт(роль: str, ид: str, папка: Path, волна: Path, корень: Path = КОРЕНЬ,
           рабочая: РабочаяКарточка | None = None) -> str:
    имя, нужны = АРТЕФАКТ.get(роль, (None, []))
    хвост = (f"Результат запиши в `{папка / имя}`, "
             f"обязательные секции: {', '.join(нужны)}." if имя else
             "Артефакта не оставляешь, результат проверяется гейтами.")
    return (
        f"Карточка `{ид}`. Твоя рабочая копия — `{корень}`.\n"
        f"ВСЕ пути пиши абсолютные, от `{корень}`. Не уходи в другой каталог проекта, "
        f"даже если в CLAUDE.md указан иной путь: это отдельная рабочая копия.\n"
        f"Твоя папка — `{папка}`, там лежат артефакты предыдущих ролей, прочитай их.\n"
        f"Карта задевания волны — `{волна / 'MAP.md'}`.\n"
        f"Действуй строго по своей роли. {хвост}"
        + стенд_для(роль, ид, рабочая)
        + дифф_для(роль, рабочая)
    )


def дифф_для(роль: str, рабочая: "РабочаяКарточка | None") -> str:
    """Ревьюер судит правку продукта, а не следы работы конвейера.

    В волне r04 он забраковал две готовые карточки за файлы `tests/cases/*.md`, которые
    написал тестировщик по своей роли. Поэтому список правок продукта считает скрипт
    и отдаёт готовым, а не оставляет ревьюеру гадать по грязному дереву.
    """
    if роль not in ("reviewer", "ui-critic") or рабочая is None:
        return ""
    try:
        файлы = дифф_реализации(рабочая.корень)
    except Exception:                                        # noqa: BLE001
        return ""
    if not файлы:
        return "\n\nПравок продукта в карточке нет — только стадийные артефакты."
    список = "\n".join(f"  {ф}" for ф in файлы)
    return ("\n\nПравка продукта в этой карточке — ровно эти файлы:\n" + список +
            "\nОстальное в дереве — стадийные артефакты ролей (кейсы, разборы, доказательства). "
            "К границам экрана они отношения не имеют и находкой быть не могут.")


def стенд_для(роль: str, ид: str, рабочая: РабочаяКарточка | None = None) -> str:
    if роль != "clicker":
        return ""
    try:
        креды = поднять_стенд(ПОЛОСА.get(ид, 1), рабочая)
    except TypeError:
        # Совместимость с тестовым адаптером старого контракта.
        креды = поднять_стенд(ПОЛОСА.get(ид, 1))
    if not креды:
        return ("\n\nСТЕНД НЕ ПОДНЯЛСЯ. Не ищи его сам и не подбирай порты — "
                "запиши это как причину и остановись.")
    return ("\n\nСтенд уже поднят, вот он:\n" + креды +
            "\nНичего не поднимай и не ищи. Прод (194.87.96.144) запрещён.")


def шаг(ид: str, роль: str, папка: Path, волна: Path,
        корень: Path = КОРЕНЬ,
        рабочая: РабочаяКарточка | None = None) -> tuple[bool, str]:
    # Судью перезапускаем только если он в прошлый раз нашёл находки: тогда его вердикт
    # относится к старому коду. Чистый вердикт при возобновлении переигрывать незачем —
    # это лишний дорогой вызов на ровном месте.
    if артефакт_готов(папка, роль)[0] and (роль not in СУДЬИ or not есть_находки(папка, роль)):
        журнал(волна, f"  {ид} · {роль}: уже сделано, пропускаю")
        return True, ""
    for попытка in range(ПОВТОРОВ + 1):
        код, хвост = запустить(роль, промпт(роль, ид, папка, волна, корень, рабочая), cwd=корень)
        готов, беда = артефакт_готов(папка, роль)
        if готов:
            журнал(волна, f"  {ид} · {роль}: готово")
            return True, ""
        журнал(волна, f"  {ид} · {роль}: {беда} (код {код}, попытка {попытка + 1})")
    return False, f"{роль}: {беда}\n{хвост.strip()[-600:]}"


def сверить_архитектуру(волна: Path, ид_список: list[str]) -> None:
    """Барьер после арх-решений: свести их между собой, пока не написан ни один контракт.

    Первый архитектор пишет решение по каждой карточке в своей параллельной полосе и не видит
    готовых решений соседей — их в тот момент ещё нет. Карта задевания предупреждает, что
    карточки связаны, но что именно каждая выберет, знать заранее нельзя. Поэтому нужен второй
    проход, который читает все решения разом и переписывает то, что не сходится: два разумных
    по отдельности решения дают несовместимую пару, и обнаруживается это в коде через восемь
    часов работы.
    """
    файл = волна / "ARCH-CROSS.md"
    if файл.exists():
        return
    решения = [и for и in ид_список if (волна / "cards" / и / "ARCH.md").exists()]
    if len(решения) < 2:
        return                       # сводить нечего
    журнал(волна, f"\n### перекрёстная сверка архитектуры ({len(решения)} решений)")
    код, хвост = запустить("arch-critic", (
        f"Твоя рабочая копия — `{КОРЕНЬ}`, все пути абсолютные.\n"
        f"Арх-решения волны: " + ", ".join(f"`{волна / 'cards' / и / 'ARCH.md'}`" for и in решения) +
        f"\nКарта задевания — `{волна / 'MAP.md'}`.\n"
        f"Прочитай все решения разом, найди где они друг друга ломают, поправь их и запиши "
        f"итог в `{файл}`. Секции: Столкновения, Что переписал, Порядок, "
        f"Что осталось за бортом. Первой строкой — ВЕРДИКТ: ЧИСТО или ВЕРДИКТ: НАХОДКИ N."))
    журнал(волна, "перекрёстная сверка: " + ("готова" if файл.exists()
                                             else f"НЕ СОЗДАНА (код {код}) {хвост.strip()[-200:]}"))


def провести(ид: str, волна: Path, рабочая: РабочаяКарточка | None = None) -> str:
    if рабочая is None:
        рабочая = РабочаяКарточка(ид, 0, КОРЕНЬ, волна, волна / "cards" / ид, "")
    папка = рабочая.папка
    волна = рабочая.волна
    папка.mkdir(parents=True, exist_ok=True)
    тип = тип_карточки(папка)
    if not тип and (папка / "TYPE.txt").exists():
        тип = (папка / "TYPE.txt").read_text(encoding="utf-8").strip().lower()
    if тип not in ЦЕПОЧКИ:
        журнал(волна, f"{ид}: тип «{тип or 'не назван'}» — отложено")
        (папка / "OTLOZHENO.md").write_text(f"Тип не определён: «{тип}»\n", encoding="utf-8")
        return "отложено"

    круг = 0
    цепочка = ЦЕПОЧКИ[тип]
    i = 0
    while i < len(цепочка):
        роль = выбрать_dev(папка) if цепочка[i] == "dev" else цепочка[i]
        ок, беда = шаг(ид, роль, папка, волна, рабочая.корень, рабочая)
        if not ок:
            (папка / "OTLOZHENO.md").write_text(беда + "\n", encoding="utf-8")
            журнал(волна, f"{ид}: отложено на шаге {роль}")
            return "отложено"
        if роль in СУДЬИ and есть_находки(папка, роль):
            круг += 1
            if круг > КРУГОВ:
                (папка / "OTLOZHENO.md").write_text(
                    f"{роль} нашёл находки после {КРУГОВ} кругов правки\n", encoding="utf-8")
                журнал(волна, f"{ид}: отложено — {роль}, круги кончились")
                return "отложено"
            журнал(волна, f"  {ид} · {роль}: находки, круг {круг} — назад к разработке")
            мусор_для_повтора = ("DEV.md", АРТЕФАКТ[роль][0])
            if роль == "ui-critic":
                мусор_для_повтора += ("CONTRACT.md", "CASES.md", "DESIGN-REVIEW.md")
            for мусор in мусор_для_повтора:
                (папка / мусор).unlink(missing_ok=True)
            i = цепочка.index("ux-architect" if роль == "ui-critic" else "dev")
            continue
        i += 1
    сохранено, сведения = проверить_сохранение(рабочая)
    if not сохранено:
        (папка / "OTLOZHENO.md").write_text(сведения + "\n", encoding="utf-8")
        журнал(волна, f"{ид}: отложено — {сведения}")
        return "отложено"
    (папка / "BRANCH-SHA.txt").write_text(сведения + "\n", encoding="utf-8")
    (папка / "OTLOZHENO.md").unlink(missing_ok=True)
    журнал(волна, f"{ид}: СДЕЛАНО")
    return "сделано"


def карточки(волна: Path) -> list[str]:
    корзина = волна / "cards"
    return sorted(п.name for п in корзина.iterdir() if п.is_dir()) if корзина.exists() else []


def проверить_стыки() -> list[str]:
    """Хватает ли каждому шагу того, что произвели шаги до него.

    Эта проверка существует потому, что цепочку легко собрать как список имён и не заметить,
    что роль требует файл, которого никто не создаёт. Именно так легла волна r04: разработчик
    требует контракт, а в цепочке бага контракта не было, и девять карточек узнали об этом
    ночью, по одной, за деньги.
    """
    беды: list[str] = []
    # Что кладут вечерние роли и сам оркестратор до старта цепочки.
    до_цепочки = {"ISTOCHNIK.md", "RAZBOR.md", "SVERKA.md", "MAP.md", "KANDIDATY.md"}
    for тип, цепочка in ЦЕПОЧКИ.items():
        есть = set(до_цепочки)
        for шаг_ in цепочка:
            роли = ("screen-dev", "backend-dev") if шаг_ == "dev" else (шаг_,)
            for роль in роли:
                варианты = ТРЕБУЕТ.get(роль)
                if варианты and not any(set(в) <= есть for в in варианты):
                    нужно = " или ".join("+".join(в) for в in варианты)
                    беды.append(
                        f"цепочка «{тип}»: шагу {роль} нужен {нужно}, "
                        f"а до него есть только {', '.join(sorted(есть)) or 'ничего'}")
            for роль in роли:
                имя, _ = АРТЕФАКТ.get(роль, (None, []))
                if имя:
                    есть.add(имя)
    return беды


def проверки_старта() -> list[str]:
    """Падать надо при владельце, а не в три ночи на двадцатой карточке."""
    беды = []
    if not (КОРЕНЬ / ".claude/agents").exists():
        беды.append("нет каталога .claude/agents")
        return беды
    роли = {p.stem for p in (КОРЕНЬ / ".claude/agents").glob("*.md")}
    нужны = {r for ц in ЦЕПОЧКИ.values() for r in ц if r != "dev"}
    нужны |= {"intake", "analyst", "requirement-critic", "product-acceptor",
              "screen-dev", "backend-dev"}
    for р in sorted(нужны - роли):
        беды.append(f"роль {р} есть в цепочке, но нет файла .claude/agents/{р}.md")
    for р in sorted(нужны):
        if р not in АРТЕФАКТ:
            беды.append(f"для роли {р} не назван артефакт в таблице АРТЕФАКТ")
    команда = os.environ.get("NIGHT_CODEX_BIN", "codex") if ИСПОЛНИТЕЛЬ == "codex" else "claude"
    if not shutil.which(команда):
        беды.append(f"в PATH нет команды {команда}")
    беды.extend(проверить_стыки())
    # Роль с артефактом, которую никто не запускает, — тихая дыра: снаружи этапы зелёные,
    # а работа не делается. Так перекрёстная сверка архитектуры существовала функцией и
    # ни разу не вызывалась, и архитекторы могли принять несовместимые решения незаметно.
    исходник = Path(__file__).read_text(encoding="utf-8", errors="replace")
    в_цепочках = {р for ц in ЦЕПОЧКИ.values() for р in ц} | {"screen-dev", "backend-dev"}
    for роль in АРТЕФАКТ:
        if роль in в_цепочках:
            continue
        # Роль может запускаться и через переменную (вечерний цикл), поэтому ищем любое
        # второе упоминание имени в коде, кроме самой строки таблицы АРТЕФАКТ.
        if исходник.count(f'"{роль}"') < 2:
            беды.append(f"роль {роль} объявлена в АРТЕФАКТ, но её никто не запускает")
    return беды


def вечер(исходник: Path, fresh: bool = False, run_id: str | None = None) -> int:
    if fresh:
        if not run_id:
            raise ValueError("для --fresh нужен --run-id")
        волна = создать_свежую_волну(исходник, run_id)
    else:
        волна = КОРЕНЬ / "night" / исходник.stem
    (волна / "cards").mkdir(parents=True, exist_ok=True)
    журнал(волна, f"# Волна {волна.name}\n\n## Понимание")

    # Нарезка идемпотентна: повторный вечер продолжает волну, а не режет её заново.
    # Иначе агент придумывает новые идентификаторы, и на девять задач появляется
    # тринадцать карточек — половина дубли, и утром не понять, какая настоящая.
    if карточки(волна):
        журнал(волна, f"карточки уже нарезаны ({len(карточки(волна))}), нарезку пропускаю")
        код, хвост = 0, ""
    else:
        код, хвост = запустить("intake", (
            f"Твоя рабочая копия — `{КОРЕНЬ}`. ВСЕ пути абсолютные, не уходи в другой "
            f"каталог проекта, даже если в CLAUDE.md указан иной путь.\n"
            f"Разрежь список владельца из `{исходник}` на карточки. "
            f"На каждую заведи `{волна / 'cards'}/<id>/ISTOCHNIK.md` с дословной цитатой, "
        f"и общий `{волна / 'QUEUE.md'}` со списком id."))
    ид_список = карточки(волна)
    if not ид_список:
        журнал(волна, f"нарезка не дала карточек (код {код}): {хвост.strip()[-400:]}")
        return 1
    журнал(волна, f"нарезано карточек: {len(ид_список)}")

    for имя, роль in (("разбор", "analyst"), ("сверка", "requirement-critic")):
        журнал(волна, f"\n### {имя}")
        with futures.ThreadPoolExecutor(max_workers=6) as пул:
            # Критик идёт по ВСЕМ карточкам, а не только по фичам и доменам. Его главная
            # работа — поймать неверный тип, а неверный тип чаще всего выглядит как «баг»:
            # если фильтровать по типу, ошибка аналитика становится невидимой навсегда.
            список = ид_список
            def безопасный_шаг(и: str) -> tuple[bool, str]:
                try:
                    return шаг(и, роль, волна / "cards" / и, волна)
                except Exception as е:  # одна карточка не останавливает вечер
                    папка = волна / "cards" / и
                    папка.mkdir(parents=True, exist_ok=True)
                    (папка / "OTLOZHENO.md").write_text(f"исключение: {е}\n", encoding="utf-8")
                    журнал(волна, f"{и} · {роль}: отложено — исключение {е}")
                    return False, str(е)
            list(пул.map(безопасный_шаг, список))

    собрать_вопросы(волна, ид_список)

    журнал(волна, "\n### карта задевания")
    запустить("solution-architect", (
        f"Твоя рабочая копия — `{КОРЕНЬ}`, все пути абсолютные.\n"
        f"Собери карту задевания волны. Прочитай RAZBOR.md всех карточек в "
        f"`{волна / 'cards'}` целиком, все сразу, и напиши "
        f"`{волна / 'MAP.md'}`: по каждой карточке — задетые экраны, "
        f"файлы и таблицы, столкновения с другими карточками, порядок и полоса, и список "
        f"смежных экранов, чьи кейсы придётся перекликать. Секции: `## Карта`, `## Порядок`."))
    карта_готова = not any(e.startswith("MAP.md:") for e in проверить_вход_волны(волна, ид_список))
    журнал(волна, "карта: " + ("готова" if карта_готова else "НЕ СОЗДАНА"))
    журнал(волна, "\nПонимание собрано, перехожу к исполнению без остановки.")
    return 0 if карта_готова else 2


def ночь(волна: Path, полос: int) -> int:
    global _АКТИВНАЯ_ВОЛНА
    _АКТИВНАЯ_ВОЛНА = волна
    signal.signal(signal.SIGINT, _сигинтум)
    ид_список = карточки(волна)
    if not ид_список:
        print(f"в {волна}/cards нет карточек — сначала вечер", file=sys.stderr)
        return 1
    входные_ошибки = проверить_вход_волны(волна, ид_список)
    if входные_ошибки:
        журнал(волна, "входной гейт красный: " + "; ".join(входные_ошибки))
        return 2
    for н, и in enumerate(ид_список):
        ПОЛОСА[и] = н % полос + 1
    try:
        рабочие = рабочие_карточки(волна, ид_список, полос)
    except (OSError, RuntimeError) as е:
        журнал(волна, f"изоляция карточек не создана: {е}")
        return 2
    журнал(волна, f"\n## Ночь · карточек {len(ид_список)} · полос {полос}")
    # Барьер: домены сначала доводим до арх-решения, потом сводим решения между собой,
    # и только после этого пускаем всё дальше. Без этого несколько архитекторов принимают
    # несовместимые решения, а этапы при этом зелёные — снаружи не видно ничего.
    домены = [и for и in ид_список if тип_карточки(волна / "cards" / и) == "домен"]
    if домены:
        журнал(волна, f"\n### арх-решения по доменам ({len(домены)})")
        with futures.ThreadPoolExecutor(max_workers=полос) as пул_арх:
            list(пул_арх.map(
                lambda и: шаг(и, "solution-architect", волна / "cards" / и, волна,
                              рабочие.get(и)), домены))
        сверить_архитектуру(волна, домены)

    with futures.ThreadPoolExecutor(max_workers=полос) as пул:
        def безопасно(и: str) -> str:
            try:
                return провести(и, волна, рабочие[и])
            except Exception as е:  # карточка не должна остановить соседей
                папка = рабочие[и].папка
                папка.mkdir(parents=True, exist_ok=True)
                (папка / "OTLOZHENO.md").write_text(f"исключение: {е}\n", encoding="utf-8")
                журнал(волна, f"{и}: отложено — исключение {е}")
                return "отложено"
        итоги = list(пул.map(безопасно, ид_список))
    сделано = итоги.count("сделано")
    журнал(волна, f"\n## Итог: сделано {сделано}, отложено {len(итоги) - сделано}")

    запустить("product-acceptor", (
        f"Твоя рабочая копия — `{КОРЕНЬ}`, все пути абсолютные.\n"
        f"Прими работу ночи одним проходом. Карточки — `{волна / 'cards'}`, "
        f"скриншоты — `{КОРЕНЬ}/docs/evidence/`. Карточки проверяй в отдельных ветках/worktree:\n"
        + "\n".join(
            f"- {и}: branch {рабочие[и].ветка}, SHA "
            f"{_git('rev-parse', 'HEAD', cwd=рабочие[и].корень).stdout.strip() or 'unknown'}, "
            f"worktree {рабочие[и].корень}, artifacts {рабочие[и].папка}"
            for и in ид_список)
        + f"\nНе смешивай и не объединяй ветки автоматически. Отчёт запиши в `{волна / 'OTCHET.md'}`."))
    готов, беда = артефакт_готов(волна, "product-acceptor")
    журнал(волна, "отчёт: " + ("готов" if готов else "НЕ СОЗДАН/НЕПОЛОН: " + беда))
    _АКТИВНАЯ_ВОЛНА = None
    return 0 if готов and not any(итог == "отложено" for итог in итоги) else 2


def собрать_вопросы(волна: Path, ид_список: list[str]) -> int:
    """Один залп вопросов после анализа — и работа идёт дальше, не дожидаясь ответа.

    Владелец может быть рядом и ответить сразу, а может спать. Поэтому вопросы задаются
    ровно один раз и все сразу, а не по одному в течение ночи, и ни один из них не
    останавливает конвейер: не ответили — решает продакт и помечает допущением.
    """
    вопросы: list[str] = []
    for ид in ид_список:
        папка = волна / "cards" / ид
        for файл in ("RAZBOR.md", "SVERKA.md"):
            текст = поле(папка, файл, "Открытые вопросы") or поле(папка, файл, "Вопросы и допущения")
            # Берём только заголовки пунктов, а не все строки подряд: роли пишут вопрос
            # абзацем с пояснением, и построчная нарезка превращает десяток вопросов
            # в двести обрывков посреди предложений, которые невозможно читать.
            for строка in текст.splitlines():
                м = re.match(r"^\s*(?:\d+[.)]|[-*])\s+\*\*(.+?)\*\*", строка)
                if not м:
                    м = re.match(r"^\s*(?:\d+[.)])\s+(.{15,140})$", строка)
                if м:
                    вопросы.append(f"- **{ид}** · {м.group(1).strip().rstrip('.:')}")
    файл = волна / "VOPROSY.md"
    if not вопросы:
        файл.write_text("# Вопросы\n\nВопросов на анализе не возникло.\n", encoding="utf-8")
        журнал(волна, "вопросов на анализе нет")
        return 0
    файл.write_text(
        "# Вопросы после анализа\n\n"
        "Задаются один раз и все сразу. Работа на них не останавливается: пока ответа нет,\n"
        "решение принимает роль `product` и помечает его допущением. Чтобы ответить —\n"
        f"положи ответы в `{волна / 'OTVETY.md'}` в любой момент до того, как продакт\n"
        "дойдёт до карточки; он читает этот файл и ставит твои ответы выше своих решений.\n\n"
        + "\n".join(вопросы) + "\n", encoding="utf-8")
    журнал(волна, f"вопросов после анализа: {len(вопросы)} — см. {файл}")
    print("\n" + "─" * 70)
    print(f"ВОПРОСЫ ПОСЛЕ АНАЛИЗА ({len(вопросы)}). Работа продолжается, ответ не обязателен.")
    print(f"Ответить: положи ответы в {файл.parent / 'OTVETY.md'}\n")
    for в in вопросы:
        print("  " + в.replace("**", ""))
    print("─" * 70 + "\n", flush=True)
    return len(вопросы)


def обзор(волна: Path) -> int:
    """Что происходит прямо сейчас. Читает только диск, работающую волну не трогает."""
    корзина = волна / "cards"
    if not корзина.exists():
        print(f"нет карточек в {корзина}", file=sys.stderr)
        return 1
    сейчас = time.time()
    # Ищем любую фазу, а не только ночь: обзор, сказавший «не запущен» во время вечера,
    # пугает зря и заставляет лезть в процессы руками.
    # На macOS pgrep -a не печатает командную строку, только номера процессов, поэтому
    # фазу через него не определить. Берём команды у ps по найденным номерам.
    def команды(образец: str) -> list[str]:
        номера = subprocess.run(["pgrep", "-f", образец], capture_output=True, text=True)
        стр = [н for н in номера.stdout.split() if н.isdigit()]
        if not стр:
            return []
        пс = subprocess.run(["ps", "-o", "command=", "-p", ",".join(стр)],
                            capture_output=True, text=True)
        return [с for с in пс.stdout.splitlines() if с.strip()]

    свои = команды("night.py")
    фаза = next((ф for ф in ("вечер", "ночь", "полный")
                 if any(ф in с for с in свои)), "")
    жив = bool(свои)
    сколько = sum(1 for с in команды("claude") if " -p " in с or с.endswith(" -p"))
    print(f"волна {волна.name} · "
          f"{'идёт ' + (фаза or 'работа') if жив else 'оркестратор не запущен'} · "
          f"агентов в работе: {сколько}\n")
    for п in sorted(x for x in корзина.iterdir() if x.is_dir()):
        тип = поле(п, "RAZBOR.md", "Тип").strip() or "?"
        тип = re.sub(r"^ТИП:\s*", "", тип, flags=re.I).splitlines()[0][:8] if тип else "?"
        цепочка = ЦЕПОЧКИ.get(тип_карточки(п), [])
        готово, следующий = [], "—"
        for роль in цепочка:
            роли = ("screen-dev", "backend-dev") if роль == "dev" else (роль,)
            if any(артефакт_готов(п, р)[0] for р in роли):
                готово.append(роль)
            else:
                следующий = роль
                break
        свежесть = max((ф.stat().st_mtime for ф in п.glob("*.md")), default=0)
        молчит = int((сейчас - свежесть) / 60) if свежесть else 0
        состояние = "отложена" if (п / "OTLOZHENO.md").exists() else (
            "СДЕЛАНА" if цепочка and len(готово) == len(цепочка) else следующий)
        причина = ""
        if (п / "OTLOZHENO.md").exists():
            причина = " · " + (п / "OTLOZHENO.md").read_text(
                encoding="utf-8", errors="replace").strip().splitlines()[0][:60]
        print(f"  {п.name:14} {тип:7} {len(готово)}/{len(цепочка) or '?'}  "
              f"{состояние:18} молчит {молчит:3} мин{причина}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Ночной оркестратор WMS")
    p.add_argument("фаза", choices=["вечер", "ночь", "полный", "проверка", "обзор", "очистить"])
    p.add_argument("путь", nargs="?", help="файл со списком (вечер) или папка волны (ночь)")
    p.add_argument("--полос", type=int, default=6)   # полоса на агента: ждать нечего
    p.add_argument("--fresh", action="store_true",
                   help="вечером создать новый каталог прогона")
    p.add_argument("--run-id", help="идентификатор свежего прогона")
    p.add_argument("--удалить", action="store_true",
                   help="для фазы очистить удалить только чистые worktree; ветки сохраняются")
    a = p.parse_args()

    if беды := проверки_старта():
        print("не запускаюсь, пока это не починено:", file=sys.stderr)
        for б in беды:
            print(f"  - {б}", file=sys.stderr)
        return 2
    if a.фаза == "обзор":
        if not a.путь:
            p.error("нужен путь к волне")
        return обзор(Path(a.путь).resolve())
    if a.фаза == "проверка":
        print("проверки старта пройдены")
        return 0
    if not a.путь:
        p.error("нужен путь")
    путь = Path(a.путь).resolve()
    if a.фаза == "очистить":
        for строка in очистить_рабочие_карточки(путь, удалить=a.удалить):
            print(строка)
        return 0
    if a.фаза == "вечер":
        return вечер(путь, fresh=a.fresh, run_id=a.run_id)
    if a.фаза == "полный":
        # Один заход от списка задач до готового результата, без пауз и без участия
        # владельца посередине. Разделение на «вечер» и «ночь» было моей выдумкой: оно
        # существовало ради вопросов владельцу, а вопросов владельцу больше нет — их
        # закрывает решением роль product.
        код = вечер(путь, fresh=a.fresh, run_id=a.run_id)
        if код != 0:
            return код
        имя = f"{путь.stem}-{a.run_id}" if a.fresh and a.run_id else путь.stem
        волна = КОРЕНЬ / "night" / имя
        if not волна.exists():
            волна = путь if путь.is_dir() else КОРЕНЬ / "night" / путь.stem
        return ночь(волна, a.полос)
    return ночь(путь, a.полос)


if __name__ == "__main__":
    sys.exit(main())
