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
    "баг": ["tester", "dev", "reviewer", "clicker", "ux-judge"],
    "фича": ["ux-architect", "ui-critic", "tester", "breaker", "dev", "reviewer", "clicker", "ux-judge"],
    "домен": ["solution-architect", "ux-architect", "ui-critic", "tester", "breaker", "dev", "reviewer", "clicker", "ux-judge"],
    "блокировки": ["blocker-collector", "blocker-skeptic"],
}


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
    finally:
        n.subprocess.run = настоящий_вызов

    проверь("цепочки не изменились при переносе", n.ЦЕПОЧКИ, ОЖИДАЕМЫЕ_ЦЕПОЧКИ)
    for р in {r for ц in n.ЦЕПОЧКИ.values() for r in ц if r != "dev"}:
        if р not in n.АРТЕФАКТ:
            беды.append(f"роль {р} в цепочке, но её нет в таблице АРТЕФАКТ")

    for р, (имя, секции) in n.АРТЕФАКТ.items():
        if имя is not None and not секции:
            беды.append(f"для роли {р} назван файл {имя}, но нет обязательных секций")

    # Контракт Codex-адаптера: роли предметной работы идут Luna, две
    # управляющие роли — Terra. Проверяем это через публичный helper, не
    # запуская CLI.
    analyst_prompt = n.роль_с_инъекцией("analyst", "marker")
    intake_prompt = n.роль_с_инъекцией("intake", "marker")
    проверь("роль analyst принадлежит Luna", analyst_prompt.startswith(
        "Профиль исполнителя: Luna. Выполняй только роль `analyst`."), True)
    проверь("роль intake принадлежит Terra", intake_prompt.startswith(
        "Профиль исполнителя: Terra. Выполняй только роль `intake`."), True)
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
    проверь("Codex CLI: Luna model задан явно", "gpt-5.6-luna" in args, True)
    проверь("Codex CLI: Luna без Sol", "gpt-5.6-sol" not in args, True)
    проверь("Codex CLI: Luna low задан явно", "model_reasoning_effort=low" in args, True)

    вызов.clear()
    with mock.patch.object(n.shutil, "which", return_value="/usr/local/bin/codex"), \
         mock.patch.object(n.subprocess, "run", side_effect=fake_run):
        n._запустить_codex("solution-architect", "marker")
    args = вызов.get("args", [])
    проверь("Codex CLI: solution-architect по умолчанию Luna", "gpt-5.6-luna" in args, True)
    проверь("Codex CLI: solution-architect сохраняет search", "--search" in args, True)

    вызов.clear()
    try:
        with mock.patch.object(n.shutil, "which", return_value="/usr/local/bin/codex"), \
             mock.patch.object(n.subprocess, "run", side_effect=fake_run):
            n._запустить_codex("solution-architect", "marker", профиль="terra")
    except TypeError as ошибка:
        беды.append(f"Codex CLI: нет явного профиля для MAP-агрегации: {ошибка}")
    args = вызов.get("args", [])
    проверь("Codex CLI: MAP override solution-architect -> Terra", "gpt-5.6-terra" in args, True)
    проверь("Codex CLI: MAP override Terra medium", "model_reasoning_effort=medium" in args, True)
    проверь("Codex CLI: MAP override сохраняет search до exec",
            args.index("--search") < args.index("exec")
            if "--search" in args and "exec" in args else False, True)
    проверь("Codex CLI: MAP override ignore после exec",
            args.index("--ignore-user-config") > args.index("exec")
            if "--ignore-user-config" in args and "exec" in args else False, True)

    # Недопустимый профиль не должен доходить до subprocess: это защищает
    # контракт от старого/чужого имени модели вроде gpt-5.6-sol.
    вызов.clear()
    with mock.patch.object(n.shutil, "which", return_value="/usr/local/bin/codex"), \
         mock.patch.object(n.subprocess, "run", side_effect=fake_run) as запуск:
        результат = n._запустить_codex("analyst", "marker", профиль="sol")
    проверь("Codex CLI: профиль sol отклонён", результат[0] != 0, True)
    проверь("Codex CLI: профиль sol не доходит до subprocess", запуск.call_count, 0)
    проверь("Codex CLI: профиль sol не формирует модель", "gpt-5.6-sol" not in вызов.get("args", []), True)

    вызов.clear()
    with mock.patch.object(n.shutil, "which", return_value="/usr/local/bin/codex"), \
         mock.patch.object(n.subprocess, "run", side_effect=fake_run):
        n._запустить_codex("intake", "marker")
    args = вызов.get("args", [])
    проверь("Codex CLI: Terra model задан только control-роли", "gpt-5.6-terra" in args, True)
    проверь("Codex CLI: Terra без Sol", "gpt-5.6-sol" not in args, True)
    проверь("Codex CLI: Terra medium задан явно", "model_reasoning_effort=medium" in args, True)
    проверь("Codex CLI: control-роль без search", "--search" not in args, True)

    вызов.clear()
    with mock.patch.object(n.shutil, "which", return_value="/usr/local/bin/codex"), \
         mock.patch.object(n.subprocess, "run", side_effect=fake_run):
        n._запустить_codex("product-acceptor", "marker")
    args = вызов.get("args", [])
    проверь("Codex CLI: product-acceptor Terra", "gpt-5.6-terra" in args, True)
    проверь("Codex CLI: product-acceptor Terra medium", "model_reasoning_effort=medium" in args, True)
    проверь("Codex CLI: product-acceptor без Sol", "gpt-5.6-sol" not in args, True)

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

    if беды:
        print("ПРОВЕРКА ОРКЕСТРАТОРА КРАСНАЯ:", file=sys.stderr)
        for б in беды:
            print(f"  - {б}", file=sys.stderr)
        return 1
    print("оркестратор: все случаи сошлись")
    return 0


if __name__ == "__main__":
    sys.exit(main())
