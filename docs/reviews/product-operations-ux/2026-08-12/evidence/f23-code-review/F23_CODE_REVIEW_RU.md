# F23 Code Review: seller catalog publication cleanup

Дата: 2026-08-13, Europe/Moscow.
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
Роль: independent Code Review Agent.
Review commit: `0090a76bb8398f6bfcb1fc98b77aaf955af16176` (`fix seller catalog publication cleanup`).
Статус: `CODE_REVIEW_PASSED`.

Код не редактировался. Проверка выполнена по измененным файлам:

- `frontend/src/screens/v2/SellerProductsStockScreen.tsx`;
- `frontend/tests-e2e/seller-stock-directions.spec.ts`.

Утвержденные входные артефакты:

- `docs/reviews/product-operations-ux/2026-08-12/evidence/f23-ba-ux-rework/F23_BA_UX_REWORK_SPEC_RU.md`;
- `docs/reviews/product-operations-ux/2026-08-12/evidence/f23-product-design-rereview/F23_PRODUCT_DESIGN_REREVIEW_RU.md`;
- `docs/reviews/product-operations-ux/2026-08-12/evidence/f22-product-review/F22_PRODUCT_VERDICT_SAFE_STOCK_SYNC_RU.md`.

## Короткий вывод

Критичных code-review blocker-ов по F23 не найдено. Commit убирает источник прежнего runtime crash: `Chip` больше не импортируется и не используется в seller catalog component. Основной F23-путь соответствует утвержденной модели: пользователь выбирает строки, видит одно bulk-действие `Изменить публикацию`, выбирает конкретное действие, подтверждает dialog и frontend отправляет в backend только массив выбранных `product_ids`, а не `null`.

Это не является browser product QA. По feature-gate протоколу после `CODE_REVIEW_PASSED` все еще нужен отдельный живой Browser Product QA на реальном UI.

## Проверка по checklist

1. Runtime crash `Chip is not defined`: passed.

   В `SellerProductsStockScreen.tsx` импортов `Chip` нет, JSX-использований `Chip` нет. `npm run build` прошел успешно.

2. Нет `Лимит` и постоянных кнопок "всем": passed.

   В основной таблице F23 не рендерит `Лимит`, `Включить всем`, `Выключить всем` или `Пауза публикации всем`. `fbs_stock_limit` остается только типовым полем API-строки и не выводится в основной seller catalog UI.

3. Main flow: select rows -> one bulk action -> confirm -> selected `product_ids` only: passed.

   Selection хранится в `selectedProductIds`; toolbar показывает `Изменить публикацию` только при `selectedCount > 0`; confirm dialog показывает выбранные товары; `confirmBulkFbsSync` отправляет `JSON.stringify({ product_ids: productIds, fbs_stock_sync_enabled: enabled })`, где `productIds` строится из `selectedRows.map((row) => row.id)`. Основной F23 UI не отправляет `product_ids: null`.

4. Нет raw technical statuses/chip chaos: passed.

   Raw statuses свернуты в короткие пользовательские состояния: `Нет FBS`, `Ошибка WB`, `WB: N шт`, `Проверяем WB`, `Пауза`. Регулярные MUI `Chip`-плашки удалены из экрана.

5. Нет очевидного black strip/page overflow risk на 1280: passed by code review and targeted e2e.

   Корневой контейнер держит `width: 100%`, `maxWidth: 100%`, `minWidth: 0`; таблица использует `tableLayout: fixed`, colgroup на 100% и компактные fixed-width row actions. E2E дополнительно проверяет `documentElement.scrollWidth <= viewportWidth`, `body.scrollWidth <= viewportWidth` и отсутствие overflow внутри table container на viewport 1280x720.

6. F08 drawer CRUD intact: passed.

   Drawer распределения остатка по-прежнему открывается из строки, загружает направления, создает новое направление, редактирует существующее через `PATCH`, подтверждает удаление через dialog и после операций обновляет направления и summary. Измененный e2e проходит create/edit/delete сценарий.

7. F22 safe-sync не ослаблен: passed for F23 diff.

   F23 frontend не добавляет путь, который отправляет unsafe zero. Для строк без FBS-пула локальный switch disabled через `canToggle: false`, bulk flow отправляет только selected product ids, а backend sync service на том же commit блокирует publish target с amount `0` через `ERROR_UNSAFE_ZERO_BLOCKED`. В review scope не найден новый frontend route, который превращает missing/unknown FBS-пул в `0`.

8. E2E meaningful and stable: passed.

   Тест проходит реальный seller UI: готовит товар и складской остаток, открывает seller catalog, проверяет отсутствие старых bulk-кнопок и `Лимит`, выбирает строку, подтверждает bulk action, проверяет request body `product_ids: [productId]`, затем проходит drawer CRUD. Network waits подписаны до клика через `Promise.all`, что снижает race risk.

## Проверки

- `git diff --quiet 0090a76 -- frontend/src/screens/v2/SellerProductsStockScreen.tsx frontend/tests-e2e/seller-stock-directions.spec.ts` -> passed; рабочие копии этих двух файлов совпадают с review commit.
- `npm run build` в `frontend/` -> passed.
- `npx playwright test frontend/tests-e2e/seller-stock-directions.spec.ts --project=chromium` в `frontend/` -> passed, 1 test.

## Остаточный риск

В рабочем дереве есть много чужих незакоммиченных изменений вне F23 review scope. Они не использовались как основание для product approval и не включаются в этот verdict. Перед интеграцией F23 все равно нужен отдельный Browser Product QA по протоколу: code review не заменяет живой проход в браузере.

## Итог

`CODE_REVIEW_PASSED`.
