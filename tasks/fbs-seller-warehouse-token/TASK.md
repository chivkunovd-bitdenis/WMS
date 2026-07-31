# TASK — fbs-seller-warehouse-token: склады продавца и токены маркетплейса

- **Эпик:** FBS — см. `../fbs-marketplace-orders/SPEC.md`. Гейт 1 эпика ✅ (арх-курс утверждён), под-задача наследует.
- **Тип / размер:** feature / S
- **Зависит от:** нет (может идти параллельно с intake)
- **Слои:** backend: models + services / api

## Описание (для Composer)

Управление складами и офисами продавца в WB через GET /warehouses, POST /warehouses и GET /offices. Проверяем, что селлер имеет категорию токена «Маркетплейс» (или отдельное поле marketplace_token). Каждый виртуальный склад продавца имеет идентификатор (officeId) и зону доставки — это всё используется при создании поставок и отгрузок. Простая задача, но важная для мульти-селлер-изоляции.

## Scope

- Endpoint GET списка складов продавца (GET /api/fbs/seller/{seller_id}/warehouses)
- Endpoint GET списка офисов/зон (GET /api/fbs/seller/{seller_id}/offices)
- Проверка категории токена «Маркетплейс» (в seller_wildberries_credentials)
- Синхронизация складов/офисов с кэшем (optional, если нужно)
- Валидация: токен должен быть категории «Маркетплейс» (не «Остатки» или другая)

## Out of scope

- Создание складов (в WB это редко, обычно заводит поддержка)
- Интеграция с остатками (stocks) — отдельная задача
- Фронтенд-экраны
- Управление доступами пользователей к складам

## Арх-подход (из утверждённого SPEC)

- **Таблица:** проверка в `seller_wildberries_credentials` — есть ли поле `marketplace_token` или маркер категории на `supplies_token`.
- **Сервис:** `WBSellerWarehouseService` (получение списка складов/офисов по API, валидация токена).
- **Endpoints:**
  - GET `/api/fbs/seller/{seller_id}/warehouses` — список складов продавца (warehouseId, name, address)
  - GET `/api/fbs/seller/{seller_id}/offices` — список офисов/зон (officeId, name, zone)
- **WB API:** GET `/api/v3/warehouses`, GET `/api/v3/offices`, возможно POST `/api/v3/warehouses` (если создание). ⚠️ Сверить с `dev.wildberries.ru`.
- **Валидация токена:** проверяем, что в credentials есть категория «Маркетплейс» (field marketplace_token или категория на supplies_token).
- **Файлы:** backend/app/models/fbs_models.py (если новое поле в credentials), backend/app/services/fbs_seller_warehouse.py, backend/app/api/fbs_seller.py.
- Мульти-селлер: каждый вызов фильтруется по seller_id, authorization по токену селлера.

## Критерии приёмки (DoD)

- [ ] Endpoint GET warehouses — вызывает WB API, возвращает список складов селлера с officeId/name/address
- [ ] Endpoint GET offices — вызывает WB API, возвращает список зон доставки
- [ ] Валидация токена: перед любым вызовом проверяем категорию (marketplace_token или маркер категории)
- [ ] Авторизация: только селлер может видеть свои склады (по seller_id в токене)
- [ ] Кэш (optional): возможность кэшировать список офисов/складов на 1 день
- [ ] CI зелёный

## Test coverage (копируется в описание PR)

| TC-ID | Title (short) | Applies (Y/N) | Notes |
|-------|---------------|---------------|-------|
| TC-NEW-FBS-WHTOKEN-001 | Получение складов селлера | Y | Given: селлер с валидным marketplace_token / When: GET /seller/{sid}/warehouses / Then: список складов от WB, officeId/name/address; negative: нет токена → 403 |
| TC-NEW-FBS-WHTOKEN-002 | Получение офисов/зон | Y | Given: селлер авторизирован / When: GET /seller/{sid}/offices / Then: список зон доставки (zone, officeId); negative: токен неверный → 401 |
| TC-NEW-FBS-WHTOKEN-003 | Валидация категории токена | Y | Given: токен без категории «Маркетплейс» / When: попытка вызова API / Then: 403 (недостаточно прав); negative: токен с категорией → OK |
| TC-NEW-FBS-WHTOKEN-004 | Изоляция по seller_id | Y | Given: 2 селлера / When: каждый запрашивает свои склады / Then: видят только свои (officeId/warehouseId разные); negative: перекрёстный доступ → 403 |

## Где тесты

- backend: `cd backend && pytest tests/test_fbs_seller_warehouse.py`.

## Гейт перед PR

- `cd backend && ruff check . && mypy . && pytest`
