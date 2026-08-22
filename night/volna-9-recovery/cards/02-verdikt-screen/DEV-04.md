# Screen Dev · 02-verdikt-screen · feature 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-orders.spec.ts`

Старый локальный признак `Отклонено WB` удалён из существующей зоны статуса. Экран использует серверный `metadata.verdict`, `StatusChip` и `TextCell`; новой колонки, заливки строки и отдельного состояния загрузки не добавлено. В e2e добавлен UI-сценарий для принятого, необязательного, отклонённого и недоступного ответа WB, включая русскую причину и текст `Сдача пока недоступна`.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — FAIL/BLOCKED: локальный `frontend/node_modules` отсутствует, бинарник `tsc` недоступен; скачивание зависимостей не выполнялось.
- `python3 scripts/ui/ui_guard.py` — FAIL по существующей baseline-ситуации: новые нарушения обнаружены только в несвязанных файлах `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Для целевого `FfFbsOrdersScreen.tsx` guard показал улучшение: `свой-чип 2 → 1`, `экран-монолит 1587 → 1577`.
- `npm run test:unit` — FAIL/BLOCKED: `vitest: command not found`, локальные зависимости frontend отсутствуют.

## Не реализовано

- Полный запуск TypeScript и unit-тестов невозможен без локально установленных зависимостей; сеть для их установки не использовалась.
- Browser e2e локально не запускался по той же причине; тест добавлен с пользовательскими действиями и проверками видимого результата.

## Находки

Нет.
