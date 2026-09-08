# WMS-272: первоначальный Opus CLI max review

Этот отчёт относится к 8baa351f, до исправлений 08f2ac39/12c230bd. Все выводы сверены независимо в wms272-adjudication-20260908.md; рекомендации ревью не принимались автоматически.

I don't have Write or Edit tools available in this session, so I can't create the plan file at the requested path. I'll deliver the full read-only review here instead, structured as the plan file would have been. My review is grounded strictly in what I read from the working tree at `codex/wms272-finish` (SHA `8baa351f`) versus the earlier state on `main` (SHA `693ac992`), the diff at `tmp/review272/change.diff`, and the internal report at `docs/reviews/wms272-finish-20260908.md`. No live API, no data, no code edits, no tests were run.

---

# WMS-272 Finish — Independent Read-Only Review

**Range:** `8baa351f` vs `693ac992`
**Model:** claude-opus-4-7 (Claude Code CLI, Opus 4.7 — real metadata)
**Mode:** plan-mode, read-only tool set only (Glob, Grep, Read).

## Context

The change moves the WB `create_supply_from_orders` path off a session-scoped PostgreSQL advisory lock and onto a **transaction-scoped** advisory lock on the same key (`marketplace_seller_lock_service.py:39-70,82-104`). Setup (validation, `create_pending_operation`, draft `FbsSupply`) still runs inside the lock; then `session.commit()` runs **outside** the lock block at `fbs_supply_service.py:774`, atomically releasing the xact-lock *and* returning the connection to the pool before HTTP starts. The obtained WB supply id is persisted with a second commit at `fbs_supply_service.py:822-830`, so a retry can resume the exact same supply. Ozon still uses the session-scoped lock (`transaction_scoped=marketplace == "wb"` at `fbs_supply_service.py:656`). `_bind_orders_to_supply` gains WB-only skip rules so a cancellation/later step committed during HTTP is never rewound (`fbs_supply_service.py:333-347`). `_ensure_orders_not_in_pending_create` (`fbs_supply_service.py:530-554`) guards the seller's overlapping order-set instead of the whole seller. The legacy empty-supply create commits before HTTP too (`fbs_supply_service.py:1284`).

The mechanical claim ("no DB connection during HTTP; same-key mutex; existing durable operation is what claims overlapping orders") checks out against the code I read. The mutex is genuine — both `pg_try_advisory_lock` and `pg_try_advisory_xact_lock` share the PostgreSQL advisory-lock keyspace, so an xact-lock and a session-lock on the same key exclude each other (`marketplace_seller_lock_service.py:53-63`; verified against every session-lock caller in `fbs_wb_seller_lock_service.py`, `fbs_autopoll_service.py:566,683,786`, `fbs_shipment_service.py:1898`, `fbs_stock_publish_service.py:58`, `fbs_warehouse_binding_service.py:273`). Ozon path is unchanged (`transaction_scoped=False`, `release_connection_while_waiting=False`, and the marketplace-guarded skip block at `fbs_supply_service.py:668-676,756-768`).

Below are the concerns I can substantiate from the code. Nothing rises to a P0 blocker for basic FBS or navigation gates — no new entities, statuses, journals, TTLs or packing/nav gates are introduced.

---

## P0 — none confirmed

I could not confirm any P0 (functional break of FBS, new packing/navigation gate, new entity/status/journal/TTL) from reading the code. The mechanical fix works and Ozon is genuinely untouched.

---

## P1 — real regressions worth addressing before shipping

### P1-1. Stuck operation with `wb_object_id=None` blocks the order set permanently, with no UI/automatic escape

**Where.** `fbs_supply_service.py:797-820` (except branch on WB create failure) and the guards it interacts with: `fbs_supply_service.py:530-554` (`_ensure_orders_not_in_pending_create`), `fbs_supply_service.py:1047-1061` (`_resume_from_orders_operation` refuses `wb_object_id is None`), `fbs_supply_composition_service.py:204-206` and `fbs_supply_service.py:1551-1558` (repair refuses `PENDING-*`), plus frontend mapping absence at `frontend/src/screens/v2/fbsUx.ts:109-114,126`.

**Trigger.** Any of these outcomes from `create_marketplace_supply`:

- `WildberriesClientError` with `status_code is None` (transport/timeout — `wildberries_errors.py:104-119`),
- WB 5xx or 408 (grouped with transport by the `if exc.status_code is not None and 400 <= exc.status_code < 500 and exc.status_code != 408` branch),
- `"invalid_response"` synthesized when WB returns 200 with no id (`fbs_supply_service.py:794-796`),
- client cancellation between the `session.commit()` at `fbs_supply_service.py:774` and the `session.commit()` at `fbs_supply_service.py:830`.

In every case the operation ends up with `state=pending / pending_confirmation`, `wb_object_id=None`, `local_entity_id=supply.id`, and a draft `FbsSupply` whose `wb_supply_id="PENDING-{op.id}"`.

**Harm.** From that state:

- `_resume_from_orders_operation` short-circuits with `operation_incomplete` (`fbs_supply_service.py:1047-1061`). The frontend has **no** UI mapping for that code and `fbsDeliveryErrorKeepsIdempotencyKey` does **not** list it (`fbsUx.ts:109-114`), so the client will rotate the idempotency key on retry.
- A rotated key triggers `_ensure_orders_not_in_pending_create` → `operation_in_progress` 503 (retryable=True). The frontend *does* keep the key for `operation_in_progress`, so subsequent retries with that key loop back through the same guard forever.
- Manual `POST /fbs-supplies/{id}/repair-from-wb` also refuses because `supply.wb_supply_id.startswith("PENDING-")` raises `supply_without_wb_id` (`fbs_supply_service.py:1552-1558` and `fbs_supply_composition_service.py:204-206`).
- Autopoll's `repair_pending_supplies_for_seller` (`fbs_supply_service.py:1637-1688`) uses the same key from a different session, so it will always find the lock busy when called from within autopoll's own outer lock and skip — see also P2-3.

Net effect: orders in a stuck operation cannot be added to any other supply and cannot be freed without a DB write. This is a **new, permanent, operator-visible block** that did not exist before WMS-272.

**Baseline comparison.** Prior to WMS-272 the WB-create failure path called `mark_operation_failed` (see the removed lines around `fbs_supply_service.py:706-712` in `tmp/review272/change.diff:187-195`). A retry with a fresh key then succeeded (at the known cost of a possibly orphaned WB draft, since we would send another POST). That trade — "occasional orphaned WB supply" vs "permanent block on operator's own orders" — is a real product decision the report acknowledges ("восстановление неизвестного WB ID требует сверки") but neither the backend nor the frontend offers a way to resolve it.

**Minimal fix.** Add exactly one of:

1. A tiny API to abandon a stuck attempt — e.g. `POST /fbs-supplies/from-orders/{operation_id}/abandon` that transitions the operation to `failed` and deletes the empty draft; **no new column or status is required**. `_ensure_orders_not_in_pending_create` already skips `failed`. This is one endpoint + one DB write.
2. Or: extend `_resume_from_orders_operation` to re-issue the create POST when `operation.wb_object_id is None` and record the new wb_supply_id under the *same* operation row. Accepts the same "possible orphan" risk the old code had, in exchange for keeping operator workflow unblocked. Still no new entity.

Whichever is picked, `frontend/src/screens/v2/fbsUx.ts` must map `operation_incomplete` and keep the same idempotency key for it (add to the `fbsDeliveryErrorKeepsIdempotencyKey` set) so the retry actually hits the resume path.

---

### P1-2. Manual `repair-from-wb` races with mid-flight create between "wb id saved" and "add-orders finished"

**Where.** Endpoint `fbs_supplies.py:1137-1160` invokes `repair_supply_composition_from_wb` without any advisory lock. Inside, `_close_pending_operation_if_complete` (`fbs_supply_service.py:1507-1530`) is triggered on empty `unresolved` and marks the operation `confirmed`. On the create side, `fbs_supply_service.py:822-830` commits `wb_supply_id`, `operation.wb_object_id=REALID`, `state=pending_confirmation` *before* `_execute_wb_batch_add` at `fbs_supply_service.py:842-847`.

**Trigger.** Between the 830 commit and the moment WB actually processes the batch-add, an operator (or another orchestrator, or a UI reload wired to repair) calls `repair-from-wb` on this supply. `reconcile_actual_wb_supply_composition` (`fbs_supply_composition_service.py:184-314`) reads the WB composition (still empty), sees local supply also empty of bound orders, produces `discrepancies=()`, hits `_close_pending_operation_if_complete(unresolved=[])`, and marks the operation `confirmed` with `response_summary={"wb_order_ids": [], "source": "repair_from_wb"}`.

**Harm.** When our create's `refresh_after_http` returns `True` at `fbs_supply_service.py:885` or `979`, the create returns `get_supply_workspace(...)` without ever calling `_bind_orders_to_supply` for the request's orders. WB eventually holds the added orders; the WMS supply is empty; the WMS orders remain in `status='new'`, `supply_id=None`. Silent desync, and the operator now sees a "confirmed" empty supply.

**Baseline comparison.** In the old code the operation and supply were not visible outside the create's transaction until the whole thing committed at the end, so this race was not observable. WMS-272 exposes the mid-flight `pending_confirmation` intentionally (so a retry can resume), which opens the window.

**Minimal fix.** Wrap `repair_fbs_supply_from_wb` (and any future callers of `repair_supply_composition_from_wb`) in `wb_seller_lock(session, supply.seller_id)` with a small `wait_timeout_sec`. That reuses the existing session-scoped lock — no new entity — and re-establishes mutual exclusion with the xact-scoped create claim on the same key. Autopoll's inner call (`fbs_supply_service.py:1665`) already does this.

---

### P1-3. `_close_pending_operation_if_complete` marks an operation `confirmed` on a trivially empty composition even though the request had a non-empty order set

**Where.** `fbs_supply_service.py:1507-1530`. The only precondition is `if unresolved: return`; the empty case (`wb_order_ids=[]`, no local links, no discrepancies) satisfies it trivially.

**Trigger.** Any repair (manual or, if the autopoll lock bug in P2-3 is fixed, autopoll) that runs against a `pending_confirmation` operation before WB has actually accepted any order for that supply. The most likely occurrence is the race in P1-2. It can also happen if `add-orders` fails after `wb_supply_id` is committed (`fbs_supply_service.py:848-957`) and later the operator manually clicks "repair from WB" while nothing has been added yet.

**Harm.** Same shape as P1-2: operation `confirmed` with empty response, supply empty, orders unbound. The `_close_pending_operation_if_complete` is a latent bug that predates WMS-272 (was safe because ops with wb id previously implied add-orders had been at least attempted), but the new mid-flight commit at line 830 makes it much more reachable.

**Minimal fix.** Skip closure when `operation.request_summary_json.get("order_ids")` is non-empty and `wb_order_ids == []`. One condition, no new column.

---

## P2 — smaller concerns / hygiene

### P2-1. Direct-assign of `state = pending_confirmation` with `wb_object_id is None` bends the helper contract

`fbs_supply_service.py:815-818` sets `operation.state = WB_OPERATION_STATE_PENDING_CONFIRMATION`, `operation.error_code = ...`, `operation.error_context_json = ...` inline, without going through `mark_operation_pending_confirmation` (`fbs_supply_reconcile_service.py:424-440`). The helper signature makes `wb_supply_id: str` mandatory precisely because every prior consumer assumed `pending_confirmation` implied a real WB id. Three downstream readers each defensively handle the new `None` case (`fbs_supply_service.py:1047-1061`, `fbs_supply_composition_service.py:204-206`, `fbs_supply_service.py:1552-1558`) — but the invariant is now silently waived. Prefer changing the helper signature to `wb_supply_id: str | None = None` and calling it from the create failure path, so the assumption is documented once instead of scattered.

### P2-2. `_bind_orders_to_supply` silently drops orders that changed state during HTTP

`fbs_supply_service.py:333-347` correctly skips orders that were cancelled, moved to a later stage, or already assigned to another supply. But when WB accepted all N orders and 1 slipped past locally, `mark_operation_confirmed` at `fbs_supply_service.py:889` (or `1021`) still records `response_summary={"wb_order_ids": sorted(confirmed)}` — the full WB set — while only N-1 are bound locally. There is no log or `partial_rejection` payload for this shape. A `logger.info(... skipped=%s reasons=%s ...)` inside the skip branch would make this at least observable to autopoll and to any future reconciliation.

### P2-3. Autopoll's `repair_pending_supplies_for_seller` is effectively disabled by its own outer lock

Not caused by WMS-272 — but relevant to why P1-1 is truly permanent. `fbs_autopoll_service.py:562-584,679-699,782-800` acquires `marketplace_seller_lock(lock_session, target.seller_id, target.marketplace)` on a *separate* `lock_session`. Then, inside, `sync_fbs_order_statuses_for_seller` (`fbs_autopoll_service.py:461-490`) calls `repair_pending_supplies` → `repair_pending_supplies_for_seller` (`fbs_supply_service.py:1637-1688`), which tries `wb_seller_lock(session, seller_id)` on the *work* `session`. Same PostgreSQL advisory-lock key, different SQL sessions ⇒ the try always returns `None` and the repair is skipped with `"lock_busy"`. This means the only working repair path today is the manual API endpoint. Worth fixing separately (either use `lock_session` for the inner repair, or drop the inner lock since the outer already covers it).

### P2-4. `refresh_after_http`'s "same-order" deadlock rationale is subtle

The comment at `fbs_supply_service.py:787-789` claims resume takes orders-then-operation, matching the new create path. That is what the code does today (`fbs_supply_service.py:1182-1183`). But `reconcile_actual_wb_supply_composition` acquires `select ... with_for_update` on `FbsSupply` first (`fbs_supply_composition_service.py:193-198`), then on `FbsOrder` (`fbs_supply_composition_service.py:231-243`). Since the create path never `SELECT ... FOR UPDATE` on `FbsSupply`, there is no cycle today — but the invariant "no path locks supply-then-orders while another locks orders-then-op" is one refactor away from breaking. A one-line comment on `_close_pending_operation_if_complete` and `reconcile_actual_wb_supply_composition` pointing back to the create's lock order would make this hard to lose.

---

## What is not changed (positive confirmations, from code)

- Ozon retains the session-scoped `pg_advisory_lock` path (`fbs_supply_service.py:650-656` selects `transaction_scoped=marketplace == "wb"` and `release_connection_while_waiting=marketplace == "wb"`). Ozon's `_bind_orders_to_supply` also skips the new WB-only branch (`fbs_supply_service.py:333-347`).
- No new tables, columns, statuses, TTLs, journals, or navigation blockers were introduced. `_ensure_orders_not_in_pending_create` reuses the existing operation's `request_summary_json.order_ids` rather than creating a lease or claim entity (`fbs_supply_service.py:530-554`).
- The `transaction_scoped` opt-in reuses the identical seller key derived from `marketplace_seller_lock_key(seller_id, marketplace)` (`marketplace_seller_lock_service.py:21-28,53-63`), so the mutex property with old session-scoped callers is genuine.
- The legacy empty-supply `create_supply` (`fbs_supply_service.py:1263-1314`) commits before the HTTP call — safe because no durable state exists yet.

## About the new tests

The two new PG-only tests (`backend/tests/test_fbs_create_http_connection.py`, `backend/tests/test_fbs_create_lock_connection.py`) plus `backend/tests/test_fbs_resume_connection.py` set `pool_size=1, max_overflow=0, pool_timeout=0.2` and interleave paused HTTP monkeypatches with observer `SELECT 1`. They prove the pool-release claim and the same-key session/xact compatibility claim mechanically. They do **not** exercise:

- Concurrent manual `repair-from-wb` racing against `add-orders` (P1-2, P1-3).
- Frontend key-rotation behaviour on `operation_incomplete` (P1-1).
- Autopoll → repair inner-lock failure (P2-3).

So the "41 passed" line in the report should not be read as coverage for those areas.

## How the user could verify these findings

- Read the exact ranges cited above (no additional file access needed).
- For P1-1: check that `frontend/src/screens/v2/fbsUx.ts` neither maps `operation_incomplete` in `FBS_ERROR_TEXT` nor lists it in `fbsDeliveryErrorKeepsIdempotencyKey`, and that no other UI recovery is wired up. Confirm no backend endpoint exists to abandon a stuck `pending`/`pending_confirmation` operation with `wb_object_id is None`.
- For P1-2/P1-3: simulate the sequence in a local shell against a scratch PG (not requested here; noted as a repro path, not run). The specific `_close_pending_operation_if_complete` behaviour is directly verifiable by reading `fbs_supply_service.py:1507-1530` against `fbs_supply_composition_service.py:184-314`.
- For P2-3: read `fbs_supply_service.py:1665` alongside `fbs_autopoll_service.py:562-584`; note the different `session`/`lock_session` arguments and the same key.

## Environment / provenance

- Working directory: `/Users/deniscivkunov/Projects/WMS/.worktrees/wms272-finish`, on branch `codex/wms272-finish` at `8baa351f`.
- Tools used: `Glob`, `Grep`, `Read` (all read-only). No network, no live API, no secrets, no code edits, no test runs, no MCP calls.
- `Write`/`Edit` tools were not exposed to this session, so the plan file at `/Users/deniscivkunov/.claude/plans/independent-read-only-review-snazzy-shell.md` could not be created; this response is the review in full.