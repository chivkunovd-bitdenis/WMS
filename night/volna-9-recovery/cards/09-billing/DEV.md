# 09-billing — screen-dev

## Изменённые файлы

В рамках атома «Общая денежная ячейка и печать счёта» изменений в исходных файлах не потребовалось: требуемая реализация уже присутствует в checkout.

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Cells.tsx` — `MoneyCell` и `formatMoney`: RUB, две цифры, сторно без сигнальной окраски, правое выравнивание.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Actions.tsx` — `PrintAction` принимает `what="счёт"` и формирует подпись «Печать счёта».
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/index.ts` — экспортирует `MoneyCell`, `formatMoney` и `PrintAction`.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: команда `npx` зависла без вывода в окружении без доступного локального результата.
- `python3 scripts/ui/ui_guard.py` — красный из-за пяти ранее существующих нарушений в чужих файлах (`src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`); файлы этого атома не указаны.
- `npm run test:unit` — красный: `vitest: command not found`.
- Адресный unit-тест `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Cells.test.ts` уже покрывает положительную сумму, ноль, сторно и `—`.

## Не реализовано

По относящимся к этому атому пунктам контракта нереализованных требований не обнаружено. Находки `REVIEW.md` относятся к backend и соседним экранам; исправление их выходило бы за границы разрешённых файлов этого атома.
