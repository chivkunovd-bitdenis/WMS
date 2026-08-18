# F22 Browser Product QA final rerun after lease datetime fix

Дата: 2026-08-13, Europe/Moscow.
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
Роль: independent Browser Product QA Agent.
Fix under test: `3329aa6d270363fe1c6f4227996c51fc8c32fd57` (`Fix FBS stock sync lease datetime comparison`).
Code review source: `docs/reviews/product-operations-ux/2026-08-12/evidence/f22b-code-review/F22B_CODE_REVIEW_RU.md`.
Статус: `BROWSER_PRODUCT_QA_FAILED`.

Код продукта не редактировался. Запись была только в:

`docs/reviews/product-operations-ux/2026-08-12/evidence/f22-browser-product-qa-final/`

## Короткий вывод

F22b lease datetime fix снял прежний backend blocker: во время финального live run больше не было `TypeError: can't compare offset-naive and offset-aware datetimes`, `binding_errors` остался `0`.

Но полный Browser Product QA gate нельзя засчитать как passed. Negative safe-zero path прошел, positive backend/WB readback тоже прошел, но seller UI после подтвержденного readback показал `Ошибка WB`, а не компактное подтвержденное или pending-safe состояние. Для складского пользователя это неверный результат: WB уже подтвердил `7`, а экран говорит об ошибке.

## Обязательные сценарии

1. Seller products/catalog opens without crash — `PASS`.
   В live browser открылся seller catalog, была видна таблица `seller-products-table`, строка товара отрисовалась без runtime crash.

2. WB/emulator has `20` for product before action — `PASS`.
   Runner выставил emulator stock через `PUT /api/v3/stocks/501001`, затем negative readback держал `20`.

3. Without FBS pool, sync attempt/enable does not send unsafe `0` — `PASS`.
   UI показал `Нет FBS`, toggle был disabled, forced click не создал UI-запросов sync. Manual/backend sync attempt не отправил `0`; emulator остался `20`; sync item получил safe error `unsafe_stock_unknown` без target/confirmed amount.

4. With explicit FBS pool `N`, manual/allowed sync publishes `N`, WB readback confirms `N`, UI shows compact confirmed/pending-safe state without `Лимит` or raw code — `FAIL`.
   В run `run-20260813-171430` backend/WB часть прошла: DB readback `chrt_id=111001`, `last_target_amount=7`, `last_confirmed_amount=7`, `status=confirmed`; emulator readback был `7`.
   Но browser UI status после positive path был `Ошибка WB`. Это не compact confirmed/pending-safe state.

5. No black strip/page overflow at 1280px — `PASS`.
   Viewport `1280x720`: `scrollWidth=1280`, `bodyScrollWidth=1280`, `blackStrip=false`.

Дополнительно проверено: table header не содержит `Лимит`; visible seller text не содержит raw technical codes `unsafe_stock_unknown`, `unsafe_zero_blocked`, `warehouse_mapping_missing`, `pending_confirmation`, `undefined`, `null`.

## Evidence

Main runner:

```bash
docs/reviews/product-operations-ux/2026-08-12/evidence/f22-browser-product-qa-final/run_f22_browser_product_qa_final.sh
```

Browser scenario:

```bash
docs/reviews/product-operations-ux/2026-08-12/evidence/f22-browser-product-qa-final/f22_browser_product_qa_final.mjs
```

Decisive run:

```text
docs/reviews/product-operations-ux/2026-08-12/evidence/f22-browser-product-qa-final/run-20260813-171430/
```

Key files:

- `run-20260813-171430/f22-browser-product-qa-result.json`
- `run-20260813-171430/qa-console.log`
- `run-20260813-171430/api.log`
- `run-20260813-171430/emulator.log`
- `run-20260813-171430/wms.sqlite`
- `run-20260813-171430/wb_emulator.sqlite`
- `run-20260813-171430/seller-products-no-fbs-pool.png`
- `run-20260813-171430/seller-products-fbs-pool-7.png`

Additional harness attempts kept for traceability:

- `run-20260813-171132/` — negative path passed; harness navigation failed before positive path.
- `run-20260813-171623/` — negative path passed; harness paused before positive path while refining race-free setup.

## Commands

Mandatory instruction reads:

```bash
git rev-parse --show-toplevel
sed -n '1,240p' AGENTS.md
sed -n '1,520p' docs/WMS_FEATURE_GATE_PROTOCOL_RU.md
sed -n '1,240p' docs/reviews/product-operations-ux/2026-08-12/evidence/f22b-code-review/F22B_CODE_REVIEW_RU.md
```

Final run:

```bash
docs/reviews/product-operations-ux/2026-08-12/evidence/f22-browser-product-qa-final/run_f22_browser_product_qa_final.sh
```

Result summary:

```bash
for d in docs/reviews/product-operations-ux/2026-08-12/evidence/f22-browser-product-qa-final/run-*; do
  echo "=== $d"
  jq -r '.status, (.checks[]? | [.name, .passed, (.positiveStatus // .statusBefore // "")] | @tsv)' "$d/f22-browser-product-qa-result.json"
done
```

Decisive DB readback:

```bash
sqlite3 docs/reviews/product-operations-ux/2026-08-12/evidence/f22-browser-product-qa-final/run-20260813-171430/wms.sqlite \
  "select wb_warehouse_id, stock_sync_enabled, last_sync_status, coalesce(last_error_code, ''), coalesce(lease_until, '') from fbs_warehouse_bindings;
   select chrt_id, last_target_amount, last_confirmed_amount, status, coalesce(last_error_code, '') from fbs_stock_sync_items;"
```

Output:

```text
501001|1|confirmed||
111001|7|7|confirmed|
```

Harness syntax:

```bash
node --check docs/reviews/product-operations-ux/2026-08-12/evidence/f22-browser-product-qa-final/f22_browser_product_qa_final.mjs
bash -n docs/reviews/product-operations-ux/2026-08-12/evidence/f22-browser-product-qa-final/run_f22_browser_product_qa_final.sh
```

## Verdict

`BROWSER_PRODUCT_QA_FAILED`

Причина: F22b backend fix работает на live path и WB/emulator readback подтверждает `7`, но seller UI после confirmed readback показывает `Ошибка WB`. Gate 6 требует правильного видимого состояния для пользователя, поэтому F22 нельзя считать browser-product approved.
