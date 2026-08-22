# Backend-dev отчёт · 05-prod-slow · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/fbs_autopoll_service.py` — добавлены отдельные job-обёртки `new` и `reconcile` с single-flight по `(seller_id, sync_kind)`; во время сетевого чтения они не используют общий `wb_seller_lock`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/tasks/background_jobs.py` — добавлены Celery-задачи и dispatch-задачи, создающие независимый запуск для каждого продавца.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/celery_app.py` — Beat запускает `new` каждые 180 секунд и `reconcile` каждые 3600 секунд.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_wb_marketplace_orders_service.py` — проверки периодов и независимого single-flight для обоих контуров.

## Миграции

Нет.

## Тесты

- `test_wb_order_schedule_and_single_flight_are_per_kind` — проверяет интервалы 180 секунд и 60 минут.
- `test_wb_order_flights_allow_new_and_reconcile_together` — проверяет параллельность разных видов и отказ повторного запуска того же вида.
- Существующие тесты сервиса подтверждают, что `new` не выполняет полный обход, а `reconcile` проходит курсоры и откатывает незавершённый проход.

## Гейты

- `ruff check .` — BLOCKED: 85 предсуществующих ошибок в полном backend-проходе; `ruff check` затронутых файлов — PASS.
- `mypy .` — BLOCKED: 20 предсуществующих ошибок типизации в соседних backend-модулях; после исправления аннотации этого атома ошибок в `fbs_autopoll_service.py` нет.
- `pytest` — PASS: целевой файл `backend/tests/test_wb_marketplace_orders_service.py`.
- `python3 scripts/ci/back_guard.py` — NOT RUN: файл отсутствует в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — NOT RUN: файл отсутствует в этой рабочей копии.

## Не реализовано

- Внешние API, модели, миграции и UI не менялись: они не входят в атом 2.
- Старый агрегированный `fbs_orders_autopoll` не переписывался; новые независимые Beat-контуры работают через отдельные задания по продавцу.

## Находки

- Вне кода backend присутствует несвязанное изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/JOURNAL.md`; в работу атома не включалось.
- Commit не создан: Git не может записать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock` из-за ограничений доступа рабочей среды.
