# S12 TASK_CUT - BLG-D12

## Verdict

`TASK_CUT_READY`

## Atomic vertical card

**Card ID:** `BLG-D12-C1`
**Title:** Deliver a revalidated WMS entry document and immutable
content-addressed frontend assets as one exact-artifact release outcome.

This is one atomic release card. It must not be split into an HTML-header
change, an assets-header change, and a browser check: none of those fragments
alone prevents an operator from receiving a stale index that points to an old
or unavailable bundle. The observable outcome exists only when all entry
document aliases revalidate, only content-addressed assets receive the
immutable policy, and an ordinary warm-cache browser open reaches the bundle
from the same candidate artifact.

## Card contract

After an authorized exact-artifact release, `/`, `/index.html`, and every
application-route fallback that serves that same entry document return
`Cache-Control: no-cache` for both `GET` and `HEAD`. A browser that already
holds the prior index revalidates it during its ordinary open or normal reload;
when the entry document changed, it receives the current document and loads
the current hashed bundle without an operator cache-clear instruction.

Only an asset whose filename is content-addressed may return
`Cache-Control: public, max-age=31536000, immutable`. Its URL must identify
the same bytes recorded in the candidate manifest. HTML and non-hashed assets
must not receive this immutable one-year policy. Prior hashed assets remain
available for the declared promotion and rollback window so an old retained
index cannot become a broken mixed-version page.

This card does not create a warehouse action, an operator-facing release UI,
a service worker or offline mode. It preserves authentication, authorization,
API and tenant behavior, database and worker state, and all external
marketplace boundaries.

## Implementation boundary

S13 must identify every serving layer capable of setting or overriding these
headers, choose one authoritative policy, name its configuration/build inputs,
and establish the immutable artifact manifest and runtime/build identity used
for proof. S14 must independently test the plan for conflicting proxy or
application headers, URL-alias gaps, incorrect hash classification, stale
validator behavior, and rollback retention loss.

S18 may implement only the resulting bounded serving/build configuration and
focused verification required to deliver this card. It must not widen into
general CDN/proxy tuning, a change to API caching, session/auth caching,
service-worker behavior, operator workflows, database schema, worker logic,
marketplace calls, production deployment, or release authorization.

## Acceptance cases for S15

| ID | Fixture or oracle | Required result |
| --- | --- | --- |
| `BLG-D12-AC01` | Immutable non-production candidate; `GET` and `HEAD` for `/`, `/index.html`, and an application-route fallback that serves the entry document | Each effective response has `Cache-Control: no-cache`; it is an entry-document response, not a redirect, error, or unrelated fallback. |
| `BLG-D12-AC02` | Candidate manifest and a selected hashed JS or CSS URL referenced by its index | `GET` and `HEAD` return `Cache-Control: public, max-age=31536000, immutable`; the response digest equals the matching manifest entry and the URL is referenced by that index. |
| `BLG-D12-AC03` | A selected non-hashed asset and the entry HTML | Neither receives the immutable one-year policy. The case fails if directory placement alone classifies an asset as immutable. |
| `BLG-D12-AC04` | Prior index and bundle deliberately warmed in browser cache, then a distinct immutable candidate index/manifest on the isolated integration target | Ordinary open or normal reload revalidates the entry document and visibly reaches the new runtime/build identity and bundle URL. No cache clear, hard reload, missing asset, mixed old/new document, console error, or network load failure is accepted. |
| `BLG-D12-AC05` | Conditional request with a validator retained from the prior index, first when current index bytes differ and then when bytes are identical | A changed index does not preserve the old body through an incorrect `304`; `304 Not Modified` is accepted only for byte-identical current entry content. |
| `BLG-D12-AC06` | Previous immutable artifact/index within the declared rollback window | Its referenced hashed assets remain retrievable and match their recorded manifest entries; the candidate does not delete or overwrite an old URL with different bytes. |
| `BLG-D12-AC07` | Missing asset, redirect, or error path under the selected serving layer | It cannot be used as successful proof for an entry document or selected asset; headers/status/body identity are recorded distinctly. |

S15 must make these deterministic, bind each request and browser run to the
full candidate SHA plus index/asset digests, and identify the local/integration
fixture used for the warm-cache transition. Hard reload may be recorded only as
supporting recovery evidence, never as the success criterion for AC04.

## Review and browser-proof boundary

S20 review must check that a single effective header policy covers `GET` and
`HEAD`, all entry aliases and fallback responses, and only truly
content-addressed assets. It must reject conflicting header emitters, a
non-hashed immutable exception, a reused hashed URL, unproven old-asset
retention, or evidence not bound to an exact SHA and manifest.

S23 integration proof must execute AC01-AC07 against an immutable candidate
outside production and record response status, effective headers, index digest,
referenced asset URLs, asset digest, manifest entry, network/console result,
and the warm-cache browser build identity. BLG-D09's exact-SHA
bundle-verification mechanism is a hard prerequisite; header checks alone do
not pass integration.

S26 release preparation must name the 40-character `release_candidate_sha`,
artifact digests, target environment, previous rollback artifact, asset
retention window, smoke steps, stop conditions, and rollback procedure. S27
remains a separate owner-authorized deploy gate. Only after that authorization
may S28 repeat the exact-artifact headers and warm-cache visible-browser proof
against the deployed runtime; `curl`, a cold browser, or hard reload alone is
insufficient.

## Handoff and explicit exclusions

- **Next stage:** `S13 ARCHITECT_PLAN`, owned by `solution-architect`, because
  this is a high-risk `release_change`.
- **S16 packet condition:** Product receives this card, the S11 contract, and
  the completed S13-S15 artifacts. Any change to the card or contract
  invalidates the downstream Product-before-Dev decision.
- **Not produced by S12:** implementation, commit, push, merge, deployment,
  production request, live browser acceptance, release candidate approval, or
  rollback action.

## Verdict

`TASK_CUT_READY`: `BLG-D12-C1` preserves the single user-visible release
outcome, gives S13-S15 a complete acceptance surface, and keeps all live
release authority and proof at their later independent gates.
