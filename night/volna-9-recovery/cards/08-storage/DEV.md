# DEV · 08-storage · атом 1 · переделка по REVIEW

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py` — для `POST /operations/storage/tariffs` добавлена серверная проверка строго положительной ставки и точное сопоставление доменных ошибок HTTP-статусам; `GET /operations/storage/statements` теперь заново рассчитывает видимую предварительную сумму открытого черновика по актуальным датированным тарифам, не публикуя финансовые строки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py` — создание тарифа запрещает прошедшую по Москве дату, чужой tenant, неоперационный склад и чужого селлера; добавлен расчёт тарифного превью открытого черновика, ограниченный фактически прошедшей частью текущего месяца.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_tariff_api.py` — к исходным сценариям добавлены проверки нулевой/отрицательной ставки, прошедшей даты, tenant-границ, служебного склада и обновления предварительной суммы после создания новой версии тарифа.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — отчёт повторной backend-разработки атома.

## Что реализовано

- Эндпоинт `POST /operations/storage/tariffs`: атомарно создаёт общую ставку склада и необязательное исключение селлера, принимает только положительные суммы и даты не раньше текущего московского дня, проверяет tenant и операционный статус склада.
- Эндпоинт `GET /operations/storage/statements`: для незакрытых документов возвращает заново рассчитанные `rate_snapshot`, `amount` и итоги по действующим версиям тарифа; ledger (неизменяемый журнал начислений) до фиксации не создаётся.
- Сервис `create_storage_tariff()`: централизует инварианты даты, tenant, склада и селлера до обеих вставок.
- Сервис `get_storage_draft_pricing()`: рассчитывает предварительную сумму открытого statement (месячного расчёта хранения) без изменения зафиксированных документов.

## Миграции

Нет.

## Тесты

- Сохранены исходные тесты создания общей ставки, общей ставки с исключением и полного отката при конфликте второй вставки, а также запрета для `fulfillment_staff` с правом `inventory`.
- Добавлены тесты HTTP 422 для нулевой/отрицательной ставки и прошедшей по Москве даты.
- Добавлен тест HTTP 404/422 для чужого склада, чужого селлера и неоперационного склада с доказательством отсутствия записей тарифа.
- Добавлен сценарий повторной загрузки открытого черновика после POST: предварительная сумма меняется по новой версии тарифа.

## Гейты

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/api/storage.py app/services/storage_statement_service.py tests/test_storage_tariff_api.py
```

Результат: `All checks passed!`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy --follow-imports=silent app/api/storage.py app/services/storage_statement_service.py
```

Результат: `Success: no issues found in 2 source files`.

Обычная целевая команда `mypy app/api/storage.py app/services/storage_statement_service.py` также запускалась и остановилась на четырёх уже существующих ошибках в импортируемых несвязанных модулях `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; в двух изменённых модулях ошибок не показала. Режим `--follow-imports=silent` проверил целевые модули с типами зависимостей, но не вывел ошибки самих импортированных модулей.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_tariff_api.py
```

Результат: `8 passed in 8.21s`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_tariff_api.py tests/test_storage_statement_service.py
```

Результат относящейся к изменённому расчёту регрессии: `17 passed in 10.48s`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ci/back_guard.py
```

Результат: скрипт отсутствует в этой рабочей копии (`scripts/ci/back_guard.py: No such file or directory`). Новый маршрут относительно исходного атома покрыт целевым API-тестом; в текущем ремонтном diff новый маршрут не добавлялся. `check_migrations.py` не применим, потому что миграций нет.

## Не реализовано

- Находка 5 из `REVIEW.md` относится к `frontend/tests-e2e/storage.spec.ts` и живому Playwright-сценарию. Она намеренно не исправлялась: роль этого шага — только `backend-dev`, а разрешённый атом ограничен backend-файлами и их тестом.
- Следующие атомы из `FEATURES.md` не выполнялись.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и production не открывались и не использовались.
- Команда сохранения `git add backend/app/api/storage.py backend/app/services/storage_statement_service.py backend/tests/test_storage_tariff_api.py night/volna-9-recovery/cards/08-storage/DEV.md && git diff --cached --check && git status --short && git commit -m "fix(storage): validate and reprice tariffs"` не дошла до индексации: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`). Чужие изменения `night/volna-9-recovery/JOURNAL.md` и `night/volna-9-recovery/cards/08-storage/REVIEW.md` не индексировались.

## Блокеры

- Среда запрещает запись в общий служебный каталог Git зарегистрированного worktree, поэтому отдельный commit этого ремонта создать невозможно. Реализация и отчёт находятся только в рабочем дереве и требуют сохранения из процесса с правом записи в `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1`.
