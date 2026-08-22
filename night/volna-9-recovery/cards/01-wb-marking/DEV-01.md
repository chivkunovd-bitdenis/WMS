# DEV · 01-wb-marking · атом 1 · rework

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py`: batch-чтение сохраняет `key`, `value`, `decision` и `reason`; после `429` ровно один раз ждёт полный `Retry-After`, включая HTTP-дату, и повторяет ту же пачку.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py`: штатная E2E-заглушка теперь возвращает записанную маркировку через рабочий `meta_details`, а не через устаревшее поле `meta`.

## Миграции

- Нет.

## Тесты

- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py` сохранена проверка полного DTO `metaDetails` с `decision`, `value` и `reason`.
- Числовой `Retry-After: 3600` проверяется без искусственного ограничения; HTTP-дата проверяется отдельным тестом; оба сценария подтверждают ровно один повтор пачки.
- Добавлена проверка штатного mock-пути `PUT` → batch `POST`: сеть не вызывается, DTO содержит `meta_details`, legacy `meta` отсутствует.
- Существующие проверки подтверждают ошибку для `400`, `500` и неразбираемого тела вместо частичного успеха.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/services/wildberries_fbs_client.py tests/test_wildberries_marketplace_fbs_client.py` — PASS: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/wildberries_fbs_client.py` — PASS: `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_wildberries_marketplace_fbs_client.py` — PASS: `19 passed in 0.09s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status` — PASS: `1 passed in 1.02s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking && git diff --check` — PASS.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking && git add -- backend/app/services/wildberries_fbs_client.py backend/tests/test_wildberries_marketplace_fbs_client.py night/volna-9-recovery/cards/01-wb-marking/DEV.md && git commit -m "fix(wb-marking): honor batch retry metadata"` — BLOCKED средой: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/index.lock` (`Operation not permitted`).
- `python3 scripts/ci/back_guard.py` — не применим: атом не добавляет и не меняет роуты.
- `python3 scripts/ci/check_migrations.py` — не применим: атом не добавляет миграцию.

## Не реализовано

- Находки 1 и 3 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/REVIEW.md` относятся к атомам применения ответа и фоновой сверки в `fbs_marking_service.py`, `fbs_autopoll_service.py`, `test_fbs_kiz.py` и `test_fbs_marking.py`; по прямому ограничению текущего задания их реализация не менялась.
- Полный backend-регресс не запускался: он прямо запрещён для этого атомарного шага.

## Находки

- В `CONTRACT.md` нет отдельного заголовка «API и данные»; однозначная backend-семантика текущего атома задана разделом 1 `FEATURES.md`, а rework — находками 2 и 4 `REVIEW.md`.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Backend-изменения локально реализованы и проверены, но не сохранены коммитом: Git-метаданные зарегистрированного worktree находятся вне разрешённой для записи области песочницы. Для сохранения нужно выполнить указанную в разделе «Гейты» команду процессом с правом записи в `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/`.
