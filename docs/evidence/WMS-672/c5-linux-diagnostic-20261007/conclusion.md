# Concrete result of the one authorized Linux run

Run [37527056184](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37527056184),
attempt1, job112486609103, workflow_dispatch of exact published diagnostic SHA
b44ef10777f8d63555229d575558c6c9a5f3affd. Setup and artifact upload succeeded;
C5 itself failed. No retry/second dispatch/fullCI/product edit was performed.

The observed environment is Ubuntu24.04.5/Linuxx64, Node24.21.0, Chromium
141.0.7390.37 from Playwright1.56.1, matching the original failed CI versions.
Only one selected test executed, zero skipped/cancelled, FAIL in44.19s.
Protected source hashes before/after match; source byte checks against failed
merge2d1707cacdb9bbd2e92eee75115c9749ac969fcc passed. The diagnostic Vite transform
only added an observation before the original screen catch expression.

The injected failure150 was reached and handled correctly: error identity1,
name Error, exact message `WMS672 decode failed at 150`, parentError=true;
first attempt started160 decodes and had128 completed when iframe was removed.
The existing exact-alert/no-early-transfer assertions passed and C5 cleared the
fault and explicitly retried. Thus this is neither adapter/setup failure nor
failure to inject150.

The corrected retry then failed on the browser's original native decode, before
transfer, with identity2: EncodingError, `The source image cannot be decoded.`
Its cumulative invocation index387 is label227 in the retry's300-label tape.
Offline comparison finds that exact data URL at rank227 in both removed tapes.
The native error had complete=true, naturalWidth836, naturalHeight356. Captured
PNG is7675bytes, passes PNG CRC/inflation/pixel decode, and independent CODE128
raster decoding returns `INB-000000000227`. A malformed source barcode PNG is
therefore contradicted by this captured payload.

The very same error identity2 moved native iframe→promise catch→screen catch.
It was an Error in the iframe realm and failed the parent's instanceof Error.
The unchanged screen expression replaced its available message with the generic
Russian alert. C5 then timed out after30000ms at the existing transfer wait,
line317; transfer did not occur. At closure: started416, decoded354, frames50,
zero transfers, zero POST/nonGET requests (147GET), zero remaining iframes.
The299 iteration was never reached in this diagnostic. This differs from the
original common CI's exact299-alert failure and does not determine its index.

## Cause boundary and proposed minimal next change

Two product facts are confirmed in the actual required environment: a valid,
already loaded barcode PNG can receive native decode refusal during the bulk
preparation, and screen error normalization loses that iframe exception's
message. This is not evidence for increasing assertion timeouts, ignoring decode
errors, bypassing native readiness, or changing the frozen fault expectation.

An engine-cache-budget explanation is strongly consistent, but is an inference,
not captured Chromium tracing. ExactChrome141 source routes decode results to
EncodingError; its image controller can return failure when a lazy-image decode
cannot obtain its memory reservation. The decode tracker retains completed image
locks until draw or a250ms timeout. One836×356RGBA image uses1190464bytes;
256MiB holds about225.49 of these, near the observed retry failure227. The
existing32-image windows can run seven windows before that retention interval.
This source comparison does not identify the actual runner cache/backend/budget
or exclude every engine condition; no OOM/engine trace was captured.

A narrow proposed fix to validate separately is to reduce the native decode
window32→16 (preserve parallelism and allN successful native readiness before
transfer), plus preserve a nonempty message from iframe errors without a parent
instanceof requirement. This is a proposal, not implementation or a green C5
claim. Existing frozen C5 is already RED on this exact environment; an additional
frozen native-DOMException/message test and review must precede product code.
Then the unchanged150/299 retry contract must pass in Linux141. Merely showing
the native message cannot make this corrected retry succeed.

Primary source references (exact version, read-only):
[ImageLoader](https://chromium.googlesource.com/chromium/src/+/refs/tags/141.0.7390.37/third_party/blink/renderer/core/loader/image_loader.cc),
[ImageController](https://chromium.googlesource.com/chromium/src/+/refs/tags/141.0.7390.37/cc/tiles/image_controller.cc),
[DecodedImageTracker](https://chromium.googlesource.com/chromium/src/+/refs/tags/141.0.7390.37/cc/tiles/decoded_image_tracker.cc),
[GpuImageDecodeCache](https://chromium.googlesource.com/chromium/src/+/refs/tags/141.0.7390.37/cc/tiles/gpu_image_decode_cache.cc).

This diagnostic stops here. CandidatePR387/product/reference/policy/main,
production, operator sessions and real printers remain outside this work.
