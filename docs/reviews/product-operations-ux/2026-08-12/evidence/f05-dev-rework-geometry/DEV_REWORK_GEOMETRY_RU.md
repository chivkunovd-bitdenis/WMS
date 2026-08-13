# F05 Dev Rework Geometry

Статус: `DEV_REWORK_DONE`.

Дата: 2026-08-13.

Git-root:

```bash
/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812
```

## Что исправлено

Seller fact-card в недraft-статусах больше не задаёт таблице минимальную ширину `1080px`.
Таблица факта занимает ширину карточки, а длинные SKU, ШК, артикулы и названия ужимаются
в своих ячейках. Колонки `Заявлено`, `Факт`, `Расхождение` и отметка `Добавлено ФФ`
остались в той же карточке и без новых чипов, технических текстов, duplicate buttons
или новых колонок.

## Проверки

```bash
cd frontend
npm run test:unit -- sellerInboundDocumentUi.test.ts
```

Результат: passed, `src/screens/v2/sellerInboundDocumentUi.test.ts` — 4 tests.

```bash
cd frontend
npx playwright test tests-e2e/seller-inbound-fact-card-geometry.spec.ts --project=chromium --reporter=line
```

Результат: passed, 1 test.

Сценарий готовит факт приёмки через API, затем проходит реальный seller UI path:
seller открывает документ и видит fact-card с недостачей и добавленным ФФ товаром.
В тест добавлены regression-assertions:

- `documentScrollWidth <= viewportWidth + 1`;
- `bodyScrollWidth <= viewportWidth + 1`;
- `containerScrollWidth <= containerClientWidth + 1`;
- правый край header `Расхождение` не выходит за правый край table container;
- `Недостача 1`, `Излишек 1`, `Добавлено ФФ` видны в seller fact-card;
- draft controls после проведения отсутствуют.

```bash
cd frontend
npm run build
```

Результат: passed. Vite показал только существующий warning о крупных chunks после minification.

## Gate note

Это dev evidence, не финальный Browser Product QA. После rework F05 нужен новый scoped code review
и отдельный live Browser Product QA.
