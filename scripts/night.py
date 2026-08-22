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
import contextlib
from dataclasses import dataclass
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

КОРЕНЬ = Path(__file__).resolve().parents[1]
ТАЙМАУТ = 20 * 60          # один шаг не имеет права съесть ночь
# Разработка и переделка идут дольше остальных шагов: надо прочитать контракт, кейсы и
# находки ревью, поправить код и прогнать гейты. Двадцати минут не хватало, и карточка
# ложилась не потому, что задача сложная, а потому что не успела.
ТАЙМАУТ_КОДА = 40 * 60
ПОВТОРОВ = 1               # столько раз перезапускаем шаг, не оставивший файла
КРУГОВ = 1                 # одна обычная переделка, затем сразу эскалация
ЭСКАЛАЦИОННЫХ_КРУГОВ = 2  # два конечных Sol-ремонта; бесконечный цикл запрещён
МИНИМУМ_АГЕНТОВ = 6       # карточки не должны простаивать из-за занятого контроллера

# Роль → файл, который она обязана оставить, и секции, которые в нём обязаны быть.
# None вместо файла означает «шаг проверяется гейтами, а не артефактом».
АРТЕФАКТ = {
    "intake":             ("ISTOCHNIK.md",     ["Дословно"]),
    "analyst":            ("RAZBOR.md",        ["Дословно", "Что сейчас", "Что должно быть", "Тип"]),
    "requirement-critic": ("SVERKA.md",        ["Тип", "Расхождения"]),
    "solution-architect": ("ARCH.md",          ["Как это решают другие", "Решение", "Границы"]),
    "ux-architect":       ("CONTRACT.md",      ["Контракт", "Канон", "Макет", "Нехватка ui-kit"]),
    "ui-critic":          ("DESIGN-REVIEW.md", ["Находки"]),
    "tester":             ("CASES.md",         ["Назначенные кейсы"]),
    "breaker":            ("CASES.md",         ["Ломающие кейсы", "Смежные кейсы"]),
    "screen-dev":         ("DEV.md",           ["Изменённые файлы", "Гейты"]),
    "backend-dev":        ("DEV.md",           ["Изменённые файлы", "Гейты"]),
    "arch-critic":        (None,               []),
    "splitter":           ("FEATURES.md",      ["Фичи", "Порядок"]),
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
    # Сначала product закрывает развилки, затем UX превращает уже принятые решения в контракт.
    "ux-architect":       [("RAZBOR.md", "RESHENIYA.md")],
    "product":            [("RAZBOR.md",)],
    "tester":             [("RAZBOR.md",)],
    "breaker":            [("CASES.md",)],
    # Багу отдельный контракт не нужен: «что должно быть» из разбора плюс кейсы — это и есть
    # задание. Городить ради бага дорогого проектировщика значит платить опусом за то,
    # что уже написано.
    "screen-dev":         [("CONTRACT.md",), ("RAZBOR.md", "CASES.md")],
    "backend-dev":        [("CONTRACT.md",), ("RAZBOR.md", "CASES.md")],
    "splitter":           [("CONTRACT.md",), ("RAZBOR.md", "CASES.md")],
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
    "баг":   ["product", "tester", "splitter", "dev", "reviewer", "ui-critic", "clicker", "ux-judge"],
    "фича":  ["product", "ux-architect", "tester", "breaker", "splitter", "dev", "reviewer",
              "ui-critic", "clicker", "ux-judge"],
    "домен": ["solution-architect", "product", "ux-architect", "tester", "breaker",
              "splitter", "dev", "reviewer", "ui-critic", "clicker", "ux-judge"],
    # Разовый проход сборки реестра блокировок. Ничего не правит — только читает код
    # и пишет документы, поэтому им же безопасно обкатать сам оркестратор.
    "блокировки": ["blocker-collector", "blocker-skeptic"],
}

# Только эти вердикты возвращают уже написанный код разработчику.
ВОЗВРАЩАЮТ_К_DEV = ("reviewer", "ux-judge", "ui-critic")

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
    if зарегистрированный is None:
        # Параллельность можно повысить при resume, но уже сохранённую ветку/полосу
        # карточки менять нельзя: иначе оркестратор создаст пустую копию.
        совпадения = [(имя, каталог) for имя, каталог in существующие.items()
                       if имя.startswith(f"night/{волна.name}/lane-") and имя.endswith(f"/{ид}")]
        if len(совпадения) == 1:
            ветка, зарегистрированный = совпадения[0]
            полоса = int(re.search(r"/lane-(\d+)/", ветка).group(1))
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
    for имя in ("MAP.md", "QUEUE.md", "OTVETY.md"):
        источник = волна / имя
        назначение = рабочая_волна / имя
        if источник.exists() and (имя == "OTVETY.md" or not назначение.exists()):
            рабочая_волна.mkdir(parents=True, exist_ok=True)
            shutil.copy2(источник, назначение)
    база = _git("rev-parse", "HEAD", cwd=КОРЕНЬ).stdout.strip()
    return РабочаяКарточка(ид, полоса, путь, рабочая_волна, рабочая_папка, ветка, база)


def рабочие_карточки(волна: Path, карточки_: list[str], полос: int) -> dict[str, РабочаяКарточка]:
    """Подготовка до пула важна: git worktree add не должен гоняться параллельно."""
    if полос < 1:
        raise ValueError("число полос должно быть больше нуля")
    return {ид: _создать_рабочую_карточку(ид, волна, ПОЛОСА.get(ид, н % полос + 1))
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
    # Таймаут решаем здесь, а не параметром: лишний аргумент ломает вызовы, которые его
    # не ждут, и это уже дважды роняло проверки на ровном месте.
    таймаут = ТАЙМАУТ_КОДА if роль in ("screen-dev", "backend-dev") else ТАЙМАУТ
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
            cwd=cwd, capture_output=True, text=True, timeout=таймаут,
        )
        вывод = (р.stdout or "") + ("\n" + р.stderr if р.stderr else "")
        return р.returncode, _codex_текст(вывод)
    except subprocess.TimeoutExpired:
        return 124, f"шаг превысил {таймаут // 60} минут и снят"
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
             cwd: Path = КОРЕНЬ, модель: str | None = None) -> tuple[int, str]:
    """Один вызов агента. Падение подпроцесса — это просто ненулевой код, а не исключение."""
    if ошибка := _профиль_ошибка(профиль):
        return 2, ошибка
    if ИСПОЛНИТЕЛЬ == "codex":
        return _запустить_codex(роль, промпт, профиль, cwd)
    try:
        р = subprocess.run(
            ["claude", "-p", промпт, "--agent", роль,
             # acceptEdits разрешает только правку файлов: поиск в интернете при нём
             # всё равно спрашивает разрешения, а ночью дать его некому — и архитектор
             # писал ресёрч по памяти вместо живых источников, честно пометив это находкой.
             # Владелец разрешил любые действия, поэтому режим полный.
             "--permission-mode", "bypassPermissions"]
            + (["--model", модель] if модель else []),
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


def дифф_реализации(корень: Path, base_sha: str = "") -> list[str]:
    """Только те файлы, которые действительно меняют продукт."""
    имена: set[str] = set()
    if base_sha:
        р = _git("diff", "--name-only", f"{base_sha}..HEAD", cwd=корень)
        if р.returncode == 0:
            имена.update(строка.strip() for строка in р.stdout.splitlines() if строка.strip())
    р = _git("status", "--porcelain", cwd=корень)
    for строка in р.stdout.splitlines():
        путь = строка[3:].strip()
        if путь:
            имена.add(путь)
    return sorted(путь for путь in имена if not путь.startswith(СТАДИЙНЫЕ))


def артефакт_готов(папка: Path, роль: str) -> tuple[bool, str]:
    """Единственная проверка, которую делает оркестратор. Никакого разбора вердиктов."""
    имя, нужны = АРТЕФАКТ.get(роль, (None, []))
    if имя is None:
        return True, ""
    файл = папка / имя
    if not файл.exists():
        return False, f"нет файла {имя}"
    текст = файл.read_text(encoding="utf-8", errors="replace")
    if роль in РОЛИ_С_ВЕРДИКТОМ and not ВЕРДИКТ.search(текст):
        return False, f"в {имя} нет машинной строки «ВЕРДИКТ: ...»"
    # Ресёрч без единой ссылки — пересказ по памяти, а не исследование. Проверяем фактом,
    # потому что уговорить эту проверку нельзя, а промпт агент может и не выполнить.
    if роль == "solution-architect" and "Как это решают другие" in текст:
        раздел = текст.split("Как это решают другие", 1)[1].split("\n## ", 1)[0]
        if "http" not in раздел:
            return False, ("в ARCH.md раздел «Как это решают другие» без единой ссылки: "
                           "ресёрч делается поиском в интернете, а не по памяти")
    сам = САМОСТОП.search(текст)
    if сам and роль not in ("product", "product-acceptor"):
        return False, (f"{имя} останавливает сам себя формулировкой «{сам.group(0)}»: "
                       f"открытые вопросы закрывает роль product, а не владелец ночью")
    есть = секции(текст)
    нет = [s for s in нужны if not any(s.lower() in e.lower() for e in есть)]
    if нет:
        return False, f"в {имя} нет секций: {', '.join(нет)}"
    if роль == "splitter":
        заявлено = re.search(r"^ФИЧ:\s*(\d+)\s*$", текст, re.M)
        куски = фичи(папка)
        if not заявлено or int(заявлено.group(1)) != len(куски):
            return False, "FEATURES.md: ФИЧ не совпадает с числом блоков `### N.`"
        if any(not dev_для_фичи(кусок) for кусок in куски):
            return False, "FEATURES.md: каждый блок должен содержать только backend/ или frontend/"
        ui_решение = re.search(r"^UI-KIT:\s*(ХВАТАЕТ|НУЖНЫ\s+.+)\s*$",
                               (папка / "CONTRACT.md").read_text(
                                   encoding="utf-8", errors="replace")
                               if (папка / "CONTRACT.md").exists() else "", re.M | re.I)
        if ui_решение and ui_решение.group(1).upper().startswith("НУЖНЫ"):
            фронтовые = [кусок for кусок in куски if dev_для_фичи(кусок) == "screen-dev"]
            пути = re.findall(r"`([^`]*frontend/[^`]+)`", фронтовые[0]) if фронтовые else []
            пути = ["frontend/" + путь.split("frontend/", 1)[1] for путь in пути]
            if not пути or any(not путь.startswith("frontend/src/ui-kit/") for путь in пути):
                return False, "FEATURES.md: первый frontend-атом должен отдельно создать ui-kit"
    if роль == "ux-architect":
        решение_макета = re.search(
            r"^МАКЕТ:\s*(MOCKUP\.html|НЕ\s+НУЖЕН)\s*$", текст, re.M | re.I)
        ui_решение = re.search(
            r"^UI-KIT:\s*(ХВАТАЕТ|НУЖНЫ\s+.+)\s*$", текст, re.M | re.I)
        if not решение_макета or not ui_решение:
            return False, "CONTRACT.md: нужны машинные строки МАКЕТ и UI-KIT"
        макет_нужен = решение_макета.group(1).lower() == "mockup.html"
        if макет_нужен:
            макет = папка / "MOCKUP.html"
            if not макет.exists():
                return False, "нет обязательного визуального макета MOCKUP.html"
            макет_текст = макет.read_text(encoding="utf-8", errors="replace")
            if "<html" not in макет_текст.lower() or "UI-KIT:" not in макет_текст:
                return False, "MOCKUP.html должен быть открываемым HTML и содержать маркер UI-KIT:"
    return True, ""


# Роли, чей вердикт управляет маршрутом. Каждая обязана поставить машинную строку.
РОЛИ_С_ВЕРДИКТОМ = (
    "requirement-critic", "product", "reviewer", "ui-critic", "ux-judge", "blocker-skeptic",
)

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
    if роль not in РОЛИ_С_ВЕРДИКТОМ:
        return False
    исход, _ = вердикт(папка, роль)
    return исход == "находки"


def браузерный_блокер(папка: Path, роль: str) -> bool:
    """Не отправлять код на переделку, если судья не видел экран вообще."""
    if роль != "ux-judge":
        return False
    файл = папка / "JUDGE.md"
    if not файл.exists():
        return False
    текст = файл.read_text(encoding="utf-8", errors="replace").lower()
    заблокировано = "screen_verdict: blocked" in текст or "итог: blocked" in текст
    нет_среды = any(причина in текст for причина in (
        "стенд не поднялся", "no browser is available", "браузер недоступен",
    ))
    return заблокировано and нет_среды


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
ЗАМКИ_СТЕНДА: dict[int, threading.Lock] = {}  # один живой browser-судья на порты полосы
СЛОТЫ_АГЕНТОВ: threading.BoundedSemaphore | None = None
_АКТИВНАЯ_ВОЛНА: Path | None = None
СОБЫТИЯ_РУБЕЖЕЙ: dict[str, threading.Event] = {}
ВЛАДЕЛЬЦЫ_РУБЕЖЕЙ: dict[str, str] = {}
РУБЕЖИ_АТОМОВ: dict[tuple[str, int], list[str]] = {}
ЗАВИСИМОСТИ_АТОМОВ: dict[tuple[str, int], list[str]] = {}
ПРОВАЛЕННЫЕ_КАРТОЧКИ: set[str] = set()
ЗАМОК_ЗАВИСИМОСТЕЙ = threading.Lock()


def санитарный_снимок(корень: Path = КОРЕНЬ) -> Path | None:
    """Только существующий sanitized snapshot из главного checkout, без fallback."""
    снимок = (корень / ".stand" / "sanitized-latest.dump").resolve()
    return снимок if снимок.name == "sanitized-latest.dump" and снимок.is_file() else None


def _сигинтум(_сигнал: int, _кадр: object) -> None:
    if _АКТИВНАЯ_ВОЛНА is not None:
        журнал(_АКТИВНАЯ_ВОЛНА, "получен SIGINT; результаты сохранены, продолжение возможно через resume")
    raise KeyboardInterrupt


def поднять_стенд(полоса: int, рабочая: РабочаяКарточка | None = None,
                   force: bool = False) -> str:
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
    if ключ in СТЕНД and not force:
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
                           capture_output=True, text=True, timeout=25 * 60)
    if build.returncode != 0:
        return ""
    recreate = subprocess.run(compose + ["rm", "-sf"], cwd=корень, env=env,
                               capture_output=True, text=True, timeout=5 * 60)
    if recreate.returncode != 0:
        return ""
    р = subprocess.run([str(корень / "scripts/stand/up.sh"), str(полоса)],
                       cwd=корень, env=env, capture_output=True, text=True, timeout=25 * 60)
    хвост = (р.stdout or "") + (р.stderr or "")
    СТЕНД[ключ] = хвост[-600:] if р.returncode == 0 else ""
    return СТЕНД[ключ]


def промпт(роль: str, ид: str, папка: Path, волна: Path, корень: Path = КОРЕНЬ,
           рабочая: РабочаяКарточка | None = None) -> str:
    имя, нужны = АРТЕФАКТ.get(роль, (None, []))
    хвост = (f"Результат запиши в `{папка / имя}`, "
             f"обязательные секции: {', '.join(нужны)}." if имя else
             "Артефакта не оставляешь, результат проверяется гейтами.")
    перекрёстно = (f"\nПерекрёстное решение доменов — `{волна / 'ARCH-CROSS.md'}`; "
                   "если файл есть, его порядок и границы обязательны."
                   if (волна / "ARCH-CROSS.md").exists() else "")
    return (
        f"Карточка `{ид}`. Твоя рабочая копия — `{корень}`.\n"
        f"ВСЕ пути пиши абсолютные, от `{корень}`. Не уходи в другой каталог проекта, "
        f"даже если в CLAUDE.md указан иной путь: это отдельная рабочая копия.\n"
        f"Твоя папка — `{папка}`, там лежат артефакты предыдущих ролей, прочитай их.\n"
        f"Карта задевания волны — `{волна / 'MAP.md'}`.\n"
        f"Действуй строго по своей роли. {хвост}"
        + "\n\nРАЗРЕШЕНИЕ ВЛАДЕЛЬЦА НА ЭТУ ВОЛНУ. Блокеров он не принимает. Находки про "
          "данные, утечки, секреты в коде, персональные данные и подобное — записывай "
          "строкой в свой артефакт и РАБОТАЙ ДАЛЬШЕ. Останавливать из-за них задачу "
          "запрещено: владелец разрешил любые действия и хочет утром готовые фичи на "
          "стенде, а не список причин, почему их нет.\n"
          "Два исключения, и они не про разрешение, а про сохранность его бизнеса: "
          "боевой прод 194.87.96.144 не трогать, и запись в живой кабинет Wildberries "
          "режет сторож — если упёрся в это, так и запиши и иди дальше."
        + перекрёстно
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
        файлы = дифф_реализации(рабочая.корень, getattr(рабочая, "base_sha", ""))
    except Exception:                                        # noqa: BLE001
        return ""
    if not файлы:
        return "\n\nПравок продукта в карточке нет — только стадийные артефакты."
    список = "\n".join(f"  {ф}" for ф in файлы)
    return ("\n\nПравка продукта в этой карточке — ровно эти файлы:\n" + список +
            "\nОстальное в дереве — стадийные артефакты ролей (кейсы, разборы, доказательства). "
            "К границам экрана они отношения не имеют и находкой быть не могут.")


def стенд_для(роль: str, ид: str, рабочая: РабочаяКарточка | None = None) -> str:
    if роль not in РОЛИ_С_ПОЛНЫМ_КОНФИГОМ:
        return ""
    try:
        # Между clicker и судьёй соседняя карточка могла пересобрать общие порты.
        # Поэтому судья всегда заново поднимает свой SHA под замком полосы.
        креды = поднять_стенд(ПОЛОСА.get(ид, 1), рабочая, force=роль == "ux-judge")
    except TypeError:
        # Совместимость с тестовым адаптером старого контракта.
        креды = поднять_стенд(ПОЛОСА.get(ид, 1))
    if not креды:
        return ("\n\nСТЕНД НЕ ПОДНЯЛСЯ. Не ищи его сам и не подбирай порты — "
                "запиши это как причину и остановись.")
    return ("\n\nСтенд уже поднят, вот он:\n" + креды +
            "\nНичего не поднимай и не ищи. Прод (194.87.96.144) запрещён.")


# Первичную атомарную разработку делает Luna. Переделка по уже сформулированным
# находкам идёт Terra. Если он не закрыл вердикт, Sol получает не больше двух
# конечных ремонтов только по файлам актуальных находок. После каждого ревью повторяется.
МОДЕЛЬ_ПЕРЕДЕЛКИ: dict[str, tuple[str, str]] = {
    "backend-dev": ("sonnet", "terra"),
    "screen-dev": ("sonnet", "terra"),
    "ux-architect": ("sonnet", "terra"),
}
МОДЕЛЬ_ЭСКАЛАЦИИ = ("opus", "sol")


def шаг(*args, круг: int = 0, **kwargs):
    """Обёртка: на переделке поднимает модель разработчика."""
    if круг > КРУГОВ and args[1] in МОДЕЛЬ_ПЕРЕДЕЛКИ:
        kwargs["модель"], kwargs["профиль"] = МОДЕЛЬ_ЭСКАЛАЦИИ
    elif круг > 0 and args[1] in МОДЕЛЬ_ПЕРЕДЕЛКИ:
        kwargs["модель"], kwargs["профиль"] = МОДЕЛЬ_ПЕРЕДЕЛКИ[args[1]]
    return _шаг(*args, **kwargs)


def фичи(папка: Path) -> list[str]:
    """Полные атомарные куски из FEATURES.md в заданном splitter порядке."""
    ф = папка / "FEATURES.md"
    if not ф.exists():
        return []
    текст = ф.read_text(encoding="utf-8", errors="replace")
    начала = list(re.finditer(r"^###\s+(\d+)[.)]\s+(.{5,120})$", текст, re.M))
    результат = []
    for номер, начало in enumerate(начала):
        конец = начала[номер + 1].start() if номер + 1 < len(начала) else len(текст)
        блок = текст[начало.start():конец].strip()
        # Не затягиваем в последнюю фичу служебные секции splitter-а.
        блок = re.split(r"^##\s+(?:Порядок|Что осталось за бортом)\s*$", блок,
                        maxsplit=1, flags=re.M)[0].strip()
        if блок:
            результат.append(блок)
    return результат


def фичи_для_переделки(куски: list[str], вердикт: Path | None) -> list[tuple[int, str]]:
    """Возвращает только атомы, чьи продуктовые файлы прямо названы в находках."""
    все = list(enumerate(куски, 1))
    if вердикт is None or not вердикт.exists():
        return все
    текст = вердикт.read_text(encoding="utf-8", errors="replace")
    секция = re.search(r"^##\s+Находки\s*$\n(.*?)(?=^##\s|\Z)", текст, re.M | re.S)
    находки = секция.group(1) if секция else текст
    ссылки = set(re.findall(r"(?:backend|frontend)/[A-Za-z0-9_./-]+", находки))
    выбранные = [
        (номер, кусок) for номер, кусок in все
        if any(ссылка in кусок or Path(ссылка).name in кусок for ссылка in ссылки)
    ]
    if выбранные:
        return выбранные
    # Единственная известная безопасная причина нулевого пересечения — ревьюер ошибочно
    # включил унаследованную инфраструктуру runner-а в продуктовый diff. В этом случае код
    # не переделываем, а повторяем ревью с исправленной границей.
    только_процесс = bool(re.search(
        r"(?:\.claude/agents/|scripts/night\.py|scripts/ci/check_night_runner\.py|/AGENTS\.md)",
        находки,
    )) and not ссылки
    return [] if только_процесс else все


def подготовить_зависимости(
        волна: Path, рабочие: dict[str, "РабочаяКарточка"]) -> list[str]:
    """Загрузить маленький DAG межкарточных рубежей из ARCH-CROSS.

    Ждёт только конкретный атом, которому нужен результат соседа; слот
    модели при этом не занимается. Файл пуст для волн без пересечений.
    """
    global СОБЫТИЯ_РУБЕЖЕЙ, ВЛАДЕЛЬЦЫ_РУБЕЖЕЙ, РУБЕЖИ_АТОМОВ
    global ЗАВИСИМОСТИ_АТОМОВ, ПРОВАЛЕННЫЕ_КАРТОЧКИ
    СОБЫТИЯ_РУБЕЖЕЙ = {}
    ВЛАДЕЛЬЦЫ_РУБЕЖЕЙ = {}
    РУБЕЖИ_АТОМОВ = {}
    ЗАВИСИМОСТИ_АТОМОВ = {}
    ПРОВАЛЕННЫЕ_КАРТОЧКИ = set()
    файл = волна / "DEPENDENCIES.json"
    if not файл.exists():
        return []
    try:
        данные = json.loads(файл.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as е:
        return [f"DEPENDENCIES.json: {е}"]
    рубежи = данные.get("milestones", {})
    зависимости = данные.get("requires", {})
    if not isinstance(рубежи, dict) or not isinstance(зависимости, dict):
        return ["DEPENDENCIES.json: milestones/requires должны быть объектами"]
    ошибки: list[str] = []
    ремонтные = {ид for ид, рабочая in рабочие.items()
                 if круг_из_парковки(рабочая.папка) > 0}
    # DEPENDENCIES.json описывает номера исходной нарезки. После полного первичного dev
    # reviewer может потребовать локальную перенарезку ремонта с новой нумерацией. Старые
    # рубежи к этому моменту уже достигнуты, а применять их к repair-атомам нельзя.
    активные_требования = {цель: нужны for цель, нужны in зависимости.items()
                              if цель.split("#", 1)[0] in рабочие
                              and цель.split("#", 1)[0] not in ремонтные}
    нужные_рубежи = {str(имя) for список in активные_требования.values()
                       if isinstance(список, list) for имя in список}
    источники = dict(рабочие)
    зарегистрированные = _worktree_пути()
    for имя in нужные_рубежи:
        описание = рубежи.get(имя, {})
        ид = описание.get("card") if isinstance(описание, dict) else None
        if ид in источники:
            continue
        совпадения = [(ветка, путь) for ветка, путь in зарегистрированные.items()
                      if ветка.startswith(f"night/{волна.name}/lane-") and ветка.endswith(f"/{ид}")]
        if len(совпадения) == 1:
            ветка, путь = совпадения[0]
            lane = int(re.search(r"/lane-(\d+)/", ветка).group(1))
            рабочая_волна = путь / "night" / волна.name
            источники[ид] = РабочаяКарточка(
                ид, lane, путь, рабочая_волна, рабочая_волна / "cards" / ид, ветка)
    for имя in нужные_рубежи:
        описание = рубежи.get(имя)
        if not isinstance(описание, dict):
            ошибки.append(f"рубеж {имя}: нет card/feature")
            continue
        ид, номер = описание.get("card"), описание.get("feature")
        if ид not in источники or not isinstance(номер, int) or номер < 1:
            ошибки.append(f"рубеж {имя}: неверные card/feature")
            continue
        if ид in ремонтные:
            событие = threading.Event()
            событие.set()
            СОБЫТИЯ_РУБЕЖЕЙ[имя] = событие
            ВЛАДЕЛЬЦЫ_РУБЕЖЕЙ[имя] = ид
            continue
        if номер > len(фичи(источники[ид].папка)):
            ошибки.append(f"рубеж {имя}: нет фичи {номер} у {ид}")
            continue
        событие = threading.Event()
        отчёт = источники[ид].папка / f"DEV-{номер:02d}.md"
        try:
            относительный = отчёт.relative_to(источники[ид].корень)
            сохранён = _git("ls-files", "--error-unmatch", "--", str(относительный),
                            cwd=источники[ид].корень).returncode == 0
        except ValueError:
            сохранён = False
        if сохранён:
            событие.set()
        СОБЫТИЯ_РУБЕЖЕЙ[имя] = событие
        ВЛАДЕЛЬЦЫ_РУБЕЖЕЙ[имя] = ид
        РУБЕЖИ_АТОМОВ.setdefault((ид, номер), []).append(имя)
    for цель, нужны in активные_требования.items():
        совпало = re.fullmatch(r"([^#]+)#(\d+)", цель)
        if not совпало or совпало.group(1) not in рабочие or not isinstance(нужны, list):
            ошибки.append(f"зависимость {цель}: неверный формат")
            continue
        ключ = (совпало.group(1), int(совпало.group(2)))
        if ключ[1] > len(фичи(рабочие[ключ[0]].папка)):
            ошибки.append(f"зависимость {цель}: нет такой фичи")
            continue
        неизвестные = [имя for имя in нужны if имя not in СОБЫТИЯ_РУБЕЖЕЙ]
        if неизвестные:
            ошибки.append(f"зависимость {цель}: нет рубежей {', '.join(неизвестные)}")
            continue
        ЗАВИСИМОСТИ_АТОМОВ[ключ] = list(нужны)
    return ошибки


def дождаться_рубежей(ид: str, номер: int, волна: Path) -> tuple[bool, str]:
    нужны = ЗАВИСИМОСТИ_АТОМОВ.get((ид, номер), [])
    ждали = False
    while True:
        не_готовы = [имя for имя in нужны if not СОБЫТИЯ_РУБЕЖЕЙ[имя].is_set()]
        if not не_готовы:
            return True, ""
        провал = [имя for имя in не_готовы
                  if ВЛАДЕЛЬЦЫ_РУБЕЖЕЙ[имя] in ПРОВАЛЕННЫЕ_КАРТОЧКИ]
        if провал:
            return False, "не доехали внешние рубежи: " + ", ".join(провал)
        if not ждали:
            журнал(волна, f"  {ид} · dev: фича {номер} ждёт {', '.join(не_готовы)}; слот свободен")
            ждали = True
        СОБЫТИЯ_РУБЕЖЕЙ[не_готовы[0]].wait(timeout=1)


def отметить_рубежи(ид: str, номер: int) -> None:
    for имя in РУБЕЖИ_АТОМОВ.get((ид, номер), []):
        СОБЫТИЯ_РУБЕЖЕЙ[имя].set()


def dev_для_фичи(фича: str) -> str:
    """Один кусок принадлежит одному слою; смешанный кусок splitter обязан дорезать."""
    фронт = bool(re.search(r"(?:^|[ `/])frontend/", фича, re.I))
    бэк = bool(re.search(r"(?:^|[ `/])backend/", фича, re.I))
    if фронт == бэк:
        return ""
    return "screen-dev" if фронт else "backend-dev"


def сохранить_checkpoint(рабочая: РабочаяКарточка, сообщение: str) -> tuple[bool, str]:
    """Механически сохраняет успешный атомарный шаг; продуктовых решений не принимает."""
    статус = _git("status", "--porcelain", cwd=рабочая.корень)
    if статус.returncode != 0:
        return False, статус.stderr.strip() or "git status не сработал"
    пути = [строка[3:].strip() for строка in статус.stdout.splitlines() if строка[3:].strip()]
    опасные = [п for п in пути if re.search(
        r"(?:^|/)(?:\.env(?:\.|$)|[^/]*(?:secret|credential|token)[^/]*)|\.(?:pem|key)$", п, re.I)]
    if опасные:
        return False, "отказ сохранять возможные секреты: " + ", ".join(опасные[:5])
    if not пути:
        return True, "изменений для checkpoint нет"
    добавить = _git("add", "-A", cwd=рабочая.корень)
    if добавить.returncode != 0:
        return False, добавить.stderr.strip() or "git add не сработал"
    коммит = _git("commit", "-m", сообщение, cwd=рабочая.корень)
    if коммит.returncode != 0:
        return False, коммит.stderr.strip() or коммит.stdout.strip() or "git commit не сработал"
    return True, _git("rev-parse", "HEAD", cwd=рабочая.корень).stdout.strip()


def разработать_по_фичам(ид: str, папка: Path, волна: Path,
                         рабочая: РабочаяКарточка, круг: int) -> tuple[bool, str]:
    """Запускает Luna отдельно на каждый кусок, затем собирает DEV.md для ревью."""
    куски = фичи(папка)
    if not куски:
        return False, "splitter не оставил ни одной читаемой фичи в FEATURES.md"
    сохранённые = list(папка.glob("DEV-[0-9][0-9].md"))
    if артефакт_готов(папка, "backend-dev")[0] and len(сохранённые) == len(куски):
        журнал(волна, f"  {ид} · dev: уже сделано по {len(куски)} атомарным фичам")
        return True, ""
    источник_находок = next((папка / имя for имя in (
        "REVIEW.md", "DESIGN-REVIEW.md", "JUDGE.md")
        if (папка / имя).exists() and есть_находки(
            папка, {"REVIEW.md": "reviewer", "DESIGN-REVIEW.md": "ui-critic",
                    "JUDGE.md": "ux-judge"}[имя])), None) if круг > 0 else None
    выбранные = фичи_для_переделки(куски, источник_находок)
    if источник_находок and not выбранные:
        отчёты = []
        for номер in range(1, len(куски) + 1):
            сохранённый = папка / f"DEV-{номер:02d}.md"
            if сохранённый.exists():
                отчёты.append(
                    f"# Фича {номер}\n\n{сохранённый.read_text(encoding='utf-8', errors='replace').strip()}\n")
        if отчёты:
            (папка / "DEV.md").write_text("\n".join(отчёты), encoding="utf-8")
            журнал(волна, f"  {ид} · dev: продуктовых файлов из вердикта нет; повторяем ревью")
            return True, ""
        return False, "вердикт не называет продуктовый атом, а сохранённых DEV-отчётов нет"
    for номер, кусок in выбранные:
        можно, причина = дождаться_рубежей(ид, номер, волна)
        if not можно:
            return False, причина
        роль = dev_для_фичи(кусок)
        if not роль:
            return False, (f"фича {номер} смешивает frontend/backend или не называет слой; "
                           "splitter должен дорезать её")
        (папка / "DEV.md").unlink(missing_ok=True)
        дополнение = ("\n\nСЕЙЧАС РЕАЛИЗУЙ ТОЛЬКО ОДИН АТОМАРНЫЙ КУСОК ИЗ FEATURES.md. "
                      "Не переходи к следующим:\n\n" + кусок)
        дополнение += (
            "\n\nАТОМАРНАЯ ПРОВЕРКА: запускай только тестовые файлы и кейсы этого атома "
            "и относящиеся к нему регрессии из вердикта. На этом шаге запрещены полный "
            "backend pytest (`pytest`/`pytest -q` без путей), `ruff check .` и `mypy .`. "
            "Полный регресс запускается один раз после интеграции всех карточек, не внутри "
            "каждого атома. В DEV.md запиши точные выполненные команды."
        )
        if источник_находок:
            дополнение += (
                f"\n\nЭТО ПЕРЕДЕЛКА ПО НАХОДКАМ. Сначала прочитай `{источник_находок}`. "
                "Исходный атом выше — контекст, а не доказательство готовности. Исправь все "
                "находки из вердикта, относящиеся к файлам и слою этого атома, и проверь "
                "названные сценарии. Разрешено добавить прямо названные ревьюером файлы того "
                "же слоя, тесты и docs/blockers; соседние продуктовые задачи не трогай.")
        ок, беда = шаг(ид, роль, папка, волна, рабочая.корень, рабочая,
                       круг=круг, дополнение=дополнение)
        if not ок:
            return False, f"фича {номер}: {беда}"
        отчёт = (папка / "DEV.md").read_text(encoding="utf-8", errors="replace")
        (папка / f"DEV-{номер:02d}.md").write_text(отчёт, encoding="utf-8")
        сохранено, сведения = сохранить_checkpoint(
            рабочая, f"night({ид}): atom {номер}/{len(куски)}")
        if not сохранено:
            return False, f"фича {номер} не сохранена: {сведения}"
        отметить_рубежи(ид, номер)
        журнал(волна, f"  {ид} · dev: фича {номер}/{len(куски)} сохранена {сведения[:12]}")
    отчёты = []
    for номер in range(1, len(куски) + 1):
        сохранённый = папка / f"DEV-{номер:02d}.md"
        if сохранённый.exists():
            отчёты.append(
                f"# Фича {номер}\n\n{сохранённый.read_text(encoding='utf-8', errors='replace').strip()}\n")
    (папка / "DEV.md").write_text("\n".join(отчёты), encoding="utf-8")
    сохранено, сведения = сохранить_checkpoint(рабочая, f"night({ид}): dev reports")
    return (True, "") if сохранено else (False, сведения)


def _шаг(ид: str, роль: str, папка: Path, волна: Path,
        корень: Path = КОРЕНЬ,
        рабочая: РабочаяКарточка | None = None, модель: str | None = None,
        профиль: str | None = None,
        дополнение: str = "") -> tuple[bool, str]:
    # Судью перезапускаем только если он в прошлый раз нашёл находки: тогда его вердикт
    # относится к старому коду. Чистый вердикт при возобновлении переигрывать незачем —
    # это лишний дорогой вызов на ровном месте.
    if артефакт_готов(папка, роль)[0] and (
            роль not in РОЛИ_С_ВЕРДИКТОМ or not есть_находки(папка, роль)):
        журнал(волна, f"  {ид} · {роль}: уже сделано, пропускаю")
        return True, ""
    контекст = (ЗАМКИ_СТЕНДА.setdefault(рабочая.lane, threading.Lock())
               if рабочая and роль in РОЛИ_С_ПОЛНЫМ_КОНФИГОМ else contextlib.nullcontext())
    with контекст:
        причина_повтора = ""
        for попытка in range(ПОВТОРОВ + 1):
            доп = {}
            if модель:
                доп["модель"] = модель
            if профиль:
                доп["профиль"] = профиль
            обратная_связь = (
                "\n\nПРЕДЫДУЩАЯ ПОПЫТКА ОТКЛОНЕНА МАШИННЫМ ГЕЙТОМ: "
                f"{причина_повтора}. Исправь существующий артефакт именно по этой ошибке; "
                "не начинай задачу заново и не расширяй scope."
                if причина_повтора else ""
            )
            слот = СЛОТЫ_АГЕНТОВ or contextlib.nullcontext()
            with слот:
                код, хвост = запустить(
                    роль,
                    промпт(роль, ид, папка, волна, корень, рабочая) + дополнение + обратная_связь,
                                       cwd=корень, **доп)
            готов, беда = артефакт_готов(папка, роль)
            if готов:
                журнал(волна, f"  {ид} · {роль}: готово")
                return True, ""
            журнал(волна, f"  {ид} · {роль}: {беда} (код {код}, попытка {попытка + 1})")
            причина_повтора = беда
    return False, f"{роль}: {беда}\n{хвост.strip()[-600:]}"


def сверить_архитектуру(волна: Path,
                        рабочие: dict[str, РабочаяКарточка]) -> bool:
    """Барьер после арх-решений: свести их между собой, пока не написан ни один контракт.

    Первый архитектор пишет решение по каждой карточке в своей параллельной полосе и не видит
    готовых решений соседей — их в тот момент ещё нет. Карта задевания предупреждает, что
    карточки связаны, но что именно каждая выберет, знать заранее нельзя. Поэтому нужен второй
    проход, который читает все решения разом и переписывает то, что не сходится: два разумных
    по отдельности решения дают несовместимую пару, и обнаруживается это в коде через восемь
    часов работы.
    """
    файл = волна / "ARCH-CROSS.md"
    порядок = волна / "DEPENDENCIES.json"
    if файл.exists():
        текст_сверки = файл.read_text(encoding="utf-8", errors="replace")
        if not all(секция in текст_сверки for секция in (
                "## Столкновения", "## Что переписал", "## Порядок")):
            return False
        for рабочая in рабочие.values():
            рабочая.волна.mkdir(parents=True, exist_ok=True)
            shutil.copy2(файл, рабочая.волна / файл.name)
            if порядок.exists():
                shutil.copy2(порядок, рабочая.волна / порядок.name)
        return True
    решения = [р.папка / "ARCH.md" for р in рабочие.values()
               if (р.папка / "ARCH.md").exists()]
    if len(решения) < 2:
        return True                  # сводить нечего
    журнал(волна, f"\n### перекрёстная сверка архитектуры ({len(решения)} решений)")
    код, хвост = запустить("arch-critic", (
        f"Твоя рабочая копия — `{КОРЕНЬ}`, все пути абсолютные.\n"
        f"Арх-решения волны: " + ", ".join(f"`{путь}`" for путь in решения) +
        f"\nКарта задевания — `{волна / 'MAP.md'}`.\n"
        f"Прочитай все решения разом, найди где они друг друга ломают и запиши единый итог "
        f"в `{файл}`. Секции: Столкновения, Что переписал, Порядок, "
        f"Что осталось за бортом. Первой строкой — ВЕРДИКТ: ЧИСТО или ВЕРДИКТ: НАХОДКИ N.\n"
        f"Если есть межкарточные зависимости атомов, запиши `{порядок}`: JSON с "
        "объектами milestones (`имя`: {`card`, `feature`}) и requires "
        "(`card#feature`: [`имя`]). Только зависимости между карточками; внутренний "
        "порядок уже задан FEATURES.md. Если пересечений нет, запиши оба пустых объекта."))
    готово = файл.exists()
    if готово:
        текст_сверки = файл.read_text(encoding="utf-8", errors="replace")
        готово = all(секция in текст_сверки for секция in (
            "## Столкновения", "## Что переписал", "## Порядок"))
    if готово:
        for рабочая in рабочие.values():
            рабочая.волна.mkdir(parents=True, exist_ok=True)
            shutil.copy2(файл, рабочая.волна / файл.name)
            if порядок.exists():
                shutil.copy2(порядок, рабочая.волна / порядок.name)
    журнал(волна, "перекрёстная сверка: " + ("готова" if готово
                                             else f"НЕ СОЗДАНА (код {код}) {хвост.strip()[-200:]}"))
    return готово


def снять_устаревшую_парковку(папка: Path) -> bool:
    """Парковка старше собственных артефактов карточки — след прошлой беды, а не запрет.

    Кончился лимит, упала сборка, оборвалась сеть — карточка легла. Потом прогон
    продолжили, и она поехала дальше, а файл парковки остался лежать. При следующем
    возобновлении он делает вид, что карточка стоит, хотя она давно ушла вперёд.
    """
    о = папка / "OTLOZHENO.md"
    if not о.exists():
        return False
    свежий = max((ф.stat().st_mtime for ф in папка.glob("*.md") if ф.name != "OTLOZHENO.md"),
                 default=0)
    if свежий > о.stat().st_mtime:
        о.unlink(missing_ok=True)
        return True
    return False


def файл_эскалации(папка: Path) -> Path:
    """Маркер живёт в Git metadata: не попадает в diff карточки."""
    точка_git = КОРЕНЬ / ".git"
    if not точка_git.exists():
        основа = КОРЕНЬ / ".night-state"
    elif точка_git.is_dir():
        основа = точка_git
    else:
        ссылка = точка_git.read_text(encoding="utf-8").removeprefix("gitdir:").strip()
        gitdir = Path(ссылка)
        if not gitdir.is_absolute():
            gitdir = (КОРЕНЬ / gitdir).resolve()
        commondir = gitdir / "commondir"
        основа = ((gitdir / commondir.read_text(encoding="utf-8").strip()).resolve()
                  if commondir.exists() else gitdir)
    return основа / "night-escalation" / папка.parent.parent.name / папка.name


def круг_из_парковки(папка: Path) -> int:
    """Возвращает сохранённый уровень rework после перезапуска ночи."""
    маркер = файл_эскалации(папка)
    if маркер.exists():
        статус = маркер.read_text(encoding="utf-8", errors="replace")
        записанный = re.search(r"^КРУГ:\s*(\d+)\s*$", статус, re.M)
        круг = int(записанный.group(1)) if записанный else None
        if "СТАТУС: DONE" in статус:
            # Старый DONE без номера означает, что один Sol-ремонт уже был. После
            # добавления последнего точечного ремонта такая парковка получает ровно его.
            return (круг + 1) if круг is not None else КРУГОВ + 2
        if "СТАТУС: ACTIVE" in статус:
            return круг if круг is not None else КРУГОВ + 1
    о = папка / "OTLOZHENO.md"
    if not о.exists():
        return 0
    текст = о.read_text(encoding="utf-8", errors="replace")
    if "финальной эскалации" in текст:
        # Парковка старого runner-а означает один уже использованный Sol-ремонт.
        return КРУГОВ + 2
    if re.search(r"после\s+\d+\s+кругов правки", текст):
        # Это парковки старого маршрута: оба круга выполняла Luna. На resume они
        # сначала получают один нормальный поатомный rework Terra, а не сразу Sol.
        return КРУГОВ
    return 0


def активировать_эскалацию(папка: Path, круг: int | None = None) -> Path:
    маркер = файл_эскалации(папка)
    маркер.parent.mkdir(parents=True, exist_ok=True)
    номер = круг if круг is not None else КРУГОВ + 1
    переплан = ""
    if маркер.exists() and "ПЕРЕПЛАН: DONE" in маркер.read_text(
            encoding="utf-8", errors="replace"):
        переплан = "ПЕРЕПЛАН: DONE\n"
    маркер.write_text(
        f"СТАТУС: ACTIVE\nКРУГ: {номер}\n{переплан}", encoding="utf-8")
    return маркер


def переплан_уже_был(папка: Path) -> bool:
    маркер = файл_эскалации(папка)
    return маркер.exists() and "ПЕРЕПЛАН: DONE" in маркер.read_text(
        encoding="utf-8", errors="replace")


def отрицательный_вердикт(папка: Path) -> tuple[str, Path] | None:
    кандидаты = []
    for роль in ВОЗВРАЩАЮТ_К_DEV:
        имя, _ = АРТЕФАКТ[роль]
        файл = папка / имя
        if файл.exists() and есть_находки(папка, роль):
            кандидаты.append((файл.stat().st_mtime, роль, файл))
    if not кандидаты:
        return None
    _, роль, файл = max(кандидаты)
    return роль, файл


def перепланировать_ремонт(ид: str, папка: Path, волна: Path,
                          рабочая: РабочаяКарточка) -> tuple[bool, str]:
    """Один раз дорезает неудачный ремонт вместо вечной парковки или нового слепого круга."""
    источник = отрицательный_вердикт(папка)
    if источник is None:
        return False, "нет отрицательного вердикта для перепланирования"
    роль, файл = источник
    был_контракт = (папка / "CONTRACT.md").exists()
    аннулировать_после_вердикта(папка, роль)
    if роль in ("ui-critic", "ux-judge") and был_контракт:
        ок, беда = шаг(
            ид, "ux-architect", папка, волна, рабочая.корень, рабочая,
            круг=КРУГОВ + 1,
            дополнение=(
                f"\n\nЭто восстановление после исчерпанного ремонта. Прочитай `{файл}`. "
                "Не перепроектируй карточку целиком: уточни CONTRACT.md и MOCKUP.html "
                "только в местах названных находок, сохрани решения product и ARCH-CROSS."),
        )
        if not ок:
            return False, беда
    (папка / "FEATURES.md").unlink(missing_ok=True)
    ок, беда = шаг(
        ид, "splitter", папка, волна, рабочая.корень, рабочая,
        дополнение=(
            f"\n\nЭто перепланирование неудачного ремонта. Прочитай `{файл}` и создай "
            "FEATURES.md только из ещё не закрытых находок: одна находка или один тесно "
            "связанный слой на атом, один-три продуктовых файла, отдельная проверка. "
            "Не возвращай уже принятую карточку к полной разработке и не расширяй scope."),
    )
    if not ок:
        return False, беда
    for отчёт in папка.glob("DEV-[0-9][0-9].md"):
        отчёт.unlink(missing_ok=True)
    (папка / "DEV.md").unlink(missing_ok=True)
    маркер = файл_эскалации(папка)
    маркер.parent.mkdir(parents=True, exist_ok=True)
    маркер.write_text(
        f"СТАТУС: ACTIVE\nКРУГ: {КРУГОВ}\nПЕРЕПЛАН: DONE\n", encoding="utf-8")
    return True, ""


def аннулировать_после_вердикта(папка: Path, роль: str) -> None:
    """После правки старые проверки следующего слоя больше не являются доказательством."""
    удалить = {"DEV.md", "CLICKS.md"}
    if роль == "reviewer":
        удалить.update(("DESIGN-REVIEW.md", "JUDGE.md"))
    elif роль == "ui-critic":
        удалить.update(("REVIEW.md", "CASES.md", "CONTRACT.md", "MOCKUP.html",
                        "FEATURES.md", "JUDGE.md"))
    elif роль == "ux-judge":
        удалить.update(("REVIEW.md", "DESIGN-REVIEW.md"))
    for имя in удалить:
        (папка / имя).unlink(missing_ok=True)


def провести(ид: str, волна: Path, рабочая: РабочаяКарточка | None = None) -> str:
    if рабочая is None:
        рабочая = РабочаяКарточка(ид, 0, КОРЕНЬ, волна, волна / "cards" / ид, "")
    папка = рабочая.папка
    снять_устаревшую_парковку(папка)
    волна = рабочая.волна
    папка.mkdir(parents=True, exist_ok=True)
    тип = тип_карточки(папка)
    if not тип and (папка / "TYPE.txt").exists():
        тип = (папка / "TYPE.txt").read_text(encoding="utf-8").strip().lower()
    if тип not in ЦЕПОЧКИ:
        журнал(волна, f"{ид}: тип «{тип or 'не назван'}» — отложено")
        (папка / "OTLOZHENO.md").write_text(f"Тип не определён: «{тип}»\n", encoding="utf-8")
        return "отложено"

    круг = круг_из_парковки(папка)
    цепочка = ЦЕПОЧКИ[тип]
    if круг > КРУГОВ + ЭСКАЛАЦИОННЫХ_КРУГОВ:
        if переплан_уже_был(папка):
            журнал(волна, f"{ид}: отложено — ремонт не помог и после перенарезки")
            return "отложено"
        журнал(волна, f"  {ид} · repair-plan: сильный ремонт не помог — дорезаем находки")
        ок, беда = перепланировать_ремонт(ид, папка, волна, рабочая)
        if not ок:
            (папка / "OTLOZHENO.md").write_text(
                f"перепланирование ремонта: {беда}\n", encoding="utf-8")
            журнал(волна, f"{ид}: отложено — не удалось перенарезать ремонт")
            return "отложено"
        круг = КРУГОВ
        (папка / "OTLOZHENO.md").unlink(missing_ok=True)
    if круг > 0:
        # Старый DEV доказанно не закрыл вердикт. Оставляем REVIEW как вход
        # для сильного исполнителя и не переигрываем product/UX/tester.
        маркер = файл_эскалации(папка)
        if круг > КРУГОВ and not маркер.exists():
            активировать_эскалацию(папка, круг)
        # Сводный DEV удаляем на любом resume: DEV-N остаются доказательствами уже
        # выполненных атомов, а новый DEV собирается только после нужного ремонта.
        (папка / "DEV.md").unlink(missing_ok=True)
        i = цепочка.index("dev")
        профиль = "Sol" if круг > КРУГОВ else "Terra"
        журнал(волна, f"  {ид} · resume: поатомный rework {профиль} по сохранённым находкам")
    else:
        i = 0
    while i < len(цепочка):
        if цепочка[i] == "dev":
            роль = "dev"
            ок, беда = разработать_по_фичам(ид, папка, волна, рабочая, круг)
        else:
            роль = цепочка[i]
            ок, беда = шаг(ид, роль, папка, волна, рабочая.корень, рабочая, круг=круг)
        if not ок:
            (папка / "OTLOZHENO.md").write_text(беда + "\n", encoding="utf-8")
            журнал(волна, f"{ид}: отложено на шаге {роль}")
            return "отложено"
        if роль == "product" and есть_находки(папка, роль):
            (папка / "OTLOZHENO.md").write_text(
                "product не смог закрыть все решения\n", encoding="utf-8")
            журнал(волна, f"{ид}: отложено — product оставил нерешённые вопросы")
            return "отложено"
        if браузерный_блокер(папка, роль):
            (папка / "OTLOZHENO.md").write_text(
                "ux-judge: браузерная среда недоступна; код на переделку не возвращался\n",
                encoding="utf-8",
            )
            журнал(волна, f"{ид}: отложено — браузерная среда, не дефект кода")
            return "отложено"
        if роль in ВОЗВРАЩАЮТ_К_DEV and есть_находки(папка, роль):
            круг += 1
            if круг > КРУГОВ + ЭСКАЛАЦИОННЫХ_КРУГОВ:
                маркер = файл_эскалации(папка)
                маркер.parent.mkdir(parents=True, exist_ok=True)
                переплан = "ПЕРЕПЛАН: DONE\n" if переплан_уже_был(папка) else ""
                маркер.write_text(
                    f"СТАТУС: DONE\nКРУГ: {круг - 1}\n{переплан}", encoding="utf-8")
                (папка / "OTLOZHENO.md").write_text(
                    f"{роль} нашёл находки после {круг - 1} кругов правки "
                    "и финальной эскалации\n", encoding="utf-8")
                журнал(волна, f"{ид}: отложено — {роль}, эскалация не помогла")
                return "отложено"
            if круг > КРУГОВ:
                активировать_эскалацию(папка, круг)
                журнал(волна, f"  {ид} · {роль}: Terra-rework не закрыл вердикт — эскалация Sol")
            журнал(волна, f"  {ид} · {роль}: находки, круг {круг} — назад к разработке")
            # Вердикт с находками — вход переделки. Раньше мы удаляли его здесь, после чего
            # разработчик снова получал только исходный атом и повторял тот же код по кругу.
            аннулировать_после_вердикта(папка, роль)
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
    файл_эскалации(папка).unlink(missing_ok=True)
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


def выбрать_карточки(все: list[str], фильтр: str | None) -> list[str]:
    if not фильтр:
        return все
    нужны = {имя.strip() for имя in фильтр.split(",") if имя.strip()}
    неизвестные = нужны - set(все)
    if неизвестные:
        raise ValueError("неизвестные карточки: " + ", ".join(sorted(неизвестные)))
    return [имя for имя in все if имя in нужны]


def ночь(волна: Path, полос: int, фильтр: str | None = None) -> int:
    global _АКТИВНАЯ_ВОЛНА, СЛОТЫ_АГЕНТОВ
    _АКТИВНАЯ_ВОЛНА = волна
    агентов = max(МИНИМУМ_АГЕНТОВ, полос)
    СЛОТЫ_АГЕНТОВ = threading.BoundedSemaphore(агентов)
    signal.signal(signal.SIGINT, _сигинтум)
    все_карточки = карточки(волна)
    if not все_карточки:
        print(f"в {волна}/cards нет карточек — сначала вечер", file=sys.stderr)
        return 1
    try:
        ид_список = выбрать_карточки(все_карточки, фильтр)
    except ValueError as е:
        print(str(е), file=sys.stderr)
        return 2
    входные_ошибки = проверить_вход_волны(волна, ид_список)
    if входные_ошибки:
        журнал(волна, "входной гейт красный: " + "; ".join(входные_ошибки))
        return 2
    # Номера полос считаются по полной очереди: точечный resume не меняет worktree.
    for н, и in enumerate(все_карточки):
        ПОЛОСА[и] = н % полос + 1
    try:
        рабочие = рабочие_карточки(волна, ид_список, полос)
    except (OSError, RuntimeError) as е:
        журнал(волна, f"изоляция карточек не создана: {е}")
        return 2
    for и, рабочая in рабочие.items():
        ПОЛОСА[и] = рабочая.lane
    журнал(волна, f"\n## Ночь · карточек {len(ид_список)} · полос {полос}")
    # Барьер: домены сначала доводим до арх-решения, потом сводим решения между собой,
    # и только после этого пускаем всё дальше. Без этого несколько архитекторов принимают
    # несовместимые решения, а этапы при этом зелёные — снаружи не видно ничего.
    домены = [и for и in ид_список if тип_карточки(волна / "cards" / и) == "домен"]
    if домены:
        журнал(волна, f"\n### арх-решения по доменам ({len(домены)})")
        with futures.ThreadPoolExecutor(max_workers=len(домены)) as пул_арх:
            list(пул_арх.map(
                lambda и: шаг(и, "solution-architect", рабочие[и].папка, волна,
                              рабочие[и].корень, рабочие[и]), домены))
        if not сверить_архитектуру(волна, {и: рабочие[и] for и in домены}):
            журнал(волна, "ночь остановлена до product: единая ARCH-CROSS не готова")
            return 2

    ошибки_зависимостей = подготовить_зависимости(волна, рабочие)
    if ошибки_зависимостей:
        журнал(волна, "межкарточный порядок красный: " +
                "; ".join(ошибки_зависимостей))
        return 2

    # Каждая карточка имеет свой лёгкий контроллер. Дорогие вызовы моделей
    # ограничивает общая семафора, а не число карточек в движении.
    with futures.ThreadPoolExecutor(max_workers=len(ид_список)) as пул:
        def безопасно(и: str) -> str:
            try:
                итог = провести(и, волна, рабочие[и])
                if итог != "сделано":
                    with ЗАМОК_ЗАВИСИМОСТЕЙ:
                        ПРОВАЛЕННЫЕ_КАРТОЧКИ.add(и)
                return итог
            except Exception as е:  # карточка не должна остановить соседей
                with ЗАМОК_ЗАВИСИМОСТЕЙ:
                    ПРОВАЛЕННЫЕ_КАРТОЧКИ.add(и)
                папка = рабочие[и].папка
                папка.mkdir(parents=True, exist_ok=True)
                (папка / "OTLOZHENO.md").write_text(f"исключение: {е}\n", encoding="utf-8")
                журнал(волна, f"{и}: отложено — исключение {е}")
                return "отложено"
        итоги = list(пул.map(безопасно, ид_список))
    сделано = итоги.count("сделано")
    журнал(волна, f"\n## Итог: сделано {сделано}, отложено {len(итоги) - сделано}")

    if сделано != len(итоги):
        журнал(волна, "отчёт: product-acceptor не запускается до завершения всех карточек")
        _АКТИВНАЯ_ВОЛНА = None
        return 2

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
    # Артефакты живут в карточной копии, а не в общей папке волны: там работают агенты.
    # Обзор, смотревший только в общую, показывал нули на реально идущей работе и делал
    # слепым и меня, и сторожа.
    гнездо = КОРЕНЬ.parent / ".night-worktrees" / волна.name

    def где(ид: str, общая: Path) -> Path:
        if гнездо.exists():
            for д in гнездо.glob(f"lane-*-{ид}"):
                своя = д / "night" / волна.name / "cards" / ид
                if своя.exists():
                    return своя
        return общая

    for общая in sorted(x for x in корзина.iterdir() if x.is_dir()):
        п = где(общая.name, общая)
        # Берём тот же тип, что и маршрут: иначе обзор врёт про markdown-обёртку вокруг
        # машинной строки, а глазами кажется, что карточка уехала не туда.
        тип = тип_карточки(п) or "?"
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
        print(f"  {общая.name:22} {тип:7} {len(готово)}/{len(цепочка) or '?'}  "
              f"{состояние:18} молчит {молчит:3} мин{причина}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Ночной оркестратор WMS")
    p.add_argument("фаза", choices=["вечер", "ночь", "полный", "проверка", "обзор", "очистить"])
    p.add_argument("путь", nargs="?", help="файл со списком (вечер) или папка волны (ночь)")
    p.add_argument("--полос", type=int, default=6)   # полоса на агента: ждать нечего
    p.add_argument("--карточки", help="точечный resume: id через запятую")
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
        return ночь(волна, a.полос, a.карточки)
    return ночь(путь, a.полос, a.карточки)


if __name__ == "__main__":
    sys.exit(main())
