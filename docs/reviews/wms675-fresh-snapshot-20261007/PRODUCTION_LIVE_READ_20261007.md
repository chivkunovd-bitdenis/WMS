# WMS-675 · production live read: доказанная текущая missing delta

Этот отчёт заменяет только вывод `UNKNOWN` из предыдущего handoff: тот вывод
был честен для локального transport, где защитный флаг выключен. 07.10.2026
по Тбилиси выполнен новый ограниченный production read без изменения флага,
конфигурации, credentials или данных.

## Источник и безопасная граница

На production `sellerfocus.pro`, checkout `/opt/wms`, API-container был
запущен на SHA `8f11d912351e8de7633b4abcf74d195badaeb254`. Это факт среды
чтения, не подтверждение deploy общего кандидата. Внутри уже работающего API
использован process-scoped `HttpxOzonMarketplaceTransport`, а не локальная
фабрика, которая намеренно возвращает fake transport при
`WMS_OZON_LIVE_API=false`. Глобальная настройка не менялась.

До сети reader проверил в отдельной PostgreSQL-транзакции `READ ONLY` exact
tenant/seller/supply/warehouse, WMS-source и 31 scoped позиции, получил
seller-bound credentials только внутри `MarketplaceAccountService`, затем
выполнил rollback. Значения credentials не сохранялись и не выводились.
После этого сделаны ровно 31 запроса `POST /v3/posting/fbs/get`; по контракту
Ozon это read карточки. Не запускались sync, ship/deliver/approve, печать,
DB write, Ozon write или retry.

Sanitized allowlist ответов лежит в
`marketplace-production-read-20261007-attempt2/remote-read-sanitized.json`.
Его SHA-256: `82fe8696ac64b56461013ef9bfbaac3d0b1bd3328ed70eb745a68995b7465bab`.
В нём нет заголовков, credentials, клиентов, marking codes или raw errors.

## Внешнее доказательство

Run: `2026-10-06T20:56:24.628194+00:00` →
`2026-10-06T20:56:27.662269+00:00`. Все 31 ответа — HTTP 200, их server Date
находятся в интервале 20:56:25–20:56:27 UTC. Каждая карточка совпала с exact
WMS position по posting number, одному SKU, offer и quantity=1; related/weight
posting lists пусты.

- 13 `delivering`: 8 `posting_in_pickup_point`, 5 `posting_on_way_to_city`.
- 13 `delivered` / `posting_received`.
- 5 `cancelled` / `posting_canceled`; две карточки имеют
  `cancelled_after_ship=true`, но это не превращает отмену в новую сдачу.

Принятый `ozon_proves_handoff` WMS-662 допускает `delivering`,
`driver_pickup` или `delivered` только с разрешёнными substatus. Поэтому
точно 26 внешне подтверждённых единиц входят в recovery scope, а 5 отмен —
нет. Это актуальное доказательство, а не исторические 26 из снимка 11:31 UTC.

## Current accounting и расчёт

После Ozon read выполнены 11 bounded `SELECT` через существующий tenant
read-only gateway: `2026-10-06T20:57:32.547712+00:00` →
`2026-10-06T20:57:49.022195+00:00`. Manifest с hashes результатов находится
в `accounting-post-marketplace-20261007-attempt2/accounting-refresh-20261006-attempt1/manifest.json`,
его SHA-256 — `8b56eb9a2871465c66d2ba68a81b6a1c7051d1e81dfca02b3925434ef0643b77`.
Все 11 результатов успешны и не обрезаны; manifest фиксирует `writes=0`,
`external_calls=0`.

В exact scope всё ещё 31 ledger recipe. У каждой строки отсутствуют
`shipment_movement_id`, `written_off_at`, `reversed_at` и
`reversal_movement_id`; не найдено unlinked FBS shipment, нового
атрибутированного FBS movement или иного отрицательного movement после
предыдущей точки аудита. Следовательно, `already_conducted_quantity=0` для
доказанных 26 единиц. Текущие WMS statuses — 13 `done`, 13 `in_delivery`, 5
`cancelled`; резерв=13. 11 исторических facts и 22 charges всё ещё сохранены
по ID; всего наблюдаются 13 facts и 26 active charges, без reversal.

**Доказанная current missing delta = 26 единиц**:

`proved_unique_quantity 26 − already_conducted_quantity 0 = 26`.

Это расчёт для будущего штатного WMS-662, а не разрешение выполнить его:
`actual_recovery=NOT_PERFORMED`, `mutation_authorized=false`. Снимки Ozon и
ledger разделены примерно минутой и не являются общим lock; непосредственно
перед mutation WMS-662 обязан заново перечитать scope под своими обычными
locks и пересчитать разницу. Нужны также verified deployed SHA общего
кандидата и отдельная операционная команда root. Повторное действие должно
сохранить facts/charges и довести следующую delta до 0, а не списать 31 или
оживить отмены.

## Проверка артефактов

Локальный verifier связал все 31 external records с 31 WMS position, проверил
accepted statuses/substatuses, exact composition, отсутствие связанных child
postings и все post-read ledger guards. Он также подтвердил сохранность
11/11 historical fact IDs и 22/22 historical charge IDs. Итог verifier:
`positive_proved_units=26`, `missing_delta=26`.

Код продукта и тесты не менялись, широкие тесты не запускались. Этот отчёт не
является приёмкой, независимым review или доказательством деплоя общего
кандидата.
