# F02 Browser Product QA Final — габариты товара из приемки

Verdict: `BROWSER_PRODUCT_QA_PASSED`

Дата прогона: 2026-08-13
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`
Ветка: `iteration/wms-product-ux-features-20260812`

## Что проверено живым браузером

Открыта карточка FF-приемки из очереди `Приёмка`. В строке товара нажата компактная icon-only кнопка `Габариты`, открыта модалка `Габариты товара`, введены длина `200`, ширина `100`, высота `50`, затем нажато `Сохранить`.

Проверенный результат:

- строка товара после сохранения содержит `200×100×50 мм · 1.00 л`;
- backend-readback через `/api/products` вернул `length_mm=200`, `width_mm=100`, `height_mm=50`, `volume_liters=1`;
- кнопка габаритов компактная: `aria-label="Габариты"`, без текста внутри, размер `40×40`;
- модалка компактная, три поля помещаются в одну строку, экран не раздувается;
- return/autoprint-шум в обычной приемке отсутствует: `ff-inbound-return-autoprint` count = `0`, текст `Печатать ШК при скане` не найден;
- на viewport `1280×800` горизонтальный overflow = `0`, screenshot width = `1280`, black viewport background = `false`.

Наблюдение: на итоговом 1280px-скриншоте текст в ячейке габаритов визуально обрезается многоточием после `200×100×50 мм ...`, но полный DOM-текст и backend-readback подтверждают расчет объема `1.00 л`. По gate-критерию F02 это не блокирует проход: объем либо виден, либо подтвержден backend-readback.

## Команда

```bash
cd /Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812
set -o pipefail
E2E_API_PORT=18126 E2E_WEB_PORT=18127 E2E_DB_FILE=e2e-f02-browser-final.db frontend/node_modules/.bin/playwright test --config=docs/reviews/product-operations-ux/2026-08-12/evidence/f02-browser-product-qa-final/f02-final-playwright.config.cjs --project=chromium --headed --output=docs/reviews/product-operations-ux/2026-08-12/evidence/f02-browser-product-qa-final/playwright-output --trace=on 2>&1 | tee docs/reviews/product-operations-ux/2026-08-12/evidence/f02-browser-product-qa-final/playwright-headed.log
```

Результат: `1 passed`.

## Evidence

- `f02-final-browser-product-qa-result.json`
- `playwright-headed.log`
- `playwright-output/f02-final-browser-product--8ef5d-rowser-product-QA-at-1280px-chromium/trace.zip`
- `screenshots/01-1280-inbound-row-before-dimensions.png`
- `screenshots/02-1280-dimensions-dialog-open.png`
- `screenshots/03-1280-dimensions-dialog-filled.png`
- `screenshots/04-1280-saved-dimensions-visible.png`
- `01-before-ui-metrics.json`
- `02-dialog-open-ui-metrics.json`
- `04-after-save-ui-metrics.json`

## Финальный вывод

`BROWSER_PRODUCT_QA_PASSED`. F02 закрывает live browser gate: габариты редактируются прямо из строки приемки, модалка не ломает плотность экрана, сохранение работает, расчет объема подтвержден, и на 1280px нет горизонтального overflow или черной полосы.
