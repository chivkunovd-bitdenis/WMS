# DEV · 03-no-distribution-mode · rework атома 1

## Что реализовано

- Эндпоинты: новых нет; существующий `POST /operations/fbs-supplies/{supply_id}/boxes-without-distribution` теперь безопасно выключает режим и для коробов, созданных с максимально допустимым 128-символьным ключом.
- Сервис: `fbs_packing_box_service` переводит legacy-ключ `no-distribution:` в retired-маркер той же длины, поэтому значение остаётся в пределах `fbs_packing_boxes.creation_idempotency_key VARCHAR(128)` и повтор исходного создания по-прежнему находит тот же короб.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` — retired-маркер заменён на 16-символьный `retired-no-dist:`, равный по длине legacy-маркеру.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — регрессионный сценарий переключения использует разрешённый API-ключ длиной 128 символов и проверяет длину сохранённого retired-ключа.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — отчёт backend-разработки.

## Миграции

- Новых нет. Добавляющая миграция `20260821_0094` из исходного атома сохраняется без изменений и добавляет в `fbs_supplies` поля `boxes_without_distribution_at` и `boxes_without_distribution_by_user_id`.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py::test_without_distribution_toggle_preserves_legacy_key_for_create_retry` — создаёт короб с режимом и ключом длиной 128 символов, выключает режим, проверяет 128-символьное значение в БД и успешный идемпотентный повтор без дубля.
- Полный `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` также прошёл внутри общего прогона; он покрывает сохранение признака поставки после удаления и повторного создания пустых коробов.

## Гейты

- ruff (из `backend/`): `ruff check .` — FAIL, 80 ранее существующих ошибок в несвязанных файлах; изменённые файлы в диагностике отсутствуют.
- ruff (целевой): `ruff check app/services/fbs_packing_box_service.py tests/test_fbs_packing_box.py` — PASS.
- mypy (из `backend/`): `mypy .` — FAIL, 21 ранее существующая ошибка в 6 несвязанных файлах; изменённый сервис в диагностике отсутствует.
- pytest (целевой): `pytest -q tests/test_fbs_packing_box.py -k 'toggle_preserves_legacy_key_for_create_retry'` — PASS, `1 passed, 10 deselected`.
- pytest (из `backend/`): `pytest` — FAIL, `1 failed, 816 passed, 5 skipped`; единственное падение `test_fbs_cutoff_autoplans_supply_manual_date_and_calendar` использует дату `2026-08-15` и на текущую дату получает несвязанный `deadline_passed`. Все 11 тестов `test_fbs_packing_box.py` прошли.
- back_guard.py (из корня): NOT RUN — файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/back_guard.py` отсутствует.
- check_migrations.py (из корня): NOT RUN — файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Находка 2 из `REVIEW.md` относится к `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`; она не реализована, потому что роль этого прохода строго `backend-dev`.
- Другие атомы и соседние продуктовые задачи не изменялись.

## Находки

- В репозитории остаются несвязанные базовые ошибки `ruff`, `mypy` и один зависящий от текущей даты тест; они перечислены буквально в секции «Гейты».
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- `git commit` не выполнен: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1/index.lock` (`Operation not permitted`). Backend-rework существует только в локальном рабочем дереве и пока не имеет восстанавливаемого commit SHA.

## Блокеры

- Реализация не заблокирована, но её обязательное сохранение в Git заблокировано правами среды на служебный каталог worktree. Отсутствующие CI-скрипты и красная базовая линия отдельно отражены в гейтах.
