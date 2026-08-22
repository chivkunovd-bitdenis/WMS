# Фича 1

# Backend dev · 05-prod-slow · атом 1 · rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/wb_marketplace_orders_service.py` — восстановлен полный контракт существующего `sync_seller_orders`: ручная синхронизация снова импортирует новые задания, обходит полный список, обновляет статусы и после полного прохода связывает подтверждённые заказы с WB-поставками; раздельные контуры `sync_new_orders_for_seller` и `reconcile_orders_for_seller` сохранены.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_wb_marketplace_orders_service.py` — добавлена регрессия совместимости ручной синхронизации со статусной сверкой и привязкой поставок.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md` — записан отчёт атома.

## Что реализовано

- Эндпоинты: новых нет; существующий `POST /operations/fbs-orders/sync` через `sync_seller_orders` снова сохраняет прежний полный результат со `statuses_updated` и сводкой привязки WB-поставок.
- Сервис `sync_seller_orders`: восстановлены импорт `/orders/new`, курсорный полный обход, статусная сверка и привязка поставок; ошибка или цикл курсора не запускают статусную и supply-сверку после незавершённого прохода.
- Сервис `sync_new_orders_for_seller`: остаётся лёгким контуром и не вызывает постраничный полный список.
- Сервис `reconcile_orders_for_seller`: остаётся отдельным полным курсорным обходом и не помечает незавершённую сверку успешной.

## Миграции

Нет.

## Тесты

- `test_legacy_manual_sync_keeps_status_and_supply_reconciliation` — ручной legacy-вход вызывает новый импорт, полный список, обновление статусов и привязку поставок, сохраняя поля прежнего результата.
- `test_new_sync_does_not_fetch_paginated_orders` — лёгкий `new` не обращается к постраничному полному списку.
- `test_reconcile_walks_cursor_and_fails_incomplete_pass`, `test_reconcile_rejects_a_repeated_next_token`, `test_reconcile_walks_past_ten_pages_and_links_supplies` — полный обход до конца, безопасная ошибка/цикл курсора и отсутствие произвольного лимита страниц.
- Регрессии из ревью: `test_fbs_order_status_sync_supplier_confirm_moves_new_to_external_processing`, `test_fbs_order_status_sync_links_external_wb_supply`, `test_fbs_order_status_sync_releases_reserve_on_cancel`.

## Гейты

- `ruff check app/services/wb_marketplace_orders_service.py tests/test_wb_marketplace_orders_service.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend` — PASS, `All checks passed!`.
- `mypy app/services/wb_marketplace_orders_service.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend` — FAIL на четырёх существующих ошибках импортируемых соседних модулей: одна в `wildberries_credentials_service.py`, одна в `fbs_stock_sync_service.py`, две в `fbs_warehouse_binding_service.py`; изменённый `wb_marketplace_orders_service.py` в диагностике отсутствует.
- `pytest -q tests/test_wb_marketplace_orders_service.py tests/test_fbs_orders_intake.py::test_fbs_order_status_sync_supplier_confirm_moves_new_to_external_processing tests/test_fbs_orders_intake.py::test_fbs_order_status_sync_links_external_wb_supply tests/test_fbs_orders_intake.py::test_fbs_order_status_sync_releases_reserve_on_cancel` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend` — PASS, `19 passed in 14.87s`.
- `back_guard.py` не запускался: атом не добавляет роут.
- `check_migrations.py` не запускался: атом не добавляет миграцию.

## Не реализовано

- Остальные находки `REVIEW.md` не относятся к двум разрешённым backend-файлам атома 1 и не исправлялись.
- Полный backend-регресс, `ruff check .` и `mypy .` не запускались: роль требует выполнить их один раз после интеграции всех карточек, а на этом атоме разрешены только адресные проверки.

## Блокеры

- Продуктовых блокеров в границах атома нет.
- Публикация ветки в `origin` не выполнена: `git push -u origin night/volna-9-recovery/lane-2/05-prod-slow` завершился ошибкой `Could not resolve host: github.com` из-за недоступной сети среды. Локальный коммит создан и восстанавливаем из именованной ветки.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.

# Фича 2

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

# Фича 3

# Backend dev · 05-prod-slow · атом 3 · переделка по ревью

## Что реализовано

- Эндпоинты: новых и изменённых роутов нет; существующий запрос фоновой ленты получает исправленную семантику через сервис заданий.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/background_job_service.py`: одинаковый `marking_label_tape` возвращает тот же `done`-job, пока связанный PDF доступен; `pending/running` по-прежнему single-flight, `failed` допускает новый запуск, а истёкший или недоступный артефакт освобождает ключ для повторной сборки.
- Сервис очистки: после 12 часов удаляется только PDF и обнуляется `storage_path`; строка `FbsPrintAsset`, контрольная сумма и ссылка `BackgroundJob.result_json.asset_id` сохраняются для аудита.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/models/background_job.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/background_job_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/alembic/versions/20260822_0050_marking_label_tape_jobs.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_background_jobs.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

## Миграции

- `20260822_0050`: добавляющая миграция по-прежнему добавляет `background_jobs.idempotency_key` и `fbs_print_assets.expires_at`; частичный уникальный индекс переименован в `uq_background_jobs_reusable_idempotency` и охватывает `pending/running` для всех job, а `done` — только для `marking_label_tape`.

## Тесты

- `test_done_marking_job_is_reused_while_asset_is_available`: готовый доступный PDF возвращает тот же job и повторно не публикуется.
- `test_failed_marking_job_can_be_retried_with_same_idempotency_key`: ошибочный job не блокирует повтор.
- `test_expired_tape_cleanup_retains_audit_row_and_releases_request_key`: уборка удаляет бинарный файл один раз, сохраняет asset и `asset_id`, после чего тот же запрос может создать новый job.
- Сохранены прежние проверки состояний `pending/running/done/failed`, single-flight активного запроса, восстановления stale `running`, отсутствия PDF в `result_json` и отказа в выдаче после 12 часов.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && ruff check app/models/background_job.py app/models/fbs_print_asset.py app/services/background_job_service.py alembic/versions/20260822_0050_marking_label_tape_jobs.py tests/test_background_jobs.py tests/test_fbs_print_assets.py` — пройдено: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && mypy app/models/background_job.py app/models/fbs_print_asset.py app/services/background_job_service.py` — целевые модули проверены, но общий граф импортов дал 4 ранее существующие ошибки вне атома: `wildberries_credentials_service.py:167`, `fbs_stock_sync_service.py:617`, `fbs_warehouse_binding_service.py:23,291`; ошибок в изменённых файлах нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && pytest -q tests/test_background_jobs.py tests/test_fbs_print_assets.py` — пройдено: `18 passed in 13.10s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && alembic heads` — пройдено: единственная голова `20260822_0050 (head)`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && python3 scripts/ci/check_migrations.py` — не запущено по существу: скрипт отсутствует в этой рабочей копии; прямой вызов завершился с `No such file or directory`.
- `back_guard.py` — неприменим: атом не добавляет и не изменяет роут; скрипт также отсутствует в рабочей копии.
- `git diff --check` — пройдено.

## Не реализовано

- Находки ревью №1–5 и №8–10 относятся к frontend, infra или другим backend-атомам и не входят в файлы и слой атома 3.
- Находки №6 и №7, относящиеся к серверному контракту этого атома, исправлены полностью.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/models/fbs_print_asset.py` не менялся: уже имеющихся nullable-поля `storage_path` и `expires_at` достаточно для сохранения аудита без бинарного содержимого.
- Секреты, ключи, токены, `.env`, боевой прод `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Блокеров реализации нет. Целевой `mypy` остаётся ненулевым только из-за четырёх диагностик в чужих модулях, перечисленных в разделе «Гейты».
- Сохранение в Git заблокировано ограничением файловой системы среды: `git add ... && git commit ...` не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock` и завершается `Operation not permitted`. Изменения и этот артефакт остаются в рабочем дереве без нового commit SHA.

# Фича 4

# Backend dev · 05-prod-slow · атом 4 · rework

## Что реализовано

- `POST /operations/marking-codes/label-artifact-tape` — контракт `202`/job сохранён; одинаковый запрос переиспользует активное или готовое задание, пока его `label_tape` доступен.
- `marking_code_service.build_label_artifact_tape_pdf` — этикетки читаются из БД и передаются сборщику последовательно, без списка из 500 исходных BLOB.
- `marking_label_artifact_service.merge_label_artifact_pdfs_for_print_stream` — добавляет в итоговый PyMuPDF-документ по одному исходному PDF; при заданном формате страницы преобразованная копия также не накапливается в отдельном списке.
- `celery_app` — сборка ленты и удаление истёкшего бинарного файла направлены в одну очередь `print`.
- `docker-compose.prod.yml` — API и единственный `print_worker` используют общий именованный том `wms_data` по пути `/var/lib/wms`, поэтому сохранённый worker PDF доступен API, а уборщик видит тот же файл.
- `background_job_service` — проверено уже присутствующее исправление ревью: готовый job переиспользуется до истечения asset, а уборка очищает только `storage_path`, сохраняя строку `FbsPrintAsset` и ссылку job для аудита.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/marking_code_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/marking_label_artifact_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/celery_app.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_marking_pdf_label_artifact.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_background_jobs.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/docker-compose.prod.yml`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

## Миграции

Нет.

## Тесты

- `test_streaming_tape_merge_consumes_one_source_at_a_time` — доказывает, что следующий исходный PDF не запрашивается до добавления предыдущего в итоговый документ; проверено 155 страниц.
- `test_label_tape_load_does_not_block_health[155]` и `[500]` — параллельно со сборкой в изолированном worker-thread опрашивают `/health`, проверяют число страниц и фиксируют длительность.
- `test_label_tape_and_expiry_cleanup_share_print_queue` — сборка и уборка закреплены за очередью `print`.
- Целевой регрессионный набор также проверяет `202`, повтор того же pending/done job, ровно один asset, перевод job в `failed` и недоступность истёкшего asset при сохранённой аудиторской строке.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && ruff check app/services/marking_code_service.py app/services/marking_label_artifact_service.py app/celery_app.py tests/test_marking_pdf_label_artifact.py tests/test_background_jobs.py` — PASS, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && mypy app/services/marking_code_service.py app/services/marking_label_artifact_service.py app/services/background_job_service.py app/tasks/background_jobs.py app/celery_app.py` — FAIL только на 4 ранее существующих ошибках импортируемых зависимостей: `wildberries_credentials_service.py:167`, `fbs_stock_sync_service.py:617`, `fbs_warehouse_binding_service.py:23,291`; в файлах атома ошибок не выдано.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && mypy --follow-imports=skip app/services/marking_code_service.py app/services/marking_label_artifact_service.py app/celery_app.py` — PASS, `Success: no issues found in 3 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && pytest -q tests/test_marking_codes.py tests/test_marking_pdf_label_artifact.py tests/test_background_jobs.py tests/test_fbs_print_assets.py` — PASS, `44 passed, 5 warnings in 26.39s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && pytest -q -s tests/test_marking_pdf_label_artifact.py::test_streaming_tape_merge_consumes_one_source_at_a_time tests/test_marking_pdf_label_artifact.py::test_label_tape_load_does_not_block_health` — PASS, `3 passed`; 155 этикеток: job `0.084 s`, max `/health` `0.024 s`; 500 этикеток: job `0.275 s`, max `/health` `0.000 s`.
- Без чтения `.env` выполнен `yaml.safe_load` файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/docker-compose.prod.yml` с утверждениями общего `WMS_DATA_DIR`, mount `wms_data:/var/lib/wms` у API/print-worker и объявления volume — PASS.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && git diff --check` — PASS.
- `python3 scripts/ci/back_guard.py` не запускался: новый роут не добавлялся.
- `python3 scripts/ci/check_migrations.py` не запускался: миграция не добавлялась.
- `git add backend/app/celery_app.py backend/app/services/marking_code_service.py backend/app/services/marking_label_artifact_service.py backend/tests/test_background_jobs.py backend/tests/test_marking_pdf_label_artifact.py docker-compose.prod.yml night/volna-9-recovery/cards/05-prod-slow/DEV.md && git commit -m "fix(marking): stream queued label tape assets"` — BLOCKED средой до изменения индекса: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock`, `Operation not permitted`.

## Не реализовано

- Находки ревью №1 и №8–10 относятся к frontend/screen-dev, а №3–4 — к соседним атомам WB-sync; согласно роли `backend-dev` и границе атома 4 эти файлы не менялись.
- Реальный отдельный Celery-стенд не поднимался и production не затрагивался. Нагрузочный сценарий 155/500 выполнен локально с изоляцией сборщика от ASGI event loop и параллельным `/health`; инфраструктурный замер RSS отдельного контейнера остаётся стендовой проверкой.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Реализация и тесты находятся в постоянной рабочей копии, но новый commit SHA создать невозможно из-за запрета среды на запись в служебный Git-каталог зарегистрированного worktree. Изменения локально реализованы, но не сохранены отдельным коммитом и не опубликованы.

# Фича 5

# DEV · 05-prod-slow · атом 5 · TableLoadMore

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/TableLoadMore.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/TableLoadMore.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/UiKitShowcase.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/index.ts`
проверен и не изменён: `TableLoadMore` и `TableLoadMoreProps` уже экспортируются из
него буквально по контракту.

`TableLoadMore` скрывается без следующего курсора, показывает одно действие
«Показать ещё», при `loading=true` показывает «Загружаем…» со спиннером и
блокирует кнопку и обработчик, а при ошибке растягивает `ErrorNotice` над вновь
доступной центрированной кнопкой. Showcase явно подписывает все четыре
состояния, включая намеренно отсутствующий скрытый элемент. Добавлен unit-тест
этих состояний.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — **красный** на четырёх
  ранее существующих ошибках вне файлов атома: отсутствующий экспорт
  `beginPrintUserGesture` в `src/components/MarkingPrintDialog.tsx`, неиспользуемый
  `serverNow`, несовместимый `string | null` и запрещанный prop `size` в
  `src/screens/v2/FfFbsOrdersScreen.tsx`. Узкая проверка изменённых файлов через
  `npx tsc --ignoreConfig ... TableLoadMore.tsx TableLoadMore.test.ts UiKitShowcase.tsx`
  — **зелёная**.
- `python3 scripts/ui/ui_guard.py` из корня — **красный** на уже существующих
  превышениях baseline в `MarkingPrintDialog.tsx`, `WbProductPickerDialog.tsx`,
  `FfFbsOrdersScreen.tsx`, `FfFbsSupplyWorkspace.tsx` и
  `SellerInboundDraftScreen.tsx`. Файлы этого атома в нарушениях отсутствуют;
  baseline флагом `--update` не менялся.
- `npm run test:unit` из `frontend/` — **зелёный**, 20 файлов и 142 теста. Новый
  адресный набор `src/ui-kit/TableLoadMore.test.ts` — **зелёный**, 4 из 4.
- `git diff --check` — **зелёный**.
- `git add ... && git commit -m "fix(ui-kit): verify table load more states"` —
  **красный до изменения индекса**: Git не смог создать
  `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock`,
  `Operation not permitted`. Новый commit SHA не создан.

## Не реализовано

В пределах атома нет пунктов контракта, которые не удалось реализовать
буквально. Сделать два общих гейта зелёными нельзя без правок соседних экранов,
которые запрещены ролью `screen-dev` и не относятся к атому 5; ложное обновление
baseline также запрещено инструкцией роли.

## Находки

`REVIEW.md` не содержит замечаний к файлам или поведению `TableLoadMore` и прямо
подтверждает локальную блокировку двойного клика и доступный повтор после ошибки.
В ходе переделки закрыт отдельный пробел проверки нового ui-kit-примитива:
добавлен собственный unit-тест. Секреты, ключи, токены, `.env`, кабинеты учётных
данных, боевой прод `194.87.96.144` и живой кабинет Wildberries не читались и не
затрагивались.

## Блокеры

Атом локально реализован в постоянной рабочей копии, но не сохранён отдельным
Git-коммитом из-за запрета среды на запись в служебный индекс зарегистрированного
worktree. Старый `HEAD` `099602e2` не содержит эту переделку и не является SHA
результата.

# Фича 6

# DEV · 05-prod-slow · атом 6 · пагинация S-03 · rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-fbs-orders.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/fbsApi.ts`
проверен и не изменён: используемый экраном `fetchFbsWorklist` уже передаёт контрактные
`limit` и `cursor`.

Закрыты находки 8 и 9 из `REVIEW.md`, относящиеся к слою этого атома. Догрузка
фиксирует номер актуального запроса и ключ фильтра; ответ старого селлера, склада
или вкладки больше не добавляется к новой выдаче. Фоновый тик принимает новый
`next_cursor` первой порции, поэтому вставка заказа сверху не оставляет старую
границу пагинации. Выбор сместившейся строки сохраняется, а повторный обход нового
курсора возвращает её без дублей и без очистки ранее догруженного хвоста.

В разрешённый Playwright-файл добавлена гонка «летящая догрузка → смена склада →
старый ответ» и усилен `S-03-TC-006` с реальным сдвигом границы: новая строка
вставляется сверху, заказ № 50 возвращается по обновлённому курсору и остаётся
выбранным.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend` — **красный** только на существующей ошибке вне границы атома: `src/components/MarkingPrintDialog.tsx:3` импортирует отсутствующий `beginPrintUserGesture` из `@mui/material`. Три ранее существовавшие ошибки в разрешённом `FfFbsOrdersScreen.tsx` устранены; других ошибок команда не выдаёт.
- `python3 scripts/ui/ui_guard.py` из корня — **красный** на уже накопленных превышениях baseline: `MarkingPrintDialog.tsx` 1687 → 1753, `WbProductPickerDialog.tsx` 0 → 646, `FfFbsOrdersScreen.tsx` 1587 → 1668, `FfFbsSupplyWorkspace.tsx` 2493 → 2498, `SellerInboundDraftScreen.tsx` 1111 → 1169. Baseline флагом `--update` не менялась; четыре соседних файла запрещены границей роли.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend` — **зелёный**, 20 файлов и 142 теста.
- `npm run test:e2e -- tests-e2e/ff-fbs-orders.spec.ts` — **красный до запуска тестов**: Playwright webServer не получил разрешение среды на bind `127.0.0.1:18000` (`operation not permitted`). Production, внешний WB и сеть не затрагивались.
- `npx playwright test tests-e2e/ff-fbs-orders.spec.ts --list` — **зелёный**: файл корректно собран и обнаружены 14 сценариев, включая оба новых/усиленных сценария rework.
- `git diff --check` — **зелёный**.
- `git add frontend/src/screens/v2/FfFbsOrdersScreen.tsx frontend/tests-e2e/ff-fbs-orders.spec.ts night/volna-9-recovery/cards/05-prod-slow/DEV.md && git commit -m "fix(fbs): guard paginated worklist refreshes"` — **красный до изменения индекса**: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock`, `Operation not permitted`. Новый commit SHA не создан.

## Не реализовано

- Буквально выполнить браузерный прогон `S-03-TC-001`–`S-03-TC-007` и
  `S-03-TC-010`–`S-03-TC-012` не удалось: среда запрещает локальному API занять
  тестовый порт до старта Playwright. Сами сценарии собираются и перечисляются.
- Получить зелёные общие `tsc` и `ui_guard.py` в границах атома невозможно без
  изменения прямо запрещённого соседнего `MarkingPrintDialog.tsx` и нескольких
  соседних экранов либо без запрещённого обновления baseline.
- Находка 10 ревью про `S-03-TC-008`, `009`, `013`, `014`, `015` относится к
  следующему атому фоновой печати и общему `MarkingPrintDialog`, а не к пагинации
  этого атома; она намеренно не реализовывалась здесь.
- Изменения локально реализованы в постоянной рабочей копии, но не сохранены
  отдельным Git-коммитом из-за запрета среды на запись в служебный индекс worktree.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- Боевой production `194.87.96.144` и живой кабинет Wildberries не затрагивались.

# Фича 7

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/screens.registry.json`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/components/MarkingPrintDialog.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/utils/printMarkingCodeLabel.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-marking-print-constructor.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-separate-marking-print.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

Диалог сохраняет активную или готовую подготовку для тех же данных после закрытия и повторного открытия. Повтор в состояниях ошибки и истечения запускает только новую подготовку уже выбранных кодов, не повторяя операцию выдачи кодов. Состояния собраны из `StatusChip`, `ErrorNotice`, `ActionGroup`, `PrimaryAction` и `SecondaryAction`; PDF запрашивается только после явного действия «Открыть для печати». Реестр экранов фиксирует общий характер двух файлов для S-03/S-09/S-14/S-15 и закрывает находку ревью о границе владения.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — зелёный.
- `npm run test:unit` из `frontend/` — зелёный: 20 файлов, 142 теста.
- `npx eslint src/components/MarkingPrintDialog.tsx src/utils/printMarkingCodeLabel.ts tests-e2e/ff-marking-print-constructor.spec.ts tests-e2e/ff-separate-marking-print.spec.ts` — зелёный.
- `npx playwright test --list --grep "S-03 marking tape" ...` — зелёный: обнаружены два теста, покрывающие `S-03-TC-008`, `S-03-TC-009`, `S-03-TC-014` и `S-03-TC-015`.
- `npm run test:e2e -- --grep "S-03 marking tape" ...` — красный до выполнения сценариев: Playwright webServer не смог открыть локальный `127.0.0.1:18000`, среда вернула `[Errno 1] operation not permitted`. Это ограничение запуска среды, а не падение тестового шага в браузере.
- `python3 scripts/ui/ui_guard.py` из корня — красный на ранее существующих отклонениях: `MarkingPrintDialog.tsx` (baseline 1687, сейчас 1750 строк; до этой правки в HEAD было 1752), `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. Baseline не обновлялся; текущая правка размер `MarkingPrintDialog.tsx` не увеличила.
- `git diff --check` — зелёный.
- `git commit -m "fix(print): preserve background tape dialog state"` — красный: sandbox запретил создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock` (`Operation not permitted`). Изменения локально реализованы, но не сохранены новым commit SHA.

## Не реализовано

- Буквальных пропусков в разрешённом frontend-слое атома нет.
- Браузерное выполнение `S-03-TC-008`, `S-03-TC-009`, `S-03-TC-014`, `S-03-TC-015` не подтверждено в этой среде из-за запрета на bind локального порта; тесты добавлены и проходят обнаружение Playwright.
- Результат не удалось сохранить отдельным Git-коммитом из-за запрета sandbox на служебный `index.lock` зарегистрированного worktree; восстановление пока зависит от текущего рабочего дерева.
- Backend- и deployment-находки ревью, а также находки по `FfFbsOrdersScreen.tsx`, не менялись: они относятся к другим атомам и запрещены границами роли `screen-dev`.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой production и живой кабинет Wildberries не читались и не затрагивались.
