# F05 Code Review Current — единая карточка приемки ФФ/селлер

Дата проверки: 2026-08-13.

Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`

Ветка: `iteration/wms-product-ux-features-20260812`

HEAD на момент проверки: `5c1ab614e11c075543f95edac1361e70cdc1c1b2`

Роль: независимый Code Review / blocker audit Agent.

Код не редактировался.

## Verdict

`CODE_REVIEW_PASSED`

Текущий blocker из матрицы F05 больше не подтверждается фактическим кодом и
целевыми проверками. Ранее матрица держала F05 в `CODE_REVIEW_FAILED`, потому
что seller documents показывали raw MP statuses `collecting/cancelled`. Сейчас
`SellerDocumentsScreen.tsx` переводит эти статусы в пользовательские русские
лейблы, а неизвестные backend statuses скрывает за нейтральным текстом
`Статус уточняется`.

Селлерская карточка приемки также соответствует F05: в недraft-статусах она
показывает фактическую карточку, а не draft-форму. В ней видны статус, тип
операции, склад, короба, суммарно `Заявлено / Факт`, строки с `Заявлено`,
`Факт`, `Недостача N` / `Излишек N` и признак `Добавлено ФФ`.

## Проверенные источники

- `AGENTS.md`
- `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`
- `docs/reviews/product-operations-ux/2026-08-12/ITERATION_FEATURE_CARDS_RU.md`
- `docs/reviews/product-operations-ux/2026-08-12/AUTONOMOUS_GATE_RUN_STATUS_RU.md`
- `docs/reviews/product-operations-ux/2026-08-12/ITERATION_PRODUCT_GATE_RU.md`
- `docs/reviews/product-operations-ux/2026-08-12/evidence/f05-browser-product-qa/QA_RESULT_RU.md`
- `docs/reviews/product-operations-ux/2026-08-12/evidence/f05-browser-product-qa/f05-status-and-states.spec.cjs`
- `frontend/src/screens/v2/SellerDocumentsScreen.tsx`
- `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`
- `frontend/src/screens/ff/FfInboundRequestView.tsx`
- `backend/app/api/inbound_intake.py`
- `backend/app/services/inbound_intake_service.py`
- `backend/tests/test_inbound_intake.py`
- `frontend/src/screens/v2/sellerInboundDocumentUi.test.ts`
- `frontend/tests-e2e/inbound-receiving-v2.spec.ts`

## Code findings

### 1. Raw MP statuses в seller documents исправлены

Файл: `frontend/src/screens/v2/SellerDocumentsScreen.tsx`

Функция `sellerDocumentStatusRu` сейчас мапит MP statuses:

- `collecting` -> `На сборке`
- `cancelled` -> `Отменено`
- неизвестный MP status -> `Статус уточняется`

Та же функция мапит inbound statuses `receiving`, `sorting`, `done` и не
возвращает raw backend text для неизвестных inbound statuses. Таблица документов
использует именно эту функцию в колонке `Статус`, поэтому исходный blocker
`collecting/cancelled` в UI больше не активен.

### 2. Seller fact-card показывает факт и расхождения

Файл: `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`

Для non-draft inbound карточка строит заголовок `Карточка приёмки · <тип>` и
summary `Статус`, `Тип операции`, `Склад`, `Короба`, `Расхождения`, `Товары`.
Фактическое количество берется через `effective_actual_qty ?? actual_qty ?? 0`.
В строках таблицы видны:

- `Заявлено`
- `Факт`
- `Недостача N` или `Излишек N`
- `Добавлено ФФ` для строк, добавленных fulfillment-оператором

Draft controls на проведенной карточке отсутствуют по e2e: add-products,
submit, save и delete не отображаются.

### 3. FF карточка сохраняет тот же язык расхождений

Файл: `frontend/src/screens/ff/FfInboundRequestView.tsx`

FF-сторона использует человеческие labels `Излишек N`, `Недостача N`,
`Добавлено ФФ`, `Тип`, `Селлер`, `Принято`, `Короба`, `Расхождения`. Это
согласовано с seller read-only карточкой: обе стороны показывают один фактический
документ, а не две разные бизнес-версии.

### 4. Backend отдает поля, нужные seller fact-card

Файлы:

- `backend/app/api/inbound_intake.py`
- `backend/app/services/inbound_intake_service.py`

API response для линии содержит `added_by_fulfillment`, `expected_qty`,
`actual_qty`, `effective_actual_qty`, а request response содержит
`operation_type`, `planned_box_count`, `actual_box_count`, `boxes_discrepancy`,
`has_discrepancy`, `seller_name`. Это достаточный контракт для F05 UI.

## Targeted tests

Запущено в текущем checkout:

```bash
cd /Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/backend
pytest -q tests/test_inbound_intake.py -k 'inbound_receiving_accepts_seller_catalog_product_as_discrepancy or inbound_receiving_lines_accepts_same_seller_catalog_product or inbound_receiving_lines_rejects_foreign_seller_product'
```

Результат: `3 passed, 12 deselected`.

```bash
cd /Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/frontend
npm run test:unit -- src/screens/v2/sellerInboundDocumentUi.test.ts
```

Результат: `1 passed`, `4 tests passed`.

```bash
cd /Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/frontend
npx playwright test tests-e2e/inbound-receiving-v2.spec.ts --project=chromium --grep "seller sees conducted factual card after FF shortage and added product" --reporter=line
```

Результат: `1 passed`.

```bash
cd /Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/frontend
F05_E2E_API_PORT=18126 E2E_WEB_PORT=18127 npx playwright test -c ../docs/reviews/product-operations-ux/2026-08-12/evidence/f05-browser-product-qa/playwright.f05.evidence.config.cjs ../docs/reviews/product-operations-ux/2026-08-12/evidence/f05-browser-product-qa/f05-status-and-states.spec.cjs --project=chromium --reporter=line
```

Результат: `1 passed`.

Неверная команда, которую не нужно считать gate:

```bash
cd /Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/frontend
npm run test -- --run src/screens/v2/sellerInboundDocumentUi.test.ts
```

Результат: failed, потому что в `frontend/package.json` нет script `test`.
Правильная команда: `npm run test:unit`.

## Остаточные риски вне blocker F05

В `backend/app/services/inbound_intake_service.py` параметр
`allow_manual_product` сейчас протянут в сигнатуру `add_or_increment_received_product`,
но фактически не используется в теле функции. Это не воспроизводит F05 blocker:
F05 проверяет, что текущая fact-card показывает фактическую строку, а raw MP
statuses не попадают в seller documents. Но для соседнего rework F03/F04 стоит
отдельно решить, должен ли `source=manual_created` иметь более строгую серверную
семантику, или параметр нужно убрать как шум.

## Рекомендованный atomic dev scope

Для F05 дополнительный dev rework не нужен. Достаточно обновить матрицу F05 из
`CODE_REVIEW_FAILED / blocked_by_code_review` в `CODE_REVIEW_PASSED` и держать
следующим gate живой Browser Product QA / integration status по протоколу, если
оркестратор требует отдельного обновления карточки.

Если всё же выделять соседний технический cleanup, он не должен смешиваться с
F05: отдельная маленькая задача на `allow_manual_product` в inbound receiving
service с backend negative test на допустимость источника `seller_catalog` /
`manual_created`.
