# TASK — fbs-cancellations: отмены и синк статусов

- **Эпик:** FBS — см. `../fbs-marketplace-orders/SPEC.md`. Гейт 1 эпика ✅ (арх-курс утверждён), под-задача наследует.
- **Тип / размер:** feature / M
- **Зависит от:** fbs-orders-intake
- **Слои:** backend: services / api / tasks

## Описание (для Composer)

Отмена заказа по инициативе продавца (PATCH /orders/{id}/cancel) + синк статусов из WB (POST /orders/status). Обрабатываем отказы покупателя, возвраты, автовозврат в ПВЗ. Откатываем резерв остатка при отмене. Отслеживаем штрафы (зависят от времени отмены: <13ч -1.5%, 18ч базовый, >18ч штраф растёт, >120ч автоотмена). Раздел 06 wb-docs даёт полный процесс. Это — обратный поток с большим числом граничных случаев.

## Scope

- Endpoint PATCH отмены заказа (PATCH /api/v3/orders/{id}/cancel)
- Синк статусов заказов per-seller (фоновый job, раз в 5–10 мин)
- Статусы: waiting → sorted → sold/canceled/declined_by_client/defect
- Откат резерва при отмене (вызов inventory_reservation.cancel_reserve())
- Обработка статусов: новый → checking → ok → final (по раздела 06)
- Возвраты: направление товара (на склад / в ПВЗ автовозврата)

## Out of scope

- Интеграция с таблицей возвратов (может быть отдельная задача)
- Утилизация товара (управление из портала WB)
- Запросы покупателя на возврат (раздел 07, если будет)
- Фронтенд-экраны

## Арх-подход (из утверждённого SPEC)

- **Сервис:** `WBOrderCancellationService` (отмена заказа, откат резерва, валидация сроков).
- **Endpoint:** PATCH `/api/fbs/orders/{order_id}/cancel` — вызывает WB API `PATCH /api/v3/orders/{id}/cancel`, откатывает inventory_reservation, переводит заказ в cancelled.
- **Синк статусов:** background job per-seller, вызов `POST /api/v3/orders/status` (batch), обновление wb_status и order.status по матрице:
  - waiting → status=in_delivery (ожидает сортировки)
  - sorted → status=sorted (отсортирован на WB)
  - sold → status=done (выкуплен)
  - canceled/declined_by_client → status=cancelled (отмена)
  - defect → status=defect (дефект, направление на возврат)
- **Валидация отмены:**
  - <13ч: кС -1.5%, без штрафа
  - 13–18ч: кС базовый
  - 18–120ч: кС растёт
  - >120ч: автоотмена, штраф
- **Обработка возвратов:** по раздел 06 wb-docs (автовозврат → на склад WB или ПВЗ, сроки хранения 7 дн, день 8 → утилизация).
- **Эндпоинты WB API:** PATCH `/api/v3/orders/{id}/cancel`, POST `/api/v3/orders/status`. ⚠️ Сверить с `dev.wildberries.ru`.
- **Файлы:** backend/app/services/fbs_cancellation.py, backend/app/api/fbs_cancellation.py, backend/app/tasks/sync_fbs_statuses.py.

## Критерии приёмки (DoD)

- [ ] Endpoint PATCH отмены — вызывает WB API, откатывает резерв, переводит заказ в cancelled
- [ ] Валидация сроков отмены (таймер deadline_at, кС коэффициент логируется)
- [ ] Background job синка статусов per-seller (раз в 5–10 мин)
- [ ] Матрица переводов: waiting/sorted/sold/canceled/defect → корректные статусы в fbs_order
- [ ] Откат резерва: inventory_reservation.cancel_reserve() вызывается при отмене
- [ ] Обработка автовозврата: статусы defect/declined_by_client → направление в ПВЗ/склад
- [ ] CI зелёный

## Test coverage (копируется в описание PR)

| TC-ID | Title (short) | Applies (Y/N) | Notes |
|-------|---------------|---------------|-------|
| TC-NEW-FBS-CANCEL-001 | Отмена заказа <13ч | Y | Given: заказ в статусе new, created_at_wb <13ч назад / When: PATCH /orders/{oid}/cancel / Then: WB API вызван, order→cancelled, резерв откачен; negative: >120ч → автоотмена уже произошла, ошибка WB |
| TC-NEW-FBS-CANCEL-002 | Синк статусов | Y | Given: 3 заказа в разных статусах (new/in_delivery/done) / When: background job вызывает POST /orders/status / Then: wb_status обновлены, переводы сделаны (sorted→sorted, sold→done); negative: ошибка WB → retry |
| TC-NEW-FBS-CANCEL-003 | Откат резерва | Y | Given: заказ с резервом 1 шт / When: отмена заказа / Then: inventory_reservation.cancel_reserve() вызван, остаток восстановлен; negative: уже отказан → idempotent |
| TC-NEW-FBS-CANCEL-004 | Обработка defect (автовозврат) | Y | Given: заказ получил статус defect / When: синк / Then: wb_status=defect, order может быть отмечен для возврата; negative: направление ПВЗ/склад - из конфига селлера |

## Где тесты

- backend: `cd backend && pytest tests/test_fbs_cancellations.py`.

## Гейт перед PR

- `cd backend && ruff check . && mypy . && pytest`
