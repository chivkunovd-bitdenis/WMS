## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py` — атомарная фиксация черновика, проверка проблем, снимок тарифа и публикация ledger через общий billing-модуль; повторная фиксация идемпотентна.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py` — POST `/operations/storage/statements/{statement_id}/fix` и GET `/operations/storage/statements/{statement_id}/print`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_statement_service.py` — проверка обязательной зависимости общего billing-слоя.

## Гейты

- ruff — PASS для изменённых файлов.
- mypy — FAIL: отсутствует `app.models.billing`, плюс есть существующие ошибки в соседних сервисах.
- pytest — PASS: существующие `2 passed`; новый тест фиксирует отсутствие 09-A зависимости.
- back_guard.py — NOT RUN: файл отсутствует.
- check_migrations.py — NOT RUN: файл отсутствует.

## Не реализовано

- Полная публикация `BillingLedgerEntry` и повторная печать с тарифом-снимком не может быть выполнена буквально: общий модуль `app.models.billing` (09-A) отсутствует. Свой storage-тариф, storage-таблицу или второй путь счёта не добавлял.
- Тесты параллельной фиксации и A4-содержимого не добавлял без валидных 09-A billing fixtures.

## Находки

- Секретные файлы, ключи, токены, `.env` и кабинеты учётных данных не читались и не использовались.
