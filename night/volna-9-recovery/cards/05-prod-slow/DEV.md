# Фича 1

# Backend-dev отчёт · 05-prod-slow

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_wb_marketplace_orders_service.py` — усилен тест ошибки страницы: незавершённая `reconcile` делает rollback и не запускает связывание поставок.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md` — отчёт этой роли.

Сервисный код `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/wb_marketplace_orders_service.py` проверен: `new` использует только `fetch_marketplace_orders_new`, а `reconcile` проходит курсор до пустой финальной страницы и вызывает связывание поставок только после успешного завершения.

## Миграции

Нет.

## Тесты

- `test_new_sync_does_not_fetch_paginated_orders` — `new` не вызывает полный постраничный список и выполняет idempotent upsert.
- `test_reconcile_walks_cursor_and_fails_incomplete_pass` — ошибка страницы вызывает rollback, не считается успешной сверкой и не запускает связывание поставок.
- `test_reconcile_walks_past_ten_pages_and_links_supplies` — `reconcile` проходит курсор после десятой страницы и связывает поставки после полного прохода.

## Гейты

- `ruff check backend/app/services/wb_marketplace_orders_service.py backend/tests/test_wb_marketplace_orders_service.py` — PASS.
- `mypy .` из `backend/` — FAIL на 21 существующей ошибке в шести несвязанных файлах; изменённые файлы в выводе отсутствуют.
- `pytest -q backend/tests/test_wb_marketplace_orders_service.py` — PASS, 12 тестов.
- `python3 scripts/ci/back_guard.py` — NOT RUN: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — NOT RUN: файл отсутствует в рабочей копии; миграций нет.
- `git diff --check` — PASS.

## Не реализовано

- Находки ревью про print worker, `background_job`-уникальность, frontend и E2E относятся к другим слоям/атомам и не изменялись.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

# Фича 2

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

# Фича 3

# Backend-dev отчёт · 05-prod-slow

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/models/background_job.py` — активный уникальный индекс идемпотентности теперь условный и для PostgreSQL, и для SQLite.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/alembic/versions/20260822_0050_marking_label_tape_jobs.py` — миграция создаёт такой же частичный индекс в SQLite.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_background_jobs.py` — добавлен регрессионный тест повторного запуска после `failed` с тем же ключом.

## Что реализовано

- Существующий сервис `create_pending_job` сохраняет одну активную (`pending`/`running`) задачу `marking_label_tape` по ключу идемпотентности; завершённые задачи больше не блокируют повтор.
- Существующий worker сохраняет в `result_json` только `asset_id`, а PDF остаётся в print asset с 12-часовым сроком выдачи.

## Миграции

- `20260822_0050` — добавляет `background_jobs.idempotency_key`, частичный уникальный индекс активных задач (PostgreSQL и SQLite), `fbs_print_assets.expires_at`.

## Гейты

- `ruff check .` — FAIL: 80 уже существующих нарушений в несвязанных файлах; в изменённых backend-файлах ошибок нет.
- `mypy .` — FAIL: 21 уже существующая ошибка в 6 несвязанных файлах; изменённые файлы в выводе отсутствуют.
- `pytest` из `backend/` — полный прогон начат, выявлены падения в несвязанных существующих сценариях; целевые `tests/test_background_jobs.py tests/test_fbs_print_assets.py`: PASS, 14 passed.
- `python3 scripts/ci/back_guard.py` — не запущен: файл отсутствует в этой рабочей копии (`scripts/ci/back_guard.py` не найден).
- `python3 scripts/ci/check_migrations.py` — не запущен: файл отсутствует в этой рабочей копии (`scripts/ci/check_migrations.py` не найден).
- `git diff --check` — PASS.

## Не реализовано

- Frontend polling, закрытие диалога, popup/fallback и E2E-сценарии не менялись: это не backend-слой данного атома.
- Отдельный Celery worker очереди `print` не менялся: это инфраструктурный файл, не входящий в разрешённый backend-атом.
- Новых эндпоинтов нет, поэтому отдельный роут-тест не требуется.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

# Фича 4

# Backend-dev отчёт · 05-prod-slow

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/docker-compose.prod.yml` — очередь `print` отделена от обычного Celery worker; добавлен отдельный `print_worker` с `--concurrency=1`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_background_jobs.py` — регрессия повторного запуска с тем же ключом после `failed` и `done`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_fbs_stock_emulator_integration.py` — проверка разделения очередей в production compose.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md` — этот отчёт.

## Что реализовано

- Production запускает обычные задачи только в очереди `celery`, а печать лент — в отдельном worker очереди `print` с одним процессом; две тяжёлые ленты не собираются параллельно.
- Условный уникальный индекс активных print-job уже поддерживает PostgreSQL и SQLite; тест теперь проверяет повтор после обоих финальных статусов (`failed` и `done`).

## Миграции

- Нет новых миграций. Используется существующая `20260822_0050`, которая добавляет `idempotency_key`, частичный индекс активных job для PostgreSQL и SQLite и `fbs_print_assets.expires_at`.

## Гейты

- `ruff check .` — FAIL: 80 существующих нарушений в несвязанных файлах; изменённые backend-тесты проверены отдельно и ошибок не имеют.
- `mypy .` — FAIL: 21 существующая ошибка в 6 несвязанных файлах; изменённые файлы не добавили ошибок.
- `pytest` — целевые тесты фоновых print-job прошли; полный прогон в этой среде не завершил вывод после старта набора.
- `python3 scripts/ci/back_guard.py` — не запущен: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — не запущен: файл отсутствует в рабочей копии.
- `git diff --check` — PASS.

## Не реализовано

- Frontend polling, закрытие диалога, popup/fallback и E2E-сценарии не менялись: это не backend-dev слой данного атома.
- Нагрузочный прогон на 155/500 кодов и `/health` не запускался: для него нужен стенд с брокером и worker; production не затрагивался.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

# Фича 5

# DEV · 05-prod-slow · TableLoadMore

## Изменённые файлы

Кодовые файлы атома в этой проверке не изменялись: реализация уже присутствует в рабочей копии и соответствует контракту. Проверены:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/TableLoadMore.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/UiKitShowcase.tsx`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не завершился в доступном окружении без вывода; процесс остановлен. Результат не подтверждён.
- `python3 scripts/ui/ui_guard.py` — красный из-за новых нарушений в соседних экранах: `MarkingPrintDialog.tsx`, `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. Файлы атома в сообщениях проверки отсутствуют; baseline не изменялся.
- `npm run test:unit` — не запущен: `vitest: command not found`.

Ревью-сценарии атома проверены по коду: состояние `hasNext=false` скрывает элемент; доступное состояние показывает единственную кнопку «Показать ещё»; `loading` блокирует кнопку, показывает спиннер и «Загружаем…»; ошибка выводит `ErrorNotice` над доступным повторным действием. Showcase содержит все четыре состояния и интерактивный сценарий с защитой от повторного вызова.

## Не реализовано

Буквально не подтверждены зелёные tsc и unit-гейты из-за отсутствующих/зависших инструментов в окружении. Исправление чужих нарушений `ui_guard.py` и установка зависимостей не входят в разрешённые файлы и атомарную задачу.

# Фича 6

# DEV · 05-prod-slow

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-fbs-orders.spec.ts`

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/fbsApi.ts` не изменялся: курсор и лимит 50 уже поддерживались его контрактом.

Исправлены контрактные тексты ошибки первой загрузки и пустого списка. E2E-сценарий теперь моделирует две страницы по 50 заказов, проверяет догрузку по `next_cursor`, сохранение выбранного заказа, отсутствие дублей и скрытие кнопки после последней страницы.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: локальный TypeScript-бинарник отсутствует, `npx` завис на попытке запуска/разрешения команды и был остановлен.
- `python3 scripts/ui/ui_guard.py` — красный: скрипт сообщил о нарушениях монолитности в `src/components/MarkingPrintDialog.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsOrdersScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовую линию через `--update` не менял.
- `npm run test:unit` — красный до запуска тестов: `sh: vitest: command not found`.

## Не реализовано

- Полный набор браузерных сценариев `S-03-TC-001`–`S-03-TC-007` и `S-03-TC-010`–`S-03-TC-012` в рамках этого прохода не запускался: в окружении отсутствуют frontend-зависимости для запуска тестов.
- `fbsApi.ts` не потребовал правки, так как `fetchFbsWorklist` уже передаёт `limit` и `cursor`.

# Фича 7

# DEV · 05-prod-slow · атом 7

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/components/MarkingPrintDialog.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/utils/printMarkingCodeLabel.ts

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: локальный `frontend/node_modules/.bin/tsc` отсутствует, запуск `npx` завис без результата и был остановлен.
- `python3 scripts/ui/ui_guard.py` — красный из-за уже существующих/вне атома нарушений: `MarkingPrintDialog.tsx:1687–1741`, а также `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. Базовая линия не обновлялась.
- `npm run test:unit` — не запущен: `vitest: command not found`.
- `git diff --check` — зелёный.

Изменения проверены после финальной правки: popup создаётся только обработчиком явного открытия готовой ленты.

## Не реализовано

- Полный Playwright-путь `S-03-TC-008`, `S-03-TC-009`, `S-03-TC-014`, `S-03-TC-015` локально не подтверждён: зависимости фронтенда отсутствуют.
- Серверная дедупликация активного задания, SQLite-индекс и очереди Celery не изменялись: они относятся к backend/infra-слою и не входят в разрешённые файлы атома.
- UI-guard не исправлялся через `--update`, поскольку найденные нарушения не созданы этим атомом полностью и обновление базовой линии запрещено ролью.
