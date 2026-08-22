# Фича 1

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

# Фича 2

# DEV · 01-wb-marking · атом 2/5

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет.
- Сервис: новых и изменённых сервисов нет; атом расширяет существующий журнал КИЗ на уровне модели.
- Модель `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py`: тип события `wb_orphaned` включён в допустимый набор `MARKING_CODE_EVENT_TYPES`.
- Журнал КИЗ принимает событие `wb_orphaned`, связанное с исходным `MarkingCode`; создание события не меняет жизненный статус кода, его пул и продуктовую привязку.

## Миграции

Нет: `event_type` уже хранится в строковом поле существующей таблицы журнала, поэтому новый допустимый тип не требует изменения схемы базы данных.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py`: `test_wb_orphaned_event_is_recorded_without_releasing_code` создаёт `wb_orphaned` через существующую модель журнала и проверяет тип события, связь `code_id`, прежние статус, пул и продуктовую привязку КИЗ.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/models/marking_code.py tests/test_marking_code_events.py` — PASS, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/models/marking_code.py` — PASS, `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_marking_code_events.py::test_wb_orphaned_event_is_recorded_without_releasing_code` — PASS, `1 passed in 4.95s`.
- `back_guard.py` — не применим: атом не добавляет и не меняет роуты.
- `check_migrations.py` — не применим: атом не добавляет миграцию.

## Не реализовано

- Конкурентная и повторная дедупликация `wb_orphaned` не реализовывалась в этом атоме: `FEATURES.md` прямо относит повторную запись для той же привязки к следующей фиче сверки и запрещает ради неё новую таблицу или миграцию.
- Находки 1–3 из `REVIEW.md` относятся к `/backend/app/services/fbs_marking_service.py` и тестам следующего сервисного атома, а не к модели и журналу атома 2.
- Находка 4 из `REVIEW.md` требует конкурентного сценария сервиса сверки в `/backend/tests/test_fbs_kiz.py`; этот файл и поведение находятся за границей текущего атома 2.

## Находки

- В `CONTRACT.md` нет отдельного заголовка `API и данные`; backend-граница атома буквально задана в `FEATURES.md` и подтверждена `ARCH-CROSS.md`: карточка 01 владеет семантикой `metaDetails` и не освобождает КИЗ автоматически.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Backend-изменения атома сохранены в достижимых коммитах: основная модель и тест — `5ae86fe8018170fc68064e87b5815f8cb8af0fd3`, дополнительные проверки связи события после ревью — `acb19c362589b5544d961eda1b75e896790a3388`.
- Обновлённый обязательный отчёт `DEV.md` создан локально, но сохранить его отдельным коммитом в этой сессии невозможно: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/index.lock`, потому что метаданные worktree находятся вне разрешённой для записи области песочницы (`Operation not permitted`).

# Фича 3

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

# Фича 4

# DEV · 01-wb-marking · атом 4 · rework

## Что реализовано

- Эндпоинты: нет.
- Сервис `sync_marking_statuses_for_assembling_supplies`: подтверждена существующая последовательная обработка уникальных `wb_order_id` пачками `100/100/1`, применение ответа по `order_id` и продолжение после локализованной ошибки пачки.
- Сервис `_sync_order_meta_from_wb`: адресными тестами подтверждены исправления четырёх находок ревью — сохранение полного удалённого снимка, контрактное отображение `check_status`, отказ от legacy `row.meta` и однократный аудит при конкурентном запуске.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py` — batch-тест дополнен явной проверкой последовательности запросов и сохранности локальных данных ошибочной пачки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — отчёт текущего backend-атома.

## Миграции

- Нет.

## Тесты

- Усилен `test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches`: 201 заказ разбивается на последовательные уникальные пачки `100/100/1`; первая пачка возвращается в обратном порядке и без одной строки, средняя падает, последняя всё равно выполняется; максимум одновременно активен один batch-запрос; 100 локальных маркировок ошибочной пачки остаются в прежних статусах.
- Повторно проверены параметризованные решения WB, неизвестный ключ `metaDetails`, отсутствие ожидаемого `kind`, полный удалённый снимок и конкурентный плюс повторный запуск `wb_orphaned`.
- Проверен существующий ручной путь одного заказа через `test_fbs_marking_sync_updates_check_status`: один ID остаётся допустимой пачкой.

## Гейты

- `ruff check tests/test_fbs_marking.py app/services/fbs_marking_service.py app/services/fbs_autopoll_service.py tests/test_fbs_kiz.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — пройдено: `All checks passed!`.
- `mypy app/services/fbs_marking_service.py app/services/fbs_autopoll_service.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — целевые модули проверены, общий код возврата 1 из-за четырёх уже существующих ошибок в импортируемых соседних файлах `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; ошибок в двух названных целевых модулях вывод не содержит.
- `pytest -q tests/test_fbs_marking.py::test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status tests/test_fbs_kiz.py::test_fbs_marking_wb_meta_decision_is_safe_and_preserves_raw_detail tests/test_fbs_kiz.py::test_fbs_marking_partial_wb_row_is_unknown_without_fresh_check_time tests/test_fbs_kiz.py::test_fbs_marking_orphaned_audit_is_created_once_for_concurrent_and_repeated_missing` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — пройдено: `13 passed in 49.31s`.
- `python3 scripts/ci/back_guard.py` — неприменим: новый роут не добавлялся.
- `python3 scripts/ci/check_migrations.py` — неприменим: миграция не добавлялась.
- `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking` — пройдено.
- `git add -- backend/tests/test_fbs_marking.py night/volna-9-recovery/cards/01-wb-marking/DEV.md && git commit -m "test(wb-marking): prove sequential batch recovery"` — не выполнено ограниченной средой: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/index.lock` (`Operation not permitted`).

## Не реализовано

- Нет. Рабочая логика атома и исправления находок ревью уже присутствовали в ветке; текущий rework усилил недостающие доказательства последовательности и сохранности данных на ошибке пачки.

## Находки

- Формального раздела «API и данные» в `CONTRACT.md` нет; реализация продолжена по отдельному разрешению владельца ночной волны и однозначным backend-правилам в `FEATURES.md`, `ARCH.md` и `REVIEW.md`.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Изменения локально реализованы и проверены, но не сохранены коммитом: служебный Git-каталог зарегистрированного worktree доступен этой среде только для чтения. Для сохранения нужен повтор `git add` и `git commit` процессом с правом записи в `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/`.

# Фича 5

# DEV · 01-wb-marking · атом 5 · rework

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет; устаревший одиночный `GET /api/v3/orders/{orderId}/meta` отсутствует.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_client.py`: удалённая ранее функция `fetch_marketplace_order_meta` и её вызовы отсутствуют; комментарий mock-хранилища очищен от упоминания удалённого одиночного `GET`.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py`: batch `POST /api/marketplace/v3/orders/meta` подтверждён как единственный путь чтения метаданных.
- Находки `REVIEW.md`: четыре исправления соседних атомов присутствуют в текущей ветке и повторно подтверждены названными ревью-сценариями; дополнительного изменения их файлов в атоме 5 не потребовалось.

## Миграции

- Нет.

## Тесты

- Новые тесты не добавлялись: атом удаляет мёртвое чтение, а существующие клиентские тесты полностью покрывают разрешённые операции записи/удаления и batch-чтение.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_client.py` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py`: подтверждены клиентские контракты, включая batch-чтение `metaDetails`.
- Адресные тесты из `REVIEW.md`: подтверждены полный сырой снимок, контрактный `check_status`, отсутствие legacy fallback и конкурентная однократность `wb_orphaned`.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_client.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

## Гейты

- `ruff check app/services/wildberries_client.py tests/test_wildberries_client.py tests/test_wildberries_marketplace_fbs_client.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — пройдено: `All checks passed!`.
- `mypy app/services/wildberries_client.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — пройдено: `Success: no issues found in 1 source file`.
- `pytest -q tests/test_wildberries_client.py tests/test_wildberries_marketplace_fbs_client.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — пройдено: `26 passed in 0.24s`.
- `pytest -q tests/test_fbs_marking.py::test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status tests/test_fbs_kiz.py::test_fbs_marking_wb_meta_decision_is_safe_and_preserves_raw_detail tests/test_fbs_kiz.py::test_fbs_marking_partial_wb_row_is_unknown_without_fresh_check_time tests/test_fbs_kiz.py::test_fbs_marking_orphaned_audit_is_created_once_for_concurrent_and_repeated_missing` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — пройдено: `13 passed in 22.69s`.
- `if rg -n 'fetch_marketplace_order_meta' backend/app backend/tests; then exit 1; else printf '%s\\n' 'PASS: fetch_marketplace_order_meta отсутствует в backend/app и backend/tests'; fi` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking` — пройдено: определений и вызовов нет.
- `rg -n 'fetch_marketplace_orders_meta_batch|MARKETPLACE_ORDERS_META_BULK_PATH' backend/app/services backend/tests/test_wildberries_marketplace_fbs_client.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking` — пройдено: batch-функция определена, вызывается сервисами и покрыта тестами.
- `python3 scripts/ci/back_guard.py` — неприменим: новый роут не добавлялся.
- `python3 scripts/ci/check_migrations.py` — неприменим: миграция не добавлялась.

## Не реализовано

- Нет: атом 5 выполнен буквально; новый fallback и новое пользовательское действие не добавлялись.

## Находки

- В `CONTRACT.md` нет отдельного раздела `API и данные`; для rework использованы однозначные backend-границы атома 5 из `FEATURES.md`, решения `ARCH.md` и проверяемые требования `REVIEW.md`.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Нет.
