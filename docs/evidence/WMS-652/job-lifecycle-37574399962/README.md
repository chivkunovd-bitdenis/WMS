# WMS-652 actual job lookup run37574399962

Actual single workflow_dispatch attempt1 completed successfully on
bb8528b3127f3375fb29685577b2ab045d607658, branch
codex/wms652-chrome141-job-lifecycle-diagnostic. Job112639941395;
artifact11462046578 has the exact HEAD/run/attempt in its name and API identity.
Ubuntu24.04.5, Node24.21.0, Playwright1.56.1, Chromium141.0.7390.37.
Run API, job API, artifact API and full job log are preserved here.

Original strict result:43PASS, exit0, all exact43 cases in original order.
Original positive commands only:11670 unique sends and11670 unique replies, identical
ID sets,0 native errors,0 timeouts,0 pending. No original failure IDs in this run.
These counts exclude all auxiliary commands and their expected native errors.

Four auxiliary sends/replies, each paired to the original first fulfill by EXACT
FetchID (not URL/time proximity). Each is GET/protocolXHR, exact synthetic workspace
URL, absent networkId. Every auxiliary native reply is exactly code-32000 and
message "Can only get response body on HeadersReceived pattern matched requests."
Thus all four prove ALIVE at their lookup. No ABSENT/unexpected/unowned/duplicate,
no auxiliary pending, no response-body output. All original paired fulfills succeed.

| Auxiliary command | FetchID | Original fulfill | Send/current reply generation | Default context ID |
| --- | --- | --- | --- | --- |
| -1 | interception-job-2207.0 | 2563 | 43/43 | 12 |
| -2 | interception-job-4315.0 | 4920 | 79/79 | 21 |
| -3 | interception-job-4534.0 | 5167 | 83/83 | 22 |
| -4 | interception-job-5221.0 | 5937 | 95/95 | 25 |

ledger.json preserves exact send/reply identities, case names, active default
execution-context unique IDs, frame ID, and navigation reply/frame loader IDs at
each query. Navigate reply and frame-navigation loader IDs agree in these four
observations. The fourth belongs to qr+pool/supply_ids=A,B, which failed in the
previous run, but has a DIFFERENT FetchID and successful fulfill here. It cannot
explain the previous failed ID. Frame/context observations do not identify the
request's document owner: paused has no networkId/loaderId/executionContextId.

Important capture limit: focused metadata retained23245 records and dropped7364
by conservative byte budget. Its share is32MiB of the combined64MiB budget; the
final physical file is8728903 bytes because accounting deliberately overestimates.
No focused observer/native-error drops; nativeErrorsObserved0 agrees with complete
original transport. Auxiliary/context capture retained236 records with all its
drop/error/unsent counters0. Combined23481 retained records; finalSize drops0.
Missing focused lifecycle records are not inferred. Complete original transport,
all retained context and honest counters are preserved losslessly.

Source proof:2546 exact original source Git bindings match4c532;2546 before/after
file hashes equal. Reverse all three insertions to recover frozen browser bytes;
all43 unchanged cases and original native forwarding remain strict. Original600s
shell differs only by sibling runner path. Both generated observer copies match
published HEAD; exact Request-only Fetch pattern byte pin verified. All20 artifact
members are recoverable from raw/ with original-byte SHA256/length in
raw-manifest.json. Larger raw/JSON members are losslessly gzip-compressed; no
member discarded. provenance-manifest.json records API/log/analyzer/ledger hashes.

Result is NONREPRODUCTION, not a fix, release approval or historical cause proof.
No disappearance bound was observed: ALIVE lookups and same-ID fulfills succeeded.
Actual retirement reason/JS caller/cancellation and old etalon cause remain UNKNOWN.
The remaining discriminator is an actual failing same-ID pair (ALIVE then refusal,
or already ABSENT); explaining why additionally requires exact request-owner/
lifetime evidence. Existing frame or case timing cannot supply that binding.
No further dispatch, browser/test rerun, installation, handling/protected fixture/
policy/product/main/production change was performed or authorized by this evidence.
