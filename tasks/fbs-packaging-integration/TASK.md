# TASK — fbs-packaging-integration: стык FBS-отгрузки с модулем упаковки

- **Эпик:** FBS — см. `../fbs-marketplace-orders/SPEC.md` и `DESIGN.md`. Гейт 1 эпика ✅, под-задача наследует.
- **Тип / размер:** feature / M
- **Зависит от:** `fbs-orders-intake`, `fbs-supply-assembly` (модели FbsSupply, FbsOrder, базовые эндпоинты должны быть готовы)
- **Слои:** backend: `app/services/fbs_supply_service.py`, `fbs_shipment_service.py`, `fbs_shipment_pvz_service.py`, `packaging_task_service.py`, `app/models/fbs_supply.py`

## Описание (для Composer)

Интеграция между FBS-отгрузкой и нашим модулем упаковки (`packaging_task`). При переходе отгрузки в статус **«assembling»** система должна автоматически создавать и линковать `PackagingTask`. Для потока **ПВЗ** наши коробки упаковки маппируются на WB-грузоместа (`fbs_trbx`), а печать идёт по WB-QR грузомест.

Две ключевые операции:
1. **При старте сборки:** создать упаковочное задание (одно на всю отгрузку), добавить линии по составу заказов
2. **Для ПВЗ-потока:** при упаковке → маппировать наш короб на `fbs_trbx`, привязать КИЗ/маркировку

**Переиспользуемое:**
- Существующий `PackagingTask`, `PackagingTaskLine` (статусы, логика прогресса)
- Существующий модуль резервирования и снятия со склада (inventory_service)
- Обход маршрута: отгрузка → заказы → товары с количеством → строки упаковочного задания

## Scope
- При создании отгрузки или явном переводе в **assembling** → создавать `PackagingTask` с привязкой `fbs_supply_id`
- Структура линий упаковочного задания: один товар из отгрузки → одна или несколько строк (по товарам, не по физическим коробкам)
- Для ПВЗ-потока: при упаковке (статус линии → packed) маппировать на `fbs_trbx` и сохранять `packaging_box_id`
- Синхронизация статусов: если упаковка завершена → отгрузка переходит в статус **packed** (если не требуется маркировка) или **in_delivery** (если маркировка завершена)
- CRUD для привязки коробки упаковки → грузоместо (эндпоинт `POST /operations/fbs-supplies/{id}/trbx/bind-box`)

## Out of scope
- Логика самого модуля упаковки (PackagingTask уже существует)
- Физический процесс комплектации на ТСД (отдельная фаза)
- Откаты и переделки (если отгрузка отменена, упаковка её тоже; деталь реализации)

## Арх-подход (реальные ручки/файлы)

**Backend:**
- **Модель:** добавить в `FbsSupply` (или новую таблицу связи):
  - `packaging_task_id: UUID | None` (FK → `packaging_tasks.id`) — основная отгрузка связана с одним заданием
  - Индекс на (tenant_id, packaging_task_id)
  
- **Модель:** расширить `FbsTrbx`:
  - `packaging_box_id: UUID | None` (FK → наша таблица коробок упаковки, если она есть)
  - Или просто сохранять логику в сервисе (зависит от существующей структуры)

- **Сервис:** `fbs_supply_service.py`:
  - Функция `create_packaging_task_for_supply(session, tenant_id, supply_id)` → PackagingTask + строки
  - Вызывается при переводе отгрузки в assembling или явно после создания отгрузки
  - Строки: для каждого заказа в отгрузке (group by product_id) → линия упаковки

- **Сервис:** `fbs_shipment_pvz_service.py`:
  - Функция `bind_packaging_box_to_trbx(session, tenant_id, supply_id, trbx_id, packaging_box_id)` → обновить fbs_trbx
  - При этом обновить и наш модуль упаковки (если требуется)

- **API:** добавить эндпоинты в `fbs_supplies.py`:
  - `POST /operations/fbs-supplies/{id}/trbx/bind-box` (body: trbx_id, packaging_box_id) → FbsTrbxOut

**Интеграционные точки:**
- При `PUT /operations/fbs-supplies/{id}/status` → if status == "assembling" → `create_packaging_task_for_supply()`
- При завершении упаковочного задания (signal/callback) → если all lines packed → отгрузка status = "packed"

## Критерии приёмки (DoD)

- [ ] Добавлено поле `packaging_task_id` на `FbsSupply` с миграцией БД
- [ ] При переводе отгрузки в assembling создаётся PackagingTask с корректным составом (товары из заказов)
- [ ] Для ПВЗ: эндпоинт bind-box успешно маппирует коробку на грузоместо
- [ ] Статус отгрузки синхронизируется при завершении упаковки (packed)
- [ ] Тесты: создание задания, добавление линий, маппинг коробок, синхронизация статусов

## Test coverage (в описание PR — требование CI)

| TC-ID | Title | Applies (Y/N) | Notes |
|-------|-------|---------------|-------|
| TC-NEW-FBS-PACKINT-001 | Создание упаковочного задания при старте сборки | Y | Given: отгрузка с 3 заказами (товары A, B, A) / When: статус → assembling / Then: создан PackagingTask, 2 линии (A×2, B×1), packaging_task_id привязан к отгрузке |
| TC-NEW-FBS-PACKINT-002 | Маппинг коробки на грузоместо (ПВЗ) | Y | Given: ПВЗ отгрузка с fbs_trbx id=tb1, коробка упаковки box_id=b1 / When: POST bind-box (trbx_id=tb1, packaging_box_id=b1) / Then: fbs_trbx.packaging_box_id = b1, статус успех 200 |
| TC-NEW-FBS-PACKINT-003 | Синхронизация статуса отгрузки при завершении упаковки | Y | Given: отгрузка в assembling, associated PackagingTask с 2 линиями / When: обе линии упакованы (статус packed в PackagingTask) / Then: FbsSupply статус обновлён на packed (если маркировка не требуется) или ждёт маркировки |
| TC-NEW-FBS-PACKINT-004 | Отгрузка без упаковки (СЦ-поток, optional) | Y | Given: СЦ отгрузка (warehouse_sc), маркировка не требуется / When: статус → assembling / Then: создан PackagingTask для учёта, но можно пропустить упаковочное действие (scope ограничение) |
| TC-NEW-FBS-PACKINT-005 | Ошибка: товар не найден в каталоге | Y | Given: заказ с product_id, которого нет в БД / When: создание PackagingTask / Then: логируется warning, линия создана с null-полями, процесс не падает |

## Где тесты

backend: `cd backend && pytest tests/services/test_fbs_packaging_integration.py`

## Гейт перед PR

```bash
cd backend && ruff check . && mypy . && pytest
```
