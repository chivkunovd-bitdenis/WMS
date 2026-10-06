# WMS-517 independent bounded review — changes required

Reviewed source: `5376d15cf9be7489fb1ac28a3c5723589724c05c`. The four helper/launcher/generator/command files exactly match implementation `2230d734ff052903dca5fe8c7f970f589efa9415`. Independent Astra review, explicit effort high. Read current checkout AGENTS, freshly fetched origin/etalon AGENTS, both complete owner/failure case libraries and current WMS-517 requirements/owner release clarification. Physical Mac availability/signature is not a software release gate.

## P1 — normal asynchronous filter refresh aborts Mac preparation

`scripts/ops/avpack-sold-kiz-filter.js:91–102` waits a fixed 400 ms after clearing filters, then immediately rejects a disabled native refresh button. The real `SellerKizWithdrawalScreen` sets `loading=true` on filter changes and disables this button until its registry request completes. A successful request taking 700 ms therefore aborts valid preparation with “Штатная кнопка обновления реестра недоступна.” This is ordinary loading, not an unavailable action or failed registry.

Reproduced against the actual React/MUI screen and actual helper, using synthetic GET-only API responses and a synthetic certificate adapter. Zero-delay control opens the certificate dialog; the same scenario with 700 ms registry latency fails with refreshDisabled=true and zero certificate enumeration. Icons alone are mocked as decoration. No real browser/operator/certificate/server mutation is involved. Source and complete output: `WMS-517-mac-review.test.tsx`, `WMS-517-mac-review.config.mts`, `WMS-517-mac-real-screen-review-20261006.txt`. Run from repository root with installed frontend dependencies: `node frontend/node_modules/vitest/vitest.mjs run --config docs/evidence/WMS-517-mac-review.config.mts` (dependencies must also resolve from the root for the evidence module).

Required correction: use bounded waiting for the native refresh button to become available after filter updates, preserving current session checks and exact fresh selection. Original test writer should freeze a regression before product correction. Reviewer did not edit product or frozen tests.

## Successful checks and limits

Frozen SC17 contract: **109 PASS, 0 FAIL**, independently rerun; raw TAP in `WMS-517-mac-independent-review-20261006.tap`. Frozen tests are unchanged from `136ce395ff085955eff669ed8a96cf68fe9938c1`. Cases cover dynamic counts, multiple pages, duplicate IDs, incomplete pages, changed eligible set, foreign/session scope and no helper signing/create/submit. Existing plain DOM fixture lacks React loading state, explaining the gap.

Exact four-file equality to implementation source and node syntax checks on helper/launcher/generator plus `zsh -n` command passed. Attempted bundle regeneration was interrupted by ENOSPC (disk full); no reproducibility claim is made for this review. No deployment, physical CryptoPro signature, real Mac permission flow or True API withdrawal was performed. Native dialog source separates opening/enumerating certificates from final submit/sign; helper clicks only the preparation action and restores original fetch.

Optional separate WMS-652 observation: `product_scope.py` at `a5979fc311b88c07dace842a5786a7eefa48ea03` compares entire trusted-reference tree, committed HEAD, worktree, index and new files, without commit subject parsing. Actual candidate versus `d61805978b3e7878d1056c99b4e6e0823edf49a5` has zero product paths and verifier output exactly agrees (`WMS-652-product-scope-actual-diff-20261006.json`). Independent 51-test run was interrupted by ENOSPC and is **not accepted as passed**; raw failure output is preserved. No full independent PASS for that optional responsibility.

Verdict: **WMS-517 helper changes required for the reproduced P1**. The failure concerns software preparation and must be fixed before release; it does not add a physical operator gate. No broader unchanged WMS audit was undertaken.
