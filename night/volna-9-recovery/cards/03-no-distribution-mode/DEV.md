# Фича 1

# Backend-dev · 03-no-distribution-mode

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` — сохранённый признак поставки стал источником истины для readiness и назначения; включение блокируется на строке поставки, повторное включение не меняет аудит.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_workspace_service.py` — workspace больше не восстанавливает режим из legacy-ключей коробов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/api/fbs_errors.py` — добавлено понятное сообщение для конфликта назначенных заказов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — этот отчёт.

## Гейты

- ruff: `ruff check .` — FAIL: в репозитории 80 существующих ошибок; изменённые backend-файлы проходят целевую проверку.
- mypy: FAIL на существующих ошибках вне изменённого слоя (`inventory_movement_report_service.py`, `wildberries_credentials_service.py`, `scripts/cleanup_fbs_stub_test_orders.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`, `wildberries_product_import_service.py`).
- pytest: `backend/tests/test_fbs_packing_box.py` — PASS, 8 passed.
- back_guard.py: NOT RUN: скрипт отсутствует в этой рабочей копии.
- check_migrations.py: NOT RUN: скрипт отсутствует в этой рабочей копии.

## Не реализовано

- Полный backend `mypy` не проходит из-за перечисленных ранее существовавших ошибок, не относящихся к карточке.

## Находки

- Legacy-префиксы в ключах коробов сохраняются для совместимости данных, но больше не влияют на режим поставки.

# Фича 2

# Backend development report · 03-no-distribution-mode

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py`

Режим переключается только после проверки назначений под блокировкой строки поставки. Повторное включение не перезаписывает аудит; явное выключение очищает legacy-префикс `no-distribution:` у коробов, после чего источником истины остаются поля поставки. Добавлен регрессионный тест идемпотентности и отключения legacy-поставки.

## Миграции

Нет: схема для этого атома уже добавлена предыдущей фичей.

## Тесты

- `pytest -q tests/test_fbs_packing_box.py` — 9 passed.

## Гейты

- `ruff check .` — не пройден: 80 существующих ошибок в несвязанных файлах; проверка изменённых файлов проходит.
- `mypy .` — не пройден: существующие ошибки в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py` и тестах; после исправления nullable-проверки новых ошибок в добавленном тесте нет.
- `pytest` — полный прогон запущен, остановлен во время длительного прогона после прохождения целевого набора; целевой набор зелёный.
- `back_guard.py` — недоступен: файл отсутствует в этой рабочей копии.
- `check_migrations.py` — недоступен: файл отсутствует в этой рабочей копии.

## Не реализовано

- Находки, относящиеся к API, workspace и frontend, не входят в backend-атом 2 и не изменялись.
- Полный репозиторный прогон невозможно объявить зелёным из-за предварительно существующих ошибок и отсутствующих CI-скриптов в этой копии.

## Блокеры

Нет блокеров для реализации атома; ограничения проверок описаны выше.

# Фича 3

# DEV · 03-no-distribution-mode

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/api/fbs_supplies.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md

## Гейты

- ruff: целевые файлы — PASS; полный `ruff check .` — FAIL на 80 ранее существовавших ошибках вне изменённых участков.
- mypy: FAIL на 21 ранее существовавшей ошибке в 6 файлах; изменённые файлы в диагностике не указаны.
- pytest: полный прогон — 813 passed, 5 skipped, 2 unrelated failed; целевой `pytest -q tests/test_fbs_packing_box.py` — PASS, 9 passed. Unrelated failures: exported OpenAPI snapshot and cutoff test with stale fixed date.
- back_guard.py: FAIL — файл `scripts/ci/back_guard.py` отсутствует в этой рабочей копии.
- check_migrations.py: FAIL — файл `scripts/ci/check_migrations.py` отсутствует в этой рабочей копии.

## Не реализовано

- Фронтендовые пункты REVIEW.md (E2E, подсказка и экран) не реализованы: они вне роли backend-dev и явно разрешённых backend-файлов.
- Миграций нет: атом использует уже существующие поля поставки.

## Находки

- Секреты, ключи, токены и `.env` не читались.
- В рабочем дереве присутствует несвязанный `night/volna-9-recovery/JOURNAL.md`; его не изменял.

# Фича 4

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx

Исправлена находка REVIEW-8: объяснение блокировки переключателя показывается только когда в короба действительно назначены заказы. При пустых коробах галка остаётся доступной без ложной подсказки. Поле поставки и API-переключатель уже были реализованы предыдущими атомами и не изменялись.

Указанный в карточке файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/openapi/fbs-operations.openapi.json` отсутствует в checkout, поэтому не создавался.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend` — красный/не выполнен: локальный `node_modules/.bin/tsc` отсутствует, первый запуск `npx` завис без вывода и остановлен.
- `python3 scripts/ui/ui_guard.py` — красный: зафиксированы нарушения `экран-монолит` в `src/components/WbProductPickerDialog.tsx` (0 → 646), `src/screens/v2/FfFbsSupplyWorkspace.tsx` (2493 → 2507) и `src/screens/v2/SellerInboundDraftScreen.tsx` (1111 → 1169). Базовая линия не обновлялась.
- `npm run test:unit` — красный: `vitest: command not found` (код 127).

## Не реализовано

- Backend-находки REVIEW-1–5 и REVIEW-8 (единый источник истины, legacy-выключение, атомарность, идемпотентный аудит, текст 409 и реестр B-09) не изменялись: они находятся вне разрешённых файлов и роли `screen-dev`.
- Обновление e2e-теста из REVIEW-6 не выполнялось: файл не входит в разрешённый список файлов экрана.
- OpenAPI-файл из REVIEW-9 не найден в checkout; создание файла вне реестра запрещено.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- Боевой прод и кабинет Wildberries не затрагивались.
