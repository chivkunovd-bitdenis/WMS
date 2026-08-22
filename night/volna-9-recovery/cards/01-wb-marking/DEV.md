# Фича 1

# DEV · 01-wb-marking · backend-dev · атом 1 (rework)

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py` — ограничено ожидание `Retry-After` одной секундой; после первого `429` та же пачка повторяется ровно один раз.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py` — тест защищает ограничение внешнего `Retry-After: 3600` и единственный повтор.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — отчёт выполнения.

## Гейты

- `ruff check app/services/wildberries_fbs_client.py tests/test_wildberries_marketplace_fbs_client.py` — PASS.
- `mypy app/services/wildberries_fbs_client.py` — PASS.
- `pytest -q tests/test_wildberries_marketplace_fbs_client.py` — PASS, 17 passed.
- `ruff check .` — FAIL: 80 существующих нарушений вне изменённого слоя; два изменённых файла проходят адресную проверку.
- `mypy .` — FAIL: 21 существующая ошибка в шести посторонних файлах; изменённый модуль проходит адресную проверку.
- `pytest` — не завершён: средство выполнения прервало полный запуск после начала (827 собранных тестов, без зафиксированного итогового вердикта); целевой набор прошёл.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` нет.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` нет; миграции не добавлялись.

## Не реализовано

- Находки ревью по `fbs_marking_service.py`, `fbs_autopoll_service.py`, журналу событий и их тестам относятся к другим атомам `FEATURES.md`; этот проход ограничен атомом 1 и его клиентским слоем. Исправлена относящаяся к нему находка №6: верхняя граница `Retry-After`.

## Находки

- Секреты, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не изменялись.

# Фича 2

# DEV · 01-wb-marking · backend-dev · атом 2 (rework)

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py` — усилена проверка записи `wb_orphaned`: аудит-событие сохраняет допустимый тип и ссылку на исходный КИЗ, не меняя статус, пул или товар КИЗ.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py` — в базовом коммите этого атома уже определены `EVENT_WB_ORPHANED` и его допустимость в `MARKING_CODE_EVENT_TYPES`; повторная правка модели не потребовалась.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — отчёт rework-прохода.

## Гейты

- `ruff check backend/app/models/marking_code.py backend/tests/test_marking_code_events.py` — PASS.
- `mypy backend/app/models/marking_code.py backend/tests/test_marking_code_events.py` — PASS.
- `pytest -q backend/tests/test_marking_code_events.py` — PASS.
- `ruff check .` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — FAIL: 80 уже существующих ошибок вне изменённых файлов.
- `mypy .` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — FAIL: 21 уже существующая ошибка в шести посторонних файлах.
- `pytest` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — итог не получен: запуск собрал 827 тестов и начал выполнение, но среда прекратила возврат вывода до финального статуса; целевой набор прошёл.
- `python3 scripts/ci/back_guard.py` — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` в рабочей копии нет.
- `python3 scripts/ci/check_migrations.py` — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` в рабочей копии нет; миграции не добавлялись.

## Не реализовано

- Замечание review №7 о проверке вызова `wb_orphaned` из сервисной сверки не менялось: этот вызов и сценарии `missing`/`replacement_required` принадлежат следующему атому 3 в `backend/app/services/fbs_marking_service.py`. В границе атома 2 покрыта допустимость и сохранение самого события в существующем журнале.
- Прочие замечания `REVIEW.md` относятся к атомам 1, 3 и 4; этот проход не затрагивает соседние сервисы.

## Находки

- Секреты, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не изменялись.

# Фича 3

# DEV · 01-wb-marking · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py` — безопасное применение `metaDetails`, сохранение raw-блока, согласование legacy `check_status`, блокировки актуальных строк и идемпотентный аудит.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_autopoll_service.py` — частично возвращённый batch не учитывается как успешная синхронизация и не запускает производное обновление.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py` — сценарии решений WB, неполного ответа, сохранения raw-данных и единственного `wb_orphaned`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — этот отчёт.

## Гейты

- `ruff check` (из `backend/`, изменённые файлы): PASS.
- `ruff check .` (из `backend/`): FAIL — 80 существующих нарушений в несвязанных API, сервисах, скриптах и тестах; данный атом новых нарушений не добавляет.
- `mypy .` (из `backend/`): FAIL — 21 существующая ошибка в шести несвязанных файлах; изменённый `fbs_marking_service.py` типовых ошибок не содержит.
- `pytest -q tests/test_fbs_kiz.py -k 'wb_meta_decision_is_safe or partial_wb_row or orphaned_audit'`: PASS, 11 passed.
- `pytest` (из `backend/`): полный прогон начат, но в доступной ночной оболочке не вернул финальный код после 11 точек вывода; итог не подтверждён.
- `python3 scripts/ci/back_guard.py`: не запущен — файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` нет.
- `python3 scripts/ci/check_migrations.py`: не запущен — файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` нет.

## Не реализовано

- Ревью-находка о максимальном `Retry-After` относится к клиенту WB из атома 1 и не менялась в атоме 3.
- Миграции: нет. Для однократности `wb_orphaned` используется блокировка уже существующей строки `MarkingCode`; схема не расширяется.

## Находки

- Секреты, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не изменялись.

# Фича 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py` — добавлен сценарий batch-сверки 201 активного заказа: последовательные пачки 100/100/1, ответ в обратном порядке, частичный ответ, ошибка средней пачки и продолжение последней.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — отчёт backend-разработки.

## Гейты

- `ruff check .` из `backend/` — не пройден: 82 существующие ошибки в несвязанных файлах; добавленный `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py` проходит `ruff check`.
- `mypy .` из `backend/` — не пройден: 21 существующая ошибка в шести несвязанных файлах (`inventory_movement_report_service.py`, `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`, `wildberries_product_import_service.py`, служебный cleanup-скрипт).
- `pytest` из `backend/` — полный запуск стартовал (839 тестов), но среда оборвала поток до итогового кода; целевой `pytest tests/test_fbs_marking.py -q` пройден: 6 passed.
- `python3 scripts/ci/back_guard.py` из корня — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` в этой рабочей копии нет.
- `python3 scripts/ci/check_migrations.py` из корня — не запущен по той же причине: каталога `scripts/ci/` в этой рабочей копии нет.
- `git diff --check` — пройден.

## Не реализовано

- Изменений сервисов не потребовалось: текущая реализация `sync_marking_statuses_for_assembling_supplies` уже последовательно режет уникальные `wb_order_id` на пачки до 100, пропускает локальную обработку отсутствующих строк частичного ответа и продолжает после ошибки пачки. Добавлен регрессионный тест, который закрепляет эти требования и находку ревью №3.

# Фича 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_client.py` — устаревшие одиночные `GET /api/v3/orders/{orderId}/meta` и `fetch_marketplace_order_meta` отсутствуют; для чтения метаданных остаётся batch POST из `wildberries_fbs_client.py`. В этом rework код не менялся: состояние уже сохранено коммитом `db550384`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — отчёт повторной проверки атома 5.

## Гейты

- `ruff check .` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — не пройден: 80 существующих нарушений в несвязанных файлах; `ruff check app/services/wildberries_client.py tests/test_wildberries_client.py` — пройден.
- `mypy .` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — не пройден: 21 существующая ошибка в шести несвязанных файлах; `mypy app/services/wildberries_client.py` — пройден.
- `pytest tests/test_wildberries_client.py tests/test_wildberries_marketplace_fbs_client.py -q` — пройден: 26 passed. Полный `pytest -q` был запущен, но не завершился: после 18 тестов среда прекратила выдавать результат без кода завершения.
- `python3 scripts/ci/back_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking` — не запущен: файл отсутствует в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking` — не запущен: файл отсутствует в этой рабочей копии.
- Статический поиск `fetch_marketplace_order_meta` в `backend/app` и `backend/tests` — совпадений нет.
- `git diff --check` — пройден.

## Не реализовано

- Нет: атом 5 уже буквально реализован в сохранённом коде. Находки `REVIEW.md` №1–9 относятся к соседним сервисам, моделям и тестам фич 1–4; они не затрагивают единственный разрешённый слой атома 5 — удаление мёртвого одиночного чтения.
