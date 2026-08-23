# DEV · 04-warehouse-switch · атом 1 · rework

## Что реализовано

- Эндпоинт `PATCH /operations/inbound-intake-requests/{id}` принимает явно переданный `warehouse_id`, передаёт значение и `warehouse_id_set` в сервис и возвращает документ с обновлённым складом.
- Сервис `inbound_intake_service.patch_request_draft` меняет склад только у документа в статусе `draft`; это отдельная охрана для `warehouse_id`, поэтому существующее право селлера менять прочие плановые поля после передачи не расширяет право менять закреплённый склад.
- Новый склад загружается в границах `tenant_id` и принимается только при `Warehouse.is_operational == True`; отсутствующий, чужой, неоперационный или явно `null` склад возвращает известный код `invalid_warehouse`.
- После передачи заявки попытка селлера сменить склад возвращает `409 not_draft`.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/inbound_intake_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_inbound_intake.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

API-схема и проброс `warehouse_id` в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/inbound_intake.py` уже находились в HEAD после предыдущего атомарного коммита; в этом rework файл не менялся.

## Миграции

Нет. Атом расширяет поведение существующего PATCH и не меняет структуру базы данных.

## Тесты

- `test_patch_warehouse_id_saves_on_draft` проверяет `200`, сохранение второго операционного склада и `422 invalid_warehouse` для явно переданного `null`.
- `test_patch_warehouse_id_rejected_after_submission` теперь проходит через учётную запись селлера и проверяет `409 not_draft` после передачи заявки.
- `test_patch_warehouse_id_non_operational_rejected` проверяет `422 invalid_warehouse` для неоперационного склада.
- Фильтр `-k "warehouse"` также выполнил два относящихся к складу регрессионных теста этого файла.

## Гейты

- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch`; команда `pytest -q backend/tests/test_inbound_intake.py -k "warehouse"` — успешно: `5 passed, 16 deselected in 7.46s`.
- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend`; команда `ruff check app/api/inbound_intake.py app/services/inbound_intake_service.py tests/test_inbound_intake.py` — успешно: `All checks passed!`.
- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend`; команда `mypy app/api/inbound_intake.py app/services/inbound_intake_service.py` — завершилась с кодом 1 из-за двух существующих ошибок в импортированных соседних модулях: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/wildberries_credentials_service.py:167` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_stock_sync_service.py:617`.
- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend`; команда `mypy --follow-imports=silent app/api/inbound_intake.py app/services/inbound_intake_service.py` — успешно: `Success: no issues found in 2 source files`.
- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch`; команда `git diff --check -- backend/app/services/inbound_intake_service.py backend/tests/test_inbound_intake.py night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — успешно, ошибок пробелов нет.
- Рабочий каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch`; команда `git add backend/app/services/inbound_intake_service.py backend/tests/test_inbound_intake.py night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — не выполнена средой: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`).
- `back_guard.py` не запускался: новый роут не добавлялся, изменено поведение уже существующего PATCH.
- `check_migrations.py` не запускался: миграций нет.
- Полные `pytest`, `ruff check .` и `mypy .` не запускались согласно ограничению атомарной проверки.

## Не реализовано

- Frontend-находки 1 и 3 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/REVIEW.md` не реализованы: они относятся к ролям `screen-dev` и отдельным атомам 3–4 в `FEATURES.md`.
- Проверка наличия тарифа и ячеек у нового склада не добавлялась: `FEATURES.md` явно оставляет её за границами атома.

## Находки

- Предыдущая проверка блокировки после передачи использовала администратора и не ловила разрешение `_request_plan_editable` для селлера в статусе `submitted`; тест усилен seller-сценарием, а сервис получил отдельную draft-охрану именно для `warehouse_id`.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и production не открывались и не изменялись.

## Блокеры

- Локальная реализация и артефакт не сохранены новым коммитом: sandbox разрешает запись в worktree, но запрещает запись в общий Git-каталог `/Users/deniscivkunov/Projects/WMS/.git`, где находится индекс зарегистрированной рабочей копии. Создание второго репозитория или временного клона не выполнялось, потому что это прямо запрещено правилами проекта.
