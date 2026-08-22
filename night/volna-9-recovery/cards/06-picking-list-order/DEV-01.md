# DEV · 06-picking-list-order · атом 1 · переделка

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/Actions.tsx` — вариант `PrintAction` со значением `стикеры заказов` теперь показывает контрактную подпись `Печать стикеров`, а не неграмматичное `Печать стикеры заказов`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/PickingListPrimitives.test.ts` — добавлена изолированная проверка `ModalFrame`, `ChoiceFilter`, `CheckCell` и `PrintAction`: блокировка закрытия при `busy`, выбор фильтра, недоступные состояния с причиной и печать стикеров заказов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — записан отчёт переделки атома.

Остальные разрешённые файлы атома уже содержат требуемые `ModalFrame`, `ChoiceFilter`, `CheckCell`, их экспорты и состояния в `UiKitShowcase`; повторных изменений им не потребовалось.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — красный из-за среды: локального `tsc` нет, а `npx` не смог обратиться к `registry.npmjs.org` (`ENOTFOUND`).
- `python3 scripts/ui/ui_guard.py` из корня рабочей копии — красный только на двух существующих файлах вне атома: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/components/WbProductPickerDialog.tsx` (`экран-монолит 0 → 646`) и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/SellerInboundDraftScreen.tsx` (`экран-монолит 1111 → 1169`). Для `FfFbsPickList.tsx` храповик сообщил три улучшения; новых нарушений в UI-kit нет. Базовая линия не менялась.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — красный из-за среды: локальный `vitest` отсутствует (`sh: vitest: command not found`). Тест добавлен, но выполнить его в этой рабочей копии невозможно без установленных зависимостей.
- `git diff --check` для изменённых файлов атома — зелёный.
- `git commit -m "fix(ui-kit): verify picking list primitives"` — красный из-за ограничений рабочей среды: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` (`Operation not permitted`). Изменения локально реализованы, но отдельный восстанавливаемый commit SHA не создан.

## Не реализовано

- Находки 1–4 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/REVIEW.md` относятся к подключению продуктовой модалки, физической ленте с DataMatrix и тестам экрана в `FfFbsSupplyWorkspace.tsx`, `FfFbsPickList.tsx` и `FfFbsPickList.test.ts`. Эти файлы принадлежат последующим атомам и не входят в заданный слой переиспользуемых элементов, поэтому в атоме 1 они не менялись.
- Буквально прогнать новый unit-тест не удалось только из-за отсутствующего локального `vitest`; результат теста не объявляется зелёным.
- Сохранить переделку отдельным Git-коммитом не удалось из-за запрета записи в общие метаданные worktree; до коммита изменения остаются уязвимыми к потере.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
