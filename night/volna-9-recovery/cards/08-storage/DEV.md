# DEV · 08-storage · атом 7

## Что реализовано

- `GET /operations/storage/statements` теперь видит общий тариф `storage_liter_day`, а для зафиксированных документов возвращает неизменяемые суммы и строки из `BillingLedgerEntry`.
- `POST /operations/storage/statements/{statement_id}/fix` атомарно фиксирует только чистый завершённый месяц, публикует один общий ledger-набор и идемпотентно отвечает на конкурентный повтор.
- `GET /operations/storage/statements/{statement_id}/print` повторно отдаёт тот же состав SKU, снимок ставки, сумму и дату фиксации после последующих обмеров.
- `storage_statement_service` применяет общую или персональную версию тарифа только в её календарном интервале; ставка, начавшаяся или сменившаяся внутри месяца, не применяется задним числом.
- Подключён опубликованный фундамент 09-A: `BillingTariffVersion` и `BillingLedgerEntry` с `service_code='storage_liter_day'`, `unit='liter_day'`, `source_type='storage_measurement'`; отдельные storage-тарифы и storage-начисления не создавались.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_statement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/billing.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/__init__.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_billing_models.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0094_billing_financial_core.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0094_inventory_movement_reporting_dimensions.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Миграции

- `20260821_0094` — существующей добавляющей миграции измерений движения возвращён уникальный revision и корректный родитель `20260821_0093`; DDL не менялся.
- `20260822_0094` — добавляет общий финансовый фундамент 09-A: профили, версии тарифов и неизменяемый billing ledger. Единица `liter_day` включена в общие ограничения.
- Цепочка линейна и заканчивается единственной головой `20260822_0097`.

## Тесты

- Добавлена проверка тарифа, начавшегося внутри месяца: оплачивается только период после `valid_from`.
- Добавлена проверка смены ставки внутри месяца и приоритета персональной ставки селлера над общей.
- Добавлен API-тест двух одновременных фиксаций: оба запроса успешны, ledger-строка исходного измерения одна.
- Добавлена проверка неизменяемой повторной печати после нового ручного обмера.
- Добавлены проверки запрета проблемного и текущего черновика, нулевого документа с одной нулевой ledger-строкой и понятного `tariff_not_found`.
- Подключены тесты ограничений общих billing-моделей 09-A.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/services/storage_statement_service.py app/api/storage.py app/models/billing.py app/models/__init__.py tests/test_storage_statement_service.py tests/test_storage_measurement_service.py tests/test_billing_models.py` — успешно, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy app/services/storage_statement_service.py app/models/billing.py` — успешно, `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy --follow-imports=skip --allow-subclassing-any --allow-untyped-decorators app/api/storage.py` — успешно, `Success: no issues found in 1 source file`; ограничение импортов изолирует ранее существующие ошибки соседних модулей.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_statement_service.py tests/test_storage_measurement_service.py tests/test_billing_models.py` — успешно, `21 passed in 4.37s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && alembic heads` — успешно, единственная голова `20260822_0097 (head)`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ci/check_migrations.py` — не запущен: файла `scripts/ci/check_migrations.py` в этой рабочей копии нет. Миграционная цепочка дополнительно проверена командой `alembic heads` и компиляцией изменённых миграций.
- `back_guard.py` неприменим: новый маршрут в атоме не добавлялся.
- `git diff --check` — успешно, ошибок пробелов нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add backend/alembic/versions/20260822_0094_inventory_movement_reporting_dimensions.py backend/alembic/versions/20260822_0094_billing_financial_core.py backend/app/api/storage.py backend/app/models/__init__.py backend/app/models/billing.py backend/app/services/storage_statement_service.py backend/tests/test_billing_models.py backend/tests/test_storage_statement_service.py night/volna-9-recovery/cards/08-storage/DEV.md && git diff --cached --check && git commit -m 'night(08-storage): repair atom 7 statement fixation'` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`, `Operation not permitted`.

## Не реализовано

- API создания и версионирования тарифа не дублировался в storage: он принадлежит отдельному атому 09-billing/4. Этот атом использует его опубликованные модели и читает сохранённые версии.
- UI диалога тарифа и A4-вёрстка не менялись: это не роль `backend-dev` и не файлы атома 7; API возвращает зафиксированное представление для существующего предпросмотра.
- Находки ревью по writer движений, фильтрации WB-наблюдений, дедупликации ручного обмера и frontend-файлам относятся к другим атомам и в этом атоме не менялись.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не использовались.
- Штатные CI-скрипты `scripts/ci/check_migrations.py` и `scripts/ci/back_guard.py` отсутствуют в текущем checkout; для добавленной миграции выполнены доступные локальные проверки Alembic.

## Блокеры

- Реализация и целевые проверки завершены локально, но результат не сохранён Git-коммитом: sandbox разрешает запись в рабочую копию, но запрещает запись в служебный каталог зарегистрированного worktree. До коммита атом нельзя считать опубликованным или восстановимым по SHA.
