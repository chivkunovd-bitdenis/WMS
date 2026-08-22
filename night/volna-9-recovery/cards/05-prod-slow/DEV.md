# DEV · 05-prod-slow · атом 2

## Изменённые файлы

В рамках повторной проверки атома изменений в исходном коде не потребовалось: реализация уже содержит независимые задания `wms.wb_orders_new` и `wms.wb_orders_reconcile`, Beat-периоды 180 и 3600 секунд, а также single-flight по `(seller_id, sync_kind)` без `wb_seller_lock` на HTTP-чтении.

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/fbs_autopoll_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/tasks/background_jobs.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/celery_app.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_wb_marketplace_orders_service.py`

## Гейты

- ruff: адресные файлы атома — PASS; полный `ruff check .` — FAIL на 80 pre-existing ошибках в несвязанных файлах.
- mypy: FAIL на 4 pre-existing ошибках в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; в файлах атома ошибок нет.
- pytest: адресный `tests/test_wb_marketplace_orders_service.py` — 12 passed; полный прогон остановлен вручную после 46% (до остановки были failures в pre-existing тестах `test_fbs_*`).
- back_guard.py: не запущен — файл отсутствует в данной рабочей копии (`scripts/ci/back_guard.py` не найден).
- check_migrations.py: не запущен — файл отсутствует в данной рабочей копии (`scripts/ci/check_migrations.py` не найден).

## Не реализовано

- Находки ревью №1 и №2–11 относятся к Docker, print-job, UI, модели фоновых job и экранным тестам; они не входят в файлы и backend-слой атома 2 и здесь не менялись.
- Backend-находок, требующих исправления в пределах атома 2, нет.

## Блокеры

Нет блокеров по реализации атома. Полные ruff/mypy имеют чужие pre-existing ошибки; обязательные CI-скрипты отсутствуют в рабочей копии.

Сохранение commit невозможно из-за ограничения прав на общий git worktree: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock`.
