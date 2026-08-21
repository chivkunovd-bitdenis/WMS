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
import json
import os
import re
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
    "product-acceptor":   (None,               []),
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


def _запустить_codex(роль: str, промпт: str, профиль: str | None = None) -> tuple[int, str]:
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
            cwd=КОРЕНЬ, capture_output=True, text=True, timeout=ТАЙМАУТ,
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


def запустить(роль: str, промпт: str, профиль: str | None = None) -> tuple[int, str]:
    """Один вызов агента. Падение подпроцесса — это просто ненулевой код, а не исключение."""
    if ошибка := _профиль_ошибка(профиль):
        return 2, ошибка
    if ИСПОЛНИТЕЛЬ == "codex":
        return _запустить_codex(роль, промпт, профиль)
    try:
        р = subprocess.run(
            ["claude", "-p", промпт, "--agent", роль,
             # Без этого первая же запись файла упирается в запрос разрешения,
             # которого ночью некому дать, и агент честно останавливается.
             "--permission-mode", "acceptEdits"],
            cwd=КОРЕНЬ, capture_output=True, text=True, timeout=ТАЙМАУТ,
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


ПОЛОСА: dict[str, int] = {}          # карточка -> номер полосы стенда
СТЕНД: dict[int, str] = {}           # полоса -> строка с адресом и кредами


def поднять_стенд(полоса: int) -> str:
    """Стенд поднимает скрипт, а не агент.

    Агенту, которому дали искать стенд самому, ничего не стоит найти «похожий» и молча
    проверить не то — а хуже честного отказа только успешный отчёт о проверке чужого экрана.
    Поэтому кликер получает готовые адрес и пароль строкой в промпте.
    """
    if полоса in СТЕНД:
        return СТЕНД[полоса]
    р = subprocess.run([str(КОРЕНЬ / "scripts/stand/up.sh"), str(полоса)],
                       cwd=КОРЕНЬ, capture_output=True, text=True, timeout=15 * 60)
    хвост = (р.stdout or "") + (р.stderr or "")
    СТЕНД[полоса] = хвост[-600:] if р.returncode == 0 else ""
    return СТЕНД[полоса]


def промпт(роль: str, ид: str, папка: Path, волна: Path) -> str:
    имя, нужны = АРТЕФАКТ.get(роль, (None, []))
    хвост = (f"Результат запиши в `{папка / имя}`, "
             f"обязательные секции: {', '.join(нужны)}." if имя else
             "Артефакта не оставляешь, результат проверяется гейтами.")
    return (
        f"Карточка `{ид}`. Твоя рабочая копия — `{КОРЕНЬ}`.\n"
        f"ВСЕ пути пиши абсолютные, от `{КОРЕНЬ}`. Не уходи в другой каталог проекта, "
        f"даже если в CLAUDE.md указан иной путь: это отдельная рабочая копия.\n"
        f"Твоя папка — `{папка}`, там лежат артефакты предыдущих ролей, прочитай их.\n"
        f"Карта задевания волны — `{волна / 'MAP.md'}`.\n"
        f"Действуй строго по своей роли. {хвост}" + стенд_для(роль, ид)
    )


def стенд_для(роль: str, ид: str) -> str:
    if роль != "clicker":
        return ""
    креды = поднять_стенд(ПОЛОСА.get(ид, 1))
    if not креды:
        return ("\n\nСТЕНД НЕ ПОДНЯЛСЯ. Не ищи его сам и не подбирай порты — "
                "запиши это как причину и остановись.")
    return ("\n\nСтенд уже поднят, вот он:\n" + креды +
            "\nНичего не поднимай и не ищи. Прод (194.87.96.144) запрещён.")


def шаг(ид: str, роль: str, папка: Path, волна: Path) -> tuple[bool, str]:
    if артефакт_готов(папка, роль)[0] and роль not in СУДЬИ:
        журнал(волна, f"  {ид} · {роль}: уже сделано, пропускаю")
        return True, ""
    for попытка in range(ПОВТОРОВ + 1):
        код, хвост = запустить(роль, промпт(роль, ид, папка, волна))
        готов, беда = артефакт_готов(папка, роль)
        if готов:
            журнал(волна, f"  {ид} · {роль}: готово")
            return True, ""
        журнал(волна, f"  {ид} · {роль}: {беда} (код {код}, попытка {попытка + 1})")
    return False, f"{роль}: {беда}\n{хвост.strip()[-600:]}"


def провести(ид: str, волна: Path) -> str:
    папка = волна / "cards" / ид
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
        ок, беда = шаг(ид, роль, папка, волна)
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
            for мусор in ("DEV.md", АРТЕФАКТ[роль][0]):
                (папка / мусор).unlink(missing_ok=True)
            i = цепочка.index("dev")
            continue
        i += 1
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


def вечер(исходник: Path) -> int:
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
            list(пул.map(lambda и: шаг(и, роль, волна / "cards" / и, волна), список))

    журнал(волна, "\n### карта задевания")
    запустить("solution-architect", (
        f"Твоя рабочая копия — `{КОРЕНЬ}`, все пути абсолютные.\n"
        f"Собери карту задевания волны. Прочитай RAZBOR.md всех карточек в "
        f"`{волна / 'cards'}` целиком, все сразу, и напиши "
        f"`{волна / 'MAP.md'}`: по каждой карточке — задетые экраны, "
        f"файлы и таблицы, столкновения с другими карточками, порядок и полоса, и список "
        f"смежных экранов, чьи кейсы придётся перекликать. Секции: `## Карта`, `## Порядок`."),
        профиль="terra")
    журнал(волна, "карта: " + ("готова" if (волна / "MAP.md").exists() else "НЕ СОЗДАНА"))
    журнал(волна, f"\nВечер закончен. Посмотри вопросы и допущения, потом: "
                  f"python3 scripts/night.py ночь night/{волна.name}")
    return 0


def ночь(волна: Path, полос: int) -> int:
    ид_список = карточки(волна)
    if not ид_список:
        print(f"в {волна}/cards нет карточек — сначала вечер", file=sys.stderr)
        return 1
    for н, и in enumerate(ид_список):
        ПОЛОСА[и] = н % полос + 1
    журнал(волна, f"\n## Ночь · карточек {len(ид_список)} · полос {полос}")
    with futures.ThreadPoolExecutor(max_workers=полос) as пул:
        итоги = list(пул.map(lambda и: провести(и, волна), ид_список))
    сделано = итоги.count("сделано")
    журнал(волна, f"\n## Итог: сделано {сделано}, отложено {len(итоги) - сделано}")

    запустить("product-acceptor", (
        f"Твоя рабочая копия — `{КОРЕНЬ}`, все пути абсолютные.\n"
        f"Прими работу ночи одним проходом. Карточки — `{волна / 'cards'}`, "
        f"скриншоты — `{КОРЕНЬ}/docs/evidence/`. Отчёт запиши в `{волна / 'OTCHET.md'}`."))
    журнал(волна, "отчёт: " + ("готов" if (волна / "OTCHET.md").exists() else "НЕ СОЗДАН"))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Ночной оркестратор WMS")
    p.add_argument("фаза", choices=["вечер", "ночь", "проверка"])
    p.add_argument("путь", nargs="?", help="файл со списком (вечер) или папка волны (ночь)")
    p.add_argument("--полос", type=int, default=6)   # полоса на агента: ждать нечего
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
    return вечер(Path(a.путь).resolve()) if a.фаза == "вечер" else ночь(Path(a.путь).resolve(), a.полос)


if __name__ == "__main__":
    sys.exit(main())
