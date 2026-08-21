# S12 TASK_CUT - BLG-D09

## Verdict

`TASK_CUT_READY`

## Atomic vertical card

**Card ID:** `BLG-D09-C1`
**Title:** Prove one selected full Git SHA from build-once immutable artifacts
through deployed runtime identity to the manifest-linked frontend bundle loaded
by a browser.

This remains one atomic release card. It must not be separated into a build
step, an artifact-promotion step, a runtime version check, or a browser check:
each fragment can be green while production runs another revision or the
operator continues to receive the prior frontend bundle. The independently
observable result exists only when the same explicit 40-character SHA and its
immutable manifest bind every link in that chain.

## Card contract

Before a release may report success, the release engineer selects one full
40-character candidate SHA. The build produces one immutable manifest that
records the applicable backend, worker, migration and frontend artifact
digests. Delivery promotes only those recorded artifacts; it neither resolves a
branch tip nor rebuilds on the target.

The deployed backend and worker must read back identities that agree with the
candidate SHA and manifest. Browser evidence must record the `index.html`
response and a concrete hashed frontend asset URL loaded by a real browser,
then bind that asset by digest or manifest entry to the same candidate. For the
acceptance candidate whose frontend input changed, the observed bundle URL or
content hash must differ from the pre-release value. Any missing or conflicting
SHA, manifest, digest, runtime identity, index, asset URL, asset digest, or
browser evidence stops the release rather than reporting partial success.

This card changes the release-engineer control path only. It creates no
warehouse operator action and does not alter warehouse data, marketplace
operations, authorization semantics, migration policy, or worker business
behaviour.

## Implementation and review boundaries

S13 must map every source-selection, build, manifest, promotion, deployment,
runtime-identity and frontend-serving boundary. It must name the authoritative
identity source for each runtime and the evidence fields that connect the
browser asset to the candidate manifest. The plan must also identify the prior
artifact and the stop/rollback path without claiming that application rollback
reverses data.

S14 must independently falsify the plan against branch-tip substitution,
shortened or dirty SHA input, build-after-selection drift, manifest or digest
tampering, server-side rebuild, partial backend/worker/frontend update,
misleading health-only proof, a changed frontend candidate retaining the old
bundle, and rollback targeting another artifact.

S18 may implement only the bounded exact-SHA selection, build-once manifest,
immutable artifact promotion, fail-closed runtime identity verification and
manifest-linked browser-proof instrumentation required by this card. It must
not deploy to production, authorize a release, access secrets, modify
marketplace systems, widen into general CI/CD redesign, change cache-control
behaviour owned by BLG-D12, introduce a service worker, or alter operator
flows.

S20 must reject any success path based solely on a branch name, `HEAD`,
shortened SHA, build log, health response, server checkout, screenshot, curl,
or Playwright result without the complete manifest/runtime/browser identity
chain. It must also reject any path that rebuilds after the selected manifest
or permits a missing identity as a warning.

## Acceptance cases for S15

| ID | Fixture or oracle | Required result |
| --- | --- | --- |
| `BLG-D09-AC01` | Immutable non-production candidate with an explicit full SHA and recorded artifact manifest | Build once produces a manifest whose SHA and all applicable artifact digests are recorded; later promotion consumes exactly those digests. |
| `BLG-D09-AC02` | Branch name, `HEAD`, shortened SHA, dirty source, or SHA different from the selected candidate | Release preparation fails closed before build or promotion and cannot silently resolve another revision. |
| `BLG-D09-AC03` | Candidate manifest with a substituted, missing, or mismatched backend, worker, migration, or frontend digest | Promotion or runtime verification stops; no release success is emitted. |
| `BLG-D09-AC04` | Candidate with a partial service update or runtime identity missing/conflicting with its manifest | Read-back proves every applicable runtime identity matches the candidate, otherwise the stop/rollback path is invoked. |
| `BLG-D09-AC05` | Known frontend-changing candidate and recorded pre-release index/asset identity | A real browser loads the candidate `index.html` and manifest-linked hashed asset; the observed bundle URL or digest differs from the pre-release value and the visible screen identifies the new artifact. |
| `BLG-D09-AC06` | Health endpoint, build log, screenshot, curl-only check, or Playwright-only run without asset identity | It is rejected as insufficient release proof even when the individual check succeeds. |
| `BLG-D09-AC07` | Named previous immutable artifact/manifest | Stop or rollback targets only that named artifact; the evidence records the exact rollback SHA and does not claim data rollback without separate proof. |

S15 must bind every direct and destructive case to the full SHA, manifest,
artifact digests, runtime identities and the selected isolated fixture. Cases
must record browser asset URL/hash and read-back rather than infer browser state
from API health.

## Future S23 stopper and blocker boundary

`BLK-RELEASE-001` remains open and is not closed, weakened, or worked around by
this task cut. S23 cannot pass until the release controller records the
blocker's minimum closure artifact: exact SHA, manifest-linked asset URL and
hash, effective cache headers, hard-reload evidence, and confirmation that the
visible screen came from the new artifact. This card supplies the exact-SHA and
bundle-identity chain needed by that future proof; BLG-D12 owns cache-control
behaviour itself.

Hard reload is supporting recovery evidence, not a substitute for ordinary
browser proof of the release result. Production deployment remains unavailable
until the later S26 owner authorization for one named candidate; S27 may then
promote only its immutable manifest artifacts, and S28 owns production trace.

## Handoff and explicit exclusions

- **Next stage:** `S13 ARCHITECT_PLAN`, owned by `solution-architect`, because
  this is a high-risk `release_change`.
- **S16 packet condition:** Product receives this card together with the S11
  contract, S13/S14 plan verdicts and the S15 coverage matrix. A changed card,
  manifest contract, or oracle invalidates downstream Product-before-Dev
  approval.
- **Not produced by S12:** implementation, commit, push, merge, deployment,
  release authorization, production request, live-browser acceptance, rollback
  execution, secret access, cache-policy change, or closure of
  `BLK-RELEASE-001`.

## Verdict

`TASK_CUT_READY`: `BLG-D09-C1` preserves the only safe observable release
outcome, provides S13-S15 with explicit ownership and destructive acceptance
boundaries, and keeps the cache/browser closure proof as the independent S23
stopper required by `BLK-RELEASE-001`.
