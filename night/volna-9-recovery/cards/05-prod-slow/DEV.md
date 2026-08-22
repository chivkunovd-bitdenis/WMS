# Фича 1

# Backend-dev отчёт · 05-prod-slow

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/wb_marketplace_orders_service.py` — разделены контуры `new` и `reconcile`; `new` читает только текущие задания WB, `reconcile` проходит курсоры до конца и не завершает неполный проход успешно.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_wb_marketplace_orders_service.py` — добавлены проверки отсутствия полного списка в `new`, полного прохода курсоров, идемпотентного upsert и rollback при ошибке страницы.

## Миграции

Нет.

## Тесты

- `test_new_sync_does_not_fetch_paginated_orders` — `new` не вызывает постраничный полный список и выполняет upsert.
- `test_reconcile_walks_cursor_and_fails_incomplete_pass` — `reconcile` доходит до конца курсоров и при ошибке страницы откатывает незавершённый проход.

## Гейты

- `ruff` — PASS для измененных backend-файлов.
- `mypy` — BLOCKED: 5 ошибок, из них 4 предсуществующие в соседних сервисах и 1 в незакоммиченном соседнем `fbs_autopoll_service.py`; в сервисе этой карточки ошибок нет.
- `pytest` — PASS: 10 тестов `backend/tests/test_wb_marketplace_orders_service.py`.
- `back_guard.py` — NOT RUN: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/scripts/ci/back_guard.py` отсутствует.
- `check_migrations.py` — NOT RUN: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Планировщики, single-flight и UI не входят в этот атомарный backend-кусок и не изменялись.

## Находки

- В рабочем дереве есть несвязанные незакоммиченные изменения планировщика, фоновых задач и журнала; они не включены в этот отчёт как часть атомарного куска.

# Фича 2

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

# Фича 3

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/models/background_job.py — добавлены тип задания `marking_label_tape`, ключ идемпотентности и уникальность активного запроса.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/models/fbs_print_asset.py — добавлены вид `label_tape` и срок доступности артефакта.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/background_job_service.py — повтор активного запроса возвращает существующее задание.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/fbs_print_asset_service.py — истёкший артефакт не выдаётся.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/alembic/versions/20260822_0050_marking_label_tape_jobs.py — добавляющая миграция.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_background_jobs.py — идемпотентность и ссылка `asset_id`.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_fbs_print_assets.py — отказ после истечения срока.

## Гейты

- ruff — targeted изменённые файлы: PASS; полный `ruff check .`: FAIL на существующих несвязанных ошибках репозитория (84 ошибки, включая старые `noqa` и ошибки в других модулях).
- mypy — не выполнен полным проходом после остановки цепочки на полном ruff; targeted запуск требует повторного запуска из `backend/`.
- pytest — PASS: 10 тестов в `tests/test_background_jobs.py tests/test_fbs_print_assets.py`.
- back_guard.py — не выполнен: файл `scripts/ci/back_guard.py` отсутствует в этой рабочей копии.
- check_migrations.py — не выполнен: файл `scripts/ci/check_migrations.py` отсутствует в этой рабочей копии.
- Git commit — не выполнен: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock` из-за ограничения доступа; изменения остаются в рабочем дереве.

## Не реализовано

- API-эндпоинт постановки и worker сборки PDF не входят в этот атомарный кусок; контрактом этой карточки заданы только серверные сущности, идемпотентность и срок выдачи артефакта.
- Поле истечения не удаляет бинарный файл автоматически; уборка должна выполняться отдельным worker-контуром.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 4

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/api/marking_codes.py — `POST /operations/marking-codes/label-artifact-tape` теперь возвращает `202` и `job_id`, с идемпотентной постановкой.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/api/fbs_print_assets.py — истёкший актив отдаёт безопасный `404`.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/background_job_service.py — worker последовательно собирает ленту, сохраняет один `label_tape` PDF-asset и переводит job в `done`/`failed`.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/fbs_print_asset_service.py — выдача PDF-актива и проверка срока хранения.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/fbs_print_asset_storage.py — безопасное PDF-хранилище для лент.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/tasks/background_jobs.py — Celery-задача в очереди `print`.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_marking_pdf_label_artifact.py — тест асинхронного job/polling и PDF-актива.

## Гейты

- ruff — targeted изменённые backend-файлы: PASS; полный `ruff check .`: FAIL, 81 ранее существующих ошибок вне атомарного изменения.
- mypy — FAIL на 3 существующих ошибках в `inventory_movement_report_service.py`, `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`; новые файлы не указаны в диагностике.
- pytest — PASS: 17 тестов в `tests/test_marking_pdf_label_artifact.py`; профильный `tests/test_marking_codes.py` также проходил до изменения теста ленты.
- back_guard.py — BLOCKED: `scripts/ci/back_guard.py` отсутствует в этой рабочей копии.
- check_migrations.py — BLOCKED: `scripts/ci/check_migrations.py` отсутствует в этой рабочей копии.

## Не реализовано

- Отдельный нагрузочный прогон на 155/500 кодов и параллельная проверка `/health` не выполнены: в контракте нет локального стендового harness, а боевой прод запрещён к затрагиванию.
- Перенос `/fbs/supplies/{supply_id}/order-print-tape` не выполнялся: он явно исключён из этого атомарного куска.
- Миграция не добавлялась: требуемые поля уже присутствуют в миграции `20260822_0050_marking_label_tape_jobs.py` из предыдущего backend-шага.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Фича 5

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/TableLoadMore.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/index.ts
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/UiKitShowcase.tsx

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный: три нарушения вне разрешённых файлов, в `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`. Код и базовая линия не изменялись.
- `npm run test:unit` — не запустился: в рабочем окружении отсутствует команда `vitest` (`vitest: command not found`).

## Не реализовано

- Буквально проверить showcase вручную и повторный клик в браузере не удалось: для этой роли доступна только безголовая проверка сборки, а unit runner не установлен.

# Фича 6

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/fbsApi.ts
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-fbs-orders.spec.ts

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный: обнаружены нарушения-монолиты в `FfFbsOrdersScreen.tsx` и трёх ранее затронутых экранах; базовая линия не обновлялась.
- `npm run test:unit` — красный: `vitest: command not found` в окружении.

## Не реализовано

- Полный Playwright-набор `S-03-TC-001`–`S-03-TC-007`, `S-03-TC-010`–`S-03-TC-012` не запускался: в доступных обязательных командах отсутствует unit runner, а браузерный стенд не поднимался в рамках этой роли.
- `fbsApi.ts` не потребовал изменения: функция `fetchFbsWorklist` уже поддерживала `cursor` и `next_cursor`.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.

# Фича 7

# Screen-dev отчёт · 05-prod-slow · атом 7

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/components/MarkingPrintDialog.tsx` — добавлено состояние фоновой подготовки native-PDF ленты, блокировка повторной печати, явное «Открыть для печати» и безопасные действия «Повторить»/«Закрыть».
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/utils/printMarkingCodeLabel.ts` — добавлен запуск и опрос существующего background job с получением PDF-актива после `done`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md` — этот артефакт.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — BLOCKED: локального бинарника `tsc` нет; `npx` попытался скачать пакет и получил `ENOTFOUND registry.npmjs.org`.
- `python3 scripts/ui/ui_guard.py` — FAIL: сохранены существующие нарушения в соседних экранах; для `MarkingPrintDialog.tsx` остаётся новое нарушение `экран-монолит` из-за обязательной правки существующего диалога. Базовая линия не обновлялась.
- `npm run test:unit` — BLOCKED: `vitest: command not found`.
- `git diff --check` — PASS.

## Не реализовано

- Playwright-сценарии `S-03-TC-008`, `S-03-TC-009`, `S-03-TC-014`, `S-03-TC-015` не изменялись: пользовательский контракт перечислил их как проверку, но роль ограничена реализацией экрана, а браузерный прогон в обязательных командах не запускался из-за отсутствующих зависимостей.
- Полное устранение монолитности `MarkingPrintDialog.tsx` не выполнялось: это потребовало бы выхода за атомарную правку состояния фоновой ленты.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
- В рабочем дереве до начала работы были несвязанные изменения `night/volna-9-recovery/JOURNAL.md`; они не относятся к этому атому.
