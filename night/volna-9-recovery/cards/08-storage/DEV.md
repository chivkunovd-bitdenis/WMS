## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.test.tsx`

В `PrintAction` закреплена внутренняя таблица подписей, включая `what="накладную"`; публичный интерфейс компонента не изменён. Добавлены проверки подписей для `row` и `panel`, сохранения существующей подписи и disabled-причины.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный из-за трёх посторонних нарушений базовой линии в `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; мои файлы их не затрагивают, базовая линия не обновлялась.
- `npx vitest run src/ui-kit/Actions.test.tsx` — не завершился в отведённое время без вывода, остановлен.
- `npm run test:unit` — не завершён: общий запуск остановлен после зависания Vitest без вывода.
- Commit не создан: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` из-за ограничения доступа к служебному каталогу worktree.

## Не реализовано

- Буквально не добавлялся новый член публичного типа `Printable`: `накладную` уже присутствовал в исходной ветке. Закреплена недостающая внутренняя таблица подписей и покрыт требуемый сценарий.
