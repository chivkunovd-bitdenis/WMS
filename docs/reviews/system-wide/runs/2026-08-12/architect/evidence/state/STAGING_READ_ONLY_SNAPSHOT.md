# Sanitized staging read-only snapshot

Captured through the direct staging API on 2026-08-12 after the user explicitly authorized use of the existing staging login. Credential and token values were held only in process memory and were not printed or written.

This is existing staging data, not an isolated architect seed. It is therefore inventory-only evidence and was not mutated.

| Endpoint | HTTP | Sanitized result |
|---|---:|---|
| `/auth/me` | 200 | role `fulfillment_admin`; tenant present; no seller; permission keys: cells, inventory, mp_shipments, packaging, reception, settings, shift_lead |
| `/warehouses` | 200 | 2 rows |
| `/sellers` | 200 | 1 row |
| `/operations/inventory-balances/summary` | 200 | 20 rows |
| `/operations/inventory-movements` | 200 | 100 rows returned (endpoint default/limit may truncate total) |
| `/operations/inbound-intake-requests` | 200 | 5 rows |
| `/operations/outbound-shipment-requests` | 200 | 0 rows |
| `/operations/marketplace-unload-requests` | 200 | 5 rows |
| `/operations/packaging-tasks` | 200 | 11 rows |
| `/operations/fbs-orders/worklist` | 200 | 23 rows; no next cursor |

The snapshot proves that the authenticated API exposes all major deployed contours at commit `44fe72e…`. It does not prove correct UI behavior, state ownership, tenant isolation, successful mutations or live-WB correctness.
