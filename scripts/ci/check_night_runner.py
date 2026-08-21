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
import json
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import night as n  # noqa: E402

ОЖИДАЕМЫЕ_ЦЕПОЧКИ = {
                    "баг": ["tester", "dev", "reviewer", "ui-critic", "clicker", "ux-judge"],
                    "фича": ["ux-architect", "product", "tester", "breaker", "dev", "reviewer",
                             "ui-critic", "clicker", "ux-judge"],
                    "домен": ["solution-architect", "ux-architect", "product", "tester", "breaker",
                              "dev", "reviewer", "ui-critic", "clicker", "ux-judge"],
                    "блокировки": ["blocker-collector", "blocker-skeptic"],
                }



def регрессии_r04(проверь) -> None:
    """Каждый дефект ночи r04 — отдельной проверкой, чтобы он не мог вернуться.

    Волна r04 завалила все девять карточек не из-за одной упавшей модели, а из-за семи
    поломок конструкции. Каждая из них ловится здесь без единого вызова модели.
    """
    import pathlib
    import tempfile

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    import night as n

    # 1. Критик исполнения стоял до разработки и честно находил, что реализации нет.
    было = dict(n.ЦЕПОЧКИ)
    try:
        n.ЦЕПОЧКИ = {"фича": ["ux-architect", "ui-critic", "tester", "dev", "reviewer"]}
        проверь("r04-1: ui-critic до dev ловится на старте", bool(n.проверить_стыки()), True)
        n.ЦЕПОЧКИ = {"баг": ["dev", "reviewer"]}
        проверь("r04-2: dev без входа ловится на старте", bool(n.проверить_стыки()), True)
    finally:
        n.ЦЕПОЧКИ = было
    проверь("r04-2: настоящие цепочки сходятся", n.проверить_стыки(), [])

    t = pathlib.Path(tempfile.mkdtemp())

    # 3. Контракты 07/08/09 сами себя остановили до утра.
    (t / "CONTRACT.md").write_text(
        "## Контракт\nx\n## Канон\nR-01\n\n"
        "Документ не разрешает разработку до подтверждения владельца.\n", encoding="utf-8")
    проверь("r04-3: контракт со стопом до владельца отклонён",
            n.артефакт_готов(t, "ux-architect")[0], False)
    (t / "CONTRACT.md").write_text("## Контракт\nx\n## Канон\nR-01\n", encoding="utf-8")
    проверь("r04-3: чистый контракт принят", n.артефакт_готов(t, "ux-architect")[0], True)

    # 4. «Нет, тип неверный: ... это домен» рядом со словом «фича».
    (t / "RAZBOR.md").write_text("## Тип\nТИП: фича\n## Экраны\n- S-03\n", encoding="utf-8")
    (t / "SVERKA.md").write_text(
        "ВЕРДИКТ: НАХОДКИ 1\nТИП: домен\n\n## Тип\n"
        "Нет, тип определён неверно: в разборе указано «фича», но это домен.\n"
        "## Расхождения\n- тип\n", encoding="utf-8")
    проверь("r04-4: отрицательная коррекция типа читается как домен", n.тип_карточки(t), "домен")

    # 5. «Нарушений не найдено» под заголовком «Находки».
    (t / "DESIGN-REVIEW.md").write_text(
        "ВЕРДИКТ: ЧИСТО\n\n## Находки\nНарушений не найдено\n", encoding="utf-8")
    проверь("r04-5: положительная фраза не считается находкой",
            n.есть_находки(t, "ui-critic"), False)
    (t / "DESIGN-REVIEW.md").write_text("## Находки\nНарушений не найдено\n", encoding="utf-8")
    проверь("r04-5: судья без машинной строки не принят",
            n.артефакт_готов(t, "ui-critic")[0], False)

    # 6. Ревьюер считал кейсы тестировщика выходом за границы экрана.
    класс = type("Р", (), {"корень": t})
    with mock.patch.object(n, "_git", return_value=mock.Mock(
            returncode=0, stdout=" M tests/cases/S-03.md\n M night/x/RAZBOR.md\n"
                                 " M frontend/src/screens/v2/FfFbsOrdersScreen.tsx\n", stderr="")):
        файлы = n.дифф_реализации(t)
        текст = n.дифф_для("reviewer", класс())
    проверь("r04-6: кейсы и разборы не попадают в дифф реализации",
            файлы, ["frontend/src/screens/v2/FfFbsOrdersScreen.tsx"])
    проверь("r04-6: ревьюеру назван состав правки", "FfFbsOrdersScreen.tsx" in текст, True)
    проверь("r04-6: тестировщику нечего инкриминировать", "tests/cases" in текст, False)

    # 7. Карточка обязана оставить коммит реализации.
    проверь("r04-7: проверка коммита существует", hasattr(n, "проверить_сохранение"), True)


def fake_e2e_smoke(проверь) -> None:
    """Детерминированный full-chain smoke без Codex, git и стенда.

    Это намеренно не мок ``провести``: вечер и ночная цепочка выполняются настоящим
    оркестратором, а fake executor оставляет только контрактные артефакты. Так smoke
    ловит регрессии в пропусках, отложении и resume, не создавая worktree или оплату
    модели. Красные проверки в конце фиксируют обязательные hard-gates для следующего
    слоя оркестратора (commit карточки, идентичность стенда и SHA для acceptor).
    """
    with tempfile.TemporaryDirectory(prefix="check-night-e2e-") as временный:
        root = pathlib.Path(временный)
        source = root / "raw.md"
        source.write_text("# Список\n- карточка ok\n- карточка fail\n", encoding="utf-8")
        calls: list[tuple[str, str]] = []
        stands: list[tuple[int, str]] = []
        fail_card = {"enabled": True}
        committed: dict[str, bool] = {}
        current_wave: dict[str, pathlib.Path] = {}
        original_root = n.КОРЕНЬ
        original_launch = n.запустить
        original_cards = n.рабочие_карточки
        original_stand = n.поднять_стенд
        original_git = n._git
        original_startup = n.проверки_старта
        original_cache = dict(n.СТЕНД)

        def card_from_prompt(prompt: str) -> pathlib.Path:
            marker = "Твоя папка — `"
            start = prompt.index(marker) + len(marker)
            return pathlib.Path(prompt[start:prompt.index("`", start)])

        def fake_launch(role: str, prompt: str, профиль=None, cwd=n.КОРЕНЬ):
            calls.append((role, prompt))
            if role == "intake":
                queue_marker = "и общий `"
                queue_start = prompt.index(queue_marker) + len(queue_marker)
                queue_path = pathlib.Path(prompt[queue_start:prompt.index("`", queue_start)])
                wave = queue_path.parent
                current_wave["path"] = wave
                for card in ("ok", "fail"):
                    folder = wave / "cards" / card
                    folder.mkdir(parents=True, exist_ok=True)
                    (folder / "ISTOCHNIK.md").write_text("## Дословно\nкарточка\n", encoding="utf-8")
                (wave / "QUEUE.md").write_text("ok\nfail\n", encoding="utf-8")
                return 0, "fake intake"
            if role == "solution-architect":
                wave = current_wave["path"]
                (wave / "MAP.md").write_text(
                    "## Карта\nok, fail\n## Порядок\n1. ok\n2. fail\n", encoding="utf-8")
                return 0, "fake map"
            if role == "product-acceptor":
                wave = current_wave["path"]
                (wave / "OTCHET.md").write_text(
                    "## Сделано\nok\n## Не доехало\nнет\n## Допущения аналитиков\nнет\n"
                    "## Решения продакта\nнет\n## Оформление\nпроверено\n", encoding="utf-8")
                return 0, "fake acceptor"
            folder = card_from_prompt(prompt)
            card = folder.name
            if role == "analyst":
                (folder / "RAZBOR.md").write_text(
                    "## Дословно\nx\n## Что сейчас\nx\n## Что должно быть\nx\n## Тип\nТИП: баг\n",
                    encoding="utf-8")
            elif role == "requirement-critic":
                (folder / "SVERKA.md").write_text(
                    "ВЕРДИКТ: ЧИСТО\nТИП: баг\n\n## Тип\nбаг\n## Расхождения\nнет\n", encoding="utf-8")
            elif role == "tester":
                if card == "fail" and fail_card["enabled"]:
                    return 1, "fake timeout"
                (folder / "CASES.md").write_text("## Назначенные кейсы\n- smoke\n", encoding="utf-8")
            elif role in {"screen-dev", "backend-dev"}:
                (folder / "DEV.md").write_text("## Изменённые файлы\n- fake\n## Гейты\npass\n", encoding="utf-8")
                # Fake executor models a real card commit. ``base_sha`` differs
                # from this branch SHA and fake _git below exposes clean status.
                committed[card] = True
            elif role == "reviewer":
                (folder / "REVIEW.md").write_text(
                    "ВЕРДИКТ: ЧИСТО\n\n## Находки\nнет\n", encoding="utf-8")
            elif role == "ui-critic":
                (folder / "DESIGN-REVIEW.md").write_text(
                    "ВЕРДИКТ: ЧИСТО\n\n## Находки\nнет\n", encoding="utf-8")
            elif role == "clicker":
                (folder / "CLICKS.md").write_text("## Пройденные кейсы\n- smoke\n## Не прошло\nнет\n", encoding="utf-8")
            elif role == "ux-judge":
                (folder / "JUDGE.md").write_text(
                    "ВЕРДИКТ: ЧИСТО\n\n## Находки\nнет\n## Пройденные кейсы\n- smoke\n", encoding="utf-8")
            return 0, "fake ok"

        def fake_stand(lane: int, worker=None) -> str:
            stands.append((lane, worker.ид if worker else "unknown"))
            return f"FAKE-STAND lane={lane} card={worker.ид if worker else 'unknown'}"

        def fake_git(*args: str, cwd=root):
            if args[:2] == ("rev-parse", "HEAD"):
                return mock.Mock(returncode=0, stdout=f"branch-sha-{pathlib.Path(cwd).name}\n", stderr="")
            if args[:2] == ("status", "--porcelain"):
                return mock.Mock(returncode=0, stdout="", stderr="")
            return mock.Mock(returncode=0, stdout="", stderr="")

        class FakeWorker:
            def __init__(self, card: str, wave: pathlib.Path):
                self.ид = card
                self.lane = 1
                self.корень = root
                self.волна = wave
                self.папка = wave / "cards" / card
                self.ветка = f"fake/{card}"
                self.base_sha = f"base-sha-{card}"

        def fake_workers(wave, cards, lanes):
            return {card: FakeWorker(card, wave) for card in cards}

        try:
            n.КОРЕНЬ = root
            n.СТЕНД.clear()
            n.запустить = fake_launch
            n.рабочие_карточки = fake_workers
            n.поднять_стенд = fake_stand
            n._git = fake_git
            n.проверки_старта = lambda: []
            with mock.patch.object(sys, "argv", ["night.py", "полный", str(source), "--fresh",
                                                   "--run-id", "fake-run", "--полос", "1"]):
                проверь("fake E2E: полный запуск завершает остальные карточки и сигнализирует deferred", n.main(), 2)
            wave = root / "night" / f"{source.stem}-fake-run"
            проверь("fake E2E: MAP создан", (wave / "MAP.md").exists(), True)
            проверь("fake E2E: ok карточка завершена", not (wave / "cards" / "ok" / "OTLOZHENO.md").exists(), True)
            проверь("fake E2E: fail карточка отложена", (wave / "cards" / "fail" / "OTLOZHENO.md").exists(), True)
            fail_card["enabled"] = False
            проверь("fake E2E: resume проходит", n.ночь(wave, 1), 0)
            проверь("fake E2E: resume снимает отложено", (wave / "cards" / "fail" / "OTLOZHENO.md").exists(), False)
            проверь("fake E2E: acceptor вызван", sum(role == "product-acceptor" for role, _ in calls), 2)
            проверь("fake E2E: отдельный stand на карточку", len(stands), 2)
            проверь("fake E2E: dev обязан сохранить commit", all(committed.values()), True)
            acceptor_prompts = [p for role, p in calls if role == "product-acceptor"]
            проверь("fake E2E: acceptor получает SHA карточек",
                    all("SHA branch-sha-" in p and "artifacts" in p for p in acceptor_prompts), True)
        finally:
            n.КОРЕНЬ = original_root
            n.запустить = original_launch
            n.рабочие_карточки = original_cards
            n.поднять_стенд = original_stand
            n._git = original_git
            n.проверки_старта = original_startup
            n.СТЕНД.clear()
            n.СТЕНД.update(original_cache)


def main() -> int:
    беды: list[str] = []

    # Это smoke-проверка для Codex mode: она не должна запускать ни Claude, ни
    # любой другой внешний процесс. Если в проверку случайно попадёт вызов
    # оркестратора, тест упадёт явно, а не начнёт реальную ночную волну.
    def внешний_вызов(*_args, **_kwargs):
        raise AssertionError("smoke не должен запускать внешние процессы")

    настоящий_вызов = n.subprocess.run
    n.subprocess.run = внешний_вызов

    def проверь(имя: str, факт, ждём) -> None:
        if факт != ждём:
            беды.append(f"{имя}: получил {факт!r}, ждал {ждём!r}")

    try:
        with tempfile.TemporaryDirectory(prefix="check-night-runner-") as временный:
            t = pathlib.Path(временный)
            проверь("нет файла", n.артефакт_готов(t, "reviewer")[0], False)

            (t / "REVIEW.md").write_text("## Проверено и нормально\nвсё ок\n", encoding="utf-8")
            проверь("нет обязательной секции", n.артефакт_готов(t, "reviewer")[0], False)

            (t / "REVIEW.md").write_text(
                "ВЕРДИКТ: ЧИСТО\n\n## Находки\n\n## Проверено и нормально\nсмотрел\n", encoding="utf-8")
            проверь("вердикт ЧИСТО — шаг пройден", n.артефакт_готов(t, "reviewer")[0], True)
            проверь("вердикт ЧИСТО — без возврата", n.есть_находки(t, "reviewer"), False)

            # Ровно та формулировка, которая в волне r04 остановила готовую карточку 09.
            (t / "REVIEW.md").write_text(
                "ВЕРДИКТ: ЧИСТО\n\n## Находки\nНарушений не найдено\n", encoding="utf-8")
            проверь("«Нарушений не найдено» не считается находкой", n.есть_находки(t, "reviewer"), False)

            (t / "REVIEW.md").write_text("## Находки\nчто-то\n", encoding="utf-8")
            проверь("нет машинной строки — шаг не пройден", n.артефакт_готов(t, "reviewer")[0], False)

            (t / "REVIEW.md").write_text(
                "ВЕРДИКТ: НАХОДКИ 1\n\n## Находки\n- fbs.py:81 упадёт на статусе sorted\n\n"
                "## Проверено и нормально\nда\n",
                encoding="utf-8")
            проверь("непустые Находки — возврат", n.есть_находки(t, "reviewer"), True)

            (t / "REVIEW.md").write_text(
                "ВЕРДИКТ: ЧИСТО\n\n## Находки\nнет\n\n## Проверено и нормально\nда\n", encoding="utf-8")
            проверь("«нет» словом — без возврата", n.есть_находки(t, "reviewer"), False)

            (t / "JUDGE.md").write_text("\x00 мусор без секций", encoding="utf-8", errors="replace")
            проверь("битый файл — не пройден, без исключения", n.артефакт_готов(t, "ux-judge")[0], False)

            (t / "RAZBOR.md").write_text("## Экраны\n- S-03 FBS\n", encoding="utf-8")
            проверь("экран из реестра — фронтовик", n.выбрать_dev(t), "screen-dev")
            (t / "RAZBOR.md").write_text("## Экраны\nэкран будет создан\n", encoding="utf-8")
            проверь("без экрана — бэкендер", n.выбрать_dev(t), "backend-dev")

            (t / "RAZBOR.md").write_text("## Тип\nбаг\n## Экраны\n- S-03\n", encoding="utf-8")
            проверь("тип читается", n.поле(t, "RAZBOR.md", "Тип").strip(), "баг")
            проверь("машинный тип из разбора", n.тип_карточки(t), "баг")
            (t / "SVERKA.md").write_text(
                "## Тип\nНеверно определён. Верный тип — `домен`.\n## Расхождения\nнет\n",
                encoding="utf-8")
            проверь("критик исправляет тип и Markdown не мешает", n.тип_карточки(t), "домен")
            проверь("нет секции — пусто, без падения", n.поле(t, "RAZBOR.md", "Нетути"), "")

            проверь("неизвестная роль не роняет цепочку", n.артефакт_готов(t, "выдуманная")[0], True)
    finally:
        n.subprocess.run = настоящий_вызов

    проверь("цепочки не изменились при переносе", n.ЦЕПОЧКИ, ОЖИДАЕМЫЕ_ЦЕПОЧКИ)

    # Карточный worktree не содержит gitignored snapshot. Разрешён только
    # существующий sanitized-latest.dump из главного checkout; raw dump не
    # подставляется и не читается.
    with tempfile.TemporaryDirectory(prefix="check-night-snapshot-") as временный:
        snapshot_root = pathlib.Path(временный)
        stand = snapshot_root / ".stand"
        stand.mkdir()
        sanitized = stand / "sanitized-latest.dump"
        sanitized.write_bytes(b"sanitized fixture")
        проверь("snapshot: абсолютный sanitized путь", n.санитарный_снимок(snapshot_root), sanitized.resolve())
        sanitized.unlink()
        (stand / "raw-production.dump").write_bytes(b"must not be selected")
        проверь("snapshot: raw fallback запрещён", n.санитарный_снимок(snapshot_root), None)
    restore_text = (pathlib.Path(n.КОРЕНЬ) / "scripts/stand/restore.sh").read_text(encoding="utf-8")
    проверь("snapshot: restore получает только явный env", "WMS_SANITIZED_SNAPSHOT" in restore_text, True)
    проверь("snapshot: restore требует sanitized имя", "sanitized-latest.dump" in restore_text, True)
    for р in {r for ц in n.ЦЕПОЧКИ.values() for r in ц if r != "dev"}:
        if р not in n.АРТЕФАКТ:
            беды.append(f"роль {р} в цепочке, но её нет в таблице АРТЕФАКТ")

    for р, (имя, секции) in n.АРТЕФАКТ.items():
        if имя is not None and not секции:
            беды.append(f"для роли {р} назван файл {имя}, но нет обязательных секций")

    # Контракт Codex-адаптера повторяет класс модели из файла роли:
    # opus → Sol, sonnet → Terra, haiku → Luna.
    analyst_prompt = n.роль_с_инъекцией("analyst", "marker")
    intake_prompt = n.роль_с_инъекцией("intake", "marker")
    проверь("роль analyst opus → Sol", analyst_prompt.startswith(
        "Профиль исполнителя: Sol. Выполняй только роль `analyst`."), True)
    проверь("роль intake haiku → Luna", intake_prompt.startswith(
        "Профиль исполнителя: Luna. Выполняй только роль `intake`."), True)
    проверь("промпт analyst содержит полный текст роли",
            pathlib.Path(n.КОРЕНЬ, ".claude/agents/analyst.md").read_text(encoding="utf-8") in analyst_prompt, True)

    # JSONL-ответ Codex — это транспорт, не гейт: текст и ошибки должны
    # извлекаться детерминированно, а мусорные события игнорироваться.
    jsonl = '{"type":"message","text":"готово"}\n{"type":"error","error":"timeout"}\n{"type":"noise"}\n'
    проверь("разбор Codex JSONL", n._codex_текст(jsonl), "готово\nошибка Codex: timeout")

    # Фиксируем CLI-контракт без запуска бинарника. Этот тест намеренно
    # проверяет порядок глобального флага до подкоманды exec.
    вызов = {}

    def fake_run(args, **kwargs):
        вызов["args"] = args
        return mock.Mock(returncode=0, stdout='{"type":"message","text":"ok"}\n', stderr="")

    with mock.patch.object(n.shutil, "which", return_value="/usr/local/bin/codex"), \
         mock.patch.object(n.subprocess, "run", side_effect=fake_run):
        n._запустить_codex("analyst", "marker")
    args = вызов.get("args", [])
    проверь("Codex CLI: approval перед exec", args.index("--ask-for-approval") < args.index("exec")
            if "--ask-for-approval" in args and "exec" in args else False, True)
    проверь("Codex CLI: analyst получает search до exec", args.index("--search") < args.index("exec")
            if "--search" in args and "exec" in args else False, True)
    проверь("Codex CLI: ignore-user-config после exec для analyst",
            args.index("--ignore-user-config") > args.index("exec")
            if "--ignore-user-config" in args and "exec" in args else False, True)
    проверь("Codex CLI: analyst opus → Sol", "gpt-5.6-sol" in args, True)
    проверь("Codex CLI: Sol medium задан явно", "model_reasoning_effort=medium" in args, True)

    вызов.clear()
    with mock.patch.object(n.shutil, "which", return_value="/usr/local/bin/codex"), \
         mock.patch.object(n.subprocess, "run", side_effect=fake_run):
        n._запустить_codex("solution-architect", "marker")
    args = вызов.get("args", [])
    проверь("Codex CLI: solution-architect opus → Sol", "gpt-5.6-sol" in args, True)
    проверь("Codex CLI: solution-architect сохраняет search", "--search" in args, True)

    вызов.clear()
    try:
        with mock.patch.object(n.shutil, "which", return_value="/usr/local/bin/codex"), \
             mock.patch.object(n.subprocess, "run", side_effect=fake_run):
            n._запустить_codex("solution-architect", "marker", профиль="sol")
    except TypeError as ошибка:
        беды.append(f"Codex CLI: нет явного профиля для MAP-агрегации: {ошибка}")
    args = вызов.get("args", [])
    проверь("Codex CLI: MAP solution-architect → Sol", "gpt-5.6-sol" in args, True)
    проверь("Codex CLI: MAP Sol medium", "model_reasoning_effort=medium" in args, True)
    проверь("Codex CLI: MAP override сохраняет search до exec",
            args.index("--search") < args.index("exec")
            if "--search" in args and "exec" in args else False, True)
    проверь("Codex CLI: MAP override ignore после exec",
            args.index("--ignore-user-config") > args.index("exec")
            if "--ignore-user-config" in args and "exec" in args else False, True)

    # Недопустимый профиль не должен доходить до subprocess.
    вызов.clear()
    with mock.patch.object(n.shutil, "which", return_value="/usr/local/bin/codex"), \
         mock.patch.object(n.subprocess, "run", side_effect=fake_run) as запуск:
        результат = n._запустить_codex("analyst", "marker", профиль="opus")
    проверь("Codex CLI: профиль opus отклонён", результат[0] != 0, True)
    проверь("Codex CLI: профиль opus не доходит до subprocess", запуск.call_count, 0)

    вызов.clear()
    with mock.patch.object(n.shutil, "which", return_value="/usr/local/bin/codex"), \
         mock.patch.object(n.subprocess, "run", side_effect=fake_run):
        n._запустить_codex("intake", "marker")
    args = вызов.get("args", [])
    проверь("Codex CLI: intake haiku → Luna", "gpt-5.6-luna" in args, True)
    проверь("Codex CLI: intake Luna low", "model_reasoning_effort=low" in args, True)
    проверь("Codex CLI: control-роль без search", "--search" not in args, True)

    вызов.clear()
    with mock.patch.object(n.shutil, "which", return_value="/usr/local/bin/codex"), \
         mock.patch.object(n.subprocess, "run", side_effect=fake_run):
        n._запустить_codex("product-acceptor", "marker")
    args = вызов.get("args", [])
    проверь("Codex CLI: product-acceptor opus → Sol", "gpt-5.6-sol" in args, True)
    проверь("Codex CLI: product-acceptor Sol medium", "model_reasoning_effort=medium" in args, True)

    вызов.clear()
    with mock.patch.object(n.shutil, "which", return_value="/usr/local/bin/codex"), \
         mock.patch.object(n.subprocess, "run", side_effect=fake_run):
        n._запустить_codex("clicker", "marker")
    args = вызов.get("args", [])
    проверь("Codex CLI: browser role без ignore-user-config",
            "--ignore-user-config" not in args, True)

    # Контракт свежего прогона: существующая волна может быть грязной или
    # частично выполненной, поэтому --fresh/--run-id никогда не переиспользуют
    # её каталог и не требуют ручного копирования исходника. Проверяем только
    # публичный helper на временных каталогах; бизнес-волна и git не затрагиваются.
    with tempfile.TemporaryDirectory(prefix="check-night-fresh-") as временный:
        root = pathlib.Path(временный)
        source = root / "zadachi-2026-08-21.md"
        source.write_text("# исходный список\n- карточка\n", encoding="utf-8")
        old = root / "zadachi-2026-08-21"
        (old / "cards" / "partial").mkdir(parents=True)
        (old / "JOURNAL.md").write_text("старый прогон\n", encoding="utf-8")
        old_marker = (old / "JOURNAL.md").read_text(encoding="utf-8")

        try:
            fresh = n.создать_свежую_волну(source, "run-20260821-01", базовый_каталог=root)
        except AttributeError:
            беды.append("fresh run: нет публичного helper создать_свежую_волну")
        else:
            проверь("fresh run: отдельный каталог", fresh != old, True)
            проверь("fresh run: run-id в имени", fresh.name.endswith("-run-20260821-01"), True)
            проверь("fresh run: старая волна сохранена", (old / "JOURNAL.md").read_text(encoding="utf-8"), old_marker)
            проверь("fresh run: новая папка создана", fresh.is_dir(), True)
            try:
                manifest = json.loads((fresh / "RUN.json").read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError) as ошибка:
                беды.append(f"fresh run: нет корректного RUN.json ({ошибка})")
            else:
                проверь("fresh run: source записан", manifest.get("source"), str(source))
                проверь("fresh run: run-id записан", manifest.get("run_id"), "run-20260821-01")
            проверь("fresh run: исходник не изменён", source.read_text(encoding="utf-8"), "# исходный список\n- карточка\n")

    # Full-chain fake smoke: один запуск проходит вечер и ночь, плохая карточка
    # откладывается, а повтор продолжает её. Все внешние границы подменены.
    fake_e2e_smoke(проверь)
    регрессии_r04(проверь)

    if беды:
        print("ПРОВЕРКА ОРКЕСТРАТОРА КРАСНАЯ:", file=sys.stderr)
        for б in беды:
            print(f"  - {б}", file=sys.stderr)
        return 1
    print("оркестратор: все случаи сошлись")
    return 0


if __name__ == "__main__":
    sys.exit(main())
