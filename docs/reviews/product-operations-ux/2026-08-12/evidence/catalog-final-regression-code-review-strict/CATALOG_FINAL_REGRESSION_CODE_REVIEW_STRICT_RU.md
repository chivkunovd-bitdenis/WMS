# CATALOG_FINAL_REGRESSION_CODE_REVIEW_STRICT_RU

Дата: 2026-08-14 MSK.

Роль: Catalog Final Regression Strict Code Review Agent.

Repo: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.

HEAD на момент review: `d59959de70a8b9d447f200bdb703023c35b7b449`.

Verdict: `CODE_REVIEW_PASSED`.

Это только code review. Я не делал commit, push, staging, production, Railway, secrets и не запускал browser QA. `npm run build` и focused Playwright `seller-stock-directions.spec.ts seller-available-stock.spec.ts` не дублировались; принял уже переданный результат как внешний прогон и проверил код/diff/регрессионные ожидания.

## Reviewed Scope

Проверялись только изменения в:

- `frontend/src/screens/v2/SellerProductsStockScreen.tsx`
- `frontend/src/utils/readApiErrorMessage.ts`
- `frontend/tests-e2e/seller-stock-directions.spec.ts`
- `frontend/tests-e2e/seller-available-stock.spec.ts`

Команды review:

- `git diff -- frontend/src/screens/v2/SellerProductsStockScreen.tsx frontend/src/utils/readApiErrorMessage.ts frontend/tests-e2e/seller-stock-directions.spec.ts frontend/tests-e2e/seller-available-stock.spec.ts`
- `rg` по обязательным строкам acceptance: `WB / ШК`, `Артикул WB`, `Действия`, `В ячейках`, `На ФФ`, `Свободный FBO`, `Настроить FBS-пул`, `product_ids`, `directions_exceed_stock`
- `git diff --check -- ...` по этим четырём файлам: без whitespace-ошибок

## Findings

Blocking findings: нет.

Non-blocking risk: старый поясняющий текст над таблицей всё ещё говорит, что `Остаток` — это "всего на ФФ минус резерв", хотя новая ячейка теперь показывает несколько подписанных величин. Это не часть текущего diff acceptance и не блокирует code review, но live Product Browser QA должен смотреть на итоговый экран глазами оператора, а не считать этот code review product approval.

## Mandatory Checks

1. Header seller table.

Passed. В компоненте header заменён на `Артикул WB`: `frontend/src/screens/v2/SellerProductsStockScreen.tsx:886`. Старый `WB / ШК` в изменённых файлах не остался как positive expectation: он есть только как negative assertion в `frontend/tests-e2e/seller-stock-directions.spec.ts:96`.

2. Остатки больше не голые числа.

Passed. Ячейка остатков теперь рендерит подписанные строки `В ячейках`, `На ФФ`, `Свободный FBO`: `frontend/src/screens/v2/SellerProductsStockScreen.tsx:953-978`. E2E закрепляет эти подписи в `frontend/tests-e2e/seller-stock-directions.spec.ts:114-116` и `frontend/tests-e2e/seller-available-stock.spec.ts:217-219`.

3. Отдельная one-button колонка `Действия`.

Passed. Header `Действия` удалён из seller products table; таблица теперь имеет 7 колонок и empty-state `colSpan={7}`: `frontend/src/screens/v2/SellerProductsStockScreen.tsx:864-890`, `frontend/src/screens/v2/SellerProductsStockScreen.tsx:1081-1084`. Кнопка `ТЗ` перенесена в колонку `ТЗ / ЧЗ` и остаётся reachable через `seller-packaging-edit-*`: `frontend/src/screens/v2/SellerProductsStockScreen.tsx:1053-1078`. E2E проверяет отсутствие header `Действия`: `frontend/tests-e2e/seller-stock-directions.spec.ts:99`.

4. FBS pool action и selected-only bulk.

Passed. Row action теперь `Пул`, с `aria-label` и `title` `Настроить FBS-пул`: `frontend/src/screens/v2/SellerProductsStockScreen.tsx:992-1001`. Bulk flow остаётся selected-only: `confirmBulkFbsSync` строит массив `productIds` из `selectedRows` и отправляет `product_ids: productIds`, без `null`: `frontend/src/screens/v2/SellerProductsStockScreen.tsx:608-620`. E2E проверяет, что bulk body содержит именно `[productId]`: `frontend/tests-e2e/seller-stock-directions.spec.ts:144-149`.

5. F22 safe-sync rules.

Passed. Короткие row statuses сохранены в `fbsPublicationState`: `Нет FBS`, `Ошибка WB`, `WB: N шт`, `Проверяем WB`, `Пауза`: `frontend/src/screens/v2/SellerProductsStockScreen.tsx:107-124`. При `stock_fbs <= 0` состояние `Нет FBS` запрещает toggle через `canToggle: false`; switch disabled, когда `!publication.canToggle`: `frontend/src/screens/v2/SellerProductsStockScreen.tsx:1018-1024`. В проверенных изменениях нет `product_ids: null` и нет нового frontend fallback publish `0`. E2E закрепляет `Нет FBS`, disabled toggle, `Проверяем WB` и отсутствие технических sync enum в таблице: `frontend/tests-e2e/seller-stock-directions.spec.ts:106`, `frontend/tests-e2e/seller-stock-directions.spec.ts:118-123`, `frontend/tests-e2e/seller-stock-directions.spec.ts:176-181`.

6. Error `directions_exceed_stock`.

Passed. Код ошибки переведён на человеческий текст: `frontend/src/utils/readApiErrorMessage.ts:7`. `readApiErrorMessage` применяет словарь и для строкового `detail`, и для структурного `detail.code`: `frontend/src/utils/readApiErrorMessage.ts:48-49`, `frontend/src/utils/readApiErrorMessage.ts:68-75`. E2E проверяет, что raw `directions_exceed_stock` не виден пользователю: `frontend/tests-e2e/seller-stock-directions.spec.ts:302-307`.

7. Tests protect product acceptance.

Passed. `seller-stock-directions.spec.ts` проверяет отсутствие `WB / ШК` и `Действия`, подписанные stock labels, `Пул`, отсутствие `Лимит`, отсутствие raw sync enum, selected-only body, geometry/rowHeight `<=72` и отсутствие overflow: `frontend/tests-e2e/seller-stock-directions.spec.ts:95-123`, `frontend/tests-e2e/seller-stock-directions.spec.ts:136-149`, `frontend/tests-e2e/seller-stock-directions.spec.ts:182-218`. `seller-available-stock.spec.ts` дополнительно закрепляет `Артикул WB`, WB article и stock labels после MP-plan path: `frontend/tests-e2e/seller-available-stock.spec.ts:208-243`.

## Status

- local: reviewed in working tree
- committed: no
- pushed: no
- deployed: no
- browser-tested by this agent: no
- code review result: `CODE_REVIEW_PASSED`

Следующий gate всё равно должен быть живой Browser Product QA: code review не доказывает, что итоговая строка визуально проходит на реальном `/seller/products` при `1280x720`.
