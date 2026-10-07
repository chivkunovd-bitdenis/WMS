# WMS-675 native recovery adapter preparation

Prepared only; NEVER executed by this developer. Source branch base4164430a,
normal installed backend4c532f0cccfb8f99b34d68d9630a3763038fbc5f. This is an adapter
around accepted native662 services, not an app/guard/test/requirements correction.
No deployment/recovery/acceptance claim. Sole integrator reviews the published ref,
actual producer and source/copy hashes, then explicitly supplies --execute.

The five literal scope IDs and unchanged31-position matrix come from fresh416.
Historical26 is NOT a new delta: fresh proof26, conducted12, missing14. Current
native locked delta may be0..14; the original12 expenses/movement IDs must survive.
All26 facts/52 charges already exist; their IDs/quantities/null amounts must remain
unchanged. No15 new facts or30 extra charges are synthesized.

Adapter flow:
1. Validate exact source/scope arguments, adapter/binding/input hashes; without
   --execute stop NOT_EXECUTED before app imports, provider or DB. With execute,
   require normal /app and17 installed native files equal exact4c; imported critical
   functions must resolve to those normal package paths. No runtime/flags/key/role
   changes, no new Session implementation or source-copy application.
2. Run the UNCHANGED published Ozon reader+plan in normal configured app before
   stock locks. Normal31 semantic POST /v3/posting/fbs/get; no retries/ship/sign/print.
   Its existing maximum124 related cards is unchanged; adapter accepts ONLY31,
   children0/unknown0/HTTP200, exact composition/scope/warehouse/status vs fresh416.
   Any additional related card or status change stops before checkpoint/stock writes.
   Reader output is sanitized; process stdout/stderr content discarded, only hashes.
3. Load native orders/product_positions; actual ozon_targets with an object whose
   fetch_statuses rejects further network, then actual make_observation. No forced
   targets. Native save_observations commits the existing observed checkpoint
   separately. PENDING/RETURNED outcomes saved before/after the critical call.
4. Native lock_order_batch_packaging_rows, recheck31 parent scope, then native
   lock_handoff_batch_products. Reread scope and ledgers/reserves/balances/billing/
   facts under those locks, including ledger row locks. Fixed published SELECTs
   only; no direct SQL mutations. Reject scope/status/recipe/source/children changes,
   reversals/over-proof expense, missing prior IDs/unattributed movements/insufficient
   sorting stock or changed52 charges/26 facts. Check durable checkpoint targets
   and scopes exactly match native fresh observations; cancel5 targets excluded.
5. Recompute actual completed through native completed_quantities. Call ordinary
   conduct_supply if missing>0; never assign status/date/reserve or manually publish.
   Save sanitized read snapshots including partial returns before postcondition
   failures. Require no native business error, missing0, preserved old movement IDs,
   exactly the newly needed unit movements/delta, exact balance decrement and
   position reserves0, unchanged52/26 IDs/quantities/null amounts. Otherwise no
   outer stock commit; checkpoint may already be durable.
6. Record outer COMMIT_PENDING then await normal commit; exceptions after attempted
   commit are UNKNOWN requiring independent readback, never retried or claimed
   rolled back. Before commit, session-exit rollback is recorded. Native publication
   is NOT suppressed. Finally call actual drain_background_stock_publish_tasks
   (also after uncertain commit), no extra manual publish pass. Drain has no broker/
   provider success receipt; external publication remains independently unverified.
   Its normal native swallowed/logged task errors cannot be converted into a
   publication-success claim by this adapter.

Only sanitized state/phases/proofs/read snapshots are saved. Unexpected exception
messages/traces/payloads/credentials are omitted; type/safe code retained. Native
business error presence is explicit; unknown codes are censored, not waived.
Crash while a critical phase is pending requires readback, not an automatic retry.
Complete validation before a checkpoint does not guarantee later stock commit.

Checks performed locally: AST parse/compile ONLY,14 byte-identical published input
bindings and17 exact4c native SHA256 bindings. No adapter module/app/provider/DB
execution, no tests/deps. source-bindings.json and preparation.json contain exact
identities; all SQL copies are original reviewed SELECTs. Functional execution is
UNTESTED here; integrator scope review remains necessary. Independent11-query
normal tenant-role accounting readback after actual execution is required.

Copy this WHOLE directory from the exact published SHA into the integrator's own
private production-container temp (not /app source/config). Run INSIDE that normal
installed /app environment after its source identity check. This command is for the
SOLE integrator; it was not run by the developer. Output must be a NEW directory.

```sh
package=/tmp/wms675-native-recovery-adapter-20261007
PYTHONPATH=/app python -B "$package/adapter.py" \
  --execute \
  --source-sha 4c532f0cccfb8f99b34d68d9630a3763038fbc5f \
  --adapter-sha256 5d290b28419c72389a85a2f518efcdbf612c43c49d43f62e048dd5c3bf427535 \
  --bindings-sha256 a4e59a459c92c9fadf93455be1669d8cdd0a7be9028d397fd902766b49885e6d \
  --tenant-id b80a893b-ab87-42b6-8fd7-6d41502c900f \
  --seller-id cf6d31c5-944b-4382-af34-636ca9aa8cc3 \
  --supply-id b82d1e9a-30d2-4d7b-b52d-9775c3d266e3 \
  --warehouse-id 2d968c65-4a8d-414e-9076-0f201c2dba63 \
  --sorting-location-id 7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1 \
  --output "/tmp/wms675-native-result-$(date -u +%Y%m%dT%H%M%SZ)"
```

Omit --execute for input-only NOT_EXECUTED (no live reads/writes). Do not preserve
unsanitized process logs. Preserve adapter's entire sanitized output into permanent
Git evidence. No public release/physical shipment/print/client message follows from
preparation. Common/607/product/protected files unchanged; only this docs directory.
