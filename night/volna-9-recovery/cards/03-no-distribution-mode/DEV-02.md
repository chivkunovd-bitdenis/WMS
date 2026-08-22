# DEV · 03-no-distribution-mode · атом 2 · переделка по ревью

## Что реализовано

- Эндпоинты: новых нет; существующее создание коробов через `POST /operations/fbs-supplies/{supply_id}/boxes` теперь сохраняет полный исходный ключ идемпотентности и не кодирует режим поставки в `creation_idempotency_key`.
- Сервис: `fbs_packing_box_service.create_boxes` хранит режим «Без распределения» только в полях поставки, а legacy-префикс `no-distribution:` оставляет только в fallback-чтении существующих данных.
- Сервис: два допустимых 128-символьных ключа с одинаковыми первыми 112 символами больше не коллидируют и создают разные короба.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` — новые короба сохраняют полный исходный ключ; удалены генерация legacy-ключа и проверка режима по ключу при новом идемпотентном повторе.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — добавлены проверки нового формата ключа и отсутствия коллизии двух максимальных ключей; сценарий повторного запроса обновлён под новый источник истины.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` — отчёт текущего backend-прохода.

## Миграции

- Нет. Переделка использует добавляющие поля поставки из зависимости «фича 1» и схему не меняет.

## Тесты

- `test_without_distribution_boxes_do_not_accept_order_assignment` — дополнительно проверяет, что новый короб в режиме «Без распределения» хранит исходный ключ без `no-distribution:`.
- `test_without_distribution_toggle_preserves_full_key_for_create_retry` — проверяет полный 128-символьный ключ, выключение режима и идемпотентный повтор без дубля.
- `test_without_distribution_keeps_distinct_max_length_idempotency_keys` — воспроизводит находку ревью: ключи с общими первыми 112 символами и разными хвостами создают два разных короба и сохраняются без обрезки.
- Остальные тесты `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` проверяют переключение при пустых коробах, запрет при назначении и повторное разрешение после удаления назначения.

## Гейты

- Из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend`: `ruff check app/services/fbs_packing_box_service.py tests/test_fbs_packing_box.py` — PASS, `All checks passed!`.
- Из того же каталога: `mypy app/services/fbs_packing_box_service.py` — FAIL на одной ранее существующей ошибке импортируемого `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/wildberries_credentials_service.py:167`; в изменённом сервисе диагностик нет.
- Из того же каталога: `mypy --follow-imports=skip app/services/fbs_packing_box_service.py` — PASS, `Success: no issues found in 1 source file`.
- Из того же каталога: `pytest -q tests/test_fbs_packing_box.py` — PASS, `12 passed in 9.06s`.
- Из того же каталога: `pytest -q tests/test_fbs_packing_box.py tests/test_fbs_openapi_contract.py` — PASS, `16 passed in 12.55s`.
- `python3 scripts/ci/back_guard.py` — не применим: новый роут не добавлялся.
- `python3 scripts/ci/check_migrations.py` — не применим: миграция не добавлялась.

## Не реализовано

- Backend-находки 1 и 2 из `REVIEW.md`, относящиеся к файлам этого атома, исправлены буквально.
- Находка 3 из `REVIEW.md` относится к `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и исключена профилем `backend-dev` и границами атома.
- Следующие атомы карточки и соседние продуктовые задачи не затрагивались.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- Стандартный целевой `mypy` захватывает импортируемый соседний модуль с базовой ошибкой типов; изолированная проверка изменённого сервиса проходит.

## Блокеры

- Код, тесты и артефакт локально записаны в постоянной рабочей копии, но сохранить их отдельным Git-коммитом не удалось: команда `git add -- backend/app/services/fbs_packing_box_service.py backend/tests/test_fbs_packing_box.py night/volna-9-recovery/cards/03-no-distribution-mode/DEV.md` завершилась ошибкой `Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1/index.lock': Operation not permitted`. Текущий `HEAD` — `92bb49f6`; он не содержит эту переделку. Несвязанные изменения `JOURNAL.md`, `OTLOZHENO.md` и `REVIEW.md` не индексировались и не редактировались этой ролью.
