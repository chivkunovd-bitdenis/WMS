# WMS-681: independent combined assembly contract correction

This is a testwriter correction, not a product change, product acceptance, independent review, CI result, or deployment. The user assigned only the assembly DOM test and honest correction evidence. Original branch/product HEAD is `1eb2c30726c501a41b661a1b144864c94491a2c5`; it was not advanced to integration. No other frozen tests, policies, checkers, requirements, or UI/product files were edited.

## Exact inputs and correction reason

- Current integration test blob: `a38ce89640e8868b5a10baa705b93dfe22e07225` (20 cases).
- Accepted WMS-681 incoming test blob at original HEAD: `58e64cc04d11be4fd7ad25b5fcb93bfb254d99f3` (29 cases, including 11 QR cases).
- Tested merged product: `95b4728eb58793e3a58cb89b057e53ba8b9228a5`, captured from the integration checkout after its temporary OURS resolution. This product includes accepted WMS-681 recovery and the current scanner. Its exact frontend tree and relevant product blobs are recorded in `snapshot.json` and `product-files.json`.

The analyst subsequently resolved the explicit QR contradiction in commit `c7f755ce3a6c0ebce9a37567ae423aaa54565f51`, document `docs/reviews/WMS-681-integration-qr-expectation-clarification.md`, blob `6aa0a1c46b086c523cfa6351d111a8e6d60e36ce`. The user then explicitly directed this same testwriter to apply only that supersession.

Both source blobs were read with `git show` directly, not reconstructed from an evolving staged integration file. The incoming harness uses `Frame(alwaysExpanded)` with active/start/finish lifecycle and `fbs-assembly-boxes-*` / `fbs-kiz-scan-*` selectors. The current harness uses `FbsPackingScanBar`, `PackingScanController`, `stage`, `packingHost`, `registerScanner`, and `onScanChange`. Its KIZ validate/commit HTTP fixture routes and unified scanner guards must remain. Copying incoming wholesale would remove those routes, assertions, and accepted WMS-666 behavior.

The combined file starts from the exact current blob, keeps all 20 case names and 19 test bodies byte for byte; the one explicit QR case changes only as authorized below, keeps its shared scanner startup helper byte for byte, and appends all 11 accepted incoming QR cases. Only those appended cases use the incoming recovery/error API fixture. Their QR assertions are unchanged; they enter the current boxes stage and use its corresponding selectors. Supply switching uses the current Frame's `supplyId` and `stage="boxes"`, rather than the legacy `alwaysExpanded` prop. Recovery, partial durable success plus HTTP error, delayed response, retry after network failure, and Ozon cases all remain.

The first full attempt stalled after reaching the later QR cases and was explicitly terminated (exit 143), rather than represented as passing. Its actual partial output remains in `initial-run-interrupted.log`. The fixture passed a fresh inline `authHeaders` function on every Frame render. The merged Ozon controller is memoized with `authHeaders` and registers itself into the parent Frame; a new function causes repeated controller creation and registration. A stable `useCallback` in the fixture fixes that identity loop without changing any product source or test expectation. The next complete execution used that corrected function identity and produced `29 passed, 2 failed, 0 pending` (exit 1), preserved in `pre-ozon-boundary-run.log` and `.json`. One failure was the then-unresolved BASE-10 semantic conflict. The other was a missing Ozon HTTP fixture response, as established below. The subsequent run was interrupted by user steering during collection; its partial output is retained in `steering-interrupted-run.log` and is not represented as complete.

## Preservation evidence

`verify-preservation.mjs` parses the exact blobs and combined file with the already installed TypeScript parser. `case-preservation.json` exports original/new suite-qualified case IDs, source blobs, assertion counts, and hashes. It proves:

- 20 prior cases with unchanged names: 19 byte-identical bodies and one explicitly authorized QR supersession. Original source had 65 assertion expression statements; current prior cases have 68 because three guards were added.
- 11 accepted WMS-681 QR cases with identical assertion tokens (47 assertion expression statements). The five-QR loop still repeats its original assertion five times; the count is a source statement count, not a count of runtime iterations.
- The current shared scanner startup helper and incoming bulk-click helper are byte-identical.
- 31 total cases; no skip, only, todo, skipIf, or runIf added.

The 18 other incoming cases overlap historical scanner/card behavior that was superseded by accepted current integration cases; they are not incoming QR additions. The current base versions, with their stronger modern protections, are retained. Both prior WMS-681 refusal case IDs and both accepted incoming refusal case IDs remain under distinct suites. BASE-10 now expects the exact single POST retry-qr request and the actual fixture timeout reason, instead of the superseded zero-retry and unconditional uncreated-cargo message. Its no-preview assertion is unchanged. Three added assertions require all physical-box fields/content to remain unchanged, no POST box creation, and no QR asset fetch; the fixture uses an explicit FBS physical barcode to expose a local-label fallback. The unchanged incoming C5/C9 success case separately requires the recovered asset URL fetch and real preview. All prior zero-retry scanner/create-box/tab protections remain byte-identical.

Preservation is a source-level proof. A failing test stops at its first failed assertion as Vitest normally does; this is not evidence that assertions after that failure executed. None were removed or skipped to manufacture a green result.

## Execution and isolation

The product was archived from the exact Git SHA into `.wms681-merged-product-fixture` inside the assigned worktree. All 689 archived frontend files other than the overridden assembly test matched their source Git blobs. The fixture's only override was the combined assembly test. `node_modules` was a symlink to the existing `/Users/deniscivkunov/Projects/WMS/frontend/node_modules`; no dependencies were installed. The assigned branch's product files were never copied over, staged, or committed.

The complete target command, from the isolated fixture's `frontend` directory, was:

```sh
node node_modules/vitest/vitest.mjs run src/screens/v2/FfFbsSupplyWorkspace.assembly.dom.test.tsx --maxWorkers=1 --minWorkers=1 --reporter=verbose --reporter=json --outputFile=../../docs/reviews/WMS-681-assembly-fixture-correction-20261007/merged-run.json > ../../docs/reviews/WMS-681-assembly-fixture-correction-20261007/merged-run.log 2>&1
```

`merged-run.log` and `merged-run.json` contain real complete execution results. No name filter, excluded tests, mocked scanner, or substituted product operation is used. The synthetic HTTP boundary is the accepted test fixture; this is not evidence of real WB or physical printing.

To verify preservation from the repository root:

```sh
node docs/reviews/WMS-681-assembly-fixture-correction-20261007/verify-preservation.mjs
```

## Ozon null crash: fixture versus product

The existing real 31-case receipt remains intact. At that stage the synthetic server's unmatched-route fallback returned HTTP 200 with JSON `null` for GET `/operations/fbs-orders/{id}/ozon-exemplar-documents`. The real `OzonDocumentsAbsence` component initializes `documents` as `{}`, not null. Its real GET then stores the fixture JSON under an order ID; `Object.values(documents).some(pending)` encounters that injected null. This was an actual execution crash, but not evidence of a product-generated null initial state.

Read-only inspection of exact analyst/integration commit `c7f755ce3a6c0ebce9a37567ae423aaa54565f51` establishes the endpoint contract: the API GET delegates to `_ozon_document_action`; the read branch calls `get_exemplar_documents`; both normal read/continuation paths return `document_view`, whose result is a dictionary containing `version`, `state`, `products`, `requirements_complete`, and other fields. Service errors become non-200 HTTP errors, not 200 null. Exact blobs and the relevant expressions are in `ozon-boundary-evidence.json`.

The minimal correction supplies a valid read-only document snapshot to that exact GET route: known non-required documents, `editable` state, product/exemplar data. The real Ozon component remains mounted and its GET executes. No component is mocked or skipped, and no QR, document mutation, or product operation is stubbed out. This establishes a fixture mismatch; it does not claim that the product tolerates malformed 200-null responses or certify behavior against a real Ozon account.

## Published test-only contract and final result

The first, pure test-only commit is `879588d0ad7fe5fe579f16dcc4726c31f03fdb1d`, parent `1eb2c30726c501a41b661a1b144864c94491a2c5`. Its sole changed path is `frontend/src/screens/v2/FfFbsSupplyWorkspace.assembly.dom.test.tsx`. Before blob is `58e64cc04d11be4fd7ad25b5fcb93bfb254d99f3`; after blob is `12358c8953c842819db9a1b277ce51cbd83b9915`. Evidence is intentionally committed separately after this test contract. The literal current-base comparison is `a38ce89640e8868b5a10baa705b93dfe22e07225` to the after blob, with only the exact analyst-authorized BASE-10 supersession; the branch-parent transform is the full before/after pair above.

Final complete command exited **0**: **31 passed, 0 failed, 0 pending/skipped**, `1 passed` test file, duration `93.27s` (collection `78.52s`, tests `14.39s`). All 31 suite-qualified results and their source IDs are exported in `published-test-contract.json`; raw output and Vitest JSON remain in `merged-run.log` and `.json`. No remaining product RED was reproduced by the corrected valid fixture. The previous 29-PASS/2-FAIL receipt is preserved, not rewritten.

After the complete run, two comment lines were clarified to state the authorized QR supersession accurately. Executed test blob was `9cb7bbc43708a170b426e7ca56c24f4a43539e3a`; committed blob is `12358c8953c842819db9a1b277ce51cbd83b9915`. `published-test-contract.json` records this explicitly. Exact string comparison and matching the previously captured executed Git blob proved that these comments were the only difference; executable code and expectations did not change. The green behavior was not rerun.

The private `.wms681-merged-product-fixture` was removed before the first commit and was never staged or committed. It used only 21 MiB. No original branch product files were overwritten, so no restoration of original product source was necessary. The test-only commit's product tree differs from its original parent only at the owned test path. Policies, checkers, other frozen tests, requirements and product/UI files were not included. Independent Sol review and checker bindings are assigned by the root moderator; they are not claimed here.
