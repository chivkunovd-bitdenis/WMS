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

# DEV · 03-no-distribution-mode · атом 2 · переделка по ревью

## Что реализовано

- Эндпоинты: новых нет; существующее создание коробов через `POST /operations/fbs-supplies/{supply_id}/boxes` теперь сохраняет полный исходный ключ идемпотентности и не кодирует режим поставки в `creation_idempotency_key`.
- Сервис: `fbs_packing_box_service.create_boxes` хранит режим «Без распределения» только в полях поставки, а legacy-префикс `no-distribution:` оставляет только в fallback-чтении существующих данных.
- Сервис: два допустимых 128-символьных ключа с одинаковыми первыми 112 символами больше не коллидируют и создают разные короба.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` — новые короба сохраняют полный исходный ключ; удалены генерация legacy-ключа и проверка режима по ключу при новом идемпотентном повторе.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — добавлены проверки нового формата ключа и отсутствия коллизии двух максимальных ключей; сценарий повторного запроса обновлён под новый источник истины.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — отчёт текущего backend-прохода.

## Миграции

- Нет. Переделка использует добавляющие поля поставки из зависимости «фича 1» и схему не меняет.

## Тесты

- `test_without_distribution_boxes_do_not_accept_order_assignment` — дополнительно проверяет, что новый короб в режиме «Без распределения» хранит исходный ключ без `no-distribution:`.
- `test_without_distribution_toggle_preserves_full_key_for_create_retry` — проверяет полный 128-символьный ключ, выключение режима и идемпотентный повтор без дубля.
- `test_without_distribution_keeps_distinct_max_length_idempotency_keys` — воспроизводит находку ревью: ключи с общими первыми 112 символами и разными хвостами создают два разных короба и сохраняются без обрезки.
- Остальные тесты `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` проверяют переключение при пустых коробах, запрет при назначении и повторное разрешение после удаления назначения.

## Гейты

- Из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend`: `ruff check app/services/fbs_packing_box_service.py tests/test_fbs_packing_box.py` — PASS, `All checks passed!`.
- Из того же каталога: `mypy app/services/fbs_packing_box_service.py` — FAIL на одной ранее существующей ошибке импортируемого `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/wildberries_credentials_service.py:167`; в изменённом сервисе диагностик нет.
- Из того же каталога: `mypy --follow-imports=skip app/services/fbs_packing_box_service.py` — PASS, `Success: no issues found in 1 source file`.
- Из того же каталога: `pytest -q tests/test_fbs_packing_box.py` — PASS, `12 passed in 9.06s`.
- Из того же каталога: `pytest -q tests/test_fbs_packing_box.py tests/test_fbs_openapi_contract.py` — PASS, `16 passed in 12.55s`.
- `python3 scripts/ci/back_guard.py` — не применим: новый роут не добавлялся.
- `python3 scripts/ci/check_migrations.py` — не применим: миграция не добавлялась.

## Не реализовано

- Backend-находки 1 и 2 из `REVIEW.md`, относящиеся к файлам этого атома, исправлены буквально.
- Находка 3 из `REVIEW.md` относится к `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и исключена профилем `backend-dev` и границами атома.
- Следующие атомы карточки и соседние продуктовые задачи не затрагивались.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- Стандартный целевой `mypy` захватывает импортируемый соседний модуль с базовой ошибкой типов; изолированная проверка изменённого сервиса проходит.

## Блокеры

- Код, тесты и артефакт локально записаны в постоянной рабочей копии, но сохранить их отдельным Git-коммитом не удалось: команда `git add -- backend/app/services/fbs_packing_box_service.py backend/tests/test_fbs_packing_box.py night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` завершилась ошибкой `Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1/index.lock': Operation not permitted`. Текущий `HEAD` — `92bb49f6`; он не содержит эту переделку. Несвязанные изменения `JOURNAL.md`, `OTLOZHENO.md` и `REVIEW.md` не индексировались и не редактировались этой ролью.

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

# DEV · 03-no-distribution-mode · атом 4 · переделка по ревью

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` — добавлена версия мутаций workspace: успешное переключение режима инвалидирует фоновые GET-запросы, начатые до операции или во время неё, поэтому их поздний ответ больше не откатывает галку и нейтральную шапку. Итоговое число строк файла не выросло относительно текущего `HEAD` (2504 строки до и после правки).
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/tests-e2e/ff-fbs-supply.spec.ts` — прежняя последовательная проверка фонового обновления заменена регрессией из ревью: старый GET фиксирует снимок `false` и задерживается, POST успешно возвращает `true`, затем старый GET освобождается; тест проверяет, что режим и нейтральная шапка остаются включёнными.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — отчёт роли `screen-dev`.

## Гейты

- Из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend`: `npx tsc --noEmit -p tsconfig.app.json` — **зелёный**, exit code 0.
- Из корня: `python3 scripts/ui/ui_guard.py` — **красный на существующей базовой линии**, exit code 1: `src/components/WbProductPickerDialog.tsx` 0 → 646, `src/screens/v2/FfFbsSupplyWorkspace.tsx` 2493 → 2505, `src/screens/v2/SellerInboundDraftScreen.tsx` 1111 → 1169. Базовая линия не обновлялась, чужие экраны не трогались; затронутый `FfFbsSupplyWorkspace.tsx` содержит 2504 физические строки и не вырос относительно текущего `HEAD`.
- Из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend`: `npm run test:unit -- --run src/screens/v2/fbsApi.test.ts` — **зелёный**, 1 файл, 5 тестов прошли.
- Из того же каталога: `npx eslint tests-e2e/ff-fbs-supply.spec.ts` — **зелёный**, exit code 0.
- Из того же каталога: `npx playwright test --list tests-e2e/ff-fbs-supply.spec.ts --grep 'boxes without distribution (follows assigned orders|ignores stale background refresh after toggle)'` — **зелёный**, оба целевых сценария найдены и компилируются.
- Из того же каталога: `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'boxes without distribution (follows assigned orders|ignores stale background refresh after toggle)'` — **красный до запуска браузерных кейсов**: локальный API не смог привязаться к `127.0.0.1:18000`, `operation not permitted`; Playwright завершился с exit code 1.
- Из корня: `git diff --check` — **зелёный**, exit code 0.

## Не реализовано

- Живой браузерный прогон двух названных сценариев не выполнен: среда запретила Playwright webServer открыть локальный порт `18000`. Сами сценарии обнаруживаются и проходят загрузку/компиляцию через `playwright test --list`.
- Находки 1 и 2 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/REVIEW.md` относятся к backend-слою предыдущего атома и не входят в роль `screen-dev`; в текущем `HEAD` они уже сохранены отдельным коммитом `c1cb8e58` и в этом проходе не менялись.
- Буквальный `tasks/<slug>/CONTRACT.md` в рабочей копии отсутствует. Переделка выполнена строго по атому 4 из `FEATURES.md`, экранной находке 3 из `REVIEW.md` и экрану S-03 из `frontend/screens.registry.json`; новых продуктовых решений не добавлено.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

## Блокеры

- Изменения локально записаны в постоянной рабочей копии, но отдельный Git-коммит создать невозможно: `git add -- frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx frontend/tests-e2e/ff-fbs-supply.spec.ts night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` завершился ошибкой `Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1/index.lock': Operation not permitted`. Текущий `HEAD` — `c1cb8e58`; он не содержит экранную переделку этого прохода. Несвязанное изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/JOURNAL.md` не редактировалось и не индексировалось этой ролью.
