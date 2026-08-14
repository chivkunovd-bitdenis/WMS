# F19 Product / UX Review: возврат со сканированием и автопечатью ШК

Дата: 2026-08-13  
Роль: isolated Product / UX Review Agent  
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`

## Verdict

`PRODUCT_REWORK_REQUIRED`

## Rationale

BA artifact для F19 задает правильный складской контур: возврат остается вариантом приемки, оператор сканирует товар в том же scan flow, успешный скан увеличивает факт на +1, а режим автопечати должен печатать ШК WB после скана без отдельной печатной формы.

Текущий экран в целом идет в правильную сторону:

- тип операции виден в шапке документа: `Тип: Возврат`;
- scan panel остается тем же процессом, без новой вкладки или отдельного экрана;
- переключатель `Печатать ШК при скане` отрисовывается только при `operation_type === 'return'`;
- сам scan handler после успешного POST `/receiving/scan` вызывает прямую печать через `printBarcodeLabel`, а не открывает `MarkingPrintDialog`;
- backend scan contract увеличивает loose-факт на `+1`.

Но до dev approval есть продуктовые расхождения с F19:

1. Автопечать срабатывает не только при скане. В `applyPicker` и `onManualProductCreated` при `isReturnOperation && returnAutoPrint` тоже вызывается `printReturnBarcodeForLine`. Для оператора переключатель называется "при скане", поэтому печать после ручного добавления факта или создания товара будет неожиданной и может напечатать лишние этикетки.
2. Автопечать может напечатать не WB-штрихкод. `printReturnBarcodeForLine` берет `(line.wb_barcode ?? line.sku_code)`. BA требует печать ШК WB; fallback на `sku_code` рискован, потому что SKU и WB barcode в тесте и модели являются разными полями. При отсутствии `wb_barcode` лучше показать понятную ошибку и не печатать, пока продуктово не утвержден другой тип этикетки.
3. Мелкая UX-точка: на возврате секция все еще называется `Скан приёмки`. Это не ломает поток, потому что в шапке видно `Возврат`, но для складского оператора лучше адаптировать заголовок/копирайт к возврату, чтобы действие не выглядело как обычная приемка.
4. Playwright coverage проверяет return-autoprint happy path, но не закрывает два ограничения из acceptance: нет negative assertion, что переключатель отсутствует на обычной приемке, и нет явной проверки, что после автопечати не появился `marking-print-dialog`.

## Exact Rework

Перед `PRODUCT_APPROVED_FOR_DEV` нужно:

- ограничить автопечать только successful scan path `scanToReceiving`;
- убрать автопечать из non-scan действий `applyPicker` и `onManualProductCreated`, либо переименовать/переутвердить режим как более широкий, если бизнес действительно хочет печать на ручных добавлениях;
- печатать именно `line.wb_barcode`; если WB barcode отсутствует, показывать оператору ошибку и не печатать fallback SKU без отдельного product approval;
- желательно заменить заголовок scan panel для возврата на возвратный вариант, например `Скан возврата`;
- усилить `inbound-receiving-v2.spec.ts`: на обычной приемке проверить отсутствие `ff-inbound-return-autoprint`, а в F19-сценарии после scan/autoprint проверить отсутствие `marking-print-dialog`.

## Screens / Artifacts Checked

- `docs/reviews/product-operations-ux/2026-08-12/ITERATION_BA_FEATURE_SPEC_RU.md`, F19 lines 153-159.
- `frontend/src/screens/ff/FfInboundRequestView.tsx`: operation type display, scan panel, return autoprint switch, scan handler, print helper, non-scan add paths.
- `frontend/src/utils/printBarcodeLabel.ts`: direct iframe print helper, no product selection / manual print dialog.
- `backend/app/api/inbound_intake.py` and `backend/app/services/inbound_intake_service.py`: `/receiving/scan` route and `+1` loose actual quantity contract.
- `frontend/tests-e2e/inbound-receiving-v2.spec.ts`: F19 return scenario and existing receiving scenarios.

## Assumptions

- This is Product / UX gate, not Browser Product QA; I did not run a live browser scenario.
- I reviewed source and Playwright test intent only; I did not edit code and did not execute the test suite.
- Manual line print opening `MarkingPrintDialog` remains acceptable outside F19 auto-print; the blocker is only auto-print behavior after scan.
