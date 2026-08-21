# S13 ARCHITECT_PLAN - BLG-I07

## Verdict

`S13_BLOCKED_BASELINE_AND_IMPACT_PROFILE`

This is a real architecture plan for the single vertical card `BLG-I07-C1`,
but it is deliberately not an `ARCH_PLAN_READY` verdict. Two controller-owned
inputs are incomplete:

1. the approved result necessarily changes visible list pagination,
   cross-page selection and long-running print progress, and it changes the
   print acceptance surface, while the current task traits contain neither
   `ui_change` nor `print`; and
2. the available 20 August production observation does not contain the CPU
   quota, per-service memory limits, database/Redis limits, worker concurrency
   or ordinary/peak browser concurrency needed to call an isolated fixture
   production-like and set an absolute capacity envelope.

Passing S13 with those gaps would allow S14-S23 to omit the UX/design/browser
and printer/device gates and would turn an unverified load shape into an
architectural fact. This stage performs no implementation, migration, test
execution, production read, external call, secret access, commit, push, deploy
or acceptance.

## Binding product invariants

The plan preserves the S11 and S12 contracts without relaxing their numbers:

- first visible acknowledgement for a scan, confirmation or ordinary command:
  p95 at or below 1 second and p99 at or below 2 seconds;
- first usable list page of at most 50 rows: p95 at or below 2 seconds; next
  page, server search or filter: p95 at or below 1 second;
- all 500 orders remain reachable and selecting any orders survives page
  changes, refresh and an unrelated background update;
- print request acceptance or rejection: p95 at or below 1 second; 155-code
  generation: p95 at or below 5 seconds; 500-code generation: p95 at or below
  15 seconds;
- 155/500 print work does not push unrelated interactive journeys outside
  their own thresholds;
- a 30-minute run has no restart, OOM, monotonic swap growth or unbounded queue
  growth and retains at least 20 percent steady-state memory headroom;
- periodic refresh increases an active journey's p95 by no more than 20
  percent and never replaces a complete working set with a partial client
  subset;
- no optimization may drop, duplicate, reorder or falsely acknowledge a scan,
  supply mutation, packing action, print request or worker effect.

An HTTP 202 is only acknowledgement when a durable tenant-scoped job exists and
can be read back. A local spinner, optimistic success or in-memory task is not
acknowledgement.

## Confirmed current resource graph

The following facts are from the pinned worktree at base SHA
`69c271678782d7dcfa39df97cd905cbee1678727`. They are candidates for matched
measurement, not causal conclusions.

```text
S-03 FBS orders / supply workspace
  -> FfFbsOrdersScreen.tsx
     -> GET /operations/fbs-orders/worklist?limit=200
        -> fbs_worklist_service.fetch_worklist_page/build_worklist_items
           -> fbs_orders + seller/warehouse/product/card/inventory/reservation/
              pick/marking/print-asset reads
     -> FfFbsSupplyWorkspace.tsx
        -> GET /operations/fbs-supplies/{id}/workspace
           -> fbs_workspace_service.get_supply_workspace
              -> full supply graph + full order worklist projection + boxes +
                 marking pool + progress
        -> visible picking/boxes workspace refresh every 15 seconds

S-14 packaging and S-12 marketplace unload/supply lists
  -> GET /operations/packaging-tasks
     -> packaging_task_service.list_open_tasks
        -> all open tasks with lines/product/location, then per-task mapping
  -> GET /operations/marketplace-unload-requests
     -> marketplace_unload_service.list_requests
        -> all matching requests with lines

S-13/S-30 notification bell
  -> NotificationBell.tsx, currently one refresh every 60 seconds while mounted
  -> GET /operations/notifications
     -> notification_service.list_notifications + count_unread
        -> notifications

Marking and FBS print
  -> MarkingPrintDialog / printMarkingCodeLabel.ts
     -> POST /operations/marking-codes/label-artifact-tape
        -> marking_code_service.build_label_artifact_tape_pdf
           -> one session.get per code
           -> synchronous PyMuPDF merge/fit in the API event loop
     -> HTML fallback renders DataMatrix canvases on the browser main thread and
        may fetch one PNG conversion per stored artifact
  -> POST /operations/fbs-supplies/{id}/print-assets or /order-print-tape
     -> fbs_print_asset_service / fbs_order_tape_print_service
        -> WB-emulator/client chunks + fbs_print_assets + marking allocation

Background execution
  -> celery_app.py: one default Celery app and default queue; no explicit task
     routing between periodic marketplace sync and CPU-heavy print work
  -> background_jobs + background_job_service
  -> beat: FBS order poll, status poll and stock reconciliation

Runtime shape encoded in Git
  -> backend/Dockerfile.railway: one uvicorn process, no configured workers
  -> docker-compose*.yml: API, one Celery worker, beat, PostgreSQL and Redis;
     no CPU/memory quotas or worker concurrency are encoded
```

Additional observed differences that the baseline must keep honest:

- the current branch requests 200 FBS rows, not the historical `limit=500`;
- the current notification bell interval is 60 seconds, not the historical
  26-second observation;
- the supply workspace still returns all orders and polls at 15 seconds in two
  active stages;
- the current FBS worklist service already batches its enrichment and has a
  bounded-query-count test, so query count alone cannot prove that the DB is or
  is not the limiting resource;
- `fbs_orders` already has tenant/seller/status/deadline and
  tenant/seller/supply indexes; any new index requires measured query-plan
  evidence rather than the historical statement that the database was fast.

## Target architecture after minimum closure

### 1. One correlated evidence chain

Every baseline and candidate sample carries these non-secret identifiers:

```text
performance_run_id
  -> browser_session_id -> journey_iteration_id
     -> request_id -> route/service span -> SQL span(s)
     -> background_job_id -> queue publish/start/finish/retry
     -> durable effect id -> API read-back -> browser reload assertion
```

The implementation adds opt-in structured performance instrumentation rather
than a public diagnostics screen. Test runs collect:

- browser navigation/resource timing, long tasks, first usable page and first
  truthful acknowledgement;
- route p50/p95/p99, event-loop lag and error/timeout status;
- SQL count, total DB time, connection checkout wait and selected
  `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` output on synthetic data;
- API/worker CPU, RSS, cgroup memory, restart/OOM state and available headroom;
- queue publish-to-start lag, execution time, retries, terminal state and queue
  depth/drain;
- durable read-back and reload for every mutation.

Evidence contains only pseudonymous tenant/seller/order/code identifiers. It
must not contain Authorization headers, cookies, raw CIS/DataMatrix, marketplace
tokens, environment dumps or production payloads.

### 2. Fixed isolated fixture

The fixture is generated, versioned and reset as one unit:

- two tenants with overlapping seller/product/barcode values to expose scope
  leaks; only tenant A carries load;
- tenant A: three sellers, two warehouses, 500 reachable FBS orders, one
  500-order active supply, inventory/reservation/pick state, packing boxes,
  50 open packaging tasks and 500 notifications;
- marking data: small, 155-code and 500-code tapes, including seller PDF
  artifacts and generated-DataMatrix fallback, with deterministic order;
- WB behavior comes only from the local emulator with deterministic latency,
  partial failure and timeout profiles; test egress remains deny-by-default;
- the existing FBS seed helpers, full-stack runner and emulator are extended,
  not replaced by an unrelated mock stack;
- database, Redis, Celery queues, storage prefix and browser profiles are reset
  together; clock and random seed are fixed.

The same database snapshot, emulator script, container limits, browser build
and run manifest are used for before and after. A candidate run on a different
fixture or capacity shape is invalid.

### 3. Load protocol

Once the missing capacity/concurrency manifest is supplied, S13 is resumed and
binds its exact values. The intended matrix is:

- `L0`: one operator, used to separate intrinsic latency from contention;
- `L1`: ordinary concurrent visible browsers from the approved manifest;
- `L2`: approved peak browsers, plus one 155-code print job;
- `L3`: approved peak browsers, plus one 500-code print job and overlapping
  FBS sync/stock reconciliation in isolated queues;
- `L4`: bounded overload, used only to prove truthful rejection/backpressure
  and recovery, not to relax L1-L3 thresholds.

Each immutable build/profile pair receives a 5-minute warm-up and three
independent 30-minute measurement runs from a fresh full snapshot. Interactive
operations collect at least 1,000 completed samples per profile when p99 is an
acceptance metric. Every run, not only an aggregate average, must meet the S11
thresholds. Baseline and candidate runs alternate order to expose host drift.

### 4. List/read remediation boundary

The product contract itself requires a 50-row server page and complete
500-order reachability, so this is not optional optimization:

- use keyset/cursor pagination with deterministic `(deadline_at, id)` or the
  resource's equivalent stable ordering; no offset-only paging for mutable
  working lists;
- keep selected order IDs independently from the currently loaded page and do
  not filter the selection when the page refreshes;
- return compact list summaries; load detail/workspace projections only when
  opened;
- add an additive paged supply-workspace order surface while keeping the
  current full `/workspace` contract during a compatibility floor;
- add paged summary surfaces for open packaging tasks and marketplace unload
  requests only where the baseline shows their unbounded graph contributes to
  the journey; legacy responses stay available until all consumers migrate;
- refresh only the visible active surface, deduplicate in-flight requests,
  cancel stale filter/page requests and use a visibility-aware interval no
  more frequent than the Product/UX contract permits;
- manual refresh remains available and returns an explicit freshness timestamp.

Visible pagination, next-page controls, preserved cross-page selection,
processing/error states and refresh behavior belong to S09/S10/S24/S25. S13
defines data ownership and ordering but does not design those controls.

### 5. Durable print-generation boundary

The sub-second acknowledgement requirement and 155/500 completion windows make
large print generation a durable background operation rather than an API
event-loop function.

Add a versioned, tenant-scoped print-job contract:

- `POST` creates or returns an idempotent job and responds `202` with job ID,
  status URL and truthful initial state within the acknowledgement threshold;
- `GET` returns `pending | running | succeeded | failed | cancelled`, completed
  and total units, retryability, sanitized error code, artifact checksum and
  content URL only when complete;
- content is one authorized PDF/binary artifact for the batch; browser fallback
  must not issue 500 per-code PNG conversions or render 500 matrices on the
  active operator main thread;
- retry with the same idempotency key and request fingerprint returns the same
  durable job; the same key with a different fingerprint is rejected;
- actual `printed/applied` business state remains separate and changes only on
  the existing explicit operator confirmation, never when generation finishes;
- queue saturation either creates a durable bounded job or rejects before
  creation with a typed retry-after response. It never leaves an unknown
  spinner.

Use additive tables rather than overloading arbitrary JSON as the authority:

- `print_generation_jobs`: tenant, actor, kind, request fingerprint,
  idempotency key, status, progress, attempt/lease/heartbeat, artifact storage
  key/checksum/content type/size, typed error and timestamps;
- `print_generation_job_items`: job, stable sequence, internal order/code/item
  reference and per-item result; no copied raw CIS or external credential;
- unique `(tenant_id, kind, idempotency_key)` and job-item sequence constraints;
- tenant-scoped status/freshness indexes and a retry/lease index selected from
  measured worker queries.

The output file is written to a temporary storage key, checksummed, atomically
promoted, then committed as `succeeded`. Crash replay first validates the
existing checksum; it does not allocate marking codes or fetch external assets
twice. Expiry removes only generated binary after the retention window, not the
job audit or applied/printed business event.

### 6. Worker isolation and backpressure

Introduce explicit Celery routing and separate worker pools for:

- latency-sensitive marketplace/stock synchronization; and
- CPU/memory-heavy print rendering.

Queue names are environment/task namespaced at S17. Print tasks use late ack,
worker-lost rejection, bounded retries with jitter, time limits, database job
claim/lease and idempotent artifact promotion. Worker concurrency is calculated
from measured peak RSS per job and the supplied memory budget; it is not copied
from CPU count. The print queue may not consume the only worker capable of FBS
sync, and sync may not starve accepted print jobs.

Increasing Uvicorn process count is a capacity decision after CPU/memory and
event-loop evidence. It is not the first remedy: more processes are forbidden
when the measured memory envelope would fall below 20 percent headroom.

### 7. Database decision gate

No index or denormalized projection is approved from source inspection alone.
The candidate plan is:

1. batch the current per-code `session.get` print lookup in one tenant-scoped
   query while preserving requested order and duplicate-copy semantics;
2. measure list/workspace SQL spans and query plans at the 500-order fixture;
3. add only additive composite/partial indexes whose measured plan is a
   limiting contributor and whose write cost is included in mutation tests;
4. do not cache authorization, inventory availability or mutable warehouse
   truth without an explicit version/freshness key and invalidation proof.

Any migration is additive. S17 allocates the actual Alembic revision against
the then-current head. Upgrade, no-op legacy compatibility, integrity read-back
and restore rehearsal are mandatory. Application rollback cannot claim to
remove completed jobs or reverse printed/applied state. Schema downgrade is
allowed only before new rows exist; afterward rollback is forward-compatible
application rollback plus later owner-approved cleanup.

## Files and ownership locks

The exact S18 scope is allocated only after the two blockers close. Expected
resource groups are:

### Measurement lane

- new `scripts/performance/blg_i07_*` runner/report files;
- extensions to `backend/tests/fbs_seed_helpers.py`,
  `backend/tests/fbs_browser_e2e_seed.py`, `scripts/run_fbs_fullstack_e2e.sh`;
- new backend and browser performance cases/evidence schemas;
- optional instrumentation in `backend/app/main.py`, DB session hooks and
  Celery task signals, guarded by a test-only configuration.

### List/workspace lane

- `frontend/src/screens/v2/FfFbsOrdersScreen.tsx`;
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` and `fbsApi.ts`;
- `backend/app/api/fbs_orders.py`, `fbs_supplies.py`,
  `packaging_tasks.py`, `marketplace_unload_requests.py` only when their
  measured surfaces are selected;
- corresponding worklist/workspace/packaging/unload services, schemas and
  behavior tests.

### Print/worker/data lane

- `backend/app/api/marking_codes.py`, `fbs_supplies.py` and a new print-job API;
- `backend/app/services/marking_code_service.py`,
  `marking_label_artifact_service.py`, `fbs_print_asset_service.py`,
  `fbs_order_tape_print_service.py` and a new print-job service;
- `backend/app/models/background_job.py` only if consumed for compatibility,
  plus dedicated print-job models and model exports;
- `backend/app/tasks/background_jobs.py`, `backend/app/celery_app.py` and
  explicit queue settings;
- one controller-allocated additive Alembic migration and migration tests;
- frontend print API/utilities/dialog only after the UX route is complete.

The migration revision slot, Celery routing, FBS supply API/service, shared
print utilities and `FfFbsSupplyWorkspace.tsx` are exclusive locks. The lanes
are implementation order inside one vertical card, not separately acceptable
horizontal cards.

Explicitly unaffected unless post-diff classification proves otherwise:

- mobile/TSd contract;
- WB/Ozon endpoint semantics and credentials;
- warehouse authorization, marking validation and tenant rules;
- print label dimensions/content and physical printer protocol;
- production infrastructure, deploy scripts and live data.

## Sequencing after S13 resumes

1. Reconfirm the updated S09-S12 input hashes, deployment/concurrency manifest
   and this resource graph at S13.
2. S14 independently falsifies fixture representativeness, cross-page drift,
   fake asynchronous acknowledgement, queue starvation, crash replay, memory
   multiplication and rollback claims.
3. S15 creates direct and destructive cases before code for every S11 journey,
   both tenants, small/155/500 print, retries, restarts, saturation, migration,
   restore and matched before/after evidence.
4. S16 approves the exact updated card/UX/case packet.
5. S17 allocates isolated DB, Redis, queue names, ports, storage prefix,
   capacity quotas, evidence directory and file locks.
6. S18 implements measurement first, records the immutable baseline, then
   applies only the bounded mechanisms selected above. Baseline and remediation
   remain one card and one evidence chain.
7. S19-S23 bind runnable cases, review, docs, functional and full integration
   evidence. No live marketplace or production system is used.
8. S26 may produce only an immutable release packet. Capacity purchase,
   production sizing, deploy and live measurement remain separate owner actions.

## Stop and rollback conditions

Stop the candidate and return to the owning stage when any of these occurs:

- a candidate meets an isolated endpoint target but regresses a complete
  journey, refresh comparison or non-regression journey;
- missing/different fixture, container limits, build SHA or browser artifact;
- less than 20 percent steady-state memory headroom, monotonic queue/swap/RSS
  growth, restart/OOM, worker starvation or DB connection saturation;
- false success, lost selection, duplicate durable effect, stale partial list,
  foreign-tenant read or marking/authorization bypass;
- async job without durable read-back, checksum, idempotency or recoverable
  terminal state;
- migration/backfill/restore evidence missing or an old binary cannot safely
  coexist with new rows.

Rollback is mechanism-specific: revert the application to the compatibility
floor, stop accepting new print jobs, allow or explicitly cancel already
accepted jobs according to their durable state, preserve audit rows and never
rewrite actual printed/applied warehouse history. Infrastructure rollback and
production action are not authorized by this artifact.

## Minimum closure required to resume S13

Both items are mandatory and contain no secrets:

1. **Controller impact-profile repair.** A pipeline dispatcher reclassifies
   `BLG-I07` with at least `ui_change` and `print` in addition to the existing
   `database_change` and `background_worker`, routes the earliest newly required
   stages, and produces valid S09/S10 plus revalidated S11/S12 receipts before
   returning to S13. The UI contract must cover 50-row navigation, persistent
   cross-page selection, freshness/manual refresh and pending/failed/completed
   print states; the print contract must preserve label content, dimensions,
   repeat-print and device evidence.
2. **Sanitized capacity/concurrency manifest.** An owner-authorized DevOps or
   dispatcher artifact records the isolated target's CPU quota, total and
   per-service memory limits, API process count, Celery worker pools and
   concurrency, PostgreSQL max connections/pool limits, Redis limit, storage
   mode, ordinary visible-browser count and peak visible-browser count. It may
   reference production observations but must not contain host access, secrets,
   environment values, tenant data or live marketplace payloads.

After these artifacts exist, the controller resumes at S13. The architect binds
the exact L1/L2 values and absolute CPU/memory/connection/queue envelopes,
rechecks the resource locks and only then may issue `ARCH_PLAN_READY` with an
expensive-tier usage receipt.
