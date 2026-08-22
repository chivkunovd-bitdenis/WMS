# Фича 1

# Backend Dev — 03-no-distribution-mode

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/models/fbs_supply.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/alembic/versions/20260821_0094_fbs_supplies_boxes_without_distribution.py

Добавлены сохраняемые поля `boxes_without_distribution_at` и `boxes_without_distribution_by_user_id` на `FbsSupply`; миграция добавляет nullable-колонки и внешний ключ на `users` с `SET NULL`.

## Гейты

- ruff: PASS для изменённых backend-файлов; полный `ruff check .` — FAIL из-за 82 существующих ошибок вне этого изменения.
- mypy: PASS.
- pytest: PASS.
- back_guard.py: NOT RUN — файл отсутствует в этой рабочей копии.
- check_migrations.py: NOT RUN — файл отсутствует в этой рабочей копии.
- `git diff --check`: PASS.
- commit: BLOCKED — Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1/index.lock` из-за ограничений записи sandbox.

## Не реализовано

- Переключение режима в сервисе, чтение legacy-ключа коробов, API и workspace относятся к следующим атомарным фичам из FEATURES.md и намеренно не изменялись.

# Фича 2

# Backend Dev — 03-no-distribution-mode — фича 2

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py

## Реализовано

- Добавлен сервис `set_boxes_without_distribution`: режим меняется при пустых коробах независимо от их количества.
- При наличии хотя бы одного `FbsPackingBoxItem` переключение отклоняется доменной ошибкой `boxes_already_distributed`; после удаления назначения снова разрешается.
- Новое состояние записывается в поля поставки, а legacy-приписка `no-distribution:` не изменялась и продолжает читаться существующими путями совместимости.
- Добавлен интеграционный тест полного сценария: пустой короб → включение → удаление и пересоздание → выключение → назначение/запрет → удаление назначения/повторное включение.

## Гейты

- ruff: PASS для изменённых файлов; полный `ruff check .` — FAIL на 82 существующих ошибках вне этого изменения.
- mypy: FAIL на 19 существующих ошибках вне изменённых файлов; ошибок в изменённых файлах нет.
- pytest: целевой тест PASS; полный прогон остановлен после 152 PASS и 3 skipped из 817 за 4:57 (KeyboardInterrupt, итоговый код неуспешный).
- back_guard.py: NOT RUN — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/back_guard.py` отсутствует.
- check_migrations.py: NOT RUN — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/check_migrations.py` отсутствует.
- git commit: BLOCKED — Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1/index.lock` из-за ограничений sandbox.

## Не реализовано

- API и workspace не менялись: они относятся к следующей атомарной фиче 3.
- Миграции не менялись: поля поставки уже добавлены предыдущей фичей 1.

## Находки

- В рабочем дереве до начала работы уже были изменения `night/volna-9-recovery/JOURNAL.md` и удалённый прежний `DEV.md`; они не относятся к этой реализации и не включались в изменения backend.

# Фича 3

# Backend Dev — 03-no-distribution-mode — фича 3

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/api/fbs_supplies.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_workspace_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py

Добавлен POST `/operations/fbs-supplies/{supply_id}/boxes-without-distribution`. Он вызывает существующий сервис переключения, возвращает обновлённый workspace и переводит `boxes_already_distributed` в HTTP 409. В workspace добавлено `supply.boxes_without_distribution`; признак читается из сохранённого поля поставки и не исчезает при пустом списке коробов.

## Миграции

Нет: поля поставки и миграция добавлены предыдущей фичей.

## Тесты

Добавлены API-тесты на включение режима без коробов, сохранение флага при повторном GET workspace и конфликт при назначенном заказе.

## Гейты

- ruff: FAIL — существующий `RUF100` для `# ruff: noqa: RUF001` в `/backend/app/services/fbs_workspace_service.py`.
- mypy: FAIL — 4 существующие ошибки в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; изменённые файлы новых ошибок не добавили.
- pytest: PASS — целевые тесты `tests/test_fbs_packing_box.py -k boxes_without_distribution_api`: 2 passed.
- back_guard.py: NOT RUN — файл отсутствует в рабочей копии.
- check_migrations.py: NOT RUN — файл отсутствует в рабочей копии.
- git diff --check: PASS.

## Не реализовано

- UI и OpenAPI-файл не изменялись: они относятся к фиче 4 и находятся вне backend-dev атомарного куска.
- Массовая миграция legacy-ключей `no-distribution:` не выполнялась: контракт оставляет совместимость на чтение существующего формата.

## Находки

- Секреты, ключи, токены и `.env` не читались.
- В рабочем дереве до этой работы уже были изменения `night/volna-9-recovery/JOURNAL.md`; они не относятся к реализации и не включались в отчёт как изменённый backend-файл.

# Фича 4

# Screen dev — 03-no-distribution-mode

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/fbsApi.ts
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — PASS.
- `python3 scripts/ui/ui_guard.py` — FAIL: сообщает о новых нарушениях «экран-монолит» для `src/screens/v2/FfFbsSupplyWorkspace.tsx` (2493 → 2503), а также для существующих затронутых файлов `WbProductPickerDialog.tsx` и `SellerInboundDraftScreen.tsx`; базовая линия не обновлялась.
- `npm run test:unit` — FAIL: `vitest: command not found`, локальные зависимости для unit-тестов не установлены.

## Не реализовано

- OpenAPI-файл по указанному в карточке пути `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/openapi/fbs-operations.openapi.json` отсутствует. Фактический файл находится в `tasks/fbs-operator-flow/openapi`, но он не входит в разрешённый список файлов экранного реестра, поэтому не изменялся.

## Находки

- Секреты, ключи, токены и `.env` не читались.
