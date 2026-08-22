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
