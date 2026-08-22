# Фича 1

# Backend-dev отчёт · 05-prod-slow

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/wb_marketplace_orders_service.py` — убран искусственный предел в 10 страниц у `reconcile`; курсор теперь проходится до конца, а связывание подтверждённых заказов с поставками WB выполняется только после полного успешного прохода.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_wb_marketplace_orders_service.py` — добавлен тест сверки более 10 страниц и вызова связывания поставок; существующий тест ошибки изолирован от SQL-ветки связывания.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md` — этот отчёт.

## Миграции

Нет.

## Тесты

- `test_new_sync_does_not_fetch_paginated_orders` — `new` не вызывает полный постраничный список и выполняет upsert.
- `test_reconcile_walks_cursor_and_fails_incomplete_pass` — ошибка страницы вызывает rollback и не запускает связывание поставок.
- `test_reconcile_walks_past_ten_pages_and_links_supplies` — `reconcile` проходит курсор после десятой страницы и связывает поставки после завершения.

## Гейты

- `ruff check .` — PASS.
- `mypy .` — FAIL из-за 21 существующей ошибки в шести других файлах; измененные файлы в выводе не указаны.
- `pytest` — PASS: 11 тестов `backend/tests/test_wb_marketplace_orders_service.py`.
- `python3 scripts/ci/back_guard.py` — NOT RUN: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — NOT RUN: файл отсутствует в рабочей копии.
- `git diff --check` — PASS.

## Не реализовано

- Остальные находки ревью относятся к другим backend-сервисам, Celery/инфраструктуре, frontend или соседним атомам; в этот backend-кусок не входят и не изменялись.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

# Фича 2

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/fbs_autopoll_service.py — single-flight теперь использует отдельный PostgreSQL advisory lock для пары `(seller_id, sync_kind)`; `new` и `reconcile` не блокируют друг друга.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/celery_app.py — удалено старое дублирующее расписание `fbs-orders-autopoll`; оставлены независимые интервалы 180 секунд и 3600 секунд.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_wb_marketplace_orders_service.py — добавлены проверки отсутствия старого beat-контурa и различия межпроцессных lock-ключей для двух видов синхронизации.

## Гейты

- `ruff check .` — FAIL на существующих нарушениях в несвязанных файлах; изменённый тест после исправления `SIM117` не добавляет замечаний.
- `mypy .` — FAIL на существующих ошибках в `inventory_movement_report_service.py`, `wildberries_credentials_service.py`, cleanup-скриптах и `fbs_stock_sync_service.py`; изменённые файлы в выводе отсутствуют.
- `pytest -q` — выполняется/результат будет дополнен после завершения полного прогона; целевые `tests/test_wb_marketplace_orders_service.py tests/test_fbs_autopoll.py` проходят.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии (`file not found`).
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии (`file not found`); миграций в атоме нет.
- Commit — BLOCKED: Git не разрешил создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock` (`Operation not permitted`); изменения сохранены в рабочем дереве и перечислены ниже.

## Не реализовано

- Пункты ревью 1–2 и 7–15 относятся к печатной фоновой ленте или frontend-экранам и не входят в этот backend-атом.
- Миграции — нет.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

# Фича 3

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/background_job_service.py — конкурентно безопасное создание активной job по ключу идемпотентности и атомарный захват `marking_label_tape`.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/fbs_print_asset_storage.py — удаление одного валидированного файла после истечения срока.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/fbs_print_asset_service.py — удаление PDF ленты при отказе после 12 часов.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_background_jobs.py — проверки состояний job, результата только с `asset_id` и повторной доставки running job.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_fbs_print_assets.py — ruff-форматирование импортов существующих тестов истечения срока.

## Миграции

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/alembic/versions/20260822_0050_marking_label_tape_jobs.py` уже содержит добавляющую миграцию `idempotency_key`, активный уникальный индекс и `expires_at`; новая миграция не добавлялась.

## Тесты

- Целевой прогон `tests/test_background_jobs.py tests/test_fbs_print_assets.py`: 12 passed.
- Полный `pytest`: остановлен после зависания прогона примерно на 38%; до остановки обнаружены падения в существующих сценариях `test_fbs_orders_intake.py` и `test_fbs_stock_emulator_integration.py`, не связанных с этим атомом.

## Гейты

- `ruff check .` — FAIL: 80 существующих нарушений в несвязанных файлах; целевые изменённые файлы проходят.
- `mypy .` — FAIL: существующие ошибки в 7 файлах; после исправления типы изменённых файлов проходят, остаются ошибки соседних модулей и старых тестов.
- `pytest` — STOPPED после зависания полного прогона; целевые тесты зелёные, полный прогон выявил несвязанные падения.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии.

## Не реализовано

- Очередь Celery и production-worker из находки 1 не менялись: это инфраструктурная граница данного backend-атома.
- Периодическая уборка всех истёкших файлов не добавлялась; реализована безопасная уборка конкретного PDF при попытке выдачи после истечения срока.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
- Commit — BLOCKED: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock` (`Operation not permitted`); изменения не сохранены в commit.

# Фича 4

# DEV · 05-prod-slow · backend-dev

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/api/marking_codes.py — повторный активный job больше не публикуется повторно.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/background_job_service.py — атомарный захват pending-job и плановая очистка истёкших `label_tape` assets.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/tasks/background_jobs.py — Celery-задача очистки.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/celery_app.py — маршрут `marking_label_tape` в очередь `print` и hourly cleanup в beat.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/docker-compose.prod.yml — production worker слушает `celery,print`.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_background_jobs.py — регрессия идемпотентной публикации pending-job.

## Миграции

нет — схема базы данных не менялась.

## Гейты

- ruff: targeted files — PASS; полный `ruff check .` — FAIL на существующих несвязанных нарушениях в рабочей копии.
- mypy: FAIL на существующих несвязанных ошибках в `wildberries_credentials_service.py` и `fbs_stock_sync_service.py`; изменённые файлы не добавили диагностик.
- pytest: `backend/tests/test_background_jobs.py` — 5 passed.
- back_guard.py: не запущен — файл отсутствует в этой рабочей копии (`scripts/ci/back_guard.py` не найден).
- check_migrations.py: не запущен — файл отсутствует в этой рабочей копии (`scripts/ci/check_migrations.py` не найден).

## Не реализовано

- Frontend-состояния и Playwright-сценарии не менялись: они относятся к другой роли.
- Находки ревью по WB-autopoll и frontend не относятся к этому backend-атому и не затрагивались.
- Нагрузочный прогон 155/500 кодов с `/health` не выполнялся в рамках локального backend-теста.

## Блокеры

Нет блокеров по реализации. Полные общие ruff/mypy и два repository guard-скрипта ограничены состоянием/составом этой рабочей копии, указанным выше.

# Фича 5

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/UiKitShowcase.tsx

`TableLoadMore.tsx` и `index.ts` уже содержали требуемую реализацию и экспорт; по замечаниям ревьюера изменений в них не потребовалось.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не завершён: `npx` завис на попытке получить отсутствующий локальный `tsc`, процесс остановлен.
- `python3 scripts/ui/ui_guard.py` — красный из-за пяти нарушений в соседних экранах: `MarkingPrintDialog.tsx`, `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. Эти файлы не относятся к атомарному куску и не изменялись.
- `npm run test:unit` — красный: `vitest: command not found`.

## Не реализовано

- Новых нереализованных пунктов контракта нет. Showcase демонстрирует скрытое, доступное, загружаемое и ошибочное состояния; интерактивный пример считает вызовы и блокирует повторный вызов во время загрузки.

# Фича 6

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не завершён: локальный процесс `tsc` завис без вывода и был остановлен.
- `python3 scripts/ui/ui_guard.py` — красный: обнаружены новые нарушения в `FfFbsOrdersScreen.tsx` (монолит/своя кнопка), а также нарушения в соседних файлах; базовую линию не обновлял.
- `npm run test:unit` — красный: `vitest: command not found`.

## Не реализовано

- Полный Playwright-набор `S-03-TC-001`–`S-03-TC-007`, `S-03-TC-010`–`S-03-TC-012` не запускался: в окружении отсутствует runner зависимостей.
- Backend- и печатные находки из REVIEW.md не менялись: они не относятся к разрешённому экранному слою этого атома.

# Фича 7

# Screen-dev отчёт · 05-prod-slow · атом 7

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/components/MarkingPrintDialog.tsx` — исправлена обработка фоновой подготовки ленты: ошибки больше не уходят в HTML-fallback, состояние показывает безопасные действия «Повторить» и «Закрыть», статус подготовки назван «Готовим ленту…», дублирующий блок готового состояния удалён.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md` — этот артефакт.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — BLOCKED: локальный запуск не завершился; ранее в этой рабочей копии отсутствовал бинарник `tsc`, а установка через `npx` требует недоступной сети.
- `python3 scripts/ui/ui_guard.py` — FAIL: обнаружены новые/текущие нарушения `экран-монолит`, включая `src/components/MarkingPrintDialog.tsx:1687 → 1747`; базовая линия не обновлялась.
- `npm run test:unit` — BLOCKED: `vitest: command not found`.
- `git diff --check` — PASS.

## Не реализовано

- Playwright-кейсы `S-03-TC-008`, `S-03-TC-009`, `S-03-TC-014`, `S-03-TC-015` не запускались: роль выполняет экранную правку, а локальные frontend-зависимости отсутствуют.
- Серверная дедупликация фоновых заданий и очистка истёкших PDF не менялись: они находятся вне разрешённого слоя этого атома.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
- В рабочем дереве есть несвязанное изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/JOURNAL.md`; его не менял.
