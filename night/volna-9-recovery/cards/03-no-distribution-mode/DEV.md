# DEV · 03-no-distribution-mode · атом 2 · переделка по ревью

## Что реализовано

- Эндпоинты: новых нет; существующее создание коробов снова идемпотентно для точного повтора старого 128-символьного ключа, усечённого legacy-префиксом.
- Сервис: `fbs_packing_box_service` сверяет неоднозначный усечённый legacy-ключ с полным ключом в журнале WB-операций и возвращает старый короб только для доказанного повтора той же операции и той же поставки.
- Сервис: другой длинный ключ с теми же первыми 112 символами не сопоставляется со старым коробом и создаёт отдельный короб.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` — добавлена точная проверка полного ключа по журналу операции создания грузомест перед legacy-fallback.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — добавлена регрессия точного повтора усечённого длинного ключа для обоих legacy-префиксов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — отчёт роли `backend-dev`.

## Миграции

- Нет.

## Тесты

- `test_truncated_legacy_key_retry_returns_existing_box[no-distribution:]` — повтор исходного 128-символьного ключа находит старый короб по полному ключу WB-операции и не создаёт дубль.
- `test_truncated_legacy_key_retry_returns_existing_box[retired-no-dist:]` — тот же сценарий после погашения legacy-маркера.
- Повторно проверены различение двух длинных ключей с общим 112-символьным префиксом, совместимость коротких legacy-ключей и переключение режима по наличию назначений, а не по числу коробов.

## Гейты

- Из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend`: `ruff check app/services/fbs_packing_box_service.py tests/test_fbs_packing_box.py` — PASS: `All checks passed!`.
- Из того же каталога: `mypy --follow-imports=skip app/services/fbs_packing_box_service.py` — PASS: `Success: no issues found in 1 source file`.
- Из того же каталога: `pytest -q tests/test_fbs_packing_box.py -k 'truncated_legacy_key_retry_returns_existing_box or truncated_legacy_key_does_not_capture_distinct_long_key or legacy_without_distribution_create_retry_returns_existing_box or without_distribution_mode_depends_on_assignments_not_box_count'` — PASS: `7 passed, 11 deselected in 6.51s`.
- Из того же каталога: `pytest -q tests/test_fbs_packing_box.py tests/test_fbs_openapi_contract.py` — PASS: `22 passed in 18.10s`.
- Из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode`: `git diff --check` — PASS, exit code 0.
- Из того же каталога: `git add -- backend/app/services/fbs_packing_box_service.py backend/tests/test_fbs_packing_box.py night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "fix(fbs): preserve long legacy box retries"` — FAIL до индексации, exit code 128: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1/index.lock`, `Operation not permitted`.
- `back_guard.py` не применим: новый роут не добавлялся.
- `check_migrations.py` не применим: миграций нет.

## Не реализовано

- Новые таблицы или колонки для восстановления старых ключей не добавлялись: полный ключ уже сохранён в существующем журнале WB-операций.
- Если у исторического усечённого ключа нет соответствующей записи журнала WB-операции, сервис намеренно не угадывает совпадение и не возвращает потенциально чужой короб.
- Буквальный `tasks/<id>/CONTRACT.md` и раздел `API и данные` в рабочей копии отсутствуют; переделка ограничена переданным атомом 2 из `FEATURES.md` и единственной backend-находкой текущего `REVIEW.md`.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

## Блокеры

- Функциональных блокеров нет, но обязательное сохранение отдельным Git-коммитом заблокировано правами среды на служебный каталог зарегистрированного worktree. Локальные изменения не входят в восстановимый `HEAD` `e22abe1bc81a67d47969f6b9498ea5a13dc89441`. Несвязанные изменения `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/JOURNAL.md` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/REVIEW.md` не редактировались и не индексировались ролью `backend-dev`.
