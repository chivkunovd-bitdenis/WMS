# TASK — fbs-marking: идентификаторы и честный знак

- **Эпик:** FBS — см. `../fbs-marketplace-orders/SPEC.md`. Гейт 1 эпика ✅ (арх-курс утверждён), под-задача наследует.
- **Тип / размер:** feature / M
- **Зависит от:** fbs-orders-intake, fbs-supply-assembly
- **Слои:** backend: models + services / api

## Описание (для Composer)

Вносим государственные идентификаторы (КИЗ/УИН/IMEI/GTIN) per-order в WB через PUT `/orders/{id}/meta/{kind}`. Связываем с существующим модулем «Честный Знак» (таблица `marking_code`). Отслеживаем статусы проверки, которые WB гоняет сам. КИЗ — обязателен для текстиля, лекарств, парфюма; остальные опциональны. Обязательно внести маркировку ДО передачи в доставку.

## Scope

- Модель `fbs_order_marking` (order_id fk, kind=sgtin|uin|imei|gtin, value, check_status=new|checking|ok|error|no_check, marking_code_id fk)
- Endpoint PUT `/api/fbs/orders/{order_id}/marking` — добавление идентификатора per-kind
- Чтение идентификаторов: GET `/api/fbs/orders/{order_id}/marking`
- Синк статусов проверки с WB (periodically)
- Интеграция с `marking_code` (для КИЗ): создание записи или связь с существующей

## Out of scope

- Физическая печать КИЗ (маркировка товара на складе) — это наш процесс, не WB API
- Предварительная валидация КИЗ через Честный Знак (может быть отдельной фичей)
- Ювелирные (УИН) и мобильные (IMEI) — базовая поддержка, без валидации уникальности

## Арх-подход (из утверждённого SPEC)

- **Модель:** `fbs_order_marking` (id uuid pk, order_id fk→fbs_order, kind enum, value str, check_status enum, marking_code_id fk→marking_code nullable).
- **Сервис:** `WBOrderMarkingService` (вносит идентификатор по API `PUT /api/v3/orders/{id}/meta/{kind}`, обновляет `check_status`, синхронизирует со статусами WB).
- **Endpoint:** PUT `/api/fbs/orders/{order_id}/marking/{kind}` — тело {value: "..."}, возвращает записанный идентификатор и статус проверки.
- **Синк статусов:** background job периодически (раз в 5–10 мин) вызывает `GET /api/v3/orders/{order_id}/meta`, обновляет check_status.
- **Эндпоинты WB API:** PUT `/api/v3/orders/{id}/meta/{sgtin|uin|imei|gtin}`, GET `/api/v3/orders/{id}/meta`, DELETE `/api/v3/orders/{id}/meta?key=...`. ⚠️ Сверить с `dev.wildberries.ru`.
- **Файлы:** backend/app/models/fbs_models.py, backend/app/services/fbs_marking.py, backend/app/api/fbs_marking.py, backend/app/tasks/sync_fbs_marking.py.
- Связь с ЧЗ: при kind=sgtin находим или создаём запись в `marking_code`, сохраняем `marking_code_id`.

## Критерии приёмки (DoD)

- [ ] Модель `fbs_order_marking` создана (иначе дополнена в миграции fbs-orders-intake)
- [ ] Endpoint PUT вносит идентификатор в WB по API, сохраняет в БД с check_status=new
- [ ] Endpoint GET возвращает все идентификаторы заказа с актуальными статусами
- [ ] Background job синхронизирует check_status из WB (new → checking → ok|error|no_check)
- [ ] Интеграция с `marking_code`: sgtin-идентификаторы связаны с таблицей ЧЗ
- [ ] Валидация: вносим только до freeze перед deliver (в статусе packed/assembling, не in_delivery)
- [ ] CI зелёный

## Test coverage (копируется в описание PR)

| TC-ID | Title (short) | Applies (Y/N) | Notes |
|-------|---------------|---------------|-------|
| TC-NEW-FBS-MARK-001 | Внесение КИЗ (sgtin) | Y | Given: заказ в статусе packed / When: PUT /orders/{oid}/marking/sgtin {value: "...sgtin..."} / Then: запись в fbs_order_marking создана, WB API вызван, check_status=new; negative: невалидный формат → 400 |
| TC-NEW-FBS-MARK-002 | Синк статусов проверки | Y | Given: КИЗ добавлен, WB вернул checking / When: background job синка / Then: check_status→checking в БД; negative: ошибка WB → retry |
| TC-NEW-FBS-MARK-003 | Связь с таблицей ЧЗ | Y | Given: sgtin-идентификатор / When: вносим в WB / Then: создаётся или находится запись в marking_code, marking_code_id заполнен |
| TC-NEW-FBS-MARK-004 | Чтение всех идентификаторов | Y | Given: заказ с 2 КИЗ + IMEI / When: GET /orders/{oid}/marking / Then: возвращены все 3 с актуальными статусами; negative: нет маркировок → пустой список |

## Где тесты

- backend: `cd backend && pytest tests/test_fbs_marking.py`.

## Гейт перед PR

- `cd backend && ruff check . && mypy . && pytest`
