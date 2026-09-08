# WMS-396: Claude Opus CLI max review

Model confirmed in modelUsage: claude-opus-4-7. Read-only CLI review, permission-mode plan, no code edits. CLI emitted plan-tool caveat but full review result below. Checkpoint diff16872296, actual source had subsequent fixes while reviewing. Claims require independent validation.

I don't have `Write` in this session's toolset, so I can't create the plan file at the path Plan Mode indicated — nor can I call `ExitPlanMode`. What I can do is deliver the review inline. Everything below is grounded in the diff and the current worktree at `codex/wms396-stage` (base `693ac992`, head `16872296`). Model: **claude-opus-4-7**.

## WMS-396 review — independent senior pass

### Introduced by WMS-396

#### P1 · Loose "introduced" gate for the undocumented CRPT mobile endpoint

- Where: `backend/app/services/inbound_marking_service.py:298`
- Trigger: response has `outerStatus == "INTRODUCED"` and `checkResult is True`, but `codeResolveData.verified` is missing (`None`) or `codeResolveData` is absent entirely.
- Harm: the code is painted green ("Код введён в оборот") without an explicit cryptographic-signature confirmation. The endpoint is not documented as an integration API and its contract can shift underneath us — a downgraded/degraded response that omits `verified` would silently pass. This is exactly the "verified=true from mere valid=true" case the brief flags.
- Minimal fix: tighten the guard —
  ```python
  elif (
      outer == "INTRODUCED"
      and data.get("checkResult") is True
      and resolved.get("verified") is True
  ):
      result.update(status="introduced", reason="Код введён в оборот")
  ```
  If the current mobile endpoint always returns `verified: true` for genuine INTRODUCED codes, this is a no-op today; if the contract changes it stays honest. The parametric test at `backend/tests/test_inbound_marking.py:934-969` already asserts `verified: False → problem`, but has no case for missing `verified` — add one.

#### P2 · Wrong error code for "same receipt, different line" rescan

- Where: `backend/app/services/inbound_marking_service.py:206-221`
- Trigger: same KIZ scanned twice within one receipt — first bound to line A, then rescanned while `lastProductScan` points to line B.
- Harm: the branch that expected "another receipt" fires with code `marking_code_other_receipt`; the frontend maps that to "Этот код уже записан в другой приёмке" (`frontend/src/screens/ff/inboundMarkingCodes.ts:1602`), sending the operator hunting for a phantom other receipt. Behaviour is correct (refusal), the diagnosis is not.
- Minimal fix: split into a new code (e.g. `marking_code_line_mismatch`) when `meta.get("request_id") == str(req.id)` and map to "Код уже отсканирован на другой строке этой приёмки".

#### P2 · `run_check_job` error recovery loses `job.failed` if `_request` throws

- Where: `backend/app/services/inbound_marking_service.py:398-413`
- Trigger: request/tenant deleted (or any `_request` failure) while the check is running. Outer `except Exception:` opens a new session, sets `job.status = "failed"`, then calls `_request(...)` which throws again. The `async with SessionLocal()` unwinds and the transaction rolls back — the intended `failed`/`finished_at` write is discarded.
- Harm: job stays `pending`/`running` until the 1-hour stale window in `list_codes` (`inbound_marking_service.py:138-146`) declares it dead. During that window `checking: true` is reported to the UI, the polling loop keeps hitting the API, and a re-schedule from `post` refuses to supersede it (`schedule_check` line 317-320 short-circuits on active-and-fresh).
- Minimal fix: finalise the job before touching events —
  ```python
  await session.commit()  # persist failed
  try:
      req = await _request(...)
      ...  # best-effort per-event marking
      await session.commit()
  except Exception:
      logger.exception(...)
  ```

#### P2 · Second `schedule_check` (after `post`) wipes previous cz_check to "pending"

- Where: `backend/app/services/inbound_marking_service.py:327-330`
- Trigger: `complete-receiving` schedules and completes job A; operator immediately triggers `post`; `schedule_after_posting` fires, `schedule_check` sees no active job (A is `done`), then unconditionally overwrites every event's `meta["cz_check"] = pending` before creating job B.
- Harm: the UI flips previously-green/red rows back to "Ожидает проверки" until job B finishes. If job B never completes (worker crash), the good verdicts stay lost for the 1-hour stale window. Also wasted CRPT round-trips on codes already answered a few seconds earlier.
- Minimal fix: only reset `cz_check` for events whose current cz_check is missing or older than N minutes, or short-circuit the second `schedule_check` when the last check completed recently (e.g., `finished_at` within 5 min).

#### P2 · Marking panel invisible in `sorting` workspace and to non-admin scanners

- Where: `frontend/src/screens/ff/FfInboundRequestView.tsx:521` (`enabled = isFulfillmentAdmin && workspace !== 'sorting'`) plus the admin gates at `:2486`, `:2497`.
- Trigger 1 (workspace): operator finishes receiving, moves to the sorting workspace; `useInboundMarkingCodes` is disabled, so previously-attached codes are not shown, the Excel button and re-check button do not render, and the row expanders disappear.
- Trigger 2 (staff): `require_reception_access` (`backend/app/api/deps.py:245`) allows FULFILLMENT_STAFF with `PERM_RECEPTION`. Such a staff user can call `POST /marking-codes/scan` via `marking.attach` (the hook exposes `attach` regardless of `enabled`), but their `marking.items` is never populated (load is gated by `enabled`) and the panel is admin-only.
- Harm: the operator who did the scanning cannot verify results in the sorting workspace; staff scans succeed silently with no on-screen list.
- Minimal fix: allow the hook whenever the endpoint is callable (drop the `!== 'sorting'` gate at least when `marking.items.length > 0`), and drop the `isFulfillmentAdmin` gate around the panel (or replace with the same permission the backend enforces).

### Pre-existing / baseline, surfaced by WMS-396

#### P2 baseline · No index on `MarkingCodeEvent.document_number`

- Where: migration `backend/alembic/versions/20260626_0044_marking_code_events.py:53-65` (only `tenant_id`, `code_id`, `pool_id`, `packaging_task_id`, `created_at` are indexed).
- Trigger: `_attachments` filters by `(tenant_id, document_number, event_type)`; nulls are common (`InboundIntakeRequest.document_number` is nullable at `backend/app/models/inbound_intake.py:87`), catalog imports also write `EVENT_IMPORTED` rows into the same table.
- Harm: as tenants age, `list_codes` and `attach_code` scan a growing slice of the tenant's event partition and then filter in Python by `request_id in meta_json`. Correctness is fine; latency is not.
- Minimal fix: add a composite `(tenant_id, event_type, document_number)` index, or drop the `document_number` predicate and rely on `(tenant_id, event_type, code_id)` + the in-Python meta check for the receipt scope.

### Confirmed correct / adequate

- **Received codes cannot enter the print pool**: `pool_id` is never set on reception (`inbound_marking_service.py:243-257`); pool selects filter `pool_id IS NOT NULL` (`marking_code_service.py:2326`).
- **Single-use in FBS/Ozon**: `is_unbound_received_code` (`marking_code_service.py:3705-3729`) requires `source == external_fbs`, `status == APPLIED`, no `packaging_task_line_id`, no `pool_id`, no `FbsOrderMarking`, and a reception `EVENT_IMPORTED` with `request_id`. On the first bind `packaging_task_line_id = line.id` is set (`fbs_kiz_service.py:1011-1014`, `ozon_kiz_service.py:97-98`); the second claim fails `is_unbound_received_code`, hits `status != AVAILABLE`, and raises `duplicate_kiz`.
- **`qty_marking_printed` not inflated for received codes**: `_prepare_code_for_binding` returns `(code, not received)` → `from_pool=False` for received, so `fbs_kiz_service.py:1380-1384` bumps `qty_marking_external`, not `qty_marking_printed`; Ozon does the same at `ozon_kiz_service.py:241-244`.
- **Ordinary FBS/Ozon flows unchanged**: for non-received codes `is_unbound_received_code` returns False and the original `status != AVAILABLE → duplicate_kiz` check runs (`fbs_marking_service.py:605-611`, `fbs_kiz_service.py:810-812`, `ozon_kiz_service.py:96-101`).
- **Void semantics preserved**: `_void_existing_sgtin_marking_locally` still sets `STATUS_VOID` and decrements `qty_marking_external` for `source == external_fbs` (`fbs_kiz_service.py:1089-1100`). VOID codes fail `is_unbound_received_code` (status gate) so they cannot be reused via reception.
- **Reception scan has no inventory effect**: `attach_code` writes `MarkingCode` + `MarkingCodeEvent` only. Test `test_attach_preserves_full_code_qty_and_idempotency` asserts zero `InventoryMovement`.
- **Post-failure never undoes stock**: `complete_receiving`/`post_all_remaining` commit stock before `schedule_after_posting` runs (`inbound_intake_service.py:1267`, `:1400`); `schedule_after_posting` catches every exception and rolls back only its own session state (`backend/app/api/inbound_marking.py:149-157`). Test `test_failed_check_scheduling_cannot_undo_posting` proves the endpoint returns 200 with status=sorting and the `InventoryMovement` remains even when `schedule_check` raises.
- **Idempotent attach + insertion race**: `MarkingCode` unique on `(tenant_id, cis_code)`; the same code+line+request short-circuits at `inbound_marking_service.py:216-220`; concurrent inserts across receipts race on the constraint and are rewritten to `marking_code_other_receipt` (`:258-261`). Row-lock on the receipt (`_request(lock=True)`) serialises attaches within one request.
- **Rapid scan ordering**: `createSerialScanQueue` (`frontend/src/screens/ff/inboundReceivingRuntime.ts:38`) serialises handlers; the KIZ path reads `lastProductScan.current` set inside the previous queued POST resolution (`FfInboundRequestView.tsx:1726`); `FfInboundBoxAddDialog.tsx:1298` mirrors the same pattern via `lastProductLineId.current`.
- **GS bytes end-to-end**: `useBarcodeScanner.ts:184` marks GS with `prevented: true` so it is excluded from focused-input cleanup (`:232`) but preserved in the normalized payload (`:219-221`); backend `normalize_scanned_code` keeps `\x1d`, rejects other control chars, and caps at 512 (matching `String(512)`).
- **Excel is only problematic codes, injection-safe**: `export_problems` filters `cz_status in {problem, unavailable}`, escapes GS to `\u001d`, forces `data_type = "s"` and `number_format = "@"` (`inbound_marking_service.py:416-436`). Test `test_xlsx_only_problems_keeps_codes_as_text` asserts `"=1+1"` stays as text and only 2 of 4 rows appear.
- **Unknown/network never green**: `interpret_check` defaults to `unavailable`, downgrades known bad `outerStatus` to `problem`, treats non-dict payload as `unavailable`. HTTP errors and JSON errors map to `unavailable` with "Честный знак недоступен" (`inbound_marking_service.py:372-374`). Parametric tests cover unknown outer, non-dict payload, and offline transport.
- **HTTP outside DB transaction**: per-code loop opens `SessionLocal` briefly to read `cis_code`, closes it, then does `client.post`, then opens a new session to write meta (`inbound_marking_service.py:358-384`); `timeout=10.0` per request, 250 ms rate-limit between codes.
- **Async job semantics**: `SELECT ... FOR UPDATE` on `BackgroundJob` at the pending→running edge rejects double-delivery (`inbound_marking_service.py:344-348`); stale jobs (>1h) are marked `unavailable` in `list_codes` and superseded by the next `schedule_check` (`:138-146`, `:316-322`).
- **Tenant/seller/product isolation**: every query filters by `tenant_id`; `attach_code` checks `code.seller_id == product.seller_id` and `code.product_id in (None, product.id)` before writing (`:203-205`); `list_codes` joins `MarkingCode` with `Product` under matching `tenant_id`.
- **Effective quantity includes containers**: `effective_actual_qty` (`inbound_intake_service.py:94-111`) sums loose + container quantities while receiving; `attach_code` uses that cap (`inbound_marking_service.py:225-227`).
- **Cross-service consumers**: `count_available_for_product` (`marking_code_service.py:1514-1529`) and `_pool_status_counts` (`:2311-2340`) both filter by `status == AVAILABLE` and/or `pool_id IS NOT NULL`, so reception codes (APPLIED, pool_id NULL) never appear in stock/pool figures.

### Non-issues explicitly checked

- Added `execution_options(populate_existing=True)` on the Ozon FOR UPDATE row is defensive, not behavioural.
- `code.product_id = product.id` at `inbound_marking_service.py:262` is safe — preceding check limits to `None`/`product.id`.
- `_active_job`'s Python-side filter is bounded (`tenant_id + job_type + status in {pending,running}`) — acceptable size in practice.
- The `_meta(event)["line_id"]` read in `_item` cannot KeyError from other flows: only reception events with `request_id` in meta survive the `_attachments` filter, and reception writes always include `line_id` (`:270-272`).

### How to verify end-to-end (when the freeze lifts)

1. Bring up backend + frontend against staging (`./scripts/railway-staging-deploy.sh`) or local docker.
2. Create a receipt, put it into `receiving`, scan a product barcode twice (qty should become 2), then scan a real 010…21…GS-91… KIZ — line quantity must stay 2, KIZ must appear as a child row with status "Ожидает проверки".
3. Complete receiving via the button — the response should be 200 with `status: sorting`. Poll `/marking-codes` and see items transitioning to `introduced`/`problem`/`unavailable`.
4. Force a `problem` verdict (use one of the known-bad codes mentioned in the WMS-396 backlog entry, or monkeypatch the endpoint) — the row must go red, the ! tooltip must show the Russian reason, and only that row must appear in `problems.xlsx`.
5. Kill the local worker mid-check — the row must not stay pending forever; after 1 h `list_codes` reports `unavailable` and `checking: false`.
6. Attach a reception code, complete the receipt, then bind that code to a WB order via the packaging flow — it must be accepted once (external counter +1, printed counter unchanged) and rejected on the second attempt as `duplicate_kiz`.
7. Backend targeted tests: `cd backend && pytest -n auto tests/test_inbound_marking.py tests/test_fbs_kiz.py tests/test_marking_ledger_external.py`. Frontend: `cd frontend && npm run test:unit -- useBarcodeScanner inboundMarkingCodes && npx tsc --noEmit -p tsconfig.app.json && npm run build`. UI check must be by hand in a browser per project rules.

If you want this dropped into `/Users/deniscivkunov/.claude/plans/review-wms-396-implementation-as-memoized-hummingbird.md`, you'll need to write it there yourself or give me a session with a Write tool — I do not have one here, and I also cannot call `ExitPlanMode`, so the plan phase can't be closed from my side.
