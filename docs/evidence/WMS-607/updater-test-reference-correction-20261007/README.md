# WMS-607: исправление буквальных ссылок document gate — 07.10.2026

Программная приёмка `2f7294b215db273210952475817f8c48fc0cf761` остаётся действующей:
product bdd5a8 не изменён. Тот же отдельный replacement analyst01a11390 исправил
только Test cells WMS-607: `py::Class.test_name` → `py::test_name`, поскольку
существующий checker проверяет буквальное наличие имени в исходнике Python.
В actual документе12 ссылок:2 ArtMaksHTTPContract и10 UpdaterContract, включая
две preservation проверки. Каждое plain function name проверено по AST definitions;
точные classname/method IDs frozen JSON и XML не изменены.

После materialization разрешённых sparse путей выполнена ровно одна команда:

```sh
python3 -B scripts/ci/check_task_documents.py 49da13fd2a0d22f207818248f274cf5ff400e39f
```

**PASS, native exit0**: «Документы задач заполнены; AGENTS.md и CLAUDE.md совпадают».
[Исходный stdout](document-gate.log), [команда/exit](document-gate.json),
[привязка reference-only diff и сохранённых bytes](source-probe.json).
Это успешная проверка документа, не новые runtime tests/build/package CI.
Ранее отмеченный missing-file результат sparse checkout остаётся историей.
http-recovery-probe.py существует в Git и материализован без изменения.

Требования, сценарии, вердикты, accepted software, бэклог, checker, продукт и тесты
сохранены. Для isolated package CI предлагается новый опубликованный HEAD этой
docs-only ветки, точный SHA передаётся после push. Пакеты, публичная доставка,
установка, U-C9/U-C10/P-A7 и Telegram pending; новые условия не добавлены.
