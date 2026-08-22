# DEV · 01-wb-marking · переделка атома 1 по REVIEW.md

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py`: исходная реализация атома уже читает `decision`, `value`, `reason`, ограничивает пачку 100 заданиями, один раз повторяет 429 после ограниченного `Retry-After` и возвращает ошибку для остальных HTTP-ошибок и неразбираемого тела; изменения не потребовались.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py`: сводка заказа теперь хранит настоящий снимок `metaDetails` с удалёнными `value`, `decision`, `reason` и неизвестными ключами; deprecated-объект `meta` больше не участвует в применении ответа.
- Совместимое поле `check_status` теперь выводится из `metaDetails` по контракту: `required → new`, неизвестное решение и отсутствующий ожидаемый `kind → error`, `pending → checking`, успешные и отклонённые решения сохраняют утверждённые отображения.
- Однократность `wb_orphaned` проверяется при двух одновременных синхронизациях и последующем повторе.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py`: существующие тесты подтверждают полный DTO, ровно один повтор 429 с `Retry-After`, отсутствие повтора для других 4xx/5xx и ошибку на неразбираемом теле.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py`: усилены проверки сырой сводки заказа, неизвестного ключа, удалённого значения, совместимого `check_status`, игнорирования legacy `meta` и конкурентной однократности `wb_orphaned`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_box_clear_and_workspace_extras.py`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_packaging_integration.py`: устаревшие моки `meta` переведены на официальный `metaDetails`; адресные сценарии прошли.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_box_clear_and_workspace_extras.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_packaging_integration.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

## Гейты

- `ruff check` по всем изменённым backend-файлам: PASS.
- `ruff check .` из `backend/`: FAIL на 80 ранее существующих замечаниях в несвязанных файлах; изменённые файлы в списке ошибок отсутствуют.
- `mypy app/services/fbs_marking_service.py app/services/wildberries_fbs_client.py`: изменённые сервисы без собственных ошибок, но запуск завершается FAIL на 4 ранее существующих ошибках в импортируемых `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`.
- `mypy .` из `backend/`: FAIL, 21 ранее существующая ошибка в 6 несвязанных файлах.
- Адресные тесты клиента и маркировки: PASS; `test_wildberries_marketplace_fbs_client.py` и `test_fbs_kiz.py` прошли полностью, дополнительно три затронутых интеграционных сценария прошли адресно.
- `pytest -q` из `backend/`: FAIL после `337 passed, 4 skipped` на несвязанном `test_fbs_cutoff_autoplans_supply_manual_date_and_calendar`; тест использует фиксированную дату `2026-08-15`, которая к текущей дате `2026-08-22` закономерно получает `deadline_passed`.
- `python3 scripts/ci/back_guard.py`: NOT RUN — файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` отсутствует в checkout.
- `python3 scripts/ci/check_migrations.py`: NOT RUN — файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` отсутствует в checkout.

## Не реализовано

- Пунктов контракта или относящихся к этому backend-слою находок `REVIEW.md`, оставленных без реализации, нет.
- Репозиторные lint/type-ошибки, календарный тест и отсутствующие guard-скрипты не исправлялись: они находятся вне границ атома и не связаны с чтением или применением `metaDetails` WB.

## Находки

- Секреты, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Функциональных блокеров атома нет. Репозиторные гейты не полностью зелёные по причинам, перечисленным в разделе `Гейты`.
