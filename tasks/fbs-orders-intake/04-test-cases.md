# 04 — Тест-кейсы

## Кейсы
| # | TC-ID | Что проверяем | Вход / предусловие | Ожидаемый результат | Из критерия |
|---|-------|---------------|--------------------|---------------------|-------------|
| 1 | TC-NEW-FBS-INTAKE-001 | Upsert нового заказа | Mock WB отдаёт новый order id; селлер с токеном | Строка в fbs_orders status=new, deadline_at = created+120h; повтор sync — одна строка | идемпотентность |
| 2 | TC-NEW-FBS-INTAKE-002 | Маппинг товара | product с wb_barcode=X; заказ с skus/barcode X | product_id заполнен; unknown barcode → product_id NULL + mapping flag | маппинг |
| 3 | TC-NEW-FBS-INTAKE-003 | Резерв | available≥1 | fbs_order_reservations qty=1; available=0 → заказ без резерва | резерв |
| 4 | TC-NEW-FBS-INTAKE-004 | Синк статусов | POST status → canceled | wb_status обновлён; резерв снят | статусы |

## Крайние случаи / негатив
| # | Сценарий | Ожидаемое поведение |
|---|----------|---------------------|
| N1 | Дубликат wb_order_id | Нет второй строки |
| N2 | WB transport/4xx | Ошибка/job failed, без crash процесса |
| N3 | Нет токена у селлера | Sync пропускает / явная ошибка no_token |

## Где живут тесты
- backend: `cd backend && pytest tests/test_fbs_orders_intake.py -q`

## ### Test coverage (для PR)

| TC-ID | Title (short) | Applies (Y/N) | Notes |
|-------|---------------|---------------|-------|
| TC-NEW-FBS-INTAKE-001 | Новый заказ из WB → upsert в БД | Y | Given: селлер с токеном, новый wb_order_id / When: sync orders/new / Then: fbs_order status=new, deadline_at; negative: дубль не создаёт строку |
| TC-NEW-FBS-INTAKE-002 | Маппинг по barcode/nmId | Y | Given: известный barcode / When: sync / Then: product_id; negative: unknown → NULL + пометка |
| TC-NEW-FBS-INTAKE-003 | Резерв остатка | Y | Given: stock≥1 / When: sync / Then: reservation qty=1; negative: stock=0 → без резерва |
| TC-NEW-FBS-INTAKE-004 | Синк статусов WB | Y | Given: order new / When: status canceled / Then: wb_status + release reserve; negative: WB error → retry/fail visible |
