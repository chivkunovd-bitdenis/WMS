# DEV · 03-no-distribution-mode · переделка атома 2

## Что реализовано

- Эндпоинты: новых нет; существующее выключение режима через `POST /operations/fbs-supplies/{supply_id}/boxes-without-distribution` не переполняет `fbs_packing_boxes.creation_idempotency_key` для разрешённого ключа длиной 128 символов.
- Сервис: `fbs_packing_box_service` заменяет legacy-префикс `no-distribution:` на равный ему по длине `retired-no-dist:`, сохраняя значение в пределах `VARCHAR(128)` и возможность идемпотентно найти прежний короб при повторе создания.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` — retired-маркер сделан 16-символьным, как legacy-маркер; максимальная длина сохранённого ключа остаётся 128 символов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — регрессионный сценарий использует максимальный 128-символьный API-ключ и проверяет длину и значение retired-ключа после выключения режима.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — отчёт этого backend-прохода.

## Миграции

- Новых нет. Добавляющая миграция `20260821_0094` из зависимости «фича 1» не изменялась.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py::test_without_distribution_toggle_preserves_legacy_key_for_create_retry` — создаёт короб с ключом длиной 128 символов, выключает режим, проверяет ровно 128 символов в БД и успешный повтор без дубля.
- Полный целевой файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` покрывает включение после создания пустого короба, удаление и пересоздание короба, выключение режима, доменную ошибку при назначенном заказе и повторное разрешение после удаления назначения.

## Гейты

- Из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend`: `ruff check app/services/fbs_packing_box_service.py tests/test_fbs_packing_box.py` — PASS, `All checks passed!`.
- Из того же каталога: `mypy app/services/fbs_packing_box_service.py` — FAIL на ранее существующей ошибке импортируемого `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/wildberries_credentials_service.py:167`; изменённый сервис в диагностике отсутствует.
- Из того же каталога: `mypy --follow-imports=skip app/services/fbs_packing_box_service.py` — PASS, `Success: no issues found in 1 source file`.
- Из того же каталога: `pytest -q tests/test_fbs_packing_box.py` — PASS, `11 passed in 16.57s`.
- `python3 scripts/ci/back_guard.py` — не применим: текущая переделка не добавляет роут.
- `python3 scripts/ci/check_migrations.py` — не применим: текущая переделка не добавляет миграцию.

## Не реализовано

- Находка 2 из `REVIEW.md` относится к `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и не входит в роль `backend-dev` и файлы этого атома.
- Следующие атомы карточки и соседние продуктовые задачи не затрагивались.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- Стандартный целевой `mypy` захватывает импортируемый соседний модуль с базовой ошибкой типов; отдельная проверка изменённого сервиса без обхода импортов зелёная.
- Backend-исправление и его регрессионный тест сохранены в Git-коммите `13ab613e275ce5445327fc7655a3d3614b41e563`.

## Блокеры

- Текущую редакцию `DEV.md` не удалось закоммитить: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1/index.lock` (`Operation not permitted`). Артефакт записан в требуемый файл рабочей копии, но его новые результаты гейтов пока не имеют отдельного commit SHA.
