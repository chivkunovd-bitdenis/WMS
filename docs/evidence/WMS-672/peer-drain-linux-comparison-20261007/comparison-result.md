# WMS-672: drain is correct, C5 remains blocked

One authorized coordinator dispatch
[37532767928](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37532767928),
attempt1, headcef4cffd5d6bd1b76e691c596b87c9ad719e7d4f, job112506034543,
exact product47817f76589701ea36ba1f8b30fca84b6a136208. Setup/upload PASS;
peer2 PASS, previous native7 PASS; actual unchanged browser C5 FAIL70.15s.
Ubuntu24.04.5/Linuxx64, Node24.21.0, Playwright1.56.1/Chrome141.0.7390.37.
Five protected source bytes/hash before/after identical; original30000ms assertion
and420s outer bounds untouched. No developer dispatch/repeat/fullCI performed.

Fixture1 completed first150 known failure and corrected300 retry, ordered
renderTape and300 marks. Cleanup after first150: native159 fulfilled,0rejected,
0total pending and0removed-frame pending; success callbacks completed before
frame removal. Corrected retry reached300 additional native successes/one
transfer; root totals459 fulfilled/0rejected/0pending. RenderTape separately
fulfilled300/0rejected/0pending. Source remained alive for captured transfer.

Fixture2 failed on its FIRST preparation, before injected299 or any corrected
retry. Native errors227..240 arrived as a14-error burst, all EncodingError with
`The source image cannot be decoded.`;226 native successful callbacks,240started.
All14 payloads are loaded complete836×356 PNGs and pass offline CRC/pixel decoding.
The first rejected7675-byte PNG independently decodes to CODE128
`INB-000000000227`. Source error identity1 reaches screen unchanged; parent
instanceofError=false, actual native message preserved. After failed cohort drains,
root pending0 and removedFramePending0; cleanup follows native completion.
Fixture2 has0POST/nonGET/transfer and zero iframe. C5 fails at line308 exact299
alert wait (30000ms), because actual failure227 occurs before artificial299.

Readiness drain is therefore proven operationally correct but is NOT sufficient
to fix the browser failure. It is not valid to keep attributing this failure to
old pending workers: failure now occurs before the fixture's known failure/retry,
and its cleanup contains no outstanding native callbacks. Remaining engine
cache/resource reason is still unproven; loaded valid PNG alone is not a reason
to ignore native error or claim prepared/printed success.

Same-frame clock analysis, never compare iframe vs parent performance origins:
fixture2 nativeFrameId3 first native-start1142.3ms, first rejection1652.3ms,
span510ms. First cohort completed1183.3ms,469ms before first rejection; all
14 rejections occur1652.3..1653.0ms. Thus a simple claim that decoding failed
because the batch had not yet run for250ms is contradicted by this trace. Source
DecodedImageTracker250ms/reference budget explanation needs actual engine evidence;
no further numerical window/wait tuning or native-failure fallback is warranted.
Fixture1 frame3 starts span509.1ms (159native), corrected frame5 starts span759.2ms
(300native), visible renderTape frame1 spans1245.9ms (300native). Full cohort
completion timestamps in same-frame-timing.json constrain any next hypothesis.

Raw run/artifact metadata, logs, all three TAP reports, native pending/fulfillment/
rejection/removal snapshots, all14 rejected rasters, requests and source hashes
are retained. Manifest includes ONLY newly added evidence members; evidence-only
cherry-pick needs no diagnostic workflow/preparation file. Fixed-source-hashes
is a standalone copy of tested snapshot. Product478/local receipts690 remain
published, but reliable bulk C5 and release readiness are not achieved here.
