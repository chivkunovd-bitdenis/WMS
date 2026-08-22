# Реализация · 06-picking-list-order

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md`

В окне печати, созданном непосредственно жестом оператора, лента теперь сохраняет напечатанные коды «Честного знака», затем этикетку WB и служебную этикетку WMS с постоянным номером. При блокировке всплывающего окна операция на сервер не запускается, а оператор видит понятную ошибку.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — зелёный.
- `npm run test:unit -- --run src/screens/v2/FfFbsPickList.test.ts` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — зелёный.
- `python3 scripts/ui/ui_guard.py` из корня — красный только на уже существующих чужих экранах: `src/components/WbProductPickerDialog.tsx` (экран-монолит `0 → 646`) и `src/screens/v2/SellerInboundDraftScreen.tsx` (экран-монолит `1111 → 1169`). Базовую линию не менял.
- `git diff --check` — зелёный.

## Не реализовано

- Прямые Playwright-сценарии `S-03-TC-001…007` не добавлены: `FfFbsPickList` не импортируется и не монтируется ни одним файлом в `frontend/src`, а подключение модалки требует правки `FfFbsSupplyWorkspace.tsx`, которого нет в разрешённом списке атома. Текущий unit-тест покрывает исправленную физическую последовательность ленты с кодом маркировки.
- Серверная проверка «клиент передал полный актуальный состав поставки» из замечания ревью относится к `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_order_tape_print_service.py` и не входит в роль screen-dev.
- Исправление общего предпросмотра из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.tsx` не выполнено: это отдельный прямо названный ревьюером файл, но он не включён в ограниченный список текущего атома.

## Находки

Нет.
