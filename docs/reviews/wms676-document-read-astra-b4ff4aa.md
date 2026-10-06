# WMS-676 F1.1: независимое DELTA-ревью чтения документа

**Вердикт: PASS** для точного продуктового SHA
`b4ff4aa902628ae0b05b4ca04fc1d0b456522f1d` относительно
`a5e42b2c78ceaf0273deb1e985fabfa54dbfa708`.
F1.1 закрыт: обычное вложение и документ длинного ответа читаются в неизменяемые
bytes до последнего атомарного claim, а настоящий сетевой клиент использует
эти bytes без повторного чтения пути. Подтверждённых дефектов этой дельты нет.

Назначение отдельной сессии по прямому запросу — Astra high DELTA review;
фактические параметры модели отдельным инструментом здесь не измерялись.
Эта сессия не разрабатывала проверяемый код. Навыки, дополнительные агенты
и модельные вызовы не запускались. Единственное сохраняемое изменение — отчёт.

## Основание и границы

Прочитаны полный локальный AGENTS.md, полные owner-cases.md и failure-cases.md,
R9–R12/C17–C22 в docs/requirements/WMS-676.md. После fetch сверены правила
origin/etalon на `954862b718f9f2f1faefb2f00ad2fef72a6e1929`; более новое прямое
поручение владельца определяет модель и узкие границы данного ревью.
Прочитаны прежний FAIL в wms676-owner-reply-claim-astra-61c8304.md из
`c8925360dba040cbb291b0a7022247653ec88eab`, отдельный RED-контракт a5e42b2,
wms676-document-read-race-red-handoff.md и wms676-document-read-race-developer.md.

Дельта содержит только telegram.py и отчёт разработчика. Store, схема,
авторизация, требования, новые три и прежние 24 проверки, остальной набор
тестов и guards не изменены. Проверены точный HEAD, отсутствие рабочих правок
проверяемого кода и `git diff --check a5e42b2 b4ff4aa`. Чужие untracked-файлы
сохранены. Архитектура и исторические RED повторно не пересматривались.

## Проверка исправления

В telegram.py:311–320 путь обычного вложения либо созданного длинного ответа
читается ровно до Store.claim_outbox. Path.read_bytes возвращает bytes;
TelegramClient получает их дополнительным keyword-only аргументом file_bytes.
В send_document (строки 85–100) проверяется именно `file_bytes is None`, поэтому
пустой файл тоже использует подготовленные байты. `_call("sendDocument")`
передаёт HTTP-клиенту пару (имя, bytes); создание Path и получение имени
не открывают файл. Повторного файлового чтения в этом пути нет.

Публичный вызов send_document с прежними четырьмя аргументами по-прежнему
читает переданный путь. Сохранены имя, caption и его ограничение, reply_to,
allow_sending_without_reply, timeout=120 и классификация сетевых исходов.
Существующие записывающие двойники получают прежний интерфейс с путём;
продуктовый dispatcher использует TelegramClient через прежнюю маршрутизацию
Bots.for_chat. Других продуктовых реализаций send_document в этом контуре нет.

Точка принятия решения остаётся финальным атомарным claim: BEGIN IMMEDIATE,
повторная проверка текущей политики/источника/версии и полей намерения,
pending → sending с attempts+1, затем COMMIT до сети. Запрет, сохранённый
во время чтения файла до claim, предотвращает отправку. Новая проверка после
claim и транзакция на время сети не добавлены. Изменение политики после
успешного claim не отменяет уже начатую сетевую отправку; такой отмены это
ревью не требует.

Пути unknown, interrupted sending, not_sent, failed, sent и repeat_ok
побитово сохранены. Пауза остаётся на точном чате; разрешение относится только
к одному конкретному ответу и текущей версии, не выпускает старую очередь.
Повтор не создаёт новую отправку. Полный длинный текст, обычные вложения,
исходный file_path, сохранённый анализ и канал владельца сохранены.

## Выполненные проверки

Один ограниченный pytest-прогон: **35 passed in 0.25s**, без skips/xfail.
Это новые 3 + прежние 24 + 8 адресных проверок совместимости документов
и исходов отправки. Команда:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools/support_agent python3 -m pytest -q \
  -p no:cacheprovider -o addopts='' \
  tools/support_agent/tests/test_owner_client_reply_document_read_race.py \
  tools/support_agent/tests/test_owner_client_reply_claim_race.py \
  tools/support_agent/tests/test_owner_client_reply_pause.py \
  tools/support_agent/tests/test_owner_client_reply_pause_cli.py \
  tools/support_agent/tests/test_runner_and_safety.py::test_send_document_uploads_file_and_classifies_errors \
  tools/support_agent/tests/test_runner_and_safety.py::test_killed_between_send_and_record_is_not_repeated_and_owner_is_told \
  tools/support_agent/tests/test_runner_and_safety.py::test_lost_telegram_response_to_client_is_not_repeated_but_owner_messages_are \
  tools/support_agent/tests/test_runner_and_safety.py::test_not_sent_errors_are_retried_and_rejection_is_final \
  tools/support_agent/tests/test_review_fixes.py::test_long_answer_is_never_truncated_owner_and_client_get_same_file \
  tools/support_agent/tests/test_review_fixes.py::test_telegram_refuses_to_truncate_and_outbox_sends_long_text_as_file \
  tools/support_agent/tests/test_pipeline_chat.py::test_file_export_is_previewed_as_document_and_sent_only_after_confirmation \
  tools/support_agent/tests/test_pipeline_chat.py::test_file_changed_after_preview_is_not_sent
```

Три новых постоянных проверки используют два настоящих соединения синтетической
SQLite: пауза, отзыв разрешения/revision=2, смена версии v1 → v2 во время чтения.
Каждая теперь получает pending/attempts=0, один read до claim и ноль HTTP POST.

Дополнительно выполнены шесть узких разовых синтетических случаев через
настоящие TelegramClient, _call и httpx.MockTransport, без внешней сети:

- Длинный разрешённый ответ, обычный бинарный файл и пустой файл: Path.read_bytes
  вызван один раз при pending/0. Исходный файл удалён непосредственно перед
  настоящим claim. HTTP multipart всё равно содержит полные исходные bytes
  и прежнее имя; для обычных файлов сохранены caption/reply_to. Во время POST
  статус sending/1, транзакция закрыта. Итог sent/1, второй flush ничего не
  отправляет, поля намерения и анализ не изменены. Пауза, установленная уже
  внутри HTTP-транспорта после claim, не превращает успешную отправку в отмену.
- Обычный файл с паузой во время read: ноль POST, pending/0, намерение сохранено.
- Прямые вызовы send_document с непустыми и пустыми file_bytes при несуществующем
  пути: оба успешны. Любой Path.read_bytes был подменён исключением, поэтому
  успех отдельно доказывает отсутствие второго чтения в публичном методе.

Предыдущие положительные выводы о политике и атомарном claim не отменяются.
136 PASS из отчёта разработчика остаются его результатом; весь тот набор
здесь не повторялся и не выдаётся за независимый прогон этой сессии.
Полный CI, приёмка и ruff/mypy здесь не выполнялись.

## Передача ведущему

F1.1 получает PASS на b4ff4aa902628ae0b05b4ca04fc1d0b456522f1d.
Ведущий может продолжить отдельную безопасную установку по своему поручению
от установленной базы 8cd8; её состояние в этой сессии не проверялось.
Этот отчёт не доказывает установку или поведение рабочего процесса.
Браузер, секреты, live БД, Telegram, установленный runtime, установка и деплой
не затрагивались. Merge в main не выполняется.
