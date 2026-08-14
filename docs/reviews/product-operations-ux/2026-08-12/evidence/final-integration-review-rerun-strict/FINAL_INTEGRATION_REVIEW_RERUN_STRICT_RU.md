# Final Integration Review Rerun Strict — WMS product operations UX 2026-08-12

Дата проверки: 2026-08-14, Europe/Moscow.

Роль: Final Integration Review Rerun Agent, read-only. Код приложения, staging,
production, Railway, внешние кабинеты, secrets, commit и push не трогались.
Создан только этот review artifact.

Рабочий Git-root:

```text
/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812
```

Ветка: `iteration/wms-product-ux-features-20260812`.

HEAD на момент rerun: `d59959de70a8b9d447f200bdb703023c35b7b449`.

## Verdict

`FINAL_INTEGRATION_PASSED`

Коротко: предыдущий `FINAL_INTEGRATION_FAILED` был вызван F12 backend leak:
seller-token получал `200 OK` на
`GET /operations/inventory-balances/monthly-snapshots`, хотя контракт требует
`403`. В текущем дереве endpoint уже переведен на FF inventory permission, а
targeted backend rerun подтвердил исправление: single F12 access test passed и
полный targeted backend bundle из предыдущего final review дал `83 passed`.

Строгие per-feature Product Browser approvals по всем active release features
найдены, включая финальные rerun approvals для `F05`, `F07`, `F12`, `F14` и
`F15`. Активной фичи со статусом `PRODUCT_REWORK_REQUIRED` в финальном
консолидированном статусе не осталось.

Запрещенная трактовка: это не release-ready, не stage-ready, не production
proof и не разрешение на deploy. Final live Product Browser Regression остается
обязательным следующим gate и этим документом не засчитан.

## Sources Read

- `AGENTS.md`;
- `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`;
- `docs/reviews/product-operations-ux/2026-08-12/STRICT_PRODUCT_RECERT_AUDIT_RU.md`;
- `docs/reviews/product-operations-ux/2026-08-12/evidence/final-integration-review-strict/FINAL_INTEGRATION_REVIEW_STRICT_RU.md`;
- final live approval artifacts for `F05`, `F07/R01`, `F12/F14/R02`, `F15`;
- current F12 monthly snapshot access diff and targeted backend tests.

No repo-visible Markdown artifact containing the literal
`TECHNICAL_GATE_PASSED` string was found by `rg`. For this rerun I therefore
verified the technical fix directly with the same F12 failing contract and the
previous final-review targeted backend bundle. If an external task-level
technical gate artifact exists outside this checkout, it was not available in
the repository evidence set.

## Active Scope

Active release scope remains 21 features: `F01-F19`, `F22`, `F23`.

Out of scope / blocked outside this release scope:

- `F20`: out of scope by user;
- `F21`: blocked because the current WMS checkout has no `sellerfocus.pro`
  source/deploy target.

## Gate Matrix

| Gate | Rerun result |
|---|---|
| active_features_total | 21 |
| unresolved_PRODUCT_REWORK_REQUIRED | 0 |
| final_per_feature_browser_approvals | 21 |
| F05 final live approval | present: `evidence/f05-product-browser-qa-rerun-live-strict/F05_PRODUCT_BROWSER_QA_RERUN_LIVE_STRICT_RU.md` |
| F07 final live approval | present: `evidence/r01-packaging-product-browser-qa-rerun-live-strict/R01_PACKAGING_PRODUCT_BROWSER_QA_RERUN_LIVE_STRICT_RU.md` |
| F12 final live approval | present through R02: `evidence/r02-staff-nav-product-browser-qa-final-live-strict/R02_STAFF_NAV_PRODUCT_BROWSER_QA_FINAL_LIVE_STRICT_RU.md` |
| F14 final live approval | present through R02: `evidence/r02-staff-nav-product-browser-qa-final-live-strict/R02_STAFF_NAV_PRODUCT_BROWSER_QA_FINAL_LIVE_STRICT_RU.md` |
| F15 final live approval | present: `evidence/f15-product-browser-qa-rerun-live-strict/F15_PRODUCT_BROWSER_QA_RERUN_LIVE_STRICT_RU.md` |
| technical blocker from previous final review | closed by current endpoint diff and backend rerun |
| final browser regression | required, not passed in this artifact |
| release/stage readiness | not claimed |

## Previous Blocker Rerun

Previous blocker:

```text
tests/test_stock_directions.py::test_monthly_stock_snapshot_get_requires_ff_inventory_access
assert blocked_seller.status_code == 403
E assert 200 == 403
```

Current code state:

- `backend/app/api/inventory_balances.py` now uses
  `require_ff_inventory_access = require_ff_permission(PERM_INVENTORY)`;
- `GET /operations/inventory-balances/monthly-snapshots` depends on
  `require_ff_inventory_access`, not the broader `assert_inventory_read_access`;
- seller-token access is therefore outside the allowed monthly snapshot surface.

Commands run by this rerun:

```bash
cd backend
PYTHONDONTWRITEBYTECODE=1 \
WMS_TEST_DATABASE_URL=sqlite+aiosqlite:////tmp/wms_final_integration_rerun_f12_1786670000.sqlite \
uv run --frozen pytest \
  tests/test_stock_directions.py::test_monthly_stock_snapshot_get_requires_ff_inventory_access \
  -q -p no:cacheprovider
```

Result: `1 passed in 2.95s`.

```bash
cd backend
PYTHONDONTWRITEBYTECODE=1 \
WMS_TEST_DATABASE_URL=sqlite+aiosqlite:////tmp/wms_final_integration_rerun_backend_tests_1786670001.sqlite \
uv run --frozen pytest \
  tests/test_packaging_tasks.py \
  tests/test_marking_pending.py \
  tests/test_fbs_packaging_integration.py \
  tests/test_fbs_packaging_fulfillment.py \
  tests/test_product_packaging_instructions.py \
  tests/test_staff_packaging_billing.py \
  tests/test_marketplace_unload_and_discrepancy_acts.py \
  tests/test_stock_directions.py \
  tests/test_seller_shop_scope.py \
  tests/test_staff_users.py \
  tests/test_inbound_intake.py \
  -q -p no:cacheprovider
```

Result: `83 passed in 108.26s`.

## Per-Feature Approval Check

`STRICT_PRODUCT_RECERT_AUDIT_RU.md` has historical sections where `F05`,
`F07`, `F12`, `F14` and `F15` were sent back to rework. Those are superseded by
the later "Evidence consolidation after strict live recert" section and by the
final live rerun artifacts dated 2026-08-14.

- `F05`: `PRODUCT_BROWSER_APPROVED` after seller fact-card and seller shell
  rerun. Old overloaded 9-column card blocker is closed.
- `F07`: `PRODUCT_BROWSER_APPROVED` after R01 packaging rerun. Mixed-seller
  block, scanner/manual/undo/history, pending marking, MP/F17 print and FBS
  same-SKU overpack were checked in live UI.
- `F12`: `PRODUCT_BROWSER_APPROVED` through final R02 staff navigation rerun,
  and backend monthly snapshot seller-token leak is now closed by tests.
- `F14`: `PRODUCT_BROWSER_APPROVED` through final R02 staff navigation rerun.
  Menu/direct-route parity and FF/seller surface guard passed in live UI.
- `F15`: `PRODUCT_BROWSER_APPROVED` after delete-only-drafts rerun. Seller draft
  delete, seller/FF non-draft blocks, collecting box-line direct remove,
  shipped read-only controls and read-back preservation passed.

For the remaining active features, the final consolidated strict recert status
records strict live browser approval for `F01-F04`, `F06`, `F08-F11`, `F13`,
`F16-F19`, `F22` and `F23`.

## Docs / Status Contradictions

The repository still contains older reports that can mislead a reader if opened
without chronology:

- `ITERATION_FINAL_INTEGRATION_REVIEW_RU.md` says the old iteration integration
  and browser regression passed under the pre-strict interpretation.
- `ITERATION_PRODUCT_GATE_RU.md` has an older final gate section that says
  `passed`.
- `ITERATION_FEATURE_CARDS_RU.md` still contains legacy `integration_pending`
  rows and older per-feature notes, although its header now says it is
  superseded by `STRICT_PRODUCT_RECERT_AUDIT_RU.md`.
- `STRICT_PRODUCT_RECERT_AUDIT_RU.md` itself contains both historical rework
  findings and the later consolidated approvals; the later consolidation is the
  operative section for this rerun.

These contradictions do not block this integration rerun because the strict
handoff, strict recert consolidation, final per-feature live reruns and current
backend tests establish the newer state. They do block any casual "ready"
claim: a docs cleanup should mark old passed reports as superseded before
handoff to people who may not know the chronology.

## Remaining Required Gate

Final live Product Browser Regression is still required and may run separately.
It must cover the joined system, not only isolated per-feature approvals:

- inbound/reception/returns: `F01-F06`, `F18`, `F19`;
- packaging/MP/FBO/FBS/print: `F07`, `F15`, `F17`;
- catalog/stocks/WB sync: `F08-F11`, `F16`, `F22`, `F23`;
- staff/access/seller scope: `F12`, `F13`, `F14`;
- cross-feature route/session/read-back paths after reload.

Until that regression passes and the relevant code/evidence is committed under
a known SHA, this remains an integration-review pass only.

## Final State

- final integration rerun: `FINAL_INTEGRATION_PASSED`;
- final browser regression: still required, not passed here;
- release/stage readiness: not claimed;
- commit/push/deploy: not performed by this agent;
- durable Git state: not established by this agent because the user explicitly
  forbade commit/push;
- workspace state: dirty before this rerun; this agent created only this
  artifact and wrote test DBs under `/tmp`.
