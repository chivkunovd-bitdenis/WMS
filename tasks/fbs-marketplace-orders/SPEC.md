# SPEC — модуль FBS (Wildberries «Маркетплейс») для WMS

> **⚠️ DEPRECATED (FBSFLOW-130, 2026-08-03):** ранний тех-спек до `tasks/fbs-operator-flow/`.  
> **Актуально:** `tasks/fbs-operator-flow/BACKEND_CONTRACT.md`, `FRONTEND_TASKS.md`, `ERROR_CATALOG.md`, `OPENAPI.md`.  
> **Не использовать в новом frontend:** `sticker_file`/`barcode_file` как API-поля; обязательный bind order→trbx; add-one-order вместо batch `from-orders`.  
> Исторический текст ниже сохранён для трассировки решений.

> Тех-спек по стадии 1–2. Источники: `wb-docs/_CONSOLIDATED_FBS_SPEC.md` (процесс WB), `api-feasibility.md`
> (что умеет API). Принцип: **повторяем WB один-в-один**, отличаемся только там, где диктует наша специфика
> (мультиселлер + свой модуль упаковки). Точные имена эндпоинтов v3 — сверить с `dev.wildberries.ru`
> (помечено ⚠️), это не блокирует проектирование.

## 1. Скоуп
- **Только Wildberries**, схема «Маркетплейс» (FBS). Полный цикл по API из WMS.
- Мультиселлер: каждый селлер фулфилмента = свой WB-токен → свой склад продавца → свои заказы/поставки.
- Вне скоупа v1: Ozon/Яндекс; посылки-группировка одного покупателя (у WB отключена); претензии покупателя.

## 2. Доменная модель (новые таблицы, конвенции как в `marketplace_unload`)

**`fbs_order`** — сборочное задание (1 заказ WB = 1 товар):
`id`(uuid pk), `tenant_id`, `seller_id`, `warehouse_id`(наш склад ФФ), `product_id`(маппинг по баркоду/nmId),
`wb_order_id`(int, uniq в рамках seller), `wb_rid`, `wb_nm_id`, `wb_chrt_id`, `wb_article`, `wb_barcode`,
`price`, `is_legal`(юрлицо), `cargo_type`(mgt|kgt|sgt), `wb_office_id`(склад продавца/зона WB),
`can_pvz`(bool), `supply_id`(fk→fbs_supply, nullable), `trbx_id`(fk→fbs_trbx, nullable),
`status`(см. §3), `wb_status`(кэш статуса WB), `created_at_wb`, `deadline_at`(created_at_wb + 120ч),
`sticker_code`/`sticker_file`(кэш стикера заказа), `created_at`, `updated_at`.

**`fbs_order_marking`** — идентификаторы на заказ (КИЗ/УИН/IMEI/GTIN, их может быть >1):
`id`, `order_id`(fk), `kind`(sgtin|uin|imei|gtin), `value`, `check_status`(new|checking|ok|error|no_check),
`marking_code_id`(fk→существующий `marking_code`, для КИЗ). Связь с нашим модулем ЧЗ.

**`fbs_supply`** — отгрузка (WB supply):
`id`, `tenant_id`, `seller_id`, `warehouse_id`, `wb_supply_id`(str, напр. `WB-GI-123`), `name`,
`status`(см. §3), `delivery_type`(warehouse_sc|pvz), `cargo_type`, `wb_office_id`,
`barcode_file`(кэш QR поставки), `document_number`, `display_number`,
`created_at_wb`, `delivered_at`, `created_at`, `updated_at`.

**`fbs_trbx`** — грузоместо (только поток ПВЗ; = наш короб упаковки):
`id`, `supply_id`(fk), `wb_trbx_id`, `packaging_box_id`(fk→существующий короб упаковки, nullable),
`sticker_file`(кэш QR грузоместа), `created_at`.

> `fbs_order_line` не заводим: заказ WB — всегда один товар, `product_id`+`quantity` кладём на сам заказ.

## 3. Жизненный цикл (статусы — зеркалим WB)

**Заказ (`fbs_order.status`):**
`new` (пришёл, зарезервирован) → `in_supply` (добавлен в отгрузку) → `assembling` (сборка) →
`packed` (собран+упакован, маркировка внесена) → `in_delivery` (отгрузка передана) →
`sorted` (отсортирован на WB) → `done` (выкуплен/отказ) · терминально `cancelled`.
Отдельно кэшируем `wb_status` (waiting/sorted/sold/canceled/declined_by_client/defect…) из синка статусов.

**Отгрузка (`fbs_supply.status`):** `draft` (создана, наполняется) → `assembling` → `in_delivery`
(передана в доставку) → `done`. Пустую можно удалить.

## 4. Маппинг на WB Marketplace API v3 (⚠️ пути сверить)
| Операция в WMS | WB API |
|---|---|
| Опрос новых заказов | `GET /api/v3/orders/new` |
| Список/пагинация заказов | `GET /api/v3/orders` |
| Синк статусов | `POST /api/v3/orders/status` |
| Отмена заказа | `PATCH /api/v3/orders/{id}/cancel` |
| Стикер заказа (на товар) | `POST /api/v3/orders/stickers?type=png&width=58&height=40` |
| КИЗ/идентификаторы | `PUT /api/v3/orders/{id}/meta/{sgtin\|uin\|imei\|gtin}` |
| Создать отгрузку | `POST /api/v3/supplies` |
| Добавить заказ в отгрузку | `PATCH /api/v3/supplies/{sid}/orders/{oid}` |
| QR поставки | `GET /api/v3/supplies/{sid}/barcode?type=png` |
| Передать в доставку | `PATCH /api/v3/supplies/{sid}/deliver` |
| Грузоместа (ПВЗ) | `POST /api/v3/supplies/{sid}/trbx`, `PATCH …/trbx/{tid}` |
| QR грузомест | `POST /api/v3/supplies/{sid}/trbx/stickers?type=png` |
| Склады продавца / зоны | `GET /api/v3/warehouses`, `GET /api/v3/offices` |
| Остатки | `PUT /api/v3/stocks/{warehouseId}` |

## 5. Автоопрос заказов (постоянный, per-seller)
- Фоновый job на каждый селлер с валидным WB-токеном (категория «Маркетплейс»). Интервал — конфиг
  (старт: раз в ~2–5 мин; учесть лимиты WB — сверить ⚠️).
- Шаги цикла: `GET /orders/new` → **upsert по `wb_order_id`** (идемпотентно, без задвоения) → маппинг
  товара по `wb_barcode`/`wb_nm_id` → **резерв остатка** (`inventory_reservation`) → `deadline_at`.
- Отдельный синк статусов активных заказов (`POST /orders/status`) — ловим отмены покупателем/сортировку.
- Нулевой остаток: заводим с пометкой (как WB «товара нет в наличии»), резерв не встаёт.
- Опционально (дёшево): кнопка «Синхронизировать сейчас» — тот же сервис вручную.

## 6. Стык с существующими модулями
- **Резерв/остатки:** `inventory_reservation` — резерв при заведении заказа, снятие при отмене, списание
  при отгрузке. Один физический товар не должен резервироваться одновременно под FBS и ФБО.
- **Упаковка:** переиспользуем `packaging_task`. Поток **ПВЗ**: наш короб ↔ `fbs_trbx`, печатаем
  **WB-QR грузоместа** (иначе не примут). Поток **склад/СЦ**: упаковка внутренняя, WB нужен только QR
  поставки + стикеры заказов; наши этикетки коробов — для своего учёта.
- **Честный Знак:** существующий `marking_code`/модуль ЧЗ → пушим КИЗ per-order (`meta/sgtin`) до deliver;
  храним `check_status` (WB сам гоняет проверку).
- **Печать/ТСД:** стикеры заказов (58×40), QR поставки, QR грузомест тянем из WB и печатаем через
  конструктор печати и на ТСД. Лист подбора — свой (строим из состава отгрузки).
- **`marketplace_unload` (ФБО):** не трогаем, FBS — параллельный домен.

## 7. Два потока отгрузки (повторяем WB)
- **Склад/СЦ:** создать отгрузку → наполнить заказами → маркировка+упаковка → передать в доставку →
  QR поставки → отвезти. Грузоместа необязательны.
- **ПВЗ:** то же + обязательные **грузоместа** (trbx) с QR на каждый короб; ограничения короба
  (≤60×40×40, ≤5 кг, >1 заказа в коробе, объём ≤1 м³).

## 8. Разбивка `L` на под-задачи (каждая — свой `tasks/<slug>/` + вертикальный срез + PR)
1. **`fbs-orders-intake`** — модели + миграция + WB-клиент (чтение заказов) + автоопрос + резерв + маппинг товара. *(ядро, главный риск — начинаем отсюда)*
2. **`fbs-supply-assembly`** — создать/наполнить отгрузку, свой лист подбора, сборка, стикеры заказов (pull+print).
3. **`fbs-marking`** — КИЗ/идентификаторы per-order по API + связка с модулем ЧЗ + статусы проверки.
4. **`fbs-shipment-warehouse-sc`** — deliver + QR поставки + статусы/чек-лист.
5. **`fbs-shipment-pvz`** — грузоместа (trbx) + QR грузомест + deliver + ограничения.
6. **`fbs-cancellations`** — отмена/синк статусов/возвраты (раздел 06 WB).
7. **`fbs-frontend`** — экраны как у WB (Новые / На сборке / В доставке / Завершённые), MUI.
8. **`fbs-tsd`** — сборка на ТСД + печать стикеров.
9. **`fbs-seller-warehouse-token`** — склад продавца (officeId) + категория токена «Маркетплейс».

## 9. Открытые вопросы (сверить дёшево после сброса лимита WebFetch)
1. Точные пути/поля v3 (`meta/sgtin`, `trbx/stickers`, `deliver`, формат `orders/new`).
2. Вебхук на новые заказы или только поллинг; лимиты запросов (частота опроса).
3. Категория «Маркетплейс» на живом `supplies_token` или отдельное поле `marketplace_token`.
4. Точный набор `wb_status` для синка (для колонки «Завершённые» и таймеров).
