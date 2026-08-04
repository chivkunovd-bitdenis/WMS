# OpenAPI — FBS operator flow

> **Task:** FBSFLOW-130. **Source of truth for wire shapes:** `BACKEND_CONTRACT.md` + `FRONTEND_TASKS.md`.  
> This file documents how to regenerate the exported schema and which paths belong to the operator contract.

## Export

From repo root:

```bash
cd backend && .venv/bin/python scripts/export_fbs_openapi.py
```

Output: [`openapi/fbs-operations.openapi.json`](./openapi/fbs-operations.openapi.json) — live FastAPI OpenAPI filtered to `/operations/fbs-*` paths only.

Gate test: `backend/tests/test_fbs_openapi_contract.py` (requires export file committed after API changes).

## Error envelope (new contract paths)

Structured errors use:

```json
{
  "detail": {
    "code": "order_incompatible",
    "message": "Заказ нельзя добавить в выбранную поставку.",
    "context": { "order_id": "uuid", "reasons": ["different_wb_warehouse"] },
    "retryable": false
  }
}
```

**New operator contract paths** (table below) always return the structured envelope above — never a bare string `detail`.

**Legacy compatibility layer** (deprecated in OpenAPI): `POST …/stickers`, `POST …/trbx/stickers`, `GET …/barcode`, create+add-order, `POST …/trbx/{id}/orders` (410). These may still expose `sticker_file` / `barcode_file` only as internal compatibility fields; frontend must use **print-assets** + authorized binary content URLs, never treat paths as base64 or public URLs.

## Contract paths (operator gate)

| Area | Method | Path | Notes |
|------|--------|------|-------|
| Worklist | GET | `/operations/fbs-orders/worklist` | Enriched rows, `selection_blockers`, `server_now` |
| Preflight | POST | `/operations/fbs-supplies/preflight` | Always 200 with `compatible` + `issues` |
| Create supply | POST | `/operations/fbs-supplies/from-orders` | Atomic WB supply + batch add; idempotent |
| Workspace | GET | `/operations/fbs-supplies/{supply_id}/workspace` | Stage, progress, blockers, full orders |
| Start work | POST | `/operations/fbs-supplies/{supply_id}/start-work` | Idempotent `PackagingTask` |
| Pick location | POST | `/operations/fbs-supplies/{supply_id}/pick/scan-location` | |
| Pick product | POST | `/operations/fbs-supplies/{supply_id}/pick/scan-product` | Returns full workspace |
| Pick undo | POST | `/operations/fbs-supplies/{supply_id}/pick/{order_id}/undo` | Before pack only |
| Metadata | GET | `/operations/fbs-orders/{order_id}/metadata` | WB required/optional meta |
| Metadata scan | POST | `/operations/fbs-orders/{order_id}/metadata/scan` | GS-preserving scanner path |
| Print batch | POST | `/operations/fbs-supplies/{supply_id}/print-assets` | Stickers / cargo QR / supply QR |
| Print content | GET | `/operations/fbs-print-assets/{asset_id}/content` | Authorized binary |
| Print applied | POST | `/operations/fbs-print-assets/{asset_id}/applied` | Sticker/QR applied audit |
| Cargo preflight | POST | `/operations/fbs-supplies/{supply_id}/cargo-places/preflight` | PVZ dimensions |
| Cargo create | POST | `/operations/fbs-supplies/{supply_id}/cargo-places` | **Count only** — no `order_ids` |
| Cargo list | GET | `/operations/fbs-supplies/{supply_id}/cargo-places` | Reconcile with WB |
| Delivery preflight | POST | `/operations/fbs-supplies/{supply_id}/delivery-preflight` | Fresh WB sync + version token |
| Deliver | POST | `/operations/fbs-supplies/{supply_id}/deliver` | Requires preflight version + idempotency |
| Tracking sync | POST | `/operations/fbs-supplies/{supply_id}/sync-tracking` | Post-delivery status refresh |

## Deprecated (do not use in new frontend)

| Method | Path | Replacement |
|--------|------|-------------|
| POST | `/operations/fbs-supplies/{supply_id}/trbx/{trbx_id}/orders` | **410/deprecated** — count-only cargo places; no order→trbx mapping |
| POST | `/operations/fbs-supplies/{supply_id}/stickers` | **deprecated compatibility** — still returns `sticker_file` paths; use `POST …/print-assets` + `GET …/content` |
| POST | `/operations/fbs-supplies/{supply_id}/trbx/stickers` | **deprecated compatibility** — use `print-assets` with cargo QR kind |
| GET | `/operations/fbs-supplies/{supply_id}/barcode` | **deprecated compatibility** — supply QR via print-assets after deliver (warehouse/sc) |

## Examples

Request/response examples with field semantics live in `BACKEND_CONTRACT.md` §2–13. Exported OpenAPI carries Pydantic schemas from route models; when in doubt, **BACKEND_CONTRACT wins** for operator-visible JSON names.
