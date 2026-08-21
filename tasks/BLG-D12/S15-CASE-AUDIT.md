# S15 independent case audit - BLG-D12

## Verdict

`CASE_AUDIT_FAILED`

This is an independent `case-auditor` audit of the exact S15 package. It does
not mutate controller state, advance S15, accept S16, or authorize development,
release, deployment, production access, secret access, or live WB/Ozon work.

## Audited package

- `S11-PRODUCT-CONTRACT.md`: `sha256:4fee46a619e1b0d7499737be2bf2ce570834163397a1d83854ceae95592a8159`
- `S12-TASK-CUT.md`: `sha256:0d968d9f0a0aaba520a3dae3bfeb34f5a270f8bf32c6f338e6e341d132c44442`
- `S13-ARCHITECT-PLAN.md`: `sha256:d3ea5f9aa2bcffdf8b9d089947c510288e5cbce75827dd0888ee81649edd0305`
- `S14-ARCHITECT-FALSIFICATION.md`: `sha256:7c46808a1aaed2e1c469b34c8a6173795382b1e9cec2f291491f664cda8b08c7`
- `S15-CASE-FACTORY.md`: `sha256:1081773c63383bc3650e157f59983dd21c058ccb071b6fc4fc57a9ee1e4f5571`
- `S15-CASES.json`: `sha256:bdec333ba07311361d03cd1e0de0b85e2167255d6abb90720e697fe87b344000`

`next --task-id BLG-D12` reports `S16` owned by `pipeline-product`; `validate
--task-id BLG-D12` passes. Neither result is an S16 acceptance and no controller
command was used to advance the task.

## Covered rows

The exact matrix has deterministic direct and breaker coverage for entry HTML
aliases/fallbacks and `GET`/`HEAD`, stale validators, retained A rollback
assets and URL-byte collision, ordinary A-warmed same-origin navigation to B,
false browser shortcuts, effective header ownership, missing/redirect/error
false proof, fixture reset, S19 executable references, and the stated
non-production/no-scope-expansion boundary.

## Missing applicable row

| Source requirement | Required direct and breaker coverage | Exact gap |
| --- | --- | --- |
| S14 falsification, complete immutable asset inventory | Enumerate every current and retained asset served with immutable caching, including transitive chunks, CSS imports, fonts and images; bind each URL and bytes to the candidate manifest. A breaker must fail when an immutable response is absent from that inventory. | `D12-C1-04` verifies only selected referenced hashed JS/CSS. `D12-C1-10` enumerates retained A assets only. No case enumerates the complete current B immutable inventory, and no breaker makes a hashed immutable B response absent from that inventory fail. The fixture's phrase "complete B inventory" and S19 recording plan are not executable assertions. |

## Required rework and blocker

Add a planned-S19 direct case that enumerates the complete current B immutable
inventory and validates every URL, cache policy and digest against B's manifest,
including transitive chunks, CSS imports, fonts and images. Add its independent
breaker for an immutable B URL missing from the inventory/manifest, and map both
case IDs in the Markdown and JSON coverage matrix to the S14 complete-inventory
row. Until then the blocker is `CASE_AUDIT_REQUIRED`; S16 must not be accepted
from this audited package.

## Writer rework closure note

`pipeline-ba` repaired the S15 package after this audit snapshot by adding
`D12-C1-15` as the planned-S19 direct complete-current-B-inventory case and
`D12-C1-16` as its independent immutable-URL-outside-manifest/inventory
breaker. Both are mapped in the Markdown and JSON matrices to AC02 and the S14
complete-inventory attack lane. The direct case requires equality between every
immutable B response and the candidate-manifest-derived set, recursively
including chunks, CSS imports, fonts and images; the breaker requires a hard
failure before browser or candidate proof when an immutable URL has no matching
manifest/inventory member.

This note is not an audit verdict and does not change `CASE_AUDIT_FAILED` in
this document. An independent `case-auditor` must re-audit the repaired exact
S15 package and issue the controller receipt before S16 can proceed.
