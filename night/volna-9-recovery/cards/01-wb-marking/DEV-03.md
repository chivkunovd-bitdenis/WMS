# DEV · 01-wb-marking · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py` — безопасное применение ответа WB: полный `reason` и сырой блок, отображения решений `filled`/`optional`/`pending`/`required`/`invalid`, `missing` для `required` без значения, `replacement_required` для отличающегося значения, `unknown` для неизвестных и неполных строк, дата проверки только при возвращённой строке, однократный `wb_orphaned`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py` — тестовая фиксация отображений решений, включая неизвестное решение.

## Гейты

- `ruff check .` — не запускался для всего backend; точечные изменённые файлы PASS.
- `mypy .` — FAIL на ранее существующих ошибках в несвязанных файлах; изменённые файлы в выводе отсутствуют.
- `pytest` — `tests/test_fbs_kiz.py -k 'decision_mapping_covers_safe_sync_states or prefer_active_row_over_newer_rejected_row'` PASS, 7 passed; полный файл ранее остановился на одном найденном регрессе, который исправлен и повторно подтверждён целевым тестом.
- `back_guard.py` — FAIL: `scripts/ci/back_guard.py` отсутствует в рабочей копии.
- `check_migrations.py` — FAIL: `scripts/ci/check_migrations.py` отсутствует в рабочей копии.
- Миграции — нет.
- Commit — не создан: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/index.lock` (`Operation not permitted`), поэтому проверенного SHA нет.

## Не реализовано

- Полный backend-прогон `ruff check .` не выполнен; `mypy .` завершился с 17 ранее существующими ошибками в несвязанных файлах. Полный файл `test_fbs_kiz.py` ранее дошёл до 51 теста и выявил регресс исторической строки; после исправления целевой сценарий проходит.
- UI, API-роуты и миграции не входят в этот атомарный кусок.
- Изменения остаются в рабочей копии незакоммиченными до устранения ограничения прав Git.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.
