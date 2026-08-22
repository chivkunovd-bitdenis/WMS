# Фича 1

# DEV · 03-no-distribution-mode · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/alembic/versions/20260821_0094_fbs_supplies_boxes_without_distribution.py` — добавляющая миграция 0094: nullable-время включения режима и nullable UUID пользователя с FK `ON DELETE SET NULL`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/models/fbs_supply.py` — поля `boxes_without_distribution_at` и `boxes_without_distribution_by_user_id` в `FbsSupply`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — отчёт backend-разработки.

## Миграции

- `20260821_0094` — добавляет в `fbs_supplies` `boxes_without_distribution_at` и `boxes_without_distribution_by_user_id`; данных и существующих таблиц не удаляет. `alembic heads` подтверждает, что это единственная head-ревизия.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — проверяет сохранение режима через удаление и повторное создание пустых коробов.
- Проверка метаданных `FbsSupply` подтвердила nullable-поля и FK пользователя с `ON DELETE SET NULL`.

## Гейты

- ruff: FAIL — 80 ранее существующих ошибок в несвязанных файлах; изменённые миграция и модель в выводе отсутствуют.
- mypy: FAIL — 21 ранее существующая ошибка в 6 несвязанных файлах; изменённые миграция и модель в выводе отсутствуют.
- pytest: целевые `tests/test_fbs_packing_box.py tests/test_fbs_operator_flow_migration.py` — PASS, `11 passed, 1 skipped`; полный `pytest` был запущен и собрал 822 теста, но его итоговый вывод не вернулся из исполнителя.
- back_guard.py: NOT RUN — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/back_guard.py` отсутствует.
- check_migrations.py: NOT RUN — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Ничего в пределах атома 1. Замечание `REVIEW.md` о повторной идемпотентности POST после выключения режима относится к сервису коробов — атому 2 из `FEATURES.md`; этот атом намеренно не смешивался с хранением схемы и модели.

## Находки

- Нет.

# Фича 2

# DEV · 03-no-distribution-mode · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` — при явном выключении режима legacy-ключ переведён в нейтральный ключ совместимости; отложенный повтор исходного `create_boxes(..., without_distribution=true)` по прежнему ключу находит тот же короб, не создаёт дубль и не включает режим повторно.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — регрессия последовательности «создать короб без распределения → выключить режим → повторить исходное создание»: проверяет один и тот же короб, выключенный режим и сохранённую возможность идемпотентного поиска.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — этот отчёт.

## Гейты

- `ruff check app/services/fbs_packing_box_service.py tests/test_fbs_packing_box.py` — PASS.
- `ruff check .` — FAIL: 80 ранее существовавших ошибок в несвязанных файлах; изменённые файлы в выводе отсутствуют.
- `mypy .` — FAIL: 21 ранее существовавшая ошибка в 6 несвязанных файлах; изменённые файлы атома в выводе отсутствуют.
- `pytest -q tests/test_fbs_packing_box.py -k 'toggle_preserves_legacy_key_for_create_retry'` — PASS: `1 passed, 10 deselected`.
- `pytest` — запущен: собрал 822 теста, но исполнитель завершил вывод без итоговой строки после начала прогона; результат полного прогона не подтверждён. Целевой регрессионный тест завершился успешно.
- `python3 scripts/ci/back_guard.py` — NOT RUN: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/back_guard.py` нет.
- `python3 scripts/ci/check_migrations.py` — NOT RUN: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/check_migrations.py` нет.

## Не реализовано

- Находка `REVIEW.md` о browser E2E относится к фронтенд-слою и этому backend-атому не принадлежит.
- Миграций нет: изменение использует существующее поле поставки и только сохраняет идемпотентность legacy-ключа.

## Находки

- Секреты, ключи, токены и `.env` не читались.
- Git commit не создан: Git не смог открыть lock-файл `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1/index.lock` (`Operation not permitted`). Изменения существуют только в локальном незакоммиченном рабочем дереве.

# Фича 3

# DEV · 03-no-distribution-mode · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/api/fbs_supplies.py` — `POST /operations/fbs-supplies/{supply_id}/boxes-without-distribution` принимает `enabled`, вызывает сервис и возвращает обновлённый workspace; доменный конфликт назначенных заказов отображается как `409 boxes_already_distributed`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_workspace_service.py` — workspace получает `supply.boxes_without_distribution` из сохраняемого состояния поставки, в том числе без коробов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` — исправлена серверная находка ревью: выключение режима сохраняет адресуемость legacy-ключа для повторного `POST /boxes`, поэтому повтор возвращает исходный короб и не создаёт дубль.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — покрыты API-возврат workspace, сохранение флага после повторного чтения, конфликт при назначенном заказе и регрессия идемпотентного повтора после выключения режима.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — отчёт backend-разработки.

## Миграции

- Нет: атом 3 использует добавляющие поля из атома 1 и не меняет схему.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — API-переключение на пустой поставке, устойчивость флага при пустом списке коробов, `409` при назначении и безопасный повтор создания после выключения режима.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_openapi_contract.py` — контракт OpenAPI для FBS API.

## Гейты

- `ruff check .` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend` — FAIL: 80 существующих ошибок в несвязанных файлах; файлов этого атома в диагностике нет.
- `mypy .` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend` — FAIL: 21 существующая ошибка в 6 несвязанных файлах; файлов этого атома в диагностике нет.
- `pytest -q tests/test_fbs_packing_box.py tests/test_fbs_openapi_contract.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend` — PASS: целевой запуск завершился без ошибок.
- `pytest` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend` — запуск начат, собраны 822 теста; исполнитель прекратил передачу вывода во время прогона, итоговая строка не получена.
- `python3 scripts/ci/back_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode` — NOT RUN: файла `scripts/ci/back_guard.py` в этой рабочей копии нет.
- `python3 scripts/ci/check_migrations.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode` — NOT RUN: файла `scripts/ci/check_migrations.py` в этой рабочей копии нет.

## Не реализовано

- Находка `REVIEW.md` о browser E2E относится к `frontend/tests-e2e/ff-fbs-supply.spec.ts` и экрану S-03; она вне разрешённой backend-роли и этого атома.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 4

# DEV · 03-no-distribution-mode · экран S-03

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не запущен: локальный `typescript` отсутствует, а `npx` не смог загрузить его из-за `ENOTFOUND registry.npmjs.org`.
- `python3 scripts/ui/ui_guard.py` — красный. Базовая линия уже превышена: `src/components/WbProductPickerDialog.tsx` (0 → 646), `src/screens/v2/FfFbsSupplyWorkspace.tsx` (2493 → 2507), `src/screens/v2/SellerInboundDraftScreen.tsx` (1111 → 1169). Базовая линия не обновлялась.
- `npm run test:unit` — не запущен: `vitest: command not found`.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'boxes without distribution follows assigned orders'` — не запущен: локальный `playwright` отсутствует, а `npx` не смог загрузить его из-за `ENOTFOUND registry.npmjs.org`.
- `git commit` — не выполнен: среда запретила создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1/index.lock` (`Operation not permitted`). Изменения остаются незакоммиченными в этой рабочей копии.

## Не реализовано

- Находка 1 из `REVIEW.md` относится к `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py`; это бэкенд-слой другого атома и не менялся ролью `screen-dev`.
- Буквальный контракт `tasks/<slug>/CONTRACT.md` в рабочей копии отсутствует. Для переделки использованы заданный атом 4 из `FEATURES.md` и относящаяся к экрану находка 2 из `REVIEW.md`.

## Находки

- Усиленный E2E покрывает S-03-TC-001, S-03-TC-002 и S-03-TC-003: доступность после пустого короба, сохранение режима после удаления/повторного открытия, а также блокировку по назначению и повторную доступность после очистки.
