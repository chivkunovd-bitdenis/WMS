# WMS-672: debug-only native cache capture preparation

Bounded observational correction after37536969311/evidence005b379ac4a941950a0eb2e4e0f2cbcfe4bee0a3. The actual prior trace has36608 LocalFrameView::ScheduleAnimation events in broad cc, still overflows32MiB and captures only first150 prefix. It provides no later failure cause.

Only substantive adapter delta from tested2388 is removing broad cc from includedCategories. Keep disabled-by-default-cc.debug, disabled-by-default-memory-infra,__metadata; exact32MiB recordUntilFull, light250ms periodic dumps, gzip32MiB/128MiB parser caps, the same six boundary CDP clock samples, native Promise forwarding, code/window/waits/errors and immutable2+7/C5/source478. Rename isolated diagnostic job/artifact directory. No product/tests/source generator or release CI edits.

Actual previous raw trace confirms these relevant events all use cc.debug: SoftwareImageDecodeCache GetTaskForImageAndRefInternal, AddBudgetForImage, RemoveBudgetForImage, UnrefImage, DecodeImageIfNecessary, SoftwareImageDecodeCacheUtils::DoDecodeImage - decode, and LayerTreeHostImpl/DecodedImageTracker QueueImageDecode. Thus removal of broad animation channel preserves admission/release, cache target keys and actual low-level decoder entry. Coarse worker mode events in broad cc are omitted; the measured backend is already software, and low-level DoDecodeImage entry remains. Preserve the raw category proof in005b/trace-observation.json.

The no-loss/full clock/native-failure coverage requirement remains. Use actual key/byte/admission/release accounting, not just225/226 arithmetic or timer-source inference. A second capture limit or non-reproduction remains honest inconclusive; this preparation grants no product tuning or native bypass. Integrator alone may dispatch one corrected run after exact scope/ref verification and parent direction.

Local syntax/shell/diff checks and protected-source hashes are recorded. No Mac/browser/fullCI run. All five protected files equal47817f76589701ea36ba1f8b30fca84b6a136208.
