# DEV · 01-wb-marking · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py` — безопасное применение `metaDetails`, сохранение raw-блока, согласование legacy `check_status`, блокировки актуальных строк и идемпотентный аудит.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_autopoll_service.py` — частично возвращённый batch не учитывается как успешная синхронизация и не запускает производное обновление.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py` — сценарии решений WB, неполного ответа, сохранения raw-данных и единственного `wb_orphaned`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — этот отчёт.

## Гейты

- `ruff check` (из `backend/`, изменённые файлы): PASS.
- `ruff check .` (из `backend/`): FAIL — 80 существующих нарушений в несвязанных API, сервисах, скриптах и тестах; данный атом новых нарушений не добавляет.
- `mypy .` (из `backend/`): FAIL — 21 существующая ошибка в шести несвязанных файлах; изменённый `fbs_marking_service.py` типовых ошибок не содержит.
- `pytest -q tests/test_fbs_kiz.py -k 'wb_meta_decision_is_safe or partial_wb_row or orphaned_audit'`: PASS, 11 passed.
- `pytest` (из `backend/`): полный прогон начат, но в доступной ночной оболочке не вернул финальный код после 11 точек вывода; итог не подтверждён.
- `python3 scripts/ci/back_guard.py`: не запущен — файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` нет.
- `python3 scripts/ci/check_migrations.py`: не запущен — файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` нет.

## Не реализовано

- Ревью-находка о максимальном `Retry-After` относится к клиенту WB из атома 1 и не менялась в атоме 3.
- Миграции: нет. Для однократности `wb_orphaned` используется блокировка уже существующей строки `MarkingCode`; схема не расширяется.

## Находки

- Секреты, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не изменялись.
