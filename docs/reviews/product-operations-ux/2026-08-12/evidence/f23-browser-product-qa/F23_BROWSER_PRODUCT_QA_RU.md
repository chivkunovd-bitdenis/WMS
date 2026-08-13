# F23 Browser Product QA: seller catalog cleanup

Дата: 2026-08-13, Europe/Moscow.
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
Роль: independent Browser Product QA Agent.
Dev commit under QA: `0090a76bb8398f6bfcb1fc98b77aaf955af16176` (`fix seller catalog publication cleanup`).
Статус: `BROWSER_PRODUCT_QA_PASSED`.

Код продукта не редактировался. Запись велась только в:

`docs/reviews/product-operations-ux/2026-08-12/evidence/f23-browser-product-qa/`.

## Короткий verdict

`BROWSER_PRODUCT_QA_PASSED`.

Seller products screen открылся в реальном Chromium без crash. На viewport
1280x720 не обнаружен body/document/table horizontal overflow: `documentScrollWidth
= 1280`, `bodyScrollWidth = 1280`, `viewportWidth = 1280`.

Основной F23 flow прошел руками через UI:

1. открыть seller catalog;
2. выбрать строку товара;
3. нажать одно действие `Изменить публикацию`;
4. выбрать `Включить`;
5. увидеть confirmation dialog;
6. подтвердить;
7. проверить, что PATCH ушел только с выбранным `product_ids`;
8. увидеть результат `Обновлено 1. Будут изменены только выбранные товары.`

FBS no-pool состояние компактное и безопасное: на строке видно `Нет FBS`, toggle
disabled, `Лимит` не отображается. F08 drawer CRUD проверен достаточно для
регрессии: create -> edit -> delete направления в drawer прошли, видимый итог
после удаления есть.

## Проверки

| Requirement | Result | Evidence |
| --- | --- | --- |
| Seller products screen opens without crash | PASS | `screenshots/01-seller-products-1280-initial.png` |
| No black strip/page overflow on 1280px | PASS | `f23-browser-product-qa-evidence.json`, `geometry1280` |
| No `Лимит` | PASS | visible body text scan, row FBS cell scan |
| No permanent `Включить всем` / `Выключить всем` / `Пауза публикации всем` | PASS | visible body text scan |
| No chip chaos/raw technical statuses | PASS | visible body text scan: no `pending_confirmation`, `warehouse_mapping_missing`, `wb_upstream_error`, `conflict` |
| Select rows -> one action -> choose -> confirm | PASS | `screenshots/02-selected-only-confirm-dialog.png` |
| Request contains selected `product_ids` only | PASS | PATCH body: `{"product_ids":["2a8af69f-fd07-4cf2-8a6b-a7151d17dc31"],"fbs_stock_sync_enabled":true}` |
| Visible result after confirm | PASS | `screenshots/03-bulk-result-visible.png` |
| FBS no pool compact/safe | PASS | `fbsCellText = "Нет FBS"`, toggle disabled |
| F08 directions drawer CRUD enough for no regression | PASS | `screenshots/04-f08-direction-created.png`, `screenshots/05-f08-direction-deleted.png` |

## Commands Run

Existing F23 browser e2e against manually started local stack:

```bash
E2E_WEB_ORIGIN=http://127.0.0.1:5179 \
E2E_API_ORIGIN=http://127.0.0.1:18123 \
E2E_SELLER_PATH_PREFIX=/seller \
npx playwright test tests-e2e/seller-stock-directions.spec.ts \
  --config=playwright.live-staging.config.ts \
  --project=chromium \
  --output ../docs/reviews/product-operations-ux/2026-08-12/evidence/f23-browser-product-qa/playwright-output \
  --reporter=line
```

Result: `1 passed (8.6s)`.

Independent QA script:

```bash
E2E_WEB_ORIGIN=http://127.0.0.1:5179 \
E2E_API_ORIGIN=http://127.0.0.1:18123 \
node docs/reviews/product-operations-ux/2026-08-12/evidence/f23-browser-product-qa/run-f23-browser-product-qa.mjs
```

Result: passed; JSON evidence saved to `f23-browser-product-qa-evidence.json`.

## Evidence Files

- `f23-browser-product-qa-evidence.json`
- `run-f23-browser-product-qa.mjs`
- `screenshots/01-seller-products-1280-initial.png`
- `screenshots/02-selected-only-confirm-dialog.png`
- `screenshots/03-bulk-result-visible.png`
- `screenshots/04-f08-direction-created.png`
- `screenshots/05-f08-direction-deleted.png`
- `playwright-output/.last-run.json`

## Gate Metrics

| Метрика | Количество |
| --- | ---: |
| total_features | 1 |
| ba_ready | 1 |
| product_reviewed | 1 |
| product_approved_for_dev | 1 |
| product_rework_required | 0 |
| dev_done | 1 |
| code_review_passed | 1 |
| browser_product_qa_passed | 1 |
| browser_product_qa_failed | 0 |
| browser_product_qa_blocked | 0 |
| integrated | 0 |
| final_regression_passed | 0 |

## Status

- local: browser-tested on local stack `127.0.0.1:18123` + `127.0.0.1:5179`.
- committed: yes; final commit SHA is reported in the QA handoff.
- pushed: not pushed by this QA agent.
- deployed: not checked by this QA agent.
- browser-tested: yes, Chromium, viewport 1280x720.
- remaining risks: this is F23 feature QA only, not full iteration regression or staging deploy proof.
