# S14 ARCHITECT_FALSIFICATION - BLG-D09

## Verdict

`ARCH_REVIEW_PASSED`

Reviewer identity: `codex-pipeline-reviewer-blg-d09-s14`
Reviewed card: `BLG-D09-C1`
Reviewed plan: `tasks/BLG-D09/S13-ARCHITECT-PLAN.md`

The S13 plan is accepted for the exact-SHA release architecture. It preserves
one full Git SHA and one externally carried manifest digest from isolated build
through artifact delivery, runtime read-back, browser-loaded asset proof and a
named rollback. No unresolved high-risk conflict requires a return to S13.

`BLK-RELEASE-001` remains open. This verdict neither closes it nor permits S23
to pass without the controller-recorded browser/cache closure artifact.

## Independent falsification method

Before reading the S13 plan, the reviewer inspected the approved S11/S12
contracts and the current release surfaces: the deploy workflow, offline
artifact builder and manifest validator, production update script, compose
service identities, API version endpoint, frontend production image and Caddy
serving path. The independent target model required:

- a full commit SHA accepted as data, never resolved from a mutable ref;
- a build-once artifact set whose trusted manifest digest is checked before
  migration, restart or any other target-side effect;
- distinct read-back for API, worker, beat, migration and web identities;
- browser network evidence binding the loaded entry document and hashed asset
  bytes to the candidate manifest;
- fail-closed handling of partial promotion and a rehearsed rollback to one
  named previous immutable manifest;
- separation of marketplace side effects, secrets and production
  authorization from this architecture stage.

The S13 plan independently reaches the same boundaries and adds explicit
resource locks, migration limits, artifact provenance and documentation
ownership.

## Falsification matrix

| Attack | Failure being tested | S13 control | Judgement |
| --- | --- | --- | --- |
| Mutable-ref substitution | A branch, tag, `HEAD`, `latest` or short SHA resolves to another commit. | Only a lowercase full 40-character SHA is accepted; builder identity must equal it. | Survives. |
| Dirty or drifting source | Build inputs differ from the selected commit after candidate selection. | Isolated clean builder, Git tree identity and builder provenance are manifest inputs; mismatch fails before artifact creation. | Survives. |
| Build-after-selection drift | Target rebuilds equivalent-looking images from another source tree. | Production consumes validated prebuilt archives; the target must not resolve source or rebuild. Runner provenance is itself versioned. | Survives. |
| Manifest substitution | Manifest and archives are replaced during delivery. | Canonical manifest digest is carried outside the artifact and checked with archive digests, image IDs and OCI revision labels before runtime change. | Survives. |
| Incomplete service map | API is current while worker, beat, migration or web remains old. | Strict manifest service map plus one structured identity row for every applicable runtime; omission and `unknown` fail closed. | Survives. |
| Health-only false proof | Healthy API is treated as release identity. | Health is explicitly liveness-only; service image inspection and runtime identity read-back are both required. | Survives. |
| Old browser bundle | Backend is current but the browser loads stale or unlisted frontend bytes. | Candidate manifest records entry HTML and hashed assets; real-browser evidence records the loaded URL and byte hash and compares a known frontend-changing candidate with pre-release identity. | Survives, subject to the future S23 blocker closure. |
| Cache masking | Stale `index.html` keeps pointing at the prior asset. | S23 receipt must include effective cache headers and hard reload; BLG-D12 owns cache behavior and `BLK-RELEASE-001` stays open until controller resolution. | Correctly deferred, not bypassed. |
| Partial rollout | Some services start with candidate artifacts and others do not. | Any identity mismatch fails release; the named previous immutable manifest is restored across application services and identities are re-read. | Survives. |
| Migration failure | Application rollback is falsely reported as data rollback. | Compatibility and restore evidence gate migration; failure follows an explicit database policy and application rollback never claims data reversal. | Survives. |
| Rollback substitution | Recovery silently chooses a branch tip or an unverified approximation. | Release packet names the previous full SHA, manifest digest, retained artifact and rehearsed command; missing or incompatible rollback artifacts fail closed. | Survives. |
| Best-effort live side effect | WB synchronization runs inside deploy and release still reports success after an unrelated external failure. | Marketplace synchronization is removed from the atomic release result and remains separately authorized. | Survives. |

## Required downstream constraints

The pass is conditional only on preserving the accepted plan inputs; these are
not new blockers or implementation performed by S14:

1. S15 must turn every identity edge and attack above into isolated direct and
   destructive cases, including a known frontend-changing candidate.
2. S16 must bind Product approval to the unchanged card, manifest contract,
   runtime identity matrix, cases and this S14 verdict.
3. S18-S22 must not add production execution, secret access, live marketplace
   calls, a server-side rebuild route or a fallback from missing identity.
4. S23 must stop while `BLK-RELEASE-001` is open. Its minimum closure artifact
   remains: exact SHA, manifest-linked asset URL/hash, effective cache headers,
   hard-reload proof and confirmation that the visible screen came from the new
   artifact.
5. S26 must produce the exact candidate and rollback packet. Without separate
   owner authorization for that exact candidate, the honest result remains
   `READY_FOR_RELEASE`; S27 and S28 are outside this verdict.

Any later change to the S11 contract, S12 card, manifest identity root,
service map, browser proof or rollback boundary invalidates this verdict and
requires controller-directed re-review.

## Blocker judgement

There is no S14 blocker and no architecture rework finding. The existing
`BLK-RELEASE-001` is a future S23 release/browser evidence stopper owned by the
release path; it is deliberately unresolved here.
