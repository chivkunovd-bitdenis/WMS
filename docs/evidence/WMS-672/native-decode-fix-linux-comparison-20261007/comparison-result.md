# WMS-672 comparison:16-window does not close C5

One authorized coordinator dispatch:
[37529471517](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37529471517),
attempt1, head68207fee941e7682adbc1c0ac31f366aeeff044c, job112494847886.
Exact product9e757a02cefa0cd1f7a95d272944e0b7c2b0660a; original/new test files
and product bytes checked against it, before/after source hashes identical.
Environment Ubuntu24.04.5/Linuxx64, Node24.21.0, Chrome141.0.7390.37 from
Playwright1.56.1. Original assertions30000ms and outer420s unchanged.

The separate frozen7-case native boundary contract PASS7/0FAIL/0skip in3.57s.
Real browser C5 FAIL1/0PASS/0skip in86.75s. Setup/upload succeeded.
This is an actual transfer-wait assertion failure, not runner/import failure.

Fixture1: injected150 reason reached screen exactly. The explicitly corrected
300-label retry succeeded: one captured transfer, ordered tape/renderTape and
all300 marks completed;300POST of448 total requests. No native reject recorded.
At close global counters460started/444decoded (the first failed window had
160started/144decoded), one retained iframe; its print source remained available.

Fixture2: injected299 also reached screen exactly (first300started/288decoded).
The corrected retry then received native EncodingError at cumulative invocation
531, i.e. retry label231. Same identity2 propagated native→promise→screen.
Parent Error identity is false, but corrected screen preserves the exact native
message `The source image cannot be decoded.`. Browser had complete=true and
natural dimensions836×356. The captured7641-byte PNG passes CRC/inflation/pixel
decode; independent raster CODE128 decode returns `INB-000000000231`. Its exact
source occurs at rank231 in both captured removed tapes.

At failure close fixture2:540started/518decoded, zero transfer/iframe, all147
requests GET. No early marks or print occurred. C5 fails at original line317
transfer wait after30000ms; it was not weakened or re-run.16 is insufficient to
claim reliable corrected retry or release readiness. Message correction is
confirmed, bulk preparation remains a blocker. No deeper engine cause proven.

The new trace also records removal after first299 failure when only288 of300
started readiness workers had completed (one injected reject plus11 remaining
workers). Native-start events exist for those11. This justifies examining how
first Promise.all rejection tears down the iframe before peers settle. Current
observer lacks native-fulfillment/pending lifecycle records, so whether that
specific cleanup causes the later refusal is not yet proven. Parent authorized
bounded causal continuation; no further numeric tuning or dispatch has occurred.

Raw artifact, exact run metadata/log/TAP/requests/native identity/image/source
hashes are saved here. Manifest includes only members newly added in the evidence
commit, so evidence-only cherry-pick does not depend on diagnostic preparation
files/workflow override. `fixed-source-hashes.json` repeats the tested source
snapshot as a standalone evidence member. Diagnostic code stays outside release.
