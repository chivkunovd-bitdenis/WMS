# Final Browser Regression Rerun Live Strict — WMS product operations UX 2026-08-12

Дата: 2026-08-14, Europe/Moscow.

Repo: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.

Verdict: `FINAL_BROWSER_REGRESSION_PASSED`.

Это строгий финальный Product Browser Regression rerun после возвратов из
предыдущего full regression. Все группы ниже проверялись в живом браузере:
`browser_used: yes`. Проверки были намеренно распараллелены по независимым
складским зонам, чтобы не ждать один длинный монолитный прогон, но каждая группа
открывала реальный UI, кликала процесс и фиксировала screenshot/JSON evidence.

Код, commit, push, staging, production, Railway и secrets этим финальным
browser-regression документом не трогались.

## Why This Rerun Supersedes The Failed Regression

Исторический artifact
`evidence/final-browser-regression-live-strict/FINAL_BROWSER_REGRESSION_LIVE_STRICT_RU.md`
остается валидной записью провала: он вернул `FINAL_BROWSER_REGRESSION_FAILED`
из-за seller catalog `/seller/products`.

После него были закрыты два live browser blockers:

1. Catalog/stocks blocker:
   - Product rework spec вернул catalog на доработку;
   - code review passed;
   - dedicated live Product Browser QA passed;
   - final catalog group rerun passed.
2. Inbound stale-modal blocker:
   - first inbound group rerun failed live because discrepancy dialog stayed
     visible after successful completion;
   - stale-modal fix was applied and code-reviewed;
   - focused browser e2e passed;
   - inbound after-fix live Product Browser QA passed.

Этот документ supersedes старый failed browser regression только как более
поздний финальный rerun. Старый failed artifact не удаляется и не переписывается.

## Final Group Matrix

| Group | Scope | Live artifact | Browser evidence | Verdict |
| --- | --- | --- | --- | --- |
| Inbound / reception / returns / seller fact-card | F01-F06, F18, F19 | `evidence/final-browser-regression-rerun-inbound-after-fix-live-strict/FINAL_BROWSER_REGRESSION_RERUN_INBOUND_AFTER_FIX_LIVE_STRICT_RU.md` | Chromium `headless=false`, viewport `1280x720`, backend `18221`, frontend `5221` | `FINAL_BROWSER_GROUP_PASSED` |
| Catalog / stocks / FBS/FBO / WB sync / FF catalog cleanup | F08-F11, F16, F22, F23 | `evidence/final-browser-regression-rerun-catalog-live-strict/FINAL_BROWSER_REGRESSION_RERUN_CATALOG_LIVE_STRICT_RU.md` | Chromium `headless=false`, viewport `1280x720`, backend `18591`, frontend `15591`, WB emulator `18592` | `FINAL_BROWSER_GROUP_PASSED` |
| Staff roles / direct routes / seller scope | R02, F12, F13, F14 | `evidence/final-browser-regression-rerun-staff-live-strict/FINAL_BROWSER_REGRESSION_RERUN_STAFF_LIVE_STRICT_RU.md` | Chromium `headless=false`, viewport `1280x720`, backend `50299`, frontend `50300` | `FINAL_BROWSER_GROUP_PASSED` |
| Packaging / marking / MP print / delete-only-draft | R01, F07, F15, F17 | `evidence/final-browser-regression-rerun-packaging-delete-live-strict/FINAL_BROWSER_REGRESSION_RERUN_PACKAGING_DELETE_LIVE_STRICT_RU.md` | Chromium `headless=false`, viewport `1280x720`, API `18214`, Vite `55214` | `FINAL_BROWSER_GROUP_PASSED` |
| Technical / integration | build, focused Playwright, backend ruff, targeted backend bundle | `evidence/final-technical-integration-gate-rerun-strict/FINAL_TECHNICAL_INTEGRATION_GATE_RERUN_STRICT_RU.md` and `evidence/final-technical-integration-gate-after-inbound-fix-strict/FINAL_TECHNICAL_INTEGRATION_GATE_AFTER_INBOUND_FIX_STRICT_RU.md` | technical gate, not product browser verdict | `FINAL_TECHNICAL_INTEGRATION_PASSED` |

## Critical Product Checks Closed

### Catalog / Stocks

The previous P0 catalog blocker is closed in live browser evidence:

- `/seller/products` opened at `1280x720`;
- header is `Артикул WB`; old `WB / ШК` is absent;
- separate one-button `Действия` column is absent;
- stock is labeled as `В ячейках`, `На ФФ`, `Свободный FBO`, not naked
  `12 / 12 / 7`;
- FBS pool action is `Пул` with `Настроить FBS-пул`;
- selected-only bulk request sends `product_ids` array, not `null`;
- missing FBS pool stays `Нет FBS`, toggle disabled, no `WB: 0 шт` success;
- FBS direction read-back shows main row and drawer split clearly;
- `ТЗ` opens from the `ТЗ / ЧЗ` area;
- row height measured `68.6328125px`, no page-level overflow.

Final catalog group verdict:
`FINAL_BROWSER_GROUP_PASSED`.

### Inbound / Reception / Returns

The inbound stale-modal blocker is closed in live browser evidence:

- ordinary inbound with discrepancy completed through real browser;
- after discrepancy confirm:
  - `modalCountImmediately: 0`;
  - stale question count `0`;
  - stale confirm button absent;
  - document status `В сортировке`;
  - fact read-back `Принято: 3 из 5`;
  - line read-back `Недостача 2`;
- conducted inbound waybill print contains fact/discrepancy and no raw
  UUID/status/FBS/WB order noise;
- return inbound shows `Возврат`, autoprint switch only on return, WB barcode
  scan prints and reads back `Принято: 1 из 1`;
- seller fact-card is read-only, human, compact, and has no raw technical noise;
- every measured state at `1280x720` had no page-level horizontal overflow.

Final inbound group verdict after fix:
`FINAL_BROWSER_GROUP_PASSED`.

### Staff / Access / Seller Scope

The staff group passed live browser judgement:

- reception staff has reception/sorting and human denials for disallowed FF and
  seller routes;
- shipments/packaging staff has shipments/FBS/packaging and denials for
  stock-sync/inventory/reception/settings/sellers where not allowed;
- catalog/inventory staff has menu/direct-route parity for catalog and
  inventory;
- settings staff sees compact staff settings without irrelevant payroll-only
  columns;
- seller manager sees only allowed shop/product; forbidden shop/product does not
  leak through home/products/direct route/inbound picker.

Harness warnings were adjudicated in the artifact: they came from QA fixture
names or inactive controls under modal backdrop, not product blockers.

Final staff group verdict:
`FINAL_BROWSER_GROUP_PASSED`.

### Packaging / Marking / MP Print / Delete

The packaging/delete group passed live browser judgement:

- packaging create dialog shows seller identity and blocks mixed-seller tasks;
- scanner/manual/undo/history/reload are clear and durable;
- invalid scan uses human error, not raw `unknown_barcode`;
- overpack uses human message, not raw `line_already_packed`;
- pending marking shows human labels and no `__SORTING__`/raw codes;
- MP/FBO final print button generated the expected print HTML and no FBS order
  QR;
- seller draft delete flow supports cancel/read-back/confirm;
- submitted/non-draft document has no delete action;
- FF non-draft box-line remove is hidden in UI, direct remove returns blocked
  backend response and read-back is preserved;
- all measured `1280px` surfaces had no page-level horizontal overflow.

Final packaging/delete group verdict:
`FINAL_BROWSER_GROUP_PASSED`.

## Technical Gate

Current technical/integration state is passed:

- catalog technical rerun:
  - scoped `git diff --check`: passed;
  - `npm run build`: passed;
  - focused catalog Playwright: `2 passed`;
  - backend `ruff check .`: passed;
  - targeted backend bundle: `83 passed`.
- after inbound stale-modal fix:
  - scoped `git diff --check`: passed;
  - `npm run build`: passed;
  - focused inbound Playwright: `2 passed`;
  - strict code review: `CODE_REVIEW_PASSED`.

## Final Gate Decision

`FINAL_BROWSER_REGRESSION_PASSED`.

All active release feature groups now have strict live browser product evidence
after the final returned blockers. There is no current
`FINAL_BROWSER_GROUP_FAILED` or `FINAL_BROWSER_GROUP_BLOCKED` verdict in the
latest rerun set.

## Stage Deployment Proof

Stage deployment was verified after this final browser regression:

- application deploy commit:
  `595bf93404794ade562b7f9fc4d6c1bdc09267c6`;
- `origin/staging` points to the same SHA;
- Railway backend `WMS` deployment
  `321617c0-5727-445d-a426-c6b2ee952b3c` returned `SUCCESS`;
- Railway frontend `web` deployment
  `063166b4-a27e-4071-a558-b0aeeaeecd24` returned `SUCCESS`;
- public web smoke passed on
  `https://web-production-9e7c1.up.railway.app/`;
- public API smoke passed on `/api/health` and backend `/health`;
- live Chromium `headless=false` browser smoke passed for the staging login
  shell at `1440x900`;
- deployed frontend HTML references `/assets/ff-BEgAjw6d.js`, matching the
  local Railway-arg build from the final tree.

Stage proof artifact:
`evidence/stage-deploy-verification-595bf93/STAGE_DEPLOY_VERIFICATION_595BF93_RU.md`.
