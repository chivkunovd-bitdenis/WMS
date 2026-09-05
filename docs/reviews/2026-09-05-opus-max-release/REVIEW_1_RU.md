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
