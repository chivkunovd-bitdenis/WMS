# S13 ARCHITECT_PLAN - BLG-D09

## Verdict

`ARCH_PLAN_READY`

This plan covers the single vertical card `BLG-D09-C1`. It preserves the S11
and S12 product boundary: one explicit full Git SHA must remain identical from
source selection through a build-once manifest, delivered artifacts, running
backend and worker identities, and the concrete frontend bundle loaded by a
browser. It does not authorize or perform a release.

`BLK-RELEASE-001` remains open. This S13 verdict does not resolve it and does
not permit S23 to pass without the controller-recorded minimum closure proof.

## Architectural invariants

1. The only release input is a lowercase 40-character commit SHA. Branches,
   tags, shortened SHAs, `HEAD`, `latest`, and a dirty worktree are rejected.
2. Build happens once in an isolated builder checked out at that SHA. The
   target environment receives immutable artifacts and a manifest; it does not
   resolve source refs or rebuild application images.
3. The manifest is the identity root for the release. Its canonical bytes have
   one SHA-256 digest, and every promotion, runtime check, browser proof, and
   rollback receipt names that digest together with the release SHA.
4. Missing identity is a failure. `unknown`, an omitted service, a digest
   mismatch, or a runtime using a different image can never be downgraded to a
   warning followed by release success.
5. API health proves liveness only. Release identity requires read-back from
   every applicable runtime plus browser network evidence for the frontend.
6. Rollback always names a previously verified SHA and manifest digest. An
   application rollback never claims to reverse database changes.
7. Marketplace synchronization and other external business side effects are
   outside the atomic release transaction and require their own authorization.
   They cannot be a best-effort step inside exact-artifact promotion.

## Current resource graph and observed gaps

| Boundary | Current resources | Architectural finding |
| --- | --- | --- |
| Candidate selection | `.github/workflows/deploy.yml` | Full-SHA input and builder checkout verification exist. The target step still checks out repository source, so promotion is not yet independent of a server-side Git checkout. |
| Build once | `scripts/deploy/build-offline-release-artifact.sh`, `frontend/Dockerfile.prod`, `backend/Dockerfile` | Backend and web images are built once and exported. Builder cleanliness/source-tree identity and browser asset mapping are not represented in the manifest. |
| Manifest | `scripts/deploy/release_manifest.py`, `scripts/deploy/test-release-manifest.sh` | Manifest v1 binds SHA, two archives, image names/IDs, and service mapping. It does not bind entry HTML, hashed browser assets, migration identity, builder provenance, or the rollback candidate. |
| Delivery | `.github/workflows/deploy.yml`, `scripts/deploy/prod-update.sh` | Archive digest and loaded image ID are checked. Delivery proof and retained previous manifest are not modeled as a durable receipt. |
| Runtime start | `docker-compose.prod.yml`, generated compose override in `prod-update.sh` | API and worker use the backend image, web uses the web image. `celery_beat` lacks release identity variables, and start is not followed by complete per-service identity read-back. |
| Runtime identity | `backend/app/api/version.py`, `backend/tests/test_health.py` | `/api/version` exposes API SHA and manifest digest. There is no equivalent worker/beat read-back and no fail-closed verification of container image ID/revision for all services. |
| Browser identity | web image, Caddy configs, built `index.html` and hashed assets | No release receipt binds the browser-loaded document and JavaScript asset bytes to the candidate manifest. API version output cannot fill this gap. |
| Cache dependency | `deploy/Caddyfile*`, `frontend/deploy/Caddyfile*`, BLG-D12 | Some configs contain partial no-cache behavior, but BLG-D12 owns cache-control behavior and `BLK-RELEASE-001` still requires observed headers plus hard-reload proof at S23. BLG-D09 must consume that proof, not reimplement or assume it. |
| Failure handling | `prod-update.sh`, deploy workflow | There is no named previous-manifest rollback transaction or post-rollback identity/browser verification. Migration and partial-service failure boundaries are not explicit. |
| External side effects | `scripts/deploy/sync-all-wb-products.sh` invocation in `prod-update.sh` | A live WB resync currently sits inside the deploy script and may fail without failing deploy. It must be separated from release success and remain independently authorized. No live call is made by this plan. |
| Documentation | `docs/DEPLOY_SERVER_RU.md` | The documented `git pull + --build` path conflicts with build-once promotion and must not remain an accepted release route after implementation. |

## Target release manifest

The implementation may evolve the current v1 schema or introduce a versioned
successor, but validation must be strict and reject unknown or missing required
fields. The canonical manifest must contain at least:

- `schema_version`, full `release_sha`, and immutable Git tree identity;
- builder run identity and the declared build inputs needed to audit provenance;
- backend and web archive SHA-256 digests, image names, image IDs, and OCI
  revision labels equal to `release_sha`;
- a complete service map for `api`, `migrations`, `celery_worker`,
  `celery_beat`, and `web`;
- migration head or an explicit `not_applicable` marker tied to the backend
  artifact;
- frontend entrypoint records for fulfillment and seller HTML, including
  content hashes and the concrete content-hashed JS/CSS asset paths and hashes;
- the manifest's own digest computed over canonical stored bytes and carried
  outside the manifest wherever self-reference would otherwise be required.

The release packet, rather than the candidate artifact itself, additionally
names the previous accepted `rollback_sha`, previous manifest digest, retention
location, compatibility decision, and stop criteria. Promotion validates the
manifest and every archive before loading, verifies loaded image IDs and OCI
revision labels, and records the same values after transfer. Any discrepancy
stops before application services are changed.

The target-side command must not depend on checking out candidate source merely
to obtain deployment code. The deploy runner and compose specification are
either part of the immutable release artifact and covered by its digest, or are
a separately versioned, pre-installed release-controller tool whose accepted
version is recorded in the release packet. In both forms the runner consumes
only the supplied SHA, manifest, artifacts, and named previous manifest.

## Runtime identity contract

The release verifier must collect a structured identity row for every
applicable runtime:

| Runtime | Authoritative read-back | Required identity |
| --- | --- | --- |
| API | `/api/version` plus actual container inspection | full SHA, manifest digest, backend image ID, OCI revision |
| Celery worker | command executed in the running worker container plus Celery liveness check | full SHA, manifest digest, backend image ID, OCI revision |
| Celery beat | command executed in the running beat container plus process liveness | full SHA, manifest digest, backend image ID, OCI revision |
| Migrations | completed one-shot container receipt | full SHA, manifest digest, backend image ID, OCI revision, migration head, exit status |
| Web | running container inspection plus browser asset proof | full SHA/revision label, manifest digest, web image ID, entrypoint and asset hashes |

All rows must match the candidate manifest. Environment values alone are not
sufficient: the verifier also checks the running container image ID and image
revision label. The identity report is sanitized and contains no environment
dump, cookies, credentials, or secret headers.

## Browser bundle proof

S23 must use an isolated, known frontend-changing candidate and record both the
pre-release and candidate identities. A real browser run must capture:

1. requested page URL and the final `index.html` response URL;
2. effective cache headers for the root document and `index.html`;
3. the concrete content-hashed JavaScript asset URL actually loaded by the
   page, its response status, and a SHA-256 hash of its bytes;
4. a manifest lookup proving that the entrypoint and asset hashes belong to the
   candidate web artifact;
5. the visible screen identity and a hard reload showing that the browser still
   resolves to the candidate asset;
6. proof that the known frontend-changing candidate's asset URL or content hash
   differs from the recorded pre-release value.

The browser receipt must be linked to the same full SHA and manifest digest as
the runtime identity report. A screenshot, `curl`, API health, build log, or
Playwright-only assertion without the loaded asset identity is insufficient.
BLG-D12 supplies the cache-policy behavior; `BLK-RELEASE-001` can be resolved
only through the controller after this combined evidence exists.

## Failure and rollback boundaries

| Failure point | Required stop behavior | Rollback boundary |
| --- | --- | --- |
| Invalid SHA, dirty/mismatched builder, or source drift | Fail before build; emit no candidate artifact. | No runtime change. |
| Manifest, archive, image ID, revision label, or transfer mismatch | Fail before promotion/start. | Keep the current accepted runtime untouched. |
| Migration preflight incompatibility or missing restore evidence | Fail before migration. | No runtime or data change. |
| Migration execution failure | Stop application promotion and preserve logs/exit identity. | Follow the separately approved database restore/forward-fix policy; never claim app rollback restored data. |
| Partial API/worker/beat/web start or identity mismatch | Mark candidate failed and stop further success checks. | Promote the named previous immutable manifest for all application services, then repeat full runtime identity verification. |
| Browser loads old/unlisted asset or cache proof is missing | Release result fails even if API and workers are healthy. | Restore the named previous application manifest or hold in failed-release state according to the pre-approved stop rule; verify browser and runtime identities again. |
| Rollback artifact missing, mismatched, or incompatible with current data | Fail closed and escalate as a release incident. | Do not choose another branch/SHA or rebuild an approximation. |

The previous artifact and rollback command must be rehearsed in an isolated
environment before S26 can produce a release packet. A rollback receipt records
both the failed candidate and restored exact identities.

## Resource ownership, locks, and sequencing

`BLG-D09-C1` remains one vertical card, but its implementation work is ordered
to prevent independently green fragments from being accepted as the result.

1. **Manifest and fixture lane.** Lock `.github/workflows/deploy.yml` and
   `scripts/deploy/{build-offline-release-artifact.sh,release_manifest.py,test-release-manifest.sh}`.
   Define the versioned manifest, tamper cases, and immutable artifact handoff.
2. **Promotion and rollback lane.** With the first lock retained, additionally
   lock `scripts/deploy/prod-update.sh` and `docker-compose.prod.yml`. Remove
   target-side source selection/rebuild from the success path, add complete
   service identity propagation/read-back, retain the previous manifest, and
   separate marketplace sync from release success.
3. **Runtime identity lane.** Lock `backend/app/api/version.py` and its tests
   only if the existing endpoint must change; otherwise consume it and add
   release-verifier coverage. Worker and beat identity must be proven without
   exposing secrets.
4. **Browser evidence lane.** Lock only the BLG-D09 proof tooling and tests.
   Treat `deploy/Caddyfile*` and `frontend/deploy/Caddyfile*` as a dependency on
   BLG-D12, not writable BLG-D09 scope, unless a later controller-approved card
   explicitly reallocates those files.
5. **Documentation lane.** After behavior is accepted, reconcile
   `docs/DEPLOY_SERVER_RU.md` with the single build-once route so operators are
   not instructed to use the superseded rebuild path.

No two workers may edit the deploy workflow, manifest code, or production
update script concurrently. Pipeline control files, task runtime state,
secrets, production infrastructure, and live WB/Ozon systems are outside this
card's writable scope.

## Stage handoff

- **S14:** independently falsify source substitution, dirty source, build drift,
  manifest/archive/image tampering, incomplete service map, partial update,
  health-only false proof, stale or unlisted browser asset, missing cache
  evidence, unavailable rollback artifact, data-incompatible rollback, and the
  best-effort marketplace side effect inside release success.
- **S15:** bind `BLG-D09-AC01` through `BLG-D09-AC07` to isolated runnable
  fixtures and add destructive cases for every failure boundary above.
- **S16:** Product approves the unchanged vertical card, cases, manifest schema,
  identity matrix, and explicit BLG-D12 dependency before Dev receives scope.
- **S18-S22:** implement and review only the approved release control path;
  perform no production deployment or live marketplace operation.
- **S23:** run the full isolated exact-SHA/runtime/browser chain. It cannot pass
  while `BLK-RELEASE-001` is open or its minimum closure artifact is absent.
- **S26:** produce a named candidate and rollback packet. Without separate owner
  authorization for that exact candidate, verdict is `READY_FOR_RELEASE`.
- **S27-S28:** remain unavailable to this stage and require later explicit
  authorization and independent production evidence.

## S13 pass condition

The plan is complete for S13 because it names the authoritative identity at
every boundary, the manifest and browser evidence fields, the current resource
gaps, serialized locks, failure ownership, and honest application/data rollback
limits. There is no S13 blocker. The existing release/browser blocker remains a
mandatory future S23 gate and is neither closed nor bypassed here.
