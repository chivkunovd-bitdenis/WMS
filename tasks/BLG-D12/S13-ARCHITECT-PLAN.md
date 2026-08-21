# S13 ARCHITECT_PLAN - BLG-D12

## Verdict

`ARCH_PLAN_READY`

The atomic card `BLG-D12-C1` can be implemented without changing application,
API, database, worker, marketplace, authentication, or operator workflow
behavior. The serving boundary is the frontend Caddy layer contained in the
immutable web artifact. Caddy is the only owner of effective frontend
`Cache-Control`; build and release tooling supply identity and asset inventory
but must not add a second cache policy.

There is no S13 blocker. `BLG-D09` is a hard integration dependency for S23,
not a reason to block this plan: D12 can define its policy and verifier now,
while S23 must wait for D09's exact-SHA, web-artifact, frontend-asset identity
interface.

## Architectural decisions

### A1. Classify the response after static resolution

Cache policy follows the representation actually served, not only the incoming
URL. Each Caddy SPA route must resolve a real static file or rewrite to its
entry document before the final header classification:

- any successful response serving the FF entry document, including `/`,
  `/index.html`, and an FF client-route fallback, receives exactly
  `Cache-Control: no-cache`;
- any successful response serving the seller entry document, including
  `/seller/`, `/seller/index.html`, and a seller client-route fallback,
  receives the same entry-document policy;
- a successful content-addressed asset receives exactly
  `Cache-Control: public, max-age=31536000, immutable`;
- HTML and non-hashed files never receive the immutable policy;
- `/api/*` remains outside the static policy and is only reverse-proxied.

`no-cache` deliberately permits storage and validators but requires
revalidation. Do not replace it with an operator cache-clear workflow. A `304`
is valid only when the current entry bytes equal the browser's validator; a
validator from a different entry document must produce the current body.

The current exact-path matcher runs before SPA fallback resolution, which is
why `/` can serve `index.html` without its policy. S18 must use an explicitly
ordered Caddy route so fallback resolution and header assignment cannot be
reordered by directive sorting.

### A2. Give the static asset namespace a fail-closed route

`/assets/*` is handled before SPA fallback. A missing asset must remain a
distinct `404` and must not become a `200 index.html` response. Directory
membership alone is not proof that a file is immutable.

The immutable matcher is an allowlist for the Vite content-hash filename
shape and supported generated asset extensions. The build verifier enumerates
the actual URLs referenced by each entry document and checks their bytes and
digests. If a generated filename does not match the declared fingerprint
shape, it receives no immutable policy and the candidate fails verification;
the server must not broaden the matcher to make the check green.

Evidence fetches use `Accept-Encoding: identity` when comparing response bytes
to file or manifest digests. Transfer compression may vary without changing
the content-addressed identity.

### A3. Preserve previous content-addressed assets

The promoted web artifact must contain the current build plus the retained
hashed-asset set from every named web artifact still inside the declared
promotion/rollback window. The retained set is an immutable build input tied
to its source web-artifact digest. A path collision with different bytes fails
the candidate build; an existing hashed URL is never overwritten.

This is a self-contained web-artifact rule, not a new CDN or object-store
project. Garbage collection outside the declared retention window is out of
scope. The D09 release manifest interface must identify the current and prior
web artifact digests and expose an asset inventory with URL and content digest;
D12 consumes that interface and owns only cache policy plus retention
validation.

### A4. Prove the effective public-origin policy

The Caddy config inside the web artifact is authoritative. Any outer ingress or
platform proxy must pass this header through without appending a conflicting
directive. Candidate proof records the effective response header at the
isolated public origin and rejects duplicate or contradictory values such as
`immutable` plus `no-cache` on the same response.

The same contract is applied to every active production-like web image:

- `frontend/Dockerfile.prod` -> `frontend/deploy/Caddyfile`;
- `frontend/Dockerfile.railway` ->
  `frontend/deploy/Caddyfile.railway`;
- the host-port overlay -> `deploy/Caddyfile.http`;
- emulator/prod-like compose uses the same `frontend/deploy/Caddyfile`.

`deploy/Caddyfile` is not currently wired into these build or compose paths and
is not changed merely to keep a duplicate file visually similar. Local Vite is
not release evidence. `frontend/deploy/Caddyfile.ff.local` may be aligned only
if S15/S22 selects that local static fixture; it cannot substitute for testing
the production image. The missing local seller Caddy mount is an existing
local-compose concern and is not silently absorbed into D12.

## Resource graph

```text
full candidate SHA (BLG-D09)
  -> immutable web image digest (BLG-D09)
  -> /srv entry documents + current asset inventory
  -> retained prior asset inventories/digests
  -> active Caddy config in the same web image
  -> effective public-origin GET/HEAD responses
       -> entry HTML: no-cache + correct validator behavior
       -> hashed asset: public one-year immutable + manifest digest match
       -> non-hashed/missing asset: no false immutable success
  -> warm browser cache A
  -> same-origin promotion to candidate B
  -> ordinary navigation/reload
  -> candidate entry, candidate bundle URL, candidate build identity
```

| Resource | Ownership in D12 | Lock / interaction |
| --- | --- | --- |
| `frontend/deploy/Caddyfile` | Primary static policy for the production web image | Exclusive `frontend-static-cache-policy` lock |
| `frontend/deploy/Caddyfile.railway` | Equivalent policy for the Railway web image | Same lock and same contract cases |
| `deploy/Caddyfile.http` | Equivalent policy for the host `:8088` override | Same lock; do not touch deploy execution |
| `frontend/deploy/Caddyfile.ff.local` | Optional fixture parity only | Change only if selected by S15/S22 |
| `frontend/Dockerfile.prod`, `frontend/Dockerfile.railway` | Verify config and retained assets are inside the immutable image | Conditional write only if retention input cannot be assembled without it |
| D12 cache-contract verifier and focused tests under `scripts/testing/` | Parse entries, inventory files, exercise GET/HEAD, validators, missing paths, and header conflicts | New D12-owned files; no `scripts/deploy/**` change |
| `scripts/deploy/release_manifest.py`, release build/promotion scripts | D09-owned exact-SHA and artifact identity provider | Read-only dependency; D12 must not race or overwrite D09 |
| API, backend, DB, Redis, Celery, WB/Ozon | Not affected | No lock and no access |

The S17 allocation must replace the broad backlog-only resource list with the
exact selected files above and must serialize any overlap with D09 or another
release task. Discovery of an outer proxy that mutates `Cache-Control` returns
to S13 for a new resource and lock; S18 must not widen scope on its own.

## Delivery order and waves

1. **Interface gate.** Read the accepted D09 architecture/case artifacts when
   available. Bind to its full SHA, web-image digest, build identity, and asset
   inventory fields. If those fields are absent, D12 may still implement and
   unit-test Caddy policy, but S23 is blocked and no substitute manifest is
   invented.
2. **Atomic static-policy change.** Under one exclusive lock, update all active
   Caddy variants and any strictly necessary web-image retention input. Keep
   FF and seller entry routing explicit, static assets fail-closed, and API
   proxy behavior unchanged.
3. **Deterministic verifier.** Add tests against a built production image with
   two distinct fixtures A and B. Validate entry aliases, asset classes,
   `GET`/`HEAD`, stale/current validators, missing assets, header conflicts,
   retained old assets, and same-path/different-bytes collision rejection.
4. **Independent gates.** S19 binds the S15 cases, S20 reviews the effective
   route order and scope, S22 executes focused tests, and S23 runs the whole
   exact-artifact candidate proof outside production.
5. **Release boundary.** S26 may prepare only the named release packet. Without
   separate owner authorization, the task stops honestly at
   `READY_FOR_RELEASE`; S27/S28 are not part of this S13 run.

No parallel Dev cards are created: HTML revalidation, immutable assets,
retention, and warm-cache proof remain one vertical card.

## Required proof contract for S15/S19/S22/S23

The executable matrix must preserve `BLG-D12-AC01` through `AC07` and add the
following precise observations rather than weakening their oracles:

- record method, URL, status, final URL, effective `Cache-Control`, `ETag` or
  other validator, entry digest, selected asset URL, asset digest, manifest
  entry, candidate SHA, web-image digest, and environment identity;
- test FF and seller entry aliases that are present in the selected artifact,
  including one client-route fallback for each;
- issue both `GET` and `HEAD`; a redirect, HTML fallback for an asset, error
  body, or cold-cache-only result cannot pass;
- send A's entry validator to B: changed bytes must return B, while identical
  bytes may return a valid `304`;
- request one referenced hashed JS/CSS asset, one non-hashed public asset, one
  missing asset, and at least one retained A asset after B is active;
- assert that every URL in the retained set has the recorded bytes and that no
  URL collision changed content.

The warm-cache browser fixture uses one stable origin and one persistent
browser profile. It loads candidate A normally, records A's entry digest,
bundle URL, build identity, and successful asset loads, then promotes B at the
same origin without clearing cache or disabling browser cache. An ordinary
open or normal reload must revalidate the entry and show B's build identity and
manifest-linked bundle URL. Capture the navigation response, loaded script and
style URLs, cache/network metadata available from the browser, visible build
identity, console errors, failed requests, and a post-navigation reload/read-
back. A hard reload is captured only as recovery evidence after the ordinary
path has already passed.

S23 must run this against the immutable production web image and D09 manifest,
not Vite dev server. S28 repeats the same proof only after separately
authorized deployment. No production URL, credential, marketplace, or secret
is required or permitted before that gate.

## S14 falsification handoff

The independent architect must attempt to disprove this plan with at least:

- `/`, `/index.html`, FF fallback, `/seller/`, seller fallback, and trailing-
  slash aliases producing different headers;
- Caddy directive reordering that assigns headers before `try_files` rewrite;
- an outer proxy appending or replacing `Cache-Control`;
- a non-hashed file under `/assets/` receiving `immutable`;
- a hashed-looking missing URL returning `200 index.html`;
- a reused hashed URL whose bytes changed;
- stale A validators causing an invalid `304` after B is active;
- candidate B deleting A assets still inside the rollback window;
- browser cache disabled, cache cleared, cold profile, hard reload, or service
  worker behavior making a false warm-cache pass;
- SHA, web-image digest, entry digest, asset digest, and visible build identity
  referring to different candidates.

Any unresolved conflict in those lanes returns `ARCH_REVIEW_REWORK` to S13.
An unavailable D09 identity interface is recorded as the S23 resume condition,
not hidden by header-only evidence.

## Explicit exclusions

This plan performs no implementation, build, test execution, release,
deployment, rollback, production request, live-browser acceptance, secret
access, or WB/Ozon action. It does not introduce a CDN, service worker, offline
mode, API caching, auth/session caching, operator-facing version control, or
general proxy cleanup.

## Final verdict

`ARCH_PLAN_READY`: the plan names the authoritative cache-policy layer, active
static-serving variants, exact resource locks, retained-asset rule, D09
identity boundary, deterministic cases, and the ordinary warm-cache browser
proof required before any release action.
