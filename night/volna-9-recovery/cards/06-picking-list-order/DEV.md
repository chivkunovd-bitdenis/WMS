## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx — полная печать получает свежий серверный состав поставки; построчный запрос сохраняет переданный набор ID.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.tsx — служебная этикетка WMS выводится только для заказных стикеров и включается отдельной страницей в печать; пропущенные стикеры показываются через ErrorNotice.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не выполнен: в рабочей копии нет локального `tsc`, а сетевой fallback завершился `ENOTFOUND registry.npmjs.org`.
- `python3 scripts/ui/ui_guard.py` — красный из-за двух существующих нарушений вне атома: `frontend/src/components/WbProductPickerDialog.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Для изменённого `FfFbsSupplyWorkspace.tsx` нового нарушения после правки нет.
- `npm run test:unit` — не выполнен: `vitest: command not found`.
- `git diff --check` — зелёный.

## Не реализовано

- Полный живой browser-сценарий и unit-тесты предпросмотра не подтверждены: в окружении отсутствуют frontend-зависимости, поэтому проверить их запуском невозможно.
- Находки ревью по `FfFbsPickList.tsx`, backend и серверной ручке не изменялись: они находятся вне трёх файлов этого атома и его разрешённой границы.
