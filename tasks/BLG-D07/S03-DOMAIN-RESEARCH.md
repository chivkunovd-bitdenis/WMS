# BLG-D07 — S03 DOMAIN_RESEARCH

## Паспорт

- Задача: `BLG-D07` — повторная сверка статусов заказов WB.
- Стадия и роль: `S03 DOMAIN_RESEARCH`, `pipeline-ba`.
- Тип исследования: узкий contract research существующей интеграции FBS, без нового домена.
- Дата проверки: `2026-08-21`, Europe/Moscow.
- Внешние Marketplace-вызовы: не выполнялись. Изучены только публичные официальные страницы WB.
- Машинная матрица: `tasks/BLG-D07/S03-capability-matrix.json`.
- Предлагаемый verdict: `RESEARCH_READY`.

## Короткий вывод

WB предоставляет pull-контракт для актуализации статусов FBS: `POST /api/v3/orders/status` с массивом
`orders` от 1 до 1000 ID. Ответ содержит независимые поля `supplierStatus` и `wbStatus`; первое
обычно меняется действиями продавца, но текущий cross-border enum содержит исключение
`cancel_carrier`, изменяемое перевозчиком; второе меняется системой WB. Публичная документация не
описывает webhook для этого контракта, поэтому повторная сверка должна опираться на polling и быть
готовой к расширению списка статусов.

В текущем WMS периодический worker уже существует, но это не закрывает бизнес-проблему карточки:
локальный статус `sorted` исключается из последующих сверок, хотя официальная документация песочницы
описывает переходы после `sorted` в `ready_for_pickup`, `sold`, `canceled_by_client` и `defect`. S03
эти сценарии не исполнял и не считает их proof. Кроме того,
status-path не фиксирует успешное время сверки заказа, не имеет общего per-seller rate budget и при
ошибке batch распадается на одиночные запросы.

Между датированными официальными представлениями обнаружен version skew. Индексированный снимок
английской FBS OpenAPI, доступный при S04, формулирует множитель как **`409 x10`**. Текущая видимая
страница по тому же canonical URL на `2026-08-21T06:52:00+03:00` уже говорит, что **каждый ответ
класса `4XX` учитывается как 10 запросов**. Текущий контракт шире и безопаснее для расчёта бюджета;
`409 x10` остаётся точным правилом прежнего снимка, но не переносится как доказательство того, что
остальные `4XX` бесплатны в текущей версии.

## Источники и provenance

| ID | Источник | Проверено | Уровень | Что подтверждает |
|---|---|---:|---|---|
| SRC-01 | https://dev.wildberries.ru/en/docs/openapi/orders-fbs, section `Get Assembly Orders Statuses /api/v3/orders/status` | 2026-08-21 06:52 MSK | `official/live-visible` | Текущий OpenAPI: schema, полный enum, carrier statuses, `postponed_delivery`, `4XX x10`, responses |
| SRC-01-OLD | тот же официальный URL, индексированный snapshot, crawled 5 months before 2026-08-21 | 2026-08-21 | `official/indexed-snapshot` | Предыдущая формулировка `409 x10`, урезанный enum без carrier-cancel; источник version skew |
| SRC-02 | https://dev.wildberries.ru/knowledge-base/articles/019d49a4-0771-7571-aea9-11d5b597f34c/zakazy-fbs | 2026-08-21 | `official` | Бизнес-инструкция: текущий статус получают отдельным status endpoint, до 1000 ID |
| SRC-03 | https://dev.wildberries.ru/en/docs/openapi-other/sandbox-environment#tag/Marketplace-FBS, section `Status Model for FBS` | 2026-08-21 06:52 MSK | `official/documented-not-executed` | Описанные тестовые переходы FBS; не execution proof |
| SRC-04 | `backend/app/services/wb_marketplace_orders_service.py` и связанные файлы | 2026-08-21 | `observed` | Фактическая локальная выборка, mapping, batch fallback и ограничения worker |

У WB API нет номера версии страницы и `Last-Modified` для этого раздела. Воспроизведение SRC-01:
открыть canonical URL без авторизации, найти heading `Get Assembly Orders Statuses`, затем сверить
таблицы `Possible values of supplierStatus`, `Possible values for this field`, `Request limit` и
`Responses`. Терминальный `curl` на момент проверки получал публичный WAF-ответ `498`, поэтому
датированный live-visible claim основан на отрисованном официальном DOM, а не на Marketplace API.
Расхождение с SRC-01-OLD запрещает считать любой enum вечным: WMS сохраняет raw-значение и безопасно
обрабатывает неизвестные значения.

## Официальный внешний контракт

### Endpoint и авторизация

- Метод: `POST https://marketplace-api.wildberries.ru/api/v3/orders/status`.
- Песочница: `POST https://marketplace-api-sandbox.wildberries.ru/api/v3/orders/status`.
- Авторизация: токен категории `Маркетплейс`, header `Authorization` (`HeaderApiKey`).
- Request body:

```json
{
  "orders": [5632423]
}
```

- `orders`: обязательный массив `int64`, от 1 до 1000 элементов. Текущая видимая schema не обещает
  уникальность request ID, поэтому caller обеспечивает её сам как локальный инвариант.
- Response `200`: объект с массивом `orders`; каждая строка содержит `id`, `supplierStatus`,
  `wbStatus`.
- Status endpoint не использует pagination token. Если ID больше 1000, caller обязан разбить их на
  батчи и сохранить соответствие каждого ответа исходному ID.

### `supplierStatus`

| Значение | Смысл WB | Инициатор |
|---|---|---|
| `new` | Новое сборочное задание | создание заказа |
| `confirm` | На сборке | продавец добавил задание к поставке |
| `complete` | В доставке | продавец передал поставку в доставку |
| `cancel` | Отменено продавцом | продавец отменил задание |
| `cancel_carrier` | Отменено перевозчиком, только cross-border | перевозчик |

### `wbStatus`

| Значение | Смысл WB | Класс для будущего контракта WMS |
|---|---|---|
| `waiting` | Задание в работе | нетерминальный |
| `sorted` | WB отсортировал/принял задание | нетерминальный |
| `ready_for_pickup` | Заказ прибыл в ПВЗ | нетерминальный |
| `sold` | Покупатель получил заказ | кандидат в терминальный, решение Product |
| `canceled` | Задание отменено | кандидат в терминальный, решение Product |
| `canceled_by_client` | Покупатель отказался при получении | кандидат в терминальный, решение Product |
| `declined_by_client` | Покупатель отменил в первый час до сборки | кандидат в терминальный, решение Product |
| `defect` | Отмена из-за брака | кандидат в терминальный, решение Product |
| `postponed_delivery` | Курьерская доставка отложена | нетерминальный |
| `accepted_by_carrier` | Передано перевозчику в стране продавца | нетерминальный cross-border |
| `sent_to_carrier` | Отправлено на склад перевозчика | нетерминальный cross-border |
| `canceled_by_carrier` | Отменено перевозчиком | кандидат в терминальный cross-border, решение Product |

`cancel_carrier` и `canceled_by_carrier` подтверждены текущим видимым SRC-01; их отсутствие в
SRC-01-OLD является version skew, а не основанием выдумывать их семантику. `sorted` нельзя считать
конечным: SRC-03 документирует дальнейшие переходы в `ready_for_pickup`, `sold`,
`canceled_by_client` и `defect`. Неизвестный статус должен сохраняться в raw-поле и поднимать
наблюдаемое событие, но не запускать необратимое локальное действие.

### Лимиты и ошибки

- Общий лимит на один аккаунт продавца для FBS orders/supplies/passes/auto-return: 300 запросов в
  минуту, минимальный интервал 200 мс, burst 20.
- Датированный rate-rule имеет две версии: SRC-01-OLD — именно `409 x10`; текущий SRC-01 — любой
  `4XX x10`. Для расчёта текущего seller budget применяется более новый и более широкий SRC-01.
- Песочница: максимум один запрос в секунду суммарно для всех методов Marketplace.
- Текущий SRC-01 для status endpoint перечисляет `200`, `400`, `401`, `402`, `403`, `429`.
  `404` для этого endpoint в текущей таблице не перечислен; он остаётся malformed/unexpected response
  case локального эмулятора, а не документированным ответом endpoint.
- `400`: ошибка запроса; автоматический retry тем же payload запрещён.
- `401`/`403`: ошибка доступа; остановить seller lane до исправления доступа, не крутить retry.
- `402`: требуется платёж; остановить seller lane и показать отдельную операционную причину.
- `429`: исчерпан лимит; отложить повтор, учитывать общий бюджет продавца. Наличие и семантика
  `Retry-After` в документации status endpoint не обещаны.
- Сетевые ошибки, timeout, `5XX`, невалидный JSON и отсутствующий ID в `200` официально не
  специфицированы как partial success. Они считаются неуспешной сверкой затронутых ID, а не
  подтверждением старого состояния.

## Контракт безопасной повторной сверки для следующих стадий

Это research constraints, а не утверждённый Product/Architecture design.

1. Worker обрабатывает каждый tenant/seller отдельно и никогда не смешивает ID разных продавцов.
2. Для WB вызова используются только заказы, не признанные Product действительно терминальными.
   `sorted`, `ready_for_pickup`, `accepted_by_carrier` и `sent_to_carrier` должны оставаться в
   повторной сверке.
3. Очередь должна быть справедливой: сначала самые давно успешно сверенные, без постоянного лимита,
   из-за которого старый заказ никогда не дойдёт до WB.
4. Один успешный ответ меняет только заказ с совпавшим `id`. Пропущенный, дублированный или
   неизвестный ID изолируется и не считается успехом всего батча.
5. `last_wb_sync_at` заказа обновляется только после валидной строки ответа для этого ID. Время
   попытки, время успешной сверки и время успешного полного seller-cycle — разные факты.
6. Raw `supplierStatus` и `wbStatus` сохраняются независимо. Локальный business status выводится
   отдельным idempotent mapping, чтобы повтор одного и того же ответа не повторял снятие резерва или
   другие side effects.
7. Retry допускается для transport/timeout/`5XX` с exponential backoff и jitter; для `429` — только
   после паузы rate limiter. `400`/`401`/`402`/`403` не повторяются вслепую.
8. Rate budget общий для FBS методов одного seller account, а не локальный только для этого worker.
   Batch-to-single fallback должен иметь предел и circuit breaker, иначе один плохой батч создаст
   до 1000 запросов и ускорит блокировку.
9. Сбой одного продавца не останавливает других. Повторный запуск после падения безопасен и начинает
   со stale-заказов, не объявляя незавершённый cycle успешным.
10. Публичный API не обещает webhook в исследованной области. Если S04 найдёт официальный webhook,
    polling остаётся reconciliation safety net, а не единственным источником события.

## Документированные, но не исполненные sandbox scenarios

Статус всех строк ниже: `documented_not_executed`. Они являются test design из SRC-03, не sandbox
proof и не local-emulator proof. В рамках S03 не использовался токен и не выполнялся ни один вызов.

| Case | Начало | Действие, описанное SRC-03 | Ожидаемая пара | Evidence state |
|---|---|---|---|---|
| WB-FBS-STATUS-01 | нет заказа | создать test FBS order | `waiting/new` | `documented_not_executed` |
| WB-FBS-STATUS-02 | `waiting/new` | buyer decline в первый час | `declined_by_client/new` | `documented_not_executed` |
| WB-FBS-STATUS-03 | `waiting/new` | добавить к поставке | `waiting/confirm` | `documented_not_executed` |
| WB-FBS-STATUS-04 | до delivery | отменить продавцом | `canceled/cancel` | `documented_not_executed` |
| WB-FBS-STATUS-05 | `waiting/confirm` | передать поставку в delivery | `waiting/complete` | `documented_not_executed` |
| WB-FBS-STATUS-06 | `waiting/complete` | закрыть поставку | `sorted/complete` | `documented_not_executed` |
| WB-FBS-STATUS-07 | `sorted/complete` | доставить в ПВЗ | `ready_for_pickup/complete` | `documented_not_executed` |
| WB-FBS-STATUS-08 | `ready_for_pickup/complete` | покупатель получил | `sold/complete` | `documented_not_executed` |
| WB-FBS-STATUS-09 | `ready_for_pickup/complete` | покупатель отказался | `canceled_by_client/complete` | `documented_not_executed` |
| WB-FBS-STATUS-10 | `complete` | отмена из-за брака | `defect/complete` | `documented_not_executed` |

`postponed_delivery`, `accepted_by_carrier`, `sent_to_carrier`, `cancel_carrier` и
`canceled_by_carrier` перечислены текущим SRC-01, но отсутствуют в SRC-03 status model. Их обработка
требует local-emulator cases в S15; это проверит безопасное поведение WMS, но не докажет фактический
переход WB.

## Явная передача local-emulator coverage в S15

Все строки обязательны для case factory S15 и должны получить runnable binding без live WB calls.

| S15 case | Эмулированный ответ/событие | Обязательный оракул |
|---|---|---|
| `D07-EMU-200-FULL` | полный `200`, все запрошенные ID по одному разу | raw-поля и per-order success обновлены только совпавшим ID; повтор идемпотентен |
| `D07-EMU-200-PARTIAL` | `200` без одного/нескольких ID | пропущенным ID success time не ставится, они остаются stale/retryable |
| `D07-EMU-200-DUPLICATE` | один ID возвращён дважды | весь неоднозначный ID изолирован как invalid response, last-row-wins запрещён |
| `D07-EMU-200-FOREIGN-ID` | ответ содержит незапрошенный ID | чужой ID не меняет данные; tenant/seller isolation не нарушена |
| `D07-EMU-UNKNOWN-STATUS` | неизвестный `supplierStatus` или `wbStatus` | raw сохранён, сигнал поднят, необратимый side effect не выполнен |
| `D07-EMU-LATE-STATUS` | `sorted -> ready_for_pickup -> sold`, затем late cancel/defect | polling после `sorted` продолжается; terminal/reopen policy соответствует S11 |
| `D07-EMU-CARRIER` | все пять значений, отсутствующие в SRC-03 | `postponed_delivery` не terminal; остальные mapping/side effects только по S11 |
| `D07-EMU-400` | `400` | payload не повторяется вслепую; ошибка наблюдаема |
| `D07-EMU-401-403` | `401`, `403` | seller lane остановлен, другие seller lanes продолжают работу |
| `D07-EMU-402` | `402` | отдельная operational reason, без blind retry |
| `D07-EMU-404-UNEXPECTED` | неожиданный `404` | не трактуется как документированный success/terminal; bounded policy и сигнал |
| `D07-EMU-409-X10` | `409` | расход rate budget увеличен ровно на 10; fallback по ID не запускается |
| `D07-EMU-4XX-X10-CURRENT` | по одному `400/401/402/403/404/409/429` | в текущем режиме каждый ответ списывает 10 единиц общего seller budget |
| `D07-EMU-429` | `429` | общий seller budget приостанавливает lane; `Retry-After` не предполагается без header |
| `D07-EMU-TIMEOUT-5XX` | timeout/network/`5XX` | bounded exponential retry с jitter; success time не обновлён |
| `D07-EMU-MALFORMED` | invalid JSON/schema/type | batch не считается успешным, rows не применяются |
| `D07-EMU-FALLBACK-CAP` | batch error на 1000 ID | single-request amplification ограничен budget/circuit breaker |
| `D07-EMU-RESTART-REPLAY` | crash между apply rows/cycle marker и повтор | повтор идемпотентен; незавершённый seller cycle не объявлен successful |
| `D07-EMU-STARVATION` | объём больше cycle cap | freshness ordering/cursor гарантирует, что хвост будет выбран |

## Наблюдаемый GAP текущего WMS

| Наблюдение | Evidence | Риск для BLG-D07 |
|---|---|---|
| Celery Beat уже запускает status worker, default interval 600 секунд | `backend/app/celery_app.py`, `backend/app/core/settings.py` | Наличие расписания само по себе не доказывает повторную актуализацию |
| Выборка исключает локальный `sorted` | `STATUSES_EXCLUDED_FROM_WB_SYNC` | После приёмки WB заказ перестаёт видеть `sold`, поздний отказ или defect |
| Максимум выборки 500 x 20, затем следующий cycle снова начинается со старейших | `SYNC_STATUS_BATCH_SIZE`, `MAX_SYNC_STATUS_BATCHES` | При объёме выше 10 000 хвост может голодать без cursor/freshness ordering |
| Клиент режет status request по 100, хотя текущий WB contract допускает 1000 | `MAX_MARKETPLACE_FBS_BATCH` | Больше запросов и выше расход общего лимита; консервативный размер допустим только осознанно |
| Batch error вызывает fallback по одному ID без backoff/rate limiter | `_fetch_status_rows_resilient` | Request amplification, особенно при `429`/auth error; current SRC-01 считает `4XX x10` |
| `FbsOrder.last_wb_sync_at` есть, но status-path его не обновляет | model и status sync service | Нельзя честно показать время последней успешной сверки заказа |
| Новые live-статусы перевозчика не входят в текущую mapping-модель | live SRC-01 и local mapping | Cross-border заказ может зависнуть в старом local status |
| Raw status сохраняется, но неизвестный статус не имеет отдельной observability-сигнализации | `_apply_wb_status_to_order` | Contract drift остаётся незаметным оператору и мониторингу |

## Вопросы следующих стадий

Не блокируют S03, потому что внешний контракт собран; они не должны решаться исследователем.

1. S11 Product: какие WB-состояния действительно терминальны для WMS и какие side effects нужны для
   `canceled_by_carrier`.
2. S11 Product: какой freshness SLA видит оператор и где показывается last success для заказа и
   продавца.
3. S13 Architecture: размер батча 100 или 1000, общая per-seller rate coordination, cursor и
   starvation-proof scheduling.
4. S13 Architecture: retry budget, circuit breaker, хранение attempt/success/error и recovery после
   worker restart.
5. S04 Research Critic: независимо воспроизвести текущий live-visible SRC-01 и рассудить version skew
   `SRC-01-OLD: 409 x10` против `SRC-01: 4XX x10`; проверить carrier statuses и отсутствие webhook.

## Capability closure

Применимые строки endpoint, schema, status machine, batch, rate limit, error behavior, tenant/seller,
sandbox и объёмный режим закрыты исследовательским контрактом и явной передачей runnable cases в
S15. Version skew не замолчан и передан S04 как независимая проверка текущего oracle. Pagination для
status endpoint неприменима; каталог, остатки, маркировка, печать, поставки, возвраты, competitor
screens и пользовательские боли вне узкой области изменения и помечены `not_applicable` в машинной
матрице. Необработанных применимых research rows: `0`; исполненных sandbox/emulator proofs: `0`.
