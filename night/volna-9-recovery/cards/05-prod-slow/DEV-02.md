# Backend dev · 05-prod-slow · атом 2 · переделка по ревью

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет.
- Сервис `seller_sync_flight`: single-flight остаётся раздельным по `(seller_id, sync_kind)`, поэтому повтор одного вида блокируется, а `new` и `reconcile` одного продавца могут выполняться одновременно без общего `wb_seller_lock` во время HTTP-чтения.
- Сервисы `sync_new_orders_for_seller_job` и `reconcile_orders_for_seller_job`: сохранены независимые задания продавца для лёгкого импорта новых заказов и полной сверки.
- Сервис `_debit_stock_pool_once`: строка `FbsBindingStockPool` читается с `FOR UPDATE`, поэтому параллельные `new` и `reconcile` последовательно списывают два разных заказа из одного пула и не теряют изменение количества.
- Celery Beat и фоновые задания: `new` запускается раз в 180 секунд, `reconcile` — раз в 3600 секунд; задания распределяются по продавцам внутри своего интервала и направляются в отдельную очередь `wb_sync`.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/wb_marketplace_orders_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_wb_marketplace_orders_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

Первые два файла уже сохранены в текущем `HEAD` коммитом `ab19c4844831dd968e484a09d73a9334300a189b`; этот проход повторно проверил реализацию и восстановил обязательный артефакт, удалённый оркестратором перед запуском роли.

## Миграции

Нет.

## Тесты

- `test_wb_order_schedule_and_single_flight_are_per_kind` — подтверждает периоды 180/3600 секунд и отдельную очередь обоих контуров.
- `test_wb_order_tasks_invoke_new_and_reconcile_independently` — вызывает оба фоновых задания отдельно.
- `test_wb_order_flights_allow_new_and_reconcile_together` и `test_wb_order_flight_uses_distinct_postgres_keys_per_kind` — подтверждают single-flight по `(seller_id, sync_kind)`: одинаковый вид не дублируется, разные виды не блокируют друг друга.
- `test_wb_order_jobs_do_not_take_seller_wide_lock_during_http_read` — подтверждает отсутствие общего `wb_seller_lock` во время сетевого чтения.
- `test_new_and_reconcile_serialize_different_order_debits_on_one_pool` — регрессия на находку ревью №1: два разных заказа из параллельных контуров создают две строки `FbsStockPoolDebit` и уменьшают общий пул с 10 до 8; тест отдельно требует наличие `FOR UPDATE`.
- Весь профильный файл повторно проверяет лёгкий `new`, полный курсорный `reconcile`, идемпотентность импорта и связанные регрессии WB-заказов.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && ruff check app/services/fbs_autopoll_service.py app/services/wb_marketplace_orders_service.py app/tasks/background_jobs.py app/celery_app.py tests/test_wb_marketplace_orders_service.py` — PASS, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && mypy --follow-imports=skip app/services/fbs_autopoll_service.py app/services/wb_marketplace_orders_service.py app/tasks/background_jobs.py app/celery_app.py` — FAIL на 14 ранее существующих ошибках `no-any-return`: 12 в `wb_marketplace_orders_service.py` на строках 184, 186, 188, 190, 192, 193, 246, 318, 548, 1160, 1444, 1451 и 2 в `fbs_autopoll_service.py` на строках 55, 370; исправленная функция `_debit_stock_pool_once` и модули задач/расписания в диагностике отсутствуют.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && pytest -q tests/test_wb_marketplace_orders_service.py` — PASS, `19 passed in 4.58s`.
- `python3 scripts/ci/back_guard.py` не запускался: атом не добавляет и не меняет роуты.
- `python3 scripts/ci/check_migrations.py` не запускался: атом не добавляет миграцию.
- Полный `pytest`, `ruff check .` и `mypy .` не запускались: атомарная инструкция прямо запрещает общий backend-регресс на этом шаге.

## Не реализовано

- Находки ревью №2–6 относятся к фоновой печати, frontend и документации, поэтому не входят в backend-слой этого атома и не изменялись.
- Старые 14 ошибок `no-any-return` не исправлялись: они не относятся к конкурентному списанию, расписанию или single-flight этого атома.
- В `CONTRACT.md` нет отдельного раздела «API и данные»; работа выполнена по явно заданному владельцем атому из `FEATURES.md` и относящейся к нему находке №1 из `REVIEW.md`, без расширения поведения.

## Блокеры

Нет функциональных блокеров в границах атома.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
