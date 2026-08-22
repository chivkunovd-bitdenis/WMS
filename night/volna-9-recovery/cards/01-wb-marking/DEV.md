# DEV · 01-wb-marking · backend-dev · атом 1 (rework)

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py` — ограничено ожидание `Retry-After` одной секундой; после первого `429` та же пачка повторяется ровно один раз.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py` — тест защищает ограничение внешнего `Retry-After: 3600` и единственный повтор.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — отчёт выполнения.

## Гейты

- `ruff check app/services/wildberries_fbs_client.py tests/test_wildberries_marketplace_fbs_client.py` — PASS.
- `mypy app/services/wildberries_fbs_client.py` — PASS.
- `pytest -q tests/test_wildberries_marketplace_fbs_client.py` — PASS, 17 passed.
- `ruff check .` — FAIL: 80 существующих нарушений вне изменённого слоя; два изменённых файла проходят адресную проверку.
- `mypy .` — FAIL: 21 существующая ошибка в шести посторонних файлах; изменённый модуль проходит адресную проверку.
- `pytest` — не завершён: средство выполнения прервало полный запуск после начала (827 собранных тестов, без зафиксированного итогового вердикта); целевой набор прошёл.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` нет.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` нет; миграции не добавлялись.

## Не реализовано

- Находки ревью по `fbs_marking_service.py`, `fbs_autopoll_service.py`, журналу событий и их тестам относятся к другим атомам `FEATURES.md`; этот проход ограничен атомом 1 и его клиентским слоем. Исправлена относящаяся к нему находка №6: верхняя граница `Retry-After`.

## Находки

- Секреты, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не изменялись.
