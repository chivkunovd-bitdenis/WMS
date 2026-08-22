# 09-billing — backend-dev · ремонт атома 8

## Что реализовано

- Эндпоинт: существующий `GET /billing/ledger` принимает согласованные параметры `period=YYYY-MM` и `date=YYYY-MM-01`, возвращает человекочитаемый номер приёмки/marketplace-отгрузки и ищет по нему вместо технического UUID.
- Эндпоинты: существующие `POST /billing/invoices/{seller_id}/{period}/form`, `GET /billing/invoices`, `GET /billing/invoices/{invoice_id}` и `POST /billing/invoices/{invoice_id}/cancel` используют один tenant-изолированный алгоритм, возвращают только актуальные блокирующие причины и сохраняют идемпотентность параллельного формирования и повторной отмены.
- Сервис: `billing_invoice_service` требует зафиксированный `StorageStatement` каждого операционного склада и опубликованную ledger-строку каждого measurement, включая нулевой statement; при ещё не интегрированных моделях карточки 08 барьер безопасно остаётся закрытым.
- Сервис: при успешном повторе старые `BillingRunIssue` очищаются, текущая блокировка заменяет прежнюю ровно одной причиной, а `no_entries` не сохраняется и не выдаётся как блокирующая ошибка.
- Сервис: неизменяемая детализация счёта сохраняет `document_number`/`display_number` исходного документа; хранение получает подпись `Расчёт хранения за YYYY-MM`, а позднее сторно наследует номер исходного факта и выбирается только по месяцу самого сторно.
- Задача: существующее расписание `wms.billing_invoices_daily` в 02:30 по `Europe/Moscow` и вызов того же `form_invoice`, что использует ручной повтор, закреплены адресным тестом.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_invoice_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_api.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_tasks.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Миграции

Нет. Схема данных в этом атоме не менялась. Названная ревьюером коллизия уже устранена в текущей ветке последовательностью `20260822_09a -> 20260822_09b -> 20260822_09c`; адресный migration-тест проходит.

## Тесты

- `backend/tests/test_billing_invoice_service.py` — `unpriced`, неперсистентный `no_entries`, очистка старой причины, барьер двух операционных складов, публикация измеряемого и нулевого statement (`S-31-TC-006`, `S-31-TC-013`).
- `backend/tests/test_billing_invoice_api.py` — живые HTTP-ручки ledger/invoices: `date=YYYY-MM-01`, поиск и снимок `ПР-101`, два параллельных формирования одного счёта, повторная отмена, скрытие устранённых и неблокирующих причин (`S-31-TC-006`, `S-31-TC-013`, `S-31-TC-014`, `S-31-TC-015`).
- `backend/tests/test_billing_tasks.py` — ежедневное расписание 02:30 МСК.
- `backend/tests/test_marketplace_unload_completion.py::test_cancel_shipped_unload_records_one_reversal_http` — относящаяся к вердикту production-регрессия позднего сторно (`S-31-TC-016`).
- `backend/tests/test_billing_financial_core_migration.py` — единый migration head и порядок billing-ревизий.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/services/billing_invoice_service.py app/tasks/billing_tasks.py app/api/billing.py tests/test_billing_invoice_service.py tests/test_billing_invoice_api.py tests/test_billing_tasks.py tests/test_billing_financial_core_migration.py tests/test_marketplace_unload_completion.py` — PASS: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/services/billing_invoice_service.py app/tasks/billing_tasks.py app/api/billing.py` — PASS: `Success: no issues found in 3 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_billing_invoice_service.py tests/test_billing_invoice_api.py tests/test_billing_tasks.py tests/test_billing_financial_core_migration.py tests/test_marketplace_unload_completion.py::test_cancel_shipped_unload_records_one_reversal_http` — PASS: `11 passed, 2 warnings in 3.97s`; предупреждения только Alembic `path_separator` deprecation.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && git diff --check` — PASS, вывода нет.
- `python3 scripts/ci/back_guard.py` — не применим: новый маршрут не добавлялся, исправлены существующие ручки.
- `python3 scripts/ci/check_migrations.py` — не применим: миграция не добавлялась и не менялась.
- Полный backend `pytest`, `ruff check .` и `mypy .` не запускались согласно ограничению атомарной проверки.

## Не реализовано

- Клик из номера начисления в существующий документ относится к frontend-находке 2 и не входит в роль `backend-dev`; backend теперь отдаёт стабильный человекочитаемый номер, необходимый экрану.
- Исправление frontend-кода `storage` -> `storage_liter_day` и e2e-моков относится к находкам 3 и 8 вне файлов backend-атома и не выполнялось.
- Production-путь позднего сторно не переписывался: он уже подключён предыдущим атомом 7 через отмену финальной marketplace-отгрузки и повторно подтверждён целевым HTTP-тестом `S-31-TC-016`.

## Блокеры

- Git-сохранение недоступно из-за прав среды: адресная команда `git add backend/app/api/billing.py backend/app/services/billing_invoice_service.py backend/tests/test_billing_invoice_service.py backend/tests/test_billing_invoice_api.py backend/tests/test_billing_tasks.py night/volna-9-recovery/cards/09-billing/DEV.md && git commit -m "fix(billing): harden immutable invoice formation"` завершилась `fatal: Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock': Operation not permitted`. Изменения находятся в постоянном зарегистрированном worktree, но не добавлены в индекс и не сохранены Git-коммитом; проверенного SHA нет. Чужое изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/JOURNAL.md` не затрагивалось и не включалось в попытку коммита.

## Находки

- В текущей ветке ещё нет моделей `StorageStatement`, `StorageMeasurement` и признака `Warehouse.is_operational` межкарточного результата 08-B. Сервис подготовлен к их обязательной последующей интеграции и до неё при действующем storage-тарифе закрывает выпуск счёта, а не создаёт неполный документ.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.
