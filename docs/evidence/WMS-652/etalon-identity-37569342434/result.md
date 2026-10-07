# WMS-652: no reproduced native refusal; historical cause remains unknown

The sole run37569342434 attempt1 completed SUCCESS on exact diagnostic
`a6bbb5863f9365a45eb6bc11d510a5455b555229` and its isolated ref. Actual Ubuntu24.04.5/
Linuxx64, Node24.21.0, Playwright1.56.1 and Chromium141.0.7390.37 are confirmed.
The unchanged entire43 business cases executed in their frozen order:43PASS,
strict original command exit0, all2546 original source bindings/hashes preserved
before/after. Generated copies match their declared SHA256 and reverse byte proof.
Raw checkpoint57ce86ca3 preserves all17 artifact members and complete job/API records;
every original member is losslessly recoverable with original-byte SHA256.

There are53957 added observations, zero drops/observer errors/pending commands,
11663 native sends and11663 exact unique matching native replies, all successful.
Original transport separately contains43722 records and no pending commands.
There are no native errors or timeouts and no canceled:true Network.loadingFailed
observations. The six loadingFailed records are canceled:false/
net::ERR_CONNECTION_CLOSED/typeFetch; the unchanged source deliberately loses native
print acknowledgments through Fetch.failRequest(ConnectionClosed). These records
are not evidence of navigation cancellation or Invalid InterceptionId.

All three paused events missing networkId are GET/resourceTypeXHR, not OPTIONS.
Their exact Fetch IDs each have one fulfillment and an empty successful native reply:

| Fetch ID | Native command | Synthetic URL path | Send→reply Node monotonic ms | Send/reply generation |
|---|---:|---|---:|---|
| interception-job-2438.0 | 2814 | /api/operations/packaging-tasks/task-wb-a | 0.590288 | 45/45 |
| interception-job-3852.0 | 4392 | /api/operations/packaging-tasks/task-wb-a | 1.192494 | 69/69 |
| interception-job-6155.0 | 6980 | /api/operations/fbs-supplies/wb-b/workspace | 4.088641 | 111/111 |

The cases are respectively qr;supply_ids=A,B, qr+reprint;supply_ids=A,B, and
lost-accepted-ack;supply_id=A. URLs have the synthetic127.0.0.1:16686 origin.
Their send/current-reply cases are unchanged and redirectedRequestId is absent;
no paused redirect IDs occur anywhere in this capture. Full exact metadata is
in analysis.json. Without networkId, nearby same-URL Network.requestWillBeSent
records, their script initiator, frame/loader or case proximity do not establish
an identity mapping. Consequently no Network terminal or initiator can be
attributed to these three paused IDs merely by URL/time coincidence.

The new reply fields retain distinct contexts in47 successful native replies:
46 Runtime.evaluate and one Fetch.fulfillRequest. The latter is command7244,
FetchIDinterception-job-6387.0/network3333.6507, GET/XHR workspacewb-a: send generation112,
reply currentGeneration113, same lost-accepted-ack;supply_ids=A case, native success{},
0.507496ms observed send→reply. This is direct success across a generation boundary;
the boundary alone supplies no cancellation or refusal classification. All intervals
above use the observer's single Node monotonic clock, not Chrome-internal durations.

No source-backed handling correction follows from this PASS. It does not recover
historical run37567017373's missing URL/method/resourceType for commands2730/7689
or map their missing Network IDs. The precise remaining discriminator is the
**failing FetchID's own origin fields and same-ID terminal/invalidation evidence**
at the native refusal, including send/current-reply generation and case. Successful
GET/XHR examples cannot retroactively identify those failing requests or explain
why Chrome rejected them. Missing networkId and navigation proximity alone remain
insufficient. No random retry or blanket-ignore rule is proposed.

Analysis is read-only (`analyze.py`); no dispatch/retry/browser execution, product,
fixture, test, CI, handler, migration or policy change was made during collection.
Original staging/production release blocks remain. Any later behavior change needs
an independent frozen meaningful RED contract; a protected-fixture change additionally
requires separately reviewed policy migration, without self-updated hashes or an
old bootstrap waiver. The preserved evidence is ready for the integrator; this is
not release acceptance or a deployment claim.
