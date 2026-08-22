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
