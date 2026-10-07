# WMS-672: actual corrected clock/cache capture

Run37536969311 attempt1, diagnostic2388d03fe54148a3e1c3b0f87300d4ecb2e752f5, unchanged product47817f76589701ea36ba1f8b30fca84b6a136208. Ubuntu24.04/Linuxx64, Node24.21.0, Playwright1.56.1/Chrome141.0.7390.37. Integrator alone dispatched once. Setup/upload PASS; frozen2peer+7native PASS0skip; unchanged C5 FAIL on corrected retry transfer wait. Five source-before/after hashes agree. No product edits, external/production writes or physical print.

First150 refusal then corrected300 preparation/renderTape/all300marks PASS (459native fulfilled/0reject). Second299 injection matched its exact known error and zeroearlyexternal effects, then explicit corrected retry refused on fifteen valid PNGs242..256 (global542..556):540native fulfilled/15reject, pending0, iframe0, transfer0 and POST0. All removed-frame pending counters0. Every rejected PNG passes CRC/pixel decode and offline CODE128 with exact corresponding label242..256,836x356. Original first error preserves its identity/reason to the screen. C5 remains red.

## Limited trace and bounded useful prefix

Blink user timing flood removed successfully. Trace88108events/dataLossOccurred=true/maxUsage0.9966085553, now dominated by36608 LocalFrameView::ScheduleAnimation entries from broad cc. Only2of6 clock-sync markers and4image allocator snapshots retained. Therefore later real refusal phase is absent and cannot prove cache saturation or missing worker admission. Full clock/failure coverage prerequisite remains unmet.

The retained first150 prefix nevertheless contains159unique AddBudget and159RemoveBudget keys, all target836x356 in one renderer. Exact141 software CacheKey.locked_bytes formula is4*target_width*height:1190464bytes each. Peak158entries188093312bytes, no duplicateadd/unknownremove. First Unref occurs250.098ms after first DecodedImageTracker::ImageDecodeFinished. Release groups are1near250ms,96near500ms,62near750ms after initial decoding. Approximate clock-sync epoch correlation (Date.now bounds expanded1ms) places iframe removal with0nativepending while158cacheentries remain budgeted; all cache entries release roughly375msafter removal and corrected retry starts4.2slater, so those old locks had already cleared before that retry.

Exact source EnqueueTimeout requeues250ms from timer execution, not the next per-image expiry. These prefix facts support a bounded mechanism hypothesis: some images can remain locked near500ms even when their individual age exceeds250ms.225slots+oneearlierrelease could account for226success, but that inference about the later refusal is NOT established here. Need complete failure-phase keys/admission/livebudget/release before a product fix. first-phase-accounting.json preserves every key/timestamp/derived total and clock bounds, rather than rounding arithmetic into a verdict.

## Concrete observational correction

Actual retained event categories show all essential Queue/GetTask/AddBudget/RemoveBudget/Unref/DecodeImageIfNecessary AND SoftwareImageDecodeCacheUtils::DoDecodeImage - decode are disabled-by-default-cc.debug. Therefore omit broad cc category to remove the proven ScheduleAnimation flood; keep debug/memory/metadata,32MiB/light250ms, same clocks/native forwarding/source/tests. This is telemetry repair only; no numeric window tuning or native error fallback. Publish exact prepared ref before integrator scope check/dispatch. Prefix accounting does not close C5.

All raw artifact/trace/counts/clock receipts, environment/TAP/API identities/source hashes/PNG validation/requests are preserved. HTML snapshots are losslessly gzip-compressed with original artifact paths/hashes in manifest. Other raw bytes are unchanged. All manifest members included in evidence commit; no capture loss concealed.
