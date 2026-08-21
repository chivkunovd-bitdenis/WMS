# S11 PRODUCT_CONTRACT_APPROVAL - BLG-D12

## Product decision

The approved outcome is that an operator who opens WMS after a release receives
the current application entry document and therefore the frontend bundle from
that release, while content-addressed frontend assets remain efficiently
cacheable.

Every response that serves the application `index.html`, including `/`, the
explicit `/index.html` path and an application-route fallback that returns the
same document, must use `Cache-Control: no-cache`. Here `no-cache` means that a
browser may retain the document but must revalidate it before reuse. A
successful release must not depend on an operator clearing browser storage or
knowing a special recovery sequence.

Only assets whose filename contains a content hash that changes when their
bytes change may use the long-cache contract. Those responses must use a public
one-year cache lifetime and immutable semantics, equivalent to
`Cache-Control: public, max-age=31536000, immutable`. A non-hashed file must not
receive this immutable policy merely because it is under an assets directory.

## Operator outcome and release rationale

1. Before promotion, the browser may have the previous `index.html` and its
   referenced hashed bundle in cache.
2. After an authorized exact-artifact release, opening or normally reloading
   WMS revalidates the entry document and returns the index from the deployed
   release.
3. That index references the hashed bundle recorded in the same immutable
   artifact manifest. The browser loads that bundle or safely reuses it only
   when its URL and bytes are identical.
4. The visible application reports the runtime/build identity expected for the
   released artifact, so the release proof can distinguish the new bundle from
   a successful server command that left the browser on the old frontend.

This is a release-delivery correction, not a new warehouse step. It must not
add an operator prompt, version-selection action, cache-clear instruction or
change to any warehouse process. The operator's ordinary entry and reload path
is the acceptance path.

## Approved behavioral boundaries

- `/`, `/index.html` and every fallback response whose body is the same
  application entry document must have the same no-cache behavior. URL aliases
  must not create a stale-index path.
- A revalidation result may be `304 Not Modified` only when the retained index
  is byte-identical to the currently deployed entry document. After an index
  change, validators must not incorrectly preserve the old body.
- A hashed asset URL is content-addressed: the same URL must never be reused for
  different bytes. Its response digest must match the immutable artifact
  manifest.
- Old hashed assets must remain available for at least the declared promotion
  and rollback window. Removing them while an old index can still be active
  creates a broken mixed-version state and is not an acceptable cleanup.
- Non-hashed assets and HTML must not receive the immutable one-year policy.
- Cache policy must be consistent on successful `GET` and `HEAD` responses used
  by release checks. Error, redirect or fallback responses must not masquerade
  as proof of the requested file.
- The change must not alter authentication, authorization, API behavior,
  tenant data, database state, worker behavior or external marketplace calls.

## Required downstream proof

S12 may cut implementation and verification into vertical cards, but the
entry-document policy, hashed-asset policy and browser bundle proof form one
release outcome and must not be accepted independently.

S13-S15 must define the serving layers that can add or override headers and
cover at least: `/`, `/index.html`, an applicable application-route fallback, a
hashed asset, a non-hashed asset, `GET`/`HEAD`, stale validators, missing assets
and rollback retention. The architecture must name one authoritative header
policy and detect conflicting headers from another proxy or application layer.

S23 must test an immutable candidate outside production and bind all evidence
to the exact candidate SHA and artifact manifest. The proof must record:

- response status and effective `Cache-Control` for `/`, `/index.html` and the
  selected hashed asset URL;
- the index digest and the exact script/style asset URLs it references;
- the selected asset digest and its matching manifest entry;
- a browser run that starts with the previous index and bundle already cached,
  then uses an ordinary open or normal reload and visibly reaches the new
  bundle/build identity;
- a hard reload as supporting recovery evidence, not as the sole success path;
- no missing-asset response, mixed old/new entry document or console/network
  loading failure.

The BLG-D09 exact-SHA and bundle-verification mechanism is a prerequisite for
credible integration and release evidence. If BLG-D09 has not supplied that
mechanism by S23, BLG-D12 cannot be promoted on header checks alone.

Before release authorization, S26 must name the full immutable
`release_candidate_sha`, artifact digests, target environment, previous
rollback artifact, asset-retention window, smoke steps, stop conditions and
rollback procedure. Wrong or missing headers, an index/manifest mismatch, a
browser still executing the previous bundle after normal revalidation, or a
missing referenced asset blocks release authorization.

After a separately authorized S27 deploy, S28 must repeat the exact-artifact
header and warm-cache browser proof against the deployed runtime. A deploy
command exit code, `curl` alone, a cold browser, or a hard reload alone does not
prove the operator outcome. On failure, the release must stop or roll back to
the named previous immutable artifact; the rollback proof must show that its
index and retained hashed assets load together.

## Authorization boundary

This Product verdict approves the expected release behavior only. It does not
authorize a deploy, production request, release promotion, rollback, secret
access, branch selection, merge, commit or push. S27 requires a separate owner
authorization naming the exact full release candidate SHA and immutable
artifact manifest. Without that authorization, the honest release result is
`READY_FOR_RELEASE`, not deployed or `DONE`.

## Out of scope

No code implementation, infrastructure mutation, live environment check,
production traffic, live WB/Ozon operation or browser acceptance is performed
at S11. Service-worker introduction, offline mode, operator-facing release UI
and unrelated CDN/proxy tuning are not approved by this contract.

## Verdict

`PRODUCT_CONTRACT_APPROVED`: the contract guarantees revalidated application
HTML, immutable long caching only for content-addressed assets, and exact-
artifact warm-cache browser proof of the new bundle without changing the
operator's warehouse process or authorizing release activity.
