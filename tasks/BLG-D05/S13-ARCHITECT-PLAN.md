# S13 ARCHITECT_PLAN - BLG-D05

## Verdict

`ARCH_PLAN_READY`

This plan implements the two atomic cards approved at S12 without changing the
operator UI or the marking-code lifecycle. It is a design artifact only: no
migration, data repair, code, production read, external call, commit, push or
deploy is performed at S13.

## Architectural decision

Keep link confidence separate from `marking_codes.status`.

- `status` remains the physical lifecycle (`available`, `reserved`, `printed`,
  `applied`, `introduced`, `shipped`, `transferred`, `defective`, `replaced`,
  `void`). Reconciliation must not invent lifecycle transitions.
- Add a nullable link-classification projection to `marking_codes`. `NULL`
  means the legacy row has not been brought under this reconciliation policy;
  it is not an implicit confirmation. Rows in the explicit BLG-D05 source
  population are written as `confirmed_link` or `review_required` by C2.
- `review_required` is a quarantine independent of lifecycle status. It is
  excluded from every count, selection, reservation, print, apply, transfer
  and shipment path even if lifecycle status is still `available`.
- `confirmed_link` requires one `product_id` selected by an immutable approved
  decision. A confirmed code in a shared pool is eligible only for that exact
  product, never for every product linked to the pool.
- Absence of a reconciliation row remains backward compatible for code outside
  the explicitly approved Denmarcs population. The source population is never
  inferred from the seller name, `OLD/`, SKU text, product name or timestamps.

The current `products` model has no durable `current` or `canonical` flag.
Therefore BLG-D05 must not infer that a product is current. For this incident,
every `OLD/` to current-card target used by `confirmed_link` must be present in
the data-owner-approved lineage register. Candidate generation may use GTIN,
but it cannot authorize a target.

## Resource graph

```text
approved source manifest + approved lineage manifest
  -> reconciliation run (tenant + seller + policy + immutable input hash)
    -> immutable per-code decisions and candidate evidence
      -> explicit run approval
        -> per-code locked apply transaction
          -> marking_codes link-classification projection + product_id
          -> append-only reconciliation event
            -> allocation/count filters
              -> packaging print / catalog print / FBS scan / replacement
            -> masked read-back and population reconciliation
```

### Existing resources to extend

- `backend/app/models/marking_code.py`: projection columns and reconciliation
  models/constants. Do not change existing lifecycle constants.
- `backend/app/models/__init__.py`: export the new models.
- `backend/app/services/marking_code_service.py`: one canonical eligibility
  predicate used by product code listing, inventory, pool totals, low-stock
  totals, single/batch available counts, packaging/catalog allocation and
  replacement selection.
- `backend/app/services/fbs_marking_service.py`: direct scan/claim must reject
  `review_required` and reject a `confirmed_link` for a different product.
- `backend/app/services/marking_low_stock_service.py`: consumes corrected pool
  counts; it must not independently count quarantined `available` rows.
- `backend/alembic/versions/<controller-allocated-next-revision>.py`: one
  additive migration. S17 must recompute the actual Alembic head immediately
  before allocating the filename because parallel workers may add revisions.

### New resources

- `backend/app/services/marking_code_reconciliation_service.py`: C1 inventory,
  approval, C2 apply, read-back and compensating restore. It is the only writer
  of reconciliation decisions/projection/events.
- `backend/app/cli/reconcile_denmarcs_marking_codes.py`: controlled command with
  `inventory`, `approve`, `apply`, `read-back` and `restore` subcommands.
  Outputs structured sanitized JSON and never prints a raw CIS/DataMatrix.
- `backend/tests/test_marking_code_reconciliation_inventory.py`: C1 behavior,
  deterministic identity and population totals.
- `backend/tests/test_marking_code_reconciliation_apply.py`: C2 atomicity,
  idempotency, stale input, quarantine, read-back and restore.
- `backend/tests/test_marking_code_reconciliation_isolation.py`: tenant/seller
  negative authorization and non-disclosure.
- Existing marking pool, inventory, product-code, print, replacement and FBS
  marking tests are regression surfaces and must be extended where the shared
  eligibility predicate changes behavior.

### Explicitly unaffected resources

- Routes/API: no new public or operator route. The controlled CLI is the
  invocation boundary; adding an API later requires a new contract and route
  tests.
- Frontend/screens/ui-kit: no change.
- Celery/Redis/queues: no background worker. The known population is small and
  a restartable CLI avoids adding the `background_worker` trait. Parallel CLI
  invocations are serialized by database ownership of each decision row.
- Mobile, print layout, WB/Ozon/Denmarcs external systems and product deletion:
  no contract or call changes.

## Additive data model

### `marking_code_reconciliation_runs`

One immutable-input inventory/apply unit:

- `id`, `tenant_id`, `seller_id`, `policy_version`;
- `source_kind`, masked `source_reference`, `source_manifest_sha256`;
- `lineage_manifest_sha256`, `decision_input_hash`;
- projection status (`inventory_ready`, `approved`, `applying`, `completed`,
  `partial`, `restore_completed`) and timestamps;
- requested/approved actor IDs and an external approval reference;
- frozen source, confirmed, review-required, skipped and error totals.

Unique key: `(tenant_id, seller_id, policy_version, decision_input_hash)`.
The same inputs return the existing run; changed source or lineage evidence
creates a new run and cannot reuse old approval.

### `marking_product_lineage_decisions`

Append-only data-owner decisions:

- tenant, seller, historical product, current target product;
- canonical 14-digit GTIN used for comparison;
- action (`approved` or `revoked`), policy version, evidence hash, approval
  reference, actor, timestamp and optional `supersedes_id`.

There is no update-in-place. The active lineage is the latest valid decision
in one supersession chain. Both products are loaded through tenant-and-seller
scoped predicates before a row is accepted. `OLD/` is descriptive evidence
only and never a lookup rule.

### `marking_code_reconciliation_decisions`

Immutable C1 decision register, one row per `(run_id, code_id)`:

- code UUID plus a stable fingerprint derived from tenant ID, code UUID and
  policy version for sanitized output; no copied raw CIS value and no new
  secret/key dependency;
- source import/pool references and source artifact hash when available;
- prior lifecycle status, product link and link classification;
- canonical code GTIN, candidate product IDs and per-rule evidence booleans;
- selected target, lineage-decision ID, proposed classification, reason code;
- `precondition_hash` over all mutation-relevant inputs;
- policy version and creation time.

Candidate evidence is structured JSON with an allowlist schema. It may contain
internal IDs and booleans, but no raw CIS, token, source document or arbitrary
payload. Unique `(run_id, code_id)` prevents duplicate decisions.

### `marking_code_reconciliation_events`

Append-only audit for `proposed`, `approved`, `quarantined`, `applied`,
`stale`, `skipped`, `failed`, `restored` and `restore_skipped_operational_use`:

- tenant, seller, run, decision and code IDs;
- actor or controlled-job identity, reason code and event time;
- idempotency key;
- allowlisted before/after projection and post-write read-back JSON.

Unique `(tenant_id, idempotency_key)` makes retries observable but not
duplicative. The event and projection mutation commit in the same database
transaction, so a crash cannot leave an applied link without its audit event.

### `marking_codes` projection

Add nullable:

- `link_classification`: `confirmed_link | review_required`;
- `active_reconciliation_decision_id`;
- `link_classified_at`.

Keep existing `product_id` as the active/historical product link. C2 may set it
only for an eligible `confirmed_link`; the immutable decision/event stores the
prior value. Database checks enforce the classification enum and require an
active decision plus non-null `product_id` for `confirmed_link`. Index hot
queries by `(tenant_id, seller_id, status, link_classification, product_id)`
and by active decision. No existing column/table is dropped or renamed.

## C1 - inventory and decision register

1. Accept an explicit sanitized source manifest containing tenant, seller and
   allowed import/pool/code IDs plus its content hash. Validate the invoking
   user as `fulfillment_admin`; the operational designation "Denmarcs data
   owner" does not create a new application role at this stage.
2. Resolve every source row with tenant and seller predicates in the query.
   A foreign identifier returns the same generic invalid-scope result as an
   absent identifier and does not reveal candidate counts or names.
3. Lock nothing and change no code, product, pool, ownership or lifecycle row.
   C1 writes only the run, immutable decisions and `proposed` audit events.
4. Normalize GTIN to the canonical 14-digit representation only by the
   approved reversible 13-to-14 leading-zero rule. Invalid or conflicting
   values produce `review_required`; SKU/name are recorded only as supporting
   evidence.
5. Candidate queries are constrained by tenant and seller before comparison.
   A confirmed target requires exact canonical GTIN, one approved active
   lineage decision where an old/current relation is involved, one target and
   an available lifecycle. Any failed mandatory rule is fail-closed.
6. Freeze `precondition_hash` from code status/product/pool/import/GTIN,
   candidate set, target identity, lineage decision/hash and policy version.
7. Reconcile source totals exactly:
   `source = confirmed + review_required + skipped_non_actionable + errors`.
   A mismatch makes the run invalid and blocks approval/apply.
8. Repeating identical inputs returns the existing run and events. Changed
   evidence creates a new run and invalidates the old approval by hash.

## C2 - approval, apply and quarantine

Approval and apply are separate commands. Approval records the data-owner
reference and the exact run hash. Apply refuses an unapproved or superseded
run.

Each decision is one independent database transaction:

1. Select the decision, run, code and target with tenant/seller predicates;
   lock the code and decision using `FOR UPDATE` in canonical ID order.
2. Recompute the C1 precondition hash under the lock, including lifecycle,
   ownership, product/pool link, candidate/lineage evidence and target.
3. If evidence changed, ownership differs, lifecycle is no longer available,
   or another operation reserved/used the code, do not apply the stale target.
   Persist `review_required` only when it does not rewrite historical usage,
   append `stale`/`skipped`, and report the row independently.
4. For `review_required`, set the classification and active decision without
   making or changing a product link. This makes an otherwise `available` code
   ineligible everywhere.
5. For `confirmed_link`, atomically set the exact target `product_id`,
   classification, active decision and timestamp. Recheck target tenant,
   seller and canonical GTIN at this mutation boundary.
6. Append the audit event and perform read-back in the same transaction. The
   row is successful only when persisted tenant/seller, lifecycle,
   classification, target and active decision equal the intended result.
7. Commit the row. Continue after an independent row failure, record the
   typed reason and finish the run as `partial`; never roll back successful
   unrelated rows or make a failed row usable.

Idempotency key is derived from `(run_id, decision_id, operation,
precondition_hash)`. On retry, a matching committed event plus matching
read-back returns the stored result. A conflicting current projection does not
overwrite data; it produces a stale/conflict event and requires a new C1 run.

## Canonical eligibility predicate

All availability consumers must use one service predicate rather than ad hoc
`status == available` checks:

```text
same tenant and seller
AND lifecycle status == available
AND link_classification != review_required
AND (
  link_classification IS NULL and legacy product/pool eligibility
  OR link_classification == confirmed_link and product_id == requested product
)
```

For a direct code scan, `review_required` is always rejected. A confirmed code
is rejected when the order/product differs from its target. The predicate must
cover list/read counts, batch counts, shared-pool totals, low-stock forecast,
packaging print, catalog print, replacement selection and FBS claim. This is
the quarantine boundary; applying C2 before every consumer uses it is
forbidden.

## Tenant isolation and authorization

- Every command requires explicit tenant and seller plus an authenticated
  `fulfillment_admin` actor. Seller users and warehouse operators cannot run
  reconciliation through this task.
- Never load a code/product/pool/import by bare ID and then reuse it. The
  selecting query includes tenant and seller. Mutation repeats the check under
  lock.
- Candidate sets are built inside the authorized tenant/seller scope; foreign
  matches are indistinguishable from absence in output and errors.
- Source manifests cannot change tenant/seller ownership. Actor identity is
  audit metadata, not authority to override scope.
- Tests use two tenants and two sellers with identical GTIN/SKU/name values and
  prove zero foreign candidates, mutations, counts and existence disclosure.

## Read-back and evidence

`read-back --run-id` returns sanitized JSON with run hashes/totals and one row
per decision: fingerprint, reason, lifecycle, classification, masked target
reference, active decision, mutation outcome and audit event ID. It queries
persisted state afresh; it does not echo the request or in-memory result.

Evidence must prove:

- source totals reconcile before and after apply;
- every source code has exactly one decision and latest outcome;
- no `review_required` code appears in available counts or allocation paths;
- every `confirmed_link` in a shared pool appears only for its exact target;
- audit event and projection agree;
- no raw CIS/DataMatrix, source document, token or tenant-sensitive payload is
  written to logs, reports, screenshots or Git evidence.

## Compatibility, rollout and rollback boundaries

This is a two-phase compatibility rollout even though it may be implemented in
one card branch:

1. **Compatibility floor.** Apply the additive migration and deploy code in
   which every availability consumer understands the nullable classification.
   With all new columns `NULL`, legacy behavior is unchanged. Prove existing
   marking tests and migration upgrade before any C1/C2 data operation.
2. **Reconciliation activation.** Only after the compatibility-floor SHA and
   consumer coverage are accepted may C1/C2 create classifications. Production
   execution still requires a separate explicit owner authorization and exact
   source/lineage manifests.

After any C2 classification exists, rollback to a binary older than the
compatibility floor is forbidden: that binary would ignore quarantine and
could allocate doubtful codes. Application rollback may target only the pinned
compatibility-floor SHA.

Compensating `restore` is decision-scoped and append-only:

- lock the code and verify it still matches the applied decision;
- restore the prior product/classification only if the code is still
  `available` and no reservation, print, application, introduction, shipment,
  transfer, replacement or void event occurred after reconciliation;
- if operational use occurred, do not rewrite the link, lifecycle or history;
  append `restore_skipped_operational_use` and report manual review;
- never delete codes, reconciliation decisions or audit events;
- schema downgrade is allowed only before reconciliation data exists. After
  activation, schema removal is a separately approved destructive data change,
  not an automatic rollback.

S22/S23 must rehearse upgrade on a legacy fixture, no-op compatibility,
partial apply, retry, compensating restore and application rollback to the
compatibility floor. The rehearsal records migration head, before/after
counts, exact SHA and restore outcome.

## Locks, order and waves

The two S12 cards are sequential because they share models, migration and the
eligibility predicate.

1. `BLG-D05-C1`: allocate exclusive locks for the migration revision slot,
   marking-code model exports, new reconciliation service/CLI and C1 tests.
   Build the complete additive schema but do not activate classifications.
2. `BLG-D05-C2`: after C1 contract/tests are stable, extend the same service and
   lock `marking_code_service.py`, `fbs_marking_service.py`, low-stock service
   and all affected marking tests while implementing apply/quarantine/restore.
3. No other card may change marking allocation/count queries or the same
   migration head concurrently. Newly discovered consumers return to S13 for
   lock expansion; they are not patched out of scope.
4. `BLG-F01` remains a dependency for canonical block/dependency-registry
   integration. S15 may define the local no-auto-use cases now, but C2 must not
   pass the Product-before-Dev gate without a versioned BLG-F01 block reference
   or a controller-approved dependency resolution. This is not an S13 blocker
   because the architecture and cases can proceed independently.

## S15 handoff

S15 must turn every S12 acceptance row into direct and breaker cases and add:

- same input replay, changed input, crash/retry and concurrent double apply;
- one failing row among successful rows with reconciled totals;
- shared pool where a confirmed code is visible/allocatable to one product
  only, plus a quarantined code visible to none;
- direct FBS scan and replacement selection rejection for quarantine;
- two tenants/two sellers with identical metadata and generic foreign-ID
  failures;
- lifecycle transition between C1 and C2;
- append-only reassignment and stale approval invalidation;
- masked audit/read-back and raw-code leak checks;
- legacy migration compatibility, compatibility-floor rollback and both safe
  and skipped compensating restore branches.

Fixtures are synthetic and local. No live Denmarcs, WB/Ozon or production data
is needed for S15.

## Risks and non-blocking decisions

- Existing shared-pool behavior deliberately makes the same pool count toward
  several products. The new predicate must special-case only classified rows;
  changing legacy `NULL` rows globally is out of scope.
- `product_id` currently serves both an available-code target and historical
  consumed-code provenance. Restore therefore stops after operational use
  rather than erasing history.
- The CLI is chosen over a new API/worker because this task has no UI or
  `background_worker` trait and the known population is bounded. A later
  recurring or operator-facing workflow requires reclassification and a new
  Product contract.
- Exact production source IDs, lineage approvals and authorization to execute
  C1/C2 live are intentionally absent and are not required for S13. They are
  required before any production reconciliation run.

## Blocker status and next stage

No blocker prevents `ARCH_PLAN_READY`. Budget remains below the task and
expensive-stage hard stops. The next controller stage after S13 is `S15
CASE_FACTORY`; `S14` is not required for the current medium-risk trait set.
