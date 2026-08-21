# S15 independent case audit - BLG-D06

## Verdict

`CASE_AUDIT_PASSED`

The fixed `BLG-D06-C1` S15 package is complete enough for an independent S16
Product review. This auditor did not author the direct cases, breaker cases or
breaker verdict and changed none of those inputs. This verdict does not move
the controller, approve S16, authorize Dev, release, deploy, production access
or any live marketplace call.

## Exact reviewed inputs

- `S15-CASES.json`:
  `sha256:a56a63ff9cf75b4ca35cd1c75f0a3ed8b7d145d221f5b7e1a8b8aaa415533cd9`
- `S15-CASE-FACTORY.md`:
  `sha256:c38ce92c83eabcac5af9792ea3f94d9db7cbb0bf3a310ed6bd8a80429347bae5`
- `S15-CASE-BREAKER.md`:
  `sha256:7696a19af31e2fc70b4481e8f4aefc3b58c876fd95e6122a50c9314852cbb2df`
- Reviewed package commit:
  `cb51a020e28e41b8decd2fe3b65ecc1570f9e10a`
- Accepted upstream inputs in `state.json`: S09 `UX_CONTRACT_READY`, S10
  `DESIGN_APPROVED`, S11 `PRODUCT_CONTRACT_APPROVED`, S12 `TASK_CUT_READY`.

## Coverage audit

The package contains eight unique direct GOLD cases and four unique breaker
lanes. The coverage matrix resolves every referenced ID and covers every case.

- `D06-C1-01` plus `B01` prove the non-persisted `active` default on first
  open, route return and reload, including hostile browser state and stale
  archive selection.
- `D06-C1-02` plus `B02` prove that exact and partial searches over SKU, name,
  seller and WB vendor code cannot bypass current-only scope.
- `D06-C1-03` plus `B03` prove explicit `all`/`archived` inspection, return to
  `active`, literal `OLD/` visibility and the neutral `Архив` cue.
- `D06-C1-04` proves query/scope AND composition and clears a selected archive
  before hidden detail context can survive.
- `D06-C1-05` plus `B04` cover loading, all approved empty states, rejected
  reads and the prohibition on stale unfiltered fallback.
- `D06-C1-06` plus `B03` cover 250 rows, long SKU/name/seller values, desktop
  and `360 x 640 CSS px`, stacked filters, tooltips, four retained columns and
  table-local horizontal scrolling.
- `D06-C1-07` plus `B04` instrument the existing reads and reject any new API
  parameter, endpoint, write, fixture mutation, worker/queue action or external
  WB/Ozon call.
- `D06-C1-08` plus `B03` prove that only the exact case-sensitive initial
  `OLD/` SKU prefix classifies an archive; lower-case, missing-slash,
  non-initial and non-SKU near matches remain current.

## Consistency and executability

All twelve cases use the same deterministic local fixture version, fresh
Playwright context/reset contract, synthetic route mocks and fail-closed
external boundary. Every case has a unique test ID and planned executable
reference in `frontend/tests-e2e/catalog-products-archive.spec.ts`, plus a
specific oracle, visible/API/data expectation, read-back and reload assertion.

The breaker artifact independently confirms all four attack lanes against the
exact immutable factory and JSON hashes above. Therefore the JSON's
`PENDING_CASE_BREAKER_CONFIRMATION` provenance records are satisfied by that
separate hash-bound artifact; they are not an unclosed coverage gap. The
factory, JSON and breaker descriptions agree on scope and expected behavior.
No generic filler, unresolved coverage row, live dependency or unauthorized
surface expansion was found. `python3 scripts/pipeline/run.py validate
--task-id BLG-D06` passes.

## Next action

The orchestrator may present this exact hash-bound package to a separate
`pipeline-product` actor for S16. Any change to S09-S12, either S15 package
input, the breaker artifact or their hashes invalidates this audit and requires
a new independent S15 review.
