# F03 Browser Product QA Final Current

Статус: `BROWSER_PRODUCT_QA_PASSED`.

Проверенный Git-root:

```bash
/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812
```

Перед QA прочитаны:

- `AGENTS.md`
- `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`

Команда live browser прогона:

```bash
cd /Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/frontend
E2E_API_PORT=18136 E2E_WEB_PORT=18137 npx playwright test ../docs/reviews/product-operations-ux/2026-08-12/evidence/f03-browser-product-qa-final-current/f03-final-product-qa-current.spec.ts --config ../docs/reviews/product-operations-ux/2026-08-12/evidence/f03-browser-product-qa-final-current/playwright.f03-final-current.config.cjs --project=chromium --headed --reporter=line
```

Результат последнего прогона: `3 passed (22.3s)`.

Что проверено живым браузером:

1. Открыта приёмка FF по URL `http://127.0.0.1:18137/app/ff/reception`.
2. Сценарий "меньше приехало": плановая строка осталась с `План 1`, `Принято 0`, `Недостача 1`.
3. Сценарий "больше приехало": плановая строка после двух сканов стала `План 1`, `Принято 2`, `Излишек 1`.
4. Сценарий "другой товар селлера": товар того же селлера, которого не было в исходной заявке, добавился в факт как строка `План 0`, `Принято 1`, `Излишек 1`, с отметкой `Добавлено ФФ`.
5. Товар селлера из каталога, включая не из исходной заявки, добавляется через поле скана и кнопку `Скан`.
6. Расхождения подсвечены красным, а рядом есть человеческое предупреждение: `Есть расхождения с планом — при завершении потребуется подтверждение.`
7. Отдельной таблицы технических проблем, raw codes и лишних технических чипов на экране приёмки не видно.
8. Чужой товар другого селлера не добавляется: UI показывает человеку `Товар не найден в этой поставке.`, raw code `product_not_on_request` остаётся только в HTTP response evidence, не в интерфейсе.
9. Основной складской сценарий понятен оператору: открыть заявку, сканировать товар, увидеть план/факт/дельту, при необходимости завершить приёмку.
10. На 1280px глобального overflow и black strip нет: `documentScrollWidth=1280`, `bodyScrollWidth=1280`, `globalOverflowPx=0`.

Ключевые evidence-файлы:

- `f03-final-result.json`
- `playwright-headed-current-rerun.log`
- `screenshots/01-desktop-same-seller-added-discrepancy.png`
- `screenshots/08-desktop-same-product-overage.png`
- `screenshots/07-foreign-barcode-human-message.png`
- `playwright-output/*/trace.zip`

Итоговый verdict:

`BROWSER_PRODUCT_QA_PASSED`
