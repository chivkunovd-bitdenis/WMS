# 08-storage · backend-dev · атом 1

## Что реализовано

- `POST /operations/storage/tariffs` — общая и индивидуальная ставки проходят одинаковое денежное округление до двух знаков ещё при валидации тела; значение `0.001`, превращающееся в `0.00`, получает `422` до вызова записи и пересчёта.
- `create_storage_tariff` — внутренние вызовы защищены той же нормализацией `ROUND_HALF_UP`: ставка сначала приводится к точности `0.01`, затем нулевая отклоняется до чтения или изменения БД; положительная после округления ставка сохраняется уже в нормализованном виде.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_tariff_api.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Миграции

Нет: схема БД не менялась.

## Тесты

- Расширен `test_tariff_amount_must_be_positive`: для общей и индивидуальной ставки добавлено `0.001`; проверяются `422`, точное расположение ошибки, отсутствие версии тарифа и отсутствие запуска пересчёта черновиков.
- Добавлен `test_storage_tariff_service_rejects_amount_rounding_to_zero`: прямой вызов сервиса с общей или индивидуальной ставкой `0.001` завершается до чтения, `add`, `flush`, `commit` и пересчёта.
- Добавлен `test_tariff_amount_rounding_that_stays_positive_is_saved`: обе ставки `0.005` округляются до `0.01`, возвращаются API и сохраняются как `0.01`.

## Гейты

Финальные целевые проверки:

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && python3 -m ruff check app/api/storage.py app/services/storage_statement_service.py tests/test_storage_tariff_api.py` — успешно, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && python3 -m mypy --follow-imports=silent app/api/storage.py app/services/storage_statement_service.py` — успешно, `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && python3 -m pytest -q tests/test_storage_tariff_api.py` — успешно, `16 passed in 16.84s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && python3 -m pytest -q tests/test_storage_tariff_api.py -k 'tariff_amount'` — промежуточная целевая проверка успешно, `7 passed, 9 deselected in 7.56s`.

Промежуточные красные прогоны, после которых исправлен только новый тестовый код:

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && python3 -m ruff check app/api/storage.py app/services/storage_statement_service.py tests/test_storage_tariff_api.py` — сначала `RUF043` на несырое регулярное выражение; выражение заменено на raw string, финальный повтор зелёный.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && python3 -m pytest -q tests/test_storage_tariff_api.py` — сначала `2 failed, 14 passed`: новый сервисный тест обращался к SQLite после закрытия API-фикстуры; запрос устранён, отсутствие побочных действий теперь проверяется через session mock, финальный повтор зелёный.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && python3 -m mypy app/api/storage.py app/services/storage_statement_service.py` — завершился с четырьмя существующими ошибками в импортируемых, но не затронутых файлах `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; финальная целевая проверка с `--follow-imports=silent` проверила изменённые модули без этих внешних ошибок и прошла.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && python3 -m mypy --follow-imports=skip app/api/storage.py app/services/storage_statement_service.py` — непригодный диагностический вариант: пропущенные типы Pydantic/FastAPI дали 13 ложных ошибок `Any`; заменён на прошедший `--follow-imports=silent`.

`python3 scripts/ci/back_guard.py` не запускался: атом не добавляет роут. `python3 scripts/ci/check_migrations.py` не запускался: миграций нет.

Попытка сохранить атом в Git:

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add -- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_tariff_api.py /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — не выполнено: `fatal: Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock': Operation not permitted`. Индекс не изменён, commit SHA не создан.

## Не реализовано

- Фичи 2 и 3 из `FEATURES.md` не реализованы: они относятся к frontend и документации, а текущий атом и роль ограничены backend-фичей 1.
- Модель и миграции не менялись: точность `Numeric(14, 2)` уже существует, атом закрывает проверку до сохранения.

## Находки

Нет. Секреты, ключи, токены, `.env`, кабинеты учётных данных, production и живой кабинет Wildberries не открывались и не использовались.

## Блокеры

- Реализация и целевые гейты завершены локально, но песочница запрещает запись в `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1`, поэтому сохранить атом обычным коммитом текущей ветки из этой сессии невозможно. Изменения остаются незакоммиченными в рабочей копии; риск — их нельзя восстановить по SHA до запуска `git add` и `git commit` в среде с правом записи в Git-метаданные.
