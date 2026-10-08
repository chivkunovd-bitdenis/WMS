# C19 reopen readiness regression on product source S

This records the executed focused Vitest failure for the existing C19 composition contract. It is a readiness/loading RED, not a claim that the request was never sent and not the separate held-response draft.

- Product source: release candidate `e6542576933184f7f6632b88703f54df02e82835`.
- Workspace source blob at S and in this checkout: `100a9e51b436f13766eda63d46885f0fc393792b`.
- Test: `frontend/src/screens/v2/FfFbsSupplyWorkspace.wms662.c19.dom.test.tsx`.
- Executed command: `npx vitest run src/screens/v2/FfFbsSupplyWorkspace.wms662.c19.dom.test.tsx -t 'C19: partial → full remains order-specific' --maxWorkers=1 --minWorkers=1` from `frontend/`.
- Result: one focused test failed after 86.10 seconds while checking `partial: reopen` readiness.
- The test blob at execution is reconstructed from the immediately following, narrowly reviewed assertion/style edits: `8d5f6aaaa5833a1f320bcba7036ccef34470b111`. The frozen test blob in this commit is recorded by Git separately; the earlier blob is not presented as an independently archived stdout file.

At the failure, the second mount had issued a fresh `GET /api/operations/fbs-supplies/86b38d6f-f161-4acb-8ce1-da8d22d8796b/workspace` and received the fixture's HTTP 200 response. It also showed an indeterminate progress indicator and neither expected order row was rendered (`orderRows=[false,false]`); session storage still selected `packing`. The observed requests for that checkpoint included the fresh workspace GET and one `POST .../print-assets` for the still-missing stickers. That POST was answered by the test's synthetic 503 before any task or sticker mutation.

The frozen contract allows one exact missing-sticker preparation POST for every active `assembling` checkpoint, including reopen, and keeps historical `in_delivery` checkpoints GET-only. It still requires the fresh workspace response to be applied, the indeterminate loading state to clear, both order rows to appear, and the packing tab to remain selected. The executed failure occurred at the readiness check before those later assertions, so the failure is specifically the unapplied/unrendered workspace state; it does not condemn the allowed preparation POST.

No standalone held-response test was collected: its attempt stopped before Vitest collection with ENOSPC while Vite wrote a temporary file. That infrastructure failure is not a product test result and is not part of this RED.
