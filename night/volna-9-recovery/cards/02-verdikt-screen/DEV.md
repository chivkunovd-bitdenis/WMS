# Backend-dev · 02-verdikt-screen · переделка атома 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Что реализовано

- `GET /operations/fbs-orders/{order_id}/metadata` — синхронизирует ответ WB и для заказа без локальных строк `FbsOrderMarking`, если WB запросил обязательные или необязательные метаданные; возвращает единый серверный вердикт и состояние необязательного требования.
- `POST /operations/fbs-orders/{order_id}/markings/sync` — больше не пропускает синхронизацию заказа без локальной маркировки, когда у заказа есть запрос метаданных WB.
- `_sync_order_meta_from_wb` — сохраняет свежие `metaDetails` на уровне заказа, включая `optional`/`notRequired` без локального кода, и не теряет их при объединении с локальными маркировками.
- `_wb_order_verdict` — читает сохранённый ответ WB на уровне заказа, сохраняет приоритет причины и блокеров и принимает совместимое историческое решение `accepted` как проходное.
- `build_order_metadata` — передаёт оба источника S-03 один и тот же вердикт и серверное состояние необязательного требования без технической подписи вместо продуктового текста.

## Миграции

Нет.

## Тесты

- `backend/tests/test_fbs_marking.py::test_fbs_metadata_preserves_optional_wb_decision_without_local_marking[False]` — S-03-TC-002: заказ только с необязательным требованием и без единой локальной маркировки получает `optional`, разрешение передачи и состояние с источником WB.
- `backend/tests/test_fbs_marking.py::test_fbs_metadata_preserves_optional_wb_decision_without_local_marking[True]` — S-03-TC-002/S-03-TC-007: `filled` обязательного кода вместе с `optional` без локальной строки агрегируются в проходной вердикт.
- Повторно пройден весь целевой `backend/tests/test_fbs_marking.py`, покрывающий S-03-TC-001…007, отсутствие/неизвестность ответа, приоритет причины и блокера.
- Повторно пройдён названный ревьюером `backend/tests/test_fbs_kiz.py::test_fbs_marking_readers_prefer_active_row_over_newer_rejected_row`: исторический `decision="accepted"` снова разрешает передачу.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && pytest -q tests/test_fbs_marking.py tests/test_fbs_kiz.py::test_fbs_marking_readers_prefer_active_row_over_newer_rejected_row` — PASS, `32 passed in 7.96s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && ruff check app/services/fbs_marking_service.py tests/test_fbs_marking.py` — PASS, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && mypy app/services/fbs_marking_service.py` — целевой изменённый модуль без ошибок; команда завершилась FAIL из-за четырёх предсуществующих ошибок в импортируемых соседних файлах `wildberries_credentials_service.py:167`, `fbs_stock_sync_service.py:617`, `fbs_warehouse_binding_service.py:23,291`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && mypy --follow-imports=skip --disable-error-code=no-any-return app/services/fbs_marking_service.py` — PASS, `Success: no issues found in 1 source file`; это изолированная проверка изменённого модуля, не подмена результата обычного целевого mypy выше.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && git diff --check -- backend/app/services/fbs_marking_service.py backend/tests/test_fbs_marking.py` — PASS, ошибок пробелов нет.
- `back_guard.py` не запускался: новый роут не добавлялся.
- `check_migrations.py` не запускался: миграций нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen && git add -- backend/app/services/fbs_marking_service.py backend/tests/test_fbs_marking.py night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` — BLOCKED средой: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock`, `Operation not permitted`.

## Не реализовано

- Находка REVIEW №2 в `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` не реализована: это UI-слой и отдельный атом роли `screen-dev`; backend-dev фронтенд не меняет.
- `backend/app/api/fbs_marking.py` не менялся: существующие response model и роуты уже содержат `verdict`; исправление потребовалось в вызываемом сервисе и покрыто реальным API-тестом.
- Следующие фичи из `FEATURES.md`, включая серверный запрет передачи поставки, не затрагивались: выполнен только атом 1.

## Находки

- Обычный целевой mypy красный только на четырёх ошибках в трёх соседних, не изменённых этим атомом сервисах; в `fbs_marking_service.py` ошибок после исправления нет.

## Блокеры

- Изменения локально реализованы и проверены, но не сохранены в Git-коммите: sandbox разрешает запись в рабочую копию, однако запрещает запись в общий служебный каталог `.git`, где расположен index этого зарегистрированного worktree. Commit SHA получить в этой сессии невозможно.
