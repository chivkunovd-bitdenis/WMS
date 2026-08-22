## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/ModalFrame.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/Actions.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/UiKitShowcase.tsx`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не пройдено: локальный TypeScript не установлен, `npx` не смог скачать пакет из-за `ENOTFOUND registry.npmjs.org`.
- `python3 scripts/ui/ui_guard.py` — не пройдено: обнаружены новые нарушения в несвязанных и не изменённых файлах `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/components/WbProductPickerDialog.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не изменялась.
- `npm run test:unit` — не пройдено: `vitest: command not found`.

## Не реализовано

- Находки 1–7 из `REVIEW.md` относятся к backend и экрану S-03, а не к разрешённому атомарному UI-kit куску; эти файлы не изменялись.
- В пределах UI-kit исправлены состояния `busy`: системное закрытие `ModalFrame` блокируется, а `PrintAction` показывает индикатор и понятную причину недоступности.
