# WMS-675 · адресный операционный runbook после VERIFIED deploy

## Статус и замена ошибочной версии

Это готовая передача операционному исполнителю, но не команда, уже выполненная
в production. **ACTUAL_REPAIR=NOT_PERFORMED.** Production read в `937adf`
доказал на тот момент 26 недостающих единиц, но API был на `8f11d912…`; это не
verified deploy общего кандидата.

Версия runbook из `0c7f83a29` честно **superseded** независимым review
`49dba841493ad4ee566fd5cbc4a4ed595abe189c`. Её ошибки F1–F3: общий
seller-wide `sync-statuses` не ограничен supply, предварительная проверка
queue гоночная, а запрет на принятый адресный recovery service был
необоснован. Git-история старой версии сохраняется; в операцию её не брать.

После VERIFIED deploy дополнительное разрешение владельца или отдельная
команда root не нужны: они уже даны. VERIFIED deploy — техническое условие,
а не подмена локальным SHA. До него этот runbook не исполняется.

Адрес неизменен: tenant `b80a893b-ab87-42b6-8fd7-6d41502c900f`, seller
`cf6d31c5-944b-4382-af34-636ca9aa8cc3`, WMS-source supply
`b82d1e9a-30d2-4d7b-b52d-9775c3d266e3`, warehouse
`2d968c65-4a8d-414e-9076-0f201c2dba63`, marketplace `ozon`; полный scope —
31 order/position по одной единице. Похожая October supply не является
заменой.

## Принимаемый существующий путь WMS-662

Используется существующая адресная последовательность WMS-662 внутри обычного
backend общего развёрнутого кандидата:

`ozon_targets` → `make_observation` → `save_observations` →
`lock_order_batch_packaging_rows` → `lock_handoff_batch_products` →
`conduct_supply` → `session.commit()`.

Это не новый endpoint, runner, SQL-скрипт или ручной алгоритм. Именно эту
цепочку покрывает принятый functional scenario
`recover_exact_supply` в `backend/tests/test_wms675_recovery_scenario.py`;
сам тест не переносится и не является исполняемым production runner-ом.
Запрещены только обходы оркестратора: прямой `write_off_order`, ручные target
quantity, SQL UPDATE, новый endpoint/runner, monkeypatch и seller-wide
`sync-statuses`/import. Обычный seller sync не используется именно потому,
что он способен затронуть чужие заказы.

## Последовательность после VERIFIED deploy

1. Зафиксировать полный SHA реально работающего production API и его
   совпадение с принятым WMS-662, включая `b4043c0d`. Проверяется весь
   сервис/зависимости, не только классификатор. Не менять live-флаг,
   credentials, роли, лимиты или bindings. Локальный SHA и `8f11d912…`
   старого read не являются доказательством релиза.
2. В обычной application session загрузить **только** указанную supply с
   tenant/seller/warehouse/marketplace/source=`wms`, всеми 31 order IDs и
   eager-loaded `product_positions`. До HTTP сохранить `observation_scope` для
   каждой позиции; другой seller/supply в работу не включать.
3. Вне складских locks через существующий seller-bound
   `OzonMarketplaceProvider`/`HttpxOzonMarketplaceTransport` получить ровно
   31 posting cards. Это семантически read-only card call
   `POST /v3/posting/fbs/get`: не вызывать ship/approve/deliver/create и не
   подменять application transport fake provider-ом. Проверить
   completeness HTTP, уникальность posting, SKU/offer/quantity и все
   related/weight children. Сохранить новый sanitized proof в отдельном
   каталоге, не перезаписывая `937adf`.
4. На этих карточках вызвать только существующие `ozon_targets` и
   `make_observation` с исходным scope. Unknown не положителен; `cancelled`,
   включая `cancelled_after_ship`, не получает новый расход. Ожидание из
   snapshot — 26 positive/5 cancelled, но число 26 не подставляется вместо
   fresh read.
5. До записи прочитать exact ledger/movement/reversal, reserve, stock/source
   recipe, facts, charges и их lines, а также весь persisted
   `observed_handoff` journal этой supply. Уже проведённое должно быть
   подмножеством fresh positive proof. Старый failed `supply_deliver` не
   является доказательством передачи. Старый positive target не продолжается,
   если fresh card отрицательна/unknown или scope противоречив.
6. Если складская delta=0 **и** reserve/facts/charges уже согласованы,
   пишущие шаги не нужны: сохранить read evidence и перейти к независимому
   readback. Если billing неполный, это не повод объявить repair законченным:
   продолжить ту же принятую адресную цепочку, которая использует cumulative
   quantities и не создаёт второй расход.
7. Иначе вызвать `save_observations(session, tenant_id, seller_id,
   observations)` ровно для 31 IDs. Он создаёт/обновляет один durable journal
   `observed:<supply-id>` под штатным lock supply и коммитит evidence отдельно.
   При timeout сначала прочитать journal и accounting: evidence могло
   сохраниться при частичном либо отсутствующем расходе; новую внешнюю сдачу
   никогда не создавать.
8. В новой транзакции после evidence commit вызвать штатный порядок locks:
   `lock_order_batch_packaging_rows(session, tenant_id, exact31_ids)` затем
   `lock_handoff_batch_products(session, tenant_id, seller_id, exact31_ids)`.
   После locks заново загрузить supply/orders/positions с `populate_existing`,
   ledger под `FOR UPDATE` и весь journal. Повторно сверить 31 IDs,
   tenant/seller/warehouse/marketplace/source, composition, observation scope,
   reversal и cumulative targets. HTTP после locks не делать.
9. При согласованном scope вызвать `conduct_supply(session, exact_supply)` и
   обычный `session.commit()`. Сервис сам применяет
   `prepare_shipment_sources` → `write_off_order(proved_quantities=targets)`,
   reservation reduction и cumulative billing. Не передавать ручную delta26:
   `write_off_order` сам вычитает уже completed recipe. Частичный результат
   или `error_code` не маскировать HTTP/confirmed: продолжать после readback
   только фактически незавершённую часть тем же путём.

Смена состава/принадлежности, неатрибутированный расход, reversal или
противоречащее persisted evidence — технический конфликт. Дождаться завершения
конкурентной штатной операции и повторить fresh чтение/проверку; не расширять
scope, не чистить journal SQL и не заменять это новым approval.

## Ожидаемый неизменный результат и readback

При неизменном fresh snapshot ожидаются: расход 26 по пяти SKU, completed
ledger 26 и reserve `13 → 0`. Existing 13 facts/26 charges сохраняются по
ID, полям и lines, включая historical 11/22; добавляются 13 facts/26 charges,
итог — 26 facts/52 charges, без дублей и reversal. Старое ожидание
11→26/22→52 и reserve16→1 относится к snapshot с `awaiting` и здесь не
применяется.

После commit независимая read-only session/существующий collector сохраняет
новый manifest и повторно проверяет exact31: external composition, completed
ledger/movements, отсутствие расхода на cancelled/unknown, stock/reserve,
facts/charges/lines и preservation existing IDs. При полном результате
`missing_delta=0`; повтор адресной цепочки не добавляет movement/fact/charge.
Expense26/delta0 при неполном billing не является успешным repair.

Обычная `schedule_seller_stock_publish` не подавляется. Её область — seller и
активные stock-sync bindings, поэтому lawful publication может пересчитать и
WB, и другие товары, а не только пять Ozon SKU. Не менять лимиты/bindings и не
обещать ровно один или пять внешних publish-вызовов; фактический успех/ошибку
публикации зафиксировать отдельно.

## Границы приёмки

**Prepare завершён:** есть fresh proof937adf, независимый review49, этот
адресный runbook и verified-deploy gate. **Actual repair не выполнен:** его
примут только по независимому readback с `missing_delta=0`, согласованными
reserve/facts/charges, сохранёнными old IDs и отсутствием второго расхода.

Статус передачи: **READY_FOR_VERIFIED_DEPLOY**. До фактического deploy и
следующего операционного запуска: **ACTUAL_REPAIR=NOT_PERFORMED**.
