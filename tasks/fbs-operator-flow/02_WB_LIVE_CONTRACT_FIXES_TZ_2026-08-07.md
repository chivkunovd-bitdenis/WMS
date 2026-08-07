# ТЗ: подготовка FBS контура к real WB API

Дата: 2026-08-07.
Ветка для текущей проверки: `qa/fbs-move-wb-transfer-button-20260807`.
Цель: убрать расхождения между текущим FBS flow и официальным WB Orders FBS API так,
чтобы после выключения моков реальный seller мог пройти путь: заказы WB -> поставка ->
подбор -> упаковка/ЧЗ/QR заказа -> короба -> передача в WB -> QR поставки.

## 0. Жесткие ограничения

1. Фронт не переделывать заново.
2. Не добавлять новые чипы, статусы, сноски, технические таблицы или новые этапы.
3. Ручной ввод КИЗ не возвращать.
4. Закрытие/переоткрытие коробов не добавлять.
5. Для ПВЗ нужны WB cargo-place QR. Для склад/СЦ QR коробов не нужен.
6. Кнопка `Передать в WB` остается на этапе коробов, под блоком коробов.
7. Отдельный этап сдачи и отдельная кнопка проверки не нужны.
8. Docker не считать тестовым контуром. Проверка готовности — Railway + real/mock-флаги явно указаны.
9. Моки не являются доказательством live WB. Перед live проверкой должны быть выключены:
   `e2e_mock_wb_marketplace_orders`,
   `e2e_mock_wb_marketplace_supplies`,
   `e2e_mock_wb_marketplace_marking`,
   `e2e_mock_wb_marketplace_warehouses`.
10. Не менять секреты, ключи и Railway variables без отдельного явного разрешения пользователя.

## 1. Источники истины

### Документы продукта

- `tasks/fbs-operator-flow/00_ЭТАЛОН_FBS_UI_2026-08-06_УТВЕРЖДЁН.md`
- `tasks/fbs-operator-flow/00_ЭТАЛОН_FBS_UI_2026-08-06_МАКЕТ.html`
- `tasks/fbs-operator-flow/01_HANDOFF_ПРОДОЛЖЕНИЕ_2026-08-06.md`

### Официальный WB API

Основной источник: Wildberries Orders FBS OpenAPI.

- Страница: `https://dev.wildberries.ru/openapi/orders-fbs`
- YAML: `https://dev.wildberries.ru/api/swagger/yaml/ru/03-orders-fbs.yaml`

Если `dev.wildberries.ru` не открывается из среды агента, можно использовать зеркало
только как способ чтения того же YAML, но в отчете писать, что source в зеркале —
официальный YAML WB.

## 2. Текущий блокер live WB

На Railway WMS сейчас выявлено:

```text
app_env = staging
wildberries_marketplace_api_base = http://fbs-test-adapter.invalid
e2e_mock_wb_marketplace_orders = true
e2e_mock_wb_marketplace_supplies = true
e2e_mock_wb_marketplace_marking = true
e2e_mock_wb_marketplace_warehouses = true
```

Это значит: текущий стенд не ходит в WB, а успешные QR/ЧЗ/короба доказывают только
работу mock-ответов. Включать real WB до выполнения P0 запрещено.

## 3. P0. Backend: привести WB client к официальному контракту

Ответственный: Composer.
Ревью и приемка: Codex.

Файлы-кандидаты:

- `backend/app/services/wildberries_client.py`
- `backend/app/services/wildberries_fbs_client.py`
- `backend/app/services/wb_marketplace_orders_service.py`
- `backend/app/services/fbs_print_asset_service.py`
- `backend/app/services/fbs_order_tape_print_service.py`
- `backend/app/services/fbs_marking_service.py`
- `backend/tests/test_wildberries_fbs_client_contract.py` или близкий новый файл

### P0.1. Добавить contract tests по каждому WB endpoint

Нужны unit-тесты без реального WB, через mock transport/httpx, которые проверяют
точный method/path/query/body и парсинг ответа.

Проверить endpoints:

1. `GET /api/v3/orders/new`
   - Вход: без обязательных query-параметров.
   - Выход: `orders[]`.
   - Код: `fetch_marketplace_orders_new`.

2. `GET /api/v3/orders`
   - Вход WB: `limit` и `next` обязательны, первый запрос `next=0`.
   - Опционально: `dateFrom`, `dateTo`, если код их использует.
   - Выход: `orders[]`, `next`.
   - Код: `fetch_marketplace_orders_page`.
   - Acceptance: первый page-запрос никогда не уходит без `next=0`.

3. `POST /api/v3/orders/status`
   - Body: `{"orders": [wbOrderId...]}`.
   - Выход: `orders[].id`, `supplierStatus`, `wbStatus`.
   - Код: `fetch_marketplace_orders_status`.

4. `POST /api/v3/supplies`
   - Body: `{"name": "..."}`.
   - Success: `201`, response `{"id": "WB-GI-..."}`.
   - Код: `create_marketplace_supply`.

5. `PATCH /api/marketplace/v3/supplies/{supplyId}/orders`
   - Body: `{"orders": [wbOrderId...]}`.
   - Batch limit: максимум 100 заказов.
   - Success: `204`.
   - Код: `add_orders_to_marketplace_supply`.

6. `GET /api/marketplace/v3/supplies/{supplyId}/order-ids`
   - Выход: `orderIds[]`.
   - Код: reconcile состава поставки.

7. `GET /api/v3/supplies/{supplyId}`
   - Выход: details поставки, включая `done`/состав, если WB отдает.
   - Код: reconcile deliver.

8. `POST /api/v3/orders/stickers?type=png&width=58&height=40`
   - Body: `{"orders": [wbOrderId...]}`.
   - Batch limit: максимум 100.
   - Выход: `stickers[].orderId`, `partA`, `partB`, `barcode`, `file`.
   - Код: `fetch_marketplace_order_stickers`.

9. `POST /api/v3/supplies/{supplyId}/trbx`
   - Body: `{"amount": count}`.
   - Success: `201`.
   - Выход: `trbxIds[]`.
   - Код: `create_marketplace_supply_trbx`.

10. `GET /api/v3/supplies/{supplyId}/trbx`
    - Выход: `trbxes[].id`.
    - Код: `fetch_marketplace_supply_trbx_list`.

11. `DELETE /api/v3/supplies/{supplyId}/trbx`
    - Body: `{"trbxIds": ["WB-TRBX-..."]}`.
    - Success: `204`.
    - Код: `delete_marketplace_supply_trbx`.

12. `POST /api/v3/supplies/{supplyId}/trbx/stickers?type=png`
    - Body: `{"trbxIds": ["WB-TRBX-..."]}`.
    - Выход по доке: `stickers[].barcode`, `stickers[].file`.
    - В официальной схеме нет гарантированного `trbxId` в ответе.
    - Код: `fetch_marketplace_trbx_stickers`.

13. `PATCH /api/v3/supplies/{supplyId}/deliver`
    - Body: пустое.
    - Success: `204`.
    - `409 MetaValidationFail` должен сохранять контекст WB, а не превращаться в
      безликий `502`.

14. `GET /api/v3/supplies/{supplyId}/barcode?type=png`
    - Условие WB: QR поставки можно получить только после deliver.
    - Выход: image response или JSON/base64, если WB так отдаст.
    - Код: `fetch_marketplace_supply_barcode`.

15. `PUT /api/v3/orders/{orderId}/meta/sgtin`
    - Body: `{"sgtins": [value]}`.
    - Success: `204`.

16. `PUT /api/v3/orders/{orderId}/meta/uin`
    - Body: `{"uin": value}`.
    - Success: `204`.

17. `PUT /api/v3/orders/{orderId}/meta/imei`
    - Body: `{"imei": value}`.
    - Success: `204`.

18. `PUT /api/v3/orders/{orderId}/meta/gtin`
    - Body: `{"gtin": value}`.
    - Success: `204`.

19. `POST /api/marketplace/v3/orders/meta`
    - Body: `{"orders": [wbOrderId...]}`.
    - Выход: `orders[].id`, `orders[].metaDetails[]`.
    - Это официальный метод получения статуса/деталей metadata.

### P0.2. Исправить `GET /api/v3/orders`

Проблема: текущий первый page-запрос может уйти без `next`.

Требование:

- В `fetch_marketplace_orders_page` всегда отправлять `next`.
- Первый вызов должен быть `next=0`.
- `sync_seller_orders` должен начинать с `next_token = 0`, а не `None`.
- Если WB вернул `next=0` или пустые `orders`, цикл завершается без дублей.

Acceptance:

- Тест доказывает первый request query: `limit=100&next=0`.
- Тест доказывает вторую страницу с `next` из ответа.
- Тест доказывает отсутствие бесконечного цикла.

### P0.3. Исправить payload для metadata

Проблема: сейчас helper строит plural array для всех видов. По WB:

- `sgtin` -> `{"sgtins": [value]}`
- `uin` -> `{"uin": value}`
- `imei` -> `{"imei": value}`
- `gtin` -> `{"gtin": value}`

Требование:

- Исправить `build_marketplace_order_meta_put_body`.
- Добавить параметризованный тест по всем четырем видам.
- Невалидный kind должен падать локально до HTTP-запроса.

Acceptance:

- Контрактные тесты видят ровно те JSON-body, которые описаны выше.

### P0.4. Убрать зависимость от неподтвержденного `GET /api/v3/orders/{orderId}/meta`

Проблема: в официальной схеме подтвержден `POST /api/marketplace/v3/orders/meta`
для получения metadata. Текущий код также использует `GET /api/v3/orders/{orderId}/meta`,
который в проверенной схеме не подтвержден.

Требование:

- Для live path статусы маркировки получать через официальный
  `POST /api/marketplace/v3/orders/meta`.
- `sync_order_marking_statuses` не должен зависеть от одиночного `GET /meta`.
- Парсер должен принимать `metaDetails` и обновлять:
  - `check_status`
  - `meta_status`
  - `reason`
  - `metadata_delivery_allowed`
  - `metadata_last_checked_at`

Acceptance:

- Тест: после ответа `decision=filled` required `sgtin` становится delivery-allowed.
- Тест: после `decision=pending` delivery не разрешен.
- Тест: после `decision=required` или `sgtinInvalidFormat` delivery не разрешен, причина сохранена.

## 4. P0. Backend: ЧЗ должен реально отправляться в WB при печати

Ответственный: Composer.
Ревью: Codex.

Файлы-кандидаты:

- `backend/app/services/fbs_order_tape_print_service.py`
- `backend/app/services/fbs_marking_service.py`
- `backend/tests/test_fbs_order_tape_print_service.py` или существующие FBS marking tests

### P0.5. Исправить определение required ЧЗ

Проблема: frontend считает заказ ЧЗ-заказом, если `product.requires_honest_sign`
или `order.metadata.required` содержит `sgtin`. Backend в `fbs_order_tape_print_service`
сейчас ориентируется в основном на `product.requires_honest_sign`.

Требование:

- Backend должен считать, что заказ требует SGTIN, если:
  - `order.required_meta_json` содержит `sgtin`, или
  - товар требует ЧЗ локально.
- Это должно работать даже если локальная карточка товара еще не помечена
  `requires_honest_sign`, но WB прислал `requiredMeta=["sgtin"]`.

Acceptance:

- Тест: `required_meta_json=["sgtin"]`, `product.requires_honest_sign=false` ->
  печать требует код и не проходит как обычный не-ЧЗ заказ.

### P0.6. Отправлять SGTIN в WB из печатного FBS flow

Проблема: кнопка `Печать ЧЗ и ШК` в новом FBS workspace идет в
`POST /operations/fbs-supplies/{supply_id}/order-print-tape`.
Сейчас backend печатает/резервирует код локально, но сам вызов
`PUT /api/v3/orders/{orderId}/meta/sgtin` не гарантирован в этом flow.

Требование:

- При успешном выборе/резервации SGTIN для FBS-заказа backend обязан вызвать
  `put_marketplace_order_meta(... kind="sgtin", value=cis_code)`.
- После `204` от WB локальный `FbsOrderMarking` должен быть в состоянии,
  которое ясно означает: код отправлен в WB, ожидаем/знаем результат проверки.
- Затем статус подтягивается через официальный `POST /api/marketplace/v3/orders/meta`.
- Если WB вернул `409 MetaValidationFail`, оператор должен получить ошибку по заказу,
  а локальная модель не должна показывать, что заказ готов к передаче.
- Если WB transport timeout, результат должен быть retryable; нельзя делать вид,
  что маркировка принята.

Важно:

- Не добавлять UI ручного ввода КИЗ.
- Не добавлять новую кнопку.
- Текущая кнопка печати должна автоматически делать все, что нужно.

Acceptance:

- Тест: клик/route печати FBS order tape для SGTIN-заказа вызывает WB
  `PUT /api/v3/orders/{orderId}/meta/sgtin`.
- Тест: body ровно `{"sgtins": [cis_code]}`.
- Тест: при ошибке WB заказ не становится `metadata_delivery_allowed=true`.
- Тест: повторная печать того же заказа не создает дубль `FbsOrderMarking`.

## 5. P0. Backend: PVZ QR коробов

Ответственный: Composer.
Ревью: Codex.

Файлы-кандидаты:

- `backend/app/services/wildberries_client.py`
- `backend/app/services/fbs_print_asset_service.py`
- `backend/app/services/fbs_shipment_pvz_service.py`
- `backend/tests/test_fbs_print_assets.py`
- `backend/tests/test_fbs_shipment_pvz.py`

### P0.7. Не полагаться на `trbxId` в ответе `trbx/stickers`

Проблема: WB-дока для `POST /api/v3/supplies/{supplyId}/trbx/stickers` описывает
ответ `stickers[].barcode` и `stickers[].file`, но не гарантирует `trbxId`.
Текущий mock возвращает `trbxId`, поэтому мок мог скрыть live-баг.

Требование:

- Для надежного сопоставления запрашивать QR по одному `trbxId` за запрос
  или реализовать другой официальный способ, не требующий недокументированного
  поля ответа.
- Если в одном запросе передан один `trbxId`, первый sticker ответа закрепляется
  за этим `FbsTrbx`.
- Не использовать внутренний `FBS-...`/`WHB-...` как замену WB cargo QR.

Acceptance:

- Тест: WB ответ без `trbxId`, только `barcode` и `file`, успешно сохраняет QR
  для нужного короба.
- Тест: два PVZ-короба получают два разных asset, без зависимости от mock-only `trbxId`.
- Тест: для склад/СЦ кнопка/получение QR коробов не вызывают WB `trbx/stickers`.

## 6. P0. Backend/API: deliver должен быть live-safe

Ответственный: Composer.
Ревью: Codex.

Файлы-кандидаты:

- `backend/app/services/fbs_shipment_service.py`
- `backend/app/api/fbs_supplies.py`
- `backend/tests/test_fbs_shipment_delivery.py`
- `backend/tests/test_fbs_shipment_warehouse_sc.py`
- `backend/tests/test_fbs_shipment_pvz.py`

### P0.8. Проверить кнопку `Передать в WB` до реального WB deliver

Требование:

- Frontend не добавляет отдельную кнопку проверки.
- Route `POST /operations/fbs-supplies/{supply_id}/deliver` сам:
  - синхронизирует статусы заказов;
  - синхронизирует metadata через официальный batch endpoint;
  - вызывает WB `PATCH /api/v3/supplies/{supplyId}/deliver`;
  - на SC/warehouse после успешного deliver получает QR поставки через
    `GET /api/v3/supplies/{supplyId}/barcode?type=png`;
  - на PVZ не требует QR поставки, но требует готовые cargo-place QR.
- Ошибки WB показывать аккуратно через существующий error envelope.

Acceptance:

- Тест: успешный SC deliver -> один WB deliver call, затем один supply barcode call.
- Тест: повтор после QR failure не вызывает второй WB deliver, только добирает QR.
- Тест: `MetaValidationFail` возвращает 409 с понятным context по metadata.
- Тест: PVZ без готовых cargo QR не вызывает WB deliver.
- Тест: PVZ с готовыми cargo QR вызывает WB deliver без запроса supply barcode.

## 7. P0. Autopoll: реальные заказы должны появляться сами

Ответственный: Composer/infra.
Ревью: Codex.

Файлы-кандидаты:

- `backend/app/celery_app.py`
- `backend/app/tasks/background_jobs.py`
- `backend/app/services/fbs_autopoll_service.py`
- Railway service configuration/documentation

Проблема: код Celery beat есть, но на Railway сейчас видны только `WMS`, `web`,
`Postgres`. Отдельный worker/beat не подтвержден.

Требование:

- Поднять отдельный Railway worker/beat или другой явный production-safe scheduler.
- Нужен broker. Если используется Celery, должен быть настроен `CELERY_BROKER_URL`.
- Worker должен выполнять:
  - `wms.fbs_orders_autopoll`
  - `wms.fbs_order_statuses_autopoll`
- Нельзя тихо дергать stock sync, если это пишет остатки в WB без отдельного решения.
  Сейчас `poll_fbs_orders_for_seller` вызывает `sync_seller_stocks`; это нужно
  либо явно оставить как согласованный side effect, либо разделить order polling
  и stock sync.

Acceptance:

- Railway status показывает отдельный worker/scheduler или другой явно описанный процесс.
- Logs содержат реальные строки `fbs autopoll orders: starting cycle`.
- При выключенных моках и настоящем base новые FBS-заказы продавца появляются
  без ручного запуска background job.
- Тест/лог доказывает, что polling не делает неожиданный write в WB stocks,
  если это не было явно разрешено.

## 8. P0. Runtime configuration for real WB

Ответственный: Codex после отдельного разрешения пользователя на изменение Railway env.

Требование:

- `wildberries_marketplace_api_base = https://marketplace-api.wildberries.ru`
- Все `e2e_mock_wb_marketplace_* = false`
- У подключенных seller credentials есть marketplace token.
- Проверить только наличие токенов boolean-ами, не печатать и не расшифровывать ключи.

Acceptance:

- `/api/health` OK.
- Runtime settings check показывает mock=false и настоящий WB base.
- Не раскрыты токены в логах/ответах.

## 9. Frontend: только минимальные правки

Ответственный: Codex.

Файлы-кандидаты:

- `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `frontend/src/screens/v2/fbsApi.ts`
- существующие unit/e2e tests

### P0.9. Не менять макет, только довести существующие кнопки до real flow

Разрешенные действия:

- Если backend начнет возвращать более точные ошибки по WB metadata/trbx/deliver,
  аккуратно показать их через существующий `setError`.
- Если `order-print-tape` начнет возвращать order-level error для WB metadata,
  показать его в уже существующем механизме ошибок печати.
- Если QR короба/поставки готов, открыть текущий print preview.

Запрещено:

- новые чипы;
- новые статусы;
- новые подсказки/сноски;
- новый этап;
- ручной ввод КИЗ;
- дополнительные таблицы;
- технические поля WB в UI.

Acceptance:

- На упаковке остаются ровно текущие действия: `ТЗ`, `QR`, иконка печати, меню перепечатки.
- На коробах остается текущая структура: `Добавить короба`, `QR` только для PVZ,
  `Добавить товары`, меню действий, `Передать в WB` под блоком.
- Для склад/СЦ после deliver показывается `QR поставки WB` и кнопка `Печать QR поставки`.

## 10. P1. Live verification matrix

Ответственный: Codex, можно подключить отдельного агента на read-only проверку.

Запускать только после P0 и после явного решения по real-WB environment.

### Сценарии

1. Seller без новых заказов
   - Autopoll/ручной sync не падает.
   - Worklist пустой или без новых строк.

2. Новый FBS-заказ без обязательной metadata
   - Заказ пришел из WB.
   - Создание поставки прошло.
   - QR заказа получен через WB stickers.
   - Упаковка и короба прошли.
   - Deliver прошел.
   - Для склад/СЦ QR поставки получен после deliver.

3. Новый FBS-заказ с `requiredMeta=["sgtin"]`
   - Печать ЧЗ автоматически отправляет SGTIN в WB.
   - Batch metadata sync видит `pending` или `filled`.
   - Deliver до `filled` не проходит, если WB еще не разрешил.
   - После `filled` deliver проходит.

4. PVZ поставка
   - `Добавить короба` создает WB `trbx`.
   - QR каждого короба получен из WB `trbx/stickers`.
   - Распределение заказов по физическим WMS-коробам остается локальным.
   - Deliver не требует supply QR.

5. Склад/СЦ поставка
   - Короба локальные, WB cargo-place не создается.
   - QR коробов не показывается.
   - После deliver получен QR поставки.

6. WB metadata error
   - Искусственно/тестово получить `MetaValidationFail`.
   - UI показывает аккуратную ошибку.
   - Локальный статус не становится "готово".

7. Retry safety
   - Повтор create supply с тем же idempotency key не создает вторую WB поставку.
   - Повтор create cargo places не создает лишние WB trbx.
   - Повтор deliver после timeout не делает второй deliver, пока не reconciled.
   - Повтор supply QR после failure не вызывает второй deliver.

## 11. Definition of Done

Нельзя писать "готово", пока не выполнено все:

1. Все P0 code fixes сделаны.
2. Есть contract tests на каждый WB endpoint выше.
3. Backend tests зеленые по FBS/WB.
4. Frontend build зеленый.
5. Изменения закоммичены отдельным commit.
6. Ветка запушена.
7. Railway deployment собран из нужного SHA.
8. Runtime mock-флаги проверены и явно указаны.
9. Для real-WB проверки отдельно указано: какие операции были только read-only,
   а какие реально мутировали WB.
10. Если real-WB не проверялся физически, так и писать: "контракт готов, live WB
    mutation не доказана".

## 12. Короткий handoff для Composer

Сделай P0 backend fixes без изменений фронта:

1. Contract tests по WB Orders FBS endpoints из раздела 3.
2. `GET /api/v3/orders`: первый page query обязательно `next=0`.
3. Metadata payload:
   - `sgtin -> {"sgtins":[value]}`
   - `uin -> {"uin":value}`
   - `imei -> {"imei":value}`
   - `gtin -> {"gtin":value}`
4. Убери live-зависимость от неподтвержденного `GET /api/v3/orders/{orderId}/meta`;
   используй официальный `POST /api/marketplace/v3/orders/meta`.
5. В FBS order print tape при печати SGTIN-заказа отправляй SGTIN в WB.
6. Backend должен считать SGTIN обязательным, если WB прислал `requiredMeta=["sgtin"]`,
   даже если локальный product flag еще false.
7. PVZ `trbx/stickers`: не рассчитывай на `trbxId` в ответе, запрашивай QR по одному
   trbx или иначе сопоставляй без недокументированных полей.
8. Deliver tests: SC получает supply QR после deliver, PVZ требует cargo QR и не
   требует supply QR, `MetaValidationFail` возвращается оператору как 409.
9. Autopoll: отделить order polling от неожиданных WB stock writes или явно доказать,
   что side effect согласован.

Не трогай UI и не добавляй ручной ввод КИЗ.
