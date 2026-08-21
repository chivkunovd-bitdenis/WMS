# S11 PRODUCT_CONTRACT_APPROVAL - BLG-D09

## Product decision

Product approves the release outcome, not a particular implementation: a WMS
release may report success only when one explicitly selected full Git commit
SHA is traceably the same candidate that was built, delivered, started and
observed by the browser. A successful command, a branch name, a server-side
checkout, an image build message or an API health response alone is not release
proof.

The approved outcome removes the dangerous ambiguity in which production can
run a different commit or an operator can keep using an old frontend bundle
after the release command has completed. It does not introduce a new warehouse
operator action or change any warehouse process. The affected operational role
is the release engineer; warehouse operators continue their existing work and
must simply receive the accepted application version.

## Approved release contract

1. The release candidate is identified by one explicit, full 40-character Git
   SHA. A branch, tag, shortened SHA, `main`, `etalon`, `HEAD` or `latest` is not
   an acceptable substitute at the release boundary.
2. The candidate is built once. Its immutable release manifest binds that SHA
   to all applicable backend, worker, migration and frontend artifacts and to
   their content digests. Production delivery promotes those artifacts; it must
   not select another revision or rebuild an untracked equivalent on the
   server.
3. Before a release can be called successful, the deployed backend and worker
   runtime identities must match the approved SHA and manifest. A missing,
   unreadable or conflicting identity fails closed and produces a visible
   release failure, not a warning followed by success.
4. Frontend proof must identify the `index.html` response and the concrete
   hashed asset URL loaded by a real browser, then bind that asset by hash or
   manifest digest to the same candidate. An API version response does not prove
   which JavaScript bundle the operator received.
5. For an acceptance candidate whose frontend inputs changed, the observed
   hashed bundle URL or content hash must differ from the recorded pre-release
   value. Acceptance must use such a known frontend-changing candidate so the
   stale-bundle failure mode is actually exercised. For a future backend-only
   release, an unchanged frontend bundle is valid only when the manifest proves
   that it is the frontend artifact belonging to that exact candidate.
6. Cache evidence is part of the release chain. The root document and
   `index.html` must be revalidated rather than indefinitely reused, while
   content-hashed assets may use the separately approved long-lived immutable
   caching policy. The evidence must record the effective cache headers and a
   hard reload that resolves the screen to the candidate's asset.

## Success, failure and rollback boundaries

- Success means the selected SHA, release manifest, delivered artifact
  digests, runtime identity and browser-loaded asset all agree.
- Any SHA, digest, image, runtime version, `index.html`, asset URL or asset hash
  mismatch stops the release result. The system must not silently fall back to
  a branch tip, reuse an unverified server build or report a partial success.
- A failed or partial release follows the pre-approved stop/rollback procedure.
  Rollback must name its own exact SHA and immutable manifest and must not claim
  that data was rolled back when only application artifacts were restored.
- Migration compatibility, ordering and rollback limits remain mandatory when
  the chosen candidate includes a migration. This contract does not weaken
  those controls.
- Release evidence must be sanitized. Tokens, cookies, credentials, raw secret
  headers and sensitive production payloads must not enter Git artifacts.

## Required downstream proof

S12 may cut vertical cards for build-once packaging, exact-artifact delivery,
runtime verification and browser/cache verification, but the end-to-end release
result must retain one SHA and one hash-linked manifest across all cards. S13
and S14 must cover at least branch-tip substitution, dirty or mismatched source,
manifest/artifact tampering, server-side rebuild, partial service update,
unchanged bundle for a known frontend-changing candidate, stale `index.html`,
cache reuse and rollback to a named artifact.

S15 must create direct and destructive cases for the same boundaries. At
minimum, cases must prove the accepted exact-SHA journey, reject every identity
or digest mismatch, exercise a known frontend bundle change, verify read-back
from runtime, and verify browser reload against the manifest-linked asset.

`BLK-RELEASE-001` remains open. S11 neither closes nor bypasses it. S23 may pass
only after the minimum closure evidence is attached and the blocker is resolved
through the controller: a browser/release receipt naming the exact SHA, asset
URL and hash, effective cache headers, hard-reload proof and confirmation that
the visible screen came from the new artifact. Build logs, `curl` alone,
Playwright alone or a screenshot without asset identity are supporting evidence,
not substitutes for that chain.

S26 must name the full `release_candidate_sha`, immutable manifest and artifact
digests, green evidence, rollback SHA and rollback/stop procedure. Without a
separate owner authorization for that exact candidate, the honest outcome is
`READY_FOR_RELEASE`. If authorized later, S27 must deploy only those immutable
artifacts and prove their runtime identity; S28 must monitor the declared
runtime and browser-visible effects without rewriting the accepted evidence
after deployment.

## Out of scope and authorization

This S11 verdict does not select a candidate SHA, authorize production deploy,
run a migration, change production data, access secrets, perform a live
WB/Ozon operation, close `BLK-RELEASE-001`, accept implementation or provide
live-browser acceptance. It also does not absorb the separate BLG-D12 work:
that card owns the cache-control behavior, while BLG-D09 requires its verified
result in the release evidence chain.

## Verdict

`PRODUCT_CONTRACT_APPROVED`: the approved release outcome is fail-closed and
traceable from one full Git SHA through immutable artifact digests and runtime
identity to the exact frontend asset loaded by the browser. The warehouse
operator flow is unchanged, and cache/browser proof remains an explicit S23
stopper until `BLK-RELEASE-001` is closed through the controller.
