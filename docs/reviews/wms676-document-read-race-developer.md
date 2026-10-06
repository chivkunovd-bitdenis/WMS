# WMS-676 F1.1: передача минимального исправления

Замена разработчика по прямому поручению владельца. База — отдельный
RED-контракт `a5e42b2c78ceaf0273deb1e985fabfa54dbfa708`, после независимого
FAIL `c8925360dba040cbb291b0a7022247653ec88eab` на коде `61c8304`.
Прочитаны локальный AGENTS.md, обновлённый origin/etalon:AGENTS.md,
R9–R12 требований и обе передачи F1.1. Более новое прямое поручение владельца
задаёт отдельное Astra high ревью ведущим; эта сессия выполняет только код.

Изменён только продуктовый `tools/support_agent/support_agent/telegram.py`.
Обычный файл и файл длинного ответа читаются до финального атомарного claim.
`TelegramClient.send_document` принимает дополнительный необязательный
keyword-only параметр `file_bytes`: при переданных байтах использует тот же
`_call("sendDocument")` без чтения файла. Прежние вызовы с путём сохраняют
своё поведение. Пустые байты также передаются без повторного чтения.
Существующие записывающие отправители с прежним интерфейсом получают путь;
настоящий TelegramClient и его наследники получают подготовленные bytes.

Путь в очереди не изменяется. Store, схема, состояния, журнал попыток,
атомарная проверка разрешения, unknown/sending recovery и классификация
сетевых ошибок не менялись. Новых проверок после claim и транзакций вокруг
HTTP нет. Frozen-тесты, требования, guards и чужие файлы не изменены.

Один ограниченный прогон: **136 passed in 1.05s**, без skips/xfail.
Он включает новые 3, прежние 24, соседние 41 и дополнительные 68 проверок
документов и связанных сценариев из test_review_fixes/test_pipeline_chat.
Публичная отправка документа по пути, сетевые ошибки и восстановление
прерванной отправки покрыты существующими тестами.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools/support_agent python3 -m pytest -q \
  -p no:cacheprovider -o addopts='' \
  tools/support_agent/tests/test_owner_client_reply_document_read_race.py \
  tools/support_agent/tests/test_owner_client_reply_claim_race.py \
  tools/support_agent/tests/test_owner_client_reply_pause.py \
  tools/support_agent/tests/test_owner_client_reply_pause_cli.py \
  tools/support_agent/tests/test_agent_tools.py \
  tools/support_agent/tests/test_runner_and_safety.py \
  tools/support_agent/tests/test_two_bots.py \
  tools/support_agent/tests/test_cli_diagnostics.py \
  tools/support_agent/tests/test_review_fixes.py \
  tools/support_agent/tests/test_pipeline_chat.py
```

Два дополнительных разовых синтетических сценария с настоящим TelegramClient
и HTTP-двойником: обычное вложение и длинный ответ. Каждый подтвердил одно
чтение при pending/attempts=0, передачу исходных байтов после изменения файла
перед claim, один POST двойнику при sending, закрытую DB-транзакцию, итог sent
и неизменный file_path очереди. Сеть не использована.

`ruff check tools/support_agent/support_agent/telegram.py` — PASS.
`mypy --follow-imports=silent tools/support_agent/support_agent/telegram.py` — PASS.
`git diff --check` и проверка документов задачи — PASS.
Полный CI, независимое ревью и приёмка этой сессией не выполнялись.

Ведущему: отдельное Astra high DELTA-ревью только нового изменения на точном
опубликованном SHA относительно a5e42b2c7. После PASS безопасную установку
от установленной базы 8cd8 выполняет ведущий отдельно. Здесь установка,
runtime, live БД, Telegram, браузер, секреты и деплой не затрагивались;
skills и агенты не запускались. Merge в main не выполняется.
