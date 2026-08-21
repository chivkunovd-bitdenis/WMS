# BLG-I02: WB verdict persistence and fail-closed dispatch

Stage: `S03 DOMAIN_RESEARCH`
Role: `pipeline-ba`
Scope: narrow FBS external-contract research for WB marking verdict persistence.
Research date: `2026-08-21`
Recommended verdict: `RESEARCH_READY`

## 1. Business conclusion

The authoritative runtime signal is each `metaDetails[]` row returned by
`POST /api/marketplace/v3/orders/meta`, not the legacy `meta` object and not WMS's own inference
from `requiredMeta` or `optionalMeta`.

WMS must persist one outcome for every WB call and the exact `key`, `value`, and raw `decision` for
every verdict row WB actually returns, with a locally recorded observation time and the source
request. Completeness is checked separately against the requested assembly-order scope; an omitted
row is missing evidence, not a synthetic verdict. Dispatch must be fail-closed: it is allowed only
when every applicable current verdict is explicitly positive and belongs to the current set of
marking identifiers. Missing, stale, pending, unknown, conflicting, or failed responses do not mean
permission.

WB exposes one exceptional state: `deadlineExceeded`. WB documents it as technically eligible for
delivery while also saying that validation is unfinished and may later succeed or fail. It is not an
explicit positive verdict. Under the stated BLG-I02 business rule it remains dispatch-blocking in WMS
unless Product deliberately approves a weaker policy at S11.

## 2. Versioned sources

| ID | Source and version | Retrieved | Level | Used for |
|---|---|---:|---|---|
| WB-FBS-OPENAPI | [Official WB FBS OpenAPI](https://dev.wildberries.ru/docs/openapi/orders-fbs) | 2026-08-21 | `official` | canonical endpoint, request/response shape, errors, limits, deliver contract |
| WB-MARCH-2026 | [Official WB API March 2026 digest](https://dev.wildberries.ru/news/302) | 2026-08-21 | `official` | `metaDetails` migration, preflight before deliver, `MetaValidationFail`, positive rule published at that date |
| WB-RELEASE-2026-03-31 | [Official WB release-note journal, entry dated 31.03.2026](https://dev.wildberries.ru/release-notes) | 2026-08-21 | `official` | FBS entry "Changes in FBS Orders Methods" (observed by S04 as DOM id `note-500`): `metaDetails`, validation during deliver, and removal of deprecated `meta` announced for 2026-04-30 |
| WB-RATE-LIMITS | [Official WB API information](https://dev.wildberries.ru/docs/openapi/api-information) | 2026-08-21 | `official` | Marketplace rate-limit headers and retry behavior |
| WB-FBS-GUIDE | [Official WB FBS guide](https://dev.wildberries.ru/knowledge-base/articles/019d49a4-0771-7571-aea9-11d5b597f34c/zakazy-fbs) | 2026-08-21 | `official` | seller workflow and marking metadata availability |
| WB-SPEC-SNAPSHOT | [Public snapshot of WB OpenAPI](https://github.com/eslazarev/wildberries-sdk/blob/539e44fc044f4c75cd7c349b62d64c4b55bd88a5/specs/03-orders-fbs.yaml) | 2026-08-21 | `observed` | immutable transport copy of the complete current enum and schema |
| CZ-STATUS | [Official Chestny ZNAK community explanation](https://markirovka.ru/knowledge/tovarnye-gruppy/tabachniye-izdeliya/kogda-vyvodit-iz-oborota-a-kogda-spisyvat-produktsiyu) | 2026-08-21 | `official` | distinction between emitted/applied, in-circulation, written-off/retired states |

Immutable OpenAPI snapshot: commit
`539e44fc044f4c75cd7c349b62d64c4b55bd88a5`, file SHA-256
`3d686e49ff2855b7d0793a7987b2edbff668fe62c7ea8d41b68b9fc5d69e11a9`.

Evidence limitation: direct automated retrieval of the canonical WB documentation returned the WB
portal anti-automation response `HTTP 498` in this environment. The canonical page was therefore
cross-checked through WB's indexed official pages and the immutable public OpenAPI snapshot above.
S04 must reopen the canonical page independently before approving the enum. No production or WB
sandbox request was made.

## 3. External API contract

### 3.1 Metadata preflight

- Operation: `POST https://marketplace-api.wildberries.ru/api/marketplace/v3/orders/meta`.
- Authorization category: Marketplace.
- Request body: `{ "orders": [<int64 order id>, ...] }`, required, maximum 100 order IDs.
- Success: HTTP `200`, body `orders[]`; each row contains `id` and `metaDetails[]`.
- Verdict row: `metaDetails[].key`, nullable `metaDetails[].value`, and
  `metaDetails[].decision`.
- Marking keys: `sgtin`, `uin`, `imei`, `gtin`, `expiration`, `customsDeclaration`.
- Errors: `400`, `401`, `402`, `403`, `404`, `429`; timeout, transport error, malformed body, or
  HTTP `5xx` are also non-success outcomes.
- No pagination token exists. Volume is handled by deterministic batches of at most 100 IDs.
- Limit for FBS marking reads/deletes: 300 requests per minute per seller account, 200 ms interval,
  burst 20. Under the canonical FBS documentation current on the research date, every response with
  an HTTP `4XX` status counts as 10 requests. This is not special to `409`. Runtime protection must
  still use the actual `X-Ratelimit-*` headers returned by WB.
- On `429`, retry only after `X-Ratelimit-Retry`; observe `X-Ratelimit-Reset` and
  `X-Ratelimit-Limit`.
- The success schema does not provide a WB verdict timestamp. WMS must store its own UTC
  `observed_at`; it must not label this value as time generated by WB or Chestny ZNAK.
- The schema does not promise one row per key or order. Preserve the whole ordered `metaDetails[]`
  and treat an omitted requested order, missing expected key, duplicate conflict, or absent decision
  as incomplete rather than positive.

### 3.2 Delivery response

- Operation: `PATCH /api/v3/supplies/{supplyId}/deliver`.
- HTTP `204` is the terminal WB success for moving the supply to delivery. It has no response body
  and therefore contains no order-level or metadata-key verdict rows.
- HTTP `409` with `code: "MetaValidationFail"` contains
  `data.orders[].id` and `data.orders[].metaDetails[]` with `key`, `value`, and `decision`.
- `data.orders[]` is the subset whose metadata failed validation or is still being validated. WB
  does not promise that it contains every order in the supply, every positive order, or every key.
- The `409` response is an authoritative negative result for that delivery attempt and must be
  appended even if a preceding preflight was positive. It blocks that attempt but is not a complete
  metadata snapshot and must not replace the preflight projection.
- Other HTTP failures, timeout, malformed response, or absence of the expected `204` are not
  permission and must not be converted into a green WMS state. They can legitimately contain zero
  metadata verdict rows.

## 4. Verdict matrix

### 4.1 SGTIN / Chestny ZNAK

| Raw WB `decision` | WB meaning | WB delivery eligibility | BLG-I02 normalized class | WMS dispatch |
|---|---|---|---|---|
| `filled` | code is attached; WB says validation is not required | yes | `CONFIRMED_ALLOW` | allow |
| `optional` | code is absent and not required by WB | yes | `CONFIRMED_ALLOW` | allow, subject to the separate D03 Product/legal oracle |
| `sgtinIntroduced` | item is admitted for sale; validation passed | yes | `CONFIRMED_ALLOW` | allow |
| `sgtinSoldB2B` | B2B-sold item is admitted for resale; validation passed | yes | `CONFIRMED_ALLOW` | allow |
| `deadlineExceeded` | validation timed out and continues; future result may pass or fail | yes | `WB_ELIGIBLE_UNCONFIRMED` | block for BLG-I02 |
| `pending` | validation continues | no | `WAIT` | block and poll |
| `required` | required code is not attached | no | `BLOCK` | block |
| `sgtinInvalidFormat` | invalid format | no | `BLOCK` | block |
| `sgtinNoGS` | GS separator `0x1D` is missing | no | `BLOCK` | block |
| `sgtinHasInvalidSymbols` | invalid symbols or spaces | no | `BLOCK` | block |
| `sgtinHasNonLatinSymbols` | symbols outside allowed special/Latin set | no | `BLOCK` | block |
| `sgtinInvalidPattern` | invalid code structure | no | `BLOCK` | block |
| `sgtinNotFound` | code not found in Chestny ZNAK | no | `BLOCK` | block |
| `sgtinEmitted` | code was issued but is not in circulation | no | `BLOCK` | block |
| `sgtinApplied` | putting the item into circulation is not completed | no | `BLOCK` | block |
| `sgtinWrittenOff` | code is written off | no | `BLOCK` | block |
| `sgtinWithdrawn` | code left circulation | no | `BLOCK` | block |
| `sgtinRetired` | code left circulation | no | `BLOCK` | block |
| `sgtinDisaggregated` | aggregation was disbanded | no | `BLOCK` | block |
| `sgtinDisaggregation` | aggregation is disbanded | no | `BLOCK` | block |
| `sgtinAppliedNotPaid` | code is unpaid | no | `BLOCK` | block |

Chestny ZNAK's own material supports the lifecycle distinction: `Emitted` and `Applied` are not the
same as `In circulation`; written-off/retired states are later lifecycle states. WMS does not call
Chestny ZNAK directly in this contract. It persists and interprets WB's verdict.

### 4.2 Other WB identifiers handled by the same persistence path

| Key | Explicit positive | WB-eligible but unconfirmed | Wait/block |
|---|---|---|---|
| `imei` | `filled`, `optional`, `imeiMaySell`, `imeiSoldB2B` | `deadlineExceeded` | `required`, `pending`, `imeiInvalidFormat`, `imeiAlreadySold` |
| `uin` | `filled`, `optional`, `uinMaySell` | `deadlineExceeded` | `required`, `pending`, `uinInvalidFormat`, `uinBadStatus`, `uinBadProcess`, `uinBadStatusAndBadProcess`, `uinNotFound` |
| `gtin` | `filled`, `optional` | none documented | `required` |
| `expiration` | `filled`, `optional` | none documented | `required` |
| `customsDeclaration` | `filled`, `optional` | none documented | `required` |

The current WB text places `gtin.required` and `expiration.required` under a positive heading while
describing each as "required and not filled; validation failed". This is an official documentation
contradiction. Fail-closed semantics use the description and common `required` meaning: block. S04
must explicitly challenge this point.

Legacy values currently known by WMS such as `accepted`, `rejected`, `allowedWithoutCheck`, and
`replacementRequired` are not present in the current documented `metaDetails.decision` enum. If WB
returns one, persist it exactly and classify it `UNKNOWN_BLOCK`; do not silently map it to success.

## 5. Persistence contract for downstream Product and Architecture

Persistence has two append-only levels: exactly one attempt outcome for every call, plus zero or
more verdict detail rows returned by WB for that attempt. A mutable "latest" projection may be
derived from this history, but must not replace either level.

### 5.1 Attempt outcome: exactly one row per call

An attempt row is mandatory even when WB returns no `metaDetails`, no body, or no HTTP response.

| Field | Requirement |
|---|---|
| `attempt_id` | stable local identity for one preflight or deliver call; parent for all returned detail rows |
| `tenant_id`, `seller_id` | mandatory ownership boundary; rate limits and tokens are seller-scoped |
| `source_operation` | `orders_meta_preflight` or `supply_deliver` |
| nullable `wb_supply_id` | required for `supply_deliver`; nullable for a standalone preflight |
| `request_scope` and `requested_order_ids_hash` | exact tenant-scoped order set, ordering and batch identity; protected raw IDs or a durable protected reference are retained when needed for completeness checks |
| `transport_outcome` | `HTTP_RESPONSE`, `TIMEOUT`, `CONNECTION_ERROR`, or `MALFORMED_RESPONSE`; absence of HTTP is explicit |
| nullable `http_status`, nullable `wb_error_code` | preserves `200`, bodyless `204`, `409/MetaValidationFail`, other HTTP failures, and non-HTTP outcomes without invented values |
| `attempt_result` | `PREFLIGHT_RESPONSE`, `DELIVER_ACCEPTED`, `DELIVER_REJECTED_PARTIAL`, `HTTP_ERROR`, `TRANSPORT_ERROR`, or `MALFORMED_RESPONSE` |
| nullable `wb_request_id` | store when WB returns it in body or headers; absence is allowed |
| `observed_at_utc` | WMS receive/completion time; explicitly not a WB or Chestny ZNAK event time |
| `request_payload_hash`, nullable `response_payload_hash` | request audit plus exact response bytes when a body exists; bodyless `204` and no-response failures remain honestly nullable |
| `response_body_present` | explicit boolean; `false` for a canonical bodyless `204` and for transport outcomes without response bytes |
| nullable protected `response_payload` or durable object reference | exact WB body for incident reconstruction when present; tenant-scoped and excluded from ordinary logs |
| `contract_snapshot_sha256` | binds interpretation to the versioned external contract used above |

Attempt semantics are explicit:

- `200` from `orders_meta_preflight` stores the attempt and every returned detail row. Completeness
  is evaluated only after both have been persisted.
- bodyless `204` from `supply_deliver` stores `DELIVER_ACCEPTED` on the attempt. It proves that WB
  accepted the supply transition, but creates zero synthetic order/key decisions and does not turn
  prior detail rows into `CONFIRMED_ALLOW` rows.
- `409 MetaValidationFail` stores `DELIVER_REJECTED_PARTIAL`, the raw response, and only the
  negative or unfinished rows WB actually returned. It blocks this attempt and never deletes,
  fills, or replaces rows absent from the partial response.
- timeout, `429`, other `4XX`, `5XX`, and malformed responses store their honest attempt outcome
  with zero or more detail rows. None authorize dispatch.

### 5.2 Verdict detail: zero or more rows per attempt

Detail rows exist only when WB supplied a real `metaDetails[]` item. No placeholder row is allowed.

| Field | Requirement |
|---|---|
| `attempt_id` | mandatory parent link to the attempt outcome |
| `wb_order_id` | external order identity exactly associated with this returned detail |
| `order_ordinal`, `meta_ordinal`, `meta_key` | preserve response order, repeated rows, and the exact WB key |
| nullable protected `meta_value`, `meta_value_hash` | bind the verdict to the exact identifier revision without leaking KIZ to logs |
| `decision_raw` | exact case-sensitive WB string, never overwritten by normalized status |
| `decision_class` | `CONFIRMED_ALLOW`, `WB_ELIGIBLE_UNCONFIRMED`, `WAIT`, `BLOCK`, `UNKNOWN_BLOCK`, or `INCOMPLETE_BLOCK` |
| `reason_text` | operator-safe Russian reason derived from the raw WB code; raw code remains available for support |

The latest preflight projection additionally needs `is_complete`, `superseded_at`, and the current
marking-set revision or fingerprint. It may be complete only from a successful `orders/meta` response
that includes every requested order and all applicable real detail rows under the checks in section
6. A `409` may add newer negative evidence for returned order/key pairs, but cannot establish or
replace a complete snapshot. A positive verdict for an earlier KIZ value must not authorize a later
value.

## 6. Fail-closed dispatch invariant

For the current supply and current marking-set revision:

1. Fetch metadata in batches of at most 100 immediately in the dispatch execution path.
2. Persist the attempt outcome and all real detail rows atomically before evaluating permission.
3. For the successful preflight projection, require every requested order to be present and every
   applicable metadata row to be complete.
4. Require every current row to normalize to `CONFIRMED_ALLOW`.
5. Treat `deadlineExceeded`, `pending`, unknown values, missing rows, stale value hashes, conflicting
   duplicates, HTTP/transport errors, `429`, and malformed responses as blocked.
6. Call WB deliver only after the preflight invariant passes.
7. Persist the deliver attempt outcome before reporting its result. Only HTTP `204` means WB
   accepted dispatch, and it creates no per-key verdict rows.
8. Persist `409 MetaValidationFail` as an append-only partial negative attempt result plus only its
   returned real detail rows. It blocks that delivery attempt without replacing the complete
   preflight projection or inventing decisions for omitted orders/keys.

There is no documented freshness TTL and no webhook for these verdicts. Polling is required for
`pending`; use bounded backoff under WB rate limits. A time-of-check/time-of-use race remains possible,
so the delivery response is the final authority for the attempt.

## 7. Capability matrix

| Lane | Applicability | Evidence/result | Coverage |
|---|---|---|---|
| Official API, version, date | applicable | canonical docs + release note + immutable spec SHA | covered |
| Seller/operator workflow | applicable | WB FBS guide; preflight before deliver | covered |
| FBS/FBO and state machine | FBS applicable; FBO out of scope | FBS metadata and deliver states only | covered |
| Catalog/orders/stocks/reserves | order identity applicable; other lanes out of scope | `requiredMeta`/`optionalMeta` identify availability; no catalog or stock change | covered |
| Marking/dispatch/cancel/return | marking and dispatch applicable; cancel/return unchanged | full verdict and 409 matrix | covered |
| Pagination/batch | applicable | no pagination; max 100 IDs per request | covered |
| Rate limits/retries | applicable | 300/min, 200 ms, burst 20, every `4XX` counts as 10 requests, runtime `X-Ratelimit-*` protection | covered |
| Partial success | applicable | attempt outcome plus `0..N` real detail rows; omissions/conflicts are incomplete and block | covered |
| Webhooks/polling | applicable | no webhook documented; bounded polling for `pending` | covered |
| Security/roles/tenant | applicable | Marketplace authorization; tenant/seller-scoped storage and limits | covered |
| Volume/emergency | applicable | deterministic batches; no optimistic fallback during outage | covered |
| Competitor screens/workflow | not applicable to narrow existing call | no new module or operator workflow is researched here | N/A |
| Emulator/sandbox | required later by `external_contract` trait | official sandbox exists; not called due explicit no-live-WB boundary | deferred to S15, not an S03 claim gap |

No applicable capability row is left without a disposition.

## 8. Downstream boundaries and questions

- `BLG-I01` owns use of the current WB endpoint and polling transport.
- `BLG-D03` owns the Product/legal oracle for `requiredMeta`, `optionalMeta`, and whether optional
  marking must still be supplied. BLG-I02 must not redefine that policy.
- `BLG-I02` owns durable verdict history and the fail-closed dispatch invariant.
- S11 Product must confirm that `deadlineExceeded` is blocked despite WB technical eligibility. This
  is already the only interpretation consistent with BLG-I02's "explicitly confirmed positive"
  requirement.
- S13 Architecture must define protected raw-payload retention, current-revision identity, atomic
  persistence before dispatch, and recovery after a crash between WB response and local commit.
- S15 must bind cases for every SGTIN enum, unknown decision, missing order/key, duplicate conflict,
  stale KIZ revision, timeout/`429`/`5xx`, `409 MetaValidationFail`, and `204` success to an emulator
  or separately allowed WB sandbox. No production call is required or permitted.

Research can advance to isolated S04 critique. The S04 critic must independently verify the current
enum, the `deadlineExceeded` conflict, and the `gtin/expiration required` documentation contradiction.

## 9. S04 rework closure map

| S04 finding | Contract correction |
|---|---|
| `RC-01` | Sections 3.2, 5.1, 5.2 and 6 define `409 MetaValidationFail` as an append-only partial negative delivery-attempt result, never a projection replacement. |
| `RC-02` | Section 5 separates one mandatory attempt outcome from `0..N` real verdict details; bodyless `204` and no-body failures require no synthetic key or decision. |
| `RC-03` | Sections 3.1 and 7 state the current canonical accounting rule: every HTTP `4XX` counts as 10 requests, with runtime header protection retained. |
| `RC-04` | Section 2 attributes `metaDetails`, deliver validation, and legacy `meta` removal to the official FBS release-note entry dated `31.03.2026` in the canonical journal, observed by S04 as DOM id `note-500`. |

All enum mappings, the Product question for `deadlineExceeded`, and fail-closed `UNKNOWN_BLOCK`
semantics remain unchanged. Closure of these four findings makes S03 ready for a new independent
S04 run; it does not self-issue `RESEARCH_PASSED`.
