# WMS-672 controlled pending-peer lifecycle observation

Command, before any peer-drain product change:
`node docs/evidence/WMS-672/peer-drain-diagnosis-20261007/probe.mjs`.
Actual product source is9e757a02cefa0cd1f7a95d272944e0b7c2b0660a (16-window,
message correction). The probe reads the frozen05a7 helper setup as a COPY,
extracts/transpiles the real current full screen function and utility, and only
changes the diagnostic platform boundary timing: one decode rejects independently
while its15 peers remain controlled on a gate. The frozen test file is never
written; no Chromium/browser/API/printer or product edit occurs.

Observed before peer release:16 starts,0ready,15pending, real operation finished,
busyfalse, iframe already disconnected, error retained, zero transfers/marks/saves.
After release:15 successful readiness callbacks finish after their source iframe
was removed. This directly reproduces unbalanced worker teardown in current
Promise.all error cleanup. It does NOT prove those callbacks correspond to actual
Chromium decoder state or prove this causes native EncodingError in Linux.

Read-only review correctly notes first150 cleanup also had15 uncompleted peers
but its corrected retry succeeded in Linux; that is a countercondition against
claiming early cleanup alone sufficiently explains the second299 failure.
Saved Linux observer has no native-fulfillment callback records. Parent authorized
bounded continuation: obtain an independent held-peer regression before changing
product, then preserve strict readiness and observe native pending/fulfillment at
actual failure/removal/retry during a coordinated Linux counterfactual. No further
numeric tuning, native-error bypass, source-generator change, or dispatch here.
