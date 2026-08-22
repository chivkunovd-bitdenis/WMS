# DEV · 01-wb-marking · backend-dev · feature 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_autopoll_service.py` — автополлер выбирает все заказы активных собираемых поставок, сохраняет порядок, дедуплицирует `wb_order_id`, режет их на последовательные пачки до 100, делает один batch-запрос на пачку и продолжает следующую пачку после ошибки; ответ применяется к заказу по `order_id`, независимо от порядка строк ответа.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py` — существующее применение маркировки принимает уже загруженный batch-ответ, сохраняя одиночный ручной путь с прежним запросом из одного ID.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py` — существующий набор тестов применения batch-ответа прошёл; отдельный сценарий автополлера в этом проходе не добавлен из-за отсутствия готовой фикстуры поставок/автополлера.

## Гейты

- `ruff` — PASS для изменённых backend-файлов и `tests/test_fbs_marking.py`.
- `mypy` — PASS для `app/services/fbs_marking_service.py` и `app/services/fbs_autopoll_service.py`.
- `pytest` — PASS: `backend/tests/test_fbs_marking.py`.
- `back_guard.py` — не запущен: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` отсутствует.
- `check_migrations.py` — не запущен: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Отдельный интеграционный тест с более чем 100 заказами, переставленным ответом и ошибкой промежуточной пачки не добавлен; кодовой путь реализован, но его поведение не закреплено новым тестом.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Находки

- В рабочей копии до изменения уже были несвязанные изменения `night/volna-9-recovery/JOURNAL.md`; они не включались в работу.
