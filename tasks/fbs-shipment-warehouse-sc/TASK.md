# TASK — fbs-shipment-warehouse-sc: передача в доставку для склада/СЦ

- **Эпик:** FBS — см. `../fbs-marketplace-orders/SPEC.md`. Гейт 1 эпика ✅ (арх-курс утверждён), под-задача наследует.
- **Тип / размер:** feature / M
- **Зависит от:** fbs-orders-intake, fbs-supply-assembly, fbs-marking
- **Слои:** backend: services / api

## Описание (для Composer)

Передаём отгрузку в доставку через `PATCH /supplies/{sid}/deliver`. Получаем QR поставки (GET /barcode). Отслеживаем статусы/чек-лист для потока склад/СЦ (вес паллеты, габариты, наличие пропуска). Заказы переходят в статус in_delivery. Это — точка невозврата перед физической доставкой на склад WB.

## Scope

- Endpoint PATCH для передачи supply в доставку (deliver)
- Получение QR-кода поставки (GET /supplies/{sid}/barcode) — PNG/SVG
- Проверка pre-conditions перед deliver: все маркировки внесены (если required), нет отменённых заказов
- Обновление статусов заказов (order → in_delivery) и supply (assembling → in_delivery)
- Чек-лист: габариты, вес, паллетизация, пропуск на машину (optional)

## Out of scope

- ПВЗ-специфичные грузоместа и ограничения (задача fbs-shipment-pvz)
- Логистика за пределами WB API (отвоз на склад, приёмка)
- Фронтенд-экраны
- ТСД

## Арх-подход (из утверждённого SPEC)

- **Сервис:** `WBShipmentWarehouseSCService` (передача в доставку, валидация пред-условий, скачивание QR).
- **Endpoint:** PATCH `/api/fbs/supplies/{supply_id}/deliver` — проверяет все маркировки (if required), вызывает WB API `PATCH /api/v3/supplies/{sid}/deliver`, переводит в_delivery.
- **QR поставки:** GET `/api/fbs/supplies/{supply_id}/barcode?type=png` — возвращает PNG или кэш из WB (Column barcode_file в fbs_supply).
- **Валидация:** перед deliver проверяем:
  - Все заказы в статусе packed (если маркировка обязательна)
  - Нет заказов в статусе cancelled
  - Delivery_type = warehouse_sc (не pvz)
- **Эндпоинты WB API:** PATCH `/api/v3/supplies/{sid}/deliver`, GET `/api/v3/supplies/{sid}/barcode?type=...`. ⚠️ Сверить с `dev.wildberries.ru`.
- **Файлы:** backend/app/services/fbs_shipment.py, backend/app/api/fbs_shipment.py.
- Чек-лист: опциональная табличка из раздела §4 SPEC (габариты короба, вес, наличие паллеты), может быть в отдельном ендпоинте.

## Критерии приёмки (DoD)

- [ ] Endpoint PATCH deliver — вызывает WB API, переводит supply и заказы в in_delivery
- [ ] Валидация: проверка маркировок (required по cargo_type) перед deliver
- [ ] QR поставки: получение из WB, кэширование, возврат PNG/SVG
- [ ] Статусы: supply.status assembling → in_delivery, orders.status packed → in_delivery
- [ ] Обработка ошибок WB: повтор, откат (транзакция)
- [ ] Чек-лист: optional endpoint для регистрации (габариты, вес, паллетизация)
- [ ] CI зелёный

## Test coverage (копируется в описание PR)

| TC-ID | Title (short) | Applies (Y/N) | Notes |
|-------|---------------|---------------|-------|
| TC-NEW-FBS-SHIPWH-001 | Передача supply в доставку | Y | Given: supply в статусе assembling, все заказы packed / When: PATCH /supplies/{sid}/deliver / Then: WB API вызван, supply→in_delivery, все заказы→in_delivery; negative: есть неупакованный заказ → 400 |
| TC-NEW-FBS-SHIPWH-002 | Получение QR поставки | Y | Given: supply в доставке / When: GET /supplies/{sid}/barcode?type=png / Then: возвращен PNG, кэширован в barcode_file; negative: ошибка WB → повтор |
| TC-NEW-FBS-SHIPWH-003 | Валидация маркировок перед deliver | Y | Given: cargo_type требует КИЗ, но маркировка не внесена / When: PATCH deliver / Then: 400 валидации; negative: маркировка опциональна → deliver прошёл |
| TC-NEW-FBS-SHIPWH-004 | Откат при ошибке WB | Y | Given: WB вернул ошибку (retry impossible) / When: deliver / Then: исключение, статусы не изменены; negative: retry успешен → статусы обновлены |

## Где тесты

- backend: `cd backend && pytest tests/test_fbs_shipment_warehouse_sc.py`.

## Гейт перед PR

- `cd backend && ruff check . && mypy . && pytest`
