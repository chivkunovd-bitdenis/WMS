# FBSFLOW-020 prep — WB client gap analysis

> Source: explore agent prep, 2026-08-03. Builder MUST re-verify OpenAPI on implementation day.

## Delta summary

Most FBS WB calls exist as **untyped dict helpers** in `wildberries_client.py`.
Gaps: batch add/list supply & trbx, batch meta POST, delete meta/trbx, chunk-100 validators,
typed 409/MetaValidationFail, 204-safe void calls. **Reference:** stocks client (STOCK-020) + `test_wildberries_marketplace_stocks_client.py`.

## Missing client methods (020)

- Batch `PATCH …/supplies/{id}/orders` (≤100) — today single-order PATCH only
- GET supply details + order IDs (reconcile)
- POST batch orders meta; DELETE meta
- GET trbx list; DELETE trbx
- Chunk splitters for orders/stickers/status (≤100)
- Typed `WildberriesBusinessError` + `MetaValidationFail` parser on 409
- Shared `_ensure_success(allow_empty=True)` for 204 endpoints

## Exists but untyped / risky

- `create_marketplace_supply` — always `.json()`, breaks on 204
- `fetch_marketplace_order_stickers` — no ≤100 cap
- `deliver_marketplace_supply` — 409 body discarded
- `add_orders_to_marketplace_trbx` — deprecate for operator flow

## Test file (new)

`backend/tests/test_wildberries_marketplace_fbs_client.py` — mirror stocks client tests:
MockTransport exact URL/body, 204, chunk 101→2, 409 MetaValidationFail, timeout, 429 no-retry-on-409.

## Emulator note

Emulator uses single-order PATCH; client targets batch contract per BACKEND_CONTRACT; emulator fix → FBSFLOW-120.
