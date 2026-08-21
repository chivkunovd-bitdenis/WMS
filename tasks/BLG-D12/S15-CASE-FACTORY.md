# S15 CASE_FACTORY - BLG-D12

## Scope and BA verdict

This package turns the approved S11 product contract, atomic S12 card
`BLG-D12-C1`, S13 serving plan, and S14 falsification constraints into
deterministic non-production cases. It does not authorize implementation,
build execution, release promotion, deployment, rollback, production request,
secret access, or any live WB/Ozon action.

**BA verdict:** `CASES_READY`.

`S15-CASES.json` defines sixteen GOLD cases. Together they prove the one
release outcome: a changed entry document is revalidated during an ordinary
warm-cache navigation, it loads the candidate's immutable referenced assets,
and the prior immutable artifact remains internally consistent through the
declared rollback window. A header-only, cold-cache-only, or hard-reload-only
result is not a passing substitute.

## Fixture and reset contract

Fixture `blg-d12-cache-control-two-candidate-v1` is a hermetic local or
isolated-integration fixture built from two distinct immutable production-web
images at one stable test origin. Candidate A and candidate B each provide:

- full candidate SHA, web-image digest, active Caddy-config digest, entry
  digests, visible build identity, and complete static URL-to-digest inventory;
- FF and seller entry documents, their real client-route fallbacks, a selected
  hashed JS/CSS asset, a non-hashed public asset, and a deliberately missing
  hashed-looking asset path;
- B's retained copy of every A immutable asset within the named rollback
  window, plus a negative same-path/different-bytes collision variant.

S19 prepares a fresh persistent browser profile per case group. It loads A
normally at the stable origin, records A's entry digest, manifest-linked asset
URLs and visible identity, then atomically switches only the fixture routing
to B. It never clears storage, disables cache, changes origin, uses a service
worker shortcut, or makes hard reload the primary path. Each HTTP case receives
a clean fixture namespace; each browser group receives a new A-warmed profile.
Reset removes only that case namespace/profile after evidence capture and
recreates it from versioned A/B images and manifests. No shared, live, or
production resource is addressed; external egress is forbidden.

## Coverage matrix

| Requirement / attack lane | Direct GOLD case | Breaker case | Oracle | S19 planned binding |
| --- | --- | --- | --- | --- |
| AC01: FF entry aliases and fallback revalidate for `GET` and `HEAD` | `D12-C1-01` | `D12-C1-02`, `D12-C1-11` | S11 entry-document rule; S13 A1 | `scripts/testing/test_blg_d12_cache_control.py::test_ff_entry_aliases` |
| AC01: seller aliases and fallback have the same policy | `D12-C1-03` | `D12-C1-11` | S13 A1; S14 alias falsification | `scripts/testing/test_blg_d12_cache_control.py::test_seller_entry_aliases` |
| AC02: referenced content-addressed asset is immutable and manifest-bound | `D12-C1-04`, `D12-C1-15` | `D12-C1-05`, `D12-C1-12`, `D12-C1-16` | S11 hashed-asset policy; S13 A2 | `scripts/testing/test_blg_d12_cache_control.py::test_manifest_bound_immutable_assets`, `scripts/testing/test_blg_d12_cache_control.py::test_complete_b_immutable_inventory` |
| AC03: HTML and non-hashed assets never become immutable | `D12-C1-05` | `D12-C1-12` | S11 non-hashed prohibition | `scripts/testing/test_blg_d12_cache_control.py::test_non_hashed_never_immutable` |
| AC04: A-warmed ordinary navigation/reload reaches B without cache clearing | `D12-C1-06` | `D12-C1-07`, `D12-C1-13` | S11 operator outcome; S13 warm-cache proof | `frontend/tests-e2e/release-cache-control.spec.ts#D12-C1-06` |
| AC05: stale validator cannot preserve changed A HTML; identical current HTML may 304 | `D12-C1-08` | `D12-C1-09` | S11 validator boundary | `scripts/testing/test_blg_d12_cache_control.py::test_entry_validators` |
| AC06: prior immutable assets are retained and never overwritten | `D12-C1-10` | `D12-C1-14` | S11 rollback retention; S13 A3 | `scripts/testing/test_blg_d12_cache_control.py::test_retained_a_assets` |
| AC07: missing/redirect/error responses are not asset or entry proof | `D12-C1-12` | `D12-C1-02` | S11 proof boundary; S13 A2 | `scripts/testing/test_blg_d12_cache_control.py::test_false_proof_responses_rejected` |
| Effective policy is candidate-bound and unmodified by outer layer | `D12-C1-11` | `D12-C1-02` | S13 A4; S14 header-conflict attack | `scripts/testing/test_blg_d12_cache_control.py::test_effective_header_has_one_owner` |
| S14 complete immutable inventory: current B, transitive chunks, CSS imports, fonts and images are candidate-manifest-bound | `D12-C1-15` | `D12-C1-16` | S14 complete-inventory constraint; S13 A2 | `scripts/testing/test_blg_d12_cache_control.py::test_complete_b_immutable_inventory`, `scripts/testing/test_blg_d12_cache_control.py::test_immutable_url_outside_manifest_rejected` |

There are no applicable API, authentication, authorization, tenant, database,
worker, print, device, or marketplace cases: every approved upstream artifact
expressly preserves those surfaces. Their absence here is a scope constraint,
not an omitted implementation test.

## Case-audit gate

This author is `pipeline-ba`, the case writer, and is **not** an independent
`case-auditor`. This artifact does not claim `CASE_AUDIT_PASSED` and must not
be used as self-audit evidence. An independent auditor must review the exact
hashes of this Markdown and `S15-CASES.json`, confirm every S12 acceptance row
and S14 attack lane has deterministic direct and breaker coverage, verify the
fixture/reset and S19 bindings, and submit a separate `CASE_AUDIT_PASSED`
receipt. That independent receipt remains required before the cases may be
treated as audit-accepted; it is not a deploy authorization or a substitute
for S16 Product approval.

## S19 binding plan

S19 must turn every `PLANNED_FOR_S19` reference into executable tests against
the immutable production-web image fixture, never a Vite server. It must record
candidate SHA, web-image and Caddy-config digests, environment identity, method,
URL, final URL, status, complete effective `Cache-Control`, validator, entry
digest, asset URL/digest, manifest entry, browser-visible build identity,
console errors and failed requests. Digest comparisons request
`Accept-Encoding: identity`.

S19 must fail closed for a missing D09 identity interface, an inventory that
omits transitive chunks/fonts/images, an immutable URL outside that inventory
or its candidate manifest, non-deterministic A/B switching, a profile/origin
reset, or an oracle change. `D12-C1-15` derives the complete current-B set from
the candidate manifest plus its transitive import graph and verifies every
served immutable response; `D12-C1-16` proves that the same verifier rejects a
served immutable URL absent from that set. Hard reload may be collected only
after `D12-C1-06` succeeds as supporting recovery evidence. S23 later executes
the same package against the immutable candidate outside production; S28 only
repeats it after separately authorized deployment.

## Handoff

The executable case package is ready for independent audit and then S16
Product-before-Dev. No implementation or release action is authorized by this
stage.
