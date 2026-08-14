# F09 Browser Product QA: Свободный FBO

Дата: 2026-08-13 18:44 MSK.
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
Роль: isolated Browser Product QA Agent.

Verdict: `BROWSER_PRODUCT_QA_PASSED`.

## Mandatory checks

- `git rev-parse --show-toplevel` -> `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
- Прочитан `AGENTS.md`.
- Прочитан `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`.
- `git status --short --branch` до QA показал грязный worktree с параллельными изменениями; чужие изменения не откатывались.
- Секреты, Railway variables, внешние панели, production и staging не открывались и не менялись.

## Gate source

- Product/UX OK: `docs/reviews/product-operations-ux/2026-08-12/evidence/f09-f10-product-unblock/F09_F10_PRODUCT_UX_VERDICT_RU.md`.
- Dev commit: `1689c23261c1b347a3f31c55e9930fcbebca3855`.
- Code review passed: `a189c472f7241cd02a0711b6ebbe9e46148f7247`.

## Live browser setup

Поднят только локальный UI:

- backend: `http://127.0.0.1:18000`, sqlite QA DB, `WMS_AUTO_CREATE_SCHEMA=1`, WB e2e mocks.
- frontend: `http://127.0.0.1:5174`, Vite proxy to local backend.
- browser viewport: 1280px wide.

Browser visibility API returned `IAB visibility is not supported in a subagent thread`; after that QA continued through the Browser tab API with real UI clicks and screenshots. This did not replace the browser gate with API/unit checks.

## Seeded warehouse scenario

Required scenario was prepared and verified before UI clicks:

- physical stock: `1000`;
- FBS direction: `200`;
- non-FBS directions/reserves: `300`;
- active MP/FBO reserve: `100`;
- free FBO before active MP reserve: `500`;
- available for new FBO unload: `400`.

Seed row from live local API:

```json
{
  "quantity": 1000,
  "reserved": 100,
  "available": 400,
  "quantity_fbs": 200,
  "quantity_reserved_directions": 300,
  "quantity_free_fbo": 500
}
```

## Browser checks

Passed:

- Seller MP/FBO draft opened in the real seller UI.
- Product picker showed compact `Доступно FBO` and row availability `400`.
- No `Лимит`, raw formula, reserve ids, backend model names, technical error codes, extra chips, extra labels or double drawer were visible in the F09 path.
- Quantity `401` was blocked with visible human error: `Недостаточно свободного FBO остатка. Уменьшите количество или освободите резерв/FBS-пул.`
- Quantity `400` was added to the draft.
- `Запланировать` moved the request to `Запланировано`; seller sees the handoff hint `Дальше заявку обрабатывает фулфилмент.`
- At 1280px, `bodyScrollWidth=1280`, `documentScrollWidth=1280`, final table `scrollWidth=1232`, `clientWidth=1232`, black bars detected: `0`.

## Evidence files

- `f09-browser-product-qa-result.json` - full run log and all checks.
- `f09-seller-documents-open.png` - seller documents screen at 1280px.
- `f09-prepared-draft-open.png` - MP/FBO draft modal before product selection.
- `f09-picker-available-400.png` - picker shows `Доступно FBO` and `400`.
- `f09-qty-401-human-error.png` - `401` blocked with human-readable error.
- `f09-qty-400-line-before-plan.png` - `400` added to draft line table.
- `f09-qty-400-planned.png` - final `Запланировано` state.

## Commands run

- `git rev-parse --show-toplevel`
- `sed -n '1,240p' AGENTS.md`
- `sed -n '1,260p' docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`
- `sed -n '261,520p' docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`
- `git status --short --branch`
- local backend: `python3 -m uvicorn app.main:app --host 127.0.0.1 --port 18000`
- local frontend: `npm run dev -- --host 0.0.0.0 --port 5174`
- Browser Product QA through Browser tab API against `http://127.0.0.1:5174/seller/`

## Remaining risks

- This is local live browser QA, not staging/production proof.
- The worktree was already dirty from parallel agents before F09 QA. This evidence commit must be scoped to F09 files only.
