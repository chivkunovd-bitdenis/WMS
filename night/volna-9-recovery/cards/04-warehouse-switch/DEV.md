# DEV · 04-warehouse-switch · атом 1

## Что реализовано

- Эндпоинт `PATCH /operations/inbound-intake-requests/{id}` принимает явно переданный `warehouse_id`, передаёт значение и признак присутствия поля в сервис и возвращает обновлённый склад черновика.
- Сервис `inbound_intake_service.patch_request_draft` меняет склад только у документа в статусе `draft` и только на операционный склад того же tenant; отсутствующий, чужой, неоперационный или явно `null` склад даёт `InboundIntakeError("invalid_warehouse")`.
- Для документа после передачи сохранён существующий ответ `409 not_draft`, поэтому склад закреплён после выхода из черновика.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/inbound_intake.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/inbound_intake_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_inbound_intake.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Миграции

Нет: атом меняет PATCH-схему и сервисную валидацию, структура базы данных не меняется.

## Тесты

- `test_patch_warehouse_id_saves_on_draft` проверяет `200` и сохранение второго операционного склада; в том же сценарии явно переданный `null` проверен как `422 invalid_warehouse`.
- `test_patch_warehouse_id_rejected_after_submission` проверяет запрет смены склада после передачи документа: `409 not_draft`.
- `test_patch_warehouse_id_non_operational_rejected` проверяет отказ для неоперационного склада: `422 invalid_warehouse`.

## Гейты

- `pytest -q backend/tests/test_inbound_intake.py -k "warehouse"` из корня worktree — успешно: `5 passed, 16 deselected`.
- `ruff check app/api/inbound_intake.py app/services/inbound_intake_service.py tests/test_inbound_intake.py` из `backend/` — успешно: `All checks passed!`.
- `pytest -q backend/tests/test_inbound_intake.py -k "patch_warehouse_id"` из корня worktree — успешно: `3 passed, 18 deselected`.
- `mypy app/api/inbound_intake.py app/services/inbound_intake_service.py` из `backend/` — затронутые модули разобраны, но общий обход импортов завершился с двумя существующими ошибками в незатронутых `app/services/wildberries_credentials_service.py:167` и `app/services/fbs_stock_sync_service.py:617`.
- `mypy --follow-imports=skip app/api/inbound_intake.py app/services/inbound_intake_service.py` из `backend/` — неприменимый режим дал 64 ошибки `Any` в FastAPI/Pydantic-декораторах из-за полного пропуска импортов; результат не использован как проверка.
- `mypy --follow-imports=silent app/api/inbound_intake.py app/services/inbound_intake_service.py` из `backend/` — успешно: `Success: no issues found in 2 source files`; этот режим проверил затронутые модули и подавил диагностику внутри импортированных соседних модулей.
- `git diff --check` из корня worktree — успешно, ошибок пробелов нет.
- `back_guard.py` не запускался: новый роут не добавлялся, расширена схема существующего PATCH.
- `check_migrations.py` не запускался: миграций нет.
- Полные `pytest`, `ruff check .` и `mypy .` не запускались согласно ограничению атомарной проверки.
- `git add backend/app/api/inbound_intake.py backend/app/services/inbound_intake_service.py backend/tests/test_inbound_intake.py night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` из корня worktree — не выполнен средой: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`).

## Не реализовано

- Frontend-находки 1 и 3 из `REVIEW.md` не реализованы: они относятся к ролям `screen-dev` и отдельным атомам 3–4 в `FEATURES.md`.
- Проверка наличия тарифа и ячеек для нового склада не добавлялась: `FEATURES.md` явно оставляет её за границами этого атома.

## Находки

- Обычный целевой запуск mypy поднимает две ранее существовавшие ошибки в соседних сервисах WB/FBS; файлы этого атома проходят проверку при подавлении диагностики внутри импортированных модулей.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не открывались и не изменялись.

## Блокеры

- Backend-реализация и артефакт находятся в рабочем дереве, но не сохранены новым коммитом: sandbox разрешает запись в worktree, однако запрещает запись в общий Git-каталог `/Users/deniscivkunov/Projects/WMS/.git`, где расположен индекс этой зарегистрированной рабочей копии.
