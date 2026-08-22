# Фича 1

# DEV · 03-no-distribution-mode · rework атома 1

## Что реализовано

- Эндпоинты: новых нет; существующий `POST /operations/fbs-supplies/{supply_id}/boxes-without-distribution` теперь безопасно выключает режим и для коробов, созданных с максимально допустимым 128-символьным ключом.
- Сервис: `fbs_packing_box_service` переводит legacy-ключ `no-distribution:` в retired-маркер той же длины, поэтому значение остаётся в пределах `fbs_packing_boxes.creation_idempotency_key VARCHAR(128)` и повтор исходного создания по-прежнему находит тот же короб.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` — retired-маркер заменён на 16-символьный `retired-no-dist:`, равный по длине legacy-маркеру.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — регрессионный сценарий переключения использует разрешённый API-ключ длиной 128 символов и проверяет длину сохранённого retired-ключа.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — отчёт backend-разработки.

## Миграции

- Новых нет. Добавляющая миграция `20260821_0094` из исходного атома сохраняется без изменений и добавляет в `fbs_supplies` поля `boxes_without_distribution_at` и `boxes_without_distribution_by_user_id`.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py::test_without_distribution_toggle_preserves_legacy_key_for_create_retry` — создаёт короб с режимом и ключом длиной 128 символов, выключает режим, проверяет 128-символьное значение в БД и успешный идемпотентный повтор без дубля.
- Полный `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` также прошёл внутри общего прогона; он покрывает сохранение признака поставки после удаления и повторного создания пустых коробов.

## Гейты

- ruff (из `backend/`): `ruff check .` — FAIL, 80 ранее существующих ошибок в несвязанных файлах; изменённые файлы в диагностике отсутствуют.
- ruff (целевой): `ruff check app/services/fbs_packing_box_service.py tests/test_fbs_packing_box.py` — PASS.
- mypy (из `backend/`): `mypy .` — FAIL, 21 ранее существующая ошибка в 6 несвязанных файлах; изменённый сервис в диагностике отсутствует.
- pytest (целевой): `pytest -q tests/test_fbs_packing_box.py -k 'toggle_preserves_legacy_key_for_create_retry'` — PASS, `1 passed, 10 deselected`.
- pytest (из `backend/`): `pytest` — FAIL, `1 failed, 816 passed, 5 skipped`; единственное падение `test_fbs_cutoff_autoplans_supply_manual_date_and_calendar` использует дату `2026-08-15` и на текущую дату получает несвязанный `deadline_passed`. Все 11 тестов `test_fbs_packing_box.py` прошли.
- back_guard.py (из корня): NOT RUN — файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/back_guard.py` отсутствует.
- check_migrations.py (из корня): NOT RUN — файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Находка 2 из `REVIEW.md` относится к `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`; она не реализована, потому что роль этого прохода строго `backend-dev`.
- Другие атомы и соседние продуктовые задачи не изменялись.

## Находки

- В репозитории остаются несвязанные базовые ошибки `ruff`, `mypy` и один зависящий от текущей даты тест; они перечислены буквально в секции «Гейты».
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- `git commit` не выполнен: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1/index.lock` (`Operation not permitted`). Backend-rework существует только в локальном рабочем дереве и пока не имеет восстанавливаемого commit SHA.

## Блокеры

- Реализация не заблокирована, но её обязательное сохранение в Git заблокировано правами среды на служебный каталог worktree. Отсутствующие CI-скрипты и красная базовая линия отдельно отражены в гейтах.

# Фича 2

# DEV · 03-no-distribution-mode · переделка атома 2

## Что реализовано

- Эндпоинты: новых нет; существующее выключение режима через `POST /operations/fbs-supplies/{supply_id}/boxes-without-distribution` не переполняет `fbs_packing_boxes.creation_idempotency_key` для разрешённого ключа длиной 128 символов.
- Сервис: `fbs_packing_box_service` заменяет legacy-префикс `no-distribution:` на равный ему по длине `retired-no-dist:`, сохраняя значение в пределах `VARCHAR(128)` и возможность идемпотентно найти прежний короб при повторе создания.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` — retired-маркер сделан 16-символьным, как legacy-маркер; максимальная длина сохранённого ключа остаётся 128 символов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — регрессионный сценарий использует максимальный 128-символьный API-ключ и проверяет длину и значение retired-ключа после выключения режима.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — отчёт этого backend-прохода.

## Миграции

- Новых нет. Добавляющая миграция `20260821_0094` из зависимости «фича 1» не изменялась.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py::test_without_distribution_toggle_preserves_legacy_key_for_create_retry` — создаёт короб с ключом длиной 128 символов, выключает режим, проверяет ровно 128 символов в БД и успешный повтор без дубля.
- Полный целевой файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` покрывает включение после создания пустого короба, удаление и пересоздание короба, выключение режима, доменную ошибку при назначенном заказе и повторное разрешение после удаления назначения.

## Гейты

- Из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend`: `ruff check app/services/fbs_packing_box_service.py tests/test_fbs_packing_box.py` — PASS, `All checks passed!`.
- Из того же каталога: `mypy app/services/fbs_packing_box_service.py` — FAIL на ранее существующей ошибке импортируемого `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/wildberries_credentials_service.py:167`; изменённый сервис в диагностике отсутствует.
- Из того же каталога: `mypy --follow-imports=skip app/services/fbs_packing_box_service.py` — PASS, `Success: no issues found in 1 source file`.
- Из того же каталога: `pytest -q tests/test_fbs_packing_box.py` — PASS, `11 passed in 16.57s`.
- `python3 scripts/ci/back_guard.py` — не применим: текущая переделка не добавляет роут.
- `python3 scripts/ci/check_migrations.py` — не применим: текущая переделка не добавляет миграцию.

## Не реализовано

- Находка 2 из `REVIEW.md` относится к `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и не входит в роль `backend-dev` и файлы этого атома.
- Следующие атомы карточки и соседние продуктовые задачи не затрагивались.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- Стандартный целевой `mypy` захватывает импортируемый соседний модуль с базовой ошибкой типов; отдельная проверка изменённого сервиса без обхода импортов зелёная.
- Backend-исправление и его регрессионный тест сохранены в Git-коммите `13ab613e275ce5445327fc7655a3d3614b41e563`.

## Блокеры

- Текущую редакцию `DEV.md` не удалось закоммитить: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1/index.lock` (`Operation not permitted`). Артефакт записан в требуемый файл рабочей копии, но его новые результаты гейтов пока не имеют отдельного commit SHA.

# Фича 3

# DEV · 03-no-distribution-mode · атом 3 · переделка по ревью

## Что реализовано

- `POST /operations/fbs-supplies/{supply_id}/boxes-without-distribution` — проверен контракт: операция возвращает обновлённый workspace, сохраняет `supply.boxes_without_distribution` без коробов и отвечает `409 boxes_already_distributed`, не меняя состояние, если заказ уже назначен.
- `fbs_packing_box_service` — служебный ключ выключенного legacy-режима теперь всегда обрезается до фактического предела колонки `String(128)` независимо от длины префикса; допустимый 128-символьный API-ключ больше не может привести к ошибке PostgreSQL при выключении режима.
- `fbs_workspace_service` — проверено целевым API-тестом, что workspace читает сохраняемый признак поставки после удаления последнего короба.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` — введён единый предел длины служебного ключа и безопасное усечение содержимого при создании и снятии legacy-маркера.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — API-сценарий расширен буквальной проверкой `создать короб → удалить последний короб → GET workspace`, после которой признак режима остаётся `true`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — отчёт переделки backend-атома.

## Миграции

- Нет: переделка не меняет схему и использует добавляющие поля атома 1.

## Тесты

- `test_without_distribution_toggle_preserves_legacy_key_for_create_retry` — принимает максимальный API-ключ длиной 128 символов, выключает режим, проверяет длину сохранённого ключа и успешный идемпотентный повтор без дубля короба.
- `test_boxes_without_distribution_api_returns_persisted_workspace_flag` — включает режим отдельной API-операцией на пустой поставке, создаёт и удаляет последний короб, затем проверяет сохранённый `true` в новом workspace.
- `test_boxes_without_distribution_api_conflicts_when_order_is_assigned` — проверяет понятный `409 boxes_already_distributed` и отсутствие изменения состояния при назначенном заказе.

## Гейты

- `ruff check app/services/fbs_packing_box_service.py tests/test_fbs_packing_box.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend` — PASS: `All checks passed!`.
- `mypy app/services/fbs_packing_box_service.py app/api/fbs_supplies.py app/services/fbs_workspace_service.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend` — FAIL из-за 4 существующих ошибок в импортируемых несвязанных файлах `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; в трёх проверяемых файлах атома диагностик нет.
- `mypy --follow-imports=skip app/services/fbs_packing_box_service.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend` — PASS: `Success: no issues found in 1 source file`; это изолированная проверка изменённого сервиса без базовых ошибок импортируемых соседей.
- `pytest -q tests/test_fbs_packing_box.py tests/test_fbs_openapi_contract.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend` — PASS: `15 passed in 11.15s`.
- `back_guard.py` не применим: эта переделка не добавляет новый роут; маршрут атома уже существовал до текущего изменения.
- `check_migrations.py` не применим: миграций в переделке нет.

## Не реализовано

- Находка 2 из `REVIEW.md` о фоновой синхронизации checkbox находится в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`; frontend исключён профилем `backend-dev` и границами этого атома.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

## Блокеры

- Backend-изменение локально реализовано и проверено, но не сохранено отдельным Git-коммитом: `git add backend/app/services/fbs_packing_box_service.py backend/tests/test_fbs_packing_box.py night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1/index.lock` и завершился с `Operation not permitted`. Текущий восстановимый HEAD — `53b54bda5b22f65c76271cd32152d68ac264600d`, он не содержит эту переделку. Чужое изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/JOURNAL.md` в индекс не добавлялось.

# Фича 4

# DEV · 03-no-distribution-mode · экран S-03 · переделка по ревью

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` — удалено отдельное локальное состояние режима; галка и нейтральная шапка теперь читают один серверный признак `workspace.supply.boxes_without_distribution`, поэтому фоновый опрос не может показать противоречащие состояния.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/tests-e2e/ff-fbs-supply.spec.ts` — добавлен регрессионный сценарий двух внешних переключений режима через фоновое обновление workspace: `false → true` и `true → false`; он проверяет одновременно галку и текст шапки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — отчёт роли `screen-dev`.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend` — **зелёный**, exit code 0.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode` — **красный на существующей базовой линии**: `src/components/WbProductPickerDialog.tsx` 0 → 646, `src/screens/v2/FfFbsSupplyWorkspace.tsx` 2493 → 2505, `src/screens/v2/SellerInboundDraftScreen.tsx` 1111 → 1169. Базовая линия не обновлялась. До этой переделки `FfFbsSupplyWorkspace.tsx` уже имел 2507 строк; текущая правка уменьшила его до 2505 и не добавила новое превышение.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend` — **зелёный**: 19 файлов, 138 тестов прошли.
- `npx eslint tests-e2e/ff-fbs-supply.spec.ts` — **зелёный**, exit code 0.
- `npx playwright test --list tests-e2e/ff-fbs-supply.spec.ts --grep 'boxes without distribution follows (assigned orders|background refresh)'` — **зелёный**: оба целевых сценария обнаружены и загружаются Playwright без ошибок компиляции.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'boxes without distribution follows (assigned orders|background refresh)'` — **не запущен до браузерного шага**: Playwright webServer не смог привязать локальный API к `127.0.0.1:18000`, `operation not permitted`. Это ограничение среды; продуктовый сценарий в живом браузере здесь не подтверждён.

## Не реализовано

- Живой браузерный прогон названных сценариев не выполнен, потому что среда запретила запуск локального API на порту `18000`.
- Находка 1 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/REVIEW.md` относится к backend-сервису предыдущего атома и не входит в роль `screen-dev`; этот слой не менялся.
- Буквальный `tasks/<slug>/CONTRACT.md` в рабочей копии отсутствует. Переделка выполнена по явно заданному атому 4 из `FEATURES.md` и экранной находке 2 из `REVIEW.md`; новые продуктовые решения не добавлялись.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- Отдельный Git-коммит создать не удалось: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1/index.lock` и завершает `git add` с `Operation not permitted`. Изменения остаются только в постоянной рабочей копии; проверенного commit SHA для этой переделки нет. Чужое изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/JOURNAL.md` не добавлялось и не редактировалось.
