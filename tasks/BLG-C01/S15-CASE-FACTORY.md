# S15 CASE_FACTORY - BLG-C01

## Verdict

`CASES_READY`

This package turns the approved release card into twelve `GOLD` cases. It
tests a fresh candidate only: discovery commit
`f05207c605ddce9ae7029e8cba6ff902e2d6f1f1` and its branch are forbidden as a
promotion input. No case authorizes a deploy, live migration, tenant mutation,
or WB/Ozon operation.

## Fixture and reset contract

All S19 runs use an isolated local database/schema, synthetic UUID tenants,
sellers, warehouses, supplies, orders and physical boxes; a unique Redis
namespace, Celery queue, emulator namespace and evidence directory; frozen
clock and seed; and outbound network fail-closed. Each mutating case starts
from a fresh database snapshot or belongs to the explicit ordered history
journey. Teardown drains and acknowledges the queue, clears Redis/emulator
state and records a sanitized reset receipt. No case may use a production
tenant, credential, marketplace account or production database.

The S19 binder must record the actual controller-allocated base SHA, Alembic
head and fixture digest before execution. A changed base, migration head or
candidate tree invalidates the bindings and returns to the owning stage.

## Coverage matrix

| Requirement / oracle | Card | GOLD cases | Planned S19 binding |
| --- | --- | --- | --- |
| Fresh immutable candidate only; never promote old SHA | BLG-C01 | AC01, AC12 | `backend/tests/test_release_candidate_contract.py` |
| Additive migration from current head; existing tenants stay required; old app remains schema-compatible | BLG-C01 | AC01, AC08 | `backend/tests/test_optional_packing_migration.py` |
| Explicit tenant `false` permits only packing bypass and writes durable reason | BLG-C01 | AC02 | `backend/tests/test_fbs_packing_box.py` |
| Required/default/missing/unreadable values fail closed | BLG-C01 | AC03 | `backend/tests/test_tenant_settings.py`, `backend/tests/test_fbs_packing_box.py` |
| Audit truth survives read-back, reload and later configuration reversal | BLG-C01 | AC04 | `backend/tests/test_fbs_packing_box.py`, `frontend/tests-e2e/ff-fbs-supply.spec.ts` |
| Authorization and tenant/seller/warehouse predicates cannot leak | BLG-C01 | AC05 | `backend/tests/test_fbs_packing_box.py` |
| Retry and concurrent assignment are one atomic outcome | BLG-C01 | AC06 | `backend/tests/test_fbs_packing_box.py` |
| Marking, cargo-place, delivery and other gates remain independent | BLG-C01 | AC07 | `backend/tests/test_fbs_packing_box.py` |
| Invalid migration parent, second head and destructive rollback are rejected | BLG-C01 | AC08 | `backend/tests/test_optional_packing_migration.py` |
| Tenant configuration uses one-UUID compare-and-set after runtime verification | BLG-C01 | AC10 | `backend/tests/test_release_configuration_contract.py` |
| CAS zero/multiple/ambiguous scope stops release without mutation | BLG-C01 | AC11 | `backend/tests/test_release_configuration_contract.py` |
| S28 operator journey is bounded, exact-SHA-bound and has no live marketplace call | BLG-C01 | AC12 | `frontend/tests-e2e/ff-fbs-supply.spec.ts`, release-controller contract test |

## S19 binding plan

S19 must implement every `executable_ref` in `S15-CASES.json` without
changing its oracle. The migration runner uses a clean pre-migration fixture,
upgrades once from the recorded head, checks a single head, starts the prior
application contract against the new schema, then resets. Service/API tests
use transaction-level fixtures and a concurrency barrier. Browser coverage is
local only and proves read-back/reload on S-03; it is technical evidence, not
Product Browser acceptance. The future production-only case remains a plan for
S28 and cannot run until S27 has an independent exact-SHA owner approval.

## Independent case audit required

`CASE_AUDIT_PASSED` is required from an independent `case-auditor` before this
package can be treated as audited. I am the `pipeline-ba` / case writer, not
that auditor, and do not accept my own cases. The auditor must verify the
unchanged hashes of this file and `S15-CASES.json`, the matrix, breaker
coverage, fixture isolation and S19 bindings; a finding returns to S15.

## Release boundary

S26 may prepare an exact candidate and a sanitized one-tenant compare-and-set
plan. S27/S28 remain blocked until a separate owner approval names the full
S23 `release_candidate_sha`, its immutable manifest and the target tenant UUID.
Branch names, short SHAs, the discovery SHA, green tests and this verdict are
not deploy authority.
