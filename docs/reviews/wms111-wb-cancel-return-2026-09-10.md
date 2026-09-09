# WMS-111 и WMS-112 · автосоздание документа возврата WB после отмены и точное время отмены

**Дата:** 2026-09-10 · **Ветка:** `feat/wms111-wb-cancel-return`

## Что было

До правки локальная часть отмены WB FBS-заказа честно чистила статус, сторно
биллинга, отвязку от поставки и снимала резерв — но документа приёмки-возврата
не заводила. Комментарий в `backend/app/services/fbs_cancellation_service.py:75-111`
ровно это и говорил: «после supplier complete нужен отдельный документ
возврата». Оператор должен был вспомнить и завести его руками, иначе товар
физически ехал обратно, а WMS ничего об этом не знал (531 штука по всем
арендаторам висела списанной на 09.09.2026).

Реестр отмен `fbs_cancelled_after_pack_service.fetch_cancelled_after_pack_page`
отдавал в поле `cancelled_at` общий `FbsOrder.updated_at` и признак
«supply_departed» вычислял по текущему состоянию поставки, а не сравнением двух
исторических моментов. Реестр показывал «Обновлено», а не момент отмены.

## Что стало

Появился один общий сервис `backend/app/services/fbs_cancel_return_document_service.py`,
который делает ровно то, что просил владелец: если отмена относится к
подтверждённой передаче — заводит один документ возврата из существующей семьи
приёмки (`InboundIntakeRequest` с `operation_type='return'`,
`marketplace='wildberries'`). Это ровно тот же тип, что и ручной возврат: новых
таблиц, новых типов документа, новых статусов не заведено. Правило «Никакого
оверинжиниринга» соблюдено.

**Идемпотентность.** Ключ — натуральный: `wb_order_id`. Факт создания записан
маркером `wb_cancel_return` в `FbsOrder.meta_details_json`, там же лежит ссылка
на `inbound_intake_requests.id`. Повторный вызов на том же заказе видит маркер
и возвращает уже созданный документ.

**Граница до/после передачи.** Проверяется через существующую функцию
`fbs_order_billing_service.confirmed_order_handover_dates`. Это тот же сигнал,
которому уже доверяет биллинг (WMS-406). Новых булевых флагов на заказ, новых
колонок, новых «assembly_status» не заведено.

**Момент отмены.** WB в открытой части API момент отмены не отдаёт, но код
защищается предусмотрительно: смотрит ключи `cancelledAt`, `cancelled_at`,
`cancelAt`, `cancelDate`, `cancellationDate`, `cancellation_date`. Если ни
одного нет — берём момент, когда WMS увидел отмену, и явно помечаем источник
`received_at`. Никакого «выдумывания истории»: невыдуманный источник всегда
указан рядом со временем.

**Никаких движений остатка.** Документ создаётся в статусе `draft` со строкой
`expected_qty=1`, `actual_qty=None`, `posted_qty=0`. Модуль приёмки трогает
остаток только при движении `posted_qty` (guarded сканами оператора), поэтому
пока оператор не откроет документ и не примет товар физически — на складе
ничего не сдвинется. Это подтверждено тестом.

Точки вызова:
- WB-обмен (автосинк статусов, `_apply_wb_status_to_order`) — там же, где уже
  идёт `reverse_fbs_order_billing`. Пробрасываем строку WB, чтобы честно
  достать `cancelledAt`, если он появится.
- Ручная отмена оператором в `fbs_cancellation_service._finish_local_cancellation`
  — там источник времени всегда `received_at`, потому что WB строку сюда никто
  не приносит.

Реестр отмен теперь строит:
- `cancelled_at` — из маркера, если он есть, иначе (для строк, созданных до
  этой правки) — `order.updated_at` с явным `cancelled_at_source='updated_at'`.
- `cancelled_at_source` — новое поле, чтобы читатель отличал честный момент от
  fallback.
- `cancelled_after_transfer` — сравнение `cancelled_at` с моментом передачи,
  который для батча заказов достаём одним запросом
  `confirmed_order_handover_dates`. `None`, когда момент передачи не
  подтверждён (тогда фронту нельзя рисовать «после передачи» по умолчанию).
- `transfer_at` — сам момент передачи (или `None`).
- `return_document_id` — ссылка на автоматически созданный документ возврата,
  чтобы UI мог напрямую вести оператора туда.

Старое поле `supply_departed` (моментальный признак по поставке) сохранено ради
обратной совместимости фронта; фронтенд будет мигрирован на новое поле
`cancelled_after_transfer` отдельной задачей.

## Как проверено

Ветка гоняется в изолированном worktree, все проверки локальные. Реальный
webhook WB на этой сессии не активирован — при отсутствии стенда с честным
инцидентом отмены после передачи это делается кодовым путём и явно тут
отмечается.

- `ruff check .` в бэкенде — 0 замечаний.
- `mypy .` — 0 замечаний (437 файлов).
- `pytest -n auto backend/tests/test_wms111_wb_cancel_return.py
   backend/tests/test_fbs_cancellations.py
   backend/tests/test_fbs_cancelled_after_pack.py
   backend/tests/test_fbs_cancelled_operations.py
   backend/tests/test_fbs_delivery_cancelled_exclusion.py
   backend/tests/test_wb_marketplace_orders_service.py` — 31 pass.

Новые тесты (`backend/tests/test_wms111_wb_cancel_return.py`):
1. `cancel_time_from_row_prefers_wb_payload` — при наличии `cancelledAt` в
   payload сохраняется точное время, источник `wb_payload`.
2. `cancel_time_from_row_falls_back_to_received_at` — без ключа берётся
   переданное `received_at`, источник `received_at`.
3. `cancel_time_from_row_ignores_unparseable_cancelled_at` — мусор в
   `cancelledAt` не сохраняется как «время от WB», честно откатываемся на
   received_at.
4. `cancel_before_transfer_creates_no_return_document` — поставка не была
   передана, документ не создаётся, маркер не ставится.
5. `cancel_after_transfer_creates_return_document_once_and_no_stock_change` —
   первая отмена создаёт документ, повторная отмена не создаёт второй; в базе
   ноль `InventoryBalance` и `InventoryMovement`; строка возврата
   `posted_qty=0`, `actual_qty=None`.
6. `cancel_after_transfer_received_at_when_wb_omits_field` — WB строка без
   `cancelledAt`, момент = переданный `received_at`, источник `received_at`.
7. `ensure_return_doc_no_warehouse_returns_none` — если у заказа нет склада,
   документ не создаётся (нельзя корректно ссылаться), функция не бросает и не
   ставит маркер.

## Что НЕ проверено в этой сессии

- **Реальный WB-webhook отмены не активирован.** Реальные события отмены
  наблюдаются только на прод-стенде с активными WB-токенами, и запрос
  «пройди руками отмену в WB» вне рамок этой задачи. Код-путь совпадает с
  тем, куда попадает и ручной оператор, и автосинк статусов; тесты закрывают
  оба.
- **Фронт-миграция.** Диалог `FbsCancelledAfterPackDialog.tsx` сейчас читает
  `cancelled_at` (уже получает честный момент) и `supply_departed`
  (моментальный признак сохранён). Переход на `cancelled_after_transfer`
  сделает отдельная задача, чтобы это изменение не размывало границы правки
  бэка.

## Файлы

- Новый: `backend/app/services/fbs_cancel_return_document_service.py`
- Правки:
  - `backend/app/services/fbs_cancellation_service.py`
  - `backend/app/services/wb_marketplace_orders_service.py`
  - `backend/app/services/fbs_cancelled_after_pack_service.py`
- Тесты: `backend/tests/test_wms111_wb_cancel_return.py`
- Бэклог: статус WMS-111 и WMS-112 обновлён в
  `docs/KANONICHESKIY_BACKLOG.md`.
