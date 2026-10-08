# WMS-666 P2: bounded independent review and functional acceptance

Reviewer: Astra, effort high. Product P2: `1a4b0d687392a91a2dbfde6fbcfe9013b9e09075`. Evidence publication: `f1177c5404f59e593f97ee17b5c6339c5306554d`, verified on remote `codex/wms666-packing-release-1008`. This review record is a separate R2 commit; it is not a product source or a deployment record.

**Product technical review and affected functional acceptance: ACCEPT. Release/deploy: NO-GO until mandatory exact release CI and trusted-source transition are completed.**

This is the delta after P1 `ffb524e2950cfb250993ad4db3b0f394ca55f735` and its acceptance R `a9fe9577ba25f5d18f6e96be59574fcf6b6fbbaa`. The previously accepted whole-process ledger remains applicable only with its original execution SHAs and layer boundaries. It is not relabelled as a fresh P2 execution.

## Product delta

The only runtime file changed since the accepted Workspace source is `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, blob `c4e8608e3e8c63e7e43fd5176b5e259201161cb9`. The change fences automatic preparation until the current opening's workspace has actually been applied. A grouped parent snapshot is recognised only after that exact snapshot becomes child state, rather than by matching supply ID alone. Closing/reopening invalidates freshness. The latest successful GET restores it. The automatic initializer also excludes already-delivered/tracking/history states.

This addresses the observed stale-open write-sequence race and automatic writes while viewing an `in_delivery` supply. It adds no task-presence gate to manual printing, no navigation lock and no new user action. Manual tape, row/global scan, FIFO Escape, late binding validation, native dispatch and backend code are unchanged by P2. Explicit historical print actions remain accessible; the fence applies to automatic preparation.

The source delta has been read and reviewed. No additional product defect was identified in this bounded scope. The two frozen history/reopen contracts precede the fix. `c19-history-green-transcript.md` binds the executed 2/2 focused DOM result to the exact Workspace and test blobs. Its provenance is correctly described as a compact transcript of tool output, not a saved full stdout file. Earlier missing sparse fixture/ENOSPC attempts are not counted as passes.

## Fresh affected-path execution

Published `release-1008/p2-prefix/ordinary-r3/` and `group-r2/` exercise the current product through real React, the isolated real API/PostgreSQL, a loopback WB receiver and the actual unchanged Direct Handler. Only the final printer submission is emulated; neither live WB nor physical paper is claimed.

Each case starts with missing accounting task and stickers. The first accounting start is deliberately refused with 503 before server mutation. Manual printing still allocates and binds a KIZ while the task is absent. Explicit retry succeeds with one actual accounting task; WB sticker requests are scoped to the actual supply/order identities. Two subsequent physical scan inputs complete with distinct current KIZ bindings and two packed orders. Each run produces exactly six accepted Handler jobs: one order QR plus two identical full-CIS copies per order. Final captured errors/blocked requests are empty, API is idle, and stock/reservations remain unchanged with zero inventory movements.

The reviewer reran the two bounded prefixes and independently checked the publication rather than inferring output from job counts:

- 23 source, runner, case-file, PNG-hash and final-state checks passed against `handler-receipt-joins.json` and the underlying files.
- All twelve per-run job keys match unique actual receiver journal entries with the exact PNG SHA-256; six belong to S and six to G. Saved Handler PNG bytes match the captured browser bytes.
- The browser runner's existing decoded values are preserved; this review does not claim an additional independent pixel decoder execution. Byte identity joins that captured decoding to the actual receiver output.
- Both raw traces contain accounting `503 → 200`, the taskless manual-print intermediate state and final packed state. Thus the accounting failure does not act as permission to block manual KIZ printing.

The prefixes deliberately stop before WB refusal verification and cargo-box flows. Those retain their earlier accepted, explicitly historical execution evidence; P2 does not change their handlers or backend semantics. The published first P2 attempts failed on wrong runner expectations (all WB requests counted as sticker requests, wrong second tape lookup) and ENOSPC. They are not presented as product failures or erased by the later passes.

## Remaining release boundary

The separate full critical browser run records 43/43 assertions on P2, including scan/reprint/remount recovery, but its captured exception arrays do not observe handled React console errors. The executor reported an unpersisted `FbsPrintPreviewDialog` error-boundary line. Source inspection found its synthetic `print-assets` fixture returns `items` rather than required `assets`, which is a concrete malformed fixture. No product fix is authorised on that basis. Executed-runner provenance, the narrow fixture correction and any bounded valid-preview check belong to S2 test/evidence review. This limitation is not converted into a claim of a globally clean console or physical printing.

The final release candidate must retain the frozen history/reopen and M26 guards, incorporate reviewed test/CI corrections, and pass the complete mandatory exact-SHA CI, including PostgreSQL/native-print/Windows and full backend shards. Earlier shard cancellations and failures remain failures. Updating the trusted main anchor is a separate reviewed action; main merge still requires the owner's explicit permission. No main merge or PROD deployment is claimed by this record.

R2 permits preparation of source-binding/release metadata for this accepted P2 without a circular requirement to run final CI before acceptance. It does not permit skipping that CI, weakening existing guards or declaring the release deployed.
