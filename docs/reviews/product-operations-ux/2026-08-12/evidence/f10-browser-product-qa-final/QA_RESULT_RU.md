# F10 Browser Product QA Final

Verdict: `BROWSER_PRODUCT_QA_PASSED`.

Дата прогона: 2026-08-13. Прогон выполнен локально из Git-root
`/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`,
без deploy/push/Railway/production/staging и без внешних кабинетов секретов.

## Что проверено

F10 проверялся как продуктовый браузерный сценарий, а не как unit/API-only тест.
Runner поднял локальный FastAPI backend, Vite frontend, локальный WB mock для
`PUT/POST /api/v3/stocks/{warehouseId}` и прошёл UI через Chromium/Playwright
в viewport 1280x720.

Положительный путь:

- physical stock: `1000`;
- явный FBS-пул: `200`;
- non-FBS reserve/free-FBO side: `300`, поэтому free FBO в UI: `500`;
- active FBS reservation: `7`;
- пользователь селлера открыл экран товаров и увидел компактный FBS/WB блок;
- оператор ФФ запустил ручную синхронизацию на экране FBS stock sync;
- WB mock получил `PUT` только `193` по `chrtId=1210`;
- WB mock получил `POST` readback по `chrtId=1210`;
- seller UI после readback показал `WB: 193 шт`;
- значение не равно физическому total `1000` и не равно free FBO `500`.

Ambiguous/fail-closed путь:

- у того же типа сценария seller/product есть две активные stock-sync привязки
  WB/WMS-складов;
- задан только product-level FBS-пул;
- ручной sync вернул `products_targeted=0`, `products_confirmed=0`,
  `errors=2`, `binding_errors=2`;
- WB mock не получил новых `PUT` и `POST`;
- заранее выставленный WB остаток `20` остался `20` для обеих привязок;
- seller UI показал компактное человеческое состояние `Ошибка WB`;
- raw `ambiguous_warehouse_scope` не появился как основной текст в seller UI.

Визуальный контроль 1280px:

- в seller table нет `Лимит`;
- нет raw-кодов `pending_confirmation`, `warehouse_mapping_missing`,
  `unsafe_stock_unknown`, `unsafe_zero_blocked`, `ambiguous_warehouse_scope`,
  `wb_upstream_error`, `readback_mismatch`, `duplicate_chrt_id`, `conflict`;
- нет extra global bulk buttons `Включить всем` / `Выключить всем`;
- document/body/table horizontal overflow не обнаружен;
- black strip не обнаружен;
- row height остался компактным: `91.515625px`.

## Evidence

- Machine result: `f10_browser_product_qa_result.json`.
- Runner: `f10_browser_product_qa_runner.mjs`.
- Deterministic seed helper: `f10_seed_db.py`.
- Logs: `logs/backend.log`, `logs/frontend.log`.
- Screenshots:
  - `screenshots/positive-seller-before-sync.png`
  - `screenshots/positive-ff-manual-sync.png`
  - `screenshots/positive-seller-after-readback.png`
  - `screenshots/ambiguous-ff-fail-closed-sync.png`
  - `screenshots/ambiguous-seller-safe-error.png`

## Commands

```bash
git rev-parse --show-toplevel
sed -n '1,220p' AGENTS.md
sed -n '1,260p' docs/WMS_FEATURE_GATE_PROTOCOL_RU.md
git status --short --branch
node --check docs/reviews/product-operations-ux/2026-08-12/evidence/f10-browser-product-qa-final/f10_browser_product_qa_runner.mjs
python3 -m py_compile docs/reviews/product-operations-ux/2026-08-12/evidence/f10-browser-product-qa-final/f10_seed_db.py
node docs/reviews/product-operations-ux/2026-08-12/evidence/f10-browser-product-qa-final/f10_browser_product_qa_runner.mjs
```

## Notes

Первый локальный attempt был harness-only failure: seed запускался без
`PYTHONPATH=<repo>/backend`, поэтому Python не видел модуль `app`. Это было
исправлено в evidence runner без изменения production-кода. Второй harness
attempt дошёл до браузера, но открывал seller deep link напрямую; финальный
runner повторяет обычный пользовательский путь: `/seller/` login -> navigation
`Товары`.

Финальный verdict основан только на успешном живом browser run, завершившемся
`f10_browser_product_qa_result.json.verdict = BROWSER_PRODUCT_QA_PASSED`.
