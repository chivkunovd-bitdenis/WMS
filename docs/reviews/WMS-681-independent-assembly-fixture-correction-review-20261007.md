# WMS-681: independent integration frozen correction · 2026-10-07

**PASS. Actual reviewer model: gpt-6.1-sol; reasoning effort: high.** Scope is this exact single-file integration correction, not a repeat of WMS-658/WMS-680 or a product/release acceptance. No Astra identity is claimed.

origin/etalon was fetched at `4b298efc95be7b4b6b7fe5665be9f3671f1fe747`. Its AGENTS blob `510ce8febd402f9a78a5f1fddd964d99283afaff`, owner-cases `19a12f266ef38e697e1b30cf2f3da3d589e8cce2` and failure-cases `48263ba41e8fdb67c744864f7ec52a26b768598b` match the fully read rules/libraries retained by this same reviewer.

## Exact immutable binding

- Source/test correction: `879588d0ad7fe5fe579f16dcc4726c31f03fdb1d`.
- Actual source parent: `1eb2c30726c501a41b661a1b144864c94491a2c5`.
- Sole changed file: `frontend/src/screens/v2/FfFbsSupplyWorkspace.assembly.dom.test.tsx`.
- Branch-parent before blob: `58e64cc04d11be4fd7ad25b5fcb93bfb254d99f3`; SHA-256 `ac1a37b7a4b2e2e79c5d1f99c150e8009d74b56466dd2b388325a40ddacda153`.
- After blob: `12358c8953c842819db9a1b277ce51cbd83b9915`; SHA-256 `74b89dd7cf84ba6a335b9266dcab7c31f52f77f9b4f645800ba8ad8ff97d252e`.
- Modern integration base blob: `a38ce89640e8868b5a10baa705b93dfe22e07225`; SHA-256 `9f0cea521152d34f81c307a8efd0ad45e1899832af116056965de6d9d36fe956`.
- Tested merged product: `95b4728eb58793e3a58cb89b057e53ba8b9228a5`; frontend tree `bbe8b9795a0800810d1ae56cb0704cb5d8ccd625`.
- Analyst clarification: `c7f755ce3a6c0ebce9a37567ae423aaa54565f51`, `docs/reviews/WMS-681-integration-qr-expectation-clarification.md`, blob `6aa0a1c46b086c523cfa6351d111a8e6d60e36ce`.
- Separately committed testwriter evidence: `c52828be87526948c0800fd3da0ce63bea382116`, `docs/reviews/WMS-681-assembly-fixture-correction-20261007/`.

There are two distinct exact comparisons: branch-parent `58e64cc04d11be4fd7ad25b5fcb93bfb254d99f3` → `12358c8953c842819db9a1b277ce51cbd83b9915`, and modern integration `a38ce89640e8868b5a10baa705b93dfe22e07225` → `12358c8953c842819db9a1b277ce51cbd83b9915`. Approval is limited to this path/pair and recorded clarification; it grants no generic assertion rewrite. The moderator must bind this report's eventual commit/blob to those exact immutable inputs and preserve source/test and proof ancestry in integration. This report itself does not merge source branches or apply tests.

## Semantic closure and guard preservation

Independent TypeScript parsing of Git blobs confirms all 20 modern suite-qualified cases retained: 19 bodies byte-identical, only BASE-10 changed. That case replaces exactly the obsolete explicit-click zero-retry and unconditional uncreated-cargo text authorized by R4/R5, C5/C9. It now requires one POST to the same physical box's retry endpoint and the actual timeout reason. Its no-preview guard remains identical; added guards preserve the entire box snapshot, prohibit box creation and prohibit any QR asset fetch. The physical FBS barcode remains present to expose fallback. R1's no-local-FBS-QR requirement remains mandatory. The request retains the original box identity and introduces no replacement journal key; this DOM fixture does not independently exercise the backend journal.

All 11 approved incoming QR cases retain their 47 assertion statements token-for-token, including recovered-asset preview, five-QR loop, partial failure, durable A1/readback, zero-ready retry, delayed A→B and Ozon. Modern prior assertions increase 65→68. Scan/create-box/tab zero-retry guards, current Frame/stage/scanner, KIZ validate/commit routes, delayed-scan box selection and shared scanner startup remain intact. No skip/exclusive cases or component mocks were added. Stable authHeaders fixes fixture controller identity; it does not replace the real packing controller.

The Ozon GET fixture formerly returned synthetic HTTP 200/null. Reading exact API/service sources establishes successful dictionary results through get_exemplar_documents/document_view; failures produce HTTP errors. The real OzonDocumentsAbsence, identical in the tested product and clarification snapshot, initializes documents to {} and remains mounted. The correction supplies a valid version/state/products snapshot only at its GET boundary. It neither removes that component nor certifies malformed-response tolerance or real Ozon operations.

## Verification limits

Committed pre-correction receipt records 29 PASS/2 FAIL: obsolete BASE-10 expectation and fixture-induced Ozon null/state crash. Final raw log and Vitest JSON record **31 PASS, 0 FAIL, 0 pending/skipped**. Executed blob `9cb7bbc43708a170b426e7ca56c24f4a43539e3a` differs from the committed after blob by exactly two comment lines; independently verified by exact replacement. Eight relevant product-manifest blobs match Git. The testwriter's 689 archive-file matches remain attributed evidence, not this reviewer's filesystem observation. Interrupted attempts are not counted as passing.

Own verification was read-only Git/AST/receipt/API inspection; no runtime suite rerun. This closes the legitimacy/preservation review for the correction, not live WB/Ozon, physical printing, full CI or deployment. Only this report is committed by this reviewer; concurrent tests/product/requirements/checker files are untouched.
