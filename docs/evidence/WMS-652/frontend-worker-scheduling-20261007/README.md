# WMS-652: bounded frontend worker scheduling correction

The completed whole-package review and owner-authorized receipt-path correction remain unchanged. This follow-up changes only the execution concurrency of the full frontend producer after two real failures on immutable etalon a5df04f1560de0eaaf855199065936cb22a222b1. It has no separate reviewer PASS claim.

Run37585303815 attempt1: WMS650 first long-list case exceeded the unchanged5000ms limit (5935ms), followed by3 React act/DOM cascade failures;1668 cases passed. Attempt2 repeated that first timeout (5389ms) and its3 cascades, plus WMS684 six-print/date case at5233ms;1667 passed. Both kept the3 existing skips. Exact raw logs are saved alongside this document.

The same unchanged650 file ran separately with one worker:4PASS/0FAIL/0SKIP,6.38s total, first case1186ms. This proves a passing isolated execution; it does not replace remote full-CI proof.

Owner instruction relayed by moderator: «Делай bounded CI resource fix --maxWorkers=2 для Vitest. Это обычное исправление исполнения тестов по2 actual failures, не новая продуктовая задача/не отдельное review одной строки. All cases/assertions/5000ms/report shape остаются».

The sole command delta is --maxWorkers=2 on the existing full Vitest producer. No case, assertion, timeout, permission, collection selection, required report, or CI job was removed or changed. The manifest changes only the exact CI file digest. The product reference remains b2a03ec118f9b4a184edfc4c2973ff92e044fd6c. A new normal source pin and full exact-SHA CI remain mandatory before deployment.

Addressed verification with exactly two workers: unchanged650 and684 files together,15PASS/0FAIL/0SKIP in11.14s. C21=1620ms; the six-print/date case=1896ms, both under the unchanged5000ms limit. Raw Vitest JSON is targeted-two-workers.json. Strict product-scope comparison to b2a03ec118f9b4a184edfc4c2973ff92e044fd6c returned no changed product paths. This is targeted verification, not full remote CI or deployment.
