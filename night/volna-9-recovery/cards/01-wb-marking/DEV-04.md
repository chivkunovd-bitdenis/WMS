# DEV · 01-wb-marking · backend-dev · feature 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_autopoll_service.py` — фоновая сверка уникальных заказов активных собираемых поставок режет ID на последовательные batch-пачки до 100, продолжает цикл после ошибки пачки и сопоставляет ответ с заказом по `order_id`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py` — применение принимает заранее загруженный batch-ответ, сохраняя одиночный ручной путь с пачкой из одного ID.

## Миграции

Нет.

## Тесты

- Существующие backend-тесты маркировки и автополлера покрывают batch-вызовы, ограничение размера пачки, продолжение после локальной ошибки и применение ответа к конкретному заказу.

## Гейты

- `ruff` — PASS для целевых сервисов и тестов.
- `mypy` — PASS для целевых файлов; полный backend не проходит из-за 4 существующих ошибок в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`, вне этой фичи.
- `pytest` — PASS: 20 тестов в `tests/test_fbs_marking.py` и `tests/test_fbs_autopoll.py`.
- `back_guard.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` отсутствует.
- `check_migrations.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Новых API-эндпоинтов и миграций нет; расписание и ручной путь не менялись.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.
