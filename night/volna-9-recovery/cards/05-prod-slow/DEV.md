# Backend dev · 05-prod-slow · переделка атома 2

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет.
- Сервис планирования WB: задания `new` равномерно распределяются по 180 секундам, задания `reconcile` — по 3600 секундам, поэтому один Beat-тик больше не создаёт одновременный сетевой залп по всем продавцам.
- Исполнение WB: обе seller-задачи направлены в отдельную очередь `wb_sync`; production-worker этой очереди ограничен двумя параллельными слотами.
- Существующий single-flight по `(seller_id, sync_kind)` и отсутствие `wb_seller_lock` на время HTTP-чтения сохранены и повторно проверены; `new` и `reconcile` не блокируют друг друга.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/tasks/background_jobs.py` — общий равномерный диспетчер seller-задач и отдельные интервалы 180/3600 секунд.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/celery_app.py` — маршрутизация `wms.wb_orders_new` и `wms.wb_orders_reconcile` в очередь `wb_sync`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_wb_marketplace_orders_service.py` — проверки равномерного запуска, маршрутизации и production concurrency, а также существующих расписаний и single-flight.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/docker-compose.prod.yml` — отдельный `wb_sync_worker` с очередью `wb_sync` и `--concurrency=2` по прямой находке ревью №4.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md` — отчёт этого атомарного прохода.

## Миграции

Нет.

## Тесты

- Добавлен `test_wb_order_dispatch_spreads_each_kind_across_its_interval`: три продавца получают countdown `0/60/120` секунд для `new` и `0/1200/2400` секунд для `reconcile`.
- Расширен `test_wb_order_schedule_and_single_flight_are_per_kind`: подтверждает Beat-периоды 180/3600 секунд и маршрутизацию обоих видов в `wb_sync`.
- Добавлен `test_wb_order_sync_queue_has_two_worker_slots_in_production`: production-конфигурация закрепляет `--queues=wb_sync` и `--concurrency=2`.
- Повторно пройдены проверки раздельных задач, single-flight по `(seller_id, sync_kind)`, параллельности разных видов и отсутствия seller-wide lock при HTTP-чтении.
- Отдельно пройдены три названных ревьюером регрессии ручной синхронизации: переход подтверждённого заказа, привязка WB-поставки и освобождение резерва отменённого заказа.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && ruff check app/tasks/background_jobs.py app/celery_app.py tests/test_wb_marketplace_orders_service.py` — PASS, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && mypy app/tasks/background_jobs.py app/celery_app.py` — изменённые модули чисты; команда завершилась FAIL из-за четырёх ранее существовавших ошибок в импортируемых `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/wildberries_credentials_service.py`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/fbs_stock_sync_service.py` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/fbs_warehouse_binding_service.py`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && mypy --follow-imports=skip app/tasks/background_jobs.py app/celery_app.py` — PASS, `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && pytest -q tests/test_wb_marketplace_orders_service.py` — PASS, `18 passed in 6.57s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && pytest -q tests/test_fbs_orders_intake.py::test_fbs_order_status_sync_supplier_confirm_moves_new_to_external_processing tests/test_fbs_orders_intake.py::test_fbs_order_status_sync_links_external_wb_supply tests/test_fbs_orders_intake.py::test_fbs_order_status_sync_releases_reserve_on_cancel` — PASS, `3 passed in 3.82s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && python3 -c 'from pathlib import Path; import yaml; data=yaml.safe_load(Path("docker-compose.prod.yml").read_text()); assert data["services"]["wb_sync_worker"]["command"][-2:] == ["--queues=wb_sync", "--concurrency=2"]'` — PASS.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && git diff --check` — PASS.
- `back_guard.py` не запускался: атом не добавляет и не меняет API-роуты.
- `check_migrations.py` не запускался: атом не добавляет миграций.

## Не реализовано

- Находки ревью №1–2 и №5–10 относятся к UI, печатному контуру и хранению PDF, то есть находятся вне файлов и backend-слоя атома 2; они не изменялись.
- Общий backend-регресс, `ruff check .` и `mypy .` не запускались: инструкция роли запрещает их на атомарном шаге.
- Git-коммит и публикация ветки не выполнены: среда запретила создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock`, поэтому commit SHA отсутствует, а изменения пока восстанавливаются только из этой рабочей копии.
- Боевой прод, живой кабинет Wildberries, секреты, ключи, токены и `.env` не читались и не затрагивались.

## Блокеры

- Функциональных блокеров в границах атома нет.
- Сохранение результата в Git заблокировано правами файловой песочницы: `fatal: Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock': Operation not permitted`.
