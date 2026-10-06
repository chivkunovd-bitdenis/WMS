# WMS-672: bounded Chrome141 cache measurement preparation

This isolated workflow_dispatch branch is a diagnostic, not release CI. Product source and the frozen C5, native-error7, peer-drain2 contracts are byte-identical to product47817f76589701ea36ba1f8b30fca84b6a136208. It runs the two unchanged Node contracts then only unchanged C5 with its original assertions and420s wrapper; no full CI, external API, print hardware or product workaround. Dispatch belongs to the release integrator after exact ref/source verification.

## Source-grounded measurement

Exact Chrome141.0.7390.37 primary-source URLs and decoded SHA256 are recorded in primary-source-identities.json. SoftwareImageDecodeCache GetTaskForImageAndRefInternal emits a cc.debug event with key before checking available locked memory. AddBudgetForImage/RemoveBudgetForImage/UnrefImage expose reservation/release events; DecodeImageInTask exposes an actual worker task with the same key. The cache key includes frame_key, target_size and color parameters. ImageController CompleteTaskForRequest maps a lazy-generated request with need_unref=false to FAILURE: no decode was attempted (empty target or admission refusal). The public DOM EncodingError itself does not distinguish these reasons.

DecodedImageTracker holds successful image locks until used in a draw or a scheduled250ms timeout. Existing observed same-frame time from first completed cohort to refusal469ms disproves the simple statement that250ms had not elapsed; it does not prove its task actually ran. The trace records actual Unref/RemoveBudget rather than assuming timer expiry.

Software and GPU cache providers implement numeric memory dumps, but exact141 memory_infra_background_allowlist EXCLUDES both providers. Background-only collection would be inadequate. Use light dumps every250ms, whose per-image allocator entries contain locked_size; software also names budgeted/at_raster entries. GPU emits decode/upload/capacity events and per-entry locked sizes. SystemInfo.getInfo identifies actual browser GPU/backend configuration. A software256MiB limit remains a hypothesis:836*356*4=1190464;225 images fit256MiB,226 exceed it by609408. Actual traced target sizes, color storage and cache reuse must account for this mismatch.

## Bounded observation

CDP Tracing.start uses exact141-supported fields: recordUntilFull,32MiB trace buffer, ReturnAsStream/json/gzip, cc + disabled-by-default-cc.debug + disabled-by-default-memory-infra + blink.user_timing. It disables JS sampling/systrace, requests no GC, screenshots or network trace. Trace completion is bounded15s; compressed stream32MiB; offline decompression128MiB. Per-native-call performance marks name fixture/frame/index and permit correlation with renderer trace clocks. Existing native Promise forwarding, errors, active-cohort drain, timing, source, assertions and timeout stay unchanged. No CDP calls/waits are inserted in the decode wrapper. Existing observer now additionally records wallTime, visibility and iframe style attributes without a layout query.

Categories are inventoried before and after: renderer categories can register after launch, so an initial missing registration does not justify concluding unavailable. Actual emitted cache events/dumps determine usefulness. Buffer usage and dataLossOccurred are persisted. Offline parser retains raw cache events, numeric memory snapshots and user timing marks; it never declares a product result or cause.

## Discriminating criteria

If failure reproduces, correlate the first native-reject marker with valid target-size GetTask keys, reservations minus releases and nearby cc/image_memory snapshots in the same renderer. A never-admitted new key (no AddBudget or worker task in a complete trace), at a measured saturated working set, followed by native refusal supports admission failure; verify no other early-return condition before attributing a budget. Actual worker decode with ample/free budget contradicts that account. Compare with the successful first300 preparation and subsequent cleanup/release events, plus peer-pending0 evidence. The source does not emit the private result enum directly, so do not label an inferred reason as a recorded DecodeResult.

If C5 passes under observation, categories/dumps are absent, traces overflow, or key-to-cache identity is ambiguous, report the boundary honestly: tracing can perturb task timing and an inconclusive capture is not permission for another numeric tune or native-error fallback. A measured diagnostic pass is not full release acceptance.

## Local preparation verification

prepared-validation.txt records syntax/shell/diff checks and a synthetic parser control proving cache/memory/marker extraction. These checks do not execute C5 on macOS or claim Linux success. protected-source-hashes.json proves the five immutable sources equal478. No source fix is included.
