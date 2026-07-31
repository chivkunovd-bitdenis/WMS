# TASK — fbs-shipment-pvz: отгрузка в ПВЗ с грузоместами

- **Эпик:** FBS — см. `../fbs-marketplace-orders/SPEC.md`. Гейт 1 эпика ✅ (арх-курс утверждён), под-задача наследует.
- **Тип / размер:** feature / M
- **Зависит от:** fbs-orders-intake, fbs-supply-assembly, fbs-marking, fbs-shipment-warehouse-sc
- **Слои:** backend: models + services / api

## Описание (для Composer)

Специфичный поток в ПВЗ: создаём грузоместа (trbx — наши коробки упаковки), получаем QR-коды каждого короба, соблюдаем ограничения (≤60×40×40, ≤5 кг, >1 заказа, объём ≤1 м³). Интегрируемся с существующим модулем упаковки через `packaging_box`. WB требует QR-коды грузомест (иначе в ПВЗ не примут). Процесс: создаём grузоместа → печатаем QR каждого → deliver (как в warehouse-sc).

## Scope

- Модель `fbs_trbx` (supply_id fk, wb_trbx_id, packaging_box_id fk, sticker_file)
- Endpoint POST создания грузомест (указываем кол-во → WB создаёт + возвращает список)
- Endpoint PATCH добавления заказов в грузоместо (PATCH /supplies/{sid}/trbx/{tid})
- Получение QR-кодов грузомест (POST /trbx/stickers) — batch
- Валидация ограничений: габариты, вес, объём
- Интеграция с `packaging_task`/`packaging_box`: привязка коробки к trbx

## Out of scope

- Складская/СЦ-отгрузка (задача fbs-shipment-warehouse-sc)
- Фронтенд-экраны
- ТСД

## Арх-подход (из утверждённого SPEC)

- **Модель:** `fbs_trbx` (id uuid pk, supply_id fk→fbs_supply, wb_trbx_id str, packaging_box_id fk→packaging_box nullable, sticker_file nullable).
- **Сервис:** `WBShipmentPVZService` (создание trbx, добавление заказов, валидация ограничений, скачивание QR).
- **Endpoints:**
  - POST `/api/fbs/supplies/{supply_id}/trbx` {count: N} — создаёт N грузомест через WB API, возвращает список wb_trbx_id
  - PATCH `/api/fbs/supplies/{supply_id}/trbx/{trbx_id}/orders` {order_ids: [...]} — добавляет заказы в грузоместо
  - POST `/api/fbs/supplies/{supply_id}/trbx/stickers?type=png` — batch-запрос QR для всех trbx в supply
- **WB API:** POST `/api/v3/supplies/{sid}/trbx`, PATCH `/api/v3/supplies/{sid}/trbx/{tid}`, POST `/api/v3/supplies/{sid}/trbx/stickers?type=...`. ⚠️ Сверить с `dev.wildberries.ru`.
- **Валидация:**
  - Коробка ≤60×40×40 см (любая сторона)
  - Вес ≤5 кг
  - >1 заказа в коробе (исключение: крупный товар → на склад)
  - Объём всех trbx в supply ≤1 м³
- **Файлы:** backend/app/models/fbs_models.py, backend/app/services/fbs_shipment_pvz.py, backend/app/api/fbs_shipment_pvz.py.
- Связь с упаковкой: `packaging_box_id` → габариты/вес берём оттуда.

## Критерии приёмки (DoD)

- [ ] Модель `fbs_trbx` создана, миграция применена
- [ ] Endpoint POST создания trbx — вызывает WB API, сохраняет wb_trbx_id, возвращает список
- [ ] Endpoint PATCH добавления заказов — вызывает WB API, проверяет ограничения (кол-во, вес, габариты)
- [ ] QR-коды trbx: batch-запрос к WB, сохранение PNG, кэш в sticker_file
- [ ] Валидация: 60×40×40, ≤5 кг, >1 заказа, объём ≤1 м³
- [ ] Интеграция с `packaging_box`: габариты/вес берутся из коробки, packaging_box_id заполняется
- [ ] Deliver для ПВЗ: как в warehouse-sc (все trbx должны быть заполнены перед deliver)
- [ ] CI зелёный

## Test coverage (копируется в описание PR)

| TC-ID | Title (short) | Applies (Y/N) | Notes |
|-------|---------------|---------------|-------|
| TC-NEW-FBS-SHIPPVZ-001 | Создание грузомест | Y | Given: supply для ПВЗ, 3 заказа МГТ / When: POST /supplies/{sid}/trbx {count: 2} / Then: WB API создал 2 grузоместа, возвращены wb_trbx_id; negative: supply не для ПВЗ → 400 |
| TC-NEW-FBS-SHIPPVZ-002 | Добавление заказов в trbx | Y | Given: grузоместо создано, 2 заказа МГТ по 2 кг каждый / When: PATCH /trbx/{tid}/orders {order_ids: [1,2]} / Then: заказы добавлены; negative: вес >5 кг → 400 валидации |
| TC-NEW-FBS-SHIPPVZ-003 | Валидация габаритов | Y | Given: коробка 60×40×40 см ровно, вес 5 кг / When: добавление заказа / Then: OK; negative: коробка 61×40×40 → 400 |
| TC-NEW-FBS-SHIPPVZ-004 | Получение QR грузомест | Y | Given: 2 trbx в supply / When: POST /supplies/{sid}/trbx/stickers?type=png / Then: 2 PNG-файла, кэшированы в sticker_file; negative: WB ошибка → повтор |

## Где тесты

- backend: `cd backend && pytest tests/test_fbs_shipment_pvz.py`.

## Гейт перед PR

- `cd backend && ruff check . && mypy . && pytest`
