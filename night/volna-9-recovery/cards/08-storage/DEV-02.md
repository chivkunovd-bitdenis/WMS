# DEV · 08-storage · backend-dev · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_tariff_api.py` — тест границ тарифа расширен на чужой и отсутствующий склад, чужого и отсутствующего селлера, служебный склад, пустую транзакцию после каждого отказа и успешную пару своего операционного склада с селлером.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — отчёт backend-dev по атому 2.

## Что реализовано

- Эндпоинт `POST /operations/storage/tariffs`: целевой API-тест доказывает отказ `404 warehouse_not_found` для чужого или отсутствующего склада, `404 seller_not_found` для чужого или отсутствующего селлера и `422 warehouse_not_operational` для собственного служебного склада; ни один отказ не создаёт финансовую строку.
- Сервис `create_storage_tariff()`: в текущем коде уже выполняет обе проверки до создания `BillingTariffVersion` — загружает склад и селлера только вместе с `tenant_id` администратора и отдельно требует `Warehouse.is_operational`; дополнительная правка сервиса не понадобилась.

## Миграции

Нет.

## Тесты

- Расширен `test_tariff_scope_must_belong_to_tenant_and_operational_warehouse`: он создаёт два tenant, собственные операционный и служебный склады, чужой склад, собственного и чужого селлеров.
- Пять парных запросов проверяют чужой и отсутствующий склад, служебный склад, чужого и отсутствующего селлера. После каждого отказа число `BillingTariffVersion` текущего tenant остаётся нулевым.
- Завершающий запрос с собственными операционным складом и селлером получает `201` и сохраняет ровно две версии: общую ставку склада и исключение селлера на том же складе.

## Гейты

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/services/storage_statement_service.py tests/test_storage_tariff_api.py
```

Результат: `All checks passed!`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy --follow-imports=silent app/services/storage_statement_service.py tests/test_storage_tariff_api.py
```

Результат: `Success: no issues found in 2 source files`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_tariff_api.py
```

Результат: `11 passed in 9.79s`.

Предварительно отдельно проверен изменённый сценарий:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_tariff_api.py::test_tariff_scope_must_belong_to_tenant_and_operational_warehouse
```

Результат последнего одиночного прогона: `1 passed in 1.23s`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check -- backend/tests/test_storage_tariff_api.py night/volna-9-recovery/cards/08-storage/DEV.md
```

Результат: exit 0, ошибок пробелов нет.

`python3 scripts/ci/back_guard.py` не запускался: атом не добавляет маршрут. `python3 scripts/ci/check_migrations.py` не запускался: миграций нет.

Попытка сохранить атом отдельным коммитом:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add -- backend/tests/test_storage_tariff_api.py night/volna-9-recovery/cards/08-storage/DEV.md && git commit -m "test(storage): cover tariff tenant scope"
```

Результат: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`: `Operation not permitted`. Файлы не попали в индекс и остаются только локальным diff рабочей копии; `night/volna-9-recovery/JOURNAL.md` не затрагивался и не включался.

## Не реализовано

- Атомы 3–6 из `FEATURES.md` не выполнялись.
- Находки 1, 2, 4 и 5 из `REVIEW.md` не относятся к файлам и границам атома 2 и не менялись.
- Frontend, пересчёт черновиков, модели, миграции, внешние API, production и живой кабинет Wildberries не затрагивались.
- В `storage_statement_service.py` не внесён искусственный diff: требуемая проверка tenant и `is_operational` уже присутствует в текущем HEAD и полностью покрыта расширенным тестом.

## Находки

Нет. Секреты, ключи, токены, `.env`, кабинеты учётных данных и production не читались и не использовались.

## Блокеры

На уровне backend-кода и целевых тестов блокеров нет. Сохранение отдельного commit заблокировано правами текущей среды на общий Git-каталог за пределами разрешённой рабочей копии; commit SHA не создан.
