# WMS-441: native cargo recovery evidence

The Android recovery path was exercised against an isolated local fixture through a scoped response-loss proxy. The first cargo placement reached the server and committed, while the proxy dropped its response. The device kept the operator-visible pending state; a scan of the second cell was refused before it could form another transfer.

After force-stop and PIN re-entry, the normal sorting queue omitted the completed request. The repaired application nevertheless opened that existing request from its durable receipt for the same server and employee and presented the existing `Повторить` action. It did not retry on startup. A retry with the proxy gate still closed remained pending. After the gate was released, that same UUID/body reconciled successfully, the queue was empty, and a further process restart did not reopen a recovery request.

The API/DB read recorded one transfer group with exactly one outgoing and one incoming movement, no cargo remainder, two units in A, zero in B, and document status `done`. The JSON artifact contains the non-secret operation UUID and compact counts. No authentication material is stored here.

Validation used the targeted sorting unit tests, `lintDebug`, and `assembleDebug`; all passed on the final source. The nested Android source commits are local-only `3f37d8c4339308dc8879a234be03aa78d9cd9656` and `258989613ffd4b20d93b05be5f972b05abc8a8fb`.
