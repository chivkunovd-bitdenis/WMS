# 2А back_guard baseline exception

`python3 scripts/ci/back_guard.py` was run without `--update`. It reports exactly
four new `файл-монолит` entries. The exception is one separate baseline commit after
the product commit; it changes no other baseline entry and does not normalize the
file wholesale.

| Source service | JSON line, before → after | Minimal writer reason |
|---|---|---|
| `backend/app/services/fbs_picking_service.py` | `818 → 893` | WB and Ozon canonical pick/undo transitions must create/reuse the immutable source fact at the terminal transition; moving that call out would lose the durable event/actor context. |
| `backend/app/services/fbs_supply_service.py` | `1747 → 1762` | The automatic WB completion path has the only authoritative supply/order/performer context for its pick fact. |
| `backend/app/services/inbound_intake_service.py` | `1891 → 1893` | The completed inbound/return transition is the only place that distinguishes the terminal source kind and preserves its actor. |
| `backend/app/services/marketplace_unload_service.py` | `1205 → 1226` | Shipped and cancel retry must preserve the original unload state and one-time cancellation actor while returning the same reversal source tuple. |

`packaging_task_service.py` is smaller (`1270 → 1244`) and needs no baseline entry.
No other `docs/backend-guard-baseline.json` record is permitted to change. The SHA
of the separate baseline commit is recorded after that commit is created.
