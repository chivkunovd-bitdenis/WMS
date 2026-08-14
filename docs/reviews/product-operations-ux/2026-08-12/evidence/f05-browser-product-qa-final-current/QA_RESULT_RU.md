# F05 Browser Product QA Final Current

Статус: `BROWSER_PRODUCT_QA_FAILED`.

Дата проверки: 2026-08-13.

Git-root:

```bash
/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812
```

Проверенный HEAD до QA evidence commit:

```bash
2e5e2c4da80c5d4694b985188045737066dc180c
```

Перед QA прочитаны `AGENTS.md` и `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`.
Production, staging, Railway variables, внешние панели и секреты не трогались.

## Команда live browser QA

Из `frontend/`:

```bash
E2E_API_PORT=18146 E2E_WEB_PORT=18147 npx playwright test ../docs/reviews/product-operations-ux/2026-08-12/evidence/f05-browser-product-qa-final-current/f05-browser-product-qa-final-current.spec.ts --config ../docs/reviews/product-operations-ux/2026-08-12/evidence/f05-browser-product-qa-final-current/playwright.f05-final-current.config.cjs --project=chromium --headed --reporter=line
```

Локально подняты:

- FastAPI backend: `http://127.0.0.1:18146`
- Vite frontend: `http://127.0.0.1:18147`
- SQLite DB: временная e2e DB в evidence-папке, после прогона не добавлялась в Git.

Финальный результат команды: `1 failed`.

## Реально пройденный сценарий

1. Через UI зарегистрирован локальный FF tenant, созданы seller, seller account, warehouse и товар для e2e-сценария.
2. Создана submitted inbound-заявка с планом: `3` единицы товара, `2` короба.
3. FF admin вошёл через реальную форму логина, открыл `Приёмка`, кликнул строку нужной заявки.
4. FF дважды просканировал заявленный SKU. В карточке FF стало видно: `План 3`, `Принято 2`, `Недостача 1`.
5. FF из карточки приёмки создал новый товар и добавил его в факт. В карточке FF стало видно: `План 0`, `Принято 1`, `Излишек 1`, `Добавлено ФФ`.
6. FF нажал `Завершить приёмку`, увидел dialog расхождений с `Недостача 1` и `Излишек 1`, затем подтвердил проведение.
7. Seller вошёл в портал, открыл `Документы`, увидел ту же поставку в статусе `В сортировке`, затем открыл карточку приёмки.

## Что прошло

- Raw MP statuses больше не торчат в списке документов: мокированные `collecting` и `cancelled` на seller side отображаются как `На сборке` и `Отменено`.
- Seller карточка после проведения открывается как `Карточка приёмки · Поставка`, а не как draft-форма.
- В DOM seller fact-card есть бизнес-данные: `Заявлено 3`, `Факт 3`, строка недостачи `3 -> 2`, строка излишка `0 -> 1`, `Добавлено ФФ`.
- Draft controls после проведения отсутствуют: не показаны `seller-inbound-draft-form`, `seller-inbound-add-products`, `seller-inbound-submit-warehouse`, `seller-inbound-save-draft`, `seller-inbound-line-delete`.
- На странице не найдено raw technical text: `collecting`, `cancelled`, `receiving`, `sorting`, `done`, `undefined`, `NaN`, `null`.

## Blocking issue

`BROWSER_PRODUCT_QA_FAILED`, потому что seller fact-card при viewport `1280x900`
не показывает всю обязательную таблицу без внутренней горизонтальной прокрутки.
Правая колонка `Расхождение`, где должны быть `Недостача 1` и `Излишек 1`,
уезжает за видимую область таблицы.

Измерения из live browser:

```json
{
  "viewportWidth": 1280,
  "documentScrollWidth": 1280,
  "bodyScrollWidth": 1280,
  "containerClientWidth": 958,
  "containerScrollWidth": 1080,
  "containerRight": 1239,
  "discrepancyHeaderRight": 1361
}
```

То есть глобального overflow страницы нет, но сама таблица шире видимой зоны
seller card: `1080 > 958`. Для F05 это blocker, потому что селлер должен без
дополнительной прокрутки понимать, где недостача/излишек/добавленный ФФ товар.

## Evidence files

- `f05-browser-product-qa-final-current.spec.ts`
- `playwright.f05-final-current.config.cjs`
- `f05-final-current-result.json`
- `playwright-headed-final-current.log`
- `screenshots/01-ff-card-before-complete-1280.png`
- `screenshots/02-ff-discrepancy-dialog-1280.png`
- `screenshots/03-seller-documents-human-statuses-1280.png`
- `screenshots/04-seller-fact-card-1280.png`
- `playwright-output/f05-browser-product-qa-fin-a9f93-opens-the-same-factual-card-chromium/error-context.md`
- `playwright-output/f05-browser-product-qa-fin-a9f93-opens-the-same-factual-card-chromium/test-failed-1.png`
- `playwright-output/f05-browser-product-qa-fin-a9f93-opens-the-same-factual-card-chromium/trace.zip`

Итоговый verdict:

`BROWSER_PRODUCT_QA_FAILED`
