# Фича 1

# Backend Dev — 03-no-distribution-mode — атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/models/fbs_supply.py` — сохраняемые nullable-поля времени включения режима и пользователя, включившего режим.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/alembic/versions/20260821_0094_fbs_supplies_boxes_without_distribution.py` — добавляющая миграция колонок и внешнего ключа на `users` с `SET NULL`.

Изменения атома уже присутствовали в рабочей копии из коммита `bf6bc61`; сервис, API и UI не изменялись.

## Миграции

- `20260821_0094` — добавляет `fbs_supplies.boxes_without_distribution_at`, `fbs_supplies.boxes_without_distribution_by_user_id` и внешний ключ на `users`.

## Тесты

- Целевой тест `backend/tests/test_fbs_packing_box.py` запускался системным `pytest`, но процесс не вернул результат в доступное время.

## Гейты

- `ruff` — PASS для двух изменённых backend-файлов (`All checks passed!`). Полный `ruff check .` не подтверждён из-за отсутствующего проектного окружения.
- `mypy` — NOT RUN: проектное виртуальное окружение отсутствует; системный запуск полного набора не получил результата.
- `pytest` — NOT CONFIRMED: системный целевой запуск не вернул результат; проектное виртуальное окружение отсутствует.
- `back_guard.py` — NOT RUN: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/back_guard.py` отсутствует.
- `check_migrations.py` — NOT RUN: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Сервис переключения, API/workspace и UI не входят в атом 1 и не изменялись.
- Массовая миграция legacy-ключей `no-distribution:` не входит в контракт атома; совместимость остаётся для следующих слоёв.

## Находки

- Секреты, ключи, токены и `.env` не читались.
- Боевой прод и кабинет Wildberries не затрагивались.

## Блокеры

- Нет блокеров реализации; техническая верификация полного набора gate-команд ограничена отсутствующими локальными файлами окружения и CI-скриптами.

# Фича 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` — переключение режима на уровне поставки; запрет только при наличии записей назначений заказа в коробах; сохранена совместимость чтения старой приписки через существующий код.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — сценарий пустого короба, удаления/пересоздания, выключения режима, запрета при назначении и повторного включения после удаления назначения.

Изменения backend-файлов уже присутствовали в рабочей копии до запуска этой роли; проверка подтвердила соответствие атомарному куску 2. Новых роутов и миграций для этого куска нет.

## Гейты

- `ruff check .` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend` — FAIL: 82 ошибки в существующих несвязанных файлах; в изменённых файлах этой фичи нарушений не показано.
- `mypy .` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend` — FAIL: 21 ошибка в 6 существующих несвязанных файлах; ошибок в изменённых файлах этой фичи нет.
- `pytest -q tests/test_fbs_packing_box.py -k without_distribution_mode_depends_on_assignments_not_box_count` — PASS: 1 passed, 7 deselected.
- `pytest -q` из backend — прерван после ~8% длительного прогона без обнаруженной ошибки; целевой тест выполнен отдельно и зелёный.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл `scripts/ci/back_guard.py` отсутствует в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл `scripts/ci/check_migrations.py` отсутствует в этой рабочей копии; миграций в этом атоме нет.

## Не реализовано

- Нет непринесённых пунктов атомарного backend-контракта 2.

## Находки

- Контрактный файл `CONTRACT.md` в указанной папке отсутствует; раздел API и данные подтверждён по `FEATURES.md` и артефактам предыдущих ролей.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 3

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

# Фича 4

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx

Экран использует сохранённый признак `workspace.supply.boxes_without_distribution` для нейтральной шапки. Переключатель доступен при пустых коробах и блокируется только при наличии назначенных заказов; рядом показано объяснение, что сначала нужно убрать назначения из коробов.

Тип workspace и операция переключения уже реализованы предыдущими атомами в текущей ветке:

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/frontend/src/screens/v2/fbsApi.ts

Файл OpenAPI по указанному в карточке пути отсутствует в checkout. Найденный файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/tasks/fbs-operator-flow/openapi/fbs-operations.openapi.json` не входит в разрешённые файлы экрана и не изменялся.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из frontend — не подтверждён: локальный `tsc` отсутствует (`frontend/node_modules/.bin/tsc` не найден), команда не выдала диагностик.
- `python3 scripts/ui/ui_guard.py` из корня — FAIL: нарушения `экран-монолит` в `src/components/WbProductPickerDialog.tsx` (0 → 646), `src/screens/v2/FfFbsSupplyWorkspace.tsx` (2493 → 2503) и `src/screens/v2/SellerInboundDraftScreen.tsx` (1111 → 1169). Базовую линию не обновлял.
- `npm run test:unit` из frontend — FAIL до запуска тестов: `vitest: command not found`.

## Не реализовано

- Изменение отсутствующего OpenAPI-файла по пути `frontend/openapi/fbs-operations.openapi.json`: файла нет в checkout, а создание или перенос вне разрешённого набора файлов экрана запрещены ролью.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- Боевой прод и живой кабинет Wildberries не затрагивались.
