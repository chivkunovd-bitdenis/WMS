# Backend-dev · 02-verdikt-screen

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_worklist_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py`

## Что реализовано

- Единый `_wb_order_verdict` теперь является источником `delivery_allowed` и `verdict` в metadata worklist.
- Старый `compute_delivery_allowed` делегирует тому же правилу, поэтому причина WB и decision больше не расходятся с финальной передачей.
- Отсутствующий или неизвестный ответ, включая незаполненное optional-требование, блокирует передачу; причина имеет приоритет, а отсутствие/неизвестность — приоритет над pending.
- Добавлены регрессии для причин, отсутствующего optional-ответа, конфликта отсутствия с pending и единого delivery gate.

## Миграции

Нет.

## Тесты

- `tests/test_fbs_marking.py`: S-03-TC-001…007 и регрессии агрегирования/совпадения API-гейта.

## Гейты

- `ruff check app/services/fbs_marking_service.py tests/test_fbs_marking.py` — PASS.
- `ruff check .` — FAIL: 83 существующие ошибки в репозитории; отдельная проверка изменённого сервиса и теста зелёная.
- `mypy .` — FAIL: 22 ошибки в 7 файлах, включая существующие ошибки; одна ошибка затрагивает тип `meta_details_json` в изменённом сервисе и требует отдельного общего типизационного прохода.
- `pytest -q tests/test_fbs_marking.py` — PASS, 26 passed.
- `pytest` — не завершён в доступное время; целевой набор зелёный.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии.

## Не реализовано

- Frontend-находки 1, 5 и 6 из `REVIEW.md` не реализованы: они относятся к `fbsApi.ts`, `FfFbsOrdersScreen.tsx` и `FfFbsSupplyWorkspace.tsx`, вне backend-dev атома.

## Блокеры

Нет продуктовых блокеров. Технические ограничения гейтов указаны выше.
