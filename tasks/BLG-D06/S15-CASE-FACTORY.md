# S15 CASE_FACTORY - BLG-D06

## BA verdict

`CASES_READY`

This package turns the approved atomic card `BLG-D06-C1` into eight direct
GOLD cases and four independent breaker lanes. It covers only `S-01`,
`/app/catalog/products`, and the approved local presentation rule for product
records whose `sku_code` starts with the exact case-sensitive literal `OLD/`.
It does not authorize an API, data, query, pagination, permission, picker,
seller-stock, marketplace, deployment, or production change.

## Fixture contract and isolation

All cases use deterministic local `GET /products` and `GET /products/ff-catalog`
route mocks with synthetic catalog rows. Each case starts in a new Playwright
browser context with an empty local/session storage and a fresh request log.
The fixture never reaches WB, Ozon, a live browser session, a database, a
worker, or any external system. It has current/archive sibling rows, archive-
only search variants in SKU/name/seller/WB vendor code, deliberately similar
non-archive values, long values, and a configurable load error. Reset replaces
the fixture and request log before every case.

## Coverage matrix

| Requirement and process transition | Direct case | Independent breaker lane | Oracle |
| --- | --- | --- | --- |
| Fresh open, route return and reload enter routine catalog work as `active`; no `OLD/` row or persisted archive scope leaks in | `D06-C1-01` | `D06-C1-B01` (storage/history injection) | S09 filter contract; S11 safe default |
| Archive-only exact and partial search stays hidden in `active`; current matches remain visible | `D06-C1-02` | `D06-C1-B02` (field-by-field query bypass) | S09 AND rule; S11 ordinary search invariant |
| Explicit `all` and `archived` modes reveal the intended rows only and mark each archive unambiguously | `D06-C1-03` | `D06-C1-B03` (misclassification and missing cue) | S09 archive treatment; S11 explicit inspection journey |
| Query/scope AND composition and hidden-selection cleanup preserve safe adjacent detail context | `D06-C1-04` | `D06-C1-B01` (stale persisted scope/selection) | S09 selected-row invariant |
| Loading, empty and failed-read states describe one filtered result without stale unfiltered fallback | `D06-C1-05` | `D06-C1-B04` (stale-result/error fallback) | S09 required states; S11 failure invariant |
| Long values and 360 x 640 layout preserve four identifiers, archive cue and usable filters | `D06-C1-06` | `D06-C1-B03` (narrow visual hiding) | S09 table and narrow-layout rules |
| Scope/search are local-only and have no API/query/data/mutation/external effect | `D06-C1-07` | `D06-C1-B04` (request/mutation instrumentation) | S11 API/data boundary |
| Only the initial exact case-sensitive `OLD/` SKU prefix is archival | `D06-C1-08` | `D06-C1-B03` (near-match classifier attack) | S09 classifier; S12 card contract |

## Direct case completeness

Every direct case in `S15-CASES.json` has a named local fixture, deterministic
reset, planned Playwright binding, expected visible/API/data boundary, read-back
and reload assertion. S19 must implement each listed reference without changing
its oracle. The intended test file is
`frontend/tests-e2e/catalog-products-archive.spec.ts`; it is not created at
S15.

The direct cases cover the approved applicable UI-change dimensions: happy,
empty, error, partial-result safety, long data, narrow viewport, reload and
read-back. Mutation, authorization, tenant, worker, print, scanner, external
contract, cancellation, retry, concurrency and pagination are not applicable:
this card adds only a local read-model filter to an already loaded catalog and
must not create those behaviours. Large local list handling is covered by
`D06-C1-06`; the current S-01 surface has no pagination and this card must not
invent one.

## Independent case-breaker and audit gate

I am the `pipeline-ba` case writer, not the independent `case-breaker` or
`case-auditor`. The four `D06-C1-B*` rows are attack specifications, not a
claim that I executed or accepted my own attacks. A distinct case-breaker must
confirm their attack-lane independence and runnable fixture plan. A separate
case-auditor must then verify exact hashes of this Markdown and
`S15-CASES.json`, coverage completeness, fixture isolation, S19 references,
and the breaker confirmation before Product evaluates S16.

`CASES_READY` makes this fixed BA package available for that independent
review. It does not mean `CASE_AUDIT_PASSED`, does not authorize S16 or Dev,
and does not change the required Product-before-Dev gate.

## Handoff

Next action: assign a `case-breaker` distinct from
`codex-pipeline-ba-blg-d06-s15`, then an independent `case-auditor`. The
minimum closure artifact is `tasks/BLG-D06/S15-CASE-AUDIT.md` with exact input
hashes and `CASE_AUDIT_PASSED`; any finding returns the package to S15.
