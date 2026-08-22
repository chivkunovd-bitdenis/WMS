# Backend Dev — 03-no-distribution-mode — атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/api/fbs_supplies.py` — POST-операция переключения режима, workspace-ответ и HTTP 409 для назначенных заказов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_workspace_service.py` — workspace берёт режим из сохранённого признака поставки даже при пустом списке коробов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — API-проверки сохранения режима без коробов и конфликтного ответа при назначенном заказе.

## Миграции

Нет новых миграций в этом атоме. Поля поставки добавлены предыдущим атомом миграцией `20260821_0094`.

## Тесты

- `backend/tests/test_fbs_packing_box.py`: 8 целевых тестов прошли, включая сохранение `supply.boxes_without_distribution=true` после GET workspace без коробов и HTTP 409 без изменения состояния при назначении заказа.

## Гейты

- `ruff check .` — FAIL на 82 существующих нарушениях по всему backend; в затронутом `fbs_workspace_service.py` отмечено существующее неиспользуемое `noqa`.
- `mypy .` — FAIL: 21 существующая ошибка в 6 файлах, затронутые API/сервис в списке ошибок отсутствуют.
- `pytest -q tests/test_fbs_packing_box.py` — PASS, 8 passed.
- `pytest -q` — выполняется; результат будет дополнен после завершения процесса.
- `python3 scripts/ci/back_guard.py` — NOT RUN: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — NOT RUN: файл отсутствует в рабочей копии.

## Не реализовано

- Пункты API-контракта для этого атома реализованы. Новых внешних API, секретов, токенов и кабинетов не использовалось.
- Полный pytest не завершился к моменту записи артефакта; целевой набор прошёл.

## Находки

- Секреты, ключи, токены и `.env` не читались.
- Боевой прод и живой кабинет Wildberries не затрагивались.
