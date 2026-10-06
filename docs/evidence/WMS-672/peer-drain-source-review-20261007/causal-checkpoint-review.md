# WMS-672: bounded independent causal checkpoint review

Reviewed checkpoint `185447983635437533cfe49e8418c3e451c76233`, actual Linux
run37539919041 attempt1, product `47817f76589701ea36ba1f8b30fca84b6a136208`.
**The evidence supports admission-budget saturation as the cause of these fifteen
native refusals, with the private return/configuration inferred from source.**
This is sufficient evidence to define a separate mechanism regression contract;
it does not approve a fix, effectiveness, reference migration or release. C5 fails.

The independent reviewer verified all 55 manifest file sizes/SHA256 and the
decompressed original HTML hashes. In a disposable, automatically removed directory,
the saved offline analyzer was rerun against immutable Git blobs. All four resulting
JSON files—key ledger, budget ledger, denied keys and summary—are byte-identical to
the committed outputs. This executes accounting only, not product/browser/tests.
All six exact Chrome141.0.7390.37 primary source files were separately fetched from
the recorded upstream URLs and their decoded hashes matched the identities file.

The trace records no data loss, all four intended clock markers, a nonempty clock
offset intersection of width2ms, and maximum buffer use30.3076%. All555 native
starts match555 queue requests by content identity/order; independently checked
queue/native epoch differences range −0.197 to +0.605ms. Counts split299 first
attempt and256 corrected retry. All540 budget additions have matching removals
in one target renderer PID3897, with no unknown initial allocation, duplicate
identity or residual entry. The fifteen denied requests are retry labels242–256.

Each denied request has a positive836×356 target and the exact full key of a
previous successful low-level decode in the first attempt. At each request,
225 reservations account for267854400 bytes; none of the fifteen creates an
AddBudgetForImage event or enters a keyed DecodeImageIfNecessary worker. Thus the
recorded rejection happens before the PNG decoder is entered. Asset corruption
is not an explanation for these particular second-attempt failures. This does
not classify every EncodingError in other runs.

The [exact cache source](https://chromium.googlesource.com/chromium/src/+/refs/tags/141.0.7390.37/cc/tiles/software_image_decode_cache.cc)
checks available reservation bytes before budgeting an unbudgeted key, including
already cached images. The [controller](https://chromium.googlesource.com/chromium/src/+/refs/tags/141.0.7390.37/cc/tiles/image_controller.cc)
maps the lazy-image no-reference outcome to failure. Prior identical positive
keys and complete absence of reservations/workers, at the numerical saturation
boundary, strongly support this path. The private result enum is not emitted by
the trace, so the branch/reason remains source-backed causal inference.

The reservation size formula yields1190464 bytes per image. Exact desktop source
selects32/128/256MiB working sets and renderer settings use that selector. The
measured reservation usage exceeds128MiB and fits the256MiB configuration:
581056 bytes remain, less than one more reservation.256MiB is a source-derived
configuration inference, not an observed CDP maximum-limit field.

The initial explicit global dump returnedfalse and is not counted as a valid
snapshot. Ten actual cc/image_memory cache snapshots are present. They corroborate
growth and zero locks between phases, but their allocated-image locked_size is
not identical to the reservation ledger during active work: the last snapshot
shows209521664 locked bytes versus247616512 reservation bytes. Do not use those
snapshots as a direct measurement of the267854400 reservation peak or runtime
maximum. Complete target Add/Remove accounting supplies the peak calculation.

Timer evidence records the first sixteen retry reservations released251.953ms
after the first decode-finished event;225 available slots plus those sixteen
releases explain241 admitted requests before label242. The next release is
15.415ms after the first refusal using the clock-offset midpoint (about±1ms
calibration uncertainty). Subsequent recorded groups release101+11+113 entries,
leaving zero. The [tracker source](https://chromium.googlesource.com/chromium/src/+/refs/tags/141.0.7390.37/cc/tiles/decoded_image_tracker.cc)
re-enqueues its timer rather than scheduling each image's individual expiry.
This establishes the measured release timing; it does not justify a hardcoded
250ms sleep, hidden decode retry, browser-private limit or loaded-image fallback.

Both failed iframe removals record zero native pending peers and zero transfers.
Peer draining therefore works in this trace while corrected retry still fails:
pending-promise teardown alone is insufficient to explain or fix admission refusal.
The next contract must preserve original PNG/label geometry, genuine native-error
abort, complete readiness before one transfer/all marks, explicit recovery and
existing frozen cases. Its implementation and actual C5 verification remain
separate stages. No dispatch, package build, main/config/product edit occurred.
