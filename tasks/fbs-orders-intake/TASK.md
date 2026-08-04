# TASK — fbs-orders-intake: приём и резерв заказов от WB

- **Эпик:** FBS — см. `../fbs-marketplace-orders/SPEC.md`. Гейт 1 эпика ✅ (арх-курс утверждён), под-задача наследует.
- **Тип / размер:** feature / L
- **Зависит от:** нет
- **Слои:** backend: models + db (alembic) / services / api / tasks

## Описание (для Composer)

Ядро FBS: читаем заказы из WB API, сохраняем в БД, бронируем остатки, маппим товар по баркоду/nmId. Фоновый джоб опрашивает `GET /orders/new` и `GET /orders` per-seller каждые 2–5 минут (идемпотентно по `wb_order_id`). Синхронизируем статусы заказов с WB. Интегрируемся с существующей таблицей `inventory_reservation` для резерва товаров. Это — главный риск и точка входа в весь цикл FBS.

## Scope

- Модели `fbs_order`, `fbs_order_marking` (КИЗ/УИН/IMEI/GTIN как опция, связка с `marking_code`)
- Alembic-миграция (создание таблиц, индексы на `seller_id`, `wb_order_id`)
- WB Marketplace API v3 клиент (`GET /api/v3/orders/new`, `GET /api/v3/orders`, ⚠️ сверить пути)
- Фоновый таск (background job) на каждый селлер с категорией токена «Маркетплейс»
- Маппинг товара: по `wb_barcode` или `wb_nm_id` → `product_id` из нашего каталога
- Резерв остатка: вызов `inventory_reservation.reserve()` при создании заказа
- Синк статусов заказов: `POST /api/v3/orders/status` (периодически)
- Обработка пустого остатка: заказ заводим, резерв не встаёт, отмечаем пометкой

## Out of scope

- Упаковка, сборка, маркировка (следующие задачи)
- Фронтенд-экраны (fbs-frontend)
- ТСД/печать (fbs-tsd)
- Отмены и синк статусов интеграции с вебхуками (статья 06 в фичах)
- Посылки-группировка (у WB отключена)

## Арх-подход (из утверждённого SPEC)

- **Модели:** `fbs_order` (uuid pk, seller_id, warehouse_id, product_id, wb_order_id, wb_barcode, wb_nm_id, price, is_legal, cargo_type, status=new, wb_status, created_at_wb, deadline_at, supply_id=NULL, trbx_id=NULL) и `fbs_order_marking` (order_id fk, kind=sgtin|uin|imei|gtin, value, check_status, marking_code_id fk).
- **Сервис:** `WBMarketplaceOrdersService` (читает заказы per-seller, upsert по wb_order_id, маппит товар, резервит остаток, синхронизирует статусы).
- **Клиент:** `WBMarketplaceAPIClient` (оборачивает HTTP вызовы к `https://marketplace-api.wildberries.ru`, auth по селлеровому токену из `seller_wildberries_credentials`).
- **Фоновый таск:** `sync_wb_marketplace_orders` (per-seller, интервал 2–5 мин, идемпотентно).
- **Эндпоинты WB API:** GET `/api/v3/orders/new` (новые задания), GET `/api/v3/orders` (пагинация), POST `/api/v3/orders/status` (синк статусов). ⚠️ Точные имена сверить с `dev.wildberries.ru`.
- **Файлы:** backend/app/models/fbs_models.py, backend/app/services/wb_marketplace.py, backend/app/api/fbs_orders.py, backend/app/tasks/sync_wb_orders.py, alembic/versions/fbs_init.py.
- Резерв через `inventory_reservation`: вызов сервиса + откат при отмене. Один товар не резервируется одновременно под FBS и ФБО.
- Интеграция с модулем ЧЗ: поле `marking_code_id` в `fbs_order_marking` (связь с существующей таблицей `marking_code`).

## Критерии приёмки (DoD)

- [ ] Модели `fbs_order` и `fbs_order_marking` созданы, алембик-миграция применена
- [ ] WB API клиент реализован (авторизация по токену селлера, обработка ошибок)
- [ ] Фоновый таск запускается per-seller, идемпотентен по `wb_order_id`
- [ ] Товар маппится по баркоду/nmId в наш каталог; если маппинг не найден — заказ заводим с пометкой
- [ ] Резерв остатка вызывается через `inventory_reservation`, отмена резерва при отмене заказа
- [ ] Синк статусов (`POST /orders/status`) — обновляет `wb_status` в БД
- [ ] Таймер `deadline_at` (created_at_wb + 120ч) проставляется
- [ ] CI зелёный (ruff, mypy, pytest)

## Test coverage (копируется в описание PR — требование CI, AGENTS.md)

| TC-ID | Title (short) | Applies (Y/N) | Notes |
|-------|---------------|---------------|-------|
| TC-NEW-FBS-INTAKE-001 | Новый заказ из WB → upsert в БД | Y | Given: селлер с валидным токеном, новый wb_order_id / When: синк `GET /orders/new` / Then: заказ создан в fbs_order с статусом=new, deadline_at выставлен; negative: дублирование wb_order_id не создаёт новую строку |
| TC-NEW-FBS-INTAKE-002 | Маппинг товара по баркоду/nmId | Y | Given: заказ с wb_barcode известного товара / When: маппинг сервиса / Then: product_id заполнен; negative: неизвестный баркод → product_id=NULL, заказ в статусе с пометкой |
| TC-NEW-FBS-INTAKE-003 | Резерв остатка | Y | Given: заказ создан, товар есть в наличии / When: таск синка / Then: inventory_reservation.reserve() вызван, остаток уменьшился; negative: нулевой остаток → заказ заводим без резерва |
| TC-NEW-FBS-INTAKE-004 | Синк статусов WB | Y | Given: заказ в статусе new / When: `POST /orders/status` вернёт waiting/sorted/sold/canceled / Then: wb_status обновлён; negative: ошибка WB → повтор по retry-логике |

## Где тесты

- backend: `cd backend && pytest tests/test_fbs_orders_intake.py` (Given/When/Then в кейсах).

## Гейт перед PR

- `cd backend && ruff check . && mypy . && pytest`
