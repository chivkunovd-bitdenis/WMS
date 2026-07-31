# TASK — fbs-supply-assembly: создание и наполнение отгрузок

- **Эпик:** FBS — см. `../fbs-marketplace-orders/SPEC.md`. Гейт 1 эпика ✅ (арх-курс утверждён), под-задача наследует.
- **Тип / размер:** feature / M
- **Зависит от:** fbs-orders-intake ✅
- **Слои:** backend: models + db (alembic) / services / api / tasks

## Описание (для Composer)

Создаём поставки (supply) в WB и наполняем их заказами. Строим свой лист подбора по составу отгрузки. Координируем сборку и печать стикеров заказов (pull+print). Модель `fbs_supply` отражает состояние WB-отгрузки (draft → assembling → in_delivery → done). Интегрируемся с существующим модулем упаковки через `packaging_task`.

## Scope

- Модель `fbs_supply` (seller_id, warehouse_id, wb_supply_id, name, status, delivery_type, cargo_type, barcode_file)
- Эндпоинты: создание supply по API, добавление заказов (PATCH), получение листа подбора
- Лист подбора: свой (UI-фича), строим из состава отгрузки (группировка по артикулу/цвету/размеру)
- Печать стикеров заказов: тянем из WB API (POST /orders/stickers), печатаем через конструктор
- Интеграция с `packaging_task`: отмечаем заказы как assembled/packed

## Out of scope

- ПВЗ-специфичные грузоместа (trbx) — задача fbs-shipment-pvz
- Маркировка КИЗ (задача fbs-marking)
- Передача в доставку (задача fbs-shipment-warehouse-sc)
- Фронтенд-экраны
- ТСД/печать на ТСД

## Арх-подход (из утверждённого SPEC)

- **Модель:** `fbs_supply` (uuid pk, seller_id, warehouse_id, wb_supply_id str, name, status=draft, delivery_type=warehouse_sc|pvz, cargo_type, barcode_file).
- **Сервис:** `WBSupplyAssemblyService` (создание supply по API `POST /api/v3/supplies`, добавление заказов `PATCH /api/v3/supplies/{sid}/orders/{oid}`, смена статуса).
- **Лист подбора:** endpoint `GET /api/fbs/supplies/{supply_id}/picking-list` — возвращает JSON с группировкой товаров (артикул → цвет → размер → кол-во).
- **Стикеры:** вызов `POST /api/v3/orders/stickers?type=png&width=58&height=40` для batch заказов, сохранение файлов, интеграция с конструктором печати.
- **Эндпоинты WB API:** POST `/api/v3/supplies` (создание), PATCH `/api/v3/supplies/{sid}/orders/{oid}` (добавление заказа). ⚠️ Сверить с `dev.wildberries.ru`.
- **Файлы:** backend/app/models/fbs_models.py, backend/app/services/fbs_supply.py, backend/app/api/fbs_supplies.py, backend/app/tasks/fbs_assembly.py.
- Связь с `packaging_task`: при переходе заказа в status=assembling/packed обновляем поле в `packaging_task`.

## Критерии приёмки (DoD)

- [ ] Модель `fbs_supply` создана, миграция применена
- [ ] Endpoint POST создания supply — вызывает WB API, сохраняет в БД
- [ ] Endpoint PATCH добавления заказов в supply — вызывает WB API, переводит заказ в status=in_supply
- [ ] Лист подбора JSON — группировка по артикулу/цвету/размеру с кол-вом
- [ ] Стикеры: batch-запрос к WB, сохранение PNG, возвращение кэшированных файлов (Column sticker_file в fbs_order)
- [ ] Интеграция с `packaging_task`: заказы отмечаются как assembling/packed
- [ ] Статусы supply: draft → assembling → in_delivery → done (из SPEC §3)
- [ ] CI зелёный

## Test coverage (копируется в описание PR)

| TC-ID | Title (short) | Applies (Y/N) | Notes |
|-------|---------------|---------------|-------|
| TC-NEW-FBS-SUPPLY-001 | Создание пустой supply | Y | Given: селлер, warehouse, delivery_type=warehouse_sc / When: POST /supplies / Then: wb_supply_id получен, статус=draft, объект в БД; negative: ошибка WB → exception, rollback |
| TC-NEW-FBS-SUPPLY-002 | Добавление заказа в supply | Y | Given: supply в статусе draft, заказ в статусе new / When: PATCH /supplies/{sid}/orders/{oid} / Then: заказ перейдёт в статус in_supply, supply вернёт список заказов; negative: заказ уже в другой supply → error |
| TC-NEW-FBS-SUPPLY-003 | Лист подбора (группировка) | Y | Given: supply с 5 заказами разных артикулов (2 шт одного артикула) / When: GET picking-list / Then: JSON содержит группировку, кол-во 2 для одной группы; negative: пустая supply → пустой список |
| TC-NEW-FBS-SUPPLY-004 | Печать стикеров batch | Y | Given: supply с 3 заказами / When: POST /supplies/{sid}/print-stickers / Then: стикеры тянуты из WB, PNG-файлы кэшированы; negative: WB вернул ошибку → повтор по retry-логике |

## Где тесты

- backend: `cd backend && pytest tests/test_fbs_supply_assembly.py`.

## Гейт перед PR

- `cd backend && ruff check . && mypy . && pytest`
