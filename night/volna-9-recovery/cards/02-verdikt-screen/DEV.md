# Backend-dev · 02-verdikt-screen · переделка атома 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/api/fbs_orders.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_worklist_query_count.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_kiz.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Что реализовано

- `GET /operations/fbs-orders/worklist` — схема ответа сохраняет серверный объект `metadata.verdict` с подписью, тоном, причиной и разрешением передачи.
- `GET /operations/fbs-supplies/{supply_id}/workspace` — наследуемая схема заказа также сохраняет тот же `metadata.verdict`; Pydantic больше не вырезает его из реального ответа.
- `_reset_stale_wb_verdict` — перед свежим запросом WB очищает прежние `decision` и `reason`, переводит затронутые требования в неизвестное состояние и закрывает передачу.
- `_sync_order_meta_from_wb` — пустой batch, отсутствующая строка заказа, пустой `metaDetails` и ошибка WB больше не оставляют прежний зелёный `filled`; подавленная при финальной синхронизации ошибка остаётся fail-closed (передача запрещена).

## Миграции

Нет.

## Тесты

- `backend/tests/test_fbs_marking.py` — добавлена параметризованная регрессия S-03-TC-006/012 на переход `filled → пустой batch` и `filled → ошибка WB`; оба варианта очищают старое решение и запрещают передачу.
- `backend/tests/test_fbs_worklist_query_count.py` — реальный `GET /operations/fbs-orders/worklist` проверяет, что серверный положительный вердикт доезжает без вырезания схемой ответа.
- `backend/tests/test_fbs_kiz.py` — реальный workspace проверяет наличие и содержание серверного вердикта в `metadata` заказа.
- Целевой прогон — `31 passed`.
- Полный прогон — `842 passed, 5 skipped, 2 failed`; падения предсуществующие: `test_fbs_marking_readers_prefer_active_row_over_newer_rejected_row` ожидает разрешение для не входящего в контракт положительного набора решения `accepted`, а `test_fbs_cutoff_autoplans_supply_manual_date_and_calendar` использует прошедшую дату и получает `deadline_passed`.

## Гейты

- `ruff check .` — FAIL: 79 предсуществующих ошибок вне изменённого атома; целевой `ruff` по пяти изменённым Python-файлам — PASS.
- `mypy .` — FAIL: 21 предсуществующая ошибка в 6 файлах вне изменённого атома; новых ошибок реализации в полном выводе нет.
- `pytest` — FAIL: 842 passed, 5 skipped, 2 предсуществующих падения; целевой прогон атома — PASS, 31 passed.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/scripts/ci/back_guard.py` отсутствует.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/scripts/ci/check_migrations.py` отсутствует.
- `git diff --check` — PASS.

## Не реализовано

- Новых роутов и миграций нет: контракт этого атома их не требует.
- `backend/app/api/fbs_marking.py` не менялся: его отдельный endpoint метаданных уже объявляет `verdict` и не содержит находку ревью.
- `backend/app/services/fbs_shipment_service.py` не менялся: его подавление ошибки теперь безопасно, потому что вызываемый marking-сервис до выброса ошибки очищает старый вердикт в текущей транзакции; соседнюю продуктовую логику передачи не расширял.

## Находки

- Секреты, токены, персональные данные и утечки не читались и не исследовались.

## Блокеры

- Git-коммит технически невозможен в текущей песочнице: `git add` не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock` (`Operation not permitted`). Изменения и артефакт находятся в постоянной рабочей копии, но не сохранены коммитом.
