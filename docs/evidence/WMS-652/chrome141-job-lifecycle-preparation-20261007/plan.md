# WMS-652: one exact-ID lookup measurement, not another generic abort control

Read independent fe75db37e3918b93400485c0f5dce540a44c7f23 review. Its two actual first
workspace GET/protocolXHR refusals and four same-endpoint no-network-ID successes
remain strict; application fetch is not asserted to construct XMLHttpRequest or
explicitly abort. Original etalon cause remains UNKNOWN. Prior37552021494 already
proved ordinary networkID/Fetch explicit cancellation and is not repeated.

Exact official Chromium141.0.7390.37 tag resolves to
9f043f63b0e5b728c8d09f3e3ddfc1681a4bd58e. Downloaded exact native files and Git blob/
SHA256 identities are in native-source/manifest.json; no lkgr/blog source is used.

Verified source chain:
- fetch_handler.cc:282-291 delegates fulfill to ContinueInterceptedRequest;
  devtools_url_loader_interceptor.cc:768-776 calls FindJob.
- interceptor.h:236-249: missing jobs_[exactID] produces Invalid InterceptionId;
  AddJob/RemoveJob operate that exact map.
- interceptor.cc:700,829-849,1432-1437 and fetch_handler.cc:483-489:
  optional ResourceRequest.devtools_request_id becomes the optional networkId;
  its absence carries no cancellation reason. The constructor stores it const.
- interceptor.cc:851-852,1411-1412,1554-1564: receiver disconnect/completion can
  invoke Shutdown, erase currentID and delete the job. Redirect replaces an ID
  at1626-1631. These routes alone do not identify the historical actual cause.
- interceptor.cc:929-955: GetResponseBody first rejects missing Response-stage
  matching with the fixed HeadersReceived-pattern server error. It returns before
  BodyReader allocation, Resume, callbacks or loading. interceptor.cc:748-753
  routes that read through the SAME FindJob; fetch_handler.cc:390-404 delegates it.

A controller.abort after paused cannot retroactively change the constructor's
already-fixed optional renderer ID. A normal live instrumented helper control has
no source-backed distinct route to the missing-ID class; SetDevToolsIds in the
exact inspector_network_agent.cc:1429-1445 normally assigns an ID and separately
excludes internal initiators. This does not label these failures internal. Repeating
ordinary live-page abort would re-prove375520, not the actual missing-ID origin.
The native Fetch.requestPaused trace at1548 has only a pointer track, no requestID,
and141 Shutdown has no retirement trace. A generic trace/time/URL join would not
supply the required exact owner/disappearance binding.

Chosen single capture: original entire43, exact4c532 product/helper/fixtures/driver,
original600s command and strict assertions, same Ubuntu24.04/Node24.21.0/
Playwright1.56.1/Chrome141. On an observed paused GET/XHR, exact fake-origin
/api/operations/fbs-supplies/wb-a/workspace, with no networkId, send ONE read-only
Fetch.getResponseBody for that EXACT paused ID immediately before the original
callback processing. Do not await its reply, add a barrier/delay, alter a request,
add a signal/marker, or inspect response bodies. The existing Request-only pattern
is frozen and verified; the native source above guarantees the alive-state query
returns before body access. Keep compact original-context capture alongside it.

Use distinct negative auxiliary command IDs on the SAME native WebSocket so it is
the same FetchHandler/job map, without touching original next/pending/token/attempts.
Record exact auxiliary sends/replies and their ownership separately. Original
positive commands, their native errors and the errors.length assertions follow the
unchanged driver. No original error is retired, filtered or converted to success.

Discriminators: fixed HeadersReceived-pattern reply proves job existed at THAT
lookup; Invalid InterceptionId proves it was absent at THAT lookup. Pair each with
the original first fulfill by exact FetchID, not URL/time/case proximity. Alive
lookup followed by fulfill refusal bounds disappearance between native lookups;
absent lookup and fulfill refusal shows absence already by the first measurement.
Successful same-class fulfill remains the comparison, without a separate test run.
Neither outcome proves caller abort or navigation; unexpected/pending/overflow/
missing pairs remain UNKNOWN. Another43PASS remains nonreproduction. This probe
adds a small scheduling perturbation, so it cannot retrospectively prove old cause.

Prepare only in codex/wms652-chrome141-job-lifecycle-diagnostic. Only cheap synthetic observer controls, syntax and reverse-source proof are authorized
locally by the final preparation instruction. No actual browser/install/measurement/dispatch. Sole integrator dispatch follows independent exact-ref/
scope assessment. No application/fixture/policy/handling/migration/main/prod change.
