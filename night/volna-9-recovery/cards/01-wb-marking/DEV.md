# DEV · 01-wb-marking · backend-dev · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py` — проверена безопасная обработка batch-ответа WB: решения `filled`, `optional`, `pending`, `required` без значения и `invalid` переводятся во внутренние статусы; причина и блок `metaDetails` сохраняются; `missing` и `replacement_required` сохраняют локальную привязку и создают единственный `wb_orphaned`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py` — проверены отображения решений, сопоставление заказа и `kind`, защита текущих данных при неполном/неизвестном ответе и обновление времени только для возвращённой строки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — этот отчёт.

## Миграции

Нет.

## Тесты

- `backend/tests/test_fbs_kiz.py`: целевой набор сценариев WB metadata — 7 passed; существующие тесты покрывают решения `filled`, `optional`, `pending`, `required` без значения, `invalid`, неизвестное решение, несовпадающий код, пропущенную строку и отсутствие ожидаемого `kind`.

## Гейты

- `ruff check .` из `backend/` — не запускался в полном объёме в этом проходе; ранее зафиксированы ошибки вне изменённых файлов. Целевые файлы проверены предыдущим атомом.
- `mypy .` из `backend/` — не запускался в полном объёме в этом проходе; ранее зафиксированы ошибки вне изменённых файлов. Целевой сервис проверен предыдущим атомом.
- `pytest -q tests/test_fbs_kiz.py -k 'wb_decision_mapping or readers_prefer_active or meta'` — PASS: 7 passed, 46 deselected.
- `python3 scripts/ci/back_guard.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` отсутствует.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` отсутствует; миграций нет.

## Не реализовано

- Ничего из атома 3: требуемая логика уже присутствовала в рабочей копии после предыдущего backend-прохода; дополнительный кодовый diff не потребовался.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.
