# WMS-658 · совместимость старых WB-фикстур с обязательными справочниками

Дата: 07.10.2026. Это короткое доказательство корректировки только тестовых
фикстур; продуктовый код не менялся.

## Подтверждённый исходный RED

Координатор передал точный raw-лог CI shard 1:
`/Users/deniscivkunov/Projects/WMS/.agent-runs/night-20261006-01a112a8/integration/pr393-backend-shard1-c3.log`.
В нём зафиксированы три настоящих сбоя:

- `test_active_manual_job_skipped_then_terminal_job_allows_import`: старое
  `len(calls) == 1` получило три запроса — один `POST /content/v2/get/cards/list`
  и два обязательных `GET` справочника;
- `test_hourly_sync_selection_is_isolated_per_seller_and_tenant`: старое
  сравнение списка токенов карточек получило девять запросов для трёх
  селлеров, потому что к одному карточному запросу добавились оба GET;
- `test_f3_one_failing_wb_card_does_not_crash_the_rest_of_the_batch`: старая
  заглушка `flaky_upsert` не принимала новый keyword `marking_catalog`, поэтому
  ошибкой становились обе карточки вместо изоляции ошибки первой.

R7 WMS-658 прямо оправдывает эти два GET: связь предмета с надкатегорией
«Одежда» доказывается только через `/content/v2/object/all` и
`/content/v2/object/parent/all`. Исправление не увеличивает ожидания общего
числа вызовов: отдельно проверяются ровно один cards-list вызов на селлера,
оба category GET и их собственный токен. Неверные пути, query-параметры и
заимствование токена другого селлера вызывают ошибку фикстуры.

## GREEN после корректировки

Выполнен один адресный процесс без xdist и без новых зависимостей:

```sh
cd backend
WMS_TEST_DATABASE_URL=sqlite+aiosqlite:///:memory: \
WMS_TEST_DATA_DIR="$(mktemp -d /private/tmp/wms658-fixture-tests.XXXXXX)" \
PYTHONDONTWRITEBYTECODE=1 \
python3 -m pytest -n 0 -p no:cacheprovider --tb=short \
  tests/test_wb_catalog_schedule.py \
  tests/test_wms548_wb_sync_selection.py \
  tests/test_wms548_add_to_fulfillment.py
```

Результат: **20 passed, 6 warnings, 30.60s**. Предупреждения существующие,
депрекационные; пропусков и изменения продуктового кода не было.
