# DEV · 03-no-distribution-mode · атом 2 · переделка по ревью

## Что реализовано

- Эндпоинты: новых нет; существующий `POST /operations/fbs-supplies/{supply_id}/boxes` сохраняет совместимость с короткими legacy-ключами, но не принимает усечённый legacy-маркер за другой длинный ключ.
- Сервис: `fbs_packing_box_service` выполняет fallback к `no-distribution:` и `retired-no-dist:` только для ключей длиной не более 112 символов, когда старое представление было обратимым; для длинных ключей используется только точное совпадение.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` — исключено неоднозначное сопоставление разных 128-символьных ключей через усечённый legacy-маркер.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — добавлена регрессия для двух разных длинных ключей с общими первыми 112 символами и обоих legacy-префиксов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — отчёт роли `backend-dev` по переделке атома 2.

## Миграции

- Нет.

## Тесты

- `test_truncated_legacy_key_does_not_capture_distinct_long_key[no-distribution:]` — усечённый активный legacy-маркер не перехватывает новый отличный 128-символьный ключ.
- `test_truncated_legacy_key_does_not_capture_distinct_long_key[retired-no-dist:]` — то же для погашенного legacy-маркера.
- Повторно проверены короткие legacy-повторы, переключение режима при пустых коробах, запрет при назначении, повторная доступность после удаления назначения, сохранение полного ключа и различение новых 128-символьных ключей.

## Гейты

- Из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend`: `ruff check app/services/fbs_packing_box_service.py tests/test_fbs_packing_box.py && mypy --follow-imports=skip app/services/fbs_packing_box_service.py && pytest -q tests/test_fbs_packing_box.py -k 'truncated_legacy_key_does_not_capture_distinct_long_key or legacy_without_distribution_create_retry_returns_existing_box or without_distribution_mode_depends_on_assignments_not_box_count or without_distribution_toggle_preserves_full_key_for_create_retry or without_distribution_keeps_distinct_max_length_idempotency_keys or legacy_without_distribution_marker_still_blocks_assignment'` — зелёный: ruff `All checks passed!`; mypy `Success: no issues found in 1 source file`; pytest `8 passed, 8 deselected in 12.01s`.
- Из того же каталога: `pytest -q tests/test_fbs_packing_box.py tests/test_fbs_openapi_contract.py` — зелёный: `20 passed in 19.15s`.
- Из корня `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode`: `git diff --check` — зелёный, exit code 0.
- Из того же корня: `git add -- backend/app/services/fbs_packing_box_service.py backend/tests/test_fbs_packing_box.py night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "fix(fbs): avoid ambiguous legacy box key match"` — не выполнено до индексации, exit code 128: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1/index.lock`, `Operation not permitted`.
- `back_guard.py` не применим: новый роут не добавлялся.
- `check_migrations.py` не применим: миграций в этом атоме нет.

## Не реализовано

- Повтор старой операции с исходным ключом длиннее 112 символов нельзя надёжно связать с усечённой записью: старый формат необратимо потерял хвост ключа. Такой запрос намеренно не использует legacy-fallback, чтобы не вернуть чужой физический короб для другого валидного ключа.
- Буквальный `CONTRACT.md` в папке карточки отсутствует; переделка ограничена переданным атомом 2 из `FEATURES.md` и единственной находкой текущего `REVIEW.md`.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

## Блокеры

- Backend-переделка локально реализована и целевые тесты зелёные, но среда не разрешает запись в служебный каталог зарегистрированного Git worktree. Изменения не сохранены отдельным коммитом; текущий восстановимый `HEAD` — `43708251ad8bb1cb7ace586944f1f048b87c820c`, и он не содержит эту переделку. Несвязанные изменения `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/JOURNAL.md` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/REVIEW.md` не индексировались и не редактировались ролью `backend-dev`.
