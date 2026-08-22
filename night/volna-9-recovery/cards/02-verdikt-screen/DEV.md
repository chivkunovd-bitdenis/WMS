## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/fbsApi.ts
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/utils/metaStatus.ts

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: локальный `tsc` отсутствует, `npx` не смог скачать пакет из-за `ENOTFOUND` (сеть недоступна).
- `python3 scripts/ui/ui_guard.py` — красный: обнаружены новые нарушения в `WbProductPickerDialog.tsx`, `FfFbsSupplyWorkspace.tsx` и `SellerInboundDraftScreen.tsx`; эти файлы не изменялись в рамках карточки.
- `npm run test:unit` — красный: `vitest: command not found`, зависимости фронтенда не установлены.

## Не реализовано

Пунктов контракта, относящихся к этому атомарному куску, не осталось. Тип вердикта ограничен серверным словарём, поля источника истины доступны только для чтения, а отображение всех контрактных состояний и неизвестных причин централизовано в `metaStatusView`.
