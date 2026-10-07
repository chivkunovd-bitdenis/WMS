# WMS-672: actual Linux141 cache trace capture

Run37535645145 attempt1 tested diagnostic head d82ba1c435b5a5e2101c50bfee3534679c79673d, product bytes47817f76589701ea36ba1f8b30fca84b6a136208. Ubuntu24.04/Linuxx64, Node24.21.0, Playwright1.56.1 and native Chrome141.0.7390.37. Integrator dispatched once; no additional run, product edits, external writes or physical print. Source-before/after hashes agree for all five protected product/contracts files. Setup/upload succeeded; selected unchanged C5 failed95.7545s at transfer wait, frozen2peer +7native cases PASS0skip.

## Actual product behavior

Firstfixture: injected150 reason/noearlytransfer held; corrected retry prepared300, rendered tape and all300marks successfully. Native459fulfilled,0rejected and0pending (159 from failed active cohort +300retry). Render-page300 native successes. Secondfixture: injected299 exact reason/noearlytransfer held, then explicit corrected retry refused on six valid PNGs235..240 (cumulative535..540 after first300 preparation). Native533fulfilled/6rejected,0pending; print transfer0, POST0 and iframe0. Original first native EncodingError preserved to the screen. All cleanup records have removedFramePending0 and totalPending0. Offline CRC/pixel decode and CODE128 validation of all six rejected PNGs pass836x356 with the exact labels235..240. This differs from the prior run's refusal during first299 preparation, but still leaves the same frozen C5 red.

## Measurement limit: cause remains unproven

The trace returned dataLossOccurred=true, maximum buffer usage0.9966085553. It contains86644events;66487 carry blink.user_timing, largely React development component/insertion marks. These exhaust the32MiB recordUntilFull buffer before useful C5 native image events. Native fixture/frame/index markers0; cc/image_memory snapshots0. Only22 SoftwareImageDecodeCache GetTask events are retained, all target16x16 from early UI work. The trace therefore cannot establish missing reservation/worker events at the real native refusal, cannot measure its locked working set, and cannot prove a budget cause.

The actual environment is independently identified as software rasterization/compositing by SystemInfo.featureStatus and retained SoftwareImageDecodeCache events. Light dump callbacks to cc::SoftwareImageDecodeCache do occur (13retained), confirming the corrected provider level is callable; no image allocation entries are available during the captured early period. Software backend identity does not prove cache exhaustion.

## Next bounded measurement proposal

Remove proven noisy blink.user_timing category and observational performance marks. Retain cc/cc.debug/light250ms memory tracing with the same32MiB bound; correlate existing performance.timeOrigin+performance.now epoch fields with a few CDP Tracing.recordClockSyncMarker samples outside the native decode call. Do not change native forwarding, code/window, assertions, errors, readiness or timeouts. Prepare and verify exact published ref before the integrator alone considers another dispatch. This checkpoint grants no dispatch and supplies no product fix.

Raw HTML is stored losslessly as gzip to preserve original bytes and avoid altering snapshot whitespace; manifest entries include original artifact path and original SHA256. All other raw files retain their artifact bytes. Raw artifact, trace configuration/completion/usage, engine summaries, environment, TAP, failure log, six PNGs, requests, source hashes and API identity metadata are all preserved below raw/. manifest.json hashes every raw member plus trace-observation.json; all manifest members are included in this evidence commit. No truncated capture is represented as causal proof or release acceptance.
