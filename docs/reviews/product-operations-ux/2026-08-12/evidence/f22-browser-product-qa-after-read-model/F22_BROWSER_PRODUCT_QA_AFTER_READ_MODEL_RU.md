# F22 Browser Product QA after seller catalog read-model fix

Дата: 2026-08-13, Europe/Moscow.
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
Роль: isolated Per-feature Browser Product QA Agent.

Verdict: `BROWSER_PRODUCT_QA_PASSED`.

Код продукта не редактировался. Запись была только в:

`docs/reviews/product-operations-ux/2026-08-12/evidence/f22-browser-product-qa-after-read-model/`

Точечно обновлена F22-строка gate-матрицы в:

`docs/reviews/product-operations-ux/2026-08-12/ITERATION_FEATURE_CARDS_RU.md`

## Что проверено

Локально подняты три процесса: WMS API, Vite frontend и WB emulator. Browser path выполнялся через Chromium/Playwright с viewport `1280x720`: логин селлера, переход в `Товары`, клик по FBS toggle, открытие drawer распределения, ввод FBS-пула `7`, сохранение, возврат в каталог и readback финального статуса.

Решающий run:

`run-20260813-175847/`

## Negative safe-zero path

Стартовое состояние WB/emulator: `warehouse_id=501001`, `chrt_id=111001`, amount `20`.

На seller catalog без явного FBS-пула UI показал `Нет FBS`, toggle был disabled. Forced click по disabled toggle не создал UI-запросов `/fbs-stock-sync` или `/stocks/sync`; WB после попытки остался `20`.

Дополнительный backend sync attempt с отсутствующим FBS-пулом не отправил ноль: sync item остался `status=error`, `target=null`, `confirmed=null`, `error=unsafe_stock_unknown`, emulator amount `20`.

Скриншот: `run-20260813-175847/01-seller-products-no-fbs-pool.png`.

## Positive FBS-pool path

Через UI в drawer распределения создан явный FBS-пул:

- name: `FBS QA pool`;
- quantity: `7`;
- checkbox: `FBS-пул для публикации в WB`.

После синхронизации durable readback сошёлся:

```text
fbs_stock_sync_items: chrt_id=111001, last_target_amount=7, last_confirmed_amount=7, status=confirmed
WB emulator readback: 7
seller catalog read-model: fbs_sync_status=confirmed, fbs_published_amount=7
seller UI: WB: 7 шт
```

Скриншоты:

- `run-20260813-175847/02-seller-directions-fbs-pool-7.png`;
- `run-20260813-175847/03-seller-products-wb-7-readback.png`.

Примечание по runner output: финальный manual `POST /stocks/sync` вернул `bindings_processed=0`, потому что binding уже был занят/обработан фоновой sync-попыткой после включения. Product verdict основан не на этом счетчике, а на durable фактах выше: emulator получил amount `7`, sync item confirmed `7`, read-model confirmed `7`, и UI показал `WB: 7 шт`.

## Visual QA at 1280px

На `1280x720` не обнаружены black strip или page-level horizontal overflow:

- before sync: `scrollWidth=1280`, `bodyScrollWidth=1280`, `blackStrip=false`;
- after sync: `scrollWidth=1280`, `bodyScrollWidth=1280`, `blackStrip=false`.

Seller catalog визуально остаётся компактным: колонка `Лимит` отсутствует, кнопки и поля не раздувают строку, технические коды (`unsafe_stock_unknown`, `unsafe_zero_blocked`, `warehouse_mapping_missing`, `pending_confirmation`, `undefined`, `null`) не видны пользователю. Финальное состояние не показывает `Ошибка WB`.

## Commands

```bash
git rev-parse --show-toplevel
sed -n '1,240p' AGENTS.md
sed -n '1,260p' docs/WMS_FEATURE_GATE_PROTOCOL_RU.md
git status --short --branch
node --check docs/reviews/product-operations-ux/2026-08-12/evidence/f22-browser-product-qa-after-read-model/f22_browser_product_qa_after_read_model.mjs
bash -n docs/reviews/product-operations-ux/2026-08-12/evidence/f22-browser-product-qa-after-read-model/run_f22_browser_product_qa_after_read_model.sh
bash docs/reviews/product-operations-ux/2026-08-12/evidence/f22-browser-product-qa-after-read-model/run_f22_browser_product_qa_after_read_model.sh
jq -r '.status, (.checks[] | [.name, .passed] | @tsv)' docs/reviews/product-operations-ux/2026-08-12/evidence/f22-browser-product-qa-after-read-model/run-20260813-175847/f22-browser-product-qa-result.json
```

## Evidence files

- `f22_browser_product_qa_after_read_model.mjs` — browser QA scenario.
- `run_f22_browser_product_qa_after_read_model.sh` — local API/frontend/emulator runner.
- `run-20260813-175847/f22-browser-product-qa-result.json` — machine-readable result.
- `run-20260813-175847/qa-console.log` — full scenario output.
- `run-20260813-175847/api.log`, `web.log`, `emulator.log` — local server logs.
- `run-20260813-175847/wms.sqlite`, `wb_emulator.sqlite` — local disposable QA databases.
- screenshots listed above.

## Verdict

`BROWSER_PRODUCT_QA_PASSED`

F22 read-model fix closed the previous browser QA blocker: backend/WB confirmed amount `7`, seller catalog read-model returned `confirmed/7`, and live seller UI showed compact success `WB: 7 шт` instead of `Ошибка WB`.
