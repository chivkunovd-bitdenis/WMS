# F19 Browser Product QA Final: возврат со сканированием и автопечатью ШК

Дата: 2026-08-13
Роль: isolated Per-feature Browser Product QA Agent
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`

## Verdict

`BROWSER_PRODUCT_QA_PASSED`

F19 проходит живой browser product QA gate. Реальный UI был открыт локально через
`http://127.0.0.1:5179/`, API работал локально на `127.0.0.1:18019`, база SQLite
лежала внутри этой evidence-папки во время прогона. Production, staging,
Railway variables, внешние панели и секреты не трогались.

## Проверенный scope

- Product / UX approval: `evidence/f19-product-rereview/F19_PRODUCT_REREVIEW_RU.md`.
- Dev commit: `0d87bc3c6bbefc1546f3d4b7467e9553e54bb26f`.
- Code Review passed commit: `97510723f8f2d0f14ebba40bb035af09093cee0d`.
- Current `HEAD` during QA: `17fef5926b101d89ca11b7bf5c5834f1b2e45f08`.

## Browser evidence

Финальный проход выполнен через Playwright Chromium против того же локального UI.
Это browser-runner: он открывает настоящую страницу, кликает элементы, ждёт
видимые состояния и network responses. API-вызовы использовались только для
seed-данных.

Основные артефакты:

- `f19-playwright-result.json` — полный структурированный лог кликов, видимых
  проверок, payload печати и геометрии 1280px.
- `f19-playwright-seed.json` — ids документов и товаров финального QA-прогона.
- `f19-playwright-console.json` — console log браузера; только Vite debug и
  стандартное React DevTools info.
- `playwright-run.log` — итог команды `BROWSER_PRODUCT_QA_PASSED`.
- `backend.log`, `frontend.log` — локальные серверные логи.
- `pw-02-ordinary-inbound-no-autoprint-switch.png` — обычная поставка без
  switch автопечати.
- `pw-03-return-inbound-autoprint-enabled.png` — возврат со switch рядом со
  сканером.
- `pw-05-return-successful-scan-print-payload.png` — состояние после успешного
  scan.
- `pw-06-return-missing-wb-fails-closed.png` — понятная ошибка при отсутствии
  WB ШК.
- `pw-07-return-1280-visual-final.png` — финальная геометрия 1280px.

Дополнительно был открыт UI через Browser plugin. Этот прогон подтвердил
видимость экранов и switch, но встроенная защита Browser plugin не разрешила
включить `window.__WMS_CAPTURE_PRINT_HTML__`, поэтому проверка print payload
была завершена Playwright Chromium, где этот штатный capture используется
самим e2e-контуром проекта.

## Gate checklist

1. Реальный UI открыт в браузере: passed.
2. Ordinary inbound: `Тип: Поставка`; `ff-inbound-return-autoprint` отсутствует;
   scan panel не перегружен: passed.
3. Return inbound: `Тип: Возврат`; компактный switch `Печатать ШК при скане`
   виден рядом со сканером и включается: passed.
4. Successful scan по товару с `wb_barcode`: строка `F19 Fact Product`
   увеличилась до `1`; print payload:
   `F19 Fact Product\nwb-fact-f19-pw-1786634397925`; SKU в payload отсутствует;
   `marking-print-dialog` не открылся: passed.
5. Manual picker и manual create при включённом switch добавили факт `1`, но
   `__WMS_LAST_PRINT_HTML__` остался `__NO_PRINT__`: passed.
6. Missing WB barcode: товар без `wb_barcode` был просканирован по SKU,
   строка увеличилась до `1`, пользователь увидел `У товара нет ШК WB для печати.`,
   print payload остался `__NO_PRINT__`, SKU fallback не напечатан: passed.
7. 1280px: `documentScrollWidth = 1280`, `bodyScrollWidth = 1280`, scan panel и
   table укладываются в viewport; технического мусора (`undefined`, `null`,
   traceback, stack, `[object Object]`, `NaN`) в видимом тексте нет: passed.

## Commands run

- `git rev-parse --show-toplevel`
- `sed -n '1,220p' AGENTS.md`
- `sed -n '1,520p' docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`
- `git status --short --branch`
- local backend:
  `WMS_AUTO_CREATE_SCHEMA=1 DATABASE_URL=sqlite+aiosqlite:///.../f19-browser-qa.db JWT_SECRET_KEY=... E2E_MOCK_WB_CARDS=1 E2E_MOCK_WB_SUPPLIES=1 E2E_MOCK_WB_WAREHOUSES=1 python3 -m uvicorn app.main:app --host 127.0.0.1 --port 18019`
- local frontend:
  `VITE_API_PROXY=http://127.0.0.1:18019 E2E_SELLER_PATH_PREFIX=/seller VITE_SELLER_PORTAL_URL=http://127.0.0.1:5179/seller/ npm run dev -- --host 0.0.0.0 --port 5179`
- final browser QA:
  `node --input-type=module ... | tee ../docs/reviews/product-operations-ux/2026-08-12/evidence/f19-browser-product-qa-final/playwright-run.log`

## Status

- local: passed in local browser QA.
- committed: final commit SHA is reported by the QA agent after commit.
- pushed: no.
- deployed: no.
- browser-tested: yes.
- blocker: none.
