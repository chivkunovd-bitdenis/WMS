# WMS-058 / WMS-084 / WMS-277 / WMS-395: финальное ревью Opus

9 сентября 2026 года, итог получен в06:33МСК. Фактический reviewer
claude-opus-4-7, CLI effort max, session
4a26b04b-0320-44f7-9938-c38793d43bcb. Успешное завершение,
is_error=false,67ходов,1237841мс. Frozen HEAD
8cc97a07e6a8fa89e9506f7b79ef2474eb8a735b, base
40b722a4d2d0ff1a6a5899cdb2713a98d1265bc5.

Первый запуск после06:10 не нашёл прежнюю локальную session ID и завершился
до ревью. Финальная проверка выполнена в новой сессии тем же явно заданным
Opus max. Read/Grep/Glob — единственные разрешённые инструменты; тесты и
внешние API этому reviewer не предоставлялись.

Ниже сохранён итоговый ответ без исправления его формулировок. Это мнение
reviewer, которое независимо оценивается Astra xhigh перед выпуском.
В частности, число тестовых файлов в первом абзаце подлежит поправке в
отдельной оценке: фактический diff содержит9 прикладных и9 тестовых файлов.

---

Готов сформулировать вердикт. Проверил всю партию по коду: девять прикладных файлов + тесты в diff, сквозные цепочки WMS-058/084/277/395, границы транзакции, блокировки, все callers `is_unbound_cancelled_wb_code`, `_prepare_code_for_binding`, `_finish_box_collection`, разбор конкурирующих сценариев в тестах.

---

## Вердикт: **окончательный релиз-кандидат `8cc97a07` можно катить**

Рассмотрен frozen HEAD `8cc97a07e6a8fa89e9506f7b79ef2474eb8a735b`, база `40b722a4d2d0ff1a6a5899cdb2713a98d1265bc5`, охват — весь `tmp/wms-next-frozen.diff` (9 прикладных файлов + 6 тестовых). Обязательных исправлений нет: все четыре задачи реализованы согласно постановке владельца, а прежние ошибки (исторический INB-адрес, частичный commit, void вместо detach, autoflush до commit-guard, hasOperatorKiz без pool) закрыты корректно и без оверинжиниринга.

Ниже разбор по каждой задаче — что смотрел, что подтвердилось, и какие сопутствующие наблюдения стоит держать в голове, но которые не блокируют выкатку.

### WMS-058 — точный источник и целая транзакция

Здесь коробочный сервис перепроектирован сразу по трём осям, и все три согласованы между собой.

Скан тары теперь возвращает `kind="container"` (`marketplace_unload_box_service.py:376-395`), не двигая содержимое: клиент запоминает источник и следующим сканом снимает конкретную единицу из этой тары. Функция `_source_location` (line 227-256) резолвит адрес по фактическому `InventoryBalance` — если whole-box putaway оставил в `warehouse_map` устаревшую ячейку, реальный балансовый адрес всё равно возьмётся из новой. Fallback на `resolve_container_location` включается только для пустой тары, что безопасно. Разъезд между несколькими ячейками для одной тары корректно падает в `invalid_container_reference` (line 246-250).

Границы commit пересобраны так, как этого требовала постановка. `collect_into_box` (`marketplace_unload_collect_service.py:390`) и `_place_picked_into_box` (`marketplace_unload_box_service.py:477`) переведены с `commit()` на `flush()`, а публичные операции — `add_manual_qty_to_box`, `collect_ready_box_into_open_box`, `attach_existing_box_by_barcode`, `copy_box` — закрывают транзакцию через `_finish_box_collection` (line 211-224), которая либо коммитит через `sync_lines_from_pick_allocations` (существующий синхронизатор, `packaging_task_service.py:645`), либо делает прямой `session.commit()`, если задания упаковки нет. Прогнал по всем callers `collect_into_box` (`marketplace_unload_box_service.py:296`, `:554`, `:803`) — все три сидят внутри функций, гарантированно доходящих до `_finish_box_collection`. Прямых вызовов из API-слоя нет (`api/marketplace_unload_requests.py`).

Блокировка конкурентного подбора: `add_manual_qty_to_box` явно берёт `SELECT ... FOR UPDATE` на строку request'а (line 530-534) до расчёта `picked-boxed`, а `collect_into_box` внутри берёт ту же строку (`marketplace_unload_collect_service.py:287-295`) — блокировка re-entrant в рамках одной сессии, так что два скана одного request'а строго сериализуются. Тест `test_mixed_box_scan_failure_does_not_commit_placement` явно проверяет откат: половина операции успевает во flush, вторая половина падает `insufficient_available`, и в детальке коробок `destination["lines"] == []` — flushed box_line действительно откатился, как и должно.

Наблюдение (не блокирует): в `attach_existing_box_by_barcode` дедуп-проверка wh_box (line 611-619) стоит **после** сбора содержимого. С новой транзакционной границей это как раз работает правильно: при обнаружении дубликата откатывается ВСЁ, включая аллокации — это лучше прежнего поведения, когда каждый collect коммитил свою часть.

### WMS-084 — физический код после операторской отмены

Ключевая штука — три условия сработали вместе и без дырок.

`_void_existing_sgtin_marking_locally` (`fbs_kiz_service.py:1105-1153`) берёт код под `FOR UPDATE` с `populate_existing=True` (line 1114-1117), проверяет `operator_detach = reason == _VOID_OPERATOR_CANCEL_REASON and is_wildberries(order)` (line 1123-1126) и только для этой комбинации оставляет статус APPLIED (или INTRODUCED, если код уже был введён), обнуляя `packaging_task_line_id`. Все остальные пути — WB-замена, Ozon-отмена, WB-упаковка — уходят в старую ветку `code.status = STATUS_VOID` (line 1134). Верно, что INTRODUCED не деградирует до APPLIED (line 1129-1130).

`is_unbound_cancelled_wb_code` (`marking_code_service.py:3710-3730`) требует одновременно четырёх условий: status ∈ {APPLIED, INTRODUCED}, `packaging_task_line_id IS NULL`, отсутствие любой `FbsOrderMarking` на этот код, наличие исторического события `EVENT_VOIDED` с reason=`"отмена оператором"`. Как правильно замечено в постановке, событие проверяется как «где-то есть», а не как последнее — это допускает многократный цикл cancel→rebind→cancel, но никогда не воскресит замороженное состояние (SHIPPED/TRANSFERRED/DEFECTIVE), потому что первое условие про статус срезает такие коды на входе. Прошёл по всем сценариям пробуждения запрещённого кода — все три известных мне пути (переход через SHIPPED, ручное переключение в VOID, чужой selller/product) корректно отсекаются либо статусом (SHIPPED, VOID), либо более ранними проверками в `_claim_pool_code_if_present`.

Гейт «WB и только WB» правильно поставлен во всех вызывающих: `_ensure_kiz_not_occupied_in_pool` (line 837) и `_claim_pool_code_if_present` (`fbs_marking_service.py:618`) оба обёрнуты в `if is_wildberries(order) and …`. В `_prepare_code_for_binding` (`fbs_kiz_service.py:1041`) проверка `cancelled` вычисляется без гейта, но это безопасно: до этой точки Ozon-заказ с не-AVAILABLE кодом уже развернулся бы в `duplicate_kiz` в `_claim_pool_code_if_present`, а полный VOID код от Ozon-отмены не проходит первое условие функции. Ozon корректно продолжает использовать `_VOID_REPLACED_REASON` через `replaced_by_ozon_kiz` (`ozon_kiz_service.py:166`), не задевая WB-пул.

Гонка «два заказа хватают один освободившийся код»: `_claim_pool_code_if_present` (`fbs_marking_service.py:600-604`) берёт код под `FOR UPDATE` до всех проверок, и первый попавший ставит `packaging_task_line_id`. Второй, дождавшись коммита первого, читает уже привязанный код: `is_unbound_cancelled_wb_code` возвращает False (line != None), статус != AVAILABLE — падает `duplicate_kiz`. Тест `test_postgres_two_orders_claim_detached_code_only_once` явно это проверяет через `wait_for_row_lock(second_pid)` — гарантируется именно ожидание на замке PostgreSQL, а не тайминговая случайность.

Поздний metadata GET защищён отдельно: `apply_meta_batch_to_markings` (`fbs_marking_service.py:815-817`) фиксирует набор ID markings в начале запроса и сравнивает с текущим состоянием под `FOR UPDATE` — если после отмены/новой привязки состав изменился, ответ WB отбрасывается, старое состояние не перезаписывается.

`from_pool` в `_prepare_code_for_binding` (line 1044) — тернарник `pool_code.source == "pool" if cancelled else not received`. Разложил по всем четырём сочетаниям (cancelled × received × source):
- pool + cancelled → `from_pool=True` → `FbsOrderMarking.source="pool"` → бампает `qty_marking_printed`;
- external_fbs + cancelled → `from_pool=False` → `source="operator"` → бампает `qty_marking_external`.

Оба случая ровно совпали с ожиданиями теста `test_cancel_rescan_and_replay_preserve_code_and_move_line_counts` для параметризаций `("external_fbs", "applied")` и `("pool", "introduced")`. Счётчик `qty_marking_external` при detach внешнего кода уменьшается на 1 (line 1144-1145) — до отмены был 1, после отмены 0, после rebind снова 1. Сходится.

### WMS-395 — крестик у pool-кода

Фронтовая правка `hasRemovableKiz` (`FfFbsSupplyWorkspace.tsx:172-180`) корректна и с обоими вызывающими совместима. Для WB: `source ∈ {operator, pool}`, любые статусы кроме `missing`, в том числе `rejected`. Для Ozon: только `operator`, без `rejected` — как в исходной постановке WMS-395. Проверил через `grep` все места создания `FbsOrderMarking` в бэке (`fbs_kiz_service.py:1348`, `ozon_kiz_service.py:221`, `fbs_order_tape_print_service.py:695`) — значения `source` только `"pool"` и `"operator"`, покрытие полное, никаких `"external_fbs"` в этом поле нет.

Оба caller-а работают правильно. Inline-крестик (line 2127) выведен под `!isOzonSupply`, поэтому там жёсткая передача `'wb'` корректна: до этого места код с Ozon-поставкой не доходит. Пункт меню «Отменить КИЗ» в reprint-меню (line 2634) передаёт `isOzonSupply ? 'ozon' : 'wb'` — то есть в Ozon-поставке применит правило Ozon-варианта.

Сервер `cancel_order_kiz` (`fbs_kiz_service.py:1205-1259`) действительно уже поддерживал pool и rejected: `_current_sgtin_marking_for_update(session, order.id, include_rejected=True)` (line 1215) находит и rejected-привязку тоже. Пересчёт счётчиков `qty_marking_external` / `qty_marking_printed` по остаточным кодам, привязанным к строке упаковки (line 1239-1255), выполняется под тем же lock'ом строки — согласовано.

Совместимость с WMS-084 — самое главное: до WMS-084 крестик у pool-кода уничтожал бы физический код (status→VOID), теперь же он законно detach'ит, и код становится годным для повторной привязки на другой заказ. Именно этот флоу и подтвердил Chrome-прогон (A/WB500043 → DELETE 204 → applied/notavailable → B/WB500044 → одна новая привязка).

### WMS-277 — конфликт артикула не роняет импорт

Правка в `wildberries_product_import_service.py:326-335` минимальна и безошибочна: после `_apply_variant_fields` при `sku_changed` делается `session.flush()`, `IntegrityError` ловится тут же, транзакция откатывается, счётчик `skipped` бампается, `continue` уходит на следующий вариант. Именно этого требовала постановка — поймать столкновение до того, как автоflush внутри `SELECT` про `ProductDimensionEvent` (line 361-366) выбросит `IntegrityError` вне commit-guard.

Область rollback чистая: предыдущие успешные варианты уже закоммичены (line 392 или 269 для create-branch); `_mark_legacy_products_for_card` (line 71-100) отработал и закоммитил раньше цикла. После `session.rollback()` ORM-инстансы экспайрятся, но код тут же делает `continue`, и следующий заход в цикле начинает с `_find_product_for_variant` (line 247) — свежий SELECT, никаких stale-объектов.

Событие `ProductDimensionEvent` для пропущенного варианта не создаётся: `_record_dimension_event` (line 370-379) сидит **после** flush-гейта, поэтому в путь skip оно не попадает — тест это явно проверяет (`assert ProductDimensionEvent.id is None`).

Параметризация `swap_sizes ∈ {False, True}` покрывает оба реальных сценария из production-часа: merge (два штрих-кода в один размер) даёт `skipped=1, updated=1`; swap (WB поменял размеры местами) даёт `skipped=2, updated=0`. Оба варианта дают идентичный результат при повторном запуске — идемпотентность подтверждена сравнением `first.json() == second.json() == expected`.

### Наблюдения без блокировки

Три вещи, которые я заметил, но которые НЕ являются багами и не требуют правки перед выкаткой.

Первое — семантическая двусмысленность `EVENT_VOIDED`. Событие пишется с типом `voided` даже когда код на самом деле остаётся APPLIED (WB operator detach путь). В коде всего три consumer'а этого типа события (`is_unbound_cancelled_wb_code`, `ozon_kiz_service.py`, само `_void_existing_sgtin_marking_locally`), и никто из них не делает вывода «код в состоянии VOID» на основании только event_type — единственный, кто читает это событие, `is_unbound_cancelled_wb_code`, проверяет ещё и `reason == "отмена оператором"`. Название легаси, поведение корректно.

Второе — в container-ответе API (`api/marketplace_unload_requests.py:375-382`) не заполняется `location_code`. Фронт делает `j.location_code ?? j.storage_location_id` и в итоге может положить в `activeLocationCode` UUID вместо человеческого кода. Но чип рендерится как `activeContainer ? 'Тара: ${container.code}' : 'Ячейка: ${activeLocationCode}'` — то есть при наличии `activeContainer` UUID из fallback никогда не показывается. Побочка невидима.

Третье — диалог `readyBoxOverPlanOpen` теперь триггерится по общему `plan_limit_exceeded`, а не только на скан WHB/INB. Текст «В коробе больше товара, чем осталось по плану. Добавить всё содержимое?» немного странно смотрится при попытке добавить одну штуку сверх плана, но это UX-косметика, не корректность.

### Пределы этого ревью

Я не могу подтвердить: реальное подтверждение WB/ЧЗ на боевом кабинете (стенд использует учебный эмулятор), поведение физического ТСД и сетевого принтера, пиковую нагрузку и настоящий большой production-каталог (`WMS-398` дал 2.23/1.93с на 257 товарах — на масштабе тысяч не проверено). Про эти пределы честно сказано в постановке, и я их не переоцениваю.

Все проверенные цепочки — код, тесты, CI (34300792441 и 34302161540 успешны), сравнение с staging `50c9c88e`, зафиксированные Chrome-прогоны — согласованы между собой. Со стороны ревью кода блокеров нет: катить можно.
