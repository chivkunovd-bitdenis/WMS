# DEV · 06-picking-list-order · атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — **красный на существующих зависимостях вне разрешённых файлов атома**. Ошибки: `frontend/src/ui-kit/Cells.tsx:89` использует отсутствующий в MUI 9 prop `inputProps`; `frontend/src/ui-kit/ModalFrame.tsx:32-33` использует отсутствующий prop `disableEscapeKeyDown`, а параметр `reason` не используется. В изменённых файлах TypeScript-ошибок нет.
- `python3 scripts/ui/ui_guard.py` из корня — **красный на существующих файлах вне разрешённых файлов атома**: `frontend/src/components/WbProductPickerDialog.tsx` (`экран-монолит 0 → 646`) и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx` (`экран-монолит 1111 → 1169`). Базовая линия не обновлялась. По затронутым экранам проверка сообщает улучшения: `FfFbsPickList.tsx` — убраны локальные чип, кнопки и таблица; `FfFbsSupplyWorkspace.tsx` — монолит уменьшен.
- `npm run test:unit` из `frontend/` — **зелёный**: 21 файл, 149 тестов пройдены. Добавлены проверки полного серверного набора ID, порядка `WB → WMS № K`, сохранения номера вокруг пропущенного стикера и использования сохранённого изображения Честного знака вместо текстового КИЗ.

## Не реализовано

- Нельзя буквально сдать зелёные `tsc` и `ui_guard.py`, не меняя запрещённые этим атомом соседние файлы. Конкретные внешние ошибки перечислены в разделе «Гейты»; файлы и базовая линия не тронуты.
- Живой браузерный проход не выполнялся: роль `screen-dev` реализует экран и unit-проверки, но не подменяет роль проверки готового результата.
- Commit создать не удалось: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` из-за `Operation not permitted`. Метаданные общего Git-каталога находятся вне разрешённой для записи рабочей копии; изменения остаются локальными и незакоммиченными.
