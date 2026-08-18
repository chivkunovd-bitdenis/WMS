# WB API Gate: Wave1 FBS New Orders

Scope: FBS-02, FBS-03, FBS-17, FBS-19, FBS-07 and GLOBAL-03 for screen
`FBS — Новые заказы`.

Out of scope: FBS-01, stock publication, `fbs_stock_sync_service.py`,
`fbs_stock_availability_service.py`, existing supply enrichment from Wave 2.

Official references for manual re-check:

- `https://dev.wildberries.ru/docs/openapi/orders-fbs`
- `https://dev.wildberries.ru/swagger/orders-fbs`
- `https://dev.wildberries.ru/en/knowledge-base/articles/019d49a4-0771-7571-aea9-11d5b597f34c/fbs-orders`

Direct YAML fetch can be blocked by WB anti-bot protection, so implementation
must treat these references as the source for human review and must not infer
new fields silently.

## GET /api/v3/orders/new

Purpose: load new FBS assembly orders.

Required fields consumed by WMS:

- `id`: WB order id.
- `createdAt`: source for `created_at_wb`; UI shows "Создан WB" and elapsed time.
- `warehouseId`: seller WB warehouse source; drives row display, warehouse filter,
  Excel export and preflight compatibility.
- `nmId`, `chrtId`, `article`, `skus`: product mapping and row identifiers.
- `cargoType`, `options.isB2B` or equivalent legal buyer flag.
- `requiredMeta`, `optionalMeta`: marking/metadata hints, if WB sends them.

Limits and failures:

- Use existing client timeout behavior.
- Show a human message on 401/403/429/5xx or transport error.
- Keep the last visible WMS list when refresh fails; do not convert WB failure to
  an empty list.

Fallback:

- No confirmed WB field is used as a universal "ship by" SLA. WMS may display
  elapsed time from `createdAt` and an internal/confirmed deadline separately.

Logging:

- `tenant`, `seller`, `WB warehouse`, endpoint, WB status/code and response body
  without secrets.

## POST /api/v3/supplies

Purpose: create a WB supply before adding selected orders.

Request:

- `{ "name": string }`; WMS generates the name for this screen.

Success:

- Response must contain supply `id`.
- Without WB supply id the WMS supply remains unconfirmed and the UI must not
  show success.

Failures:

- Transport error or WB 4xx/5xx are shown as human messages.
- Log `tenant`, `seller`, endpoint, local supply id when available, request
  summary without token and WB response snippet.

## PATCH /api/marketplace/v3/supplies/{supplyId}/orders

Purpose: add selected order ids to one WB supply.

Request:

- `{ "orders": number[] }`.
- Batch size is limited to 100 WB order ids by the client helper.

Preflight before call:

- One seller.
- One WB warehouse.
- One WMS warehouse binding.
- One buyer type.
- One cargo type.
- Orders are still new, not cancelled, not already in another supply.
- Product and warehouse are mapped.

Failures and partial success:

- After any transport error, timeout, 409, or other WB add error, WMS must run
  read-back before deciding local state.
- If read-back confirms some orders, WMS binds only confirmed orders and returns
  `partial_rejection.accepted_orders` and `partial_rejection.rejected_orders`.
- If read-back cannot confirm composition, WMS marks the operation
  `pending_confirmation`; UI shows "ожидает подтверждения WB" and offers retry
  with the same idempotency key.

Logging:

- `tenant`, `seller`, `WB warehouse`, `WMS warehouse`, endpoint, `orderId` list,
  `supplyId`, WB status/code, request summary, response snippet without secrets,
  and read-back result.

## GET /api/marketplace/v3/supplies/{supplyId}/order-ids

Purpose: read-back actual WB supply composition.

Response:

- `orderIds` or equivalent parsed list of WB order ids.

Use:

- Mandatory after supply order add when success is uncertain.
- Also used after apparently successful add to ensure local state follows WB.

Failures:

- Transport timeout means pending confirmation.
- Non-transport WB errors fail the operation with a human message and a log ref.

No fallback:

- WMS must not assume all requested orders were added if this read-back fails.
