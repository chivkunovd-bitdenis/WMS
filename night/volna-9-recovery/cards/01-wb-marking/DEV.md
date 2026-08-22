# Фича 1

# DEV · 01-wb-marking · атом 1 · rework

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py`: batch-чтение `metaDetails` сохраняет `key`, `value`, `decision` и `reason`; при `429` один раз ожидает `Retry-After` (число или HTTP-дата) и повторяет ту же пачку не более 100 заказов.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py`: ответы 4xx/5xx и неразбираемое тело возвращают ошибку, без частичного успешного результата.

## Миграции

- Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py`: полный DTO `decision`/`value`/`reason`, один повтор после `429`, числовой и HTTP-date `Retry-After`, ошибки 400/500 и неразбираемый успешный ответ.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status`: адресная регрессия вызывающего контура.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

Код атома уже сохранён в текущей ветке коммитом `8e8f2a3e9908956550eb8cb3278ec137d404f8ba`; повторная проверка JUDGE.md не выявила замечаний в файлах и слое этого атома.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/services/wildberries_fbs_client.py tests/test_wildberries_marketplace_fbs_client.py` — PASS: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/wildberries_fbs_client.py` — PASS: `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_wildberries_marketplace_fbs_client.py` — PASS: `19 passed in 0.06s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status` — PASS: `1 passed in 0.94s`.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — не применим: роуты не добавлялись и не менялись.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — не применим: миграции не добавлялись.

## Не реализовано

- Замечание `JUDGE.md` о недоступном живом UI относится к browser-product-review экранов S-03, S-14 и S-15. Этот backend-атом не меняет UI, поэтому исправлений в его файлах и слое нет.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Нет для backend-атома. Browser-product-review остаётся отдельной проверкой живого UI.

# Фича 2

# DEV · 01-wb-marking · атом 2/5 (повторная проверка после JUDGE)

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет.
- Сервисы: новых и изменённых сервисов нет; атом расширяет допустимые типы существующего журнала КИЗ.
- Модель `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py`: `EVENT_WB_ORPHANED` включён в `MARKING_CODE_EVENT_TYPES`.
- Журнал КИЗ принимает `wb_orphaned` для исходного `MarkingCode`; добавление записи не освобождает код и не меняет его статус, пул или продуктовую привязку.

## Миграции

Нет: `event_type` уже является строковым полем существующей таблицы `marking_code_events`, поэтому новый допустимый тип не меняет схему.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py`: `test_wb_orphaned_event_is_recorded_without_releasing_code` создаёт событие через существующую модель и проверяет `code_id`, пул, статус и продуктовую привязку КИЗ.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/models/marking_code.py tests/test_marking_code_events.py` — PASS, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/models/marking_code.py` — PASS, `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_marking_code_events.py::test_wb_orphaned_event_is_recorded_without_releasing_code` — PASS, `1 passed in 0.90s`.
- `python3 scripts/ci/back_guard.py` — не применим: атом не добавляет и не меняет роуты.
- `python3 scripts/ci/check_migrations.py` — не применим: атом не добавляет миграцию.

## Не реализовано

- Повторная и конкурентная дедупликация `wb_orphaned` не входит в этот атом: её реализует следующая фича сверки без новой таблицы или миграции.
- Из `JUDGE.md` нет находок в модели, журнале или тесте этого атома. Единственная находка — недоступность живого UI-стенда для browser-проверки — относится к отдельной продуктовой проверке и не требует backend-изменений.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

Нет для backend-атома. Живой browser-review остаётся заблокированным по причине из `JUDGE.md`; это не меняет результат целевых backend-гейтов.

# Фича 3

# DEV · 01-wb-marking · атом 3 · rework

## Что реализовано

- Эндпоинты: нет.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py`: применяет `metaDetails.decision` к существующей привязке КИЗ безопасно — сохраняет `reason` и сырой блок, сопоставляет известные решения, фиксирует `missing` или `replacement_required` без отвязки КИЗ и создаёт единственный `wb_orphaned`.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py`: ответ без строки заказа, без ожидаемого `kind` либо с неизвестным решением переводит вердикт в `unknown`, не перезаписывает локальную привязку, жизненный статус КИЗ, сохранённые детали или дату успешной проверки.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

## Миграции

- Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py`: отображения `filled`, `optional`, `pending`, `required` без значения, `invalid`, неизвестного решения и несовпадающего значения; частичный и пропущенный ответ; однократный аудит `wb_orphaned` для повторных и конкурентных `missing` / `replacement_required`.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking && ruff check backend/app/services/fbs_marking_service.py backend/tests/test_fbs_kiz.py` — успешно: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/fbs_marking_service.py` — не зелёный из-за четырёх ранее существующих ошибок в импортируемых соседних модулях: `app/services/wildberries_credentials_service.py:167`, `app/services/fbs_stock_sync_service.py:617`, `app/services/fbs_warehouse_binding_service.py:23` и `:291`; в файле атома ошибок не выведено.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_fbs_kiz.py::test_fbs_marking_wb_meta_decision_is_safe_and_preserves_raw_detail tests/test_fbs_kiz.py::test_fbs_marking_partial_wb_row_is_unknown_without_fresh_check_time tests/test_fbs_kiz.py::test_fbs_marking_omitted_wb_row_clears_stale_verdict_only tests/test_fbs_kiz.py::test_fbs_marking_orphaned_audit_is_created_once_for_concurrent_and_repeated_mismatch` — успешно: `13 passed in 10.91s`.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — не применимо: атом не добавляет маршрут.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — не применимо: атом не добавляет миграцию.

## Не реализовано

- Находка `JUDGE.md` относится только к недоступности живого UI-стенда и отсутствию browser evidence; изменений в backend-слое атома 3 она не требует.
- Новые эндпоинты, модели, миграции, UI и обращения к внешнему WB не добавлялись.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

# Фича 4

# DEV · 01-wb-marking · атом 4 · rework

## Что реализовано

- Эндпоинты: нет.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_autopoll_service.py`: активные собираемые поставки сверяются последовательными пачками до 100 уникальных `wb_order_id`; после ошибки одной пачки следующая продолжает работу, а ответ применяется по `order_id`, а не по позиции.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py`: ручной путь с одним заказом остаётся допустимой пачкой; пропущенная строка WB не засчитывается как успешная сверка.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

Код атома уже находится в текущем `HEAD`; по находке из `JUDGE.md` изменений backend-кода не требуется: вердикт фиксирует только отсутствие живого браузерного стенда.

## Миграции

- Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py::test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches`: 201 заказ обрабатывается пачками `100/100/1` без дублей и параллельности; неполный ответ сопоставляется по `order_id`, ошибка средней пачки сохраняет её локальные данные и не останавливает последнюю.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status`: ручная сверка одного заказа использует batch-клиент с одним ID.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/services/fbs_autopoll_service.py app/services/fbs_marking_service.py tests/test_fbs_marking.py` — успешно: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/fbs_autopoll_service.py app/services/fbs_marking_service.py` — код выхода 1 из-за четырёх ранее существующих ошибок в импортируемых соседних модулях: `wildberries_credentials_service.py:167`, `fbs_stock_sync_service.py:617`, `fbs_warehouse_binding_service.py:23` и `:291`; в двух модулях атома ошибок не выведено.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_fbs_marking.py::test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status` — успешно: `2 passed in 1.84s`.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — неприменимо: атом не добавляет маршрут.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — неприменимо: атом не добавляет миграцию.

## Не реализовано

- Исправление browser evidence из `JUDGE.md`: это вне backend-слоя данного атома; проверка требует живого UI-стенда и снимков зон `S-03`, `S-14`, `S-15`.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Нет для backend-реализации. Browser-проверка из `JUDGE.md` остаётся отдельным непроходимым в этой роли контуром.

# Фича 5

# DEV · 01-wb-marking · атом 5 · rework

## Что реализовано

- Эндпоинты: нет.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_client.py`: подтверждено отсутствие устаревшего одиночного чтения `GET /api/v3/orders/{orderId}/meta` и его функции `fetch_marketplace_order_meta`; актуальное batch-чтение остаётся единственным путём.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

Backend-код в текущем `HEAD` уже соответствует атому 5, поэтому изменение кода не потребовалось. Находка из `JUDGE.md` относится только к отсутствующему живому browser-стенду и не затрагивает файлы или слой этого атома.

## Миграции

- Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_client.py`: импорт и поведение публичных функций клиента, включая запись метаданных.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py`: batch-клиент метаданных, остающийся актуальным путём чтения.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/services/wildberries_client.py tests/test_wildberries_client.py tests/test_wildberries_marketplace_fbs_client.py` — успешно: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/wildberries_client.py` — успешно: `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_wildberries_client.py tests/test_wildberries_marketplace_fbs_client.py` — успешно: `28 passed in 0.15s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ! rg -n 'fetch_marketplace_order_meta' app tests --glob '*.py' && ! rg -n 'async def fetch_marketplace_order_meta|def fetch_marketplace_order_meta' app --glob '*.py'` — успешно: совпадений нет.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — неприменимо: атом не добавляет маршрут.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — неприменимо: атом не добавляет миграцию.

## Не реализовано

- Нет: весь объём атома уже присутствует в текущем backend-коде и подтверждён целевыми проверками.

## Находки

- `JUDGE.md` фиксирует отсутствие живого UI-стенда и browser evidence. Это не относится к backend-файлу и не требует изменения в атоме 5.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Нет для backend-реализации атома 5.
