# REVIEW · 01 · wb-marking

Читал дифф целиком через `git diff HEAD` по шести файлам продуктовой правки, канон
контракта из `CONTRACT.md`, разбор границ по `RESHENIYA.md` и `CASES.md`, сверял с
`MAP.md`. Тесты сам не запускал — дев прямо признал, что pytest в sandbox не
поднялся, оценка по коду «зелёный» была ручным ревью, не прогоном.

## Находки

- **`backend/app/services/fbs_autopoll_service.py:257` — регрессия для продавцов
  с content-only токеном.** `require_marketplace_token(...)` вынесен выше цикла
  и вне try/except. Раньше `sync_order_marking_statuses` вызывался per-order и
  ловил `FbsMarkingError("missing_marketplace_token")` в своём `except
  FbsMarkingError` per-order — на цикл влияло только логированием warning'а, а
  дальнейшая часть `sync_fbs_order_statuses_for_seller` (в частности
  `sync_in_delivery_supplies`) продолжала работать. Теперь исключение
  пробрасывается наружу из `sync_marking_statuses_for_assembling_supplies`,
  минует `except (WbMarketplaceOrdersError, FbsCancellationError)` в
  `sync_fbs_order_statuses_all_sellers`, ловится общим `except Exception`,
  инкрементит `seller_errors` и — критично — весь оставшийся хвост
  `sync_fbs_order_statuses_for_seller` (включая `sync_in_delivery_supplies`)
  не выполняется. **Сценарий поломки:** продавец, у которого настроен только
  `content_token_encrypted`, но нет `marketplace_token_encrypted` (это
  разрешённая комбинация по `list_sellers_with_marketplace_token`) — каждый цикл
  ловит ошибку в логах и теряет tracking supplies. До правки — та же ветка
  давала per-order warning и tracking продолжал ехать.

- **`backend/app/services/fbs_autopoll_service.py:239` — снят per-tick лимит на
  количество заказов.** Константа `MARKING_SYNC_BATCH_SIZE = 100` удалена вместе
  с `.limit(MARKING_SYNC_BATCH_SIZE)`. Запрос теперь грузит все заказы селлера в
  статусе `assembling` в память (`orders = list((await
  session.execute(stmt)).scalars().all())`) и режет их на пачки по 100 в
  `split_marketplace_order_id_batches`. **Сценарий поломки:** продавец с
  большим backlog (500+ assembling заказов) удерживает `wb_seller_lock` на
  время последовательных 5+ HTTP-вызовов к WB. Ручной вызов
  `POST /operations/fbs-orders/{id}/markings/sync` от оператора в это время
  либо ждёт лок, либо получает 409/500. Контракт (Q4 в RESHENIYA) явно говорит
  «ритм и объём цикла не меняем, только режем количество HTTP-запросов». Здесь
  же незаявленно вырос объём заказов, обрабатываемых за один тик.

- **`backend/tests/test_fbs_marking.py:522-535` — тест ORPHAN-003 проверяет
  константу, а не поведение.** Тест ассёртит, что `META_STATUS_REJECTED`,
  `META_STATUS_REPLACEMENT_REQUIRED`, `META_STATUS_MISSING` не входят в
  `_ORPHAN_CANDIDATE_STATUSES`. Guard-clause `if marking.meta_status not in
  _ORPHAN_CANDIDATE_STATUSES: continue` (fbs_marking_service.py:531) при этом
  не задевается. **Сценарий поломки:** будущий рефактор уберёт этот `continue`
  или заменит его на `if marking.meta_status == META_STATUS_MISSING: continue`
  — константа останется в том же виде, тест зелёный, а строки в статусе
  `rejected` начнут получать `wb_orphan_candidate_at` и на следующем тике
  переезжать в `missing`, теряя `reason`, который прислал WB при отклонении.
  Ключевое поведение контракта («rejected/replacement_required не трогаем»)
  ни одним тестом не защищено.

- **`backend/app/services/wildberries_fbs_client.py:22` — слишком короткий
  fallback backoff.** `META_429_BACKOFF_SECONDS = 0.05` (50 мс) — это то, что
  ждёт клиент, если WB вернул 429 БЕЗ заголовка `Retry-After`. Контракт говорит
  «не более двух retry с backoff по Retry-After, ограниченным одной секундой»
  — верхняя граница задана, а fallback при отсутствии Retry-After сделан
  агрессивным. **Сценарий поломки:** WB при перегрузке отдаёт голый 429 без
  `Retry-After` (штатная ситуация под нагрузкой); клиент выстреливает три
  запроса подряд с интервалом 50 мс — усугубляя нагрузку, из-за которой WB и
  вернул 429. Ожидание при контрактной формулировке — секундный порядок
  задержки. Не блокер выкатки, но противоречит цели «устойчивость к 429».

## Проверено и нормально

- Границы правки: все шесть файлов диффа входят в разрешённый список; ничего
  за пределами `backend/app/{models,services,tasks}` и `backend/tests` не
  тронуто; фронт не задевается (S-03/S-14/S-15 остаются как есть).
- Совпадение с контрактом: удаление мёртвого `fetch_marketplace_order_meta`
  выполнено буквально; `EVENT_WB_ORPHANED` добавлено в
  `MARKING_CODE_EVENT_TYPES`; двухтиковое подтверждение с флагом
  `wb_orphan_candidate_at` реализовано; `_release_orphan_code` берёт
  `SELECT FOR UPDATE`, различает `reserved` (возврат в пул), `printed/applied`
  (консервация физического статуса) и терминальные (снятие ссылки); аудит-блок
  `previous_meta_status`/`previous_check_status` пишется в
  `meta_details_json` и в `MarkingCodeEvent.meta_json`.
- Идемпотентность: после тика 2 marking переходит в `META_STATUS_MISSING`,
  которого нет в `_ORPHAN_CANDIDATE_STATUSES` — повторный тик его пропустит.
- Не задет боевой прод, не задет живой WB (все тесты монкипатчат
  `fetch_marketplace_orders_meta_batch`; сторож `wb_seller_lock` не
  переустановлен).
- Утечек секретов, PII и явных данных в диффе нет; токен ходит через
  существующий `require_marketplace_token`, в логах не мелькает.

ВЕРДИКТ: НАХОДКИ 4
