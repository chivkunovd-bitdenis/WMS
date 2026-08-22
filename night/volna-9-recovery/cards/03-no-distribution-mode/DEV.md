# Фича 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` — сохранена обратная совместимость с legacy-префиксом; старый POST создания коробов теперь проверяет назначения до включения режима.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_workspace_service.py` — workspace учитывает legacy-режим старых поставок.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — добавлен регрессионный тест обхода охраны через старый POST.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/tasks/fbs-operator-flow/openapi/fbs-operations.openapi.json` — экспортирован новый маршрут.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/docs/blockers/S-03.md` — B-09 приведён к правилу «есть назначение», а не «есть короб».

## Гейты

- ruff: целевые изменённые backend-файлы — PASS; полный `ruff check .` — FAIL на 80 существующих ошибках репозитория.
- mypy: FAIL на 21 существующей ошибке в 6 несвязанных файлах; новых ошибок изменённого слоя не выявлено.
- pytest: целевые `tests/test_fbs_packing_box.py` и `tests/test_fbs_openapi_contract.py` — PASS, 14 passed; полный прогон прерван после длительного выполнения без итогового результата.
- back_guard.py: NOT RUN — `scripts/ci/back_guard.py` отсутствует в этой рабочей копии.
- check_migrations.py: NOT RUN — `scripts/ci/check_migrations.py` отсутствует в этой рабочей копии.

## Не реализовано

- Фронтовой браузерный тест из находки 3 не менялся: это слой screen-dev, вне роли backend-dev.

## Находки

- В рабочем дереве присутствовали несвязанные изменения ночного оркестратора (`JOURNAL.md`, `REVIEW.md`); они не включались в реализацию.

# Фича 2

# DEV · 03-no-distribution-mode

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` — назначение заказа теперь учитывает legacy-признак `no-distribution:` так же, как сохранённый признак поставки; старые поставки не обходят запрет.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — добавлен регрессионный тест старой поставки с legacy-префиксом.

## Гейты

- `ruff check app/services/fbs_packing_box_service.py tests/test_fbs_packing_box.py` — PASS.
- `mypy .` — FAIL на 17 существующих диагностик в несвязанных файлах; изменённые файлы в выводе отсутствуют.
- `pytest -q tests/test_fbs_packing_box.py` — PASS, 11 passed.
- `pytest` — 816 passed, 5 skipped, 1 unrelated failure: `tests/test_fbs_supply_from_orders.py::test_fbs_cutoff_autoplans_supply_manual_date_and_calendar` получает `deadline_passed` для фиксированной даты 2026-08-15.
- `python3 scripts/ci/back_guard.py` — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/back_guard.py` нет.
- `python3 scripts/ci/check_migrations.py` — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/check_migrations.py` нет.

## Не реализовано

- Остальные находки ревью относятся к API/OpenAPI, frontend E2E и документации B-09; в этот backend-атом они не входят.

# Фича 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` — рабочие чтения режима используют сохранённый признак поставки с fallback на legacy-префикс; старый `create_boxes(..., without_distribution=true)` теперь также проверяет назначения `FbsPackingBoxItem`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_workspace_service.py` — workspace сохраняет корректный режим даже у старых поставок с пустым nullable-полем.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/api/fbs_supplies.py` — API переключения режима возвращает workspace и переводит конфликт назначений в понятный HTTP-конфликт.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — регрессии legacy-режима, обхода через старый POST, пустых коробов, сохранения после удаления коробов и API-конфликта.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/tasks/fbs-operator-flow/openapi/fbs-operations.openapi.json` — канонический экспорт содержит новый маршрут.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/docs/blockers/S-03.md` — B-09 описывает блокировку по назначениям, а не по наличию коробов.

## Гейты

- `ruff check .` из `backend/` — FAIL: 80 существующих ошибок в несвязанных файлах; измененные файлы атома проходят целевую проверку.
- `mypy .` из `backend/` — FAIL: 21 существующая ошибка в 6 несвязанных файлах; измененные файлы атома в диагностике отсутствуют.
- целевой `pytest -q tests/test_fbs_packing_box.py tests/test_fbs_openapi_contract.py` — PASS, 15 passed.
- полный `pytest` — INTERRUPTED после 313 passed, 4 skipped и 340.68 секунд; новых падений до остановки не было.
- `python3 scripts/ci/back_guard.py` — NOT RUN: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/back_guard.py` отсутствует.
- `python3 scripts/ci/check_migrations.py` — NOT RUN: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Frontend E2E и изменения экранов из находки REVIEW-3 не реализованы: это роль screen-dev и другой атом.
- Полный pytest не получил финального результата, потому что был остановлен после длительного прогона; целевые backend-тесты завершились успешно.

## Находки

- Секреты, ключи, токены и `.env` не читались.
- В рабочем дереве есть несвязанные изменения `night/volna-9-recovery/JOURNAL.md`; они не входят в этот результат.

# Фича 4

# DEV · 03-no-distribution-mode

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/tests-e2e/ff-fbs-supply.spec.ts` — mock workspace теперь содержит `boxes_without_distribution`, а тест переключения моделирует отдельный toggle API и сохраняет включённый режим до создания коробов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/docs/blockers/S-03.md` — B-09 описывает блокировку только при наличии назначений и показывает операторскую подсказку.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: `npx` попытался скачать пакет `tsc` из npm, но сеть недоступна (`ENOTFOUND registry.npmjs.org`).
- `python3 scripts/ui/ui_guard.py` — красный: guard сообщил новые относительно текущей базы нарушения в `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; базовую линию не обновлял.
- `npm run test:unit` — красный: локальная зависимость `vitest` отсутствует (`vitest: command not found`).

## Не реализовано

- Backend-находки 1–2 из `REVIEW.md` не менялись: они находятся вне роли screen-dev и вне разрешённого экранного слоя.
- Каноническая OpenAPI-схема уже содержит маршрут `/operations/fbs-supplies/{supply_id}/boxes-without-distribution` и поле `boxes_without_distribution`, поэтому изменений в ней не потребовалось.
