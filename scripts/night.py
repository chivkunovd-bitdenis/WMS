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
    "reviewer":           ("REVIEW.md",        ["Находки"]),
    "clicker":            ("CLICKS.md",        ["Пройденные кейсы", "Не прошло"]),
    "ux-judge":           ("JUDGE.md",         ["Находки", "Пройденные кейсы"]),
    "guard":              ("GUARD.md",         ["Находки"]),
    "blocker-collector":  ("BLOCKERS.md",     ["Блокировки", "Без обоснования", "Разошлись слои"]),
    "blocker-skeptic":    ("SKEPTIC.md",      ["Находки", "Проверено"]),
    "product-acceptor":   ("OTCHET.md",        ["Сделано", "Не доехало", "Допущения аналитиков", "Вопросы владельцу", "Оформление"]),
}

# Пути по типам задач. Ровно то, чем баг отличается от фичи: у бага нет проектирования.
ЦЕПОЧКИ = {
    "баг":   ["tester", "dev", "reviewer", "clicker", "ux-judge"],
    "фича":  ["ux-architect", "ui-critic", "tester", "breaker", "dev", "reviewer", "clicker", "ux-judge"],
    "домен": ["solution-architect", "ux-architect", "ui-critic", "tester", "breaker",
              "dev", "reviewer", "clicker", "ux-judge"],
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
КОНТРОЛЬНЫЕ_РОЛИ = {"intake", "product-acceptor"}
ИССЛЕДОВАТЕЛИ = {"analyst", "solution-architect"}
# Эти роли используют живой браузер или подключённые плагины; им нужен
# пользовательский конфиг Codex. Остальные роли изолируются от него.
РОЛИ_С_ПОЛНЫМ_КОНФИГОМ = {"clicker", "ux-judge"}
ДОПУСТИМЫЕ_ПРОФИЛИ = {"terra", "luna"}


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
                "допустимы только 'terra' и 'luna'")
    return None


def роль_с_инъекцией(роль: str, промпт: str, профиль: str | None = None) -> str:
    """Явно закрепляет владельца роли при запуске через Codex.

    Luna выполняет содержательную работу. Terra используется только для двух
    оркестрационных ролей, где нет предметного решения. Это не даёт модели
    выбрать иной профиль по тексту карточки.
    """
    исполнитель = профиль.capitalize() if профиль else ("Terra" if роль in КОНТРОЛЬНЫЕ_РОЛИ else "Luna")
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
        профиль_cli = профиль or ("terra" if роль in КОНТРОЛЬНЫЕ_РОЛИ else "luna")
        модель = f"gpt-5.6-{профиль_cli}"
        effort = "medium" if профиль_cli == "terra" else "low"
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


def артефакт_готов(папка: Path, роль: str) -> tuple[bool, str]:
    """Единственная проверка, которую делает оркестратор. Никакого разбора вердиктов."""
    имя, нужны = АРТЕФАКТ.get(роль, (None, []))
    if имя is None:
        return True, ""
    файл = папка / имя
    if not файл.exists():
        return False, f"нет файла {имя}"
    текст = файл.read_text(encoding="utf-8", errors="replace")
    есть = секции(текст)
    нет = [s for s in нужны if not any(s.lower() in e.lower() for e in есть)]
    if нет:
        return False, f"в {имя} нет секций: {', '.join(нет)}"
    return True, ""


def есть_находки(папка: Path, роль: str) -> bool:
    """Непустая секция «Находки». Пустая — это «чисто», отсутствие — уже поймано выше."""
    имя, _ = АРТЕФАКТ.get(роль, (None, []))
    if имя is None or not (папка / имя).exists():
        return False
    текст = (папка / имя).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^#{1,4}\s*Находки\s*$(.*?)(?=^#{1,4}\s|\Z)", текст, re.M | re.S)
    if not m:
        return False
    тело = re.sub(r"^\s*[-*]\s*$", "", m.group(1), flags=re.M).strip()
    return bool(тело) and тело.lower() not in {"нет", "чисто", "пусто", "—", "-"}


def поле(папка: Path, файл: str, секция: str) -> str:
    п = папка / файл
    if not п.exists():
        return ""
    m = re.search(rf"^#{{1,4}}\s*{re.escape(секция)}\s*$(.*?)(?=^#{{1,4}}\s|\Z)",
                  п.read_text(encoding="utf-8", errors="replace"), re.M | re.S)
    return m.group(1).strip() if m else ""


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
        f"Действуй строго по своей роли. {хвост}" + стенд_для(роль, ид, рабочая)
    )


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
    if артефакт_готов(папка, роль)[0] and роль not in СУДЬИ:
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


def провести(ид: str, волна: Path, рабочая: РабочаяКарточка | None = None) -> str:
    if рабочая is None:
        рабочая = РабочаяКарточка(ид, 0, КОРЕНЬ, волна, волна / "cards" / ид, "")
    папка = рабочая.папка
    волна = рабочая.волна
    папка.mkdir(parents=True, exist_ok=True)
    тип = поле(папка, "RAZBOR.md", "Тип").strip().lower()
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
    return беды


def вечер(исходник: Path, fresh: bool = False, run_id: str | None = None) -> int:
    if fresh:
        if not run_id:
            raise ValueError("для --fresh нужен --run-id")
        волна = создать_свежую_волну(исходник, run_id)
    else:
        волна = КОРЕНЬ / "night" / исходник.stem
    (волна / "cards").mkdir(parents=True, exist_ok=True)
    журнал(волна, f"# Волна {волна.name}\n\n## Вечер")

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

    журнал(волна, "\n### карта задевания")
    запустить("solution-architect", (
        f"Твоя рабочая копия — `{КОРЕНЬ}`, все пути абсолютные.\n"
        f"Собери карту задевания волны. Прочитай RAZBOR.md всех карточек в "
        f"`{волна / 'cards'}` целиком, все сразу, и напиши "
        f"`{волна / 'MAP.md'}`: по каждой карточке — задетые экраны, "
        f"файлы и таблицы, столкновения с другими карточками, порядок и полоса, и список "
        f"смежных экранов, чьи кейсы придётся перекликать. Секции: `## Карта`, `## Порядок`."),
        профиль="terra")
    карта_готова = not any(e.startswith("MAP.md:") for e in проверить_вход_волны(волна, ид_список))
    журнал(волна, "карта: " + ("готова" if карта_готова else "НЕ СОЗДАНА"))
    журнал(волна, f"\nВечер закончен. Посмотри вопросы и допущения, потом: "
                  f"python3 scripts/night.py ночь night/{волна.name}")
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


def main() -> int:
    p = argparse.ArgumentParser(description="Ночной оркестратор WMS")
    p.add_argument("фаза", choices=["вечер", "ночь", "полный", "проверка", "очистить"])
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
        if not a.fresh or not a.run_id:
            p.error("для полного прогона обязательны --fresh и --run-id")
        код = вечер(путь, fresh=a.fresh, run_id=a.run_id)
        if код != 0:
            return код
        имя = f"{путь.stem}-{a.run_id}" if a.fresh and a.run_id else путь.stem
        return ночь(КОРЕНЬ / "night" / имя, a.полос)
    return ночь(путь, a.полос)


if __name__ == "__main__":
    sys.exit(main())
