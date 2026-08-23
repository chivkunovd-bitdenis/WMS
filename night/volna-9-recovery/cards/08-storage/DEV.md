# DEV · 08-storage · backend-dev · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py` — доменная ошибка `tariff_amount_must_be_positive` сопоставлена с HTTP 422; в схемах основная и индивидуальная ставки остаются строго положительными.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py` — `create_storage_tariff()` теперь сам отклоняет нулевую и отрицательную основную или индивидуальную ставку до создания ORM-объектов; проверка обеих дат относительно сегодняшнего дня по Москве сохранена в одном доменном сервисе.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_tariff_api.py` — проверки расширены на обе части атомарного запроса, доказывают отсутствие версий тарифа после 422 и используют динамические московские даты вместо скоро устаревающих констант 2026 года.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — артефакт backend-dev по текущему атому.

## Что реализовано

- Эндпоинт `POST /operations/storage/tariffs`: основная ставка и необязательное исключение селлера принимаются только со строго положительной ставкой и датой не раньше текущего дня по МСК; отказ возвращает 422 до любой записи.
- Сервис `create_storage_tariff()`: дублирует инвариант положительной ставки на доменном слое, чтобы не-HTTP вызов не мог обойти схему запроса.

## Миграции

Нет.

## Тесты

- `test_tariff_amount_must_be_positive`: нуль и отрицательная ставка отклоняются отдельно для склада и исключения селлера; проверены HTTP 422, точный путь ошибочного поля и нулевое число созданных версий.
- `test_tariff_valid_from_cannot_be_in_the_past`: вчерашняя дата по Москве отклоняется отдельно для основной ставки и исключения; проверены HTTP 422, `tariff_valid_from_in_past` и отсутствие версий.
- `test_admin_creates_warehouse_tariff` и `test_admin_creates_tariff_with_seller_exception`: основная ставка с датой «сегодня» и атомарная пара с будущими датами создаются с HTTP 201.
- Относящиеся к ручке регрессии атомарности и ролевого доступа также остались зелёными.

## Гейты

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/api/storage.py app/services/storage_statement_service.py tests/test_storage_tariff_api.py
```

Результат: `All checks passed!`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy app/api/storage.py app/services/storage_statement_service.py
```

Результат: целевые модули проверены, но команда завершилась с кодом 1 из-за четырёх уже существующих ошибок в трёх импортируемых, но не затронутых атомом файлах: `app/services/wildberries_credentials_service.py:167`, `app/services/fbs_stock_sync_service.py:617`, `app/services/fbs_warehouse_binding_service.py:23,291`. В двух целевых модулях ошибок не выведено.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy --follow-imports=silent app/api/storage.py app/services/storage_statement_service.py
```

Результат: `Success: no issues found in 2 source files`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_tariff_api.py
```

Финальный результат: `11 passed in 11.00s`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check -- backend/app/api/storage.py backend/app/services/storage_statement_service.py backend/tests/test_storage_tariff_api.py
```

Результат: exit 0, ошибок пробелов нет.

`python3 scripts/ci/back_guard.py` не запускался: в этом rework-атоме новый роут не добавлялся. `python3 scripts/ci/check_migrations.py` не запускался: миграций нет.

Первая диагностическая попытка `./.venv/bin/pytest -q tests/test_storage_tariff_api.py` не запустила тесты, потому что в `backend/` нет `.venv`; целевой прогон затем успешно выполнен доступным `pytest`.

## Не реализовано

- Атомы 2–6 из `FEATURES.md` не выполнялись.
- Находки 1, 3 и 5 из `REVIEW.md` относятся к следующим backend/frontend-атомам и не менялись в этом шаге.
- Frontend, миграции, внешние API, production и живой кабинет Wildberries не затрагивались.

## Находки

Нет. Секреты, ключи, токены, `.env`, кабинеты учётных данных и production не читались и не использовались.

## Блокеры

Нет на уровне backend-реализации и целевых тестов.
