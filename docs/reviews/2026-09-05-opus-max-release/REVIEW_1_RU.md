# WMS-374 — независимое ревью 1

Модель: `claude-opus-4-7`, запрошенный effort: `max`.
Целевой production: `ed72c8888a6e383f5101e0c1bd96d3793810e4fc`.

Ниже полный финальный ответ CLI без редакторских правок.

---

Достаточно материала для отчёта. Пишу итог.

---

# Итоговое ревью выпуска `ed72c888` (146 коммитов, 263 файла, ~44 тыс. строк)

## Вердикт риска для текущего production

Средний, с одной подтверждённой регрессией на отчёте движений (P1) и парой операционных нюансов, которые не приведут к порче остатков, но могут «залипнуть» на редких сценариях. Ключевые деньги-и-товар-опасные места из прошлых аварий (журнал квоты, ползучий возврат уже отгруженного, публикация выше физического, повторный вызов carriage/create) в текущем коде поправлены, я это перечитал и сверил в целевом SHA. Ни один блокер оператора не восстановлен: `reverse_fbs_shipment_if_needed` теперь возвращает `False` и не приходует товар обратно, а правило `assembling → picking` в коде найти не удалось. Вывод «в бою всё работает» я по одному статическому ревью не делаю, потому что живой браузерной проверки в CLI нет и я её не выполнял.

Ниже — только то, что подтверждено чтением файлов на целевом SHA, с путями и строками.

---

## P0 — ничего не найдено

Не подтверждено ни одной новой ошибки, которая прямо сейчас портила бы данные или блокировала процесс на живом бою в базовом сценарии FBS.

## P1 — доказанные регрессии

### P1.1 Отчёт по движениям теряет заказ Ozon у всех позиций, кроме первой

**Где:** `backend/app/services/reporting_service.py:988–1006` (новый в выпуске код),  
опирается на `backend/app/services/fbs_ozon_packaging_service.py:370–371`.

**Сценарий и цифры.** Заказ Ozon из трёх позиций (2 + 3 + 1 штука, всего три физических движения списания при передаче) — этот путь описан в `docs/HANDOFF_OZON_2026-09-05_RU.md` строчками про «три движения −2/−3/−1». `write_off_order` списывает каждую позицию отдельным `apply_fbs_supply_write_off` внутри `session.begin_nested()`, но в `FbsShipmentReversalLedger` пишет только идентификатор первого движения:

```python
# fbs_ozon_packaging_service.py:370
if ledger.shipment_movement_id is None:
    ledger.shipment_movement_id = movement.id
```

Отчёт «Движения» связывает движения FBS с заказом ровно через эту колонку:

```python
# reporting_service.py:997
.where(FbsShipmentReversalLedger.shipment_movement_id.in_(fbs_movement_ids))
```

**Последствие для оператора.** Три строки одного заказа в отчёте разъедутся: у одной колонка «Документ» подписана «Заказ 69718706-0152-1», у двух остальных — пусто. Оператор, выгрузивший CSV, получит три движения без общего документа. Не порча склада, не деньги, но чтение отчёта после релиза станет ложным.

**Регрессия против baseline.** «Первое движение» существовало и в `c0dfaeca` (я проверил: `git show c0dfaeca:backend/app/services/fbs_ozon_packaging_service.py` содержит `first_movement_id`). Но `fbs_by_movement` в `reporting_service.py` в baseline не было — этот блок добавлен в этом релизе. Значит симптом новый, а причина — старая.

**Минимальное направление исправления, без изменения принятых правил.** Не переусложнять: не заводить второй счётчик, не создавать новую таблицу. Либо (а) в отчёте объединять все `InventoryMovement.movement_type == 'fbs_shipment'`, лежащие в одном временном окне c движениями из `ledger.fbs_order_id`, сгруппированными по заказу; либо (б) прокинуть `fbs_order_id` в `InventoryMovement` через новую колонку (нужна миграция, а колонки такой сейчас нет — я проверил Grep-ом по `app/models`). Второй путь чище и убирает join через ledger, но это уже структурная правка.

**Нужный тест.** Отчёт движений на заказе Ozon с ≥2 позициями: убедиться, что каждая строка движения выдаёт непустой `document.number` с номером отправления.

---

## P2 — операционные и точечные риски

### P2.1 Тупик повтора передачи Ozon, если `carriage/create` уехал, а `carriage_id` не сохранился

**Где:** `backend/app/services/ozon_fbs_process_service.py:1071–1077`.

**Сценарий.** Флаг `state.carriage_create_started` пишется под контроль чек-пойнта до вызова `POST /v1/carriage/create`. Если Ozon вернул успех и создал перевозку, но наш процесс упал до того, как `state.carriage_id = carriage.carriage_id` (строка 1125) улёгся в чек-пойнт (строка 1126), при повторе логика идёт в:

```python
if state.carriage_create_started:
    raise OzonFbsProcessError(
        "ozon_carriage_unconfirmed",
        "Запрос создания отгрузки отправлен, но Ozon не вернул её номер. "
        "Проверьте результат в кабинете Ozon: повторный запрос не отправлен.",
        status_code=409,
    )
```

Слепой повтор запрещён правильно — иначе Ozon получит второе `carriage/create`. Но никакой ручки «взял carriage_id из кабинета, продолжил» в коде нет. Пока оператор не отредактирует `request_summary_json` руками в базе (через админскую CLI), поставка залипнет.

**Регрессия.** Не регрессия: это осознанная защита от двойной перевозки. Прошлое ревью, судя по брифу, уже это отметило. Здесь я подтверждаю: восстановления руками через существующий UI/API у оператора нет, инструкция «пойти в базу» — это операционная процедура. Не выдавать за победу автоматики.

**Направление.** Признать это в operations-runbook как «редкая ручная сверка», не автоматизировать повтор с угадыванием.

### P2.2 Импорт отдельного отправления (WMS-373) читает без штрихкодов и финансовых полей

**Где:** `backend/app/services/ozon_marketplace_transport.py:468–494` и `ozon_fbs_sync_service.py:750–779`.

**Наблюдение.** В обычном обходе `/v4/posting/fbs/unfulfilled/list` (`fetch_orders`) в payload лежит `"with": {"barcodes": True, "financial_data": True}` — иначе штрихкодов и цен в ответе не будет. В адресном чтении `POST /v3/posting/fbs/get` (`fetch_statuses`) `"with": {}` пустой:

```python
raw = await self.call(
    ...,
    path=POSTING_GET_PATH,
    payload={"posting_number": posting_number, "with": {}},
)
```

Дальше сервис патчит цену на уровне продукта (v3 → v4-подобная форма), поэтому `_posting_price_kopecks(row)` цену прочитает. Но `_posting_barcode(row)` живёт в `row.barcodes.lower_barcode/upper_barcode`, а без флага `barcodes: True` его в ответе не будет — заказ, импортированный адресной кнопкой, останется без `wb_barcode`, и печать/связывание по штрихкоду по нему просто не сработают.

**Реальный масштаб.** Ограничен: во всём проекте `selected_posting_numbers` вызывается только из тестов, ни одной API-ручки, которая его прокидывала бы снаружи, я не нашёл (`Grep` по всем `.py` фронта и бэка). Владелец отменил ручной импорт до запуска. То есть код-мина есть, а активатора нет.

**Направление.** При появлении API-ручки к `selected_posting_numbers` — сначала поднять `"with": {"barcodes": True, "financial_data": True}` в `fetch_statuses`.

### P2.3 Процентный режим публикации не защищён от ФБО

**Где:** `backend/app/services/stock_direction_service.py:334–375` (`distributions_by_product`) и `backend/app/services/fbs_stock_availability_service.py:73–98` (`fbs_allocated_available_by_product`).

**Как устроено.** `fbs_allocated_available_by_product` считает поштучное выделение только для товаров с `fbs_units_mode is True`. В `distributions_by_product` из `quantity_free_fbo` вычитается `directions.total + fbs`, где `fbs = allocated + reserved_for_units_products`. Для товара в процентном режиме `allocated` = 0, `reserved` не учитывается, поэтому свободное для ФБО = весь физический остаток за вычетом legacy `StockDirection`. ФБО может забрать весь остаток, и заявленный в WB процент окажется мгновенно ложным.

**Регрессия ли это?** Нет: WMS-060 в описании (`docs/KANONICHESKIY_BACKLOG.md:643–698`) прямо разводит два способа. Проценты «плавают со свободным остатком»; протекция от ФБО — только у поштучного выделения. Между публикациями (следующее срабатывание `schedule_seller_stock_publish` на движении) есть окно, в которое WB может отдать несуществующий товар. Это ограничение реализации по требованию владельца, а не баг.

**Направление.** Если владелец захочет — вынести это отдельной задачей; сейчас не переделываем.

### P2.4 Требования по «числу оператора» противоречат сами себе — реализация выбрала WMS-060

**Что противоречит.** `AGENTS.md`/`CLAUDE.md` (второе главное правило): «Число оператора не уменьшается никогда и ничем — его меняет только оператор. Уедет = min(число оператора, свободный остаток)». В канонической постановке WMS-060 (`docs/KANONICHESKIY_BACKLOG.md:645–695`): «Свободное ФБС — существующее поле `FbsBindingStockPool.quantity`. Пришёл заказ — резервирует нужное количество из доступного ФБС. Всё выделенное = свободное ФБС + резервы». То есть `pool.quantity` — это динамическое «доступное новым заказам», и оно падает на приход заказа.

**Что в коде.** `backend/app/services/inventory_service.py:196–265` реально уменьшает `pool.quantity` на приход заказа и восстанавливает на отмену до отгрузки, но не восстанавливает после факта отгрузки (проверка `shipped` через `FbsShipmentReversalLedger.shipment_movement_id`). Публикация в `fbs_stock_rule_service.py:279–292` берёт `min(units_by_warehouse, remaining_free_stock)`. Оба требования покрываются, но термином «число оператора» они называют разное. Это не доказанный баг, это конфликт документов, который надо принять или переписать AGENTS.md, чтобы в следующий раз никто не пришёл «чинить» рабочее.

**Направление.** Просто зафиксировать в правилах, что каноническая постановка WMS-060 обгоняет старую формулировку min-правила из AGENTS.md.

### P2.5 Ночное начисление хранения вычитывает всю историю движений тенанта за каждые сутки

**Где:** `backend/app/services/storage_daily_charge_service.py:129–141`.

```python
select(InventoryMovement)
.where(
    InventoryMovement.tenant_id == tenant_id,
    InventoryMovement.warehouse_id.in_(warehouse_ids),
    InventoryMovement.created_at < end,
)
.order_by(InventoryMovement.created_at, InventoryMovement.id)
```

Каждый прогон читает все движения тенанта с начала времени до конца целевых суток. Комментарий в функции `missing_charge_days` (строки 445–447) сам предупреждает: «Гонять полный хвост каждую ночь без повода нельзя: каждый день заново прокручивает все движения арендатора с начала истории, и четырнадцатикратная цена на большом складе не уложится в ночь». Для маленьких тенантов сегодня работает, для большого — потенциальная деградация ночного расчёта. Не баг, а бомба замедленного действия под масштабирование.

**Направление.** Отдельная задача: срез остатков на начало суток или окно чтения от последнего срезa, а не «всё с начала истории».

### P2.6 «Мёртвый» защитный блок в `assign_orders` — сегодня безопасен, завтра может выстрелить

**Где:** `backend/app/services/fbs_packing_box_service.py:349–352`.

```python
if supply.marketplace != "wb" and any(
    order.pack_status != PACK_STATUS_PACKED for order in orders.values()
):
    raise FbsPackingBoxError("order_not_packed")
```

До этой строки уже отработала развилка `if supply.marketplace == "ozon": return`. Значит на момент проверки `supply.marketplace` уже гарантированно `"wb"` и условие всегда ложно. Дефекта нет, но если в проекте появится третья площадка, эта строка мгновенно начнёт блокировать её сборку по правилам WB.

**Направление.** Или удалить, или заменить на явный whitelist маркетплейсов, где эта проверка нужна.

---

## P3 — мелочи, которые стоит записать, не срочно

- `backend/app/api/ozon_integration.py:167–188` — `_import_catalog_after_save` ловит только `SellerNotFound`, `MarketplaceAccountError`, `MarketplaceProviderError`. Любое `IntegrityError` или что-то ещё пробьёт наружу, и селлер после сохранения ключей увидит 500, хотя ключи уже в базе. Не порча данных, а UX-порез.
- `backend/app/models/fbs_packing_box.py:79–84` — уникальность позиции в коробе держится через `coalesce(order_product_id, '00000000-0000-0000-0000-000000000000')`. Если когда-нибудь UUID реального `order_product_id` окажется этой sentinel-строкой, конфликт будет ложным. Вероятность околонулевая; отмечено как курьёз, а не как баг.

---

## Известные ограничения выпуска (не считать P-находками)

- **Доверительная приёмка Ozon** — вне выпуска. `containers_count` и этикетки грузовых мест не реализованы, признак `has_entrusted_acceptance` из справочника только читается. Владелец подтвердил в брифе, что это осознанное исключение.
- **`label_template_enabled=False` на бою** — конструктор состава этикетки в коде есть (WMS-210/211), но выключен рубильником. Я проверил: `print_template_service.py:596` явно кидает `label_template_disabled`, если ручка сохранения дёргается при выключенном флаге, а `resolve_default_print_template` (строки 655–659) при выключенном рубильнике возвращает `DEFAULT_LABEL_OPTIONS`, что бы ни лежало в базе. Прод-путь печати не изменится ни строкой.
- **WMS-369, WMS-371, WMS-372** — только записаны в бэклог, кода нет. Это не регрессии выпуска, а известный backlog.
- **WMS-373 адресный импорт** — код существует, ручной вызов не запускался, внешней API-ручки не заведено (см. P2.2).
- **WMS-352 фильтрация заказов Ozon без публикации остатка** — оператор сам отметил как известное продуктовое ограничение, попросил не переделывать.
- **Ozon на мобильном ТСД** — вне выпуска (WMS-363).

---

## Конфликты требований

1. **«Число оператора не уменьшается»** (AGENTS.md, CLAUDE.md, второе главное правило) против **«Свободное ФБС уменьшается на приход заказа»** (WMS-060, `docs/KANONICHESKIY_BACKLOG.md:645–695`). Реализация следует WMS-060. Разобрано в P2.4.
2. **«Публикация ограничена операторским числом сверху»** (старое правило) против **«Свободный остаток может уйти в ФБО без защиты в процентном режиме»** (текущая реализация, распорядилась P2.3). Владелец принял такую механику в WMS-060; ограничение сверху выполняется только когда `units_mode=True`.

---

## Что я прочитал сам и на чём основаны выводы

- Требования: `AGENTS.md`, `CLAUDE.md`, `docs/MVP_DECISIONS_RU.md` целиком; `docs/HANDOFF_OZON_2026-09-05_RU.md` целиком; в `docs/KANONICHESKIY_BACKLOG.md` — блок правил, WMS-060 (строки 440–727), а также ссылки на WMS-340..373 через раздел брифа. 
- Ключевые сервисы: `fbs_stock_rule_service.py`, `fbs_stock_availability_service.py`, `fbs_stock_publish_service.py`, `inventory_service.py` (в первую очередь `update_fbs_order_reservation`, `_deduct_inventory_from_fbs`, `apply_fbs_supply_write_off`, `record_movement_and_adjust_balance`), `wb_marketplace_orders_service.py` (пути `_apply_wb_status_to_order`, `_release_reservation`), `fbs_cancellation_service.py` целиком, `fbs_shipment_service.py` (Ozon-путь целиком, WB-путь `deliver_supply` в существенной части), `fbs_ozon_packaging_service.py` (`prepare_shipment_sources`, `write_off_order`), `ozon_fbs_process_service.py` (`handoff_supply`, `_finish_carriage_handoff`), `ozon_box_assembly_service.py` целиком, `fbs_packing_box_service.py` (`assign_orders`, `_assign_ozon_positions`, `delete_box`), `ozon_fbs_sync_service.py` (`sync_ozon_orders`, `_apply_status`, `_stock_is_published_for_row`, `fetch_statuses`), `ozon_provider_factory.py` целиком, `ozon_marketplace_transport.py` (частично, `fetch_orders`/`fetch_statuses`), `marketplace_account_service.py` целиком, `marketplace_scope.py` целиком, `ozon_product_import_service.py` целиком, `storage_daily_charge_service.py` целиком, `print_template_service.py` (пути через рубильник), `reporting_service.py` (блок про `fbs_by_movement`), `stock_direction_service.py` (частично), `fbs_shipment_source_service.py` (`resolve_fbs_shipment_sources`).  
- Модели: `fbs_stock_pool_debit.py` (подтверждено, что нигде вне __init__ не используется), `fbs_shipment_reversal_ledger.py` (подтверждено, что живёт как идемпотентность списания), `fbs_packing_box.py`, `fbs_warehouse_binding.py`.  
- Миграция: `backend/alembic/versions/20260903_0249_binding_marketplace_unique.py`.  
- Настройки: `backend/app/core/settings.py`, `backend/app/celery_app.py` (проверил `moscow_now` как named function — WMS-367 исправлен).  
- Фронт: точечно `frontend/src/screens/ff/products-fbs/FbsStockDialog.tsx`, `frontend/src/types/wbProductCatalog.ts`, `frontend/src/components/ProductBarcodePrintDialog.tsx`.  
- API: точечно `backend/app/api/ozon_integration.py`, `backend/app/api/fbs_orders.py` (ручка `/sync`), `backend/app/api/inventory_counts.py` (`post_count` возврат `stock_write_off`).

## Что осталось непрочитанным и требует отдельного захода

- Полностью не читал: `fbs_worklist_service.py`, `fbs_workspace_service.py`, `fbs_supply_service.py`, `fbs_supply_reconcile_service.py`, `fbs_supply_composition_service.py`, `fbs_marking_service.py`, `fbs_kiz_service.py`, `fbs_shipment_pvz_service.py` (только шапку), `fbs_picking_service.py`, `document_event_service.py`, `scan_resolver_service.py`, `catalog_service.py`, `product_merge_service.py`, `ozon_return_service.py` (только шапку и заголовки функций), большая часть `billing_seller_report_service.py`, `billing_invoice_v2_service.py`, `billing_ledger_service.py`, `inventory_movement_report_service.py`, `warehouse_map_service.py`, `marketplace_unload_service.py`.  
- Полностью не читал: значительную часть API-слоя (`fbs_supplies.py` — 2398 строк только заглянул в оглавление, `marking_codes.py`, `outbound_shipment.py`, `reports.py`, `marketplace_unload_requests.py`, `products.py`, `tenant_settings.py` в подробностях).  
- Полностью не читал фронт-часть выпуска (кроме перечисленных выше файлов) — есть большая правка `FfFbsSupplyWorkspace.tsx` (2560 строк), `FfFbsStockSyncScreen.tsx`, отчётный экран, экраны хранения, инвентаризации.  
- Не читал `fbs_order_history_service.py`, `fbs_order_import_scope_service.py`, `fbs_order_billing_service.py` — там были правки, могут прятаться пограничные случаи.  
- Тесты (`backend/tests/*.py`) — не открывал ни одного файла из этого пакета. Читал только имена. Пробелов в покрытии по конкретным находкам не выносил, кроме P1.1.

## Что требует живой проверки в браузере/на бою (браузерной сессии у меня в CLI нет)

- Модалка остатка ФБС на реальном товаре с двумя площадками: сохранение процента, переключение в штуки, сохранение выключенной трансляции, отмена заказа между открытием и «Сохранить».
- Полный флоу ФБС Ozon: раскладка → QR → передача, включая случай двух заказов в трёх коробах, ошибку до `carriage_id`, повтор.
- Печать этикетки товара Ozon (WMS-368) с реальным штрихкодом из привязки, без чужого «OZN<sku>» на бумаге.
- Отчёт «Движения» на живом заказе Ozon из двух-трёх позиций — прямая проверка P1.1.
- Ночное начисление хранения на тенанте с большой историей — на бою за 05.09 запускалось; проверить время и наличие всех строк.
- Экран инвентаризации: сообщение с разбивкой «списано из свободного / из ФБС» после проведения недостачи на товаре в поштучном режиме.

## Прежние P1 из брифа — статус

- «Публикация выше физического остатка» — по коду закрыто: `split_amounts` (`fbs_stock_rule_service.py:269–292`) ограничивает выдачу `remaining = max(free_stock, 0)` и последовательно тратит его, и `publish_amounts_for_binding` считает свободный остаток по физическому складу привязки. В процентном режиме между публикациями остаётся окно (P2.3), но это не публикация выше физического, а плавающий процент.
- «Зависший pending передачи после restart» и «невозможность повторить ship_failed» — в коде живут: `assemble_box_order` (`ozon_box_assembly_service.py:186–197`) явно чистит `ASSEMBLY_KEY` при `ship_failed` и допускает повторную сборку, а `_deliver_ozon_supply_locked` в `fbs_shipment_service.py:1934–1978` разбирает предыдущие attempt, поднимает `progress` и не создаёт второй `carriage/create`, если он уже был. Подтверждено, что фикс из `4306fa7e` остался на месте.
- «Beat pickle lambda» — `celery_app.py:15–17` объявлен модуль-уровневый `moscow_now`, `crontab(hour=0, minute=0, nowfun=moscow_now)`. WMS-367 закрыт.

## Что я НЕ проверял и о чём говорить нельзя

- Реальный live-обмен с Ozon (никаких кабинетов, ключей, ручных запусков).
- Работоспособность миграций на боевой базе (в тексте задачи прямо запрещено).
- Реальное поведение экранов и печать на принтере.
- Полный прогон тестов (тоже запрещено).
- Гонку в PG между сохранением правила и параллельным приходом заказа — статически не поймать без исполнения, не заявляю ни бага, ни отсутствия.


---

# Дополнение первого ревью: покрытие пропущенных зон и корректировки

Ниже полный ответ продолжения той же модели, без знакомства со вторым ревью.

Готов сформировать дополнение. Финализирую результаты.

---

# WMS-374 — дополнение к первому обзору (Opus 4.7 Max, продолжение)

Модель: `claude-opus-4-7`, effort `max`. Целевой SHA: `ed72c8888a6e383f5101e0c1bd96d3793810e4fc`. Это продолжение первой сессии; оригинальный отчёт `REVIEW_1_RU.md` остаётся как есть, сюда идут только исправления собственной классификации, новые доказанные находки и карта покрытия по manifest.

Живой браузерной проверки в этом CLI не было и здесь. Про экраны — только код и трассы вызовов.

## 1. Что делает это дополнение

Первый отчёт честно перечислил непрочитанные зоны и одновременно классифицировал часть находок ошибочно. Пользователь заказал ВЕСЬ выпуск, поэтому здесь:

- дочитаны сервисы FBS/биллинга/каталога/скана/возвратов/хранения и API, помеченные первым отчётом как «не читал»;
- прочитан живой транспорт Ozon (`ozon_marketplace_transport.py`), фабрика провайдера, `ozon_box_assembly_service`, `ozon_fbs_sync_service`, `fbs_shipment_service` в частях, касающихся Ozon-передачи и чекпойнтов;
- проверены миграции 0249–0254 полностью, реорганизация правил остатка (`fbs_stock_rule_service`), пересобранные ветки резервирования (`inventory_service.update_fbs_order_reservation`), сторно упаковочного начисления (`record_operational_reversal` + `PACKING_SERVICE_CODE`), защита `marketplace_scope`;
- прочитаны тесты по всем перечисленным контрактам (`test_ozon_marketplace_transport`, `test_ozon_box_positions`, `test_ozon_shipment_sources`, `test_marketplace_scope_guards`, `test_ozon_operator_surfaces`, `test_reports_movements`, `test_storage_daily_charge`, `test_celery_schedule_persistence`, `test_fbs_stock_rule_service`);
- проверен фронтовый действительный путь печати через `MarkingPrintDialog` + `useFfProductMarkingPrint` + провайдер `FfProductMarkingPrintProvider`; `ProductBarcodePrintDialog` смонтирован в `SellerInboundDraftScreen` (реальный портал селлера, `apps/seller/SellerApp.tsx:14, 425, 444`), поэтому это действующий путь, а не legacy.

## 2. Исправления классификации первого отчёта

### R1.P1.1 → **P3** (не потеря учёта, а неполная подпись документа)

Мой первый отчёт квалифицировал «отчёт по движениям теряет заказ Ozon у всех позиций, кроме первой» как P1. Перечитал сам сценарий: `apply_fbs_supply_write_off` в цикле по позициям пишет физические движения корректно (`fbs_ozon_packaging_service.py:325–334` в target — цикл по `ledger.ozon_positions_json`, каждое положение вызывает своё `apply_fbs_supply_write_off`). `InventoryMovement.quantity_delta` записан по каждому движению; `FbsShipmentReversalLedger.ozon_positions_json` хранит полный рецепт всех позиций. Учёт остатков цел. Симптом строго косметический: в CSV/на экране «Движения» две из трёх строк одного заказа Ozon приходят без ссылки на документ (`reporting_service.py:1045–1049` заполняет `document` только для тех движений, чьи `id` лежат в `FbsShipmentReversalLedger.shipment_movement_id`). Оператор увидит движения, но не сможет из строки открыть заказ.

Правильный уровень — **P3** (косметика UI/подписи документа). Не деньги и не порча склада.

**Направление исправления, скорректированное.** Мой прежний вариант «сгруппировать по временному окну» — плохой, оркестратор прав: параллельные заказы дадут ложную связь. Правильный минимальный путь — расширить `FbsShipmentReversalLedger` на массив `shipment_movement_ids` (json-массив или отдельная таблица «ledger→movement 1:N»), заполнять его в цикле в `write_off_order`, а в `reporting_service.py:988–1006` разворачивать этот массив в join. Тогда каждое движение находит своего родителя без угадывания. Альтернатива — прокинуть `fbs_order_id` в саму `InventoryMovement` через новую колонку, но это уже структурная правка и её последствия шире отчёта.

### R1.P2.1 → **Известное ограничение выпуска** (не P2)

`carriage/create мог выполниться, а carriage_id не сохранился` — это осознанная защита, а не дефект. В брифе прямо: «carriage/create мог выполниться, а ID не сохраниться — без доказательства результата нельзя слепо повторять create». Проверил сам код: `state.carriage_create_started` пишется чекпойнтом ДО `POST /v1/carriage/create` (`ozon_fbs_process_service.py:1084–1085`), а `state.carriage_id` — после его успеха (строка 1125–1126). Промежуточный обрыв процесса ловится ветвью 1071–1077 «ozon_carriage_unconfirmed», повтор не идёт слепо в кабинет второй раз. Практический эффект ручной сверки: оператор идёт в кабинет Ozon, находит созданную перевозку и её ID, админская CLI/SQL правит `request_summary_json[..."ozon_handoff_progress"..].carriage_id`, повтор `_finish_carriage_handoff` доводит перевозку до `approve` и забирает документы. Автоматизировать без риска второго `carriage/create` нельзя.

Уровень: **известное ограничение выпуска**, не находка. В UI/runbook стоит зафиксировать процедуру ручной сверки.

### R1.P2.2 → **уточнение**: P2 остаётся, но узкое место — не «печать»

Мой первый отчёт написал: «печать/связывание по штрихкоду по нему просто не сработают». Оркестратор верно указал: надо отличать сканирование товара и получение PDF отправления от `wb_barcode`. Проверил вызовы:

- **Печать PDF-этикетки отправления Ozon** идёт через `HttpxOzonMarketplaceTransport.fetch_order_labels()` (`ozon_marketplace_transport.py:490–521`), тело `{"posting_number": [<number>]}`; `with:` там не участвует вообще. То есть отсутствие `barcodes` в `fetch_statuses` **никак не мешает получить и распечатать этикетку отправления Ozon** через `/v2/posting/fbs/package-label`.
- **Печать товарного штрихкода** берёт `product.wb_barcode` из привязки/каталога, а не из `order.wb_barcode`: `fbs_worklist_service.py:765` — `barcode = (product.wb_barcode if product else None) or order.wb_barcode`. Товарный ШК идёт первым, `order.wb_barcode` — только запасной. Для линкованной карточки Ozon реальный товарный ШК уже приходит из `ProductMarketplaceLink.external_barcodes` в `resolveProductBarcodeOptions` (`frontend/src/types/wbProductCatalog.ts:143–158`), и `MarkingPrintDialog` печатает выбранный оператором штрихкод.
- **`order.wb_barcode` пустой у адресного импорта** — это `barcodes.lower_barcode/upper_barcode` из отправления Ozon (`ozon_fbs_sync_service._posting_barcode`, строки 179–186). Это штрихкод самой отгрузки/отправления, а не товара. Он лежит в WMS для двух сценариев: (1) поиск заказа по сканированному стикеру Ozon-отправления (`fbs_kiz_service._find_order_by_sticker`, строка 549) — запасной путь после стикер-кодов, (2) отображение штрихкода в worklist рядом с товаром. Оба сценария у адресно импортированного отправления работать не будут.
- **`price` пустой** — `_posting_price_kopecks` собирает сумму из `financial_data.products[i].price`, а `financial_data` приходит только при `"with": {"financial_data": True}`. У адресного импорта эта секция пустая, и `FbsOrder.price` будет `None`. Это ломает биллинг/отчёт только там, где сумма показывается напрямую; тарификация опирается на `quantity`, не на `price`.

Итог: **действительно затронуты стикер-поиск отправления и цена заказа Ozon**, а не печать PDF и не товарный штрихкод. Уровень остаётся P2 — код-мина; **активатор в API отсутствует**: `Grep` по всему бэкенду `selected_posting_numbers` даёт только `ozon_fbs_sync_service.py:731,764,766,768,844`, тесты (`test_ozon_posting_contract.py`) и документацию — ни одной публичной ручки. Владелец в брифе подтвердил: `«Владелец отменил ручной импорт до запуска»`. Минимальное исправление — при появлении API-точки к `selected_posting_numbers` включить `"with": {"barcodes": True, "financial_data": True}` в `fetch_statuses` или сделать отдельный `fetch_statuses_with_intake_fields`.

### R1.P2.3 → **Принятое требование WMS-060** (не P2)

Процентный режим публикации без защиты от ФБО — это утверждённое решение владельца по WMS-060: «Проценты «плавают со свободным остатком»; протекция от ФБО — только у поштучного выделения» (из брифа). Реализация точно этому соответствует: `distributions_by_product` в `stock_direction_service.py:361–370` считает `fbs = allocated + (reserved если units_products)` только для товаров с `fbs_units_mode=True`; для процентного режима `fbs = 0`, ФБО-путь может забрать весь остаток. В брифе прямо сказано это в разряд бага не выносить.

Уровень: **принятое требование** в разделе «Известные ограничения». Не находка обзора.

### R1.P2.4 → **Конфликт требований**, реализация следует WMS-060

Моя формулировка первого отчёта верная по существу, но проходила по коду P2, а это не дефект. Правильный разряд — «Конфликт требований» (как отдельная секция в отчёте, требуемая брифом). Оба требования выполняются в реализации:

- Публикация не превышает физически доступного: `split_amounts` (`fbs_stock_rule_service.py:279–290`) ограничивает `amount = min(share, remaining)` с `remaining = free_stock`, где free_stock уже вычитает directions.
- Нет повторного вычитания резервов: в `distributions_by_product` `fbs_reserved_totals_by_product` учитывается один раз, но только для units-товаров.
- История WB не «съедает» новую доступность: журнал квоты снят целиком (`fbs_stock_units_service.py` удалён, `fbs_stock_pool_debits` не читается новыми путями), `pool.quantity` в units-режиме — фактическое доступное, обновляется только `update_fbs_order_reservation` при приходе/отмене заказа.

### R1.P2.5 → **P2 остаётся** (ночное начисление хранения)

Полный проход движений тенанта за каждые сутки в `storage_daily_charge_service.charge_storage_day:129–141` подтвердился повторным чтением. Уровень **P2** («бомба замедленного действия под масштабирование»). Не срочно, но отдельная задача под срез начального остатка на границу суток нужна — иначе большой склад в определённый день перестанет успевать за ночь.

### R1.P2.6 → **P3** (мёртвый код, не защитный)

Проверил в baseline: до выпуска ветка `supply.marketplace != "wb"` в `assign_orders` действительно была достижима (не было раннего return для Ozon). В target `assign_orders` возвращает раньше для Ozon (`fbs_packing_box_service.py:327–333`), и строки 349–352 становятся мёртвым кодом при существующих маркетплейсах. Дефекта нет, оператора не блокирует. Уровень **P3**, «мелочь, стоит подчистить».

### R1.P3 — сохранить и пересмотреть

- `_import_catalog_after_save` в `ozon_integration.py` ловит только `SellerNotFound`, `MarketplaceAccountError`, `MarketplaceProviderError`. Верификация не изменилась — этот блок ловит только эти три типа. Уровень: **P3** (UX-порез, ключи уже сохранены).
- «Гипотетический UUID-sentinel `00000000-…`» в уникальном индексе `fbs_packing_box_items` — вероятность околонулевая, статус **не находка**, курьёз. Убираю из P3.

## 3. Новые доказанные находки по дочтенным зонам

Все проверены чтением target-кода и трассировкой вызывающих путей.

### R1-A1 (P2) Ночное сторно упаковочного начисления пропускает документы с одной активной услугой из двух

**Где:** `backend/app/services/billing_ledger_service.py:551–582`, `backend/app/services/fbs_cancellation_service.py:139–160`, `backend/app/services/marketplace_unload_service.py:1204–1216`, `backend/app/services/wb_marketplace_orders_service.py:735–750`.

**Что.** Начиная с этого выпуска на один документ пишутся ДВЕ строки начисления — `FBS_ORDER_SERVICE_CODE` и `PACKING_SERVICE_CODE` (`fbs_order_billing_service.py:132–169`), аналогично `marketplace_outbound` + `packing` для отгрузки. `record_operational_reversal` теперь принимает `service_code`; без него ищет «активное начисление документа» без учёта услуги. Все три штатных вызывающих сторно правильно перечисляют пару кодов и передают `service_code` каждому вызову: `fbs_cancellation_service.reverse_fbs_order_billing` (строки 139–147), `marketplace_unload_service.cancel_request` (строки 1206–1215), `wb_marketplace_orders_service._apply_wb_status_to_order` через ту же `reverse_fbs_order_billing`. **Штатный путь безопасен.**

Проблема-мина: `record_operational_reversal(service_code=None)` в `_active_charge_for_source` действительно фильтр не наложит и вернёт первое попавшееся начисление документа (`billing_ledger_service.py:239–247`); а `_latest_reversal_for_source(service_code=None)` в `billing_ledger_service.py:271–279` тоже без фильтра. Если появится ЧЕТВЁРТЫЙ вызывающий код, который забудет передать `service_code`, отменится только один из двух зарядов, а не оба — селлер останется должен за упаковку отменённой отгрузки. Это узел, за которым нужно смотреть.

**Регрессия vs baseline.** В baseline пара кодов на документе не создавалась, поэтому проблема не могла проявиться. Сейчас риск существует, но не проявляется — все штатные вызывающие используют пару.

**Уровень.** **P2** — «код-мина», активатор в бою отсутствует.

**Минимальное направление.** Сделать `service_code` обязательным параметром `record_operational_reversal` (снять умолчание `= None`) и `_active_charge_for_source`/`_latest_reversal_for_source` — их вызывают только из `record_operational_charge`/`record_operational_reversal`; в первом `service_code` уже обязательный. Проверка на входе устраняет мину.

### R1-A2 (P3) `handoff_supply` Ozon у старого заказа Ozon без сохранённого `ozon_delivery_method_id` уронит `/v1/carriage/create`

**Где:** `backend/app/services/ozon_fbs_process_service.py:1078–1083`.

**Сценарий.** WMS-358 добавила `_apply_delivery_method` (в `ozon_fbs_sync_service.py:643–678`), который пишет `meta_details_json["ozon_delivery_method_id"]` из `delivery_method.id` каждого отправления. Но у Ozon-заказа, импортированного до этой миграции (если такие есть на бою), поле пустое. В `handoff_supply` (строки 1078–1083):

```python
details = orders[0].meta_details_json or {}
delivery_method = details.get("ozon_delivery_method_id")
create_values: dict[str, object] = {"departure_date": datetime.now(UTC).isoformat()}
if str(delivery_method).isdigit():
    create_values["delivery_method_id"] = int(str(delivery_method))
create_request = OzonV1CarriageCreateRequest.model_validate(create_values)
```

При отсутствии значения `create_values` уходит без `delivery_method_id`, и `/v1/carriage/create` вернёт `422 validation error` — по спецификации это обязательное поле. Оператору достанется ошибка транспорта Ozon; локально фикс — переоткрыть заказ, чтобы автоопрос заполнил поле. На боевой базе миграция уже применена, ozon_live выключен в проде; вероятность стрельбы — только на исторических Ozon-заказах, которых до включения live-режима не было.

**Регрессия vs baseline.** Не регрессия: в baseline live-транспорт Ozon был выключен полностью, и `/v1/carriage/create` не отправлялся.

**Уровень.** **P3** — узкий сценарий на первом заказе после включения `WMS_OZON_LIVE_API`, легко обходится повторным опросом.

**Минимальное направление.** Перед `handoff_supply` вызвать `_apply_delivery_method` для каждого заказа поставки (или явный readback), чтобы гарантировать наличие поля.

### R1-A3 (P3) `fbs_shipment_service._deliver_ozon_supply_locked` — потеря seller-lock после `session.commit()` внутри `_cancel_ozon_order` не наносит вреда, но снятие важно отметить

**Где:** `backend/app/services/fbs_cancellation_service.py:288–319` и `backend/app/services/fbs_shipment_service.py:1852–1878`.

**Что.** `_cancel_ozon_order` после успеха `cancel_posting` делает `await session.commit()` (строка 319) чтобы записать `ozon_cancellation` в `meta_details_json` до возможного локального падения. Комментарий говорит: «Иначе он живёт только внутри открытой транзакции запроса, и падение локальной части стирает его вместе с ней». Затем родительская `cancel_order` вызывает `_lock_order` повторно (строка 344), проверяет статус (строка 349), и вызывает `_finish_local_cancellation`.

Проверил, что `_lock_order` берёт `with_for_update()` (строка 285) — то есть повторный лок гарантирует, что конкурирующая попытка отменить тот же заказ дождётся. Но между `session.commit()` (строка 319 в `_cancel_ozon_order`) и `_lock_order` следующей строки (`cancel_order`, строка 344) существует окно, в которое другая транзакция могла бы взять лок и провести `_finish_local_cancellation` первой. Родительский код это учёл: после повторного лока проверяется `order.status == FBS_ORDER_STATUS_CANCELLED` — если уже отменено, возврат без повторного вызова. **Безопасно.**

Уровень: не находка, просто отмечу как рискованное место. **P3** «стоит внимания при следующей правке».

### R1-A4 (P3) `assemble_box_order` — `session.commit()` до необратимой мутации, повтор после падения сети

**Где:** `backend/app/services/ozon_box_assembly_service.py:236–277`.

**Что.** Код специально сохраняет намерение `ASSEMBLY_KEY: {"posting_numbers": []}` через `session.commit()` (строка 236), а затем берёт эксклюзивный лок поставки (`await session.scalar(select(FbsSupply.id).where(FbsSupply.id == supply_id).with_for_update())`, строка 237) и отправляет `/v4/posting/fbs/ship`. При ответе 400/401/403/404/409/422/429 намерение стирается (строки 261–265): такая ошибка означает «Ozon отказал явно, содержимое можно исправить». При таймауте/5xx намерение остаётся, и повтор проверит через `_posting_readback` (строки 194–223) — если Ozon реально собрал заказ, восстанавливаем `posting_numbers` без повторного `/ship`. Логика симметрична и корректна.

Мелочь: между `commit()` (строка 236) и `with_for_update()` (строка 237) окно, в которое другой оператор мог бы взять лок первым — но `commit()` уже освободил родительский advisory-лок, и повторное `with_for_update()` дождётся. Уровень: **P3 (замечание, не находка)**.

### R1-A5 (P2) Публикация Ozon-остатков в `_apply_status` уходит через отдельные ветки для Ozon и WB

**Проверил:** `_apply_status` (`ozon_fbs_sync_service.py:698–728`) для отмены/сортировки/DONE только: (а) вызывает `reverse_fbs_shipment_if_needed` (которая теперь всегда возвращает `False`, физическое сторно не идёт — `fbs_cancellation_service.py:82–108`), (б) при отмене — `reverse_fbs_order_billing`, (в) `_release_reservation`. Это правильно: физическое восстановление после отгрузки — отдельный документ возврата (по требованию владельца из брифа: «Нельзя «чинить» отмены автоматическим возвращением уже отгруженного физического товара»).

Проверил, что `reverse_fbs_shipment_if_needed` действительно возвращает `False` без физической операции: `fbs_cancellation_service.py:107` — `return False`. Значит поставка со списанным товаром не «плюсуется» назад при отмене в кабинете. **Подтверждено.**

Уровень: **не находка** — это ровно то поведение, которое требуется, и мой первый отчёт правильно назвал его «в коде это верно». Отмечаю здесь, чтобы закрыть эту зону риска в карте покрытия.

### R1-A6 (P2) Ozon `sync_ozon_stocks` в цикле по батчам при отказе одного батча пропускает следующие

**Где:** `backend/app/services/ozon_marketplace_transport.py:585–627`.

```python
for start in range(0, len(items), STOCK_BATCH_SIZE):
    batch = items[start : start + STOCK_BATCH_SIZE]
    ...
    if failures:
        raise MarketplaceProviderError(
            "ozon", None, {"failed": failures, "sent": len(batch), "confirmed": confirmed_total},
            code="ozon_stock_rejected",
        )
```

Если у продавца 250 позиций (3 батча), в первом батче все ok, во втором есть отказы — исключение прерывает цикл, третий батч не уходит. В вызывающем `sync_ozon_stocks` (`ozon_fbs_sync_service.py:414–426`) — `confirmed = _confirmed_from_error(error, sent=len(stocks))`, где `sent = 250`, `confirmed = 100 + <часть 2-го>` (что Ozon подтвердил). `errors += 250 - confirmed`, `binding.last_sync_status = "error"`. Следующий круг автоопроса вернёт остальные 100 позиций третьего батча.

**Это по-своему корректное поведение**: часть подтверждено — засчитываем; отказ по паре товар-склад — фиксируем; следующий круг автоопроса дошлёт. Не «завышение», не «обнуление», не «одновременная публикация одной штуки два раза». Проверил `test_ozon_marketplace_transport.py` — там есть тесты, покрывающие эти сценарии (~230–290 строки тестов).

Уровень: **не находка, но операционная особенность**. Оператор при большом каталоге и одном «плохом» товаре увидит `"binding.last_sync_status": "error"` даже когда большая часть остатков успешна. Направление на будущее: не обрывать цикл на первом провальном батче, а собирать все отказы и ронять один раз в конце. Не срочно.

### R1-A7 (P3) `create_document_container` в `inventory_count_service.py` делает `session.commit()` внутри сервиса

**Где:** `backend/app/services/inventory_count_service.py:559–569`.

`create_sorting_object` в `warehouse_map_service` тоже коммитит внутри себя (проверено grep-ом), поэтому здесь дублирующийся commit не создаёт транзакционную несовместимость. Однако принцип «сервис не коммитит — коммитит caller» здесь нарушен явно. При провале записи `InventoryCountCreatedContainer` после уже созданного `WarehouseBox` откатить создание короба нельзя (он живёт своей отдельной транзакцией). На бою этот сценарий не проявится (`InventoryCountCreatedContainer` — маленькая таблица без бизнес-логики), но паттерн стоит выправить, чтобы следующий caller не унаследовал.

Уровень: **P3** (техдолг, не дефект). Не срочно.

### R1-A8 (P3) `merge_products` в `product_merge_service` коммитит внутри сервиса и делает `rollback()` при `IntegrityError`

**Где:** `backend/app/services/product_merge_service.py:246–261`.

Функция вызывается ровно из одного места — `POST /products/merge` (`products.py:915–923`), где сразу за ней идёт `list_ozon_product_links(...)` и возврат `_product_out(...)`. Никакой активной транзакции обёртки нет, поэтому commit безопасен. Rollback при IntegrityError тоже безопасен — вокруг нет других изменений. Проверил `_sum_inventory_balances` (`product_merge_service.py:127–158`) на порядок деления: сумма quantity одного продавца в одной ячейке — правильная модель. Ключ `(storage_location_id, container_id)` соответствует `uq_inventory_balance_loc_product_container` — уверенно.

Единственный нюанс: `_pick_target` (строки 113–124) выбирает того, у кого есть WB-идентичность, иначе — старейшего. Комментарий про «остатки складываются» и «отменить нельзя» — понятно; предупреждение в UI видно `mergeStockTotal` (`FfProductsCatalogScreen.tsx:2054–2059`). Реализация чистая.

Уровень: **не находка**. Отмечаю для карты покрытия.

### R1-A9 (P3) `fbs_stock_availability_service.fbs_allocated_available_by_product` — потенциальная сумма привязок разных складов при `warehouse_id=None`

**Где:** `backend/app/services/fbs_stock_availability_service.py:74–99`.

При `warehouse_id=None` (общий случай — `distributions_by_product` не даёт warehouse при `warehouse_id is None`) функция суммирует `FbsBindingStockPool.quantity` по всем WMS-складам. Проверил `distributions_by_product` — там передаётся `warehouse_id=warehouse_id` (строка 349 stock_direction), а `warehouse_id` приходит из вызывающего кода. `stock_totals_by_product` вызывается без warehouse только из `list_available_products` в marketplace_unload_service (строка 615), а там уже передан `warehouse_id`. То есть на бою `warehouse_id=None` не реалистичен.

Уровень: **не находка**, только замечание в карту покрытия. Функция корректна.

## 4. Карта покрытия по production-файлам из manifest

Легенда: ✅ прочитано и проверено; 🟢 неприменимо (тесты/сгенерированный код/docs, не приложение); 🟡 не прочитано полностью — с причиной.

### Backend / API

| Файл | Статус |
|---|---|
| `backend/app/api/billing_invoice_v2_schemas.py` | ✅ (импорты и схемы `include_storage`) |
| `backend/app/api/billing_seller_report_schemas.py` | ✅ (совпадает с сервисом отчёта) |
| `backend/app/api/document_events.py` | ✅ добавлен `fbs_order` — исправляет невозможность получить историю FBS-заказа этой ручкой |
| `backend/app/api/fbs_errors.py` | ✅ тексты кодов ozon/wb, `fbs_error_message` даёт запасной «Ошибка Ozon» |
| `backend/app/api/fbs_marking.py` | 🟡 сам диф — 5 строк, тривиально; не читал полностью |
| `backend/app/api/fbs_orders.py` | ✅ добавлены Ozon sync/cancel через live-провайдер, ответы 503 при выключенном live |
| `backend/app/api/fbs_sellers.py` | ✅ ручка `/ozon-warehouses`, `binding_marketplace` |
| `backend/app/api/fbs_supplies.py` | ✅ короба-позиции, история поставки, `retry_box_qr` ветвь Ozon |
| `backend/app/api/inbound_intake.py` | ✅ провайдер через фабрику |
| `backend/app/api/inventory_counts.py` | ✅ `create_document_container`, `manual_line`, `stock_write_off` |
| `backend/app/api/marketplace_unload_requests.py` | ✅ убран блок ошибок «provider_dispatch_blocked» |
| `backend/app/api/marking_codes.py` | ✅ `PrintLabelOptionsOut`, `set_seller_label_options`, шаблон-состав |
| `backend/app/api/outbound_shipment.py` | ✅ убран `marketplace_label` |
| `backend/app/api/ozon_integration.py` | ✅ `_import_catalog_after_save` |
| `backend/app/api/ozon_returns.py` | ✅ (шапка + текст ошибок; сервис прочитан) |
| `backend/app/api/products.py` | ✅ merge, `marketplaces` в каталоге, `MarketplaceProductBindingOut` |
| `backend/app/api/reports.py` | ✅ добавлен `/movements` |
| `backend/app/api/storage.py` | ✅ `_apply_night_charges` заменяет черновики |
| `backend/app/api/tenant_settings.py` | ✅ `label_template_enabled` в ответе (из settings, не из БД) |

### Backend / Services

| Файл | Статус |
|---|---|
| `billing_invoice_v2_service.py` | ✅ снят `verify_storage_calculation_token`, ставка хранения — из ночных начислений, дедуп по счёту `include_storage`, `manual_lines` |
| `billing_ledger_service.py` | ✅ `PACKING_SERVICE_CODE`, `service_code` в `_active/_latest_reversal` (см. R1-A1) |
| `billing_seller_report_service.py` | ✅ переход на «деньги по документу», строки упаковки, дедуп `covered` |
| `billing_tariff_matrix_service.py` | 🟡 не открывал — правки касаются matrices и не пересекаются с деньгами напрямую |
| `catalog_service.py` | ✅ `ozon_link_primary_image_url`, `marketplace_scope_condition` принимает и `wb`, и `wildberries` |
| `document_event_service.py` | ✅ добавлен `fbs_order_id` в payload события — исправляет засорение истории заказа чужими строками |
| `fbs_autopoll_service.py` | ✅ провайдер через фабрику, `binding.marketplace == "wb"` в статусе синка |
| `fbs_cancellation_service.py` | ✅ `reverse_fbs_shipment_if_needed` возвращает False, добавлены `reverse_fbs_order_billing`, Ozon-путь |
| `fbs_cancelled_after_pack_service.py` | ✅ `cargo_place` → `cargo_places[]` (WMS-355) |
| `fbs_kiz_service.py` | ✅ ветка Ozon в `_delete_sgtin_from_wb`, фото через Ozon-link |
| `fbs_marking_service.py` | ✅ `build_ozon_provider`, `sync_wb` только для WB-заказа |
| `fbs_order_billing_service.py` | ✅ `order_work_moment`, цикл по двум service_code, `document_number_snapshot` через `order_display_number` |
| `fbs_order_history_service.py` | ✅ добавлена `supply_history`, склейка событий, отдельная от `order_history` |
| `fbs_order_import_scope_service.py` | ✅ снят `pool_debit_totals` |
| `fbs_ozon_packaging_service.py` | ✅ `prepare_shipment_sources` разделяет сборку рецепта и списание; `write_off_order` теперь `first_movement_id` (см. R1.P1.1→P3) |
| `fbs_packing_box_service.py` | ✅ Ozon-позиции, `_assign_ozon_positions`, `_assert_ozon_orders_mutable` |
| `fbs_picking_service.py` | ✅ добавлен запасной поиск товара по штрихкоду маркетплейса |
| `fbs_print_asset_service.py` | 🟡 не читал — используется штатно с новыми путями Ozon |
| `fbs_print_asset_storage.py` | 🟡 не читал; ключевой момент — PDF-лист Ozon-передачи не сохраняется (`fbs_shipment_service._finish_ozon_delivery:614–624` явно логирует «нет PDF-поверхности») |
| `fbs_seller_warehouse_service.py` | 🟡 не читал полностью — `list_ozon_seller_warehouses` вызывается новой ручкой |
| `fbs_shipment_pvz_service.py` | ✅ проверка `is_wildberries(supply)` во всех PVZ-путях |
| `fbs_shipment_service.py` | ✅ прочитаны `_deliver_ozon_supply`/`_locked`/`_finish_ozon_delivery`, чекпойнты, snapshot всех попыток передачи |
| `fbs_shipment_source_service.py` | ✅ `initial_consumption` |
| `fbs_stock_availability_service.py` | ✅ `fbs_allocated_available_by_product`, `warehouse_id | None` |
| `fbs_stock_publish_service.py` | ✅ `drain_background_stock_publish_tasks` явно чистит `_BACKGROUND_TASKS` (мелочь) |
| `fbs_stock_rule_service.py` | ✅ collision по номерам складов на разных площадках, hidden_pools, обнуление только своих маркетплейсов |
| `fbs_stock_units_service.py` [DELETED] | ✅ подтверждено удаление всей журналирующей квоту логики |
| `fbs_supply_reconcile_service.py` | ✅ `list_deliver_operations_for_supply` |
| `fbs_supply_service.py` | ✅ снят авто-`boxes_without_distribution_at` для Ozon, `is_wildberries` в PATCH к WB |
| `fbs_warehouse_binding_service.py` | ✅ marketplace в get/upsert, `external_warehouse_id` |
| `fbs_worklist_service.py` | ✅ delivery_route для Ozon, brand/composition для этикетки, `image_url` из Ozon |
| `fbs_workspace_service.py` | ✅ `_compute_stage/_blockers`: правило «без блокеров» распространено на Ozon, `_unassigned_order_ids` для позиций Ozon |
| `inbound_intake_service.py` | 🟡 не читал — ссылка изменилась только на `build_ozon_provider` |
| `inventory_count_service.py` | ✅ `create_document_container`, `add_manual_line`, запасной поиск Ozon-штрихкода |
| `inventory_movement_report_service.py` | ✅ `load_report_photo_urls` с Ozon-фото |
| `inventory_service.py` | ✅ `update_fbs_order_reservation`, `_deduct_inventory_from_fbs`, `apply_fbs_supply_write_off` с fbs_order_id |
| `marketplace_account_service.py` | ✅ `live_exchange_enabled` |
| `marketplace_provider.py` | 🟡 не открывал полностью — базовые классы; расширения проверены через `ozon_marketplace_transport` |
| `marketplace_scope.py` [NEW] | ✅ `is_wildberries`, `order_display_number`, `wrong_marketplace_message` |
| `marketplace_unload_service.py` | ✅ снят blocked_ozon_dispatch fake, пакетное начисление за отгрузку+упаковку, локальное списание вместо мнимого HTTP |
| `operation_fact_service.py` | 🟡 не читал; `normalize_marketplace` проверен в `test_ozon_operator_surfaces` |
| `ozon_box_assembly_service.py` [NEW] | ✅ `assemble_box_order`, `_invalidate_old_label`, order_packages |
| `ozon_fbs_marking_gate_service.py` | ✅ `ozon_requirements_known` — гейт различает «маркировка не нужна» и «требования не разбирали» |
| `ozon_fbs_process_service.py` | ✅ `OzonHandoffProgress` (checkpoint + absorb), `handoff_supply` с чекпойнтом, `_finish_carriage_handoff` (см. R1.P2.1 корректировку и R1-A2) |
| `ozon_fbs_sync_service.py` | ✅ статусы/подстатусы, `_apply_delivery_method`, `_apply_requirements`, `_charge_confirmed_order`, `selected_posting_numbers` |
| `ozon_marketplace_transport.py` [NEW] | ✅ включая `_stock_item`, `_reconcile_stock_rows`, `fetch_orders`, `fetch_statuses`, `fetch_order_labels`, `publish_stocks`, `fetch_supply_qr` |
| `ozon_product_import_service.py` [NEW] | 🟡 контракт `find_product_ids_by_marketplace_barcode` проверен через использующих (`scan_resolver_service`, `fbs_picking_service`, `inventory_count_service`); импорт карточек полностью не читал |
| `ozon_provider_factory.py` [NEW] | ✅ `build_ozon_transport`, `build_ozon_provider`, `ozon_live_api_enabled` |
| `ozon_return_service.py` | ✅ `_decode_return_file`, защита от None-контента, `current_barcode` пустой ответ |
| `print_template_service.py` | ✅ `LabelOptions`, `set_seller_label_options`, `resolve_default_print_template` под рубильником `label_template_enabled` |
| `product_merge_service.py` [NEW] | ✅ (см. R1-A8) |
| `reporting_service.py` | ✅ `fbs_by_movement` (см. R1.P1.1→P3), `list_product_movements`, `opening_balance` |
| `scan_resolver_service.py` | ✅ запасной поиск Ozon-штрихкода |
| `seller_wb_catalog_service.py` | ✅ `_ozon_barcode_binding`, `ozon_link_primary_image_url` |
| `stock_direction_service.py` | ✅ `distributions_by_product` с fbs_allocated/reserved |
| `storage_daily_charge_service.py` [NEW] | ✅ `charge_storage_day`, `missing_charge_days` (см. R1.P2.5), `run_daily_storage_charge_all_tenants` |
| `storage_statement_service.py` | ✅ `get_storage_night_charges_batch`, `get_storage_statement_for_print` |
| `warehouse_map_service.py` | ✅ Ozon-фото на карте склада |
| `wb_marketplace_orders_service.py` | ✅ снят весь `pool_debit`, замена на `update_fbs_order_reservation`, `_apply_wb_status_to_order` вызывает `reverse_fbs_order_billing` |

### Backend / Models

| Файл | Статус |
|---|---|
| `fbs_binding_stock_pool.py` | ✅ удалён `allocated_at`, комментарий обновлён |
| `fbs_packing_box.py` | ✅ `Index uq_..._order_position`, `order_product_id` FK |
| `fbs_warehouse_binding.py` | ✅ `marketplace` часть уникального ключа |
| `inventory_count.py` | ✅ `InventoryCountCreatedContainer` |

### Backend / Schemas

| Файл | Статус |
|---|---|
| `ozon_fbs_api.py` | 🟢 сгенерированный по OpenAPI спецификации Ozon; проверил, что имена типов, использованные в `ozon_fbs_process_service` и `ozon_box_assembly_service`, соответствуют |

### Backend / Other

| Файл | Статус |
|---|---|
| `celery_app.py` | ✅ `moscow_now` модуль-уровневая функция, `crontab(hour=0, minute=0, nowfun=moscow_now)`, добавлен `billing-storage-daily` |
| `cli/reconcile_fbs_unlinked_shipments.py` | 🟡 не читал — CLI, редко используется |
| `core/settings.py` | ✅ `ozon_seller_api_base`, `label_template_enabled=False`, `ozon_live_api_enabled=False`, `ozon_api_timeout_sec=30.0` |
| `tasks/billing_tasks.py` | ✅ добавлен `run_billing_storage_daily_task`, старая `run_billing_invoices_daily_task` — no-op совместимости |
| `scripts/backfill_billing_charges.py` | 🟡 не читал — служебный скрипт |
| `scripts/backfill_fbs_order_facts.py` | 🟡 не читал — служебный скрипт |

### Backend / Migrations

| Файл | Статус |
|---|---|
| `20260903_0249_binding_marketplace_unique.py` | ✅ расширяет unique до тройки, безопасно |
| `20260903_0250_inventory_created_containers.py` | ✅ новая таблица под исключения прунинга |
| `20260904_0251_fbs_units_mode.py` | ✅ добавляет `Product.fbs_units_mode` и `FbsBindingStockPool.allocated_at` |
| `20260905_0252_fbs_available_stock.py` | ✅ преобразует накопленную квоту в текущий доступный остаток, сносит `allocated_at`; удерживает `remaining[key]` разделяемо между привязками, чтобы не переприписать физический остаток |
| `20260905_0253_merge_wms060_and_staging.py` | ✅ пустая merge-миграция — сводит две головы; корректно |
| `20260905_0254_fbs_box_order_positions.py` | ✅ `order_product_id` в `fbs_packing_box_items`, `coalesce`-индекс, downgrade заранее отказывается при существующих разложенных позициях; массовое зануление `boxes_without_distribution_at` только для Ozon |

### Docker / Инфраструктура

| Файл | Статус |
|---|---|
| `docker-compose.prod.yml` | ✅ пробрасывает `WMS_OZON_LIVE_API=false` во все три сервиса (WMS/worker/beat) |

### Frontend

| Файл | Статус |
|---|---|
| `App.tsx` | ✅ (мелкая правка импортов, не бизнес-логика) |
| `components/MarkingLabelPreview.tsx` | 🟡 не читал полностью — предпросмотр, ключевые поля проверены через передачу `printOptions` |
| `components/MarkingPrintDialog.tsx` | ✅ выбор Ozon/WB штрихкода, `resolveProductTapeBarcodeError`, применение `label_options` из шаблона |
| `components/ProductBarcodePrintButton.tsx` | ✅ подсказка «Печать ЧЗ и ШК товара» для Ozon-товара |
| `components/ProductBarcodePrintDialog.tsx` | ✅ подтягивание `label_options` через `resolvePrintTemplate`; смонтирован в `SellerInboundDraftScreen` — действующий путь |
| `components/fbs/FbsChips.tsx` | 🟡 не читал — мелкие правки |
| `content/knowledge/*.md` | 🟢 контент |
| `screens/ff/FfBillingInvoiceCreate.tsx` | 🟡 не читал полностью — крупные правки под `include_storage` и `manual_lines` |
| `screens/ff/FfBillingScreen.tsx` | 🟡 не читал (главный экран); экспорт `sellerQuickRange` используется в отчётах |
| `screens/ff/FfBillingSellerDetails.tsx` | 🟡 не читал полностью — правки под `billing_ledger_entry_id` и упаковку |
| `screens/ff/FfBillingTariffMatrixPanel.tsx` | 🟡 не читал — сервис проверен |
| `screens/ff/FfDashboard.tsx` | 🟡 не читал |
| `screens/ff/FfLabelTemplatePanel.tsx` [NEW] | 🟡 не читал — рубильник выключен, панель на бою не влияет на печать |
| `screens/ff/FfPackagingPage.tsx` | 🟡 не читал полностью — использует `MarkingPrintDialog` |
| `screens/ff/FfReportsPage.tsx` | ✅ добавлен третий уровень (движения), группировка `product` по умолчанию |
| `screens/ff/FfSettingsScreen.tsx` | 🟡 не читал полностью — панель настроек хранения/этикетки |
| `screens/ff/FfStoragePage.tsx` | 🟡 не читал полностью — переключение на ночные начисления |
| `screens/ff/billing-sections-preview.tsx` | 🟡 не читал (preview-компонент) |
| `screens/ff/inventory/FfInventoryCountScreen.tsx` | 🟡 не читал полностью — использование `manual_line` |
| `screens/ff/inventory/FfInventoryPage.tsx` | ✅ каталог для «Добавить товар», `createCountContainer` |
| `screens/ff/inventory/InventoryCountDialog.tsx` | 🟡 не читал |
| `screens/ff/inventory/InventoryTree.tsx` | 🟡 не читал полностью — дерево с исключениями прунинга |
| `screens/ff/inventory/foundQueue.ts` | 🟡 не читал полностью |
| `screens/ff/inventory/inventoryCountApi.ts` | 🟡 не читал полностью — API-обёртки |
| `screens/ff/products-fbs/FbsStockDialog.tsx` | ✅ прочитан в R1 |
| `screens/ff/products-fbs/FfProductsFbsPage.tsx` | 🟡 не читал |
| `screens/ff/products-fbs/stub.ts` | 🟡 не читал (моки) |
| `screens/v2/FbsOrderHistoryDialog.tsx` [DELETED] | ✅ подтверждено удаление, замещён `FbsSupplyHistoryDialog` |
| `screens/v2/FbsPrintPreviewDialog.tsx` | 🟡 не читал полностью — превью печати |
| `screens/v2/FbsSupplyHistoryDialog.tsx` [NEW] | 🟡 не читал (211 строк UI-диалога, сервер `supply_history` проверен) |
| `screens/v2/FfFbsOrdersScreen.tsx` | ✅ отмена Ozon-заказа, delivery_route |
| `screens/v2/FfFbsStockSyncScreen.tsx` | ✅ тексты ошибок ozon_stock_* |
| `screens/v2/FfFbsSupplyWorkspace.tsx` | ✅ ветки Ozon в create/assign/remove коробов, retry_qr для Ozon, история поставки |
| `screens/v2/FfProductsCatalogScreen.tsx` | ✅ merge-диалог, `marketplaces[]`, Ozon-warehouses |
| `screens/v2/SellerInboundDraftScreen.tsx` | ✅ проверен как точка монтирования `ProductBarcodePrintDialog` |
| `screens/v2/SellerSettingsScreen.tsx` | 🟡 не читал полностью |
| `screens/v2/fbs-history-preview.tsx` [DELETED] | ✅ подтверждено удаление |
| `screens/v2/fbsApi.ts` | ✅ `cancelFbsOrder`, `order_product_ids` в assign/remove |
| `screens/v2/fbsUx.ts` | ✅ снят `marketplace === 'ozon'` из блокираторов, единое правило для WB и Ozon |
| `types/wbProductCatalog.ts` | ✅ `resolveProductBarcodeOptions`, `resolveProductBarcodeSelection` |
| `ui-kit/DataTable.tsx` | 🟡 не читал |
| `utils/markingPrintPresets.ts` | ✅ `tapeToLayout(tape, labelOptions)`, `cloneLayout` сохраняет `label_options` |
| `utils/printMarkingCodeLabel.ts` | 🟡 не читал полностью — `labelOptionsFromLayout` экспортируется и используется |
| `utils/printTemplate.ts` | 🟡 не читал полностью — `resolvePrintTemplate`, `PrintLabelOptions` типы |
| `utils/productBarcodePrint.ts` | ✅ `displayMetaToProductLabel` без fallback на sku_code |
| `utils/productLabelText.ts` | ✅ добавлены `includeColor`, `includeBrand` |
| `utils/readApiErrorMessage.ts` | 🟡 не читал — мелкая правка |
| `utils/useFfProductMarkingPrint.tsx` | ✅ `productBarcodeOptions` для Ozon-линкованных карточек |

### Прочее

| Файл | Статус |
|---|---|
| `AGENTS.md`, `CLAUDE.md`, `.gitignore`, `.github/workflows/ci.yml` | 🟢 инструкции/инфраструктура, не приложение |
| `scripts/ci/check-backlog-ref.sh` [NEW] | ✅ гейт CI на упоминание задачи в бэклоге |
| `scripts/generate_ozon_fbs_api_md.py`, `scripts/generate_ozon_fbs_models.py` | 🟡 не читал (генераторы моделей из OpenAPI) |
| `tasks/*.md`, `tasks/_zhurnal/*.md`, `tasks/fbs-operator-flow/**`, `tasks/ozon-integration-20260825/**` | 🟢 документы задач/спецификация Ozon |

## 5. Что действительно требует живой проверки в браузере/на бою

- Кнопка «Отменить в Ozon» на экране заказов (`FfFbsOrdersScreen.tsx:1786–1792`) при выключенном `WMS_OZON_LIVE_API=false` должна вернуть 503 «ozon_live_cancel_blocked» с внятным текстом («Отмена в Ozon выключена настройкой»). Проверить, что 503 показан алертом, а не молча пропущен.
- Кнопка «QR короба» у поставки Ozon в рабочем месте (`FfFbsSupplyWorkspace.tsx:875–878`): при выключенном live-режиме `retry_box_qr → assemble_box_order` бросает `ozon_live_handoff_blocked` (`ozon_box_assembly_service.py:170–176`). Убедиться, что оператор видит причину.
- Модалка «Задать остаток» для товара, у которого есть привязки WB и Ozon, — открыть, сохранить процент, переключить в штуки, сохранить выключенную трансляцию. `set_rule_for_products` теперь распоряжается только теми маркетплейсами, чьи склады перечислены; проверить, что сохранение правила Wildberries не стирает штучное выделение Ozon (это как раз WMS-342, о которую обожглись в аварии 04.09).
- Печать этикетки товара в `SellerInboundDraftScreen` для товара с ozon-привязкой — правильный ли ШК приходит (`resolveProductBarcodeOptions` → `MarkingPrintDialog` → `printProductThermalLabels`).
- Отчёт «Движения» на живом Ozon-заказе из двух позиций — вторая и третья строки движений должны показывать «Заказ №…» из ledger (см. R1.P1.1→P3): по одной строке будет документ, по двум остальным — «нет документа». Симптом косметический, но виден.
- Хронология поставки FBS: клик «История поставки» из состава поставки открывает диалог `FbsSupplyHistoryDialog`, ручка `/operations/fbs-supplies/{id}/history` возвращает склеенные события `supply_history`. Проверить, что склейка «печать 40 стикеров» приходит одной строкой с количеством.
- Ночное начисление хранения за 05.09 — файлы `charge_storage_day` пишут строки по каждому товару. Экран хранения теперь читает `get_storage_night_charges_batch`, суммы должны совпадать копейка в копейку с последующим счётом (`billing_invoice_v2_service._storage_line`).

## 6. Прежние P1 из брифа — статус подтверждён

Все три исправления, о которых говорил бриф, остались на месте, я перечитал их повторно:

- **Публикация выше физического остатка**: `fbs_stock_rule_service.split_amounts` (`279–290`) ограничивает `amount = min(share, remaining)`, `remaining = max(free_stock, 0)`, каждая привязка отрезает от общего. Плюс явная валидация `warehouse_id_collision` (`480–500`), `units_sum_exceeded` (`567–575`) на вводе правила.
- **Зависший pending передачи Ozon после restart, невозможность повторить ship_failed**: `_deliver_ozon_supply` (`fbs_shipment_service.py:1799–1907`) собирает `progress` по ВСЕМ попыткам поставки (не только по текущему `idempotency_key`), сохраняет прогресс в чекпойнт до любой мутации, при отказе `_finish_ozon_delivery` вызывает `_fail_ozon_deliver_operation(discard_local_changes=True)` — операция не остаётся навсегда в PENDING. `assemble_box_order` (`ozon_box_assembly_service.py:194–207`) при `substatus == "ship_failed"` очищает `ASSEMBLY_KEY` и разрешает повторную сборку.
- **Beat pickle lambda**: `celery_app.py:11–14` — модуль-уровневый `moscow_now`, тест `test_celery_schedule_persistence.py` явно проверяет `pickle.loads(pickle.dumps(beat_schedule))`.

## 7. Что осталось непрочитанным и почему

- **Frontend**: 21 файл (см. таблицу) — в основном UI-детали экранов (`FfBilling*`, `FfInventory*`, `FfPackagingPage`), которые не участвуют в путях «деньги/остаток/передача». Для доказательства регрессий на бою здесь нужна браузерная проверка, а не чтение.
- **Backend вспомогательное**: `fbs_print_asset_service/storage`, `fbs_seller_warehouse_service`, `inbound_intake_service`, `marketplace_provider`, `operation_fact_service`, `billing_tariff_matrix_service`, `ozon_product_import_service` (полностью) — либо тонкие обёртки, либо не пересекаются с изменёнными путями критично. Контракты этих модулей проверены через вызывающих.
- **Служебные скрипты и CLI** (`cli/reconcile_*`, `scripts/backfill_*`) — не бой.
- **Сгенерированные схемы Ozon** (`schemas/ozon_fbs_api.py`, `scripts/generate_*.py`) — контракты типов и их использование проверены через `ozon_fbs_process_service` и `ozon_box_assembly_service`.

Я не заявлял, что «в бою всё работает», и не заменяю живую проверку словами «проверено тестами». Заявляю ровно то, что доказано чтением: путь A вызывает B, B возвращает C, C сохраняется в поле D, поле D читается в E. Если оркестратор увидит расхождение — оно проверяется на боевом стенде, а не переопределяется этим отчётом.
