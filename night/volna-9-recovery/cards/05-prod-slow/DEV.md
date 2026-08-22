# Фича 1

# Backend dev · 05-prod-slow · атом 1 · переделка по ревью

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/wb_marketplace_orders_service.py`: списание `FbsBindingStockPool` теперь читает строку с `FOR UPDATE`, поэтому одновременно разрешённые контуры `new` и `reconcile` не теряют одно из списаний для двух разных заказов одного пула; существующая идемпотентность повторного импорта одного заказа через `UNIQUE(order_id)` сохранена.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/wb_marketplace_orders_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_wb_marketplace_orders_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

## Миграции

Нет.

## Тесты

- Добавлен `test_new_and_reconcile_serialize_different_order_debits_on_one_pool`: два параллельных списания разных заказов требуют блокировку строки пула, создают две записи `FbsStockPoolDebit` и уменьшают количество с 10 до 8.
- Повторно проверены атомарные сценарии `new`: отсутствие вызова постраничного полного списка и идемпотентный upsert.
- Повторно проверены атомарные сценарии `reconcile`: полный курсорный обход, отказ считать незавершённый проход успешным после ошибки, обнаружение цикла курсора и отсутствие произвольного лимита в десять страниц.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && ruff check app/services/wb_marketplace_orders_service.py tests/test_wb_marketplace_orders_service.py` — PASS, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && mypy app/services/wb_marketplace_orders_service.py` — FAIL только на четырёх существующих ошибках импортируемых соседних модулей: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/wildberries_credentials_service.py:167`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/fbs_stock_sync_service.py:617`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/fbs_warehouse_binding_service.py:23,291`; изменённый модуль в диагностике этой штатной команды отсутствует.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && mypy --follow-imports=skip app/services/wb_marketplace_orders_service.py` — дополнительная узкая попытка завершилась FAIL на 12 ранее существующих `no-any-return` в самом модуле; изменённая функция `_debit_stock_pool_once` в диагностике отсутствует.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && pytest -q tests/test_wb_marketplace_orders_service.py::test_new_and_reconcile_serialize_different_order_debits_on_one_pool tests/test_wb_marketplace_orders_service.py::test_new_sync_does_not_fetch_paginated_orders tests/test_wb_marketplace_orders_service.py::test_reconcile_walks_cursor_and_fails_incomplete_pass tests/test_wb_marketplace_orders_service.py::test_reconcile_rejects_a_repeated_next_token tests/test_wb_marketplace_orders_service.py::test_reconcile_walks_past_ten_pages_and_links_supplies` — PASS, `5 passed in 0.27s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && pytest -q tests/test_wb_marketplace_orders_service.py` — PASS, `19 passed in 3.88s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && git diff --check` — PASS.
- `python3 scripts/ci/back_guard.py` не запускался: атом не добавляет и не меняет роуты.
- `python3 scripts/ci/check_migrations.py` не запускался: атом не добавляет миграцию.

## Не реализовано

- Находки ревью №2–6 относятся к фоновым заданиям печати, frontend и документации; они находятся вне двух разрешённых backend-файлов этого атома и не изменялись.
- Полный backend-регресс, `ruff check .` и `mypy .` не запускались: инструкция атома прямо запрещает общий прогон до интеграции всех карточек.
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/CONTRACT.md` нет отдельного раздела «API и данные»; реализация ограничена буквально заданным пользователем атомом и относящейся к нему находкой №1 из `REVIEW.md`.

## Блокеры

- Функциональных блокеров в границах атома нет.
- Локальная реализация не сохранена отдельным Git-коммитом и не опубликована: команда `git add backend/app/services/wb_marketplace_orders_service.py backend/tests/test_wb_marketplace_orders_service.py night/volna-9-recovery/cards/05-prod-slow/DEV.md && git commit -m "fix(wb): serialize concurrent stock pool debits"` остановилась до изменения индекса с `fatal: Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock': Operation not permitted`. Риск: изменения пока восстанавливаются только из этой постоянной рабочей копии.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.

# Фича 2

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

# Backend dev · 05-prod-slow · атом 4 · повторный rework

## Что реализовано

- `background_job_service.run_marking_label_tape_job` — завершение задания теперь публикуется условным обновлением только при совпадении статуса `running` и последней отметки lease; потерявший lease worker откатывает свою транзакцию и не может заменить готовый результат нового владельца на `failed`.
- `_maintain_marking_label_tape_lease` — heartbeat возвращает последнюю подтверждённую отметку владения; ошибка БД или несовпадение отметки явно означают потерю lease.
- `docs/blockers/S-03.md` — блокировка повторной печати ленты получила уникальный идентификатор `B-14`; существующий `B-13` однозначно оставлен действию «Передать в доставку».
- Существующий `POST /operations/marking-codes/label-artifact-tape` не менялся: он по-прежнему отвечает `202`, возвращает `job_id` и переиспользует активное задание.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/background_job_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_background_jobs.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/docs/blockers/S-03.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

## Миграции

Нет.

## Тесты

- Добавлен `test_marking_label_tape_worker_losing_lease_preserves_new_owner_result`: первый worker зависает, heartbeat фиксирует передачу владения, новый владелец публикует один готовый asset, после чего старый worker просыпается и не изменяет `done`, `result_json` и `error_message`.
- Повторно проверены свежий и протухший lease, heartbeat длинной сборки, идемпотентность задания, `202`, единственный asset, безопасная ошибка worker и недоступность истёкшего asset.
- Нагрузочный сценарий повторён для 155 и 500 этикеток одновременно с `/health`.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && ruff check app/services/background_job_service.py tests/test_background_jobs.py` — PASS, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && mypy app/services/background_job_service.py` — FAIL на четырёх ранее существующих ошибках импортируемых соседних модулей: `wildberries_credentials_service.py:167`, `fbs_stock_sync_service.py:617`, `fbs_warehouse_binding_service.py:23,291`; в изменённом модуле новых ошибок не выдано.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && mypy --follow-imports=skip app/services/background_job_service.py` — PASS, `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && pytest -q tests/test_background_jobs.py::test_marking_label_tape_worker_losing_lease_preserves_new_owner_result tests/test_background_jobs.py::test_marking_label_tape_worker_does_not_reclaim_fresh_running_job tests/test_background_jobs.py::test_marking_label_tape_worker_reclaims_stale_running_job tests/test_background_jobs.py::test_marking_label_tape_heartbeat_prevents_duplicate_worker_and_asset` — PASS, `4 passed in 3.68s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && pytest -q tests/test_marking_codes.py tests/test_marking_pdf_label_artifact.py tests/test_background_jobs.py tests/test_fbs_print_assets.py` — PASS, `46 passed, 5 warnings in 28.52s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && pytest -q -s tests/test_marking_pdf_label_artifact.py::test_label_tape_load_does_not_block_health` — PASS, `2 passed, 5 warnings in 1.62s`; 155 этикеток: job `0.090 s`, max `/health` `0.026 s`; 500 этикеток: job `0.277 s`, max `/health` `0.000 s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && git diff --check` — PASS.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && git add backend/app/services/background_job_service.py backend/tests/test_background_jobs.py docs/blockers/S-03.md night/volna-9-recovery/cards/05-prod-slow/DEV.md && git diff --cached --check && git commit -m "fix(marking): preserve result after lease transfer"` — BLOCKED: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock`, `Operation not permitted`.
- `python3 scripts/ci/back_guard.py` не запускался: новый роут не добавлялся.
- `python3 scripts/ci/check_migrations.py` не запускался: миграция не добавлялась.

## Не реализовано

- Новые эндпоинты, модели, миграции и изменения соседних продуктовых карточек не добавлялись: повторный проход ограничен двумя находками `REVIEW.md`.
- Полный backend-регресс не запускался по прямому запрету атомарной проверки.
- Боевой production `194.87.96.144` и живой кабинет Wildberries не затрагивались.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.

## Блокеры

- Изменения находятся в постоянной зарегистрированной рабочей копии, но среда запрещает запись в служебный Git-каталог этого worktree. Отдельный commit SHA создать невозможно; изменения локально реализованы и проверены, но не сохранены коммитом и не опубликованы.

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

# DEV · 05-prod-slow · атом 6 · rework пагинации S-03

Исправлена находка №3 из `REVIEW.md`, относящаяся к этому атому. Асинхронный
обход курсоров по действию «Выбрать все» теперь фиксирует поколение запроса и
ключ фильтра. Если оператор во время обхода меняет вкладку, селлера или WB-склад,
поздний ответ старого фильтра не добавляет строки, не меняет курсор и не переносит
выбор в новую выдачу. Та же проверка не позволяет показать ошибку от уже
неактуального обхода.

В Playwright добавлен сценарий `S-03-TC-003 / S-03-TC-010`: вторая страница
старого WB-склада задерживается, оператор переключается на другой склад, после
чего старый ответ освобождается и проверяется отсутствие старых строк и выбора.

`frontend/src/screens/v2/fbsApi.ts` проверен и не изменён: его контракт `limit` и
`cursor` для этого исправления достаточен.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-fbs-orders.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx tsc --noEmit -p tsconfig.app.json` — **зелёный**, ошибок TypeScript нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && python3 scripts/ui/ui_guard.py` — **красный** на накопленном превышении baseline: `MarkingPrintDialog.tsx` 1687 → 1750, `WbProductPickerDialog.tsx` 0 → 646, `FfFbsOrdersScreen.tsx` 1587 → 1675, `FfFbsSupplyWorkspace.tsx` 2493 → 2498, `SellerInboundDraftScreen.tsx` 1111 → 1169. Baseline флагом `--update` не менялась; четыре соседних файла находятся вне границы атома, а несвязанный рефакторинг экрана запрещён контрактом.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npm run test:unit` — **зелёный**, 20 файлов и 142 теста.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx playwright test tests-e2e/ff-fbs-orders.spec.ts --list` — **зелёный**, файл собран, обнаружено 15 сценариев, включая новый сценарий гонки.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx playwright test tests-e2e/ff-fbs-orders.spec.ts --grep 'list, tabs and empty state|cursor pagination preserves rows and selection|first page shows a table skeleton|empty new list explains automatic WB loading|failed continuation preserves rows and retries|changing warehouse does not merge a previous page|changing warehouse discards an in-flight old continuation|polling preserves the loaded tail and pauses while hidden|select all includes every cursor page|changing warehouse discards an in-flight select all'` — **красный до запуска сценариев**: Playwright webServer не смог открыть `127.0.0.1:18000`, `operation not permitted`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && git diff --check` — **зелёный**.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && git add -- frontend/src/screens/v2/FfFbsOrdersScreen.tsx frontend/tests-e2e/ff-fbs-orders.spec.ts night/volna-9-recovery/cards/05-prod-slow/DEV.md && git diff --cached --check && git commit -m "fix(fbs): discard stale select-all pages"` — **красный до изменения индекса**: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock`, `Operation not permitted`; новый commit SHA не создан.

## Не реализовано

- Буквальный браузерный прогон `S-03-TC-001`–`S-03-TC-007` и
  `S-03-TC-010`–`S-03-TC-012` не состоялся: среда запретила локальному API
  занять тестовый порт до старта Playwright. Сценарии корректно компилируются и
  перечисляются командой `--list`.
- `ui_guard.py` нельзя сделать зелёным в границе этого атома без несвязанного
  сокращения существующего экрана, правки четырёх запрещённых соседних файлов
  или запрещённого обновления baseline.
- Находки №1–2 и №4–6 из `REVIEW.md` относятся к backend, слою фоновой печати и
  документации блокеров. В атоме пагинации S-03 эти файлы намеренно не менялись.
- Изменения локально реализованы в постоянной рабочей копии, но не сохранены
  отдельным Git-коммитом из-за запрета среды на запись в служебный индекс
  worktree. До появления commit SHA атом нельзя считать сохранённым или готовым.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- Боевой production `194.87.96.144` и живой кабинет Wildberries не затрагивались.

# Фича 7

# DEV · 05-prod-slow · атом 7 · rework фоновой ленты

Исправлены находки №4 и №5 из `REVIEW.md`, относящиеся к экранному слою этого
атома. Трекер подготовки теперь хранит отдельную сессию для каждого контекста
ленты: запуск товара B не вытесняет активное или готовое задание товара A, а
повторное открытие A восстанавливает его состояние без нового запуска.

Ошибка выдачи готового PDF больше не считается истечением автоматически.
Истечение определяется только по серверному коду `asset_expired`; временная
ошибка доступа показывает «Не удалось открыть ленту. Попробуйте ещё раз», а
«Повторить» запрашивает тот же готовый PDF и не создаёт тяжёлое задание заново.

Playwright-сценарии усилены проверкой двух одновременно запомненных контекстов,
временной ошибки открытия, настоящего истечения и отсутствия лишнего запуска.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/components/MarkingPrintDialog.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/utils/printMarkingCodeLabel.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-marking-print-constructor.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-separate-marking-print.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx tsc --noEmit -p tsconfig.app.json` — **зелёный**, ошибок TypeScript нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npm run test:unit` — **зелёный**, 20 файлов и 142 теста.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx playwright test tests-e2e/ff-marking-print-constructor.spec.ts tests-e2e/ff-separate-marking-print.spec.ts --list` — **зелёный**, оба целевых сценария и две относящиеся к файлам регрессии собраны; всего 4 теста.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend && npx playwright test tests-e2e/ff-marking-print-constructor.spec.ts tests-e2e/ff-separate-marking-print.spec.ts --grep 'S-03 marking tape'` — **красный до запуска сценариев**: Playwright webServer не смог открыть `127.0.0.1:18000`, `operation not permitted`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && python3 scripts/ui/ui_guard.py` — **красный на унаследованном превышении baseline**: `MarkingPrintDialog.tsx` 1687 → 1750, `WbProductPickerDialog.tsx` 0 → 646, `FfFbsOrdersScreen.tsx` 1587 → 1675, `FfFbsSupplyWorkspace.tsx` 2493 → 2498, `SellerInboundDraftScreen.tsx` 1111 → 1169. Этот атом не увеличил размер `MarkingPrintDialog.tsx` относительно текущего `HEAD`; baseline флагом `--update` не менялась, а четыре соседних файла находятся вне разрешённых границ.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && git diff --check` — **зелёный**.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && git add -- frontend/src/components/MarkingPrintDialog.tsx frontend/src/utils/printMarkingCodeLabel.ts frontend/tests-e2e/ff-marking-print-constructor.spec.ts frontend/tests-e2e/ff-separate-marking-print.spec.ts night/volna-9-recovery/cards/05-prod-slow/DEV.md && git diff --cached --check && git commit -m "fix(printing): retain background tape sessions"` — **красный до изменения индекса**: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock`, `Operation not permitted`; commit SHA не создан.

## Не реализовано

- Буквальный браузерный прогон `S-03-TC-008`, `S-03-TC-009`, `S-03-TC-014` и
  `S-03-TC-015` не состоялся: среда запретила локальному API занять тестовый
  порт до старта Playwright. Целевые тесты корректно компилируются и
  перечисляются командой `--list`.
- `ui_guard.py` нельзя сделать зелёным в границе атома без несвязанного
  сокращения существующего монолита, правки четырёх запрещённых соседних
  файлов или запрещённого обновления baseline. Нового роста разрешённого
  `MarkingPrintDialog.tsx` относительно `HEAD` нет.
- Находки №1–3 и №6 из `REVIEW.md` относятся к backend, пагинации S-03 и
  документации блокеров; в экранном атоме фоновой ленты они не менялись.
- Изменения локально реализованы в постоянной рабочей копии, но не сохранены
  отдельным Git-коммитом из-за запрета среды на запись в служебный индекс
  worktree. До появления commit SHA атом нельзя считать сохранённым или готовым.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- Боевой production `194.87.96.144` и живой кабинет Wildberries не затрагивались.
