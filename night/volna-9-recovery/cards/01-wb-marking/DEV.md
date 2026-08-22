# DEV · 01-wb-marking · атом 3 · rework по JUDGE

## Что реализовано

- Эндпоинты: нет.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py`: уже сохранённая в истории ветки реализация безопасно применяет `metaDetails.decision`, сохраняет `reason` и сырой блок, переводит `required` без значения в `missing`, а отличающееся заполненное значение — в `replacement_required`.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py`: сохраняет `marking_code_id` и жизненный статус КИЗ, однократно пишет `wb_orphaned`, а пропущенную строку, отсутствующий ожидаемый `kind` и неизвестное решение обрабатывает как безопасный `unknown` без ложной даты успешной проверки.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py` — реализация атома уже сохранена в коммите `cce84fd4`; в текущем rework backend-код не менялся, потому что единственная находка `JUDGE.md` относится к недоступному живому UI-стенду.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py` — тесты атома уже сохранены в коммите `cce84fd4`; в текущем rework они повторно выполнены адресно.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — восстановлен обязательный отчёт с фактическими результатами rework.

## Миграции

- Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py::test_fbs_marking_wb_meta_decision_is_safe_and_preserves_raw_detail` — отображения `filled`, `optional`, `pending`, `required` без значения, `invalid`, неизвестного решения и несовпадающего кода; сохранение причины и сырого блока.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py::test_fbs_marking_partial_wb_row_is_unknown_without_fresh_check_time` — отсутствие ожидаемого `kind` даёт `unknown`, не стирает прежние детали КИЗ и не ставит дату успешной проверки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py::test_fbs_marking_omitted_wb_row_clears_stale_verdict_only` — пропущенный `order_id` не меняет привязку, жизненный статус КИЗ, прежнюю причину, сырой блок и время последней успешной проверки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py::test_fbs_marking_orphaned_audit_is_created_once_for_concurrent_and_repeated_mismatch` — повторные и конкурентные `missing` / `replacement_required` оставляют один аудит-факт `wb_orphaned`.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking && ruff check backend/app/services/fbs_marking_service.py backend/tests/test_fbs_kiz.py` — успешно: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/fbs_marking_service.py` — код выхода 1 из-за четырёх ранее существующих ошибок в импортируемых соседних модулях: `app/services/wildberries_credentials_service.py:167`, `app/services/fbs_stock_sync_service.py:617`, `app/services/fbs_warehouse_binding_service.py:23` и `app/services/fbs_warehouse_binding_service.py:291`; в файле атома ошибок не выведено.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_fbs_kiz.py::test_fbs_marking_wb_meta_decision_is_safe_and_preserves_raw_detail tests/test_fbs_kiz.py::test_fbs_marking_partial_wb_row_is_unknown_without_fresh_check_time tests/test_fbs_kiz.py::test_fbs_marking_omitted_wb_row_clears_stale_verdict_only tests/test_fbs_kiz.py::test_fbs_marking_orphaned_audit_is_created_once_for_concurrent_and_repeated_mismatch` — успешно: `13 passed in 11.04s`.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — не запускался: атом не добавляет маршрут.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — не запускался: атом не добавляет миграцию.

## Не реализовано

- Единственная находка `JUDGE.md` — неподнятый живой UI-стенд и отсутствие browser evidence — не относится к разрешённым файлам и backend-слою атома 3; backend-изменений для неё нет.
- В `CONTRACT.md` отсутствует буквально названный раздел `API и данные`; backend-спецификация атома дана в `FEATURES.md`. В текущем rework новая реализация по неполному контракту не начиналась: выполнена только адресная проверка уже сохранённого атома.
- Новые эндпоинты, модели, миграции, UI и обращения к внешнему Wildberries не добавлялись.

## Блокеры

- Backend-блокеров поведения атома нет. Целевой `mypy` остаётся не зелёным из-за четырёх ошибок в соседних импортируемых модулях вне разрешённых файлов атома.
- Product browser review остаётся заблокированным отсутствием живого стенда; это зафиксировано в `JUDGE.md` и не исправляется в роли `backend-dev`.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.
