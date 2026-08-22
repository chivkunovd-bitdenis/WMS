# DEV · 01-wb-marking · атом 3 · rework

## Что реализовано

- Эндпоинты: нет.
- Сервисы: нет — backend-изменения не начаты, потому что входной `CONTRACT.md` не содержит обязательного для роли `backend-dev` раздела «API и данные».

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — зафиксирована невозможность начать backend-rework без обязательного раздела контракта.

## Миграции

- Нет.

## Тесты

- Не добавлялись и не изменялись: без раздела «API и данные» нельзя определить утверждённую семантику данных, которую должны закреплять тесты.

## Гейты

- `ruff check` по изменённым Python-файлам — не запускался: Python-файлы не изменялись.
- `mypy` по затронутым модулям — не запускался: Python-модули не изменялись.
- `pytest -q` по целевым тестам — не запускался: реализация и тесты не изменялись.
- `python3 scripts/ci/back_guard.py` — неприменим: новый роут не добавлялся.
- `python3 scripts/ci/check_migrations.py` — неприменим: миграция не добавлялась.

## Не реализовано

- Не исправлены четыре находки `REVIEW.md` в `backend/app/services/fbs_marking_service.py` и `backend/tests/test_fbs_kiz.py`.
- Для продолжения `CONTRACT.md` должен содержать раздел «API и данные», определяющий как минимум: канонический формат сводки `FbsOrder.meta_details_json`, совместимое отображение `meta_status` в `check_status`, запрет или допустимость legacy `row.meta`, а также гарантию однократности `wb_orphaned` при конкурентных транзакциях.

## Находки

- `CONTRACT.md` содержит UX-описание и явно передаёт реализацию backend-контуру, но раздела «API и данные» в нём нет.
- `REVIEW.md` содержит четыре конкретных замечания, однако по правилам роли ревью не заменяет отсутствующий контракт данных.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Отсутствует обязательный раздел «API и данные» в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/CONTRACT.md`.
