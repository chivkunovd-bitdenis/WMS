# 04 — Тест-кейсы

| # | TC-ID | Given | When | Then |
|---|-------|-------|------|------|
| 1 | TC-NEW-SCAN-FAST-001 | Приёмка с товаром и WB-карточкой | Скан в общий факт и в короб с `product_id` | Каталог не перечитывается; количество становится 1, повторные сканы не теряются |
| 2 | TC-NEW-SCAN-FAST-002 | Товар не входит в документ | Клиент передаёт чужой `product_id` | Сервер отвечает `product_not_on_request` / `product_not_in_shipment`, остатки не меняются |
| 3 | TC-NEW-SCAN-FAST-003 | Отгрузочный короб и выбранная ячейка | Скан товара | План и остаток проверяются, строка и счётчик обновляются без полного reload |
| 4 | TC-NEW-SCAN-FAST-004 | Товар лежит в зоне сортировки | Скан без выбора ячейки | Добавляется одна единица по существующему правилу |
| 5 | TC-NEW-SCAN-FAST-005 | Задание упаковки | Скан SKU | `+1`, текущая строка подсвечена, повторная загрузка истории не выполняется до ответа |

## Где живут тесты

- `backend/tests/test_inbound_intake_box_ondemand.py`
- `backend/tests/test_marketplace_unload_tsd_scan_contract.py`
- `backend/tests/test_packaging_tasks.py`
- `frontend/src/screens/ff/inboundScanLookup.test.ts`
- `frontend/tests-e2e/inbound-receiving-v2.spec.ts`
- `frontend/tests-e2e/ff-mp-box-add-modal.spec.ts`
- `frontend/tests-e2e/ff-packaging-page.spec.ts`

