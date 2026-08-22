# Фича 1

# DEV · 01-wb-marking · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py`

## Что реализовано

- `fetch_marketplace_orders_meta_batch`: `MarketplaceMetaDetail` теперь сохраняет `decision`, `value` и `reason` из `metaDetails`.
- `fetch_marketplace_orders_meta_batch`: при первом `429` ждёт числовой `Retry-After` и повторяет ровно ту же пачку один раз; остальные ошибки и неразбираемый ответ возвращаются как ошибка без DTO.

## Миграции

Нет.

## Тесты

- Расширен batch-тест на сохранение `decision`, `value`, `reason`.
- Добавлен тест ровно одного повтора `429` с проверкой `Retry-After`.
- Добавлены проверки отсутствия повтора для `400`/`500` и ошибки неразбираемого тела после повтора.

## Гейты

- `ruff`: целевые файлы — PASS; полный `ruff check .` — FAIL из-за 81 ранее существующей ошибки в несвязанных файлах backend.
- `mypy`: целевой файл `app/services/wildberries_fbs_client.py` — PASS (`Success: no issues found in 1 source file`). Полный запуск остановлен после полного ruff.
- `pytest`: `tests/test_wildberries_marketplace_fbs_client.py` — PASS, 17 passed. Полный suite не запускался после обнаружения общих lint-ошибок.
- `back_guard.py`: FAIL технически — файл отсутствует в рабочей копии по ожидаемому пути `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py`.
- `check_migrations.py`: FAIL технически — файл отсутствует в рабочей копии по ожидаемому пути `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py`; миграций нет.

## Не реализовано

- Остальные фичи карточки (`wb_orphaned`, применение ответа к локальной привязке, автополлер пачек и удаление одиночного чтения) не затрагивались: реализован только кусок 1.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.

# Фича 2

# DEV · 01-wb-marking · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py`
  — добавлен допустимый тип события `EVENT_WB_ORPHANED = "wb_orphaned"`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py`
  — добавлен тест записи `wb_orphaned` в существующий журнал без изменения статуса,
  `pool_id` и `product_id` КИЗ.

## Гейты

- `ruff check .` — FAIL: 81 ранее существующая ошибка в несвязанных файлах; точечные файлы PASS.
- `mypy .` — FAIL: 21 ранее существующая ошибка в 6 несвязанных файлах; точечная модель PASS,
  тестовый файл упирается в существующий импорт `test_packaging_tasks` без stubs.
- `pytest -q tests/test_marking_code_events.py` — PASS, 3 passed.
- `pytest -q` — прерван после 92 passed и 5 warnings из-за длительного полного прогона.
- `python3 scripts/ci/back_guard.py` — недоступен: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — недоступен: файл отсутствует в рабочей копии.
- `git diff --check` — PASS.

## Не реализовано

- Повторная запись для одной привязки не добавлялась: её идемпотентность относится к следующей
  фиче сверки.
- Автоматическая сверка WB, изменение статуса, освобождение пула и новые API не входят в этот
  атомарный кусок и не реализовывались.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет
  Wildberries не читались и не затрагивались.

# Фича 3

# DEV · 01-wb-marking · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py` — безопасное применение ответа WB: полный `reason` и сырой блок, отображения решений `filled`/`optional`/`pending`/`required`/`invalid`, `missing` для `required` без значения, `replacement_required` для отличающегося значения, `unknown` для неизвестных и неполных строк, дата проверки только при возвращённой строке, однократный `wb_orphaned`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py` — тестовая фиксация отображений решений, включая неизвестное решение.

## Гейты

- `ruff check .` — не запускался для всего backend; точечные изменённые файлы PASS.
- `mypy .` — FAIL на ранее существующих ошибках в несвязанных файлах; изменённые файлы в выводе отсутствуют.
- `pytest` — `tests/test_fbs_kiz.py -k 'decision_mapping_covers_safe_sync_states or prefer_active_row_over_newer_rejected_row'` PASS, 7 passed; полный файл ранее остановился на одном найденном регрессе, который исправлен и повторно подтверждён целевым тестом.
- `back_guard.py` — FAIL: `scripts/ci/back_guard.py` отсутствует в рабочей копии.
- `check_migrations.py` — FAIL: `scripts/ci/check_migrations.py` отсутствует в рабочей копии.
- Миграции — нет.
- Commit — не создан: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/index.lock` (`Operation not permitted`), поэтому проверенного SHA нет.

## Не реализовано

- Полный backend-прогон `ruff check .` не выполнен; `mypy .` завершился с 17 ранее существующими ошибками в несвязанных файлах. Полный файл `test_fbs_kiz.py` ранее дошёл до 51 теста и выявил регресс исторической строки; после исправления целевой сценарий проходит.
- UI, API-роуты и миграции не входят в этот атомарный кусок.
- Изменения остаются в рабочей копии незакоммиченными до устранения ограничения прав Git.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

# Фича 4

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

# Фича 5

# DEV · 01-wb-marking · backend-dev · feature 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_client.py` — удалено устаревшее одиночное GET-чтение `fetch_marketplace_order_meta`; batch POST и существующий PUT-сценарий не изменялись.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py` и `test_wildberries_client.py` — релевантный набор прошёл: 26 тестов.
- Статический поиск по backend не находит определений или вызовов `fetch_marketplace_order_meta`.

## Гейты

- `ruff check .` — FAIL из-за 80 ранее существующих ошибок в несвязанных файлах backend; изменённый файл не присутствует в ошибках.
- `mypy .` — FAIL из-за 21 ранее существующей ошибки в 6 несвязанных файлах; изменённый файл не присутствует в ошибках.
- `pytest` — полный запуск начат (827 тестов), но не получил финальный статус в доступном окне; релевантный набор — PASS, 26 passed.
- `back_guard.py` — недоступен: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` отсутствует.
- `check_migrations.py` — недоступен: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` отсутствует; миграций нет.
- `git diff --check` — PASS.

## Не реализовано

- Остальные фичи карточки не затрагивались; реализован только пункт 5.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.
