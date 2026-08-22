# DEV · 01-wb-marking · атом 3 · rework

## Что реализовано

- Эндпоинты: нет.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py`: применяет `metaDetails.decision` к существующей привязке КИЗ безопасно — сохраняет `reason` и сырой блок, сопоставляет известные решения, фиксирует `missing` или `replacement_required` без отвязки КИЗ и создаёт единственный `wb_orphaned`.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py`: ответ без строки заказа, без ожидаемого `kind` либо с неизвестным решением переводит вердикт в `unknown`, не перезаписывает локальную привязку, жизненный статус КИЗ, сохранённые детали или дату успешной проверки.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

## Миграции

- Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py`: отображения `filled`, `optional`, `pending`, `required` без значения, `invalid`, неизвестного решения и несовпадающего значения; частичный и пропущенный ответ; однократный аудит `wb_orphaned` для повторных и конкурентных `missing` / `replacement_required`.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking && ruff check backend/app/services/fbs_marking_service.py backend/tests/test_fbs_kiz.py` — успешно: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/fbs_marking_service.py` — не зелёный из-за четырёх ранее существующих ошибок в импортируемых соседних модулях: `app/services/wildberries_credentials_service.py:167`, `app/services/fbs_stock_sync_service.py:617`, `app/services/fbs_warehouse_binding_service.py:23` и `:291`; в файле атома ошибок не выведено.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_fbs_kiz.py::test_fbs_marking_wb_meta_decision_is_safe_and_preserves_raw_detail tests/test_fbs_kiz.py::test_fbs_marking_partial_wb_row_is_unknown_without_fresh_check_time tests/test_fbs_kiz.py::test_fbs_marking_omitted_wb_row_clears_stale_verdict_only tests/test_fbs_kiz.py::test_fbs_marking_orphaned_audit_is_created_once_for_concurrent_and_repeated_mismatch` — успешно: `13 passed in 10.91s`.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — не применимо: атом не добавляет маршрут.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — не применимо: атом не добавляет миграцию.

## Не реализовано

- Находка `JUDGE.md` относится только к недоступности живого UI-стенда и отсутствию browser evidence; изменений в backend-слое атома 3 она не требует.
- Новые эндпоинты, модели, миграции, UI и обращения к внешнему WB не добавлялись.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.
