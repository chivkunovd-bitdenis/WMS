# WB API Gate: Wave 1 Seller Warehouses

Date: 2026-08-15
Screen: `Склады селлеров`
Scope: FBS-13, INFRA-01

## Decision

The screen may use the existing WB Marketplace seller warehouse read endpoints and the
existing local binding/stock-sync endpoints. It must not add a new stock availability
formula, must not touch `fbs_stock_sync_service.py` or
`fbs_stock_availability_service.py`, and must not implement the excluded FBS-01 fix.

## Endpoints

### Seller WB warehouses

- WB endpoint: `GET /api/v3/warehouses`
- Existing WMS wrapper: `GET /operations/fbs-sellers/{seller_id}/warehouses`
- Existing client: `fetch_marketplace_seller_warehouses`
- Expected fields used by this screen: `id`, `name`, `address`, `officeId`,
  `cargoType`, `deliveryType`, `isDeleting`, `isProcessing`
- Empty fallback: show `Склады WB не загружены: подключите токен WB Marketplace или обновите список`
- Error fallback: show a human FBS error envelope message; log tenant, seller,
  endpoint, WB status and safe WB response snippet without tokens

### Seller offices / city data

- WB endpoint: `GET /api/v3/offices`
- Existing WMS wrapper: `GET /operations/fbs-sellers/{seller_id}/offices`
- Existing client: `fetch_marketplace_seller_offices`
- Expected fields used by this screen: `id`, `officeId`, `name`, `city`, `address`,
  `selected`
- Fallback: if the office/city cannot be matched, keep the warehouse visible and
  show `город не определён`

### FBS orders warehouse source

- WB order source: `warehouseId` from existing FBS order sync
- Existing local field: `fbs_orders.wb_warehouse_id`
- Contract for other screens: this screen owns the binding dictionary; FBS new
  orders consume `wb_warehouse_id` for row/filter/Excel, but this branch does not
  implement FBS-02/FBS-17 UI.

### Stock publication status

- Existing WMS wrapper: `POST /operations/fbs-sellers/{seller_id}/stocks/sync`
  and `GET /operations/fbs-sellers/{seller_id}/stocks/sync-status`
- Existing WB publication/read-back methods remain owned by the current stock-sync
  implementation.
- This screen only blocks unmapped/technical warehouses from being used as a
  publication source and lets the operator enable publication after explicit
  WB-warehouse to WMS-warehouse mapping.

## Constraints

- No manual WB ID guessing in the UI.
- No automatic physical WMS warehouse creation named `FBS WB <id>`.
- An existing technical `FBS WB <id>` warehouse is shown as `склад не сопоставлен`
  and is not a source for stock publication.
- One active WB warehouse can map to one WMS warehouse; changing or disabling a
  binding stays blocked when active FBS reserves/orders depend on it.
- Human UI text only; raw WB bodies and tokens never appear on screen.

## Sources

- Official WB docs page: `https://dev.wildberries.ru/docs/openapi/work-with-products`
  lists `GET /api/v3/warehouses` for seller warehouses.
- Official WB docs/search page: `https://dev.wildberries.ru/docs/openapi/orders-fbs`
  covers FBS order methods used by the existing order sync.
- Local contract snapshot: `tasks/fbs-wb-emulator/contract-from-client.md`
  documents the current emulator fields for `/api/v3/warehouses` and `/api/v3/offices`.
