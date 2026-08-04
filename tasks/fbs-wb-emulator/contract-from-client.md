# WB Marketplace API contract — as consumed by WMS client

Source of truth: `backend/app/services/wildberries_client.py` (+ downstream field usage in FBS services).

## Connection

| Setting | Env variable | Default |
|---------|--------------|---------|
| `settings.wildberries_marketplace_api_base` | `WILDBERRIES_MARKETPLACE_API_BASE` | `https://marketplace-api.wildberries.ru` |

All marketplace calls use base URL: `(marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/") + path`.

### Authorization

| Header | Value |
|--------|-------|
| `Authorization` | Raw API token string (no `Bearer` prefix) |

JSON endpoints also send `Content-Type: application/json` where a body is present.

### Error handling (client)

HTTP status `>= 400` → `WildberriesClientError("upstream_error", status_code=...)`. Emulator should return 4xx/5xx for failures; WMS does not parse WB error JSON bodies.

---

## Endpoints (16)

| Path | Method | Query | Request body | Response fields client reads | Notes / mock shape |
|------|--------|-------|--------------|------------------------------|-------------------|
| `/api/v3/orders/new` | GET | — | — | **Envelope:** raw `list` **or** `{ "orders": list }`. **Per order:** `id`, `rid`, `createdAt`, `nmId`, `chrtId`, `article`, `skus[]`, `price`, `cargoType`, `officeId`, `isLegal`, `options.isB2B`, `canPvz`, `isPvz` (also accepts `warehouseId`, `barcode`, `sku` as fallbacks in services) | Mock (`e2e_mock_wb_marketplace_orders`): `[{ "id": 990001, "rid": "mock-rid-990001", "createdAt": "2026-07-01T10:00:00+03:00", "nmId": 424242, "chrtId": 111, "article": "E2E-MOCK", "skus": ["E2E-MOCK-BARCODE"], "price": 150000, "cargoType": 1, "officeId": 12345, "isLegal": false, "options": { "isB2B": false } }]` |
| `/api/v3/orders` | GET | `limit` (1–1000, default 100), `next` (int, optional cursor) | — | `{ "orders": list, "next": int \| null }` — reads `orders` array and `next` pagination token | Mock returns `[], null`. Same order fields as `/orders/new` in each list item |
| `/api/v3/orders/status` | POST | — | `{ "orders": [int, ...] }` — WB order IDs | **Envelope:** raw `list` **or** `{ "orders": list }`. **Per row:** `id`, and one of `wbStatus`, `supplierStatus`, `status` (string) | Mock: `[{ "id": oid, "supplierStatus": "new", "wbStatus": "waiting" } for oid in order_ids]`. Service maps statuses: cancel variants → cancelled; `sold` → done; `sorted` → sorted; `defect` → defect; `waiting` → no local status change unless already in_delivery |
| `/api/v3/orders/{order_id}/cancel` | PATCH | — | — | *(none — success = HTTP < 400, empty body OK)* | Mock: no-op success |
| `/api/v3/orders/stickers` | POST | `type=png`, `width` (default 58), `height` (default 40) | `{ "orders": [int, ...] }` | **Envelope:** raw `list` **or** `{ "stickers": list }`. **Per sticker:** `orderId` or `order_id`, `barcode` (string), `file` (base64 PNG string, optional `data:` prefix) | Mock: `[{ "orderId": oid, "partA": oid, "partB": oid+1, "barcode": "MOCK-{oid}", "file": "<base64 1×1 png>" }]`. Service requires `barcode` and/or decodable `file` per order |
| `/api/v3/orders/{order_id}/meta` | GET | — | — | `dict` — see [Meta GET shapes](#meta-get-response-shapes) below | Mock (`e2e_mock_wb_marketplace_marking`): in-memory `{ "sgtins": [{ "value": "...", "checkStatus": "new" }], ... }` |
| `/api/v3/orders/{order_id}/meta/{kind}` | PUT | — | `{ "<plural>": ["<value>"] }` where `kind` → plural: `sgtin`→`sgtins`, `uin`→`uins`, `imei`→`imeis`, `gtin`→`gtins` | *(none — success = HTTP < 400)* | Mock upserts into in-memory store with `checkStatus: "new"` |
| `/api/v3/supplies` | POST | — | `{ "name": string }` | `{ "id": string \| int, ... }` — **must** have `id` (WB supply id) | Mock: `{ "id": "WB-GI-MOCK-1", "name": name }` |
| `/api/v3/supplies/{supply_id}/orders/{order_id}` | PATCH | — | — | *(none — success = HTTP < 400)* | Mock: no-op. `supply_id` is string; `order_id` is int path segment |
| `/api/v3/supplies/{supply_id}/deliver` | PATCH | — | — | *(none — success = HTTP < 400)* | Mock: no-op |
| `/api/v3/supplies/{supply_id}/barcode` | GET | `type` (default `png`) | — | **Either:** raw image bytes (`Content-Type` contains `image`) **or** JSON `{ "file" \| "barcode" \| "image": base64-or-data-uri }` | Mock: returns tiny 1×1 PNG bytes |
| `/api/v3/supplies/{supply_id}/trbx` | POST | — | `{ "amount": int }` | List of trbx id strings — parser accepts: raw `list[str]`, `list[{id\|trbxId\|trbx_id}]`, or `{ "trbxIds" \| "trbx_ids" \| "data" \| "trbxes": ... }`. **Must** return exactly `amount` ids | Mock: `["MOCK-TRBX-1", "MOCK-TRBX-2", ...]` |
| `/api/v3/supplies/{supply_id}/trbx/{trbx_id}` | PATCH | — | `{ "orderIds": [int, ...] }` | *(none — success = HTTP < 400)* | Mock: no-op |
| `/api/v3/supplies/{supply_id}/trbx/stickers` | POST | `type` (default `png`) | `{ "trbxIds": [string, ...] }` | **Envelope:** raw `list` **or** `{ "stickers": list }`. **Per row:** `trbxId` or `trbx_id` or `id`; image in `file` or `barcode` or `image` (base64 / data-uri / bytes) | Mock: `[{ "trbxId": id, "file": "<base64 png>", "barcode": "MOCK-QR-{id}" }]` |
| `/api/v3/warehouses` | GET | — | — | Raw `list` of objects. Service passes through: `id`, `name`, `address`, `officeId`, `cargoType`, `deliveryType`, `isDeleting`, `isProcessing` (only if present) | Mock (`e2e_mock_wb_marketplace_warehouses`): `[{ "id": 501001, "name": "E2E Seller Warehouse", "officeId": 601001, "address": "...", "cargoType": 1, "deliveryType": 1 }]` |
| `/api/v3/offices` | GET | — | — | Raw `list` of objects. Service passes through: `id`, `officeId`, `name`, `city`, `address`, `longitude`, `latitude`, `selected` | Mock (same flag as warehouses): `[{ "id": 601001, "officeId": 601001, "name": "E2E Seller Office", "city": "Moscow", "address": "...", "longitude": 37.62, "latitude": 55.75 }]` |

---

## Meta GET response shapes

Parsed by `fbs_marking_service.parse_wb_meta_statuses()`:

1. **Nested `meta` dict** — keys are kind (`sgtin`) or plural (`sgtins`); values are string, dict `{value, checkStatus|check_status}`, or list of those.
2. **Nested `meta` list** — items `{ key\|type, value, checkStatus\|check_status }`.
3. **Top-level plural keys** — `sgtins`, `uins`, `imeis`, `gtins` (and singular `sgtin`, `uin`, `imei`, `gtin`).
4. **Per entry:** `value` (string), `checkStatus` or `check_status` — int `0=new, 1=checking, 2=ok, 3=error, 4=no_check` or string aliases (`ok`, `success`, `valid`, `error`, `failed`, `in_progress`, etc.).

PUT body uses **plural array keys only** (see table row for meta PUT).

---

## Order field usage by service

| Field | Used in |
|-------|---------|
| `id` | `wb_marketplace_orders_service` — primary key |
| `rid` | stored as `wb_rid` |
| `createdAt` | `created_at_wb`, deadline = +120h |
| `nmId`, `chrtId`, `article` | product mapping |
| `skus[0]`, `barcode`, `sku` | barcode resolution |
| `price` | stored |
| `cargoType` | `1→mgt, 2→kgt, 3→sgt` |
| `officeId`, `warehouseId` | `wb_office_id` |
| `isLegal`, `options.isB2B` | `is_legal` |
| `canPvz`, `isPvz` | `can_pvz` |

---

## E2E mock flags (`settings`)

| Flag | Affects |
|------|---------|
| `e2e_mock_wb_marketplace_orders` | orders/new, orders page, status, cancel |
| `e2e_mock_wb_marketplace_supplies` **or** `e2e_mock_wb_marketplace_orders` | supplies create/add, stickers, deliver, barcode, trbx create/bind/stickers |
| `e2e_mock_wb_marketplace_warehouses` | seller warehouses **and** offices |
| `e2e_mock_wb_marketplace_marking` | meta GET/PUT (in-memory `_mock_order_meta`) |

Env names: `E2E_MOCK_WB_MARKETPLACE_ORDERS`, `E2E_MOCK_WB_MARKETPLACE_SUPPLIES`, `E2E_MOCK_WB_MARKETPLACE_WAREHOUSES`, `E2E_MOCK_WB_MARKETPLACE_MARKING`.

Helper: `reset_mock_marketplace_order_meta()` clears marking mock store (tests).

---

## Not used by client (do not implement for WMS parity)

- `GET /api/v3/supplies/{supply_id}` and `GET /api/v3/supplies/{supply_id}/orders` — mentioned in task brief but **no functions** in `wildberries_client.py`.
- Order sticker fields `partA`, `partB` appear in mock only; services do not read them.

---

## Ambiguities / gaps

1. **Response envelope inconsistency** — client tolerates both bare arrays and wrapped objects (`orders`, `stickers`). Emulator should pick one canonical shape per endpoint or support both like the client.
2. **Status precedence** — `_wb_status_from_row` checks `wbStatus` → `supplierStatus` → `status` in that order; real WB may differ.
3. **Cancel / deliver / add-order success bodies** — client ignores response body; unknown if WB returns JSON.
4. **Supply `id` type** — client stores `str(wb_row["id"])`; mock uses string `"WB-GI-MOCK-1"`; real WB format unspecified in code.
5. **Trbx create response** — client accepts many shapes; emulator should return `{ "trbxIds": ["..."] }` or plain string list for clarity.
6. **Meta GET canonical shape** — service handles 3+ layouts; emulator should implement plural top-level keys (`sgtins: [{value, checkStatus}]`) as minimum.
7. **Barcode endpoint content-type** — client prefers `image/*` raw bytes; JSON fallback is secondary.
8. **Order stickers** — mock includes `partA`/`partB`; production WB fields unknown; only `orderId`, `barcode`, `file` are required downstream.
9. **Pagination `next`** — type is int; semantics (cursor value vs offset) not documented in code.
10. **No auth validation in client** — emulator must implement 401 for unknown tokens separately (product requirement in TASK.md, not in client).
