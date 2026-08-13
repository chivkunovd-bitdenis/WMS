# F05 Browser Product QA After Geometry

Статус: `BROWSER_PRODUCT_QA_PASSED`.

Дата проверки: 2026-08-13.

Git-root:

```bash
/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812
```

Проверенный HEAD перед QA evidence commit:

```bash
25e0e2dd4dc86f7570836ae9ca7a42ccf785322a
```

Перед QA прочитаны `AGENTS.md` и `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`.
Production, staging, Railway variables, внешние панели и секреты не трогались.

## Команда live browser QA

Из `frontend/`:

```bash
E2E_API_PORT=18206 E2E_WEB_PORT=18207 npx playwright test ../docs/reviews/product-operations-ux/2026-08-12/evidence/f05-browser-product-qa-after-geometry/f05-browser-product-qa-after-geometry.spec.ts --config ../docs/reviews/product-operations-ux/2026-08-12/evidence/f05-browser-product-qa-after-geometry/playwright.f05-after-geometry.config.cjs --project=chromium --headed --reporter=line
```

Локально подняты:

- FastAPI backend: `http://127.0.0.1:18206`
- Vite frontend: `http://127.0.0.1:18207`
- SQLite DB: временная e2e DB в evidence-папке, после прогона удалена и в Git не добавлялась.

Финальный результат команды: `1 passed (49.0s)`.

## Реально пройденный сценарий

1. Через UI зарегистрирован локальный FF tenant, созданы seller, seller account, warehouse и товар для e2e-сценария.
2. Создана submitted inbound-заявка с планом: `3` единицы товара, `2` короба.
3. FF admin вошёл через реальную форму логина, открыл `Приёмка`, кликнул строку нужной заявки.
4. FF дважды просканировал заявленный SKU. В карточке FF стало видно: `План 3`, `Принято 2`, `Недостача 1`.
5. FF из карточки приёмки создал новый товар и добавил его в факт. В карточке FF стало видно: `План 0`, `Принято 1`, `Излишек 1`, `Добавлено ФФ`.
6. FF нажал `Завершить приёмку`, увидел dialog расхождений с `Недостача 1` и `Излишек 1`, затем подтвердил проведение.
7. Seller вошёл в портал, открыл `Документы`, увидел ту же поставку в статусе `В сортировке`, затем открыл карточку приёмки.

## Что проверено

- Seller documents показывают человеческие статусы: `В сортировке`, `На сборке`, `Отменено`; raw MP statuses `collecting/cancelled` не видны.
- Seller карточка после проведения открывается как `Карточка приёмки · Поставка`, а не как draft-форма.
- В seller fact-card видны `Заявлено 3`, `Факт 3`, строка недостачи `3 -> 2`, строка излишка `0 -> 1`, `Добавлено ФФ`.
- Draft controls после проведения отсутствуют: нет `seller-inbound-draft-form`, `seller-inbound-add-products`, `seller-inbound-submit-warehouse`, `seller-inbound-save-draft`, `seller-inbound-line-delete`.
- На странице не найден raw technical text: `collecting`, `cancelled`, `receiving`, `sorting`, `done`, `undefined`, `NaN`, `null`.
- UI не получил новых перегружающих chips/labels/columns/buttons в проверяемой карточке; таблица компактная, без внутренней горизонтальной прокрутки на `1280x900`.

## Geometry evidence

Live browser metrics из `f05-after-geometry-result.json`:

```json
{
  "viewportWidth": 1280,
  "viewportHeight": 900,
  "documentScrollWidth": 1280,
  "bodyScrollWidth": 1280,
  "globalOverflowPx": 0,
  "tableClientWidth": 958,
  "tableScrollWidth": 958,
  "containerClientWidth": 958,
  "containerScrollWidth": 958,
  "containerLeft": 281,
  "containerRight": 1239,
  "discrepancyHeaderLeft": 1104.8515625,
  "discrepancyHeaderRight": 1239,
  "discrepancyTexts": ["Недостача 1", "Излишек 1"]
}
```

Ключевой previous blocker снят: `containerScrollWidth == containerClientWidth`
и `discrepancyHeaderRight == containerRight`, поэтому колонка `Расхождение`
с `Недостача 1` / `Излишек 1` видна без внутреннего horizontal scroll.

## Evidence files

- `f05-browser-product-qa-after-geometry.spec.ts`
- `playwright.f05-after-geometry.config.cjs`
- `f05-after-geometry-result.json`
- `playwright-headed-after-geometry-rerun.log`
- `screenshots/01-ff-card-before-complete-1280.png`
- `screenshots/02-ff-discrepancy-dialog-1280.png`
- `screenshots/03-seller-documents-human-statuses-1280.png`
- `screenshots/04-seller-fact-card-1280.png`
- `playwright-output/f05-browser-product-qa-aft-f1264-ll-factual-card-at-1280x900-chromium/trace.zip`

Итоговый verdict:

`BROWSER_PRODUCT_QA_PASSED`
