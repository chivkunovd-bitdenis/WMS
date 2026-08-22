# DEV · 03-no-distribution-mode · атом 2 · переделка по ревью

## Что реализовано

- Эндпоинты: новых нет; существующий `POST /operations/fbs-supplies/{supply_id}/boxes` снова идемпотентно возвращает ранее созданный короб при повторе legacy-операции.
- Сервис: `fbs_packing_box_service` сначала ищет точное совпадение нового сырого ключа, а при его отсутствии читает совместимые значения `no-distribution:<key>` и `retired-no-dist:<key>`; точный поиск имеет приоритет, поэтому новые 128-символьные ключи не смешиваются с усечённым legacy-форматом.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` — восстановлен поиск идемпотентного повтора по обоим старым форматам ключа с приоритетом точного нового ключа.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — добавлен параметризованный регрессионный тест, доказывающий отсутствие дублирования короба для `no-distribution:` и `retired-no-dist:`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — отчёт роли `backend-dev` по переделке атома 2.

## Миграции

- Нет.

## Тесты

- `test_legacy_without_distribution_create_retry_returns_existing_box[no-distribution:]` — повтор старой операции возвращает исходный короб и не создаёт второй физический короб.
- `test_legacy_without_distribution_create_retry_returns_existing_box[retired-no-dist:]` — то же после выключения legacy-режима и перевода ключа в retired-формат.
- Повторно проверены сценарии атома: переключение при пустых коробах, запрет при назначении, повторная доступность после удаления назначения и сохранность различных 128-символьных ключей.

## Гейты

- Из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend`: `.venv/bin/ruff check app/services/fbs_packing_box_service.py tests/test_fbs_packing_box.py && .venv/bin/mypy --follow-imports=skip app/services/fbs_packing_box_service.py && .venv/bin/pytest -q tests/test_fbs_packing_box.py -k 'legacy_without_distribution_create_retry_returns_existing_box or without_distribution_mode_depends_on_assignments_not_box_count or without_distribution_toggle_preserves_full_key_for_create_retry or without_distribution_keeps_distinct_max_length_idempotency_keys or legacy_without_distribution_marker_still_blocks_assignment'` — не запущено, exit code 127: в этой рабочей копии отсутствует `backend/.venv/bin/ruff`; код не проверялся этой командой.
- Из того же каталога: `ruff check app/services/fbs_packing_box_service.py tests/test_fbs_packing_box.py && mypy --follow-imports=skip app/services/fbs_packing_box_service.py && pytest -q tests/test_fbs_packing_box.py -k 'legacy_without_distribution_create_retry_returns_existing_box or without_distribution_mode_depends_on_assignments_not_box_count or without_distribution_toggle_preserves_full_key_for_create_retry or without_distribution_keeps_distinct_max_length_idempotency_keys or legacy_without_distribution_marker_still_blocks_assignment'` — **зелёный**: ruff `All checks passed!`; mypy `Success: no issues found in 1 source file`; pytest `6 passed, 8 deselected in 5.34s`.
- Из того же каталога: `pytest -q tests/test_fbs_packing_box.py` — **зелёный**, `14 passed in 11.00s`.
- Из корня `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode`: `git diff --check` — **зелёный**, exit code 0.
- Из того же корня: `git add -- backend/app/services/fbs_packing_box_service.py backend/tests/test_fbs_packing_box.py night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md && git diff --cached --check && git commit -m "fix(fbs): preserve legacy box create idempotency"` — **красный до индексации**, exit code 128: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1/index.lock`, `Operation not permitted`.
- `back_guard.py` не применим: новый роут не добавлялся.
- `check_migrations.py` не применим: миграций в этом атоме нет.

## Не реализовано

- Нет: единственная находка текущего `REVIEW.md`, относящаяся к backend-файлам атома 2, исправлена и покрыта обоими названными legacy-состояниями.
- Буквальный `CONTRACT.md` в папке карточки отсутствует; переделка ограничена явно переданным атомом 2 из `FEATURES.md` и единственной находкой повторного `REVIEW.md`, новых продуктовых решений не добавлено.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

## Блокеры

- Backend-переделка реализована и целевые тесты зелёные, но среда не разрешает запись в служебный каталог зарегистрированного Git worktree, поэтому изменения не сохранены отдельным коммитом. Текущий `HEAD` — `f4dde7e0`; он не содержит эту переделку. Для завершения сохранности нужен запуск `git add` и `git commit` в среде с правом записи в `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1`. Несвязанные изменения `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/JOURNAL.md` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/REVIEW.md` не индексировались и не редактировались ролью `backend-dev`.
