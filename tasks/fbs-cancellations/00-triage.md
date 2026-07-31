# 00–04 — fbs-cancellations (модератор MVP)

## In
1. `PATCH /operations/fbs-orders/{order_id}/cancel` → WB `PATCH /api/v3/orders/{id}/cancel`, order.status=cancelled, release `FbsOrderReservation` (reuse intake release helper or shared).
2. Extend status sync (existing `sync_order_statuses` in wb_marketplace_orders_service OR dedicated `fbs_cancellation_service`):
   - Map: canceled/cancelled/declined_by_client/cancel → cancelled + release reserve
   - sold → done
   - sorted → sorted (add constant)
   - defect → defect (add constant); optional `return_note` field skip — just status
   - waiting → keep/in_delivery if already shipped else leave
3. Cancel window: compute hours since created_at_wb; log penalty band (`lt13`, `13_18`, `18_120`, `gt120`) in logger; if status already cancelled → idempotent 200; if in_delivery/done → 409 `order_not_cancellable` (seller cancel only before deliver — or allow if WB allows; moderator: block local cancel if status in {in_delivery, done, cancelled}).
4. Background: reuse/extend marketplace orders sync job OR POST `/operations/fbs-orders/sync-statuses?seller_id=` — prefer enhance existing sync path + API cancel.
5. WB client: `cancel_marketplace_order`

## Out
Full returns module; disposal; buyer return requests; fee billing; frontend; invent inventory_reservation.cancel_reserve — use FbsOrderReservation delete.

## Tests TC-NEW-FBS-CANCEL-001..004
`tests/test_fbs_cancellations.py`

## Ок на код
