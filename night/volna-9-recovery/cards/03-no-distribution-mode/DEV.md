# Фича 1

# Backend Dev — 03-no-distribution-mode — атом 1

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/models/fbs_supply.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/alembic/versions/20260821_0094_fbs_supplies_boxes_without_distribution.py

В `FbsSupply` добавлены сохраняемые поля `boxes_without_distribution_at` и `boxes_without_distribution_by_user_id`. Миграция `20260821_0094` добавляет nullable-поля и внешний ключ на `users` с `SET NULL`; состояние теперь живёт на поставке и не зависит от жизненного цикла коробов.

## Миграции

- `20260821_0094` — добавляет время включения режима, пользователя-переключателя и внешний ключ на `users`.

## Тесты

- `backend/tests/test_fbs_packing_box.py` — целевой прогон: 8 passed.

## Гейты

- ruff: FAIL — 82 существующие ошибки в несвязанных файлах; изменённые файлы отдельно проходят проверку.
- mypy: FAIL — 21 существующая ошибка в 6 несвязанных файлах; изменённые файлы новых ошибок не добавили.
- pytest: PASS — `tests/test_fbs_packing_box.py`, 8 passed.
- back_guard.py: NOT RUN — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/back_guard.py` отсутствует.
- check_migrations.py: NOT RUN — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Сервис переключения, API/workspace и UI не изменялись: это следующие атомарные фичи из `FEATURES.md`.
- Массовая миграция legacy-ключей `no-distribution:` не выполнялась; совместимость остаётся в следующих слоях.

## Находки

- Секреты, ключи, токены и `.env` не читались.
- Боевой прод и живой кабинет Wildberries не затрагивались.

# Фича 2

# Backend Dev — 03-no-distribution-mode — атом 2

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py

Сервис `set_boxes_without_distribution` теперь разрешает включать и выключать режим при любом количестве пустых коробов. Изменение блокируется только при наличии хотя бы одного `FbsPackingBoxItem` в коробах этой поставки; после удаления назначения переключение снова разрешено. Новое состояние записывается в поля поставки, а legacy-приписка `no-distribution:` остаётся только совместимым чтением существующего поведения.

## Миграции

Нет: поля поставки и миграция добавлены атомом 1.

## Тесты

- `backend/tests/test_fbs_packing_box.py::test_without_distribution_mode_depends_on_assignments_not_box_count` — пустой короб, удаление и пересоздание, выключение режима, запрет при назначении и повторное включение после удаления назначения.

## Гейты

- ruff: PASS — изменённые backend-файлы.
- mypy: FAIL — существующая ошибка в `backend/app/services/wildberries_credentials_service.py:167`, вне изменённых файлов.
- pytest: PASS — `backend/tests/test_fbs_packing_box.py`, 8 passed.
- back_guard.py: NOT RUN — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/back_guard.py` отсутствует.
- check_migrations.py: NOT RUN — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- API, workspace и UI не входят в этот атом и не изменялись.
- Массовая миграция legacy-прицепок `no-distribution:` не входит в контракт; совместимое чтение сохранено.

## Находки

- Секреты, ключи, токены и `.env` не читались.
- Боевой прод и живой кабинет Wildberries не затрагивались.

# Фича 3

# Backend-dev: 03-no-distribution-mode

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/api/fbs_supplies.py` — POST `/operations/fbs-supplies/{supply_id}/boxes-without-distribution` принимает `enabled`, возвращает обновлённый workspace и переводит конфликт назначенных заказов в HTTP 409.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_workspace_service.py` — workspace отдаёт сохранённый признак поставки независимо от наличия коробов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — API-проверки сохранения режима без коробов и конфликтного ответа при назначенном заказе.

Реализация этих файлов уже находилась в текущей рабочей копии; в рамках backend-dev она проверена без расширения объёма.

## Гейты

- `ruff check .` — FAIL: 82 pre-existing ошибок в несвязанных файлах backend и scripts; `fbs_workspace_service.py` отмечен только неиспользуемым `noqa`.
- `mypy .` — FAIL: 21 pre-existing ошибок в 6 несвязанных файлах; ошибок в затронутом API/workspace коде нет.
- `pytest` — INTERRUPTED after 5% (41 passed before stop); целевой `pytest -q tests/test_fbs_packing_box.py` — PASS, 8 passed.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в текущем checkout.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в текущем checkout.

## Не реализовано

- Новых изменений сверх атомарной backend-фичи не добавлялось.
- Product/browser gate и frontend не входят в роль backend-dev.

## Блокеры

- Полные lint/type-check и guard-гейты заблокированы существующими ошибками/отсутствующими скриптами, перечисленными выше; целевые тесты фичи проходят. Полный pytest не завершён из-за длительного прогона и остановлен после проверки первых 41 теста.

# Фича 4

# Screen dev — 03-no-distribution-mode — фича 4

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx

Экран использует сохранённый признак `workspace.supply.boxes_without_distribution` как источник истины для нейтральной шапки. Поэтому режим не сбрасывается визуально после удаления и повторного создания пустых коробов. Переключатель остаётся доступным без назначений и блокируется только при наличии назначенных заказов; tooltip объясняет, что сначала нужно убрать назначения из коробов.

Изменения API-типа и операции переключения уже присутствовали в предыдущем атоме в текущей ветке:

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/fbsApi.ts

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend`) — PASS.
- `python3 scripts/ui/ui_guard.py` (из корня) — FAIL: существующие/предыдущие нарушения `экран-монолит` в `src/components/WbProductPickerDialog.tsx` (0 → 646), `src/screens/v2/FfFbsSupplyWorkspace.tsx` (2493 → 2503) и `src/screens/v2/SellerInboundDraftScreen.tsx` (1111 → 1169). Базовую линию не обновлял.
- `npm run test:unit` (из frontend) — FAIL до запуска тестов: `vitest: command not found`.

## Не реализовано

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/openapi/fbs-operations.openapi.json` отсутствует в checkout. Фактический OpenAPI-файл находится в `tasks/fbs-operator-flow/openapi`, но он не входит в разрешённые файлы экрана S-03, поэтому не изменялся.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- Боевой прод и живой кабинет Wildberries не затрагивались.
