# DEV · 01-wb-marking · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py`
  — добавлен допустимый тип события `EVENT_WB_ORPHANED = "wb_orphaned"`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py`
  — добавлен тест записи `wb_orphaned` в существующий журнал без изменения статуса,
  `pool_id` и `product_id` КИЗ.

## Гейты

- `ruff check .` — FAIL: 81 ранее существующая ошибка в несвязанных файлах; точечные файлы PASS.
- `mypy .` — FAIL: 21 ранее существующая ошибка в 6 несвязанных файлах; точечная модель PASS,
  тестовый файл упирается в существующий импорт `test_packaging_tasks` без stubs.
- `pytest -q tests/test_marking_code_events.py` — PASS, 3 passed.
- `pytest -q` — прерван после 92 passed и 5 warnings из-за длительного полного прогона.
- `python3 scripts/ci/back_guard.py` — недоступен: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — недоступен: файл отсутствует в рабочей копии.
- `git diff --check` — PASS.

## Не реализовано

- Повторная запись для одной привязки не добавлялась: её идемпотентность относится к следующей
  фиче сверки.
- Автоматическая сверка WB, изменение статуса, освобождение пула и новые API не входят в этот
  атомарный кусок и не реализовывались.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет
  Wildberries не читались и не затрагивались.
