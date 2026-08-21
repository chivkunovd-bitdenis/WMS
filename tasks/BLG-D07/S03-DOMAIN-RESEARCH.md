# BLG-D07 — S03 DOMAIN_RESEARCH

## Паспорт

- Задача: `BLG-D07` — повторная сверка статусов заказов WB.
- Стадия и роль: `S03 DOMAIN_RESEARCH`, `pipeline-ba`.
- Тип исследования: узкий contract research существующей интеграции FBS, без нового домена.
- Дата проверки: `2026-08-21`, Europe/Moscow.
- Внешние вызовы: не выполнялись. Изучены только публичные официальные страницы WB.
- Машинная матрица: `tasks/BLG-D07/S03-capability-matrix.json`.
- Предлагаемый verdict: `RESEARCH_READY`.

## Короткий вывод

WB предоставляет pull-контракт для актуализации статусов FBS: `POST /api/v3/orders/status` с массивом
`orders` от 1 до 1000 ID. Ответ содержит независимые поля `supplierStatus` и `wbStatus`; первое
меняется действиями продавца, второе — системой WB. Публичная документация не описывает webhook для
этого контракта, поэтому повторная сверка должна опираться на polling и быть готовой к расширению
списка статусов.

В текущем WMS периодический worker уже существует, но это не закрывает бизнес-проблему карточки:
локальный статус `sorted` исключается из последующих сверок, хотя официальная песочница показывает
переходы после `sorted` в `ready_for_pickup`, `sold`, `canceled_by_client` и `defect`. Кроме того,
status-path не фиксирует успешное время сверки заказа, не имеет общего per-seller rate budget и при
ошибке batch распадается на одиночные запросы. Последнее особенно опасно, потому что WB считает каждый
ответ `4XX` как десять запросов.

## Источники и provenance

| ID | Источник | Проверено | Уровень | Что подтверждает |
|---|---|---:|---|---|
| SRC-01 | https://dev.wildberries.ru/ru/openapi/orders-fbs | 2026-08-21 | `official` | Live OpenAPI endpoint, auth, request/response, статусы, лимиты, коды ответов |
| SRC-02 | https://dev.wildberries.ru/knowledge-base/articles/019d49a4-0771-7571-aea9-11d5b597f34c/zakazy-fbs | 2026-08-21 | `official` | Бизнес-инструкция: текущий статус получают отдельным status endpoint, до 1000 ID |
| SRC-03 | https://dev.wildberries.ru/docs/openapi-other/sandbox-environment#tag/Marketplejs-FBS | 2026-08-21 | `official` | Тестовый контур и воспроизводимые переходы FBS |
| SRC-04 | `backend/app/services/wb_marketplace_orders_service.py` и связанные файлы | 2026-08-21 | `observed` | Фактическая локальная выборка, mapping, batch fallback и ограничения worker |

У WB API нет номера версии страницы. Для фиксации версии используется URL и дата живой проверки.
Поисковые снимки этой же страницы содержали более старый набор статусов, поэтому список нельзя
зашивать как исчерпывающий без сохранения raw-значения.

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

- `orders`: обязательный массив уникальных положительных `int64`, от 1 до 1000 ID.
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
| `accepted_by_carrier` | Передано перевозчику в стране продавца | нетерминальный cross-border |
| `sent_to_carrier` | Отправлено на склад перевозчика | нетерминальный cross-border |
| `canceled_by_carrier` | Отменено перевозчиком | кандидат в терминальный cross-border, решение Product |

`sorted` нельзя считать конечным: официальный sandbox показывает дальнейшие переходы в
`ready_for_pickup`, `sold`, `canceled_by_client` и `defect`. Неизвестный статус должен сохраняться в
raw-поле и поднимать наблюдаемое событие, но не запускать необратимое локальное действие.

### Лимиты и ошибки

- Общий лимит на один аккаунт продавца для FBS orders/supplies/passes/auto-return: 300 запросов в
  минуту, минимальный интервал 200 мс, burst 20.
- Любой ответ `4XX` считается как десять запросов.
- Песочница: максимум один запрос в секунду суммарно для всех методов Marketplace.
- Описанные ответы status endpoint: `200`, `400`, `401`, `402`, `403`, `429`.
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

## Официально воспроизводимые sandbox cases

Эти кейсы описаны официальной песочницей; вызовы в рамках S03 не выполнялись.

| Case | Начало | Действие sandbox | Ожидаемая пара статусов |
|---|---|---|---|
| WB-FBS-STATUS-01 | нет заказа | создать test FBS order | `waiting/new` |
| WB-FBS-STATUS-02 | `waiting/new` | buyer decline в первый час | `declined_by_client/new` |
| WB-FBS-STATUS-03 | `waiting/new` | добавить к поставке | `waiting/confirm` |
| WB-FBS-STATUS-04 | до delivery | отменить продавцом | `canceled/cancel` |
| WB-FBS-STATUS-05 | `waiting/confirm` | передать поставку в delivery | `waiting/complete` |
| WB-FBS-STATUS-06 | `waiting/complete` | закрыть поставку | `sorted/complete` |
| WB-FBS-STATUS-07 | `sorted/complete` | доставить в ПВЗ | `ready_for_pickup/complete` |
| WB-FBS-STATUS-08 | `ready_for_pickup/complete` | покупатель получил | `sold/complete` |
| WB-FBS-STATUS-09 | `ready_for_pickup/complete` | покупатель отказался | `canceled_by_client/complete` |
| WB-FBS-STATUS-10 | `complete` | отмена из-за брака | `defect/complete` |

Cross-border статусы перевозчика перечислены production OpenAPI, но официальный sandbox matrix не
даёт для них эмуляции. Они требуют emulator cases и отдельной проверки в S04/S15 без live WB calls.

## Наблюдаемый GAP текущего WMS

| Наблюдение | Evidence | Риск для BLG-D07 |
|---|---|---|
| Celery Beat уже запускает status worker, default interval 600 секунд | `backend/app/celery_app.py`, `backend/app/core/settings.py` | Наличие расписания само по себе не доказывает повторную актуализацию |
| Выборка исключает локальный `sorted` | `STATUSES_EXCLUDED_FROM_WB_SYNC` | После приёмки WB заказ перестаёт видеть `sold`, поздний отказ или defect |
| Максимум выборки 500 x 20, затем следующий cycle снова начинается со старейших | `SYNC_STATUS_BATCH_SIZE`, `MAX_SYNC_STATUS_BATCHES` | При объёме выше 10 000 хвост может голодать без cursor/freshness ordering |
| Клиент режет status request по 100, хотя текущий WB contract допускает 1000 | `MAX_MARKETPLACE_FBS_BATCH` | Больше запросов и выше расход общего лимита; консервативный размер допустим только осознанно |
| Batch error вызывает fallback по одному ID без backoff/rate limiter | `_fetch_status_rows_resilient` | Request amplification, особенно при `429`/auth error; каждый `4XX` стоит 10 |
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
5. S04 Research Critic: независимо проверить отсутствие webhook, актуальность carrier statuses и
   расхождение со старыми снимками, где встречался `postponed_delivery`.

## Capability closure

Применимые строки endpoint, schema, status machine, batch, rate limit, error behavior, tenant/seller,
sandbox и объёмный режим закрыты. Pagination для status endpoint неприменима; каталог, остатки,
маркировка, печать, поставки, возвраты, competitor screens и пользовательские боли вне узкой области
изменения и помечены `not_applicable` в машинной матрице. Необработанных применимых строк: `0`.
