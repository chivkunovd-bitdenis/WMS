# DEV · 06-picking-list-order · атом 1 · переделка по REVIEW

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/ModalFrame.tsx` — убран отсутствующий в установленной MUI 9 prop `disableEscapeKeyDown`; управляемая модалка по-прежнему игнорирует любой запрос закрытия, пока `busy=true`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/Cells.tsx` — aria-подпись `CheckCell` передаётся в нативный input через актуальный MUI API `slotProps.input`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/PickingListPrimitives.test.ts` — точечная проверка `ModalFrame` приведена к актуальному публичному контракту компонента и продолжает доказывать блокировку закрытия в состоянии `busy`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — записан отчёт переделки атома.

Остальные разрешённые файлы атома уже содержат требуемые `ChoiceFilter`, `PrintAction` со значением `стикеры заказов`, экспорты и изолированную демонстрацию всех четырёх элементов в `UiKitShowcase`; находка ревью не потребовала их изменения.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **зелёный**, код завершения 0.
- `npm run test:unit -- src/ui-kit/PickingListPrimitives.test.ts` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **зелёный**, 1 файл и 4 теста пройдены.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` — **красный только на двух существующих нарушениях вне файлов атома**: `frontend/src/components/WbProductPickerDialog.tsx` (`экран-монолит 0 → 646`) и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx` (`экран-монолит 1111 → 1169`). Для карточки guard фиксирует улучшения в `FfFbsPickList.tsx` и `FfFbsSupplyWorkspace.tsx`; новых нарушений в UI-kit нет, базовая линия не менялась.
- `git diff --check -- frontend/src/ui-kit/ModalFrame.tsx frontend/src/ui-kit/Cells.tsx frontend/src/ui-kit/PickingListPrimitives.test.ts night/volna-9-recovery/cards/06-picking-list-order/DEV.md` из корня рабочей копии — **зелёный**, код завершения 0.
- `git add -- frontend/src/ui-kit/ModalFrame.tsx frontend/src/ui-kit/Cells.tsx frontend/src/ui-kit/PickingListPrimitives.test.ts night/volna-9-recovery/cards/06-picking-list-order/DEV.md && git diff --cached --check && git commit -m "fix(ui-kit): support MUI 9 picking primitives"` из корня рабочей копии — **красный из-за ограничения среды**: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` (`Operation not permitted`). Несвязанные изменения оркестратора в коммит не добавлялись.

## Не реализовано

- Находки 1, 3–6 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/REVIEW.md` относятся к реестру экрана, продуктовой модалке, backend-сервису, общему предпросмотру печати и браузерным сценариям. Они не относятся к файлам и слою атома 1, поэтому в этой переделке не исправлялись.
- Полностью зелёный `ui_guard.py` нельзя получить в границе атома: оба новых нарушения находятся в запрещённых для этой роли соседних экранах. Храповая базовая линия намеренно не обновлялась.
- Отдельный восстанавливаемый commit SHA не создан: общая Git-метапапка worktree находится вне доступной для записи области. Исправление локально реализовано, но не сохранено в Git.
- Следующие атомы из `FEATURES.md` не выполнялись.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
