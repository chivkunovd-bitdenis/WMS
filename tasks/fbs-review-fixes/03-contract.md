# 03 — Контракт (критерии приёмки)

## TC-NEW-FBS-FIX-001 — отмена не вешает отгрузку
- **Given:** отгрузка `assembling`, packaging task с qty_total по заказам, ≥1 заказ в отгрузке.
- **When:** заказ отменён (API cancel или WB status cancel в sync).
- **Then:** `order.supply_id is None`; qty_total уменьшен; при полной упаковке оставшихся — supply → `packed`; при отмене последнего — supply → `draft`, не тупик.
- **Negative:** отмена заказа не в отгрузке — поведение как раньше.

## TC-NEW-FBS-FIX-002 — резерв без оверселла
- **Given:** остаток 1, два заказа на тот же товар.
- **When:** два конкурентных `_try_reserve_order`.
- **Then:** ровно один `reserved`, второй `no_stock`; тик не падает с IntegrityError.

## TC-NEW-FBS-FIX-003 — синк >500
- **Given:** >500 нетерминальных заказов + sorted в хвосте.
- **When:** `sync_order_statuses`.
- **Then:** самый старый нетерминальный (не sorted) тоже получает WB-статус за полный цикл пагинации.

## TC-NEW-FBS-FIX-004 — PACKED ждёт ok КИЗ
- **Given:** supply assembling, упаковка complete, sgtin `check_status=new`.
- **When:** promote.
- **Then:** остаётся assembling; после sync → ok → packed.
