# S15 CASE_FACTORY - BLG-D09

## Verdict

`CASES_READY`

This package covers the one vertical release card `BLG-D09-C1`: one explicit
40-character SHA travels through one clean build, immutable manifest and
artifact digests, promotion, all runtime identities, and the concrete
manifest-listed browser bundle. It describes isolated, non-production tests
only. It neither deploys nor authorizes a release, touches secrets or external
marketplaces, changes BLG-D12 cache policy, or closes `BLK-RELEASE-001`.

## Fixture and reset contract

Fixture set `blg-d09-exact-sha-release-v1` contains two deterministic immutable
candidate packages: a prior accepted package and a known frontend-changing
candidate. Each has synthetic full SHA, canonical manifest digest, backend/web
archives, OCI IDs/revision labels, five runtime identity rows, entry HTML, and
hashed JS/CSS assets. Tamper variants alter exactly one field or byte.

Every case runs in a fresh isolated local runner/container namespace with a
fresh browser profile. It starts from the recorded previous package and removes
generated containers, archives, manifests, browser cache and receipts after the
case. External egress, production hosts, credentials, live deploy, and
WB/Ozon calls are forbidden. Cases must redact any accidentally captured
authorization material before persistence.

## Coverage Matrix

| Requirement and process transition | Direct GOLD case | Independent breaker cases | Oracle | S19 binding |
| --- | --- | --- | --- | --- |
| Full SHA -> build once -> immutable manifest -> exact promotion | AC01 | AC02, AC03, AC04 | S11/S12 exact-SHA contract; S13 manifest invariants | `tests/deploy/test_exact_sha_release.py` |
| Manifest digests -> complete API/worker/beat/migration/web identities | AC01 | AC05, AC06, AC07 | S13 runtime identity matrix | `tests/deploy/test_release_verifier.py` |
| Candidate entry HTML -> loaded hashed asset -> visible browser -> hard reload | AC01 | AC08, AC09, AC10 | S11 browser/cache contract; S13 browser proof | `frontend/tests-e2e/release-bundle-proof.spec.ts` plus verifier test |
| Failed candidate -> named previous immutable package -> complete read-back | AC11 | AC12 | S11/S13 rollback boundary | `tests/deploy/test_release_rollback.py` |

There are no applicable tenant, warehouse, print/device, pagination, worker
business-job, or external-marketplace cases: the approved card changes only the
release-engineer control path. Worker and migration *runtime identity* are
covered because they are explicit release-chain members.

## GOLD and breaker cases

The executable machine matrix is `S15-CASES.json`. `AC01` is the direct GOLD
journey. `AC02`--`AC10` use distinct destructive attack lanes: invalid/mutable
source selection, dirty-source/build drift, transfer/manifest tampering,
target-side rebuild, incomplete or conflicting runtime identities, health-only
false proof, stale entry document, old/unlisted browser asset, and missing
cache/hard-reload proof. `AC11` proves a named rollback and `AC12` breaks
rollback substitution or incomplete recovery.

## S19 binding plan

S19 must implement each `executable_ref` against this fixture set without
changing its oracle. Unit/integration cases validate manifest canonicalization,
archive/image/revision comparison, source/ref rejection, complete identity
rows, and rollback selection. The browser case records the final `index.html`
URL, effective cache headers, requested content-hashed asset URL, response
status and SHA-256, manifest lookup, visible screen identity, and a hard
reload. The known frontend-changing candidate must differ from the prior asset
URL or byte hash. S19 may mark a case executable only after fresh reset and
read-back prove it is independent of prior case state.

## Independent audit requirement

An independent `case-auditor` must examine this exact package and issue
`CASE_AUDIT_PASSED` before Product considers S16. I am the `pipeline-ba` case
writer, not the independent auditor; this `CASES_READY` verdict does not accept
my own cases as audited.

## Future S23 blocker

`BLK-RELEASE-001` remains open and is deliberately neither closed nor worked
around. S23 must still stop until the controller has a browser/release receipt
with exact SHA, manifest-linked asset URL and hash, effective cache headers,
hard-reload proof, and confirmation that the visible screen came from the new
artifact. These cases plan that evidence; they are not that evidence.
